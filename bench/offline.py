#!/usr/bin/env python3
"""Score the rules alone against a gold set, in a second and for free (no model call).

    python3 offline.py gold.jsonl [--rules rules.json] [-v]

Use it after every rule edit: recall should not drop. The bench (bench.py) is the real test, since Claude still
decides whether to follow a suggestion."""
import argparse, importlib.util, json, os

a = argparse.ArgumentParser()
a.add_argument("gold"); a.add_argument("--rules"); a.add_argument("-v", action="store_true")
x = a.parse_args()
if x.rules:
    os.environ["SKILL_ROUTER_RULES"] = os.path.abspath(x.rules)
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "skill_router.py"))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
tp = fn = fp = 0
for it in map(json.loads, open(x.gold)):
    P = {s for s, _ in r.candidates(it["prompt"], it.get("cwd") or "")}
    G, O = set(it["gold"]), set(it.get("optional", []))
    tp += len(G & P); fn += len(G - P); fp += len(P - G - O)
    if x.v and (G - P or P - G - O):
        print("missed", sorted(G - P), "extra", sorted(P - G - O), "|", it["prompt"][:100])
print(f"recall {tp / max(1, tp + fn):.2f}  precision {tp / max(1, tp + fp):.2f}")
