# skill-router

**Claude Code loads the skills that fit a prompt, all of them, and you can measure it on your own sessions.**

With a handful of skills, Claude picks the right one. With a hundred, it does not: on my own prompts, replayed
against my real setup, Claude loaded only **57 %** of the skills a request needed, and every needed skill in only
**half** of the requests. Descriptions alone are not enough. "Check the Search Console alerts for the agency site"
loaded the browser skill and skipped the SEO skill, whose description contains that exact phrase.

skill-router is a `UserPromptSubmit` hook plus the bench that proved it works:

| Held-out prompts (77 needing skills, 40 needing none, 2 passes) | Without | With skill-router |
|---|---|---|
| Needed skills loaded (recall) | 57 % | **84 %** |
| Requests where every needed skill loaded | 52 % | **82 %** |
| Prompts needing no skill left clean | 99 % | 95 % |

A third set drawn after the last fixes, never used for tuning, gave the same picture: recall 74 % to **93 %**, every
needed skill in 59/80 to **74/80** requests (final version, after an independent code review). Replayed **in the
middle of real sessions** (the transcript cut just before the prompt, then `--resume`), 28 prompts: recall 43 % to
**80 %**, every needed skill in 8/23 to **18/23**.

Measured with Claude Opus 5.5 in Claude Code 2.1.328, 80 to 95 skills per session depending on the repo (global,
project and plugin), real prompts from 75 days of work. Labels were proposed by four labelling agents and reviewed in
a second pass. Details and caveats: [bench/README.md](bench/README.md).

## How it works

On each prompt the hook adds one or two lines to Claude's context:

1. **Rules in your words.** A regex per skill, written from how *you* ask for things ("the notifs of the search
   console", "make it a skill", "post it on X"), filtered by the current directory for project skills, each skill
   named once per session. Claude still decides: the line says "load these before acting, skip one only if it is
   clearly off topic".
2. **A reminder** that a request often needs several skills (content + video + ticket), so Claude does not stop at
   the first match.

Each half alone gave the same gain on the dev set (66 % to 84 % recall), together 89 %, and 93 % once the injected
line said "before any other action" instead of "each one that really applies". Fixing four descriptions took it to
96 %. The held-out numbers above are the honest ones.

It costs about 150 tokens per prompt (median, measured) and about 20 ms. No model call, no server, no dependency.

## Install

```
/plugin marketplace add emoubarak/claude-skill-router
/plugin install skill-router@skill-router
```

Then write your rules in `~/.config/skill-router/rules.json` (start from
[examples/rules.example.json](examples/rules.example.json)); a repo can add its own in `.claude/skill-router.json`.

```json
{
  "rules": [
    {"skill": "seo", "pattern": "\\bseo\\b|search console|semrush|backlinks?", "why": "SEO"},
    {"skill": "invoices", "pattern": "invoices?|receipts?", "cwd": "/accounting\\b", "why": "bookkeeping repo only"}
  ],
  "replaces": [{"if": "channel-video", "drop": "video"}],
  "always_available": ["recall"]
}
```

Modes (`SKILL_ROUTER_MODE`): `both` (default), `rules`, `reminder`, `off`.

Skills from plugins or built into Claude Code have no folder to check: list them in `always_available`, or their
rules never fire. Project skills are suggested only inside their repo (the hook looks for
`<parent>/.claude/skills/<name>`). A repo's `.claude/skill-router.json` can add rules but cannot change the injected
text.

**Privacy.** The hook logs, per prompt, the suggested skills and the first 160 characters of the prompt to
`~/.local/share/skill-router/log.jsonl`, for `review.py`. Nothing leaves your machine. `SKILL_ROUTER_LOG=""` turns it off.

## Write the rules from your history, not from your skills

The useful words are the ones you type, not the ones in the descriptions. `bench/extract.py` pulls every prompt from
your transcripts with the skills Claude loaded after it: read the misses and copy your phrasing into the patterns.
`bench/offline.py gold.jsonl` scores the rules alone in a second.

## Measure it on your own setup

`bench/bench.py` replays a labelled set of your prompts through `claude -p` against a **copy** of `~/.claude`
(`CLAUDE_CONFIG_DIR`), in each prompt's original directory, with a guard hook that lets Claude choose skills and read
files but denies every action. Your real config, usage counters and history are untouched. Change one thing per copy
(a hook, a description, a `skillOverrides` entry) and compare. The method, and what I learned from about 1,600 replays, is in
[bench/README.md](bench/README.md).

## Keep it honest

Rules rot: you start a new project, you phrase things differently. `maintenance/review.py` reads the log the hook
writes and your transcripts, and lists per skill: suggested then loaded, suggested and ignored (pattern too wide),
loaded without a suggestion (words missing, with your prompt quoted), plus your own complaints ("you skipped the
skill"). Run it weekly; with `--gold` it also re-scores the rules so an edit that hurts shows up.

## What did not help

- **Hiding skills** (`skillOverrides: name-only` on 17 overlapping third-party skills): same recall, more noise on
  prompts that need no skill.
- **Renaming skills**: names were already explicit; with the router you no longer need to remember them.
- **The listing budget** was not the cause on my setup once raised (`skillListingBudgetFraction: 0.02`), but check
  yours: `claude --debug` logs "Skill listing over budget" when descriptions get dropped, and a dropped description
  is a skill Claude will almost never pick.

Also found on the way: a `description:` spanning several lines with a `: ` inside is not valid YAML, and Claude Code
silently falls back to the skill's title. Quote it or use `>-`.

## License

MIT
