import json
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rpg.author_revisions import digest, encode
from rpg.engine import Pack
from rpg.saves import Save


@unittest.skipUnless(find_spec("textual"), "Textual is optional")
class StudioTest(unittest.IsolatedAsyncioTestCase):
    async def test_browse_for_project_and_export_destination(self):
        from textual.widgets import Input, OptionList, TabbedContent

        from rpg.studio import Studio, TEMPLATE

        with TemporaryDirectory() as directory:
            root = Path(directory)
            projects = root / "Projects with spaces"
            projects.mkdir()
            (root / "ignore.txt").touch()
            project = projects / "harbor.JSON"
            data = json.loads(TEMPLATE.read_bytes())
            data.pop("art", None)
            project.write_bytes(encode(data))
            app = Studio()
            with patch("rpg.studio.ROOT", root):
                async with app.run_test(size=(80, 24)) as pilot:
                    async def settle():
                        await pilot.pause()
                        await app.workers.wait_for_complete()
                        await pilot.pause()

                    self.assertTrue(await pilot.click("#open"))
                    await settle()
                    self.assertEqual(app.screen.query_one(OptionList).option_count, 1)
                    await pilot.press("enter")
                    await settle()
                    await pilot.press("backspace")
                    await settle()
                    self.assertEqual(app.screen.folder, root)
                    await pilot.press("enter")
                    await settle()
                    await pilot.press("enter")
                    await settle()
                    self.assertEqual(app.project, project)

                    tabs = app.query_one(TabbedContent)
                    self.assertTrue(await pilot.click(tabs.get_tab("playtest")))
                    self.assertTrue(await pilot.click("#export"))
                    self.assertTrue(await pilot.click("#browse-0"))
                    await settle()
                    await pilot.press("escape")
                    await settle()
                    self.assertEqual(app.screen.query_one("#path-field-0", Input).value, "")
                    self.assertTrue(await pilot.click("#browse-0"))
                    await settle()
                    self.assertTrue(await pilot.click("#folder-workspace"))
                    await settle()
                    app.screen.query_one("#new-filename", Input).value = "new pack"
                    self.assertTrue(await pilot.click("#use-output"))
                    await settle()
                    self.assertEqual(app.screen.query_one("#path-field-0", Input).value, str(root / "new pack.json"))
                    self.assertTrue(await pilot.click("#confirm"))
                    await settle()
                    self.assertEqual(Pack.load(root / "new pack.json").title, data["title"])

    async def test_create_edit_preview_review_and_restore(self):
        from textual.widgets import Input, Select, Static, TabbedContent, TextArea

        from rpg.studio import Studio

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "test-mystery.json"
            previews = root / "previews"
            previews.mkdir()
            app = Studio(preview_root=previews)
            launched = []

            def play(arguments):
                pack_path = Path(arguments[arguments.index("--pack") + 1])
                save_path = Path(arguments[arguments.index("--save") + 1])
                pack = Pack.load(pack_path)
                save = Save(save_path)
                try:
                    save.load_or_start(pack)
                finally:
                    save.close()
                launched.append((pack, save_path))

            launcher = patch.object(app, "launch", side_effect=play)
            launcher.start()
            self.addCleanup(launcher.stop)
            async with app.run_test(size=(80, 24)) as pilot:
                async def click(button):
                    self.assertTrue(await pilot.click(button))
                    await pilot.pause()
                    await app.workers.wait_for_complete()
                    await pilot.pause()

                async def submit(*values):
                    for field, value in zip(app.screen.query(Input), values, strict=True):
                        field.value = str(value)
                    await click("#confirm")

                await click("#template")
                await submit(project, "Studio mystery")
                original = project.read_bytes()
                tabs = app.query_one(TabbedContent)
                self.assertEqual(tabs.active, "design", str(app.query_one("#status", Static).content))

                section = app.query_one("#section", Select)
                section.value = "clues"
                await pilot.pause()
                editor = app.query_one("#editor", TextArea)
                self.assertGreaterEqual(editor.region.height, 6)
                clues = json.loads(editor.text)
                clues[0]["text"] += " Revised in Studio."
                editor.load_text(encode(clues).decode().rstrip())
                await pilot.press("ctrl+s")
                await app.workers.wait_for_complete()
                self.assertEqual(json.loads(project.read_bytes())["clues"], clues)
                self.assertEqual(app.section, "clues")

                await pilot.press("f5")
                await app.workers.wait_for_complete()
                self.assertEqual(tabs.active, "design")
                self.assertEqual(launched[-1][0].version, 2)

                await click(tabs.get_tab("playtest"))
                self.assertGreaterEqual(app.query_one("#checks").region.height, 4)
                await click("#validate")
                self.assertIn("passed validation", str(app.query_one("#status", Static).content))
                await click("#resume")
                self.assertEqual(launched[-1][1], launched[-2][1])
                app.query_one("#variant", Select).value = "timeline"
                await click("#play")
                self.assertTrue(launched[-1][0].id.endswith("-timeline"))
                self.assertNotEqual(launched[-1][1], launched[-2][1])

                current = project.read_bytes()
                proposal = root / "proposal.json"
                proposal.write_bytes(encode({
                    "proposal_schema": 1,
                    "base_sha256": digest(current),
                    "edits": [{"path": "/title", "before": "Studio mystery", "after": "Reviewed mystery"}],
                }))
                await click(tabs.get_tab("revisions"))
                await click("#review")
                await submit(proposal, "")
                await click("#apply")
                self.assertEqual(json.loads(project.read_bytes())["title"], "Reviewed mystery")
                await click("#restore")
                await submit(digest(original)[:12])
                self.assertEqual(project.read_bytes(), original)

                prompt = root / "prompt.txt"
                result = root / "model-result.json"
                prompt.write_text("Review this prompt.", encoding="utf-8")
                with patch("rpg.author_provider.suggest", return_value={"test": True}) as suggest:
                    await click("#suggest")
                    await submit(prompt, "ollama", "test-model", result)
                    self.assertEqual(app.screen.query_one(TextArea).text, "Review this prompt.")
                    suggest.assert_not_called()
                    prompt.write_text("Changed after review.", encoding="utf-8")
                    await click("#confirm")
                    suggest.assert_called_once_with("ollama", "test-model", "Review this prompt.")
                    self.assertEqual(json.loads(result.read_bytes()), {"test": True})
