#!/usr/bin/env python3
"""Replay prompts in the middle of their real session, against a config copy.

    python3 midsession.py <config-dir> mid.jsonl [--n 3] [--out results.jsonl]

mid.jsonl lines: the gold fields of bench.py plus "file" (the original transcript) and "ts" (the timestamp of the
prompt's line in it). The transcript is cut just before that line, copied into <config-dir>/projects with a new
session id, and resumed with `claude -p --resume <id> --fork-session`, so Claude sees everything that came before.
Only tool calls made after the prompt are logged (by guard.py). Large histories cost tokens: keep them under a few MB."""
import argparse, json, os, re, subprocess, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from bench import HERE, score


def cut(item, cfg):
    cwd = item["cwd"] if os.path.isdir(item.get("cwd") or "") else os.path.expanduser("~")
    sid = str(uuid.uuid4())
    d = os.path.join(cfg, "projects", re.sub(r"[^A-Za-z0-9]", "-", cwd))
    os.makedirs(d, exist_ok=True)
    out, target = [], item["prompt"][:80]
    for line in open(item["file"], errors="ignore"):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if not isinstance(j, dict):
            continue
        if j.get("type") == "user" and j.get("timestamp") == item["ts"]:
            c = (j.get("message") or {}).get("content")
            t = c if isinstance(c, str) else " ".join(x.get("text") or "" for x in c or [] if isinstance(x, dict))
            if t.strip()[:80] == target:
                break
        if "sessionId" in j:
            j["sessionId"] = sid
        if "cwd" in j:
            j["cwd"] = cwd
        out.append(json.dumps(j, ensure_ascii=False))
    else:
        return None, None
    with open(os.path.join(d, sid + ".jsonl"), "w") as f:
        f.write("\n".join(out) + "\n")
    return sid, cwd


def run(item, cfg, model, timeout):
    sid, cwd = cut(item, cfg)
    if not sid:
        return dict(item, pred=[], err="prompt not found in transcript", sec=0)
    log = tempfile.mktemp(prefix="skm-", suffix=".jsonl")
    env = dict(os.environ, SKILL_BENCH_LOG=log, CLAUDE_CONFIG_DIR=cfg)
    settings = json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": f"python3 -I '{HERE}/guard.py'"}]}]}})
    cmd = ["claude", "-p", "--resume", sid, "--fork-session", "--no-session-persistence", "--model", model,
           "--max-turns", "10", "--settings", settings, "--output-format", "json", item["prompt"]]
    t0, err = time.time(), None
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        if p.returncode:
            err = (p.stderr or p.stdout)[:200]
    except subprocess.TimeoutExpired:
        err = "timeout"
    pred = set()
    if os.path.exists(log):
        for line in open(log):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d["tool"] == "Skill":
                pred.add(d["input"].get("skill", "").split(":")[-1])
            else:
                pred.update(re.findall(r"skills/([\w-]+)/SKILL\.md", json.dumps(d["input"])))
        os.unlink(log)
    return dict(item, pred=sorted(pred), sec=round(time.time() - t0), err=err)


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("config"); a.add_argument("gold")
    a.add_argument("--n", type=int, default=3); a.add_argument("--model", default="claude-opus-5-5")
    a.add_argument("--timeout", type=int, default=240); a.add_argument("--out")
    x = a.parse_args()
    items = [json.loads(l) for l in open(x.gold)]
    cfg = os.path.abspath(x.config)
    with ThreadPoolExecutor(x.n) as ex:
        rows = list(ex.map(lambda it: run(it, cfg, x.model, x.timeout), items))
    out = x.out or f"{os.path.basename(cfg)}--mid--{os.path.basename(x.gold)}"
    with open(out, "w") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(json.dumps(score(rows), ensure_ascii=False, indent=1))
