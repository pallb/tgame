# Ashenfell dialogue benchmark

80 question and game-state cases. Same options and settings across prompts. Each case starts from a fresh game state, with authored evidence revealed only in recall cases. The benchmark never opens a save.

| Profile | Prompt | Overall | Supported | Local unknown | Unrelated | Gated | Recall | Errors | Median reply |
|---|---|---|---|---|---|---|---|---:|---:|
| qwen-1.7b | original | 42/80 (52.5%) | 30/30 (100.0%) | 0/18 (0.0%) | 8/16 (50.0%) | 0/12 (0.0%) | 4/4 (100.0%) | 0 | 109 ms |
| qwen-1.7b | strict | 35/80 (43.8%) | 30/30 (100.0%) | 0/18 (0.0%) | 3/16 (18.8%) | 0/12 (0.0%) | 2/4 (50.0%) | 0 | 109 ms |
| qwen-4b | original | 73/80 (91.2%) | 29/30 (96.7%) | 15/18 (83.3%) | 15/16 (93.8%) | 10/12 (83.3%) | 4/4 (100.0%) | 0 | 141 ms |
| qwen-4b | strict | 72/80 (90.0%) | 22/30 (73.3%) | 18/18 (100.0%) | 16/16 (100.0%) | 12/12 (100.0%) | 4/4 (100.0%) | 0 | 172 ms |

## Results by NPC

| Profile | Prompt | Garrick | Mara | Nessa | Ivo |
|---|---|---|---|---|---|
| qwen-1.7b | original | 11/20 (55.0%) | 8/20 (40.0%) | 10/20 (50.0%) | 13/20 (65.0%) |
| qwen-1.7b | strict | 9/20 (45.0%) | 8/20 (40.0%) | 7/20 (35.0%) | 11/20 (55.0%) |
| qwen-4b | original | 18/20 (90.0%) | 19/20 (95.0%) | 19/20 (95.0%) | 17/20 (85.0%) |
| qwen-4b | strict | 15/20 (75.0%) | 20/20 (100.0%) | 18/20 (90.0%) | 19/20 (95.0%) |

## Model preload

- qwen-1.7b took 3,016 ms. Ollama may already have had the model loaded.
- qwen-4b took 9,672 ms. Ollama may already have had the model loaded.

## Rephrasing samples

The first rephrasing prompt permitted verbatim fallback. All 32 samples copied the source exactly. The results below replay those same samples with an instruction to use fresh first-person wording.

32 samples, 0 verbatim repeats and 0 request or format errors. Selection results above exclude the rephrasing pass. Review the generated text for factual changes. A valid format alone does not establish fidelity.

Both models changed who sealed the warning in Nessa's recall lines. The source attributes the action to Garrick, while the generated versions have Nessa claim she sealed it herself. The smaller model also had Nessa claim she picked up the lantern that the source says the merchant collected. These rewrites were kept out of live dialogue.

### qwen-1.7b original nessa-recall-1

**Question** Who sealed the merchant's warning?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed the warning myself

### qwen-1.7b original garrick-local_unknown-1

**Question** How many horses did you hear?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-1.7b original nessa-recall-2

**Question** Who was the sealed warning addressed to?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed a warning addressed to the merchant

### qwen-1.7b original garrick-local_unknown-2

**Question** What time did the horses pass?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-1.7b original ivo-recall-1

**Question** What light did you see heading toward the landing?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I saw a light moving downhill toward the landing.

### qwen-1.7b original ivo-recall-2

**Question** Which way did the light move after you checked the log?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** Ivo recalls a light moving downhill toward the landing.

### qwen-1.7b original mara-local_unknown-1

**Question** How deep is the river at this landing?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-1.7b original mara-local_unknown-2

**Question** Who made the lockbox?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-1.7b strict ivo-recall-1

**Question** What light did you see heading toward the landing?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I saw a light moving downhill toward the landing.

### qwen-1.7b strict garrick-local_unknown-1

**Question** How many horses did you hear?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-1.7b strict ivo-recall-2

**Question** Which way did the light move after you checked the log?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** Ivo recalls a light moving downhill toward the landing.

### qwen-1.7b strict garrick-local_unknown-2

**Question** What time did the horses pass?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-1.7b strict mara-answerable-1

**Question** Which road do you think the merchant took?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I think he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-1.7b strict mara-answerable-2

**Question** Do you reckon he headed north?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-1.7b strict nessa-answerable-1

**Question** What did the merchant pick up?

**Authored** Nessa says, 'The merchant picked up a lantern before dusk. The delivery docket should still be on the wall.'

**Generated** I picked up a lantern before dusk. The delivery docket should still be on the wall.

### qwen-1.7b strict nessa-answerable-2

**Question** When did the merchant collect the lantern?

**Authored** Nessa says, 'The merchant picked up a lantern before dusk. The delivery docket should still be on the wall.'

**Generated** I picked up a lantern before dusk. The delivery docket should still be on the wall.

### qwen-4b original nessa-recall-1

**Question** Who sealed the merchant's warning?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed the warning for the merchant.

### qwen-4b original garrick-local_unknown-1

**Question** How many horses did you hear?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-4b original nessa-recall-2

**Question** Who was the sealed warning addressed to?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed a warning for the merchant.

### qwen-4b original mara-unrelated-1

**Question** where are your friends

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-4b original ivo-recall-1

**Question** What light did you see heading toward the landing?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I saw a light moving downhill toward the landing.

### qwen-4b original ivo-recall-2

**Question** Which way did the light move after you checked the log?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I remember the light moving downhill toward the landing when I checked the log.

### qwen-4b original garrick-answerable-1

**Question** What did you hear by the water?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-4b original mara-answerable-1

**Question** Which road do you think the merchant took?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-4b strict nessa-recall-1

**Question** Who sealed the merchant's warning?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed the warning for the merchant.

### qwen-4b strict nessa-recall-2

**Question** Who was the sealed warning addressed to?

**Authored** After seeing the docket, Nessa confirms Garrick sealed a warning addressed to the merchant.

**Generated** I sealed a warning for the merchant.

### qwen-4b strict ivo-recall-1

**Question** What light did you see heading toward the landing?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I saw a light moving downhill toward the landing.

### qwen-4b strict ivo-recall-2

**Question** Which way did the light move after you checked the log?

**Authored** After checking the patrol log, Ivo recalls a light moving downhill toward the landing.

**Generated** I remember the light moving downhill toward the landing when I checked the log.

### qwen-4b strict garrick-answerable-1

**Question** What did you hear by the water?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-4b strict garrick-answerable-2

**Question** Where were the horses you heard?

**Authored** Garrick says, 'I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.'

**Generated** I heard horses near the river. Bring me something to show the merchant trusted me and I'll help.

### qwen-4b strict mara-answerable-1

**Question** Which road do you think the merchant took?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.

### qwen-4b strict mara-answerable-2

**Question** Do you reckon he headed north?

**Authored** Mara says, 'I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.'

**Generated** I reckon he took the north road. The lockbox will open if you follow the old rhyme. Reeds grow first, then the moon rises, then the fish come up to feed.
