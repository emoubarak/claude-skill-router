#!/usr/bin/env python3
"""PreToolUse hook used only by the bench: log every tool call, allow reading, deny every action.

The replayed prompt runs for real (same model, same skills, same hooks), but nothing can be written, pushed,
posted or opened: Claude only gets to choose skills and read files. Log path: SKILL_BENCH_LOG."""
import json, os, sys

e = json.load(sys.stdin)
tool, inp = e.get("tool_name"), e.get("tool_input") or {}
log = os.environ.get("SKILL_BENCH_LOG")
if log:
    with open(log, "a") as f:
        small = {k: (v[:500] if isinstance(v, str) else v) for k, v in inp.items()} if isinstance(inp, dict) else {}
        f.write(json.dumps({"tool": tool, "input": small}, ensure_ascii=False) + "\n")
if tool in ("Skill", "Read", "Glob", "Grep", "ToolSearch", "TodoWrite"):
    sys.exit(0)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": "Rehearsal mode: no action is executed. Do not "
                                         "retry or work around it: only prepare (skills, reading), then stop in one "
                                         "sentence."}}))
