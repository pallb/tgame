import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from rpg.author_provider import suggest
from rpg.author_revisions import digest, encode, prepare_prompt, revise


class AuthorRevisionTest(unittest.TestCase):
    def setUp(self):
        self.checkout = Path(__file__).resolve().parents[1]
        fixture = self.checkout / "authoring_examples" / "lantern_at_low_tide.json"
        self.project = json.loads(fixture.read_bytes())
        self.project["locks"] = ["/brief/canon", "/clues/2/text"]
        # The revision tests focus on the story structure and require no art dependencies.
        self.project.pop("art", None)
        self.original = encode(self.project)

    def proposal(self, original, edits):
        return {"proposal_schema": 1, "base_sha256": digest(original), "edits": edits}

    def test_rejects_changed_locks_and_stale_proposals(self):
        original = self.original
        changed_brief = {**self.project["brief"], "canon": "The lamp was stolen."}
        proposal = self.proposal(original, [{"path": "/brief", "before": self.project["brief"], "after": changed_brief}])
        with self.assertRaisesRegex(ValueError, "locked field /brief/canon"):
            revise(original, proposal, self.checkout)
        with self.assertRaisesRegex(ValueError, "different project revision"):
            revise(original + b"\n", proposal, self.checkout)

    def test_import_review_apply_and_rollback_through_normal_launcher(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            draft = directory / "draft.json"
            project = directory / "project.json"
            proposal_file = directory / "proposal.json"
            draft.write_bytes(self.original)

            def author(*args):
                result = subprocess.run([sys.executable, "-m", "rpg", "--author", *map(str, args)],
                                        capture_output=True, encoding="utf-8", cwd=self.checkout,
                                        env={**os.environ, "PYTHONUTF8": "1"})
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            author("import-draft", draft, "--output", project)
            original = project.read_bytes()
            edits = [
                {"path": "/actions/1/message", "before": self.project["actions"][1]["message"],
                 "after": "Oren studies the chart. 'Now I know why you came.' He unlocks the storehouse."},
                {"path": "/characters/1/voice", "before": self.project["characters"][1]["voice"],
                 "after": "Speaks only in short questions."},
            ]
            proposal_file.write_bytes(encode(self.proposal(original, edits)))
            preview = author("review", project, proposal_file, "--only", "1")
            self.assertIn("+\"Oren studies the chart.", preview)
            self.assertEqual(project.read_bytes(), original)
            author("apply", project, proposal_file, "--only", "1")
            first = project.read_bytes()
            revised = json.loads(first)
            self.assertEqual(revised["actions"][1]["message"], edits[0]["after"])
            self.assertEqual(revised["characters"][1]["voice"], edits[1]["before"])
            self.assertEqual(revised["version"], 2)

            timeline = revised["puzzle_variants"]["timeline"]
            swapped = [
                {"path": "/puzzles", "before": revised["puzzles"], "after": timeline["puzzles"]},
                {"path": "/playtests/puzzle", "before": revised["playtests"]["puzzle"],
                 "after": timeline["playtests"]["puzzle"]},
                {"path": "/locations/1/description", "before": revised["locations"][1]["description"],
                 "after": timeline["location_descriptions"]["signal_hut"]},
                {"path": "/characters/0/opening_reply", "before": revised["characters"][0]["opening_reply"],
                 "after": timeline["character_replies"]["lysa"]},
            ]
            proposal_file.write_bytes(encode(self.proposal(first, swapped)))
            author("apply", project, proposal_file)
            self.assertEqual(json.loads(project.read_bytes())["brief"]["canon"], self.project["brief"]["canon"])
            self.assertEqual(json.loads(project.read_bytes())["clues"][2]["text"], self.project["clues"][2]["text"])
            runtime = directory / "timeline.json"
            author("bake", project, "--output", runtime)
            self.assertIn("solve surge blackout bell", author("walkthrough", project))
            self.assertEqual(json.loads(runtime.read_bytes())["version"], 3)
            self.assertIn(digest(first), author("history", project))
            author("rollback", project, "--to", digest(first)[:12])
            self.assertEqual(project.read_bytes(), first)
            self.assertIn("solve wave star shell", author("walkthrough", project))

    def test_prepare_includes_only_requested_sections(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "draft.json"
            source.write_bytes(self.original)
            prompt = prepare_prompt(source, False, ["/characters/1"], "Can Oren be more welcoming?")
            self.assertIn("base_sha256", prompt)
            self.assertIn("Oren", prompt)
            self.assertNotIn(self.project["brief"]["canon"], prompt)


class AuthorProviderTest(unittest.TestCase):
    def test_both_providers_return_same_structured_proposal(self):
        proposal = {"proposal_schema": 1, "base_sha256": "example", "edits": []}
        body = json.dumps({"payload_json": json.dumps(proposal)})
        responses = [
            ("openai", {"status": "completed", "output": [{"content": [{"type": "output_text", "text": body}]}]}),
            ("claude", {"stop_reason": "end_turn", "content": [{"type": "text", "text": body}]}),
        ]
        for name, response in responses:
            with self.subTest(provider=name), patch.dict(os.environ, {"OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"}):
                with patch("rpg.author_provider.request_json", return_value=response) as send:
                    self.assertEqual(suggest(name, "test-model", "Selected author prompt"), proposal)
                    request = send.call_args.args[-1]
                    self.assertEqual(request["model"], "test-model")
                    self.assertIn("Selected author prompt", json.dumps(request))

    def test_local_ollama_uses_an_installed_model_and_returns_raw_project_json(self):
        proposal = {"proposal_schema": 1, "base_sha256": "example", "edits": []}
        with patch("rpg.author_provider.request_ollama", side_effect=[
            {"models": [{"name": "qwen3:4b-instruct"}]},
            {"done": True, "done_reason": "stop", "message": {"content": json.dumps(proposal)}},
        ]) as local:
            self.assertEqual(suggest("ollama", "qwen3:4b-instruct", "Local prompt", context=4096), proposal)
        self.assertEqual(local.call_args_list[0].args, ("/api/tags",))
        path, payload = local.call_args_list[1].args
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload["messages"][-1]["content"], "Local prompt")
        self.assertEqual(payload["options"]["num_ctx"], 4096)

    def test_local_ollama_rejects_a_remote_alias_before_sending_the_prompt(self):
        with patch("rpg.author_provider.request_ollama", return_value={
            "models": [{"name": "alias:latest", "remote_host": "remote.example"}],
        }) as local:
            with self.assertRaisesRegex(ValueError, "points to a remote"):
                suggest("ollama", "alias", "Do not send")
        local.assert_called_once_with("/api/tags")

    def test_local_ollama_rejects_truncated_proposals(self):
        with patch("rpg.author_provider.request_ollama", side_effect=[
            {"models": [{"name": "qwen3:4b-instruct"}]},
            {"done": True, "done_reason": "length", "message": {"content": '{"edits":'}},
        ]):
            with self.assertRaisesRegex(ValueError, "did not finish"):
                suggest("ollama", "qwen3:4b-instruct", "Local prompt")

    def test_prepared_local_revision_binds_metadata_from_the_author_prompt(self):
        fields = {
            "base_sha256": "a" * 64,
            "locked_paths": [],
            "sections": {"/actions/1": {"message": "Old line"}},
        }
        prompt = "Revise the line.\n\n" + json.dumps(fields)
        answer = {"base_sha256": "incorrect model copy", "edits": [
            {"path": "/actions/1/message", "before": "incorrect", "after": "New line"},
        ]}
        with patch("rpg.author_provider.request_ollama", side_effect=[
            {"models": [{"name": "qwen3:4b-instruct"}]},
            {"done": True, "message": {"content": json.dumps(answer)}},
        ]):
            self.assertEqual(suggest("ollama", "qwen3:4b-instruct", prompt), {
                "proposal_schema": 1, "base_sha256": fields["base_sha256"],
                "edits": [{"path": "/actions/1/message", "before": "Old line", "after": "New line"}],
            })

        answer["edits"][0]["path"] = "/actions/2/message"
        with patch("rpg.author_provider.request_ollama", side_effect=[
            {"models": [{"name": "qwen3:4b-instruct"}]},
            {"done": True, "message": {"content": json.dumps(answer)}},
        ]):
            with self.assertRaisesRegex(ValueError, "outside the prepared scope"):
                suggest("ollama", "qwen3:4b-instruct", prompt)
