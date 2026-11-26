import copy
import json
import unittest
from importlib.util import find_spec
from pathlib import Path

from rpg.authoring import compile_project, load_project
from rpg.engine import Command


class AuthoringTest(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).resolve().parents[1] / "authoring_examples" / "lantern_at_low_tide.json"
        self.fixture = fixture
        self.project = json.loads(fixture.read_text(encoding="utf-8"))
        self.project.pop("art", None)

    def test_compiles_new_pack_and_author_playtests(self):
        self.project["locations"][0]["author_note"] = "Private location note."
        self.project["actions"][0]["author_note"] = "Private action note."
        build = compile_project(self.project)
        self.assertNotIn("author_note", build.data["locations"]["quay"])
        self.assertNotIn("author_note", build.data["rules"][0])
        self.assertEqual(set(build.routes), {"shortest", "witness", "puzzle"})
        self.assertEqual(len(build.pack.locations), 3)
        self.assertEqual(len(build.pack.characters()), 2)
        self.assertNotIn("brief", build.data)
        self.assertNotIn("playtests", build.data)
        self.assertEqual(build.pack.evidence(build.pack.start_state()), [])
        for name, route in build.routes.items():
            with self.subTest(route=name):
                state = build.pack.start_state()
                for command in route:
                    result = build.pack.step(state, command)
                    self.assertTrue(result.accepted, result.message)
                    state = result.state
                self.assertTrue({"resolved", "bell_call", "signal_log"} <= state.flags)
        self.assertIn(Command("solve", "wave star shell"), build.routes["puzzle"])
        self.assertIn(Command("show", "oren"), build.routes["witness"])

    def test_invalid_references_and_puzzles(self):
        invalid_puzzle = copy.deepcopy(self.project)
        invalid_puzzle["puzzles"][0]["sequence"] = ["wave", "wrong", "shell"]
        with self.assertRaisesRegex(ValueError, "Incompatible symbol puzzle"):
            compile_project(invalid_puzzle)
        self.project["locations"][0]["exits"].append("missing_room")
        with self.assertRaisesRegex(ValueError, "unknown location"):
            compile_project(self.project)

    def test_detects_circular_gate_and_unreachable_clue(self):
        self.project["gates"][0]["requires"] = "signal_log"
        with self.assertRaisesRegex(ValueError, "Unreachable mandatory clues: signal_log.*possible circular gates"):
            compile_project(self.project)

    def test_playtest_must_complete_the_mystery(self):
        self.project["playtests"]["witness"].pop()
        with self.assertRaisesRegex(ValueError, "did not finish"):
            compile_project(self.project)

    def test_timeline_variant_uses_each_card_once_and_has_own_save_identity(self):
        build = compile_project(self.project, variant="timeline")
        self.assertNotEqual(build.pack.id, self.project["id"])
        self.assertEqual(build.pack.puzzle_views["signal_hut"]["title"], "Harbor warning timeline")
        self.assertIn(Command("solve", "surge blackout bell"), build.routes["puzzle"])
        self.project["puzzle_variants"]["timeline"]["puzzles"][0]["sequence"] = ["surge", "surge", "bell"]
        with self.assertRaisesRegex(ValueError, "Incompatible timeline"):
            compile_project(self.project, variant="timeline")

    @unittest.skipUnless(find_spec("PIL"), "Pillow is optional for text-only authoring")
    def test_images_bake_with_ascii_fallback_and_no_source_paths(self):
        project = json.loads(self.fixture.read_bytes())
        art = {entry["id"]: entry for entry in project["art"]}
        art["quay_at_dusk"]["style"] = "color"
        art["oren_portrait"]["style"] = "classic"
        build = compile_project(project, root=self.fixture.parent)
        self.assertEqual(build.data["portraits"]["lysa"], "lysa_portrait")
        self.assertEqual(len(build.pack.scenes["quay"].ascii_rows), art["quay_at_dusk"]["height"])
        self.assertTrue(build.pack.scenes["quay"].palette)
        self.assertFalse(build.pack.portraits["oren"].palette)
        self.assertNotIn(".png", json.dumps(build.data))
        self.assertFalse(load_project(self.fixture, no_art=True).pack.scenes)
