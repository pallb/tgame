import argparse
import json
import math
from pathlib import Path
from statistics import median

from .dialogue import OllamaDialogue, OllamaProfile
from .engine import Command, Pack, State
from .voice_benchmark import measured


ROOT = Path(__file__).resolve().parents[1]
LOCKED_TEXT = {
    "nessa_seal": ("garrick sealed a warning", "garrick sealed the warning", "garrick put his seal"),
    "ivo_lantern": ("light moving downhill", "light headed downhill", "lantern heading downhill"),
    "ledger": ("canceled north-road shipment", "canceled the north-road shipment"),
    "patrol": ("north gate was barred during the storm", "north gate was barred throughout the storm"),
}


def load_release_cases(pack, fixture):
    for scenario in fixture["scenarios"]:
        state = State(scenario["at"])
        for verb, target in scenario.get("steps", []):
            result = pack.step(state, Command(verb, target))
            if not result.accepted:
                raise ValueError(f"Invalid scenario setup for {scenario['id']}: {result.message}")
            state = result.state
        previous = dict(zip(("question", "approved_reply"), scenario["previous"])) if "previous" in scenario else None
        for index, question in enumerate(scenario["questions"], 1):
            yield f"{scenario['id']}:{index}", scenario["npc"], state, question, scenario["expect"], previous


def action_checks(pack):
    states = {
        "inn": pack.start_state(),
        "river": State("river", frozenset({"closed_road"})),
        "forge": State("forge"),
        "watch": State("watch"),
    }
    attempts = [
        ("inn", "give", "cellar_key"), ("inn", "present", "garrick letter"),
        ("inn", "present", "garrick nessa_seal"), ("river", "mark", "resolved"),
        ("river", "report", "mara"), ("river", "move", "cellar"), ("river", "open", "cellar"),
        ("river", "present", "mara patrol"), ("river", "show", "mara"),
        ("forge", "present", "nessa docket"), ("watch", "present", "ivo patrol"),
        ("watch", "present", "mara patrol"),
    ]
    return [
        {"location": location, "command": f"{verb} {target}",
         "unchanged": not result.accepted and result.state == states[location]}
        for location, verb, target in attempts
        for result in (pack.step(states[location], Command(verb, target)),)
    ]


def locked_matches(row):
    observed = " ".join(row["available_replies"].values()) + " " + row.get("text", "")
    return [fact for fact, phrases in LOCKED_TEXT.items()
            if fact not in row["flags"] and any(phrase in observed.casefold() for phrase in phrases)]


def summarize(rows, actions, hardware):
    selection = [row for row in rows if row["type"] == "selection"]
    review = [row for row in rows if row["type"] == "review"]
    misses = [row for row in selection if not row["correct"]]
    leaks = [(row["id"], locked_matches(row)) for row in selection if locked_matches(row)]
    closed = [row for row in selection if row["expected"] == "unsure"]
    false_refusals = sum(row.get("choice") == "unsure" for row in selection if row["expected"] != "unsure")
    times = sorted(row["elapsed_ms"] for row in selection)
    changed = [row for row in selection if row.get("rewrite") == "varied"]
    authored = [row for row in selection if row.get("rewrite") == "authored"]
    bad_approved = [row for row in review if not row["valid"] and row.get("approved") is True]
    review_errors = sum("error" in row for row in review)
    passed_actions = sum(row["unchanged"] for row in actions)
    resident, gpu = hardware["resident_bytes"], hardware["resident_gpu_bytes"]
    placement = f"{gpu / resident:.1%} GPU" if resident and gpu is not None else "GPU placement unavailable"
    lines = [
        "# Ashenfell held-out release checks", "",
        f"Model {hardware['model']} with {hardware['context']} context tokens.", "",
        f"- Correct reply selection **{len(selection) - len(misses)}/{len(selection)}**.",
        f"- Correct abstentions **{sum(row['correct'] for row in closed)}/{len(closed)}** and false refusals **{false_refusals}**.",
        f"- Model wording varied **{len(changed)}** eligible lines. **{len(authored)}** used authored wording.",
        f"- Independent review accepted **{sum(r['valid'] and r.get('approved') is True for r in review)}** good drafts "
        f"and let **{len(bad_approved)}** flawed drafts through. Review errors **{review_errors}**.",
        f"- Measured median **{median(times):.0f} ms** and P95 **{times[math.ceil(len(times) * 0.95) - 1]} ms**.",
        f"- Preload **{hardware['preload_ms']} ms**, {placement}, sampled device peak **{hardware['peak_device_mib']} MiB**.", "",
        "## Release gates", "",
        f"- Unauthorized commands rejected with state intact **{passed_actions}/{len(actions)}**.",
        f"- Locked-fact phrase matches in reply choices or displayed lines **{len(leaks)}**.",
        "- Phrase checks cover the named locked clues and their listed variants. Human assessment of wording, "
        "playtime, and a network-disabled Windows Terminal playtest are separate checks.", "",
        "## Cases to review", "",
    ]
    lines.extend(f"- {row['id']} expected `{row['expected']}`, got `{row.get('choice')}`." for row in misses)
    lines.extend(f"- {row['id']} approved this flawed draft: {row['draft']}" for row in bad_approved)
    lines.extend(f"- {case_id} matched locked evidence: {', '.join(keys)}." for case_id, keys in leaks)
    return "\n".join(lines) + "\n", not leaks and passed_actions == len(actions)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the held-out Ashenfell dialogue and engine checks.")
    parser.add_argument("--model", default="qwen-4b")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    pack = Pack.load(ROOT / "packs/ashenfell.json")
    fixture = json.loads((ROOT / "tests/ashenfell_release_cases.json").read_text(encoding="utf-8"))
    cases = list(load_release_cases(pack, fixture))
    args.output.mkdir(parents=True)
    provider = OllamaDialogue(OllamaProfile.load(ROOT / "model-profiles.json", args.model))
    print(f"Running {len(cases)} held-out cases on {args.model}", flush=True)
    with (args.output / "results.jsonl").open("x", encoding="utf-8", buffering=1) as output:
        rows, hardware = measured(args.model, provider, pack, cases, fixture["review"], output)
        actions = action_checks(pack)
        for action in actions:
            output.write(json.dumps({"type": "action", **action}) + "\n")
    report, passed = summarize(rows, actions, hardware)
    (args.output / "report.md").write_text(report, encoding="utf-8")
    (args.output / "hardware.json").write_text(json.dumps(hardware, indent=2) + "\n", encoding="utf-8")
    print(f"Release gate results: {args.output / 'report.md'}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
