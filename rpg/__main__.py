import argparse
import sqlite3
import sys
from pathlib import Path

from .dialogue import OllamaDialogue, OllamaProfile
from .engine import Command, Pack
from .saves import Save

COMMAND_HELP = (
    "look, move <location>, talk <person>, inspect <object>, show <person>, "
    "present <person> <clue>, "
    "solve <symbols>, open <object>, report <person>, journal, inventory, quit"
)


def play(pack: Pack, save: Save) -> None:
    state = save.load_or_start(pack)
    print(pack.title)
    print("Actions autosave. Type help for commands or look to inspect your surroundings.")
    while True:
        location = pack.locations[state.location]
        print(f"\n{location['name']} | Turn {state.turn}")
        if pack.goal in state.flags:
            print("Mystery solved.")
            return
        try:
            verb, _, target = input("> ").strip().lower().partition(" ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if verb == "quit":
            return
        if verb == "help":
            print(COMMAND_HELP)
        elif verb == "look":
            print(location["description"])
            print("Exits: " + ", ".join(location["exits"]))
        elif verb == "journal":
            print("\n".join(pack.journal(state)) or "The journal is empty.")
        elif verb == "inventory":
            print(", ".join(pack.items[item]["name"] for item in sorted(state.inventory)) or "Empty.")
        elif verb:
            command = Command(verb, target.strip())
            result = pack.step(state, command)
            save.commit(state, command, result)
            state = result.state
            print(result.message)


def main() -> None:
    if sys.argv[1:2] == ["--release-check"]:
        from .release_checks import main as release_checks

        raise SystemExit(release_checks(sys.argv[2:]))
    if sys.argv[1:2] == ["--benchmark-voice"]:
        from .voice_benchmark import main as benchmark_voice

        benchmark_voice(sys.argv[2:])
        return
    if sys.argv[1:2] == ["--benchmark"]:
        from .benchmark import main as benchmark

        benchmark(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description="Play a local terminal mystery.")
    parser.add_argument("--pack", type=Path, default=Path("packs/ashenfell.json"))
    parser.add_argument("--save", type=Path, default=Path("ashenfell.sqlite3"))
    parser.add_argument("--tui", action="store_true", help="Open the Textual interface")
    parser.add_argument("--model", help="Select an Ollama dialogue profile for the TUI")
    parser.add_argument("--profiles", type=Path, default=Path("model-profiles.json"))
    parser.add_argument("--model-check", action="store_true", help="Test the selected model without opening a save")
    parser.add_argument("--model-log", type=Path, help="Append local Ollama requests and responses to a JSONL file")
    parser.add_argument("--character-voice", action="store_true", help="Try evidence-checked model rewrites for /ask")
    args = parser.parse_args()
    if args.model_check and not args.model:
        parser.error("--model-check requires --model")
    if args.model and not (args.tui or args.model_check):
        parser.error("--model requires --tui or --model-check")
    if args.model_log and not args.model:
        parser.error("--model-log requires --model")
    if args.character_voice and not (args.tui and not args.model_check):
        parser.error("--character-voice requires --tui")
    if args.character_voice and not args.model:
        args.model = "qwen-4b"
    try:
        provider = (OllamaDialogue(OllamaProfile.load(args.profiles, args.model), args.model_log)
                    if args.model else None)
        if args.model_check:
            try:
                provider.choose("Where is the inn?", {"inn": "Across the road.", "unsure": "I don't know."})
            except (OSError, ValueError, KeyError, TypeError) as error:
                parser.exit(1, f"{args.model} failed the model check. Verify Ollama is running "
                               f"and {provider.profile.model} is installed. {error}\n")
            print(f"{args.model} passed the Ollama structured reply check.")
            return
        pack = Pack.load(args.pack)
        save = Save(args.save)
        try:
            if args.tui:
                try:
                    from .tui import Adventure
                except ModuleNotFoundError as error:
                    if error.name != "textual":
                        raise
                    parser.exit(1, "Install the TUI dependencies from requirements-tui.txt.\n")
                Adventure(pack, save, provider=provider, character_voice=args.character_voice).run()
            else:
                play(pack, save)
        finally:
            save.close()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
