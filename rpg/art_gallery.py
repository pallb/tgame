"""Interactive terminal art preview for an author project's image entries."""

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Footer, OptionList, Static

from .authoring import art_options, art_source
from .terminal_art import ART_STYLES, TerminalArt, convert_image
from .tui import art_render


class ArtGallery(App[str | None]):
    BINDINGS = [
        Binding("ctrl+s", "use_style", "Use style", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
    ]
    CSS = """
    Screen { background: #111813; color: #e2e5d9; }
    #art-title { padding: 0 1; height: auto; color: #e4bd73; background: #25372a; }
    #gallery { height: 1fr; }
    #styles { width: 24; max-width: 40%; height: 1fr; border-right: solid #49644c; }
    #preview-area { width: 1fr; height: 1fr; padding: 0 1; }
    #style-description { height: auto; color: #a5c3a8; padding-bottom: 1; }
    #preview-scroll { height: 1fr; }
    #preview-picture { height: auto; }
    #actions { height: auto; padding: 0 1; }
    #actions Button { margin-right: 1; }
    Footer { background: #25372a; }
    """

    def __init__(self, asset: str, artworks: dict[str, TerminalArt], current: str):
        super().__init__()
        self.asset = asset
        self.artworks = artworks
        self.style_ids = list(artworks)
        self.current = current
        self.selected = current
        self.ascii_only = False

    def compose(self) -> ComposeResult:
        yield Static(Text(f"Art preview  /  {self.asset}"), id="art-title")
        with Horizontal(id="gallery"):
            yield OptionList(*(Text(ART_STYLES[style][0] + ("  •" if style == self.current else ""))
                               for style in self.style_ids), id="styles")
            with Vertical(id="preview-area"):
                yield Static(id="style-description")
                with ScrollableContainer(id="preview-scroll"):
                    yield Static(id="preview-picture")
        with Horizontal(id="actions"):
            yield Button("Use this style", id="use-style", variant="primary")
            yield Button("View ASCII fallback", id="toggle-ascii")
        yield Footer()

    def on_mount(self):
        menu = self.query_one("#styles", OptionList)
        menu.highlighted = self.style_ids.index(self.current)
        menu.focus()
        self.show_preview()

    def show_preview(self):
        picture = self.query_one("#preview-picture", Static)
        art = self.artworks[self.selected]
        width = len(art.ascii_rows[0])
        picture.styles.width = width
        picture.update(art_render(art, width, color=not self.ascii_only))
        self.query_one("#style-description", Static).update(Text(ART_STYLES[self.selected][1]))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted):
        self.selected = self.style_ids[event.option_index]
        self.show_preview()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "use-style":
            self.action_use_style()
        if event.button.id == "toggle-ascii":
            self.ascii_only = not self.ascii_only
            event.button.label = "View chosen style" if self.ascii_only else "View ASCII fallback"
            self.show_preview()

    def action_use_style(self):
        self.exit(self.selected)

    def action_cancel(self):
        self.exit()


def preview_project(path: Path, asset_id: str):
    path = path.resolve()
    original = path.read_bytes()
    project = json.loads(original.decode("utf-8"))
    entries = [entry for entry in project.get("art", []) if entry.get("id") == asset_id]
    if len(entries) != 1:
        raise ValueError(f"Expected one art entry named {asset_id!r}.")
    entry = entries[0]
    source = art_source(path.parent, entry)
    options = art_options(entry)
    current = options.pop("style", "color" if options.get("mode") == "color" else "classic")
    if current not in ART_STYLES:
        raise ValueError(f"Unknown saved art style {current!r}.")
    previews = {style: convert_image(source, **options, style=style) for style in ART_STYLES}
    chosen = ArtGallery(asset_id, previews, current).run()
    if chosen is None:
        return
    entry["style"] = chosen
    save_project_style(path, original, project)
    print(f"Saved {ART_STYLES[chosen][0]} for {asset_id}. Bake the project to use it in the game.")


def save_project_style(path: Path, original: bytes, project: dict):
    with NamedTemporaryFile(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp", delete=False,
                            mode="w", encoding="utf-8", newline="\n") as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(project, ensure_ascii=False, indent=2) + "\n")
    try:
        if path.read_bytes() != original:
            raise ValueError("The project changed while previewing. Reopen the gallery to apply the style.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
