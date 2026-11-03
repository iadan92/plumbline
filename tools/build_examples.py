#!/usr/bin/env python3
"""Render every example spec to examples/*.svg and fail on renderer warnings or invalid XML.

Run from the repository root:  python3 tools/build_examples.py
Doubles as a smoke test: it exits non-zero if a spec stops rendering cleanly.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "plumbline"
SPECS = SKILL / "assets" / "examples"
OUT = ROOT / "examples"

# output name, spec, extra renderer flags
JOBS = [
    ("lineage-by-stage", "lineage-by-stage", []),
    ("lineage-by-stage-animated", "lineage-by-stage", ["--animate", "packets"]),
    ("lineage-by-stage-dark", "lineage-by-stage", ["--theme", "dark"]),
    ("star-schema-lanes", "star-schema", []),
    ("star-center", "star-center", []),
    ("star-auto", "star-auto", []),
    ("star-auto-dark", "star-auto", ["--theme", "dark"]),
    ("architecture", "architecture", []),
    ("architecture-nested", "architecture-nested", []),
    ("architecture-nested-dark", "architecture-nested", ["--theme", "dark"]),
    ("sequence-pipeline", "sequence-pipeline", []),
    ("sequence-pipeline-dark", "sequence-pipeline", ["--theme", "dark"]),
    ("sequence-pipeline-animated", "sequence-pipeline", ["--animate", "packets"]),
    ("sequence-phase-headers", "sequence-phase-headers", []),
]


def main():
    OUT.mkdir(exist_ok=True)
    failed = False
    for name, spec, flags in JOBS:
        out = OUT / f"{name}.svg"
        proc = subprocess.run(
            [sys.executable, str(SKILL / "scripts" / "render_diagram.py"), str(SPECS / f"{spec}.json"), str(out), *flags],
            capture_output=True, text=True)
        problems = []
        if proc.returncode != 0:
            problems.append(proc.stderr.strip() or "renderer failed")
        problems += [line for line in proc.stdout.splitlines() if line.startswith("WARNING")]
        if not problems:
            try:
                ET.parse(out)
            except ET.ParseError as exc:
                problems.append(f"invalid XML: {exc}")
        status = "ok  " if not problems else "FAIL"
        print(f"{status} {out.relative_to(ROOT)}")
        for p in problems:
            print("     ", p)
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
