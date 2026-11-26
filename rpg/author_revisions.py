"""Review and apply author proposals without changing a playable project until approval."""

import argparse
import copy
import difflib
import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from .authoring import compile_project


FIXED_FIELDS = {"author_schema", "id", "version", "locks"}


def encode(document) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pointer(path: str) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError(f"Invalid JSON pointer: {path!r}")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def child(container, key: str):
    if isinstance(container, list):
        if not re.fullmatch(r"0|[1-9][0-9]*", key):
            raise ValueError(f"Invalid array index: {key!r}")
        return int(key)
    if isinstance(container, dict):
        return key
    raise ValueError("The path crosses a value that is neither an object nor an array.")


def at(document, keys: list[str]):
    value = document
    for key in keys:
        try:
            value = value[child(value, key)]
        except (KeyError, IndexError) as error:
            raise ValueError(f"Unknown project path /{'/'.join(keys)}") from error
    return value


def same(left, right) -> bool:
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def validate_project(project: dict, root: Path, *, no_art=False):
    if not isinstance(project, dict):
        raise ValueError("An author project must be an object.")
    for path in project.get("locks", []):
        at(project, pointer(path))
    if no_art:
        project = {key: value for key, value in project.items() if key != "art"}
    for variant in (None, *project.get("puzzle_variants", {})):
        compile_project(project, root=root, variant=variant)


def check_locks(project: dict, updated: dict):
    for locked in project.get("locks", []):
        keys = pointer(locked)
        try:
            unchanged = same(at(project, keys), at(updated, keys))
        except ValueError:
            unchanged = False
        if not unchanged:
            raise ValueError(f"The revision changes the locked field {locked}.")


def revise(original: bytes, proposal: dict, project_dir: Path, only: list[int] | None = None):
    if not isinstance(proposal, dict) or proposal.get("proposal_schema") != 1:
        raise ValueError("Expected a proposal with proposal_schema 1.")
    if proposal.get("base_sha256") != digest(original):
        raise ValueError("The proposal targets a different project revision. Prepare a new proposal from this project.")
    edits = proposal["edits"]
    if not isinstance(edits, list) or not edits:
        raise ValueError("A proposal needs at least one field edit.")
    indices = set(only) if only else set(range(1, len(edits) + 1))
    if any(index < 1 or index > len(edits) for index in indices):
        raise ValueError("An --only number is outside the proposal.")
    project = json.loads(original)
    updated = copy.deepcopy(project)
    changes = []
    selected_paths = []
    for index in sorted(indices):
        edit = edits[index - 1]
        if not isinstance(edit, dict) or set(edit) != {"path", "before", "after"}:
            raise ValueError(f"Edit {index} must contain path, before and after.")
        path = edit["path"]
        keys = pointer(path)
        if keys[0] in FIXED_FIELDS:
            raise ValueError(f"Edit {index} cannot change {path}.")
        if any(keys[:len(previous)] == previous or previous[:len(keys)] == keys
               for previous in selected_paths):
            raise ValueError(f"Overlapping edit at {path}. Combine the edits before reviewing.")
        if not same(at(project, keys), edit["before"]):
            raise ValueError(f"Edit {index} expected a different current value at {path}.")
        if same(edit["before"], edit["after"]):
            raise ValueError(f"Edit {index} does not change {path}.")
        parent = at(updated, keys[:-1])
        parent[child(parent, keys[-1])] = edit["after"]
        selected_paths.append(keys)
        changes.append((index, edit))
    check_locks(project, updated)
    validate_project(updated, project_dir)
    return updated, changes


def show_changes(changes):
    for index, edit in changes:
        print(f"\n{index}. {edit['path']}")
        before = encode(edit["before"]).decode("utf-8").splitlines()
        after = encode(edit["after"]).decode("utf-8").splitlines()
        for line in difflib.unified_diff(before, after, fromfile="current", tofile="proposed", lineterm=""):
            print(line)


def history_dir(project: Path) -> Path:
    return project.parent / ".author-history" / project.name


def snapshots(project: Path) -> list[Path]:
    return sorted(history_dir(project).glob("*.json"))


def save_revision(project: Path, original: bytes, replacement: bytes):
    directory = history_dir(project)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".apply-lock"
    try:
        lock_handle = lock.open("x")
    except FileExistsError as error:
        raise ValueError("Another revision is being written. Check the author history lock if it was interrupted.") from error
    temporary = None
    try:
        with lock_handle:
            if project.read_bytes() != original:
                raise ValueError("The project changed before approval. Review the proposal again.")
            snapshot = directory / f"{digest(original)}.json"
            if not snapshot.exists():
                with snapshot.open("xb") as saved:
                    saved.write(original)
            with NamedTemporaryFile(dir=project.parent, prefix=f".{project.stem}-",
                                    suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(replacement)
            os.replace(temporary, project)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def commit_revision(project: Path, original: bytes, updated: dict) -> int:
    versions = [json.loads(snapshot.read_bytes())["version"] for snapshot in snapshots(project)]
    version = max([updated["version"], *versions]) + 1
    save_revision(project, original, encode({**updated, "version": version}))
    return version


def restore_revision(project: Path, original: bytes, prefix: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{8,64}", prefix):
        raise ValueError("Use a revision hash or at least eight characters from history.")
    matches = [path for path in snapshots(project) if path.stem.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("The revision hash does not identify a unique saved snapshot.")
    snapshot = matches[0]
    restored = snapshot.read_bytes()
    if digest(restored) != snapshot.stem:
        raise ValueError("The saved revision has been modified.")
    validate_project(json.loads(restored), project.parent)
    save_revision(project, original, restored)
    return snapshot.stem


def prepare_prompt(source: Path, draft: bool, scopes: list[str], request: str) -> str:
    if draft:
        return (
            "Create an author project as a JSON object with author_schema 1, id, version, title, brief, "
            "start, goal, flags, mandatory_clues, locations, characters, clues, actions, gates, puzzles and playtests. "
            "Make a small mystery using the brief below. Locations are objects with id, name, description and exits. "
            "Characters have id, location, name, opening_reply and reveals. Clues have id, kind and text. "
            "Actions have location, verb, target, message, requires and sets as applicable. "
            "Gates have from, to and requires. Write ordinary talk as character opening replies, "
            "movement as exits and solve commands through the symbol_sequence puzzle, if used. "
            "A symbol puzzle has template, location, symbols, sequence, solved_flag and success_reply. "
            "Playtests map route names to arrays of verb and target objects. Use real actions to reach the goal flag. "
            "Use lowercase stable IDs and leave out image references unless available to the author. Return just the JSON.\n\n"
            f"Request\n{request}\n\nAuthor brief\n{source.read_text(encoding='utf-8')}\n"
        )
    if not scopes:
        raise ValueError("Choose scoped project sections with --scope, such as /characters/0.")
    original = source.read_bytes()
    project = json.loads(original)
    selected = {scope: at(project, pointer(scope)) for scope in scopes}
    return (
        "Propose edits only to the supplied sections of a terminal mystery author project. "
        "Return a JSON object with proposal_schema 1, the exact base_sha256, and edits. "
        "Each edit has path (a JSON pointer), before (the exact existing JSON value), "
        "and after (the replacement value). Use disjoint paths. Keep locked fields unchanged. "
        "Mention any related work in the response only by proposing the corresponding supplied fields. "
        "Return just the JSON. The author will review and validate all edits before applying them.\n\n"
        f"Request\n{request}\n\n"
        + encode({"base_sha256": digest(original), "locked_paths": project.get("locks", []),
                  "sections": selected}).decode("utf-8")
    )


def register(actions):
    for name in ("fingerprint", "history", "review", "apply", "rollback"):
        parser = actions.add_parser(name)
        parser.add_argument("project", type=Path)
        if name in {"review", "apply"}:
            parser.add_argument("proposal", type=Path)
            parser.add_argument("--only", type=int, nargs="+", metavar="EDIT")
        if name == "rollback":
            parser.add_argument("--to", required=True, help="A revision hash from history")
    parser = actions.add_parser("prepare", help="Write an offline draft or scoped revision prompt")
    parser.add_argument("project", type=Path, help="An author project, or a text brief with --draft")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser = actions.add_parser("import-draft", help="Validate an imported draft as a new author project")
    parser.add_argument("draft_file", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser = actions.add_parser("suggest", help="Generate a draft or proposal from a selected prompt file")
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--provider", choices=("ollama", "openai", "claude"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context", type=int, help="Context size for Ollama authoring (default 8192)")
    parser.add_argument("--output", required=True, type=Path)


def write_new(path: Path, data: bytes):
    with path.open("xb") as output:
        output.write(data)


def run(args):
    if args.action == "suggest":
        from .author_provider import suggest

        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}")
        result = suggest(args.provider, args.model, args.prompt_file.read_text(encoding="utf-8"),
                         context=args.context)
        write_new(args.output, encode(result))
        print(f"Saved a proposal to {args.output} for author review.")
        return
    if args.action == "import-draft":
        draft = json.loads(args.draft_file.read_bytes())
        validate_project(draft, args.output.parent)
        write_new(args.output, encode(draft))
        print(f"Imported a validated author project to {args.output}.")
        return
    project = args.project.resolve()
    if args.action == "prepare":
        prompt = prepare_prompt(project, args.draft, args.scope, args.request)
        write_new(args.output, prompt.encode("utf-8"))
        print(f"Saved an author prompt to {args.output}.")
        return
    original = project.read_bytes()
    if args.action == "fingerprint":
        print(digest(original))
    elif args.action == "history":
        print(f"{digest(original)}  current  v{json.loads(original)['version']}")
        for snapshot in snapshots(project):
            print(f"{snapshot.stem}  saved  v{json.loads(snapshot.read_bytes())['version']}")
    elif args.action == "rollback":
        restored = restore_revision(project, original, args.to)
        print(f"Restored {restored} and saved the displaced project in history.")
    else:
        proposal = json.loads(args.proposal.read_bytes())
        updated, changes = revise(original, proposal, project.parent, args.only)
        show_changes(changes)
        if args.action == "review":
            print("\nValid proposal. Use apply to accept the displayed edits.")
        else:
            version = commit_revision(project, original, updated)
            print(f"\nAccepted {len(changes)} edits as version {version}.")
