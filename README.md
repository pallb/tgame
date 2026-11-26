# Ashenfell prototype

Explore a terminal mystery about a missing merchant across five locations, with four characters and ten journal entries to discover. The Python engine loads the world and rules from `packs/ashenfell.json`. Dialogue is scripted and both interfaces run offline after setup.

## Textual interface

On this workspace, the launcher can use the local TUI dependencies in `.deps`:

```powershell
.\play.cmd --tui --save ashenfell.sqlite3
```

On another machine, install the interface with your Python 3.10+ interpreter, then launch it:

```powershell
python -m pip install -r requirements-tui.txt
python -m rpg --tui --save ashenfell.sqlite3
```

- **F2** or `/map` shows your position, visited places, and locked routes. Select a nearby destination with the arrow keys and press Enter.
- **F3** or `/journal` opens the evidence board. Select a clue to see its source, location and certainty. **Compare linked clue** brings up a related clue you have already discovered. In model-enabled play, **Ask witness** opens the conversation with a suggested question when that witness is nearby.
- **F6** or `/characters` opens the character board. Select a person to see where to find them, their testimony, and discovered evidence about them. In model-enabled play, **Talk to** opens a conversation with a nearby character.
- Click **Views** or **Actions here** entries in the sidebar to open a panel or run a command. You can also focus a menu with Tab and select an entry with Enter.
- Type `try lockbox` or `/puzzle`, or press **F4**, to open the lockbox at the landing. Click the engravings or select them with the arrow keys and Enter. Click **Try combination** or press **F5** to test the slots. Use **Undo**, **Backspace**, or **Reset** to revise the attempt.
- **Esc** closes a panel. **Up** and **Down** browse command history from the input. **Ctrl+Q** quits.
- Type the start of a command and press **Right** to accept its suggested completion.

The Textual interface and the plain prompt can resume the same save. Textual restores the last 50 saved actions in the transcript.

## Optional local dialogue

With Ollama running locally and the selected model installed:

```powershell
ollama pull qwen3:4b-instruct
.\play.cmd --model-check --model qwen-4b
.\play.cmd --tui --model qwen-4b --save ashenfell.sqlite3
```

On Windows, open Ollama from the Start menu to start its background server. Ashenfell connects directly to that local server. You can ignore Ollama's app integration prompts. The title screen starts loading the selected model. If the model takes longer than the intro, you can start playing while it finishes. An early `/ask` waits for the same load. The default timeout is 60 seconds and can be adjusted with `timeout_seconds` in the model profile.

Try `/ask garrick Where did you hear the horses?`. This first integration uses the model to select from authored replies available to the current NPC. The engine still controls what is revealed and which actions are legal. Press **Esc** at the prompt to discard a pending reply. If the model is unavailable or returns an invalid choice, the scripted reply is used.

To try the smaller profile, install `qwen3:1.7b` and launch with `--model qwen-1.7b`. Both profiles can use the same save. Edit `model-profiles.json` or point `--profiles` at a separate configuration to try other Ollama models. Running without `--model` uses the scripted game, including for `/ask`.

To try experimental character-voice dialogue:

```powershell
.\play.cmd --tui --model qwen-4b --character-voice --model-log model-trace.jsonl
```

With `--character-voice`, 4B is selected by default. Click **Talk to** in the sidebar or type `talk <npc>` to open a conversation. Click a topic or type a question directly. A follow-up can refer to the last answered question in that panel. Esc closes the conversation and discards a pending reply. Recent exchanges stay available when you reopen the panel during the same game session. `/ask` remains available for a one-off question.

Use **Show evidence** in the conversation panel to present a discovered clue the witness can use. The typed equivalent is `present <person> <clue-id>` in the main prompt or `present <clue-id>` inside the conversation. In scripted play, `/chat <person>` opens the same panel. NPCs remember what you show them after saving and resuming. For example, after asking about Mara's theory, you can show her the patrol log with `present mara patrol`.

After selecting an approved reply, the model drafts different wording from the NPC's voice and the facts authored for that reply. The game checks protected phrases in order, then asks the model in a separate request to review the draft against the original authored reply. On rejection or a model error, the game uses the authored reply. `unsure` is displayed as authored. The engine applies the same clue and quest rules in either case. The model's review can miss changes in meaning, so this mode is opt-in. The debug file records the draft and review requests as separate entries.

Character-voice mode also offers focused replies for NPC names, Garrick's testimony and offer, and Mara's surroundings. Questions about the lockbox, rhyme, cellar door and key each get their own evidence. Door and key replies depend on the current game state. Discussing these topics does not add Mara's north-road testimony to the journal. Mechanics such as the exact rhyme, key use and Garrick's condition use fixed lines. The review response lists specific factual violations. An empty list means the draft passed review.

To capture Ollama exchanges for later review:

```powershell
.\play.cmd --tui --model qwen-1.7b --model-log model-trace.jsonl
Get-Content .\model-trace.jsonl -Tail 5
```

The log appends one JSON object per completed request. It includes the full Ollama payload, returned reply ID and timing fields when available, or a request error. It also includes the startup preload. Because it records player questions and dialogue choices, enable it for sessions you want to inspect.

## Dialogue benchmark

With both local Ollama models installed, run from the project folder:

```powershell
.\play.cmd --benchmark --output benchmarks/my-run --rephrase 2
```

Use a new output folder each run. The command tests 20 cases per NPC against the original and strict prompts. It writes an overview to `report.md` and detailed selection results to `results.jsonl` inside the output folder. `--rephrase 2` samples up to two selected authored lines per NPC and configuration, saving the results to `rephrases.jsonl`. Omit the option to run selection alone. Generated wording is for review; the game continues to display its authored dialogue.

To compare the current conversation pipeline with the installed 4B and Q4 8B profiles:

```powershell
.\play.cmd --benchmark-voice --output benchmarks/my-voice-run
```

This reruns 80 legacy cases and adds 12 cases for follow-ups and changing world state. It also checks 12 fixed candidate drafts for factual drift. The report includes end-to-end model time and GPU residency. Sampled peak GPU memory includes other GPU applications.

Run the held-out release suite after dialogue or engine changes:

```powershell
.\play.cmd --release-check --output benchmarks/my-release-run
```

The report covers 108 questions grouped by story situation, six independent review cases, and 12 unauthorized commands. It measures selection, refusals, rewrites, model timings and specific locked-clue phrases. The phrase checks do not cover every possible paraphrase.

## Plain prompt

On Windows, run the launcher from the project folder. It can use the Codex desktop Python runtime even when `python` is missing from PATH.

```powershell
.\play.cmd --save ashenfell.sqlite3
```

With a standalone Python install, you can also run:

```powershell
python -m rpg --save ashenfell.sqlite3
```

Start with `look` and `talk garrick`. Use `help` for commands and `journal` to review testimony and physical evidence. Accepted actions autosave. Use `quit` and rerun the same command to resume, or choose a new save filename to start over.

## Tests

Run the engine and UI tests with the Textual dependencies installed. The UI test is skipped when Textual is absent.

```powershell
python -m unittest discover -s tests -v
```


## Author a pack

Open Mystery Studio from the checkout with `.\play.cmd --studio`. You can also open a project directly.

```powershell
.\play.cmd --studio authoring_examples/lantern_at_low_tide.json
```

Use **Projects** to start from a template or import a draft, then edit sections in **Design**. Save with **Ctrl+S** and press **F5** to build and play a fresh preview. Quit the preview with **Ctrl+Q** to return to Studio. **Playtest** lets you choose a puzzle variant, resume a preview during the current Studio session, validate every variant, view walkthroughs, and export a runtime pack. Use **Revisions** to review and apply proposals or restore a saved version.

Studio uses `requirements-tui.txt`. Install `requirements-authoring.txt` for art, or select **Text-only build** to playtest without it.

**Open project** starts in a file picker. Everywhere else that asks for a file path has a **Browse** button. Use the arrow keys and **Enter** or click a file or folder. For a new file, browse to the destination folder, enter the filename, and choose **Use this path**.

Use the [pack authoring quickstart](docs/pack-authoring-quickstart.md) to validate, bake and play the included mystery. The [authoring plan](docs/pack-authoring-plan.md) tracks the planned asset pipeline and model-assisted revision workflow.
