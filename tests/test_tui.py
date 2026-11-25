import unittest
from importlib.util import find_spec
from pathlib import Path
from threading import Event

from rpg.engine import Pack
from rpg.saves import Save


@unittest.skipUnless(find_spec("textual"), "Textual dependencies are optional")
class AdventureTest(unittest.IsolatedAsyncioTestCase):
    def new_game(self, **options):
        from rpg.tui import Adventure

        path = Path(__file__).resolve().parents[1] / "packs" / "ashenfell.json"
        save = Save(Path(":memory:"))
        self.addCleanup(save.close)
        return Adventure(Pack.load(path), save, **options)

    async def test_startup_animates_and_holds_for_five_seconds(self):
        from textual.widgets import Static

        from rpg.splash import Startup

        started = Event()
        release = Event()
        chosen = Event()

        class Provider:
            def preload(self):
                started.set()
                release.wait(12)

            def choose(self, question, replies):
                chosen.set()
                return "introduce"

        game = self.new_game(provider=Provider())
        async with game.run_test() as pilot:
            try:
                self.assertIsInstance(game.screen, Startup)
                first = str(game.screen.query_one("#startup-progress", Static).content)
                await pilot.pause(0.6)
                self.assertTrue(started.is_set())
                self.assertNotEqual(first, str(game.screen.query_one("#startup-progress", Static).content))
                await pilot.pause(4.0)
                self.assertIsInstance(game.screen, Startup)
                await pilot.pause(1.0)
                self.assertNotIsInstance(game.screen, Startup)
                game.ask("garrick Did you see horses?")
                await pilot.pause()
                self.assertFalse(chosen.is_set())
                release.set()
                await game.dialogue_worker.wait()
                self.assertTrue(chosen.is_set())
                self.assertEqual(game.state.turn, 1)
            finally:
                release.set()

    async def test_invalid_model_reply_falls_back_without_sending_locked_dialogue(self):
        class Provider:
            def choose(self, question, replies):
                self.question = question
                self.replies = replies
                return "transfer_key"

        provider = Provider()
        game = self.new_game(provider=provider, show_startup=False)
        async with game.run_test() as pilot:
            game.ask("garrick Where is the merchant?")
            await game.dialogue_worker.wait()
            await pilot.pause()
            self.assertEqual(provider.question, "Where is the merchant?")
            self.assertEqual(set(provider.replies), {"introduce", "unsure"})
            self.assertEqual(game.state.flags, {"horses"})
            self.assertEqual(game.state.inventory, set())
            self.assertEqual(game.state.turn, 1)

    async def test_verified_voice_changes_saved_text_and_preserves_authored_turn(self):
        class Provider:
            def choose(self, question, replies, *, prompt):
                return "introduce"

            def rewrite(self, question, evidence, npc, voice, protected, facts):
                self.evidence = evidence
                self.facts = facts
                return "Horses down by the river last night. Heard them myself."

        provider = Provider()
        game = self.new_game(provider=provider, character_voice=True, show_startup=False)
        async with game.run_test():
            game.ask("garrick What did you hear?")
            await game.dialogue_worker.wait()
            self.assertIn("I heard horses near the river", provider.evidence)
            self.assertIn("When: last night", provider.facts[0])
            self.assertEqual(game.state.flags, {"horses"})
            self.assertFalse(game.state.inventory)
            self.assertTrue(game.save.recent_events(game.state.turn)[0][2].startswith("Garrick: Horses down"))

    async def test_lockbox_topic_does_not_add_merchant_testimony(self):
        class Provider:
            def choose(self, question, replies, *, prompt):
                self.replies = replies
                return "topic_lockbox"

            def rewrite(self, question, evidence, npc, voice, protected, facts):
                return evidence

        from rpg.engine import Command

        provider = Provider()
        game = self.new_game(provider=provider, character_voice=True, show_startup=False)
        async with game.run_test():
            game.apply_command(Command("move", "river"))
            game.ask("mara Is that a lockbox?")
            await game.dialogue_worker.wait()
            self.assertNotIn("topic_cellar_key", provider.replies)
            self.assertIn("topic_locked_door", provider.replies)
            self.assertNotIn("topic_open_door", provider.replies)
            self.assertEqual(game.state.turn, 1)
            self.assertNotIn("closed_road", game.state.flags)

    async def test_talk_opens_conversation_and_followup_reuses_context(self):
        from textual.widgets import Input

        from rpg.tui import Conversation

        class Provider:
            def choose(self, question, replies, *, prompt, previous=None):
                self.calls.append((question, previous))
                return "introduce" if previous is None else "unsure"

            def rewrite(self, question, evidence, npc, voice, protected, facts):
                return evidence

            calls = []

        provider = Provider()
        game = self.new_game(provider=provider, character_voice=True, show_startup=False)
        async with game.run_test(size=(90, 28)) as pilot:
            game.query_one("#command", Input).value = "talk garrick"
            await pilot.press("enter")
            self.assertIsInstance(game.screen, Conversation)
            self.assertEqual(game.state.turn, 0)
            await pilot.click("#topics", offset=(3, 1))
            await game.dialogue_worker.wait()
            self.assertEqual(game.state.flags, {"horses"})
            game.screen.query_one("#question", Input).value = "How many were there?"
            await pilot.press("enter")
            await game.dialogue_worker.wait()
            self.assertEqual(provider.calls[0], ("What did you hear by the river?", None))
            self.assertEqual(provider.calls[1][0], "How many were there?")
            self.assertEqual(provider.calls[1][1]["question"], provider.calls[0][0])
            self.assertEqual(game.state.turn, 1)
            await pilot.press("escape")
            self.assertNotIsInstance(game.screen, Conversation)
            await pilot.click("#local-actions", offset=(3, 2))
            self.assertIsInstance(game.screen, Conversation)
            self.assertTrue(any("How many were there?" in line.plain for line in game.screen.history))

    async def test_can_cancel_dialogue_and_open_map_while_model_waits(self):
        release = Event()
        started = Event()

        class Provider:
            def choose(self, question, replies):
                started.set()
                release.wait(5)
                return "introduce"

        game = self.new_game(provider=Provider(), show_startup=False)
        async with game.run_test() as pilot:
            try:
                game.ask("garrick Did you see horses?")
                await pilot.press("f2")
                self.assertTrue(started.is_set())
                self.assertEqual(game.screen.__class__.__name__, "TravelMap")
                await pilot.press("escape", "escape")
                self.assertTrue(game.dialogue_worker.is_cancelled)
                self.assertEqual(game.state.turn, 0)
            finally:
                release.set()

    async def test_keyboard_puzzle_route_and_evidence(self):
        from textual.widgets import Input, RichLog, Static

        from rpg.tui import EvidenceBoard, Lockbox, TravelMap

        game = self.new_game(show_startup=False)

        async with game.run_test(size=(80, 24)) as pilot:
            async def submit(text):
                field = game.query_one(Input)
                field.focus()
                field.value = text
                await pilot.press("enter")

            await pilot.click("#views", offset=(3, 1))
            self.assertIsInstance(game.screen, TravelMap)
            await pilot.press("enter")
            self.assertEqual(game.state.location, "river")
            await submit("talk mara")
            await pilot.press("up")
            self.assertEqual(game.query_one(Input).value, "talk mara")

            await submit("try lockbox")
            self.assertIsInstance(game.screen, Lockbox)
            before = game.state
            await pilot.press("home", "enter", "enter", "enter", "f5")
            self.assertIsInstance(game.screen, Lockbox)
            self.assertIn("combination didn't match", str(game.screen.query_one("#lock-feedback", Static).content))
            self.assertEqual(game.state, before)
            await pilot.click("#reset-lock")
            await pilot.press("end", "enter", "up", "enter", "home", "enter", "f5")
            self.assertEqual(game.state.inventory, {"spare_key"})

            await submit("open cellar")
            await submit("move cellar")
            await submit("inspect ledger")
            await pilot.press("f3")
            self.assertIsInstance(game.screen, EvidenceBoard)
            board = game.screen.query_one(RichLog)
            lines = " ".join(line.text for line in board.lines)
            self.assertIn("Testimony", lines)
            self.assertIn("Evidence", lines)
            await pilot.press("escape")
            await submit("move river")
            await submit("report mara")
            self.assertIn(game.pack.goal, game.state.flags)
            self.assertEqual(game.save.load_or_start(game.pack), game.state)
