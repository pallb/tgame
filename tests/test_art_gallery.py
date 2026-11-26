import json
import shutil
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rpg.authoring import art_options, load_project
from rpg.terminal_art import ART_STYLES, convert_image


@unittest.skipUnless(find_spec("PIL") and find_spec("textual"), "Pillow and Textual are optional")
class ArtGalleryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.examples = Path(__file__).resolve().parents[1] / "authoring_examples"

    async def test_all_styles_preview_and_keyboard_choice(self):
        from textual.widgets import Static

        from rpg.art_gallery import ArtGallery

        source = self.examples / "art" / "lysa.png"
        artworks = {style: convert_image(source, alt="Lysa", width=50, style=style) for style in ART_STYLES}
        self.assertEqual(len({repr(art.as_data()) for art in artworks.values()}), len(ART_STYLES))
        gallery = ArtGallery("lysa_portrait", artworks, "classic")
        async with gallery.run_test(size=(65, 22)) as pilot:
            picture = gallery.query_one("#preview-picture", Static)
            first = picture.content.plain
            self.assertGreater(gallery.query_one("#preview-scroll").max_scroll_x, 0)
            await pilot.press("end")
            self.assertEqual(gallery.selected, "amber")
            self.assertNotEqual(picture.content.plain, first)
            await pilot.click("#toggle-ascii")
            self.assertEqual(picture.content.plain.splitlines()[0], artworks["amber"].ascii_rows[0])
            await pilot.press("ctrl+s")
        self.assertEqual(gallery.return_value, "amber")

    def test_cancel_preserves_project_and_selection_changes_next_bake(self):
        from rpg.art_gallery import ArtGallery, preview_project

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(self.examples / "art", root / "art")
            project = root / "project.json"
            shutil.copy2(self.examples / "lantern_at_low_tide.json", project)
            original = project.read_bytes()
            with patch.object(ArtGallery, "run", return_value=None):
                preview_project(project, "lysa_portrait")
            self.assertEqual(project.read_bytes(), original)

            with patch.object(ArtGallery, "run", return_value="ansi256"):
                preview_project(project, "lysa_portrait")
            expected = json.loads(original)
            selected = next(entry for entry in expected["art"] if entry["id"] == "lysa_portrait")
            selected["style"] = "ansi256"
            self.assertEqual(json.loads(project.read_bytes()), expected)
            output = load_project(project).pack.portraits["lysa"]
            self.assertEqual(output, convert_image(root / selected["source"], **art_options(selected)))

    def test_half_blocks_emit_indexed_and_rgb_terminal_colors(self):
        from io import StringIO
        from rich.console import Console

        from rpg.terminal_art import TerminalArt
        from rpg.tui import art_render

        source = self.examples / "art" / "low-tide-quay.png"
        indexed = convert_image(source, alt="Quay", style="ansi256")
        rgb = convert_image(source, alt="Quay", style="truecolor")
        dots = convert_image(source, alt="Quay", style="braille")
        for art in (indexed, rgb, dots):
            self.assertEqual(TerminalArt.from_data(art.as_data()), art)
        self.assertEqual(indexed.color_space, "xterm256")
        self.assertEqual(rgb.color_space, "rgb")
        self.assertTrue(all(0x2800 <= ord(glyph) <= 0x28FF for row in dots.glyph_rows for glyph in row))
        self.assertTrue(any(ord(glyph) > 0x2800 for row in dots.glyph_rows for glyph in row))
        self.assertNotEqual(dots.glyph_rows, dots.ascii_rows)
        self.assertEqual(art_render(dots, 24, color=False).plain, "\n".join(dots.ascii_rows))

        for art, prefix, background in ((indexed, "\x1b[38;5;", "48;5;"), (rgb, "\x1b[38;2;", "48;2;")):
            with self.subTest(space=art.color_space):
                stream = StringIO()
                console = Console(file=stream, force_terminal=True, no_color=False, color_system="truecolor", width=80)
                console.print(art_render(art, 24))
                self.assertIn(prefix, stream.getvalue())
                self.assertIn(background, stream.getvalue())
                self.assertIn("▀", stream.getvalue())
