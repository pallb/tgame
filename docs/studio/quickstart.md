# From a story brief to a playable mystery

You can start with one or two paragraphs in a plain-text file. Studio uses the brief to prepare a prompt for a model, then validates and imports the draft JSON the model returns. You can call a configured model from Studio or use a model separately and bring back the response.

## 1. Write the brief

Start with the player's situation. Give them a place, a problem they can investigate, and a reason to act. Then write the private answer in plain language so the model knows which facts the clues should support.

- **Opening and tone.** Where does the player start? What just happened? Is this cozy, tense, funny, or eerie?
- **People and places.** Name one or two people the player can talk to and a few places they can search. Give each person one thing they know, saw, or got wrong.
- **What really happened.** Say who did what and why. Include an innocent explanation for any misleading clue you want to use.
- **Clues and ending.** Name two or three pieces of evidence, where to find them, and what the player must do to finish. If you want a puzzle or a second route, describe what it unlocks.

You can save the following example as `clocktower-brief.txt` and use it as written.

> The clocktower stopped just before the town's evening bell. The player starts in the square, where Mina, a bakery apprentice, says she heard the gears turning after the clock face had stopped. The player can interview the caretaker in the workshop and inspect the clock mechanism upstairs. Keep the tone curious and slightly eerie.
>
> The caretaker stopped the clock deliberately after a loose counterweight nearly fell. A repair note in the workshop records the fault, and a fresh scrape on the mechanism shows where it caught. Finish when the player brings both clues to Mina and reports why the bell never rang. Keep the story to three locations and one short route.

## 2. Prepare and generate a draft

1. Run `.\play.cmd --studio` from the checkout. Under **Projects**, choose **Prepare draft prompt**.
2. Browse to your brief file. In **Draft request**, add a short instruction such as “Make a beginner-friendly mystery with three locations and one complete playtest route.” Save the prompt as a new file such as `clocktower-prompt.txt`.
3. In **Revisions**, select **Generate with model** and browse to that prompt. Choose a provider, enter the model ID, and pick a new JSON file for the response, such as `clocktower-draft.json`. Use **Review prompt** to inspect what will be sent, then use **Send prompt** to generate the draft.

For local generation, run Ollama and select an installed local model using its exact name. Cloud generation uses `OPENAI_API_KEY` for OpenAI or `ANTHROPIC_API_KEY` for Claude, set in the environment before launching Studio. If you prefer to use a model separately, give it the prepared prompt and save its returned JSON object as a plain `.json` file.

## 3. Import, test, and revise

1. In **Projects**, choose **Import draft**. Select the model's JSON and choose a separate author project filename such as `clocktower-project.json`. Studio validates the draft before creating and opening the project.
2. If import fails, read the diagnostic and fix the draft JSON or ask the model to correct it using that message. Check that every clue and location referenced by a rule exists, that mandatory clues can actually be found, and that each authored route ends with the required evidence.
3. Press **F5** to play the project from a fresh save. Try following the writing as a first-time player. If you get stuck, quit with **Ctrl+Q** and open **Playtest → Show walkthrough**. Compare the intended next action with what the player is told in the room or conversation.
4. Use **Design** to revise any misleading line or clue. Save with **Ctrl+S**, run **Validate all variants**, and press **F5** again.
5. When the mystery is ready, use **Playtest → Export runtime pack** and choose a new filename, such as `clocktower-pack.json`. Run the following command to play the export outside Studio.

   ```powershell
   .\play.cmd --tui --pack "clocktower-pack.json" --save "clocktower.sqlite3"
   ```

See the [Studio README](README.md) for the rest of the controls, including revision proposals, history, and the art gallery.
