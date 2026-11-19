#!/usr/bin/env python3
"""Replay a gold set against a Claude Code configuration and score which skills get loaded.

    python3 bench.py <config-dir> gold.jsonl [--n 4] [--rep 2] [--model claude-opus-5-5] [--out results.jsonl]

<config-dir> is a full copy of ~/.claude (rsync it, add .claude.json for auth), run through CLAUDE_CONFIG_DIR:
your real config, usage counters and session history are never touched. Change one thing per copy (a hook, a
description, a skillOverrides entry) and compare. Each prompt runs in its own cwd (project skills only exist there)
with --no-session-persistence and guard.py, which denies every action.

gold.jsonl lines: {"id", "cwd", "prompt", "gold": [skills that must load], "optional": [fine either way]}."""
import argparse, collections, json, os, re, subprocess, tempfile, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
NEUTRAL = set()  # skills loaded unprompted that cost nothing for you (e.g. a memory skill): never counted as extra


def run(item, cfg, model, timeout):
    log = tempfile.mktemp(prefix="skb-", suffix=".jsonl")
    env = dict(os.environ, SKILL_BENCH_LOG=log, CLAUDE_CONFIG_DIR=cfg)
    settings = json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": f"python3 -I '{HERE}/guard.py'"}]}]}})
    cmd = ["claude", "-p", "--no-session-persistence", "--model", model, "--max-turns", "10",
           "--settings", settings, "--output-format", "json", item["prompt"]]
    cwd = item.get("cwd") if os.path.isdir(item.get("cwd") or "") else os.path.expanduser("~")
    t0, err = time.time(), None
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        try:
            j = json.loads(p.stdout or "{}")
            if j.get("is_error") or p.returncode:
                err = (j.get("result") or p.stderr or "")[:200]
        except ValueError:
            err = (p.stdout or p.stderr)[:200]
    except subprocess.TimeoutExpired:
        err = "timeout"
    skills, reads = [], []
    if os.path.exists(log):
        for line in open(log):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d["tool"] == "Skill":
                skills.append(d["input"].get("skill", "").split(":")[-1])
            else:
                reads += re.findall(r"skills/([\w-]+)/SKILL\.md", json.dumps(d["input"]))
        os.unlink(log)
    return dict(item, pred=sorted(set(skills) | set(reads)), sec=round(time.time() - t0), err=err)


def score(rows):
    num = den = full = pos = neg = neg_ok = extra = 0
    missed, wrong = collections.Counter(), collections.Counter()
    for r in rows:
        G, O, P = set(r["gold"]), set(r.get("optional", [])) | NEUTRAL, set(r["pred"])
        if G:
            pos += 1; den += len(G); num += len(G & P); full += G <= P
            missed.update(G - P)
        else:
            neg += 1; neg_ok += not (P - O)
        extra += len(P - G - O); wrong.update(P - G - O)
    return {"recall": round(num / max(1, den), 3), "all_found": f"{full}/{pos}", "clean_negatives": f"{neg_ok}/{neg}",
            "extra_loads": extra, "missed": missed.most_common(10), "extra": wrong.most_common(10)}


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("config"); a.add_argument("gold")
    a.add_argument("--n", type=int, default=4); a.add_argument("--rep", type=int, default=1)
    a.add_argument("--model", default="claude-opus-5-5"); a.add_argument("--timeout", type=int, default=150)
    a.add_argument("--out")
    x = a.parse_args()
    items = [json.loads(l) for l in open(x.gold)] * x.rep
    with ThreadPoolExecutor(x.n) as ex:
        rows = list(ex.map(lambda it: run(it, os.path.abspath(x.config), x.model, x.timeout), items))
    out = x.out or f"{os.path.basename(os.path.abspath(x.config))}--{os.path.basename(x.gold)}"
    with open(out, "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(json.dumps(score(rows), ensure_ascii=False, indent=1))
