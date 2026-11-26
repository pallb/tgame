# Author a Playable Mystery

Start with [Lantern at Low Tide](../authoring_examples/lantern_at_low_tide.json). It is a three-location harbor mystery with two characters, three journal clues, and two completion routes.

## Validate bake and play

Run from the authoring checkout in PowerShell.

```powershell
.\play.cmd --author validate authoring_examples/lantern_at_low_tide.json
.\play.cmd --author bake authoring_examples/lantern_at_low_tide.json --output lantern-preview.json
.\play.cmd --pack lantern-preview.json --save lantern-preview.sqlite3
```

Start with `look` and `talk lysa`. Use `--tui` with the play command if you installed Textual in this checkout. The Windows launcher can also reuse the primary Git checkout's TUI dependencies in a linked worktree. Use a fresh output filename for subsequent builds. The compiler validates the whole project before creating a runtime file, and refuses to overwrite a file. Use a fresh save when playtesting changes to the mystery's rules.

For the author-only solution steps, including the shortest route that the engine found:

```powershell
.\play.cmd --author walkthrough authoring_examples/lantern_at_low_tide.json
```

## Edit the author project

| Field | What to supply |
|---|---|
| `brief` | The author's premise, tone, audience, difficulty and private account of what happened. Use it to guide the structured draft. The compiler emits no brief. |
| `id`, `version`, `title` | Keep the pack ID stable for revisions. Use a new version when changing the meaning of saved clues, locations or rules. |
| `locations`, `start`, `gates` | Give rooms stable IDs and list connecting exits. A gate on a directed exit requires a named flag or a discovered clue. |
| `characters` | Give each character a location, opening line, and the clue IDs they reveal when talked to. Voice and a suggested opening question are optional. |
| `clues`, `mandatory_clues` | Write the journal text and supply a source and certainty where possible. Mark clues the player must possess when the mystery ends. Rules still control when each clue is discovered. |
| `flags`, `actions`, `goal` | Use rules to inspect objects, show evidence, open doors and report the answer. Requirements can reference flags and clues. The goal is the flag denoting a successful ending. |
| `items` | Optional inventory entries. An engine rule can give an item once, from its declared source. |
| `puzzles` | The first template is `symbol_sequence`. Give it a location, two to six distinct symbol words, a solution the same length as the symbol list, and a unique solved flag. An authored rule can use that flag to unlock an exit. |
| `playtests` | Supply named lists of commands for the routes you intend players to take. The compiler replays them from a fresh state. Every listed route must finish with all mandatory clues. |

The compiler searches through reachable combinations of locations, clues, flags and items using the game engine. It reports missing references, invalid puzzles, and endings that cannot be reached with the required clues. When a blocked gate could be the cause, the error names the exit and missing prerequisite. The search stops at 25,000 distinct states and reports that it could not finish. A valid pack has a proven route through the current rules. Playtesting still matters for whether the player can understand the clues, find the next action, and enjoy the pacing.


## Add images and choose a puzzle

Install the optional authoring dependency if your Python environment does not already have Pillow.

```powershell
python -m pip install -r requirements-authoring.txt
.\play.cmd --author art authoring_examples/art/low-tide-quay.png --width 40 --height 10
.\play.cmd --author bake authoring_examples/lantern_at_low_tide.json --variant timeline --output lantern-timeline.json
.\play.cmd --tui --pack lantern-timeline.json --save lantern-timeline.sqlite3
```

The sample includes a harbor scene and two portraits. In an author project, each `art` entry has an `id`, a project-relative `source` image and `alt` text. Assign it to one `portrait` (character ID) or one `scene` (location ID). Set `width`, `height`, `mode` (`ascii` or `color`), and optional `contrast` and `crop`. The crop is a four-number rectangle with left, top, right and bottom pixel coordinates. The art preview command accepts `--crop`, `--width`, `--height` and `--contrast` and prints the ASCII version. The TUI displays color art where available. Add `--no-art` to bake a text-only preview without Pillow.

The baked JSON includes a manifest mapping portraits and scenes to embedded terminal art. It contains neither the input pictures nor their paths. Playing a baked pack needs no image processing dependency. Rendered artwork is decorative. Keep instructions and clues in the story, dialogue, and puzzle labels.

Omit `--variant timeline` to bake the symbol lockbox. The timeline uses `cards` with IDs and labels plus a `sequence` containing each card once. A named `puzzle_variants` entry can replace the puzzle, update the location description and witness hint, and override its playtest. Named variants have distinct runtime pack IDs, so use a separate save for each one. Open either puzzle with **F4**, its sidebar action, or `try puzzle`.

## Compare art styles interactively

Open the gallery with the author project path and an art entry ID.

```powershell
.\play.cmd --author preview authoring_examples/lantern_at_low_tide.json lysa_portrait
.\play.cmd --author preview authoring_examples/lantern_at_low_tide.json quay_at_dusk
```

Use the arrow keys or click a style to compare the styles listed below. **View ASCII fallback** shows what the current style looks like in a plain terminal. Click **Use this style** or press **Ctrl+S** to record the choice under the image's `style` field. Press **Esc** to leave the project as it was. A saved `style` takes precedence over the older `mode` setting. Bake again with a new output path to play the updated art.


### Available styles

| Style | What it shows |
|---|---|
| Classic ASCII | Coarse density shading using printable text |
| Fine Shaded ASCII | More density levels for gradients and portraits |
| High Contrast ASCII | Three levels for readable silhouettes |
| ASCII Line Art | Sparse directional outlines |
| Unicode Shades | Monochrome shading with block glyphs |
| Braille Dots | Eight samples per character cell for detailed monochrome |
| ANSI 256 Half Blocks | Two samples per cell using xterm palette indices |
| True Color Half Blocks | Two full RGB samples per cell |
| Color Blocks, Green Phosphor, Amber Phosphor | The original full-cell styles with sampled or tinted palettes |

The gallery renders these styles through the same code the game uses. Terminal fonts determine how well Braille and block glyphs display. The plain prompt and the gallery’s **View ASCII fallback** use the ASCII rows baked with each asset. [Rich terminal colors](https://rich.readthedocs.io/en/stable/style.html) · [Unicode Braille patterns](https://www.unicode.org/charts/PDF/U2800.pdf)

## Review an assisted draft or revision

For a new story, save a brief as a text file or start with the [sample harbor brief](../authoring_examples/lantern_brief.txt). Prepare a prompt, give the prompt to your model, save the returned author project JSON, then import it into a new file.

```powershell
.\play.cmd --author prepare authoring_examples/lantern_brief.txt --draft --request "Draft a short harbor mystery" --output draft-prompt.txt
.\play.cmd --author import-draft draft-from-model.json --output my-mystery.json
```

For revisions, pick the sections the model needs. The prompt includes the project fingerprint and selected fields.

```powershell
.\play.cmd --author prepare my-mystery.json --scope /characters/1 --scope /actions/1 --request "Make the witness warmer after seeing the tide chart" --output revision-prompt.txt
.\play.cmd --author review my-mystery.json proposal.json
.\play.cmd --author apply my-mystery.json proposal.json --only 1
.\play.cmd --author history my-mystery.json
.\play.cmd --author rollback my-mystery.json --to REVISION_HASH
```

Use `--only` with one or more numbered edits when you want a subset. Omit it to use every edit. A proposal must specify `proposal_schema: 1`, the exact `base_sha256` (available from `--author fingerprint`), and an `edits` array. Each edit supplies a JSON Pointer `path`, the exact `before` value, and the new `after` value. For example, replace `/actions/1/message` to adjust Oren's authored reaction after seeing the tide chart. Replacing a section is useful for swapping a puzzle, its witness hint, and the corresponding playtest as one revision.

To protect canon, add `"locks": ["/brief/canon", "/clues/2/text"]` directly to the author project before preparing a proposal. Review and apply both run the compiler on the default pack and every named variant. Applying an edit creates a new pack version and saves a snapshot under the project's private `.author-history` directory. Rollback restores the project JSON from that snapshot. Keep source images available if restoring a revision that uses them. Use a fresh save after baking a new pack version.

The optional cloud command sends the exact prompt file you select. Review that file before running it. Set the provider key through the environment and choose a model with structured outputs. This command saves a proposal for review without changing an author project.

```powershell
.\play.cmd --author suggest revision-prompt.txt --provider openai --model MODEL_ID --output proposal.json
```

Use `--provider claude` and `ANTHROPIC_API_KEY` for Claude, or `OPENAI_API_KEY` for OpenAI. The manual copy and import workflow works with any model that can return the documented JSON.

### Generate proposals locally with Ollama

With Ollama running and a model installed on this PC, send the same prepared prompt to the local provider.

```powershell
.\play.cmd --author suggest revision-prompt.txt --provider ollama --model qwen3:4b-instruct --output local-proposal.json
.\play.cmd --author review my-mystery.json local-proposal.json
```

Ollama authoring uses the local API at `127.0.0.1:11434` and checks that the named model is installed and has no remote provider before sending the prompt. It uses an 8,192-token context by default. Use `--context` to adjust it, or give a smaller model one focused change at a time. For a prepared revision, the tool fills in the fingerprint and original values from the prompt and rejects proposed changes outside the selected sections. A prepared draft prompt works with the same command. Validate the result with `import-draft` for a new project, or `review` and `apply` for a revision. [Ollama chat API](https://docs.ollama.com/api/chat)
