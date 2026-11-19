#!/usr/bin/env python3
"""Weekly review of the router: what it suggested against what Claude actually loaded.

    python3 maintenance/review.py [--days 7] [--gold gold.jsonl]

Three lists, each one a rule fix:
  suggested and loaded       the rule earns its place (rate per skill);
  suggested, never loaded    the pattern is too wide: tighten it;
  loaded, never suggested    words missing from your rules (the prompt is quoted);
plus your own complaints about skills ("use the skill", "you skipped the skill") and, with --gold, the offline score
so a rule edit that hurts shows up. Writes ~/.local/share/skill-router/review-<date>.md and prints its path.
Schedule it (cron, systemd timer, launchd) or run it before you edit the rules."""
import argparse, collections, datetime, glob, json, os, re, subprocess, sys

HOME = os.path.expanduser("~")
LOG = f"{HOME}/.local/share/skill-router/log.jsonl"
OUT = f"{HOME}/.local/share/skill-router"
COMPLAINT = re.compile(r"(use|load|forgot|skipped|why didn'?t you)[^.\n]{0,50}\bskills?\b|\bskills?\b[^.\n]{0,40}"
                       r"(not used|forgot|skipped|wrong)", re.I)


def prompts(path):
    out, cur = [], None
    for line in open(path, errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        c = (d.get("message") or {}).get("content")
        if d.get("type") == "user" and not d.get("isMeta"):
            if isinstance(c, str):
                txt = c
            elif any(isinstance(i, dict) and i.get("type") == "tool_result" for i in c or []):
                continue
            else:
                txt = " ".join(i.get("text") or "" for i in c or [] if isinstance(i, dict) and i.get("type") == "text")
            if txt and not txt.startswith(("<", "Base directory", "[Request interrupted", "This session is being continued")):
                cur = [txt.strip(), set()]
                out.append(cur)
        elif d.get("type") == "assistant" and cur and isinstance(c, list):
            for i in c:
                if isinstance(i, dict) and i.get("type") == "tool_use":
                    inp = i.get("input") or {}
                    if i.get("name") == "Skill":
                        cur[1].add(inp.get("skill", "").split(":")[-1])
                    else:
                        cur[1].update(re.findall(r"skills/([\w-]+)/SKILL\.md", json.dumps(inp)))
    return out


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--days", type=int, default=7); a.add_argument("--gold")
    x = a.parse_args()
    since = (datetime.datetime.now() - datetime.timedelta(days=x.days)).strftime("%Y-%m-%dT%H:%M:%S")
    entries = []
    if os.path.exists(LOG):
        for line in open(LOG):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("ts", "") >= since and (e.get("suggested") or e.get("already")):
                entries.append(e)
    took, ignored, missing, cache = collections.Counter(), collections.Counter(), collections.defaultdict(list), {}
    used = collections.Counter()  # the n-th log entry of a repeated prompt matches its n-th occurrence
    for e in entries:
        m = glob.glob(f"{HOME}/.claude/projects/*/{e.get('sid')}.jsonl")
        if not m:
            continue
        cache.setdefault(m[0], prompts(m[0]))
        key = (m[0], e.get("start", "")[:60])
        hit = [p for p in cache[m[0]] if p[0][:60] == key[1]]
        if len(hit) <= used[key]:
            continue
        loaded, offered = hit[used[key]][1], set(e.get("suggested", [])) | set(e.get("already", []))
        used[key] += 1
        for s in e.get("suggested", []):
            (took if s in loaded else ignored)[s] += 1
        for s in loaded - offered:
            missing[s].append(e.get("start", "")[:80])
    complaints = []
    for p in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"):
        if datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%dT%H:%M:%S") >= since:
            complaints += [t[:200] for t, _ in prompts(p) if COMPLAINT.search(t) and len(t) < 600]
    day = datetime.date.today().isoformat()
    L = [f"# skill-router review, {day}", "", f"{len(entries)} prompts with a suggestion since {since}.", ""]
    if x.gold:
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "..", "bench", "offline.py"), x.gold],
                           capture_output=True, text=True)
        L += [f"Offline score on {x.gold}: {r.stdout.strip()}", ""]
    L += ["## Suggested, then loaded", ""]
    for s in sorted(set(took) | set(ignored), key=lambda s: -(took[s] + ignored[s])):
        L.append(f"- `{s}`: {took[s]}/{took[s] + ignored[s]}")
    L += ["", "## Loaded without a suggestion (words to add)", ""]
    for s, v in sorted(missing.items(), key=lambda i: -len(i[1])):
        quoted = " ; ".join('"' + q + '"' for q in v[:4])
        L.append(f"- `{s}` ({len(v)}): {quoted}")
    L += ["", "## Your complaints about skills", ""] + [f"- \"{c}\"" for c in complaints[:20]]
    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/review-{day}.md"
    open(path, "w").write("\n".join(L) + "\n")
    print(path)


if __name__ == "__main__":
    main()
