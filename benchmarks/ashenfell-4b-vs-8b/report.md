# Ashenfell character voice benchmark

The selection timings include draft and review when the reply uses them. The 80 legacy cases are rerun with the current dialogue choices, and 12 new cases cover context and game state.

| Profile | Legacy cases | Current cases | Correct abstentions | Varied / eligible | Median | P95 |
|---|---:|---:|---:|---:|---:|---:|
| qwen-4b | 76/80 | 10/12 | 49/49 | 19/25 | 203 ms | 922 ms |
| qwen-8b | 76/80 | 10/12 | 47/49 | 33/33 | 235 ms | 1094 ms |

## Independent review cases

| Profile | Good drafts accepted | Bad drafts rejected | Review errors |
|---|---:|---:|---:|
| qwen-4b | 4/6 | 5/6 | 3 |
| qwen-8b | 6/6 | 2/6 | 0 |

## Model loading

Peak device memory is sampled system-wide and includes other GPU applications. Ollama residency shows how much of the model allocation was on the GPU.

- **qwen-4b** took 10,500 ms to preload (cold), 100.0% GPU, context 2048, sampled peak 5482 MiB.
- **qwen-8b** took 17,360 ms to preload (cold), 100.0% GPU, context 2048, sampled peak 7671 MiB.

## Playtest findings

Both profiles selected the expected answer in 86 of 92 cases. The 8B profile varied more of the eligible lines, but some of the extra variation changed the facts. It approved a draft that turned Mara's guess into an eyewitness account, as well as a draft that reordered the lockbox symbols. In the end-to-end cases it added tracks and pack animals to Mara's testimony and suggested using strength to open the lockbox. The 4B profile also let some changes through. In two Nessa replies, her expectation that the docket would still be on the wall became a claim that she could see it. Its three standalone review errors were malformed JSON. In live play an invalid review uses the authored fallback.

Keep 4B as the default at this context size. Use the new conversation panel to test follow-ups and evidence discovery. For the next engine change, represent who observed each clue and how certain they are as explicit data. The evidence board can use those fields to link back to the right NPC and question.
