# Mystery Studio

Mystery Studio is a terminal workspace for writing, playtesting, revising, and exporting playable mystery packs. To start with an idea, follow the [quick guide from story brief to playable pack](quickstart.md).

## Open Studio

Run these commands from the repository checkout in PowerShell. Install the Textual dependencies once in the Python environment used by the launcher.

```powershell
python -m pip install -r requirements-tui.txt
.\play.cmd --studio
```

This opens the example directly.

```powershell
.\play.cmd --studio authoring_examples/lantern_at_low_tide.json
```

Install `requirements-authoring.txt` to use art or build projects with images. **Text-only build** on the Playtest tab lets you validate, preview, and export without the images.

## What each tab does

| Tab | Controls |
| --- | --- |
| **Projects** | **Open project** browses for an author project. **New from template** creates a playable copy of the sample without its images. **Prepare draft prompt** turns a text brief into a prompt, and **Import draft** validates a model's JSON response and saves it as a new author project. |
| **Design** | Choose a section such as **Locations**, **Characters**, **Clues**, or **Playtests** and edit its JSON. **Save revision** or **Ctrl+S** validates the default puzzle and all variants, then records a version in history. **Discard edits** clears unsaved changes. **Open art gallery** compares styles for an existing art asset. |
| **Playtest** | Choose a puzzle variant and launch **Fresh preview** with **F5**. Quit the game with **Ctrl+Q** to return to Studio. **Resume last preview** reopens the last build and save for the selected variant and art setting during the current Studio session. **Validate all variants** checks reachability and replays authored routes. **Show walkthrough** displays the shortest successful route and the authored routes for the selected variant. **Export runtime pack** writes a game JSON for that variant. |
| **Revisions** | **Prepare prompt** packages a scoped change request. **Generate with model** displays the prompt for confirmation and saves the model's JSON response. **Review proposal** validates the edits and shows a diff. Leave edit numbers blank to review all edits, or enter specific numbers to review a subset. **Apply reviewed edits** saves the reviewed changes as a revision. **Show history** lists saved snapshots, and **Restore snapshot** takes a full hash or a unique prefix of at least eight characters. |

**Browse** is available for input files and output paths. Click an entry or use the arrow keys and **Enter**. **Backspace** goes up a folder, and **Esc** closes the picker. When saving a new file, pick the destination folder and enter the filename.

## Revise and share a game

For a model-assisted revision, use **Prepare prompt** and supply JSON pointers such as `/characters/0 /actions/1` to limit its scope. Describe what should change and which clues or facts should stay consistent. Review the diff before applying it. You can list protected JSON pointers in the project's **Locks** section.

Keep the author project JSON for future editing. Share the exported runtime JSON with players. The following command plays it from the repository checkout with a dedicated save file.

```powershell
.\play.cmd --tui --pack "my-mystery-pack.json" --save "my-mystery.sqlite3"
```

Use a fresh save when playtesting changes to clues, locations, or rules. See the [pack authoring reference and CLI examples](../pack-authoring-quickstart.md) for schema fields, art styles, and model setup.
