#!/usr/bin/env python3
"""Pull your real prompts out of Claude Code transcripts, with the skills Claude loaded after each one.

    python3 extract.py out.json [--days 75]

A prompt is a message you typed (not a tool result, a skill body or a compaction summary). "Loaded" means a Skill
tool call, or a Read of some skills/<name>/SKILL.md, before your next message. That is what Claude did, not what it
should have done: label the gold set yourself (see README)."""
import argparse, glob, json, os, re, time

a = argparse.ArgumentParser()
a.add_argument("out")
a.add_argument("--days", type=int, default=75)
x = a.parse_args()
cut = time.time() - x.days * 86400
rows = []
for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
    if os.path.getmtime(f) < cut:
        continue
    cur = None
    for line in open(f, errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        c = (d.get("message") or {}).get("content")
        if d.get("type") == "user" and not d.get("isMeta") and not d.get("isCompactSummary"):
            if isinstance(c, str):
                txt = c
            elif any(isinstance(i, dict) and i.get("type") == "tool_result" for i in c or []):
                continue
            else:
                txt = " ".join(i.get("text", "") for i in c or [] if isinstance(i, dict) and i.get("type") == "text")
            txt = txt.strip()
            if not txt or txt.startswith(("<", "Base directory", "[Request interrupted", "This session is being continued")):
                continue
            cur = {"file": f, "cwd": d.get("cwd"), "ts": d.get("timestamp"), "prompt": txt[:3000], "loaded": []}
            rows.append(cur)
        elif d.get("type") == "assistant" and cur and isinstance(c, list):
            for i in c:
                if isinstance(i, dict) and i.get("type") == "tool_use":
                    inp = i.get("input") or {}
                    if i.get("name") == "Skill":
                        cur["loaded"].append(inp.get("skill", "").split(":")[-1])
                    else:
                        cur["loaded"] += re.findall(r"skills/([\w-]+)/SKILL\.md", json.dumps(inp))
json.dump(rows, open(x.out, "w"), ensure_ascii=False)
print(len(rows), "prompts")
