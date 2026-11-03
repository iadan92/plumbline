#!/usr/bin/env python3
"""Rasterize an SVG into overlapping square-ish PNG slices so each part can be inspected.

Usage: preview_slices.py diagram.svg outdir [slice_width]

Why: macOS Quick Look (qlmanage) renders a square thumbnail that crops wide or tall
SVGs, so a single call hides most of the diagram. Slicing via viewBox shows all of it.
Requires macOS (qlmanage). On other systems, open the SVG in a browser instead.
"""
import os
import re
import shutil
import subprocess
import sys


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    sw = int(sys.argv[3]) if len(sys.argv) > 3 else 900
    if not shutil.which("qlmanage"):
        raise SystemExit("qlmanage not found (macOS only). Open the SVG in a browser to inspect it.")
    os.makedirs(outdir, exist_ok=True)
    text = open(src).read()
    m = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', text)
    w, h = float(m.group(1)), float(m.group(2))
    step = sw - 80  # overlap so lines crossing a cut are visible on both sides
    x, i, made = 0.0, 0, []
    while x < w:
        vw = min(sw, w - x) if w - x > 40 else sw
        sl = re.sub(r'viewBox="[^"]*"', f'viewBox="{x:g} 0 {sw} {max(h, 1):g}"', text, count=1)
        sl = re.sub(r'(<svg[^>]*?) width="[0-9.]+" height="[0-9.]+"', rf'\1 width="{sw}" height="{h:g}"', sl, count=1)
        path = os.path.join(outdir, f"slice-{i}.svg")
        open(path, "w").write(sl)
        subprocess.run(["qlmanage", "-t", "-s", str(max(sw, int(h))), "-o", outdir, path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        made.append(path + ".png")
        x += step
        i += 1
    for p in made:
        print(p)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main()
