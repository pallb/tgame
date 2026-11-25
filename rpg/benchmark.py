import argparse
import json
from collections import Counter
from itertools import chain, zip_longest
from pathlib import Path
from statistics import median
from time import monotonic

from .dialogue import ORIGINAL_PROMPT, STRICT_PROMPT, OllamaDialogue, OllamaProfile, available_replies
from .engine import Command, Pack


PROMPTS = {"original": ORIGINAL_PROMPT, "strict": STRICT_PROMPT}
ERRORS = (OSError, ValueError, KeyError, TypeError)


def load_cases(path: Path, pack: Pack) -> list[dict]:
    cases = []
    for npc, group in json.loads(path.read_text(encoding="utf-8")).items():
        for category, questions in group.items():
            if category == "location":
                continue
            state = pack.start_state()
            if state.location != group["location"]:
                route = {
                    "river": [Command("move", "river")],
                    "forge": [Command("move", "forge")],
                    "watch": [Command("move", "river"), Command("move", "watch")],
                }[group["location"]]
                for command in route:
                    result = pack.step(state, command)
                    if not result.accepted:
                        raise ValueError(f"Could not reach {npc}: {result.message}")
                    state = result.state
            if category == "recall":
                evidence = {"nessa": "docket", "ivo": "log"}[npc]
                for command in (Command("inspect", evidence), Command("show", npc)):
                    result = pack.step(state, command)
                    if not result.accepted:
                        raise ValueError(f"Could not unlock recall for {npc}: {result.message}")
                    state = result.state
            greeting = pack.step(state, Command("talk", npc))
            if not greeting.accepted:
                raise ValueError(f"No eligible dialogue for {npc}")
            replies = available_replies(pack, state, npc, greeting.message)
            expected = "unsure"
            if category == "answerable":
                expected = "introduce"
            elif category == "recall":
                expected = {"nessa": "recall_nessa_seal", "ivo": "recall_ivo_lantern"}[npc]
            if expected not in replies:
                raise ValueError(f"Missing expected reply {expected} for {npc}")
            for index, question in enumerate(questions, 1):
                cases.append({
                    "id": f"{npc}-{category}-{index}", "npc": npc, "category": category,
                    "location": state.location, "flags": sorted(state.flags),
                    "question": question, "choices": replies, "expected": expected,
                })
    return cases


def score(provider: OllamaDialogue, prompt: str, case: dict) -> dict:
    started = monotonic()
    try:
        choice = provider.choose(case["question"], case["choices"], prompt=prompt)
        return {"choice": choice, "correct": choice == case["expected"],
                "elapsed_ms": round((monotonic() - started) * 1000)}
    except ERRORS as error:
        return {"choice": None, "correct": False, "error": str(error)}


def summarize(rows: list[dict]) -> str:
    correct = sum(row["correct"] for row in rows)
    return f"{correct}/{len(rows)} ({correct / len(rows):.1%})" if rows else "—"


def report(rows: list[dict], preloads: dict, samples: list[dict]) -> str:
    lines = [
        "# Ashenfell dialogue benchmark", "",
        f"{len({row['id'] for row in rows})} question and game-state cases. Same options and settings across prompts. "
        "Each case starts from a fresh game state, with authored evidence revealed only in recall cases. "
        "The benchmark never opens a save.", "",
        "| Profile | Prompt | Overall | Supported | Local unknown | Unrelated | Gated | Recall | Errors | Median reply |",
        "|---|---|---|---|---|---|---|---|---:|---:|",
    ]
    groups = {}
    for row in rows:
        groups.setdefault((row["profile"], row["prompt"]), []).append(row)
    for (profile, prompt), group in groups.items():
        category_scores = [summarize([row for row in group if row["category"] == category])
                           for category in ("answerable", "local_unknown", "unrelated", "gated", "recall")]
        errors = sum("error" in row for row in group)
        times = [row["elapsed_ms"] for row in group if "elapsed_ms" in row]
        latency = f"{median(times):.0f} ms" if times else "—"
        fields = [profile, prompt, summarize(group), *category_scores, str(errors), latency]
        lines.append("| " + " | ".join(fields) + " |")
    lines.extend(["", "## Results by NPC", "",
                  "| Profile | Prompt | Garrick | Mara | Nessa | Ivo |", "|---|---|---|---|---|---|"])
    for (profile, prompt), group in groups.items():
        scores = [summarize([row for row in group if row["npc"] == npc])
                  for npc in ("garrick", "mara", "nessa", "ivo")]
        lines.append("| " + " | ".join([profile, prompt, *scores]) + " |")
    lines.extend(["", "## Model preload", ""])
    for profile, milliseconds in preloads.items():
        lines.append(f"- {profile} took {milliseconds:,} ms. Ollama may already have had the model loaded.")
    if samples:
        repeats = sum(row.get("text") == row["choices"][row["choice"]] for row in samples)
        failures = sum("error" in row for row in samples)
        lines.extend(["", "## Rephrasing samples", "",
                      f"{len(samples)} samples, {repeats} verbatim repeats and {failures} request or format errors. "
                      "Selection results above exclude the rephrasing pass. "
                      "Review the generated text for factual changes. A valid format alone does not establish fidelity.", ""])
        for row in samples:
            lines.extend([
                f"### {row['profile']} {row['prompt']} {row['id']}", "",
                f"**Question** {row['question']}", "",
                f"**Authored** {row['choices'][row['choice']]}", "",
                f"**Generated** {row.get('text', row.get('error'))}", "",
            ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Compare Ashenfell NPC reply selection on local Ollama.")
    parser.add_argument("--pack", type=Path, default=Path("packs/ashenfell.json"))
    parser.add_argument("--cases", type=Path, default=Path("tests/ashenfell_dialogue_cases.json"))
    parser.add_argument("--profiles", type=Path, default=Path("model-profiles.json"))
    parser.add_argument("--models", nargs="+", default=["qwen-1.7b", "qwen-4b"])
    parser.add_argument("--output", type=Path, required=True, help="New directory for results")
    parser.add_argument("--rephrase", type=int, default=0, metavar="N",
                        help="Sample up to N non-abstention replies per NPC, model and prompt")
    args = parser.parse_args(argv)
    if args.rephrase < 0:
        parser.error("--rephrase must be zero or greater")
    cases = load_cases(args.cases, Pack.load(args.pack))
    args.output.mkdir(parents=True)
    rows, samples, preloads = [], [], {}
    with (args.output / "results.jsonl").open("x", encoding="utf-8", buffering=1) as output:
        for profile in args.models:
            provider = OllamaDialogue(OllamaProfile.load(args.profiles, profile))
            started = monotonic()
            provider.preload()
            preloads[profile] = round((monotonic() - started) * 1000)
            for variant, prompt in PROMPTS.items():
                group = []
                print(f"Running {profile} / {variant}", flush=True)
                for case in cases:
                    row = {"profile": profile, "model": provider.profile.model, "prompt": variant,
                           **case, **score(provider, prompt, case)}
                    output.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows.append(row)
                    group.append(row)
                if args.rephrase:
                    counts = Counter()
                    candidates = [row for row in group if row["choice"] not in (None, "unsure")]
                    # Alternate useful and mistaken selections when available.
                    good = iter(sorted((row for row in candidates if row["correct"]),
                                       key=lambda row: row["category"] != "recall"))
                    bad = iter(row for row in candidates if not row["correct"])
                    for row in chain.from_iterable(zip_longest(good, bad)):
                        if row is None or counts[row["npc"]] >= args.rephrase:
                            continue
                        sample = dict(row)
                        try:
                            sample["text"] = provider.rephrase(row["question"], row["choices"][row["choice"]])
                        except ERRORS as error:
                            sample["error"] = str(error)
                        samples.append(sample)
                        counts[row["npc"]] += 1
                print(f"Completed {profile} / {variant}: {summarize(group)}", flush=True)
    if samples:
        (args.output / "rephrases.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in samples), encoding="utf-8"
        )
    (args.output / "report.md").write_text(report(rows, preloads, samples), encoding="utf-8")


if __name__ == "__main__":
    main()
