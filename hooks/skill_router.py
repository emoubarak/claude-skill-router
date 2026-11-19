#!/usr/bin/env python3
"""UserPromptSubmit hook: tell Claude which skills fit this prompt, so it loads all of them before acting.

Two signals, both measured (see bench/README.md):
  rules     your own words mapped to skills (regex), filtered by the current directory for project skills,
            each skill named at most once per session;
  reminder  a short line asking Claude to load every skill that applies, not just the first one.
Mode: SKILL_ROUTER_MODE = both (default) | rules | reminder | off.

Rules: ~/.config/skill-router/rules.json, then <repo>/.claude/skill-router.json for every parent of the cwd
(later files add rules). Format: see examples/rules.example.json. Silent when nothing matches, never blocks,
fails open on any error. Every suggestion is logged to ~/.local/share/skill-router/log.jsonl for review.py.
"""
import json, os, re, sys, time

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or f"{HOME}/.claude"
CONFIG = os.environ.get("SKILL_ROUTER_RULES", f"{HOME}/.config/skill-router/rules.json")
STATE = os.environ.get("SKILL_ROUTER_STATE", f"{HOME}/.cache/skill-router/seen")
LOG = os.environ.get("SKILL_ROUTER_LOG", f"{HOME}/.local/share/skill-router/log.jsonl")  # "" = no log
MODE = os.environ.get("SKILL_ROUTER_MODE", "both")
MAX = 5

REMINDER = ("[skills] Before acting, go through your skill list and load with the Skill tool EVERY skill that applies "
            "to this message (often several: content + video + ticket, site + SEO + browser), project skills included. "
            "If none applies, carry on without mentioning it.")


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def config(cwd):
    """Merge the user file and every <parent>/.claude/skill-router.json, outermost first."""
    files = [CONFIG]
    d, chain = os.path.abspath(cwd or "/"), []
    while True:
        chain.append(os.path.join(d, ".claude", "skill-router.json"))
        p = os.path.dirname(d)
        if p == d:
            break
        d = p
    files += reversed(chain)
    merged = {"rules": [], "replaces": [], "always_available": [], "message": None}
    for f in files:
        c = _load(f)
        if not isinstance(c, dict):
            continue
        merged["rules"] += c.get("rules", [])
        merged["replaces"] += c.get("replaces", [])
        merged["always_available"] += c.get("always_available", [])
        if f == CONFIG:  # a cloned repo may add rules, never rewrite the injected text
            merged["message"] = c.get("message") or merged["message"]
    return merged


def available(skill, cwd, always):
    """A skill exists globally, in a parent repo's .claude/skills, or is declared always available (plugins)."""
    if skill in always or os.path.isdir(f"{CLAUDE_DIR}/skills/{skill}"):
        return True
    d = os.path.abspath(cwd or "/")
    while True:
        if os.path.isdir(os.path.join(d, ".claude", "skills", skill)):
            return True
        p = os.path.dirname(d)
        if p == d:
            return False
        d = p


PASTED = re.compile(r"<pasted_content[^>]*>.*?</pasted_content[^>]*>|```.*?```", re.S)


def candidates(prompt, cwd, cfg=None):
    """Every matching skill, rule order, no duplicates. Pasted text and code blocks are ignored: your words count."""
    cfg = cfg or config(cwd)
    text, out = PASTED.sub(" ", prompt)[:4000], []
    for r in cfg["rules"]:
        try:
            if r.get("cwd") and not re.search(r["cwd"], cwd or ""):
                continue
            if re.search(r["pattern"], text, re.I) and available(r["skill"], cwd, cfg["always_available"]):
                if r["skill"] not in [s for s, _ in out]:
                    out.append((r["skill"], r.get("why", "")))
        except (re.error, KeyError, TypeError):
            continue
    names = {s for s, _ in out}
    for rep in cfg["replaces"]:  # {"if": "channel-video", "drop": "video", "unless": "<regex>"}
        try:
            if rep.get("if") in names and rep.get("drop") in names and not (
                    rep.get("unless") and re.search(rep["unless"], text, re.I)):
                out = [x for x in out if x[0] != rep["drop"]]
        except (re.error, TypeError, AttributeError):
            continue
    return out


def context(prompt, cwd, sid):
    if MODE == "off" or len(prompt) < 12 or prompt.startswith(("<", "This session is being continued")):
        return ""
    parts = []
    if MODE in ("rules", "both"):
        cfg = config(cwd)
        cand = candidates(prompt, cwd, cfg)
        seen_file = os.path.join(STATE, re.sub(r"[^\w-]", "", sid or "no-session"))
        try:
            seen = set(open(seen_file).read().split())
        except OSError:
            seen = set()
        new = [(s, w) for s, w in cand if s not in seen][:MAX]
        try:
            if LOG:
                os.makedirs(os.path.dirname(LOG), exist_ok=True)
                with open(LOG, "a") as f:
                    f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": sid, "cwd": cwd,
                                        "suggested": [s for s, _ in new], "already": [s for s, _ in cand if s in seen],
                                        "start": prompt[:160]}, ensure_ascii=False) + "\n")
            if new:
                os.makedirs(STATE, exist_ok=True)
                with open(seen_file, "a") as f:
                    f.write("".join(s + "\n" for s, _ in new))
        except OSError:
            pass
        if new:
            listing = ", ".join(f"{s} ({w})" if w else s for s, w in new)
            parts.append((cfg["message"] or
                          "[skills] Skills that fit this message: {skills}. Before any other action, load them with "
                          "the Skill tool (several calls in the same reply); skip one only if it is clearly off topic. "
                          "Also load any other skill from your list that applies.").replace("{skills}", listing))
    if MODE in ("reminder", "both"):
        parts.append(REMINDER)
    return " ".join(parts)


def main():
    try:
        d = json.load(sys.stdin)
        ctx = context((d.get("prompt") or "").strip(), d.get("cwd") or os.getcwd(), d.get("session_id"))
    except Exception:
        return
    if ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
