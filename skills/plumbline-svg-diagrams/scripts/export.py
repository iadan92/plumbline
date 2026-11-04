#!/usr/bin/env python3
"""Export a plumbline diagram as PNG, PDF or an animated GIF, on macOS, Linux and Windows.

Usage: export.py INPUT OUTPUT [--scale 2] [--max-width 1200] [--fps 12] [--theme dark] [--animate packets]

  INPUT   an .svg file, or a spec .json (needed for .gif: the frames are drawn from the spec)
  OUTPUT  .png, .pdf or .gif; the extension picks the format
          .png  one image, 2x by default so text stays sharp on retina screens and slides
          .pdf  one page holding a 2x raster image of the diagram (not vector)
          .gif  one animation loop, from a spec with --animate packets (default) or dashes

Needs Node.js 18 or newer with npm. The first run installs @resvg/resvg-js and gifenc into
~/.cache/plumbline (set PLUMBLINE_CACHE to move it); after that it works offline. Text is drawn with the
fonts installed on the machine, so a Linux box without fonts needs one installed (for example fonts-dejavu).
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render_diagram import render  # noqa: E402

PACKAGES = ["@resvg/resvg-js@2.6.2", "gifenc@1.0.3"]


def modules_dir():
    """Folder holding node_modules with the two packages; installs them on first use."""
    root = os.environ.get("PLUMBLINE_CACHE") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache"), "plumbline")
    if os.path.isdir(os.path.join(root, "node_modules", "@resvg", "resvg-js")) and os.path.isdir(os.path.join(root, "node_modules", "gifenc")):
        return root
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("export needs Node.js with npm (https://nodejs.org). Without it, open the .svg in a browser and "
                         "take a screenshot, or on macOS use preview_slices.py.")
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "package.json"), "w") as f:
        json.dump({"name": "plumbline-export-cache", "private": True}, f)
    print(f"installing {', '.join(PACKAGES)} into {root} (first run only)")
    proc = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--loglevel=error", "--prefix", root, *PACKAGES],
                          capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit("npm install failed (is there network access?):\n" + proc.stderr.strip())
    return root


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--scale", type=float, default=2, help="PNG and PDF zoom, default 2")
    ap.add_argument("--max-width", type=int, default=1200, help="GIF width in pixels, default 1200 (0 keeps the full size)")
    ap.add_argument("--fps", type=float, default=12, help="GIF frames per second, default 12")
    ap.add_argument("--colors", type=int, default=128, help="GIF palette size, default 128")
    ap.add_argument("--theme", help="theme for a spec input (light, dark, print)")
    ap.add_argument("--theme-file", help="brand palette JSON for a spec input")
    ap.add_argument("--animate", choices=["packets", "dashes"], help="animation for a GIF, default packets")
    ap.add_argument("--at", type=float, help="PNG or PDF of a spec input at this second of the animation")
    args = ap.parse_args()

    ext = os.path.splitext(args.output)[1].lower().lstrip(".")
    if ext not in ("png", "pdf", "gif"):
        ap.error("OUTPUT must end in .png, .pdf or .gif (for an SVG, use render_diagram.py)")
    node = shutil.which("node")
    if not node:
        raise SystemExit("export needs Node.js 18 or newer (https://nodejs.org)")
    is_spec = args.input.lower().endswith(".json")
    if ext == "gif" and not is_spec:
        raise SystemExit("a GIF is drawn from a spec: pass the spec .json, not the .svg (an SVG has no frames to sample)")

    tmp = tempfile.mkdtemp(prefix="plumbline-export-")
    try:
        inputs = [args.input]
        if is_spec:
            spec = json.load(open(args.input))
            palette, extra = None, {}
            if args.theme_file:
                extra = json.load(open(args.theme_file))
                palette = extra.get("palette")
                spec.setdefault("options", {})
                for k in ("font", "mono"):
                    if k in extra:
                        spec["options"].setdefault(k, extra[k])
            theme = args.theme or extra.get("theme")
            if ext == "gif":
                animate = args.animate or "packets"
                first = render(spec, theme=theme, animate=animate, t=0, palette=palette)
                for w in first["warnings"]:
                    print("WARNING:", w)
                if not first["loop"]:
                    raise SystemExit("nothing animates in this diagram; a sequence or lineage with connections is needed")
                count = max(2, int(math.ceil(first["loop"] * args.fps)))
                inputs = []
                for k in range(count):
                    path = os.path.join(tmp, f"frame-{k:04d}.svg")
                    with open(path, "w") as f:
                        f.write(render(spec, theme=theme, animate=animate, t=k / args.fps, palette=palette)["svg"])
                    inputs.append(path)
                print(f"drew {count} frames for a {first['loop']:.1f} s loop")
            else:
                res = render(spec, theme=theme, animate="packets" if args.at is not None else None, t=args.at, palette=palette)
                for w in res["warnings"]:
                    print("WARNING:", w)
                path = os.path.join(tmp, "diagram.svg")
                with open(path, "w") as f:
                    f.write(res["svg"])
                inputs = [path]
        cmd = [node, os.path.join(HERE, "raster.mjs"), "--modules", modules_dir(), "--mode", ext, "--out", os.path.abspath(args.output),
               "--scale", str(args.scale), "--max-width", str(args.max_width if ext == "gif" else 0), "--fps", str(args.fps),
               "--colors", str(args.colors), *inputs]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(proc.stdout)
        if proc.returncode:
            raise SystemExit("rasteriser failed:\n" + proc.stderr.strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
