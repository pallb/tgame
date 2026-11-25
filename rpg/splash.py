from time import monotonic

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class Startup(ModalScreen):
    DURATION = 5.4
    DEFAULT_CSS = """
    Startup { align: center middle; background: #101712; }
    Startup Vertical { width: 54; max-width: 98%; height: auto; padding: 1; }
    Startup Static { height: auto; content-align: center middle; text-align: center; }
    #startup-title { color: #e4bd73; text-style: bold; margin-top: 1; }
    #startup-progress { color: #8bb498; margin-top: 1; }
    """

    def __init__(self, title: str, model_status: str = ""):
        super().__init__()
        self.title = title
        self.model_status = model_status

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(id="startup-scene"),
            Static(Text(self.title), id="startup-title"),
            Static(id="startup-progress"),
            Static(Text(self.model_status), id="startup-model"),
        )

    def set_model_status(self, status: str):
        self.query_one("#startup-model", Static).update(Text(status))

    def on_mount(self):
        self.started = monotonic()
        self.animate_scene()
        self.set_interval(0.10, self.animate_scene)

    def animate_scene(self):
        elapsed = monotonic() - self.started
        if elapsed >= self.DURATION:
            self.dismiss()
            return
        frame = int(elapsed * 10)
        scene = Text(justify="center")
        roofs = ("           /\\           ", "     /\\   /  \\    /\\    ",
                 "    /__\\ /____\\  /__\\   ", "    |  | |    |  |  |   ",
                 "____|__|_|____|__|__|___")
        for y, row in enumerate(roofs):
            for x, cell in enumerate(row):
                if (x, y) == (11, 3):
                    scene.append("▪" if frame % 7 else "·", "#e4bd73")
                elif cell == " " and (x * 7 + (y - frame) * 11) % 23 < 3:
                    scene.append("╱", "#526d58")
                else:
                    scene.append(cell, "#8bb498")
            scene.append("\n")
        self.query_one("#startup-scene", Static).update(scene)
        fill = int(elapsed / self.DURATION * 24)
        self.query_one("#startup-progress", Static).update(
            Text("━" * fill + "─" * (24 - fill), justify="center")
        )
