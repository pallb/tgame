import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from rpg.engine import Command, Pack
from rpg.saves import Save


class AshenfellTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "packs" / "ashenfell.json"
        self.pack = Pack.load(path)

    def advance(self, state, commands, save=None):
        for verb, target in commands:
            command = Command(verb, target)
            result = self.pack.step(state, command)
            self.assertTrue(result.accepted, result.message)
            if save is not None:
                save.commit(state, command, result)
            state = result.state
        return state

    def test_both_routes_survive_save_and_resume(self):
        routes = {
            "cellar_key": [
                ("talk", "garrick"), ("inspect", "letter"),
                ("show", "garrick"), ("move", "river"),
            ],
            "spare_key": [
                ("move", "river"), ("talk", "mara"), ("solve", "reed moon fish"),
            ],
        }
        ending = [
            ("open", "cellar"), ("move", "cellar"), ("inspect", "ledger"),
            ("move", "river"), ("report", "mara"),
        ]
        for key, route in routes.items():
            with self.subTest(key=key), TemporaryDirectory() as directory:
                path = Path(directory) / "game.sqlite3"
                save = Save(path)
                try:
                    middle = self.advance(save.load_or_start(self.pack), route, save)
                finally:
                    save.close()
                save = Save(path)
                try:
                    resumed = save.load_or_start(self.pack)
                    self.assertEqual(resumed, middle)
                    self.assertEqual(resumed.inventory, {key})
                    self.assertFalse(any("ledger" in line for line in self.pack.journal(resumed)))
                    final = self.advance(resumed, ending, save)
                    self.assertIn(self.pack.goal, final.flags)
                    self.assertEqual(final, save.load_or_start(self.pack))
                    self.assertEqual(final, self.advance(self.pack.start_state(), route + ending))
                finally:
                    save.close()

    def test_blocked_actions_leave_state_and_event_log_unchanged(self):
        save = Save(Path(":memory:"))
        self.addCleanup(save.close)
        initial = save.load_or_start(self.pack)
        river = self.advance(initial, [("move", "river")], save)
        for state, command in [
            (initial, Command("show", "garrick")),
            (river, Command("give", "cellar_key")),
            (river, Command("open", "cellar")),
            (river, Command("move", "cellar")),
            (river, Command("solve", "read fish moon")),
            (river, Command("inspect", "ledger")),
            (river, Command("report", "mara")),
        ]:
            with self.subTest(command=command):
                result = self.pack.step(state, command)
                self.assertFalse(result.accepted)
                self.assertEqual(result.state, state)
                if command.verb == "solve":
                    self.assertIn("combination didn't match", result.message)
                save.commit(state, command, result)
        self.assertEqual(save.load_or_start(self.pack), river)
        self.assertEqual(save.connection.execute("SELECT count(*) FROM events").fetchone(), (1,))

    def test_stale_turn_cannot_overwrite_saved_turn(self):
        save = Save(Path(":memory:"))
        self.addCleanup(save.close)
        initial = save.load_or_start(self.pack)
        river = self.advance(initial, [("move", "river")], save)
        command = Command("inspect", "letter")
        with self.assertRaisesRegex(ValueError, "Save changed"):
            save.commit(initial, command, self.pack.step(initial, command))
        self.assertEqual(save.load_or_start(self.pack), river)

    def test_optional_witness_clues_require_physical_evidence(self):
        forge = self.advance(self.pack.start_state(), [("move", "forge"), ("talk", "nessa")])
        self.assertFalse(self.pack.step(forge, Command("show", "nessa")).accepted)
        state = self.advance(forge, [
            ("inspect", "docket"), ("show", "nessa"), ("move", "inn"),
            ("move", "river"), ("move", "watch"), ("talk", "ivo"),
        ])
        self.assertFalse(self.pack.step(state, Command("show", "ivo")).accepted)
        state = self.advance(state, [("inspect", "log"), ("show", "ivo")])
        self.assertIn("nessa_seal", state.flags)
        self.assertIn("ivo_lantern", state.flags)
