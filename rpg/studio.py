"""Interactive authoring workspace for playable mystery packs."""

import asyncio
import json
import re
import subprocess
import sys
from difflib import unified_diff
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Checkbox, Footer, Input, Label, OptionList, RichLog, Select, Static, TabbedContent, TabPane, Tabs, TextArea,
)
from textual.widgets.option_list import Option

from . import author_revisions as revisions
from .authoring import compile_project


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "authoring_examples" / "lantern_at_low_tide.json"
OPTIONAL_SECTIONS = {
    "actions": [], "art": [], "brief": {}, "flags": [], "gates": [], "items": [], "locks": [],
    "mandatory_clues": [], "playtests": {}, "puzzle_variants": {}, "puzzles": [],
}
ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError)


class FilePicker(ModalScreen[Path | None]):
    BINDINGS = [
        ("escape", "dismiss(None)", "Cancel"),
        ("backspace", "parent", "Up"),
    ]

    def __init__(self, title: str, folder: Path, suffix: str = "", *, filename: str | None = None):
        super().__init__()
        self.title_text = title
        self.folder = folder
        self.suffix = suffix
        self.filename = filename
        self.entries = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="file-picker"):
            yield Static(self.title_text, classes="form-title", markup=False)
            yield Static("", id="folder-path", markup=False)
            with Horizontal(classes="actions folder-actions"):
                yield Button("Up", id="folder-up")
                yield Button("Workspace", id="folder-workspace")
                yield Button("Home", id="folder-home")
                yield Button("Cancel", id="folder-cancel")
            yield OptionList(id="file-entries")
            if self.filename is not None:
                yield Label("New filename")
                with Horizontal(classes="browse-row"):
                    yield Input(value=self.filename, id="new-filename")
                    yield Button("Use this path", id="use-output", variant="primary")
            yield Static("↑ ↓ Navigate  ·  Enter Select  ·  Backspace Up  ·  Esc Cancel",
                         id="picker-hint", markup=False)

    def on_mount(self):
        self.load_folder(self.folder)

    @staticmethod
    def list_entries(folder: Path, suffix: str, folders_only: bool) -> list[tuple[Path, bool]]:
        entries = []
        for path in folder.iterdir():
            try:
                if path.is_dir():
                    entries.append((path, True))
                elif not folders_only and (not suffix or path.suffix.casefold() == suffix) and path.is_file():
                    entries.append((path, False))
            except OSError:
                continue
        if sys.platform == "win32" and folder == folder.parent:
            from ctypes import windll
            from string import ascii_uppercase

            drives = windll.kernel32.GetLogicalDrives()
            entries.extend((Path(f"{letter}:/"), True) for index, letter in enumerate(ascii_uppercase)
                           if drives & (1 << index) and letter != folder.drive.rstrip(":").upper())
        return sorted(entries, key=lambda entry: (not entry[1], entry[0].name.casefold()))

    @work(exclusive=True)
    async def load_folder(self, folder: Path, highlight: Path | None = None):
        status = self.query_one("#folder-path", Static)
        view = self.query_one(OptionList)
        try:
            entries = await asyncio.to_thread(self.list_entries, folder, self.suffix, self.filename is not None)
        except OSError as error:
            status.update(f"Could not open {folder} • {error.strerror or error}")
            return
        self.folder, self.entries = folder, entries
        filter_label = f"  ·  *{self.suffix}" if self.suffix and self.filename is None else ""
        status.update(f"{self.folder}{filter_label}")
        view.set_options([
            Option(Text(f"{path.name}{'/' if directory else ''}" if path.name else str(path),
                        style="#d6b9ff" if directory else "#f7edf9"))
            for path, directory in entries
        ] or [Option(Text("No matching files or folders"), disabled=True)])
        view.highlighted = next((index for index, (path, _) in enumerate(entries) if path == highlight), 0)
        view.focus()

    def action_parent(self):
        if self.folder.parent != self.folder:
            self.load_folder(self.folder.parent, highlight=self.folder)

    @on(OptionList.OptionSelected)
    def select_entry(self, event):
        event.stop()
        path, directory = self.entries[event.option_index]
        if directory:
            self.load_folder(path)
        else:
            self.dismiss(path)

    @on(Button.Pressed, ".folder-actions Button")
    def folder_button(self, event):
        event.stop()
        if event.button.id == "folder-up":
            self.action_parent()
        elif event.button.id == "folder-workspace":
            self.load_folder(ROOT)
        elif event.button.id == "folder-home":
            self.load_folder(Path.home())
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#use-output")
    @on(Input.Submitted, "#new-filename")
    def select_output(self, event):
        event.stop()
        filename = self.query_one("#new-filename", Input).value.strip()
        status = self.query_one("#folder-path", Static)
        if not filename or filename in {".", ".."} or any(char in filename for char in '/\\:'):
            status.update("Enter a filename for this folder.")
            return
        if self.suffix and not Path(filename).suffix:
            filename += self.suffix
        output = self.folder / filename
        if not self.folder.is_dir() or output.exists():
            status.update("Choose an accessible folder and a filename that is available.")
            return
        self.dismiss(output)


class Form(ModalScreen[list[str] | None]):
    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, title, fields, *, action="Continue", note="", preview=None,
                 folder: Path = ROOT, file_fields: dict[int, tuple[str, bool]] | None = None):
        super().__init__()
        self.title_text = title
        self.fields = fields
        self.confirm_label = action
        self.note = note
        self.preview = preview
        self.folder = folder
        self.file_fields = file_fields or {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="form"):
            yield Static(self.title_text, classes="form-title")
            if self.note:
                yield Static(self.note, markup=False)
            if self.preview is not None:
                yield TextArea(self.preview, read_only=True, classes="prompt-preview")
            for index, (label, value) in enumerate(self.fields):
                yield Label(label)
                if index in self.file_fields:
                    with Horizontal(classes="browse-row"):
                        yield Input(value=value, id=f"path-field-{index}")
                        yield Button("Browse…", id=f"browse-{index}")
                else:
                    yield Input(value=value)
            with Horizontal(classes="actions"):
                yield Button(self.confirm_label, id="confirm", variant="primary")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#confirm")
    @on(Input.Submitted)
    def submit(self):
        self.dismiss([field.value for field in self.query(Input)])

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, ".browse-row Button")
    def browse_path(self, event):
        event.stop()
        index = int(event.button.id.removeprefix("browse-"))
        field = self.query_one(f"#path-field-{index}", Input)
        suffix, output = self.file_fields[index]
        start = self.folder
        current = Path(field.value).expanduser() if field.value else None
        if current is not None:
            if not current.is_absolute():
                current = start / current
            if current.parent.is_dir():
                start = current.parent

        def selected(path):
            if path is not None:
                field.value = str(path)

        if output:
            self.app.push_screen(
                FilePicker("Choose a destination", start, suffix, filename=current.name if current else ""),
                selected,
            )
        else:
            self.app.push_screen(FilePicker("Choose a file", start, suffix), selected)


class Studio(App):
    TITLE = "Mystery Studio"
    BINDINGS = [
        ("ctrl+s", "save_project", "Save"),
        ("f5", "playtest", "Fresh preview"),
        ("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen { background: #161429; color: #f7edf9; }
    #masthead { height: 2; background: #30204b; color: #ffafda; padding: 0 2; text-style: bold; }
    #project-line { height: 2; padding: 0 2; background: #211a37; color: #c9b9ed; }
    TabbedContent { height: 1fr; }
    TabbedContent > ContentSwitcher, TabPane { height: 1fr; }
    TabPane { padding: 1 2; }
    Tabs { background: #211a37; }
    Tab { color: #d4bdfb; }
    Tab.-active { color: #ffb9db; text-style: bold; }
    Underline > .underline--bar { color: #ff83ba; }
    .pane-title { text-style: bold; height: 1; margin-bottom: 1; }
    .project-title { color: #f8a3df; }
    .revision-title { color: #ffd28b; }
    .actions { height: auto; layout: grid; grid-size: 2; grid-rows: 2; grid-gutter: 1 1; }
    #design-actions, #play-actions, #revision-actions { grid-size: 3; }
    Button { width: 100%; height: 2; border: none; background: #423363; color: #ffffff; }
    Button:hover, Button:focus { background: #66528c; }
    Button.-primary { background: #8c3d75; }
    #play, #resume { background: #23556e; }
    #play:focus, #resume:focus, #play:hover, #resume:hover { background: #34738b; }
    #review, #apply, #restore { background: #674523; }
    #review:focus, #apply:focus, #restore:focus,
    #review:hover, #apply:hover, #restore:hover { background: #906134; }
    #section { margin-bottom: 1; }
    #build-options { height: 3; margin-bottom: 1; }
    #variant { width: 1fr; margin-right: 1; }
    #no-art { width: auto; }
    #editor { height: 1fr; border: round #65528e; }
    #checks, #revision-log { height: 1fr; min-height: 3; background: #211a37; border: round #514371; }
    #status { height: 2; padding: 0 2; background: #30204b; color: #fff0bb; }
    .hint { color: #c4b4da; margin-bottom: 1; }
    Form, FilePicker { align: center middle; background: #0e0b1c 75%; }
    .form { width: 72; max-width: 96%; height: auto; max-height: 90%; padding: 1 2;
            background: #30204b; border: round #e48dc7; }
    .form-title { color: #ffb9db; text-style: bold; margin-bottom: 1; }
    .form Input { height: 2; border: none; padding: 0 1; background: #211a37; }
    .form Input:focus { background: #4a3266; }
    .form .actions { margin-top: 1; }
    .prompt-preview { height: 7; margin: 1 0; border: round #65528e; }
    .browse-row { height: 2; }
    .browse-row Input { width: 1fr; }
    .browse-row Button { width: 16; margin-left: 1; }
    .browse-row Input { height: 2; border: none; padding: 0 1; background: #211a37; }
    .file-picker { width: 76; max-width: 96%; height: 90%; padding: 1 2;
                   background: #30204b; border: round #e48dc7; }
    #folder-path { height: 2; color: #ffd28b; overflow: hidden; }
    .folder-actions { grid-size: 4; margin-bottom: 1; }
    #file-entries { height: 1fr; background: #211a37; border: round #65528e; }
    #picker-hint { height: 1; color: #c4b4da; }
    """

    def __init__(self, project: Path | None = None, preview_root: Path | None = None):
        super().__init__()
        self.initial_project = project
        self.preview_root = preview_root
        self.project = None
        self.original = b""
        self.data = {}
        self.edits = {}
        self.section = None
        self.previews = {}
        self.reviewed = None
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Static("✦  MYSTERY STUDIO", id="masthead")
        yield Static("No project open", id="project-line", markup=False)
        with TabbedContent():
            with TabPane("Projects", id="projects"):
                with VerticalScroll():
                    yield Static("Start a mystery", classes="pane-title project-title")
                    yield Static("Open an author project, start with a playable mystery, or draft from your own brief.",
                                 classes="hint")
                    with Horizontal(classes="actions"):
                        yield Button("Open project", id="open", variant="primary")
                        yield Button("New from template", id="template")
                        yield Button("Prepare draft prompt", id="draft")
                        yield Button("Import draft", id="import")
            with TabPane("Design", id="design"):
                yield Select([], prompt="Choose a section", id="section")
                yield TextArea("", language="json", show_line_numbers=True, id="editor", disabled=True)
                with Horizontal(id="design-actions", classes="actions"):
                    yield Button("Save revision", id="save", variant="primary")
                    yield Button("Discard edits", id="discard")
                    yield Button("Open art gallery", id="gallery")
            with TabPane("Playtest", id="playtest"):
                with Horizontal(id="build-options"):
                    yield Select([("Default puzzle", "")], allow_blank=False, id="variant")
                    yield Checkbox("Text-only build", id="no-art")
                with Horizontal(id="play-actions", classes="actions"):
                    yield Button("Fresh preview  F5", id="play")
                    yield Button("Resume last preview", id="resume")
                    yield Button("Validate all variants", id="validate")
                    yield Button("Show walkthrough", id="walkthrough")
                    yield Button("Export runtime pack", id="export")
                yield RichLog(id="checks", wrap=True)
            with TabPane("Revisions", id="revisions"):
                yield Static("Proposals and history", classes="pane-title revision-title")
                with Horizontal(id="revision-actions", classes="actions"):
                    yield Button("Prepare prompt", id="prepare")
                    yield Button("Generate with model", id="suggest")
                    yield Button("Review proposal", id="review")
                    yield Button("Apply reviewed edits", id="apply", disabled=True)
                    yield Button("Show history", id="history")
                    yield Button("Restore snapshot", id="restore")
                yield RichLog(id="revision-log", wrap=True)
        yield Static("Open a project or start from the template.", id="status", markup=False)
        yield Footer()

    def on_mount(self):
        if self.initial_project is not None:
            try:
                self.open_project(self.initial_project)
            except ERRORS as error:
                self.status(str(error), failure=True)

    def status(self, message, *, failure=False):
        self.query_one("#status", Static).update(message)
        if failure:
            self.notify(message, title="Studio", severity="error")

    def open_project(self, path, *, section=None, page="design"):
        path = path.resolve()
        original = path.read_bytes()
        data = json.loads(original)
        if not isinstance(data, dict) or data.get("author_schema") != 1:
            raise ValueError("Choose an author project with author_schema 1.")
        if path != self.project:
            self.query_one("#checks", RichLog).clear()
            self.query_one("#revision-log", RichLog).clear()
        self.project, self.original, self.data = path, original, data
        self.edits.clear()
        self.reviewed = None
        self.query_one("#apply", Button).disabled = True
        self.section = None
        sections = [key for key in dict.fromkeys((*data, *OPTIONAL_SECTIONS))
                    if key not in {"author_schema", "id", "version"}]
        picker = self.query_one("#section", Select)
        picker.set_options([(key.replace("_", " ").capitalize(), key) for key in sections])
        if sections:
            picker.value = section if section in sections else sections[0]
            self.show_section(picker.value)
        else:
            self.query_one("#editor", TextArea).clear()
            self.query_one("#editor", TextArea).disabled = True
        variants = data.get("puzzle_variants")
        variant_picker = self.query_one("#variant", Select)
        old_variant = variant_picker.value
        variant_options = [("Default puzzle", "")]
        if isinstance(variants, dict):
            variant_options.extend((key, key) for key in variants if key)
        variant_picker.set_options(variant_options)
        if isinstance(variants, dict) and old_variant in variants:
            variant_picker.value = old_variant
        self.call_after_refresh(self.show_page, page)
        self.refresh_project_line()
        self.status("Choose a section to edit, or press F5 to play a fresh build.")

    def show_page(self, page):
        tabs = self.query_one(TabbedContent)
        tabs.query_one(Tabs).focus()
        tabs.active = page

    def refresh_project_line(self):
        if self.project is not None:
            dirty = "  •  Unsaved edits" if self.edits else ""
            self.query_one("#project-line", Static).update(
                f"{self.data.get('title', self.project.stem)}  •  v{self.data.get('version', '?')}"
                f"  •  {self.project.name}{dirty}"
            )

    def section_text(self, section):
        return revisions.encode(self.data.get(section, OPTIONAL_SECTIONS.get(section))).decode().rstrip()

    def show_section(self, section):
        self.section = section
        editor = self.query_one("#editor", TextArea)
        editor.disabled = self.busy
        editor.load_text(self.edits.get(section, self.section_text(section)))

    @on(Select.Changed, "#section")
    def change_section(self, event):
        if event.value == event.select.value and isinstance(event.value, str) and event.value != self.section:
            self.remember_edit()
            self.show_section(event.value)

    @on(TextArea.Changed, "#editor")
    def remember_edit(self):
        if self.section is None:
            return
        value = self.query_one("#editor", TextArea).text
        if value == self.section_text(self.section):
            self.edits.pop(self.section, None)
        else:
            self.edits[self.section] = value
        self.refresh_project_line()

    def require_saved(self):
        self.remember_edit()
        if self.edits:
            raise ValueError("Save or discard your edits in Design first.")

    def require_current(self):
        self.require_saved()
        if self.project is None:
            raise ValueError("Open or create a project in Projects first.")
        if self.project.read_bytes() != self.original:
            raise ValueError("The project changed on disk. Reopen it in Projects to reload.")

    def can_run(self, action: str) -> bool:
        if self.busy:
            self.status("Wait for the current operation to finish.")
            return False
        if action not in {"open", "template", "draft", "import", "suggest"} and self.project is None:
            self.status("Open or create a project in Projects first.", failure=True)
            return False
        return True

    @on(Button.Pressed)
    def handle_button(self, event):
        action = event.button.id
        if action in {"confirm", "cancel"}:
            return
        if not self.can_run(action):
            return
        try:
            if action == "discard":
                self.push_screen(Form("Discard unsaved changes?", [], action="Discard"),
                                 self.discard_edits)
            elif action in {"save", "play", "resume", "validate", "walkthrough", "history", "apply"}:
                self.execute(action, [])
            else:
                self.open_form(action)
        except ERRORS as error:
            self.status(str(error), failure=True)

    def discard_edits(self, confirmed):
        if confirmed is not None:
            self.edits.clear()
            if self.section:
                self.show_section(self.section)
            self.refresh_project_line()
            self.status("Unsaved edits discarded.")

    def action_save_project(self):
        if self.can_run("save"):
            self.execute("save", [])

    def action_playtest(self):
        if self.can_run("play"):
            self.execute("play", [])

    def action_quit(self):
        self.remember_edit()
        if self.busy:
            self.status("Wait for the current operation to finish.")
        elif self.edits:
            self.push_screen(Form("Quit and discard unsaved edits?", [], action="Quit"),
                             lambda values: self.exit() if values is not None else None)
        else:
            self.exit()

    def open_form(self, action):
        forms = {
            "template": ("Create a playable project", [("New project JSON path", ""), ("Title", "")]),
            "draft": ("Prepare a draft prompt", [("Brief text file", ""), ("Draft request", ""),
                                                ("New prompt file", "draft-prompt.txt")]),
            "import": ("Import and validate a draft", [("Draft JSON path", ""), ("New project JSON path", "")]),
            "export": ("Export the selected variant", [("New runtime JSON path", "")]),
            "gallery": ("Compare terminal art styles", [("Art asset ID", "")]),
            "prepare": ("Prepare a scoped revision", [("JSON pointers, separated by spaces", "/characters"),
                                                     ("Requested change", ""), ("New prompt file", "revision-prompt.txt")]),
            "suggest": ("Generate a draft or proposal", [("Exact prompt file to send", ""),
                                                        ("Provider (ollama, openai, claude)", "ollama"),
                                                        ("Model ID", ""), ("New result JSON path", "proposal.json")]),
            "review": ("Review proposed edits", [("Proposal JSON path", ""), ("Edit numbers (blank for all)", "")]),
            "restore": ("Restore a snapshot from history", [("Unique revision hash prefix (8 or more characters)", "")]),
        }
        if action in {"open", "template", "import"}:
            self.require_saved()
        if action in {"export", "gallery", "prepare", "review", "restore"}:
            self.require_current()
        folder = self.project.parent if self.project is not None else ROOT
        if action == "open":
            self.push_screen(
                FilePicker("Open an author project", folder, ".json"),
                lambda path: self.execute("open", [str(path)]) if path is not None else None,
            )
            return
        title, fields = forms[action]
        note = ""
        label = "Continue"
        if action == "suggest":
            label = "Review prompt"
        elif action == "gallery":
            assets = [asset["id"] for asset in self.data.get("art", [])]
            if not assets:
                raise ValueError("Add an art entry in Design before opening the gallery.")
            fields = [("Art asset ID", assets[0])]
            note = "Available assets: " + ", ".join(assets)
        elif action == "restore":
            note = "Restore validates this snapshot and saves the displaced project in history."
            label = "Restore"
        def submitted(values):
            if values is not None:
                if action == "suggest":
                    self.call_after_refresh(self.confirm_model_prompt, values)
                else:
                    self.execute(action, values)

        file_fields = {
            "template": {0: (".json", True)},
            "draft": {0: ("", False), 2: (".txt", True)},
            "import": {0: (".json", False), 1: (".json", True)},
            "export": {0: (".json", True)},
            "prepare": {2: (".txt", True)},
            "suggest": {0: ("", False), 3: (".json", True)},
            "review": {0: (".json", False)},
        }
        self.push_screen(Form(title, fields, action=label, note=note, folder=folder,
                              file_fields=file_fields.get(action)), submitted)

    def confirm_model_prompt(self, values):
        try:
            source, provider, model, output = values
            if provider not in {"ollama", "openai", "claude"} or not model.strip():
                raise ValueError("Choose ollama, openai, or claude and enter a model ID.")
            prompt = Path(source).read_text(encoding="utf-8")
            if not prompt.strip():
                raise ValueError("Choose a prompt file with content.")
            note = f"Provider: {provider}  •  Model: {model}"
            self.push_screen(
                Form("Review the prompt", [], action="Send prompt", note=note, preview=prompt),
                lambda confirmed: self.execute("suggest", [prompt, provider, model, output])
                if confirmed is not None else None,
            )
        except ERRORS as error:
            self.status(str(error), failure=True)

    @work
    async def execute(self, action, values):
        if self.busy:
            return
        self.busy = True
        picker = self.query_one("#section", Select)
        editor = self.query_one("#editor", TextArea)
        picker.disabled = editor.disabled = True
        self.status("Working…")
        try:
            if action in {"open", "template", "import"}:
                self.require_saved()
                path = Path(values[-1] if action == "import" else values[0]).resolve()
                if action != "open":
                    await asyncio.to_thread(self.create_project, action, path, values)
                self.open_project(path)
            elif action in {"draft", "suggest", "prepare"}:
                if action == "prepare":
                    self.require_current()
                output = await asyncio.to_thread(self.create_assistance_file, action, values)
                self.status(f"Saved {output}")
            elif action == "save":
                await self.save_edits()
            elif action in {"play", "resume", "validate", "walkthrough", "export"}:
                await self.run_playtest(action, values)
            elif action == "gallery":
                self.require_current()
                self.launch(["--author", "preview", str(self.project), values[0], "--record-revision"])
                self.open_project(self.project, section=self.section)
                self.status("Returned from the art gallery.")
            else:
                await self.run_revision(action, values)
        except ERRORS as error:
            self.status(str(error), failure=True)
            if action in {"play", "resume", "validate", "walkthrough", "export"}:
                self.query_one("#checks", RichLog).write(Text(str(error), style="bold #ff9cac"))
            elif action in {"review", "apply", "restore"}:
                self.query_one("#revision-log", RichLog).write(Text(str(error), style="bold #ff9cac"))
        finally:
            self.busy = False
            picker.disabled = False
            editor.disabled = self.section is None

    @staticmethod
    def create_project(action, path, values):
        if action == "template":
            data = json.loads(TEMPLATE.read_bytes())
            title = values[1].strip()
            project_id = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
            if not title or not project_id or project_id == data["id"]:
                raise ValueError("Enter a title and a distinct project filename with ASCII letters or digits.")
            data.update(id=project_id, title=title)
            data.pop("art", None)
        else:
            data = json.loads(Path(values[0]).read_bytes())
        revisions.validate_project(data, path.parent)
        revisions.write_new(path, revisions.encode(data))

    def create_assistance_file(self, action, values):
        output = Path(values[-1]).resolve()
        if output.exists():
            raise FileExistsError(f"Output already exists: {output}")
        if action == "suggest":
            from .author_provider import suggest

            prompt, provider, model, _ = values
            result = suggest(provider, model, prompt)
            content = revisions.encode(result)
        else:
            source, scopes = (Path(values[0]), []) if action == "draft" else (self.project, values[0].split())
            if not values[1].strip():
                raise ValueError("Enter a request describing what to draft or change.")
            content = revisions.prepare_prompt(source, action == "draft", scopes, values[1]).encode("utf-8")
        revisions.write_new(output, content)
        return output

    async def save_edits(self):
        self.remember_edit()
        if not self.edits:
            self.status("There are no edits to save.")
            return
        updated = dict(self.data)
        for section, value in self.edits.items():
            try:
                updated[section] = json.loads(value)
            except ValueError as error:
                raise ValueError(f"{section}: {error}") from error
        if revisions.same(self.data, updated):
            self.discard_edits([])
            self.status("The project content is unchanged.")
            return
        revisions.check_locks(self.data, updated)

        def save():
            revisions.validate_project(updated, self.project.parent)
            return revisions.commit_revision(self.project, self.original, updated)

        version = await asyncio.to_thread(save)
        self.open_project(self.project, section=self.section)
        self.status(f"Saved version {version}. Press F5 to preview the revision.")

    async def run_playtest(self, action, values):
        self.require_current()
        variant = self.query_one("#variant", Select).value or None
        no_art = self.query_one("#no-art", Checkbox).value
        key = (self.project, variant, no_art)
        log = self.query_one("#checks", RichLog)
        if action == "resume":
            preview = self.previews.get(key)
            if preview is None:
                raise ValueError("Launch a preview for this variant and art setting first.")
            pack, save, fingerprint = preview
        else:
            data = json.loads(self.original)
            if action == "validate":
                await asyncio.to_thread(revisions.validate_project, data, self.project.parent, no_art=no_art)
                self.status("All variants passed validation." if not no_art else
                            "All variants passed text-only validation.")
                log.clear().write("Passed: default pack and all named variants.")
                return
            if no_art:
                data.pop("art", None)
            build = await asyncio.to_thread(compile_project, data, root=self.project.parent, variant=variant)
            if action == "walkthrough":
                log.clear()
                for name, commands in build.routes.items():
                    log.write(Text(f"{name} · {len(commands)} turns", style="bold #76e5ff"))
                    for command in commands:
                        log.write(f"  {command.verb} {command.target}".rstrip())
                self.status("Walkthrough ready.")
                return
            if action == "export":
                output = Path(values[0]).resolve()
                revisions.write_new(output, revisions.encode(build.data))
                self.status(f"Exported {output}")
                log.write(f"Exported {output}")
                return
            folder = self.preview_root / str(len(list(self.preview_root.iterdir())) + 1)
            folder.mkdir()
            pack, save = folder / "pack.json", folder / "save.sqlite3"
            revisions.write_new(pack, revisions.encode(build.data))
            fingerprint = revisions.digest(self.original)
        self.launch(["--tui", "--pack", str(pack), "--save", str(save)])
        self.previews[key] = (pack, save, fingerprint)
        if fingerprint == revisions.digest(self.original):
            self.status("Returned from preview. Make a revision or resume this playtest.")
        else:
            self.status("Returned from an earlier build. Press F5 to play the current revision.")

    def launch(self, arguments):
        try:
            with self.suspend():
                try:
                    result = subprocess.run([sys.executable, "-m", "rpg", *arguments], cwd=ROOT)
                except (OSError, KeyboardInterrupt) as error:
                    result = error
        except SuspendNotSupported:
            raise ValueError("Launch Studio in an interactive terminal to open previews.") from None
        if isinstance(result, KeyboardInterrupt):
            return
        if isinstance(result, OSError):
            raise result
        if result.returncode:
            raise ValueError(f"The preview tool exited with code {result.returncode}.")

    async def run_revision(self, action, values):
        self.require_current()
        log = self.query_one("#revision-log", RichLog)
        if action == "history":
            log.clear().write(f"Current  {revisions.digest(self.original)}  v{self.data['version']}")
            for snapshot in revisions.snapshots(self.project):
                version = json.loads(snapshot.read_bytes())["version"]
                log.write(f"Saved    {snapshot.stem}  v{version}")
            self.status("Copy a saved revision hash to restore it.")
        elif action == "review":
            self.reviewed = None
            self.query_one("#apply", Button).disabled = True
            log.clear()
            proposal = json.loads(Path(values[0]).read_bytes())
            only = [int(number) for number in values[1].replace(",", " ").split()]
            updated, changes = await asyncio.to_thread(
                revisions.revise, self.original, proposal, self.project.parent, only
            )
            for index, edit in changes:
                log.write(Text(f"{index}. {edit['path']}", style="bold #ffd28b"))
                before, after = (revisions.encode(edit[key]).decode().splitlines() for key in ("before", "after"))
                for line in unified_diff(before, after, "current", "proposed", lineterm=""):
                    color = "#ff9cac" if line.startswith("-") else "#90ebbf" if line.startswith("+") else ""
                    log.write(Text(line, style=color))
            self.reviewed = updated
            self.query_one("#apply", Button).disabled = False
            self.status("Selected edits passed validation. Review the diff before applying.")
        elif action == "apply":
            if self.reviewed is None:
                raise ValueError("Review a proposal first.")
            version = await asyncio.to_thread(
                revisions.commit_revision, self.project, self.original, self.reviewed
            )
            self.open_project(self.project, section=self.section, page="revisions")
            log.write(f"Applied the reviewed edits as version {version}.")
            self.status(f"Saved version {version}. Press F5 to try it.")
        elif action == "restore":
            restored = await asyncio.to_thread(
                revisions.restore_revision, self.project, self.original, values[0].strip()
            )
            self.open_project(self.project, section=self.section, page="revisions")
            log.write(f"Restored {restored}.")
            self.status("Revision restored. The displaced project is in history.")


def run_studio(project):
    with TemporaryDirectory(prefix="mystery-studio-") as directory:
        Studio(project, Path(directory)).run()
