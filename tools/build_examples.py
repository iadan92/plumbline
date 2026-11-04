#!/usr/bin/env python3
"""Render every example to examples/*.svg and fail on renderer warnings or invalid XML.

Run from the repository root:  python3 tools/build_examples.py [--check] [--gif]
  --check  render into a temporary folder and compare with the committed files instead of overwriting them
           (the unit tests and CI use this: output must be byte for byte reproducible)
  --gif    also rebuild examples/lineage-by-stage-animated.gif (needs Node.js; the GIF depends on installed
           fonts, so it is never part of --check)
Doubles as a smoke test: it exits non-zero if a spec stops rendering cleanly.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "plumbline-svg-diagrams"
SCRIPTS = SKILL / "scripts"
SPECS = SKILL / "assets" / "examples"
OUT = ROOT / "examples"

# (output name, kind, input, extra flags for the kind, renderer flags)
#   render      input is a spec in assets/examples
#   diff        input is "old new" spec names; the comparison is rendered
#   import-dbt  input is a manifest in assets/examples; flags go to import_dbt.py
#   import-ddl  input is a .sql file in assets/examples; flags go to import_ddl.py
JOBS = [
    ("lineage-by-stage", "render", "lineage-by-stage", [], []),
    ("lineage-by-stage-animated", "render", "lineage-by-stage", [], ["--animate", "packets"]),
    ("lineage-by-stage-dark", "render", "lineage-by-stage", [], ["--theme", "dark"]),
    ("lineage-by-stage-print", "render", "lineage-by-stage", [], ["--theme", "print"]),
    ("lineage-brand", "render", "lineage-by-stage", [], ["--theme-file", str(SPECS / "theme-brand.json")]),
    ("lineage-auto", "render", "lineage-auto", [], []),
    ("lineage-auto-pinned", "render", "lineage-auto-pinned", [], []),
    ("lineage-diff", "diff", "lineage-by-stage lineage-by-stage-v2", [], []),
    ("star-schema-lanes", "render", "star-schema", [], []),
    ("star-schema-diff", "diff", "star-schema star-schema-v2", [], []),
    ("star-center", "render", "star-center", [], []),
    ("star-auto", "render", "star-auto", [], []),
    ("star-auto-dark", "render", "star-auto", [], ["--theme", "dark"]),
    ("architecture", "render", "architecture", [], []),
    ("architecture-nested", "render", "architecture-nested", [], []),
    ("architecture-nested-dark", "render", "architecture-nested", [], ["--theme", "dark"]),
    ("sequence-pipeline", "render", "sequence-pipeline", [], []),
    ("sequence-pipeline-dark", "render", "sequence-pipeline", [], ["--theme", "dark"]),
    ("sequence-pipeline-animated", "render", "sequence-pipeline", [], ["--animate", "packets"]),
    ("sequence-phase-headers", "render", "sequence-phase-headers", [], []),
    ("sequence-diff", "diff", "sequence-pipeline sequence-pipeline-v2", [], []),
    ("dbt-import", "import-dbt", "dbt-manifest-sample.json", ["--exclude", "tag:legacy", "--columns", "4", "--title", "Imported from a dbt manifest"], []),
    ("ddl-import", "import-ddl", "billing-schema.sql", ["--title", "Imported from DDL"], []),
]


def run(cmd):
    return subprocess.run([sys.executable, *map(str, cmd)], capture_output=True, text=True)


def build(name, kind, source, extra, flags, out_dir, tmp):
    """Render one job into out_dir; returns a list of problems."""
    out = out_dir / f"{name}.svg"
    spec = tmp / f"{name}.json"
    if kind == "render":
        spec = SPECS / f"{source}.json"
    elif kind == "diff":
        old, new = source.split()
        proc = run([SCRIPTS / "diff_specs.py", SPECS / f"{old}.json", SPECS / f"{new}.json", "-o", spec])
        if proc.returncode:
            return [proc.stderr.strip() or "diff failed"]
    else:
        tool = "import_dbt.py" if kind == "import-dbt" else "import_ddl.py"
        proc = run([SCRIPTS / tool, SPECS / source, "-o", spec, *extra])
        if proc.returncode:
            return [proc.stderr.strip() or "import failed"]
    proc = run([SCRIPTS / "render_diagram.py", spec, out, *flags])
    problems = []
    if proc.returncode != 0:
        problems.append(proc.stderr.strip() or "renderer failed")
    problems += [line for line in proc.stdout.splitlines() if line.startswith("WARNING")]
    if not problems:
        try:
            ET.parse(out)
        except ET.ParseError as exc:
            problems.append(f"invalid XML: {exc}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--gif", action="store_true")
    args = ap.parse_args(argv)
    failed = False
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        out_dir = tmp / "svg" if args.check else OUT
        out_dir.mkdir(exist_ok=True)
        for name, kind, source, extra, flags in JOBS:
            problems = build(name, kind, source, extra, flags, out_dir, tmp)
            if args.check and not problems:
                committed = OUT / f"{name}.svg"
                if not committed.exists():
                    problems.append("no committed file; run build_examples.py")
                elif committed.read_bytes() != (out_dir / f"{name}.svg").read_bytes():
                    problems.append("output differs from the committed file; run build_examples.py and review the change")
            print(f"{'ok  ' if not problems else 'FAIL'} examples/{name}.svg")
            for p in problems:
                print("     ", p)
            failed |= bool(problems)
        if args.gif:
            proc = run([SCRIPTS / "export.py", SPECS / "lineage-by-stage.json", OUT / "lineage-by-stage-animated.gif"])
            print(proc.stdout.strip() or proc.stderr.strip())
            failed |= proc.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
