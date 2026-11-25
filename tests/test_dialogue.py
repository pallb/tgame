import unittest
from unittest.mock import patch

from rpg.dialogue import OllamaDialogue, OllamaProfile


class VoiceRewriteTest(unittest.TestCase):
    def setUp(self):
        self.provider = OllamaDialogue(OllamaProfile("test"))

    def test_checker_gets_evidence_and_rejects_actor_change(self):
        evidence = "Nessa confirms Garrick sealed a warning for the merchant."
        draft = "I sealed the warning for the merchant. Garrick knew about it."
        with patch.object(OllamaDialogue, "dialogue_object", side_effect=[
            {"line": draft}, {"violations": ["Wrong actor."]},
        ]) as request:
            result = self.provider.rewrite("Who sealed it?", evidence, "nessa", "Precise", ["warning", "merchant"])
        self.assertEqual(result, evidence)
        self.assertEqual(request.call_args.args[2], {"npc": "nessa", "evidence": evidence, "draft": draft})

    def test_mechanical_check_requires_lockbox_order(self):
        evidence = "Reed, moon, fish."
        with patch.object(OllamaDialogue, "dialogue_object", return_value={"line": "Fish, moon, reed."}) as request:
            result = self.provider.rewrite("What's the order?", evidence, "mara", "Direct", ["reed", "moon", "fish"])
        self.assertEqual(result, evidence)
        request.assert_called_once()

    def test_approved_rewrite_is_returned(self):
        with patch.object(OllamaDialogue, "dialogue_object", side_effect=[
            {"line": "I heard horses down by the river."},
            {"violations": []},
        ]):
            result = self.provider.rewrite("What did you hear?", "I heard horses near the river.",
                                           "garrick", "Gruff", ["horses", "river"])
        self.assertEqual(result, "I heard horses down by the river.")

    def test_garrick_offer_has_its_own_fixed_topic(self):
        from pathlib import Path

        from rpg.dialogue import available_replies
        from rpg.engine import Command, Pack

        path = Path(__file__).resolve().parents[1] / "packs" / "ashenfell.json"
        pack = Pack.load(path)
        evidence = pack.rules[("inn", Command("talk", "garrick"))].message
        replies = available_replies(pack, pack.start_state(), "garrick", evidence, focus=True)
        self.assertEqual(replies["introduce"], "I heard horses near the river last night.")
        self.assertIn("trusted me and I'll help", replies["topic_help"])
        self.assertTrue(pack.dialogue_style["garrick"]["topics"]["help"]["fixed"])
