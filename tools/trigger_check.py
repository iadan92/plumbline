#!/usr/bin/env python3
"""Measure whether an agent picks the skill for the queries in evals/trigger-evals.json.

Usage: python3 tools/trigger_check.py evals/trigger-evals.json results.json [--split train|test|all] [--runs 2]
                                      [--turns 6] [--workers 6] [--skill plumbline-svg-diagrams]
                                      [--variant SKILL.md --as skill-name | --plugin-dir REPO] [--fixtures DIR] [-v]

Each query runs `claude -p` in an empty temporary directory, with every skill the user has installed
competing, and counts a run as triggered when the agent calls the Skill tool for the target skill within
--turns turns (a Glob or Read first is not a miss). Recall is triggered runs of should_trigger queries,
false triggers are triggered runs of the others. Queries carry a "split" (train or test): tune the
description on train, report on test, so the number is not fitted to the queries it was tuned on.

--plugin-dir measures the skill together with the routing hook in hooks/ (Claude Code plugin form).
--variant measures a candidate SKILL.md without publishing it: the installed copy is moved aside, the
candidate is installed under the name given by --as for the run, and the original is put back at the end
(also if the run is interrupted; `--restore` puts it back after a crash). Do not use Claude Code for other
work while a variant run is in progress. Requires the Claude Code CLI.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

SKILLS = os.path.join(os.path.expanduser("~"), ".claude", "skills")
BACKUP = os.path.join(SKILLS, ".trigger-backup")
FAMILY = ("plumbline", "plumbline-svg-diagrams", "svg-data-diagrams")


def name_of(skill_md):
    m = re.search(r"^name:\s*(\S+)", open(skill_md).read(), re.M)
    return m.group(1) if m else None


def swap_out(target):
    """Move every installed copy of this skill family aside; returns what was moved."""
    os.makedirs(BACKUP, exist_ok=True)
    moved = []
    for entry in sorted(os.listdir(SKILLS)):
        path = os.path.join(SKILLS, entry)
        md = os.path.join(path, "SKILL.md")
        if entry.startswith(".") or not os.path.isfile(md):
            continue
        if name_of(md) in FAMILY + (target,):
            dest = os.path.join(BACKUP, entry)
            if os.path.exists(dest):
                raise SystemExit(f"{dest} already exists: a previous run did not finish. Run with --restore first.")
            shutil.move(path, dest)
            moved.append(entry)
    return moved


def restore():
    if not os.path.isdir(BACKUP):
        return
    for entry in os.listdir(BACKUP):
        dest = os.path.join(SKILLS, entry)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.move(os.path.join(BACKUP, entry), dest)
    os.rmdir(BACKUP)


def run_once(query, skill, turns, workdir, env, plugin_dir=None):
    cmd = ["claude", "-p", query, "--output-format", "stream-json", "--verbose", "--max-turns", str(turns)]
    if plugin_dir:
        cmd += ["--plugin-dir", plugin_dir]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=workdir, env=env)
    except subprocess.TimeoutExpired:
        return None, ["timeout"]
    calls, failed = [], p.returncode not in (0, 1)
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "result" and e.get("is_error"):
            failed = True                       # rate limit, overload or API error: no answer, so not a miss
        if e.get("type") == "assistant":
            for c in e["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls.append(c["name"] + (":" + str(c["input"].get("skill", "")) if c["name"] == "Skill" else ""))
    hit = any(c.startswith("Skill:") and c.endswith(skill) for c in calls)
    if failed and not hit:
        return None, calls + ["error"]
    return hit, calls     # plugin skills are namespaced plugin:skill


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("evals", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--split", choices=["train", "test", "all"], default="all")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--skill", default="plumbline-svg-diagrams")
    ap.add_argument("--variant", help="candidate SKILL.md to measure instead of the installed one")
    ap.add_argument("--as", dest="as_name", help="skill name to install the variant under")
    ap.add_argument("--plugin-dir", help="load this plugin (the repository root) for the run: the skill plus its routing hook. "
                    "The installed copy of the skill is moved aside meanwhile, so the plugin's copy is the only one")
    ap.add_argument("--fixtures", help="folder whose files are copied into the working directory the agent starts in (a dbt manifest, a schema.sql)")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if args.restore:
        restore()
        return 0
    if not args.evals or not args.out:
        ap.error("evals and out are required")
    items = [e for e in json.load(open(args.evals)) if args.split == "all" or e.get("split", "train") == args.split]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    workdir = tempfile.mkdtemp(prefix="trigger-check-")
    if args.fixtures:
        shutil.copytree(args.fixtures, workdir, dirs_exist_ok=True)
    skill = args.as_name or args.skill if args.variant else args.skill
    if args.plugin_dir:
        swap_out(skill)
    if args.variant:
        if not args.as_name:
            ap.error("--variant needs --as")
        swap_out(args.as_name)
        installed = os.path.join(SKILLS, args.as_name)
        os.makedirs(installed)
        shutil.copy(args.variant, os.path.join(installed, "SKILL.md"))
    jobs = [(i, r) for i in range(len(items)) for r in range(args.runs)]
    try:
        with ThreadPoolExecutor(args.workers) as ex:
            results = list(ex.map(lambda j: run_once(items[j[0]]["query"], skill, args.turns, workdir, env, args.plugin_dir), jobs))
    finally:
        if args.variant:
            shutil.rmtree(os.path.join(SKILLS, args.as_name), ignore_errors=True)
        if args.variant or args.plugin_dir:
            restore()
    runs = {}
    for (i, _), (hit, calls) in zip(jobs, results):
        runs.setdefault(i, []).append({"triggered": hit, "calls": calls})
    out = [{**items[i], "runs": rs} for i, rs in sorted(runs.items())]
    json.dump(out, open(args.out, "w"), indent=1)

    def count(should):
        rs = [r for e in out if e["should_trigger"] == should for r in e["runs"] if r["triggered"] is not None]
        return sum(1 for r in rs if r["triggered"]), len(rs)

    hit, n = count(True)
    fp, m = count(False)
    print(f"{args.split}: recall {hit}/{n} = {hit / n:.0%}   false triggers {fp}/{m}" if n else "no queries")
    if args.verbose:
        for e in out:
            for r in e["runs"]:
                if r["triggered"] != e["should_trigger"]:
                    print(("MISS  " if e["should_trigger"] else "FALSE ") + e["query"][:80].replace("\n", " "), "->", r["calls"][:4])
    return 0


if __name__ == "__main__":
    sys.exit(main())
