"""Compile an author project to a playable RPG pack and test its routes."""

import argparse
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .engine import Command, Pack, State
from .terminal_art import ART_STYLES, convert_image


ART_OPTIONS = ("alt", "width", "height", "mode", "crop", "contrast", "style")


def art_source(root: Path, entry: dict) -> Path:
    root = root.resolve()
    source = (root / entry["source"]).resolve()
    if not source.is_relative_to(root):
        raise ValueError(f"Art source for {entry['id']} is outside the author project.")
    return source


def art_options(entry: dict) -> dict:
    return {key: entry[key] for key in ART_OPTIONS if key in entry}


@dataclass(frozen=True)
class Build:
    data: dict
    pack: Pack
    routes: dict[str, list[Command]]


def unique_ids(entries, label, fields):
    result = {}
    for entry in entries:
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or not entry_id or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in entry_id
        ):
            raise ValueError(f"Invalid {label} ID: {entry_id!r}. Use lowercase letters, digits, _ or -.")
        if entry_id in result:
            raise ValueError(f"Duplicate {label} ID: {entry_id}")
        result[entry_id] = {name: value for name, value in entry.items() if name in fields}
    return result


def compile_project(project: dict, *, root: Path | None = None, variant: str | None = None) -> Build:
    if project["author_schema"] != 1:
        raise ValueError("Unsupported author project schema.")
    locations = unique_ids(project["locations"], "location", {"name", "description", "exits", "map", "map_label"})
    facts = unique_ids(project["clues"], "clue", {"title", "kind", "text", "certainty", "source",
                                                  "location", "witness", "question", "subjects", "links"})
    items = unique_ids(project.get("items", []), "item", {"name", "source"})
    characters = unique_ids(project["characters"], "character", {"name", "voice", "opening_question",
                                                               "location", "opening_reply", "reveals"})
    puzzles = project.get("puzzles", [])
    playtests = project.get("playtests", {})
    if variant is not None:
        options = project.get("puzzle_variants", {}).get(variant)
        if options is None:
            raise ValueError(f"Unknown puzzle variant: {variant}")
        puzzles = options["puzzles"]
        playtests = {**playtests, **options.get("playtests", {})}
        for location, description in options.get("location_descriptions", {}).items():
            locations[location]["description"] = description
        for npc, reply in options.get("character_replies", {}).items():
            characters[npc]["opening_reply"] = reply

    flags = set(project.get("flags", []))
    rules = []
    action_fields = {"location", "verb", "target", "message", "requires", "needs_items",
                     "needs_any_item", "sets", "gives", "consumes", "once", "blocked",
                     "accepts_evidence", "after"}
    for action in project.get("actions", []):
        if action["verb"] in {"move", "talk", "solve"}:
            raise ValueError(f"Define {action['verb']} through locations, characters, or puzzles.")
        rules.append({key: value for key, value in action.items() if key in action_fields})
    dialogue_style = {}
    for npc, character in characters.items():
        dialogue_style[npc] = {key: character[key] for key in ("name", "voice", "opening_question")
                               if key in character}
        rules.append({
            "location": character["location"], "verb": "talk", "target": npc,
            "message": character["opening_reply"], "sets": character.get("reveals", []),
        })

    puzzle_symbols, puzzle_views = {}, {}
    for puzzle in puzzles:
        location = puzzle["location"]
        if location in puzzle_symbols:
            raise ValueError(f"Only one puzzle can be placed at {location}.")
        template = puzzle["template"]
        sequence = puzzle["sequence"]
        if template == "symbol_sequence":
            symbols = puzzle["symbols"]
        elif template == "timeline_order":
            cards = unique_ids(puzzle["cards"], "timeline card", {"label"})
            symbols = list(cards)
            labels = {key: card["label"] for key, card in cards.items()}
            if any(not isinstance(label, str) or not label.isprintable() or len(label) > 60 for label in labels.values()):
                raise ValueError(f"Timeline cards at {location} need printable labels up to 60 characters.")
            puzzle_views[location] = {
                "title": puzzle.get("title", "Put the events in order"),
                "prompt": puzzle.get("prompt", "Choose the events from earliest to latest."),
                "menu": "Try timeline",
                "labels": labels,
                "wrong_order": "That order doesn't match the record.",
            }
        else:
            raise ValueError(f"Unsupported puzzle template at {location}: {template}")
        if (not isinstance(symbols, list) or not isinstance(sequence, list)
                or not 2 <= len(symbols) <= 6 or len(sequence) != len(symbols)
                or any(not isinstance(symbol, str) or not symbol.isascii() or not symbol.islower()
                       or not symbol.isalpha() or len(symbol) > 12 for symbol in symbols)
                or len(set(symbols)) != len(symbols)
                or any(symbol not in symbols for symbol in sequence)
                or (template == "timeline_order" and set(sequence) != set(symbols))):
            label = "timeline" if template == "timeline_order" else "symbol puzzle"
            raise ValueError(f"Incompatible {label} at {location}. Use 2–6 distinct lowercase "
                             "ASCII words and a solution of matching length using those words. "
                             "A timeline must use each card once.")
        solved_flag = puzzle["solved_flag"]
        if solved_flag in flags or solved_flag in facts:
            raise ValueError(f"Puzzle at {location} needs a unique solved flag: {solved_flag}")
        flags.add(solved_flag)
        puzzle_symbols[location] = symbols
        rules.append({
            "location": location, "verb": "solve", "target": " ".join(sequence),
            "message": puzzle["success_reply"], "requires": puzzle.get("requires", []),
            "sets": [solved_flag], "once": solved_flag,
        })

    data = {
        "schema": 1, "id": project["id"], "version": project["version"], "title": project["title"],
        "start": project["start"], "goal": project["goal"], "locations": locations,
        "facts": facts, "items": items, "flags": sorted(flags),
        "rules": rules, "gates": [{key: gate[key] for key in ("from", "to", "requires")}
                                  for gate in project.get("gates", [])], "puzzle_symbols": puzzle_symbols,
        "dialogue_style": dialogue_style, "puzzle_views": puzzle_views,
    }
    if variant:
        data["id"] = f"{data['id']}-{variant}"
    data.update(compile_assets(project.get("art", []), root, characters, locations))
    pack = Pack.from_data(data)
    mandatory = set(project.get("mandatory_clues", []))
    if mandatory - facts.keys():
        raise ValueError(f"Unknown mandatory clues: {', '.join(sorted(mandatory - facts.keys()))}")
    shortest = check_reachability(pack, mandatory)
    routes = {"shortest": shortest}
    for label, steps in playtests.items():
        if label in routes:
            raise ValueError(f"Reserved or duplicate playtest name: {label}")
        commands = [Command(**step) for step in steps]
        state = pack.start_state()
        for index, command in enumerate(commands, 1):
            if pack.goal in state.flags:
                raise ValueError(f"Playtest {label} continues after the ending at step {index}.")
            result = pack.step(state, command)
            if not result.accepted:
                raise ValueError(f"Playtest {label} failed at step {index} "
                                 f"({command.verb} {command.target}): {result.message}")
            state = result.state
        if pack.goal not in state.flags or not mandatory <= state.flags:
            raise ValueError(f"Playtest {label} did not finish with all mandatory clues.")
        routes[label] = commands
    return Build(data, pack, routes)


def compile_assets(entries, root: Path | None, characters: dict, locations: dict) -> dict:
    if not entries:
        return {}
    if root is None:
        raise ValueError("A project directory is required to resolve source images.")
    root = root.resolve()
    assets, portraits, scenes = {}, {}, {}
    for asset_id, entry in unique_ids(entries, "art", {"id", "source", "portrait", "scene", *ART_OPTIONS}).items():
        source = art_source(root, entry)
        npc, location = entry.get("portrait"), entry.get("scene")
        if (npc is None) == (location is None):
            raise ValueError(f"Assign {asset_id} to one character portrait or one location scene.")
        if npc is not None:
            if npc not in characters or npc in portraits:
                raise ValueError(f"Unknown character or duplicate portrait: {npc}")
            portraits[npc] = asset_id
        else:
            if location not in locations or location in scenes:
                raise ValueError(f"Unknown location or duplicate scene: {location}")
            scenes[location] = asset_id
        assets[asset_id] = convert_image(source, **art_options(entry)).as_data()
    return {"assets": assets, "portraits": portraits, "scenes": scenes}


def check_reachability(pack: Pack, mandatory: set[str]) -> list[Command]:
    start = pack.start_state()
    queue = deque([start])
    paths = {start: None}
    observed_flags = set()
    observed_states = set()

    while queue:
        state = queue.popleft()
        observed_flags.update(state.flags)
        observed_states.add(state.location)
        if pack.goal in state.flags:
            if mandatory <= state.flags:
                route = []
                while paths[state] is not None:
                    state, command = paths[state]
                    route.append(command)
                return route[::-1]
            continue
        commands = [Command("move", destination) for destination in pack.locations[state.location]["exits"]]
        commands.extend(command for location, command in pack.rules if location == state.location)
        for command in commands:
            result = pack.step(state, command)
            if not result.accepted:
                continue
            # The current engine's rules depend on location, flags and inventory. Ignore the turn counter.
            next_state = State(result.state.location, result.state.flags, result.state.inventory)
            if next_state in paths:
                continue
            if len(paths) >= 25_000:
                raise ValueError("Reachability search exceeded 25,000 states. Reduce the pack's branching.")
            paths[next_state] = state, command
            queue.append(next_state)

    missing = mandatory - observed_flags
    details = ["No playable route reaches the ending with all mandatory clues."]
    if missing:
        details.append(f"Unreachable mandatory clues: {', '.join(sorted(missing))}.")
    blocked = [
        f"{source} -> {destination} requires {flag}"
        for (source, destination), flag in pack.gates.items()
        if source in observed_states and flag not in observed_flags
    ]
    if blocked:
        details.append(f"Unreachable gate prerequisites (possible circular gates): {'; '.join(blocked)}.")
    raise ValueError(" ".join(details))


def load_project(path: Path, *, variant: str | None = None, no_art: bool = False) -> Build:
    data = json.loads(path.read_text(encoding="utf-8"))
    if no_art:
        data.pop("art", None)
    try:
        return compile_project(data, root=path.parent, variant=variant)
    except KeyError as error:
        raise ValueError(f"Missing author project field: {error}") from error


def main(argv=None):
    from . import author_revisions

    parser = argparse.ArgumentParser(description="Validate and bake an Ashenfell author project.")
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("validate", "bake", "walkthrough"):
        command = actions.add_parser(action)
        command.add_argument("project", type=Path)
        command.add_argument("--variant", help="Use a named puzzle variant from the author project")
        command.add_argument("--no-art", action="store_true", help="Build or test a text-only preview")
        if action == "bake":
            command.add_argument("--output", type=Path, required=True, help="New runtime JSON file")
    preview = actions.add_parser("art", help="Preview a local image as plain ASCII")
    preview.add_argument("image", type=Path)
    preview.add_argument("--width", type=int, default=24)
    preview.add_argument("--height", type=int, default=10)
    preview.add_argument("--crop", nargs=4, type=int)
    preview.add_argument("--contrast", type=float, default=1.15)
    preview.add_argument("--style", choices=ART_STYLES)
    gallery = actions.add_parser("preview", help="Compare terminal art styles and save a choice to a project")
    gallery.add_argument("project", type=Path)
    gallery.add_argument("asset", help="The art entry's ID")
    gallery.add_argument("--record-revision", action="store_true", help="Validate and save the style in project history")
    author_revisions.register(actions)
    args = parser.parse_args(argv)
    try:
        if args.action not in {"validate", "bake", "walkthrough", "art", "preview"}:
            author_revisions.run(args)
            return
        if args.action == "preview":
            try:
                from .art_gallery import preview_project
            except ModuleNotFoundError as error:
                if error.name not in {"textual", "rich"}:
                    raise
                parser.exit(1, "Install requirements-tui.txt to use the interactive art preview.\n")
            preview_project(args.project, args.asset, record_revision=args.record_revision)
            return
        if args.action == "art":
            art = convert_image(args.image, alt="Image preview", width=args.width, height=args.height,
                                crop=args.crop, contrast=args.contrast, style=args.style)
            print("\n".join(art.ascii_rows))
            return
        build = load_project(args.project, variant=args.variant, no_art=args.no_art)
        if args.action == "bake":
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(build.data, ensure_ascii=False, indent=2) + "\n")
            print(f"Baked {build.pack.title} to {args.output}")
        elif args.action == "walkthrough":
            for name, commands in build.routes.items():
                print(f"\n{name} ({len(commands)} turns)")
                for command in commands:
                    print(f"  {command.verb} {command.target}")
        else:
            print(f"Valid: {build.pack.title}. {len(build.pack.locations)} locations, "
                  f"{len(build.pack.characters())} characters, {len(build.pack.facts)} clues, "
                  f"{len(build.routes) - 1} authored routes.")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"{getattr(args, 'project', getattr(args, 'image', 'authoring'))}: {error}\n")


if __name__ == "__main__":
    main()
