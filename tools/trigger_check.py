"""Measure whether the installed skill triggers.

Usage: python3 tools/trigger_check.py evals/trigger-evals.json results.json

Runs each query with `claude -p --max-turns 1` in an empty temporary directory and checks whether the first
action is a Skill call for plumbline. The skill must be installed (project or user level). One run per
query is noisy, so read the result as a rough rate, not a score. Requires the Claude Code CLI.
"""
import json, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

evals = json.load(open(sys.argv[1]))
out = sys.argv[2]
env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
WORKDIR = tempfile.mkdtemp(prefix="trigger-check-")


def run(item):
    try:
        p = subprocess.run(["claude", "-p", item["query"], "--output-format", "stream-json", "--verbose", "--max-turns", "1"],
                           capture_output=True, text=True, timeout=240, cwd=WORKDIR, env=env)
    except subprocess.TimeoutExpired:
        return {**item, "triggered": None, "calls": ["timeout"]}
    calls = []
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls.append(c["name"] + (":" + str(c["input"].get("skill", "")) if c["name"] == "Skill" else ""))
    return {**item, "triggered": any(c == "Skill:plumbline" for c in calls), "calls": calls}


with ThreadPoolExecutor(5) as ex:
    res = list(ex.map(run, evals))
json.dump(res, open(out, "w"), indent=1)
tp = sum(1 for r in res if r["should_trigger"] and r["triggered"])
fn = sum(1 for r in res if r["should_trigger"] and r["triggered"] is False)
fp = sum(1 for r in res if not r["should_trigger"] and r["triggered"])
tn = sum(1 for r in res if not r["should_trigger"] and r["triggered"] is False)
print(f"recall {tp}/{tp + fn}  false triggers {fp}/{fp + tn}  unknown {sum(1 for r in res if r['triggered'] is None)}")
