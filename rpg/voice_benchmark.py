import argparse
import json
import math
import shutil
import subprocess
from collections import Counter
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from statistics import median
from threading import Event, Thread
from time import monotonic

from .benchmark import ERRORS, load_cases
from .dialogue import VOICE_SELECTION_PROMPT, OllamaDialogue, OllamaProfile, available_replies, rewrite_choice
from .engine import Command, Pack, State


def selection_cases(pack, legacy_path, extra):
    for case in load_cases(legacy_path, pack):
        expected = case["expected"]
        index = int(case["id"].rsplit("-", 1)[-1])
        if expected == "introduce":
            if case["npc"] == "garrick" and index >= 5:
                expected = "topic_help"
            elif case["npc"] == "mara" and index >= 3:
                expected = "topic_rhyme"
        yield case["id"], case["npc"], State(case["location"], frozenset(case["flags"])), case["question"], expected, None

    for index, case in enumerate(extra, 1):
        state = State(case["at"])
        for verb, target in case.get("steps", []):
            result = pack.step(state, Command(verb, target))
            if not result.accepted:
                raise ValueError(f"Invalid benchmark state for case {index}: {result.message}")
            state = result.state
        previous = dict(zip(("question", "approved_reply"), case["previous"])) if "previous" in case else None
        yield f"current-{index}", case["npc"], state, case["question"], case["expect"], previous


def running_models():
    connection = HTTPConnection("127.0.0.1", 11434, timeout=3)
    try:
        connection.request("GET", "/api/ps")
        response = connection.getresponse()
        return json.load(response)["models"] if response.status == 200 else []
    except (OSError, HTTPException, ValueError, KeyError):
        return []
    finally:
        connection.close()


def sample_gpu(stop: Event, readings: list[int]):
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return
    while not stop.is_set():
        try:
            output = subprocess.check_output(
                [executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True, timeout=3, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            readings.append(int(output.splitlines()[0]))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return
        stop.wait(0.75)


def measured(profile, provider, pack, cases, review_cases, output):
    stop, readings = Event(), []
    monitor = Thread(target=sample_gpu, args=(stop, readings), daemon=True)
    monitor.start()
    rows = []
    try:
        loaded = any(model["name"] == provider.profile.model for model in running_models())
        started = monotonic()
        provider.preload()
        preload_ms = round((monotonic() - started) * 1000)
        resident = next((model for model in running_models() if model["name"] == provider.profile.model), {})
        for case_id, npc, state, question, expected, previous in cases:
            greeting = pack.step(state, Command("talk", npc))
            if not greeting.accepted:
                raise ValueError(f"NPC unavailable in {case_id}")
            replies = available_replies(pack, state, npc, greeting.message, focus=True)
            if expected not in replies:
                raise ValueError(f"Expected unavailable reply {expected} in {case_id}")
            row = {"type": "selection", "profile": profile, "id": case_id, "npc": npc,
                   "question": question, "expected": expected, "available_replies": replies,
                   "flags": sorted(state.flags), "inventory": sorted(state.inventory)}
            started = monotonic()
            try:
                choice = provider.choose(question, replies, prompt=VOICE_SELECTION_PROMPT, previous=previous)
                row["choice"] = choice
                row["correct"] = choice == expected
                line = replies[choice]
                row["approved_line"] = line
                row["text"] = line
                try:
                    row["text"] = rewrite_choice(provider, pack, state, npc, choice, question, line)
                except ERRORS as error:
                    row["rewrite_error"] = str(error)
                style = pack.dialogue_style.get(npc, {})
                topic = style.get("topics", {}).get(choice.removeprefix("topic_"), {})
                if choice != "unsure" and style and not topic.get("fixed"):
                    row["rewrite"] = "varied" if row["text"] != line else "authored"
            except ERRORS as error:
                row["error"] = str(error)
                row["correct"] = False
            row["elapsed_ms"] = round((monotonic() - started) * 1000)
            rows.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
        for index, case in enumerate(review_cases, 1):
            row = {"type": "review", "profile": profile, "id": f"review-{index}", **case}
            try:
                row["violations"] = provider.review(case["npc"], case["evidence"], case["draft"])
                row["approved"] = not row["violations"]
            except ERRORS as error:
                row["error"] = str(error)
            rows.append(row)
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        stop.set()
        monitor.join(timeout=4)
    stats = {
        "model": provider.profile.model, "already_loaded": loaded, "preload_ms": preload_ms,
        "resident_bytes": resident.get("size"), "resident_gpu_bytes": resident.get("size_vram"),
        "context": resident.get("context_length"), "digest": resident.get("digest"),
        "peak_device_mib": max(readings, default=None),
    }
    return rows, stats


def result_report(results, hardware):
    lines = ["# Ashenfell character voice benchmark", "",
             "The selection timings include draft and review when the reply uses them. "
             "The 80 legacy cases are rerun with the current dialogue choices, and 12 new cases cover context and game state.", "",
             "| Profile | Legacy cases | Current cases | Correct abstentions | Varied / eligible | Median | P95 |",
             "|---|---:|---:|---:|---:|---:|---:|",
             ]
    for profile, rows in results.items():
        selections = [row for row in rows if row["type"] == "selection"]
        legacy = [row for row in selections if not row["id"].startswith("current-")]
        current = [row for row in selections if row["id"].startswith("current-")]
        unknown = [row for row in selections if row["expected"] == "unsure"]
        counts = Counter(row.get("rewrite") for row in selections)
        times = sorted(row["elapsed_ms"] for row in selections)
        scores = [f"{sum(row['correct'] for row in group)}/{len(group)}" for group in (legacy, current, unknown)]
        lines.append(f"| {profile} | {' | '.join(scores)} | {counts['varied']}/{counts['varied'] + counts['authored']} "
                     f"| {median(times):.0f} ms | {times[math.ceil(len(times) * 0.95) - 1]} ms |")
    lines += ["", "## Independent review cases", "",
              "| Profile | Good drafts accepted | Bad drafts rejected | Review errors |",
              "|---|---:|---:|---:|"]
    for profile, rows in results.items():
        review = [row for row in rows if row["type"] == "review"]
        good = [row for row in review if row["valid"]]
        bad = [row for row in review if not row["valid"]]
        lines.append(f"| {profile} | {sum(r.get('approved') is True for r in good)}/{len(good)} "
                     f"| {sum(r.get('approved') is False for r in bad)}/{len(bad)} | {sum('error' in r for r in review)} |")
    lines += ["", "## Model loading", "",
              "Peak device memory is sampled system-wide and includes other GPU applications. "
              "Ollama residency shows how much of the model allocation was on the GPU.", ""]
    for profile, stats in hardware.items():
        size = stats["resident_bytes"]
        gpu = stats["resident_gpu_bytes"]
        residency = f"{gpu / size:.1%} GPU" if size and gpu is not None else "GPU placement unavailable"
        lines.append(f"- **{profile}** took {stats['preload_ms']:,} ms to preload "
                     f"({'already resident' if stats['already_loaded'] else 'cold'}), {residency}, "
                     f"context {stats['context']}, sampled peak {stats['peak_device_mib']} MiB.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark the current character-voice pipeline on local Ollama.")
    parser.add_argument("--models", nargs="+", default=["qwen-4b", "qwen-8b"])
    parser.add_argument("--output", type=Path, required=True, help="New directory for benchmark results")
    args = parser.parse_args(argv)
    pack = Pack.load(Path("packs/ashenfell.json"))
    extras = json.loads(Path("tests/ashenfell_voice_cases.json").read_text(encoding="utf-8"))
    cases = list(selection_cases(pack, Path("tests/ashenfell_dialogue_cases.json"), extras["selection"]))
    args.output.mkdir(parents=True)
    results, hardware = {}, {}
    with (args.output / "results.jsonl").open("x", encoding="utf-8", buffering=1) as output:
        for profile in args.models:
            provider = OllamaDialogue(OllamaProfile.load(Path("model-profiles.json"), profile))
            print(f"Running {profile} ({len(cases)} selection cases)", flush=True)
            results[profile], hardware[profile] = measured(profile, provider, pack, cases, extras["review"], output)
            print(f"Finished {profile}: {hardware[profile]}", flush=True)
            if profile != args.models[-1]:
                provider.request_chat("unload", {"model": provider.profile.model, "stream": False, "keep_alive": 0})
    (args.output / "hardware.json").write_text(json.dumps(hardware, indent=2) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text(result_report(results, hardware), encoding="utf-8")


if __name__ == "__main__":
    main()
