# Ashenfell Pack Authoring Plan

Build an authoring tool that turns a story brief into a playable pack, then lets the author revise the mystery, characters, visuals, and difficulty in short playtest rounds. The first implementation should compile one small mystery from structured inputs and run it offline in the existing game. Add model-assisted drafting once the compiler can validate and play that pack.

## Author workflow

1. **Supply the brief.** Ask for a premise, intended audience and tone, beginning and ending, locations, and character sketches. A mystery also needs an author-only account of what happened, what proves it, and what each character believes. Accept optional pictures with the portrait or scene they belong to. Let the author choose a short or standard play length and how much deduction and puzzle solving they want.
2. **Review the outline.** Sketch the opening, the evidence needed to reach the ending, possible routes, and a budget for locations, NPCs, clues, and puzzles. Surface contradictions and unanswered design choices as questions. For example, ask whether a witness is guessing or lying, because that decision changes the evidence, dialogue, and permitted reveals.
3. **Generate the first draft.** Create locations and exits, character sheets, evidence with sources and certainty, reveal conditions, fallback dialogue, puzzle instances, and art placeholders or converted pictures. Produce an author-only solution walkthrough alongside the playable preview.
4. **Play and revise in rounds.** First check mystery logic and pacing. Then tune how each NPC sounds and reacts. Finally review portraits, location styles, puzzle hints, and readability. Allow specific requests such as “Make the warden colder until shown the ledger” or “Replace the lock with a timeline puzzle.” Show proposed changes against the last accepted version. The author can accept individual edits and lock established facts or assets before requesting another pass.
5. **Bake the release pack.** Compile accepted changes, run checks, and export a versioned folder that the game can load directly. Keep the original brief, source images, private solution notes, review history, and any provider credentials in the authoring workspace. Include runtime conditions and only the clues, assets, and dialogue the engine needs to play.

## Authoring and runtime formats

Keep three separate representations. Use a human-readable author project for the brief, canon, decisions, and original pictures. Use a typed draft format with stable IDs and reviewable proposed changes. Compile that draft into the existing game format with a manifest for relative asset paths. Begin by emitting JSON accepted by `Pack.load`. Add a pack directory entry point when the TUI can render assets, while retaining support for existing standalone JSON packs and saves.

Distinguish **world truth**, **character belief**, **player-visible evidence**, and **reveal conditions** in the author project. An NPC profile should record goals, vocabulary, cadence, and how the NPC responds to topics or events such as being challenged or shown proof. Bind reactions to conditions the engine can check. For the first slice, use a handful of authored states such as guarded, cooperative, or challenged. Provide an authored response for each progression-critical exchange. Models can help propose the wording and variants, while the compiler and engine determine when the player sees them.

## Visuals and puzzles

- **Portraits.** Let each NPC reference an optional portrait with a text label. Start with a local image converter that crops and scales a supplied picture, corrects for terminal cell proportions, and previews monochrome ASCII and color Unicode variants. The author can adjust crop, contrast, palette, and output size. Ship the chosen terminal asset and an ASCII fallback where needed.
- **Locations.** Give each location a reusable theme with a limited palette, a small scene or decoration, and contextual symbols. Preview at compact and standard terminal sizes. Use safe text and palette data for styles. Missing art falls back to the normal text view.
- **Puzzles.** Start with a catalog of typed templates. Generalize Ashenfell's symbol sequence first. Then add a timeline ordering puzzle and an evidence matching puzzle. Each instance supplies its prompt, pieces, solution, hints, and engine effects. The author chooses which templates fit the story and can substitute one in a revision. Difficulty settings control clue density, step count, hint timing, and optional routes. Check every puzzle's solution and access conditions against the chosen settings.

## Model assistance

Start with manual entry and an importer for structured drafts. An author can use ChatGPT or Claude to draft an outline or work through character revisions in conversation, then import a proposal. For repeated use, add optional OpenAI or Claude API adapters that return the same provider-neutral draft or patch format. Structured outputs help parse the proposals. The compiler still checks references, reveal conditions, and whether the ending can be reached. Models propose changes to the draft and the author chooses what becomes canon. [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) · [Claude structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)

Choose a provider per authoring task. Send only the needed brief, scene, or NPC sheet when the author opts in, and let them review which pictures would be sent. Local image conversion and compiling should work without cloud access. The baked pack runs offline using authored dialogue and the existing optional local-model path.

## Milestones

| Milestone | Deliverable | Acceptance check |
|---|---|---|
| **A1 Compiler and preview** | Author project format, validate and bake commands, and one original micro-mystery as a fixture. | A brief for three locations, two NPCs, several clues, and one puzzle can be structured and baked into a playable pack. The existing engine loads it and completes the mystery offline. Diagnostics identify invalid references, unreachable mandatory clues, circular gates, and incompatible puzzle settings. |
| **A2 Assets and puzzle catalog** | Portrait and scene converter, pack asset manifest, terminal previews, and two selectable puzzle templates. | The author can convert one supplied image, assign it to a character or location, choose a template, and finish the same mystery with either puzzle choice. Visuals remain legible in a compact terminal and have text fallbacks. |
| **A3 Assisted draft and revision** | Structured proposal import, optional provider adapter, field-level diffs, and accepted revisions. | Starting from the same brief, draft a pack and complete two author edits. Change an NPC's reaction to evidence and swap a puzzle. A locked fact stays intact, and the author can return to the previous playable build. |
| **A4 Release and playtest** | Versioned export, author walkthrough, and validation report with scripted solution routes. | The exported folder runs offline in a clean checkout. Both intended solution routes work, optional clues stay optional, and NPCs cannot disclose gated evidence early. |

For the first build, prioritize the compiler and a second playable pack over a dedicated authoring UI. That tests whether the engine can support a different story and exposes which edits need a wizard or a visual preview.
