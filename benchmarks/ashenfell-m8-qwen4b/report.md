# Ashenfell held-out release checks

Model qwen3:4b-instruct with 2048 context tokens.

- Correct reply selection **96/108**.
- Correct abstentions **27/27** and false refusals **10**.
- Model wording varied **35** eligible lines. **9** used authored wording.
- Independent review accepted **3** good drafts and let **0** flawed drafts through. Review errors **0**.
- Measured median **234 ms** and P95 **953 ms**.
- Preload **10688 ms**, 100.0% GPU, sampled device peak **5129 MiB**.

## Release gates

- Unauthorized commands rejected with state intact **12/12**.
- Locked-fact phrase matches in reply choices or displayed lines **0**.
- Phrase checks cover the named locked clues and their listed variants. Human assessment of wording, playtime, and a network-disabled Windows Terminal playtest are separate checks.

## Cases to review

- garrick-heard:7 expected `introduce`, got `unsure`.
- garrick-condition:8 expected `topic_help`, got `unsure`.
- mara-still-guessing:6 expected `introduce`, got `unsure`.
- mara-reconsidered:5 expected `recall_mara_retraction`, got `unsure`.
- mara-door-locked:7 expected `topic_locked_door`, got `unsure`.
- mara-door-locked:8 expected `topic_locked_door`, got `unsure`.
- mara-door-locked:9 expected `topic_locked_door`, got `unsure`.
- mara-door-open:1 expected `topic_open_door`, got `unsure`.
- mara-door-open:2 expected `topic_open_door`, got `unsure`.
- mara-door-open:5 expected `topic_open_door`, got `unsure`.
- mara-key:6 expected `topic_cellar_key`, got `topic_lockbox`.
- mara-key:9 expected `topic_cellar_key`, got `topic_lockbox`.

## Review of displayed dialogue

The six standalone reviewer cases passed their expected decisions. A read of the 35 varied lines still found incorrect drafts that made it through the live pipeline. In `mara-reconsidered:2`, Mara added that the storm hit hard and that nobody passed the gate. The source only establishes that the gate was barred during the storm. In `mara-reconsidered:4`, the draft invented a prior belief that the gate might have been open. Keep these examples as reviewer regressions.

Garrick's short fragments generally fit his authored voice. Some accepted replies used the NPC's name in their own speech or omitted the source of a recollection. The variation count measures visible changes to wording and includes those cases. It does not measure character quality or fidelity.

The earlier 4B run measured 203 ms median and 922 ms P95. This run measured 234 ms and 953 ms on different cases and includes newly available evidence actions and follow-ups. Treat the figures as comparisons of observed play behavior. A same-case rerun is needed to isolate any performance change.
