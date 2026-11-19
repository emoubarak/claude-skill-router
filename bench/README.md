# The bench

How the numbers in the main README were produced, so you can reproduce them on your own setup.

## 1. A gold set from your own prompts

`extract.py` pulled 4,370 prompts from 75 days of my Claude Code transcripts on one machine. Prompts that only make
sense with the conversation before them ("go", "and that one?") were dropped. Four labelling passes, one per quarter
of the 924 remaining candidates, proposed for each prompt the skills that would change how it should be handled
(0 to 4, several allowed), plus "optional" skills that are fine either way. A second pass reread the positives of
every set and the negatives of the dev set, fixed the wrong labels and dropped prompts that need prior context. Two
rules mattered:

- **Gold means "changes the outcome", not "a keyword matched".** Reading a PDF needs no skill (Claude reads PDFs
  natively); editing a .docx does.
- **About a third of the set needs no skill at all.** A router that fires on everything would look great on
  recall and cost context on every turn.

Three disjoint sets: **dev** (77 positives, 39 negatives) to tune on, **test** (77 and 40) untouched until the
variant was frozen, **fresh** (80 and 30) drawn after a last round of fixes made from the test misses, to check those
fixes generalise.

## 2. Replay against the real harness

`bench.py` runs each prompt with `claude -p --no-session-persistence` in its original working directory (project
skills only exist there), with the same model I use (Opus 5.5) and the same skills, hooks and settings, through
`CLAUDE_CONFIG_DIR` pointing at a copy of `~/.claude`. A `PreToolUse` guard (`guard.py`) logs every call and denies
everything except Skill, Read, Glob, Grep, ToolSearch and TodoWrite: the prompt that says "open a ticket and push" cannot open a ticket or
push. A skill counts as loaded if Claude called the Skill tool or read its `SKILL.md`.

Why a copy of the config: every Skill call bumps a usage counter in `.claude.json`, and Claude Code uses that counter
to decide which descriptions to drop when the listing is over budget. Benchmarking on your live config would change
the thing you measure.

## 3. One change per copy

| Variant (dev set, 1 pass) | Recall | All needed skills |
|---|---|---|
| nothing | 66 % | 45/77 |
| rules, soft wording ("load each that really applies") | 84 % | 60/77 |
| reminder only | 84 % | 60/77 |
| rules + reminder | 89 % | 65/77 |
| rules v2, firm wording ("load them before any other action") | 94 % | 71/77 |
| rules v2 + reminder | 93 % | 70/77 |
| rules v2 + reminder + 17 skills hidden with `skillOverrides: name-only` | 95 % | 72/77, but 28/39 clean negatives |
| rules v2 + reminder + 4 descriptions fixed | 96 % | 73/77 |

The wording of the injected line moved recall more than any rule: "load each one that really applies" let Claude
talk itself out of half the suggestions.

The last variant on the held-out **test** set, 2 passes each, against the untouched setup:

| | Pass 1 | Pass 2 |
|---|---|---|
| without, recall | 59.6 % | 54.5 % |
| with, recall | 83.8 % | 84.8 % |
| without, all needed skills | 42/77 | 38/77 |
| with, all needed skills | 63/77 | 64/77 |
| without, clean negatives | 40/40 | 39/40 |
| with, clean negatives | 38/40 | 38/40 |

On the **fresh** set (80 positives, 30 negatives, drawn after a last round of rule fixes), one pass each: recall
74.1 % to 90.6 %, every needed skill in 59/80 to 72/80 requests, clean negatives 28/30 to 27/30.

The final version (after an independent review fixed the 5-skill cut, duplicates and pasted text), one pass on the
fresh set: recall 92.9 %, every needed skill in 74/80, clean negatives 24/30 (most "extra" loads were the tool's own
project skill while working inside that tool's repo).

**Mid-session** (`midsession.py`): the real transcript is cut just before the prompt,
copied into the isolated config and resumed with `claude -p --resume <id> --fork-session`. 28 prompts (23 needing
skills): recall 43 % to 80 %, every needed skill in 8/23 to 18/23, clean negatives 5/5 to 4/5. Skills already
loaded earlier in the session count as misses on both sides.

The hook itself: median 21 ms and about 150 tokens of added context per prompt, measured over the test set.

## Cost

Every replay is a real `claude -p` run on your plan. My full study, about 2,000 runs on Opus with several variants in
parallel, used up the rest of my plan's weekly usage on the last day. The scripts now cap a launch at 120 runs
(`--max-runs`) and stop starting new runs at the first usage-limit error. Tune on a small dev set, run the held-out
set once per finalist, and keep parallelism low.

## Caveats

- One user, one language (French), one model. Your gain depends on how far your phrasing is from your descriptions.
- The replay stops when Claude would act, so a skill Claude loads later in a real session (the ticket skill after
  the bug is found) counts as a miss. Real-world recall is somewhat higher on both sides.
- Labels were proposed by labelling agents and reviewed in a second pass; some are judgement calls. The optional list absorbs most of them.
- "Extra" loads (a skill loaded that the label did not ask for) roughly doubled. Most were defensible (the design
  skill on an "ugly interface" prompt); each costs a few thousand tokens of context.
