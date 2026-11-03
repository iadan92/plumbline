#!/usr/bin/env python3
"""Render a hand-laid SVG diagram in the PR Lens visual style from a JSON spec.

Usage: render_diagram.py spec.json out.svg [--theme light|dark] [--animate none|packets|dashes]

Why this exists: PR Lens lays nodes out itself (two per row, staggered, lines routed
over the top). This script puts every node exactly where the spec says, so stage
columns, chain rows and line routes stay predictable. See SKILL.md for the spec.
"""
import argparse
import html
import itertools
import json
import os
import sys

MONO = 'ui-monospace, SFMono-Regular, &quot;SF Mono&quot;, Menlo, Consolas, monospace'
SANS = '-apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, &quot;Noto Sans&quot;, Helvetica, Arial, sans-serif'

# state -> (line color, card stroke opacity, pill text, badge fill)
THEMES = {
    "light": {
        "bg": "#f4f5f7", "dots": "rgba(140,149,159,.5)", "lane": "rgba(255,255,255,.55)",
        "lane_label": "#59636e", "lane_sub": "#8c959f", "card": "#ffffff", "card_stroke": "#d0d7de",
        "chip": "#f1f3f5", "glyph": "#59636e", "title": "#1f2328", "sub": "#59636e",
        "colname": "#1a7f37", "coltype": "#59636e", "sep": "#d8dee4", "pill": "#ffffff",
        "pill_stroke": "#d1d9e0", "shadow": "rgba(31,35,40,.14)", "packet_ring": "#ffffff",
        "group_fill": ["rgba(31,35,40,.035)", "rgba(31,35,40,.055)", "rgba(31,35,40,.08)"],
        "group_stroke": "#c7ced6", "group_title": "#59636e",
        "states": {
            "added": ("#1f883d", 0.55, "#116329", "#b9f0c4"),
            "modified": ("#bf8700", 0.55, "#7d4e00", "#fff1b8"),
            "removed": ("#cf222e", 0.55, "#82071e", "#ffd1d4"),
            "unchanged": ("#8c959f", 1.0, "#59636e", "#f1f3f5"),
        },
    },
    "dark": {
        "bg": "#0d1117", "dots": "rgba(110,118,129,.18)", "lane": "rgba(110,118,129,.07)",
        "lane_label": "#9198a1", "lane_sub": "#6e7681", "card": "#1c2128", "card_stroke": "#3d444d",
        "chip": "rgba(110,118,129,.22)", "glyph": "#9198a1", "title": "#e6edf3", "sub": "#9198a1",
        "colname": "#3fb950", "coltype": "#9198a1", "sep": "#30363d", "pill": "#1c2128",
        "pill_stroke": "#3d444d", "shadow": "rgba(0,0,0,.28)", "packet_ring": "#0d1117",
        "group_fill": ["rgba(255,255,255,.03)", "rgba(255,255,255,.05)", "rgba(255,255,255,.07)"],
        "group_stroke": "#3d444d", "group_title": "#9198a1",
        "states": {
            "added": ("#3fb950", 0.4, "#3fb950", "rgba(46,160,67,.15)"),
            "modified": ("#d29922", 0.4, "#d29922", "rgba(187,128,9,.15)"),
            "removed": ("#f85149", 0.4, "#f85149", "rgba(248,81,73,.12)"),
            "unchanged": ("#6e7681", 1.0, "#9198a1", "rgba(110,118,129,.22)"),
        },
    },
}

STEP_SECONDS, TRAVEL_SECONDS, PAUSE_SECONDS = 1.6, 1.1, 1.6


def esc(s):
    return html.escape(str(s), quote=False)


def glyph(kind, x, y, color):
    """Icon inside a 26x26 chip whose top-left corner is (x, y)."""
    s = f'stroke="{color}" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    cx, cy = x + 13, y + 13
    if kind == "db":
        return (f'<ellipse {s} cx="{cx}" cy="{cy - 4.5}" rx="6.5" ry="2.6"/>'
                f'<path {s} d="M{cx - 6.5},{cy - 4.5} v9 a6.5,2.6 0 0 0 13 0 v-9"/>')
    if kind == "module":
        return (f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="11" font-weight="600" fill="{color}" '
                f'font-family="{MONO}">{{ }}</text>')
    if kind == "table":
        return (f'<rect {s} x="{cx - 6.5}" y="{cy - 6}" width="13" height="12" rx="2"/>'
                f'<path {s} d="M{cx - 6.5},{cy - 1.5} h13 M{cx - 1},{cy - 1.5} v7.5"/>')
    if kind == "service":
        return (f'<rect {s} x="{cx - 6.5}" y="{cy - 6.5}" width="13" height="13" rx="3"/>'
                f'<circle {s} cx="{cx}" cy="{cy}" r="2"/>')
    if kind == "ui":
        return (f'<rect {s} x="{cx - 7}" y="{cy - 6}" width="14" height="12" rx="2"/>'
                f'<path {s} d="M{cx - 7},{cy - 2} h14"/>')
    if kind == "queue":
        return f'<path {s} d="M{cx - 6},{cy - 4} h12 M{cx - 6},{cy} h12 M{cx - 6},{cy + 4} h12"/>'
    if kind == "file":
        return f'<path {s} d="M{cx - 5},{cy - 7} h7 l3,3 v11 h-10 z M{cx + 2},{cy - 7} v3 h3"/>'
    return ""


def rounded(points, r=8):
    """Orthogonal polyline with rounded corners."""
    d = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]

        def toward(ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            ln = (dx * dx + dy * dy) ** 0.5 or 1
            k = min(r, ln / 2) / ln
            return ax + dx * k, ay + dy * k

        sx, sy = toward(x1, y1, x0, y0)
        ex, ey = toward(x1, y1, x2, y2)
        d.append(f"L{sx:.1f},{sy:.1f} Q{x1:.1f},{y1:.1f} {ex:.1f},{ey:.1f}")
    d.append(f"L{points[-1][0]:.1f},{points[-1][1]:.1f}")
    return " ".join(d)


def simplify(points):
    """Drop duplicate and collinear points."""
    out = []
    for p in points:
        if not out or (abs(p[0] - out[-1][0]) > 0.01 or abs(p[1] - out[-1][1]) > 0.01):
            out.append(p)
    i = 1
    while i < len(out) - 1:
        (x0, y0), (x1, y1), (x2, y2) = out[i - 1], out[i], out[i + 1]
        if (abs(x0 - x1) < 0.01 and abs(x1 - x2) < 0.01) or (abs(y0 - y1) < 0.01 and abs(y1 - y2) < 0.01):
            out.pop(i)
        else:
            i += 1
    return out


def seg_hits_rect(p, q, rect, pad=2):
    """Axis-aligned segment p-q against rect (x, y, w, h)."""
    x, y, w, h = rect
    x0, x1 = sorted((p[0], q[0]))
    y0, y1 = sorted((p[1], q[1]))
    return x0 < x + w - pad and x1 > x + pad and y0 < y + h - pad and y1 > y + pad


def auto_star(spec, opt):
    """Lay out a star or snowflake schema automatically inside one box.

    The centre table (the fact) goes in the middle. Tables it references are balanced across the left and
    right columns (and one above or below the fact when that makes the diagram more compact). Tables that
    only a dimension references (snowflake sub-dimensions) go one column further out, next to their parent.
    """
    nodes = {n["id"]: n for n in spec["nodes"]}
    gap = opt["row_gap"]

    def h(n):
        cols = n.get("columns") or []
        return 62 + (len(cols) * 20 + 14 if cols else 0)

    adj = {k: set() for k in nodes}
    out_deg = {k: 0 for k in nodes}
    for e in spec["edges"]:
        adj[e["from"]].add(e["to"])
        adj[e["to"]].add(e["from"])
        out_deg[e["from"]] += 1
    center = spec.get("center") or max(nodes, key=lambda k: (out_deg[k], len(adj[k])))
    parent, order, queue = {center: None}, [], [center]
    while queue:
        cur = queue.pop(0)
        for nb in sorted(adj[cur]):
            if nb not in parent:
                parent[nb] = cur
                order.append(nb)
                queue.append(nb)
    missing = [k for k in nodes if k not in parent]
    if missing:
        raise SystemExit(f"star layout: not connected to {center}: {missing}")
    children = {k: [c for c in order if parent[c] == k] for k in nodes}

    def unit_h(k):
        kids = children[k]
        return max(h(nodes[k]), sum(unit_h(c) for c in kids) + gap * max(len(kids) - 1, 0))

    dims = sorted(children[center], key=lambda k: -unit_h(k))
    fact_h = h(nodes[center])
    left, right, above, below = [], [], [], []

    def col_h(units):
        return sum(unit_h(u) for u in units) + gap * max(len(units) - 1, 0)

    def centre_h(a, b):
        return fact_h + (unit_h(a[0]) + gap if a else 0) + (gap + unit_h(b[0]) if b else 0)

    for d in dims:
        options = []
        for name, col in (("L", left), ("R", right)):
            trial = col + [d]
            hl = col_h(trial) if col is left else col_h(left)
            hr = col_h(trial) if col is right else col_h(right)
            options.append((max(hl, hr, centre_h(above, below)), name))
        if not children[d]:
            if not below:
                options.append((max(col_h(left), col_h(right), centre_h(above, [d])), "B"))
            if not above:
                options.append((max(col_h(left), col_h(right), centre_h(([d]), below)), "T"))
        best = min(options, key=lambda o: (o[0], "LRBT".index(o[1])))[1]
        {"L": left, "R": right, "B": below, "T": above}[best].append(d)

    def fk_rank(k):
        """Row index in the centre table of the column that links to k, so lines leave in the same order."""
        par = parent[k]
        for e in spec["edges"]:
            if {e["from"], e["to"]} == {par, k}:
                col = e.get("from_col") if e["from"] == par else e.get("to_col")
                names = [c["name"] for c in (nodes[par].get("columns") or [])]
                if col in names:
                    return names.index(col)
        return 0

    left.sort(key=fk_rank)
    right.sort(key=fk_rank)

    def depth_of(side_units):
        def d(k):
            return 1 + max([d(c) for c in children[k]] + [0])
        return max([d(u) for u in side_units] + [0])

    dl, dr = depth_of(left), depth_of(right)
    lane_ids = [f"L{i}" for i in range(dl, 0, -1)] + ["C"] + [f"R{i}" for i in range(1, dr + 1)]
    lane_pos = {lid: i for i, lid in enumerate(lane_ids)}
    height = max(col_h(left), col_h(right), centre_h(above, below))
    y0 = 64

    def place(k, lane, y, side):
        nodes[k]["lane"], nodes[k]["row"], nodes[k]["y"] = lane, 0, y
        yy = y
        for c in children[k]:
            nxt = f"{side}{int(lane[1:]) + 1}"
            place(c, nxt, yy, side)
            yy += unit_h(c) + gap

    def stack(units, lane_prefix, top):
        y = top
        for u in units:
            place(u, f"{lane_prefix}1", y, lane_prefix)
            y += unit_h(u) + gap

    stack(left, "L", y0 + (height - col_h(left)) / 2)
    stack(right, "R", y0 + (height - col_h(right)) / 2)
    top = y0 + (height - centre_h(above, below)) / 2
    if above:
        nodes[above[0]].update(lane="C", row=0, y=top)
        top += unit_h(above[0]) + gap
    nodes[center].update(lane="C", row=0, y=top)
    if below:
        nodes[below[0]].update(lane="C", row=0, y=top + fact_h + gap)
    spec["lanes"] = [{"id": lid, "label": lid} for lid in lane_ids]
    spec["nodes"] = list(nodes.values())
    spec["groups"] = list(spec.get("groups", [])) + [
        {"id": "__star", "title": spec.get("box_title", spec.get("title", "")), "members": list(nodes)}]
    opt["show_lanes"] = False
    opt.setdefault("lines_set", False)
    return spec


def _segments(pts):
    return list(zip(pts, pts[1:]))


def _crossings(pa, pb):
    """Number of crossings or overlaps between two orthogonal polylines (touching at endpoints ignored)."""
    n = 0
    for (a0, a1) in _segments(pa):
        for (b0, b1) in _segments(pb):
            ah, bh = abs(a0[1] - a1[1]) < 0.01, abs(b0[1] - b1[1]) < 0.01
            if ah == bh:
                if ah and abs(a0[1] - b0[1]) < 0.01:
                    lo, hi = max(min(a0[0], a1[0]), min(b0[0], b1[0])), min(max(a0[0], a1[0]), max(b0[0], b1[0]))
                    n += 1 if hi - lo > 1 else 0
                elif not ah and abs(a0[0] - b0[0]) < 0.01:
                    lo, hi = max(min(a0[1], a1[1]), min(b0[1], b1[1])), min(max(a0[1], a1[1]), max(b0[1], b1[1]))
                    n += 1 if hi - lo > 1 else 0
                continue
            (h0, h1), (v0, v1) = ((a0, a1), (b0, b1)) if ah else ((b0, b1), (a0, a1))
            hx0, hx1 = sorted((h0[0], h1[0]))
            vy0, vy1 = sorted((v0[1], v1[1]))
            if hx0 + 0.5 < v0[0] < hx1 - 0.5 and vy0 + 0.5 < h0[1] < vy1 - 0.5:
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--theme", choices=THEMES)
    ap.add_argument("--animate", choices=["none", "packets", "dashes"])
    args = ap.parse_args()

    spec = json.load(open(args.spec))
    if spec.get("type") == "sequence":
        # sibling module; the explicit path keeps this working under python -I
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from render_sequence import render_sequence
        return render_sequence(spec, spec.get("options", {}), args.theme, args.animate, args.out)
    opt = {"card_w": 230, "gap": 150, "row_gap": 30, "trunk": 40, "x0": 32, "y0": 100,
           "lane_pad": 16, "show_new": False, "theme": "light", "animate": "none",
           "lines": "merge", "show_lanes": True, "group_pad": 20, "group_head": 30, "flip": False}
    opt.update(spec.get("options", {}))
    if args.theme:
        opt["theme"] = args.theme
    if spec.get("layout") == "star":
        opt.setdefault("lines", "lanes")
        if "lines" not in spec.get("options", {}):
            opt["lines"] = "lanes"
        opt["group_pad"] = spec.get("options", {}).get("group_pad", 26)
        spec = auto_star(spec, opt)
    if args.animate:
        opt["animate"] = args.animate
    T = THEMES[opt["theme"]]
    P = T["states"]
    warnings = []

    nodes = {n["id"]: n for n in spec["nodes"]}
    lanes = list(spec["lanes"])
    if opt["flip"]:
        lanes.reverse()
    lane_idx = {l["id"]: i for i, l in enumerate(lanes)}
    for n in nodes.values():
        if n["lane"] not in lane_idx:
            raise SystemExit(f"node {n['id']}: unknown lane {n['lane']}")
        n.setdefault("state", "unchanged")
        n.setdefault("glyph", "table" if n.get("columns") else "db")
        n.setdefault("w", opt["card_w"])
        cols = n.get("columns") or []
        n["h"] = 62 + (len(cols) * 20 + 14 if cols else 0)

    # row y positions: rows may be ints or floats, sorted, each as tall as its tallest card
    rows = sorted({n["row"] for n in nodes.values()})
    row_y, y = {}, opt["y0"]
    for r in rows:
        row_y[r] = y
        y += max(n["h"] for n in nodes.values() if n["row"] == r) + opt["row_gap"]
    total_h = y - opt["row_gap"] + 44
    lane_w = opt["card_w"] + 2 * opt["lane_pad"]
    col_x = [opt["x0"] + opt["lane_pad"] + i * (opt["card_w"] + opt["gap"]) for i in range(len(lanes))]
    for n in nodes.values():
        if "y" in n:
            total_h = max(total_h, n["y"] + n["h"] + 44)
    total_w = opt["x0"] * 2 + len(lanes) * opt["card_w"] + (len(lanes) - 1) * opt["gap"] + 2 * opt["lane_pad"] - 20

    for n in nodes.values():
        n["x"] = col_x[lane_idx[n["lane"]]] + (opt["card_w"] - n["w"]) / 2
        n["y"] = n["y"] if "y" in n else row_y[n["row"]]

    def port_y(n, col):
        if col and n.get("columns"):
            names = [c["name"] for c in n["columns"]]
            if col in names:
                return n["y"] + 62 + 7 + names.index(col) * 20 + 10
            warnings.append(f"{n['id']}: unknown column {col}")
        return n["y"] + (62 if n.get("columns") else n["h"]) / 2

    rects = {k: (n["x"], n["y"], n["w"], n["h"]) for k, n in nodes.items()}
    used_states = set()

    # pass 1: endpoints and direction of every edge
    infos = []
    for e in spec["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        state = e["state"] if "state" in e else (b["state"] if b["state"] != "unchanged" else a["state"])
        used_states.add(state)
        sy, ty = port_y(a, e.get("from_col")), port_y(b, e.get("to_col"))
        la, lb = lane_idx[a["lane"]], lane_idx[b["lane"]]
        infos.append({"e": e, "a": a, "b": b, "state": state, "sy": sy, "ty": ty, "la": la, "lb": lb})

    # pass 2: vertical trunk positions. "merge": every line into one target shares a trunk right before it.
    # "lanes": each line gets its own vertical lane inside the gap, ordered so lines cross as little as possible.
    gap_groups = {}
    for i in infos:
        if i["lb"] > i["la"]:
            gap_groups.setdefault(("R", i["lb"]), []).append(i)
        elif i["lb"] < i["la"]:
            gap_groups.setdefault(("L", i["lb"]), []).append(i)
    for (side, lb), items in gap_groups.items():
        if opt["lines"] == "lanes":
            if side == "R":
                x_lo, x_hi = col_x[lb - 1] + opt["card_w"] + 26, col_x[lb] - 26
            else:
                x_lo, x_hi = col_x[lb] + opt["card_w"] + 26, col_x[lb + 1] - 26
            ups = sorted([i for i in items if i["ty"] <= i["sy"]], key=lambda i: i["sy"])
            downs = sorted([i for i in items if i["ty"] > i["sy"]], key=lambda i: -i["sy"])
            ordered = ups + downs  # heuristic start; last index is closest to the target
            n_ = len(ordered)

            def tx_of(c):
                f = (c + 1) / (n_ + 1)
                return x_lo + f * (x_hi - x_lo) if side == "R" else x_hi - f * (x_hi - x_lo)

            def poly(i, tx):
                a_, b_ = i["a"], i["b"]
                if side == "R":
                    p0, p3 = (a_["x"] + a_["w"], i["sy"]), (b_["x"], i["ty"])
                else:
                    p0, p3 = (a_["x"], i["sy"]), (b_["x"] + b_["w"], i["ty"])
                return [p0, (tx, p0[1]), (tx, p3[1]), p3]

            def cost(order):
                polys = [poly(i, tx_of(c)) for c, i in enumerate(order)]
                return sum(_crossings(polys[x], polys[y]) for x in range(len(polys)) for y in range(x + 1, len(polys)))

            if 1 < n_ <= 6:
                best, best_cost = ordered, cost(ordered)
                for perm in itertools.permutations(ordered):
                    c_ = cost(list(perm))
                    if c_ < best_cost:
                        best, best_cost = list(perm), c_
                ordered = best
            for c, i in enumerate(ordered):
                i["tx"] = tx_of(c)
        else:
            for i in items:
                i["tx"] = i["b"]["x"] - opt["trunk"] if side == "R" else i["b"]["x"] + i["b"]["w"] + opt["trunk"]

    paths, pills, seen_pills = [], [], set()
    for i in infos:
        e, a, b, la, lb, sy, ty = i["e"], i["a"], i["b"], i["la"], i["lb"], i["sy"], i["ty"]
        if lb > la:
            p0, p3 = (a["x"] + a["w"], sy), (b["x"], ty)
            pts = [p0, (i["tx"], p0[1]), (i["tx"], p3[1]), p3]
        elif lb < la:
            p0, p3 = (a["x"], sy), (b["x"] + b["w"], ty)
            pts = [p0, (i["tx"], p0[1]), (i["tx"], p3[1]), p3]
        else:
            cx = a["x"] + a["w"] / 2
            if b["y"] >= a["y"]:
                pts = [(cx, a["y"] + a["h"]), (cx, b["y"])]
            else:
                pts = [(cx, a["y"]), (cx, b["y"] + b["h"])]
        pts = simplify(pts)
        for p, q in zip(pts, pts[1:]):
            for k, r in rects.items():
                if k not in (e["from"], e["to"]) and seg_hits_rect(p, q, r):
                    warnings.append(f"edge {e['from']}->{e['to']} crosses card {k}")
        # animation step: explicit, else the stage the data arrives in
        step = e.get("step", lb if lb != la else la + 0.5)
        paths.append({"pts": pts, "state": i["state"], "style": e.get("style", "solid"), "step": step})
        label = e.get("label")
        if label:
            p, q = pts[0], pts[1]
            horizontal = abs(p[1] - q[1]) < 0.01
            length = abs(q[0] - p[0]) if horizontal else abs(q[1] - p[1])
            w = len(label) * 5.9 + 16
            if horizontal and length < w + 8:
                warnings.append(f"label '{label}' on {e['from']}->{e['to']} is wider than its first segment; increase options.gap")
            key = (e["from"], label, round(p[0]), round(p[1]), round(q[0]), round(q[1]))
            if key not in seen_pills:
                seen_pills.add(key)
                pills.append(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, label, i["state"]))

    # groups: nested boxes drawn around their members (nodes or other groups)
    groups = {g["id"]: g for g in spec.get("groups", [])}
    gbox, glevel = {}, {}

    def box_of(mid, trail=()):
        if mid in nodes:
            n = nodes[mid]
            return n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]
        if mid not in groups:
            raise SystemExit(f"group member {mid} is neither a node nor a group")
        if mid in trail:
            raise SystemExit(f"group {mid} contains itself")
        if mid in gbox:
            return gbox[mid]
        bs = [box_of(m, trail + (mid,)) for m in groups[mid]["members"]]
        pad = opt["group_pad"]
        gbox[mid] = (min(b[0] for b in bs) - pad, min(b[1] for b in bs) - pad - opt["group_head"],
                     max(b[2] for b in bs) + pad, max(b[3] for b in bs) + pad)
        return gbox[mid]

    for gid in groups:
        box_of(gid)

    def level(gid):
        parents = [g for g, d in groups.items() if gid in d["members"]]
        return 0 if not parents else 1 + max(level(p) for p in parents)

    for gid in groups:
        glevel[gid] = level(gid)
    content_w, content_h = total_w, total_h
    min_x = min([b[0] for b in gbox.values()] + [opt["x0"]])
    min_y = min([b[1] for b in gbox.values()] + [opt["y0"]])
    if gbox:
        content_w = max(content_w, max(b[2] for b in gbox.values()) + 20)
        content_h = max(content_h, max(b[3] for b in gbox.values()) + 30)
    dx = max(0, 14 - min_x) if gbox else 0
    dy = max(0, (74 if opt["show_lanes"] else 14) - min_y) if gbox else 0
    total_w, total_h = int(round(content_w + dx)), int(round(content_h + dy))

    title = spec.get("title", "Diagram")
    s = []
    add = s.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}" '
        f'role="img" aria-label="{esc(title)}" font-family="{SANS}">')
    add(f'<title>{esc(title)}</title>')
    defs = [f'<pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1" fill="{T["dots"]}"/></pattern>']
    for st in sorted(used_states | {"unchanged"}):
        defs.append(f'<marker id="mk-{st}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" '
                    f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{P[st][0]}"/></marker>')
    add("<defs>" + "".join(defs) + "</defs>")
    add(f'<rect width="{total_w}" height="{total_h}" rx="12" fill="{T["bg"]}"/><rect width="{total_w}" height="{total_h}" rx="12" fill="url(#dots)"/>')
    add(f'<g transform="translate({dx:g},{dy:g})">')

    if opt["show_lanes"]:
        for i, lane in enumerate(lanes):
            x = col_x[i] - opt["lane_pad"]
            add(f'<g><rect x="{x}" y="28" width="{lane_w}" height="{content_h - 48}" rx="12" fill="{T["lane"]}"/>'
                f'<text x="{x + opt["lane_pad"]}" y="54" font-size="10" font-weight="700" letter-spacing=".12em" fill="{T["lane_label"]}">{esc(lane["label"].upper())}</text>'
                + (f'<text x="{x + opt["lane_pad"]}" y="70" font-size="9.5" fill="{T["lane_sub"]}">{esc(lane["sub"])}</text>' if lane.get("sub") else "")
                + '</g>')

    # outermost groups first so inner boxes sit on top
    for gid in sorted(groups, key=lambda g: glevel[g]):
        g = groups[gid]
        x0_, y0_, x1_, y1_ = gbox[gid]
        stroke = T["group_stroke"]
        if g.get("state") and g["state"] != "unchanged":
            stroke = P[g["state"]][0]
        fill = T["group_fill"][min(glevel[gid], len(T["group_fill"]) - 1)]
        add(f'<g><rect x="{x0_:.1f}" y="{y0_:.1f}" width="{x1_ - x0_:.1f}" height="{y1_ - y0_:.1f}" rx="14" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1" stroke-dasharray="{"5 4" if g.get("style") == "dashed" else "none"}"/>'
            f'<text x="{x0_ + 16:.1f}" y="{y0_ + 21:.1f}" font-size="11" font-weight="700" fill="{T["group_title"]}">{esc(g.get("title", gid))}</text>'
            + (f'<text x="{x0_ + 16 + len(g.get("title", gid)) * 6.6 + 10:.1f}" y="{y0_ + 21:.1f}" font-size="9.5" fill="{T["lane_sub"]}">{esc(g["sub"])}</text>' if g.get("sub") else "")
            + '</g>')

    for p in paths:
        color = P[p["state"]][0]
        dash = ' stroke-dasharray="2 4"' if p["style"] == "dotted" else ""
        anim = ""
        if opt["animate"] == "dashes":
            dash = ' stroke-dasharray="6 6"'
            anim = '<animate attributeName="stroke-dashoffset" from="0" to="-12" dur="0.9s" repeatCount="indefinite"/>'
        add(f'<path d="{rounded(p["pts"])}" marker-end="url(#mk-{p["state"]})" fill="none" stroke="{color}" stroke-width="1.5"{dash}>{anim}</path>')

    if opt["animate"] == "packets":
        # one dot per edge travels along the line; edges sharing a step move together, steps play in order
        steps = sorted({p["step"] for p in paths})
        dur = len(steps) * STEP_SECONDS + PAUSE_SECONDS
        fade = 0.12 / dur
        for p in paths:
            k = steps.index(p["step"])
            t0 = k * STEP_SECONDS / dur
            t1 = (k * STEP_SECONDS + TRAVEL_SECONDS) / dur
            color = P[p["state"]][0]
            add(f'<circle r="3.6" fill="{color}" stroke="{T["packet_ring"]}" stroke-width="1.4" opacity="0">'
                f'<animateMotion dur="{dur:.2f}s" repeatCount="indefinite" keyPoints="0;0;1;1" keyTimes="0;{t0:.4f};{t1:.4f};1" '
                f'calcMode="linear" path="{rounded(p["pts"])}"/>'
                f'<animate attributeName="opacity" dur="{dur:.2f}s" repeatCount="indefinite" values="0;0;1;1;0;0" '
                f'keyTimes="0;{t0:.4f};{t0 + fade:.4f};{max(t1 - fade, t0 + fade):.4f};{t1:.4f};1"/></circle>')

    for n in nodes.values():
        color, op, _, badge_fill = P[n["state"]]
        stroke = T["card_stroke"] if n["state"] == "unchanged" else color
        sop = 1 if n["state"] == "unchanged" else op
        x, y0, w, h = n["x"], n["y"], n["w"], n["h"]
        add(f'<g filter="drop-shadow(0 1px 2px {T["shadow"]})"><rect x="{x}" y="{y0}" width="{w}" height="{h}" rx="10" '
            f'fill="{T["card"]}" stroke="{stroke}" stroke-opacity="{sop}" stroke-width="1"/>')
        add(f'<rect x="{x + 14}" y="{y0 + 18}" width="26" height="26" rx="7" fill="{T["chip"]}"/>{glyph(n["glyph"], x + 14, y0 + 18, T["glyph"])}')
        add(f'<text x="{x + 50}" y="{y0 + 27}" font-size="11.5" font-weight="600" fill="{T["title"]}">{esc(n["title"])}</text>')
        sub = n.get("sub") or (f'{len(n["columns"])} columns' if n.get("columns") else "")
        if sub:
            add(f'<text x="{x + 50}" y="{y0 + 45}" font-size="9.5" fill="{T["sub"]}" font-family="{MONO}">{esc(sub)}</text>')
        badge = n.get("badge") or ("NEW" if opt["show_new"] and n["state"] == "added" else None)
        if badge:
            bw = len(badge) * 6 + 16
            bx = x + w - bw - 12
            bfill = badge_fill if n.get("badge") is None else T["chip"]
            add(f'<g><rect x="{bx}" y="{y0 - 8}" width="{bw}" height="16" rx="8" fill="{bfill}" stroke="{T["pill_stroke"]}"/>'
                f'<text x="{bx + bw / 2}" y="{y0 + 3}" text-anchor="middle" font-size="8.5" font-weight="700" letter-spacing=".06em" fill="{P[n["state"]][2]}">{esc(badge)}</text></g>')
        if n.get("columns"):
            add(f'<path d="M{x},{y0 + 62} H{x + w}" stroke="{T["sep"]}" stroke-width="1"/>')
            # key chips ("PK", "FK", or "PK,FK" for a column that is both) share one column so names line up
            kw = max([len(c["key"]) * 5.6 + 12 for c in n["columns"] if c.get("key")] + [22])
            for i, c in enumerate(n["columns"]):
                cy = y0 + 62 + 7 + i * 20 + 10
                key = c.get("key")
                if key:
                    add(f'<rect x="{x + 14}" y="{cy - 7.5}" width="{kw:.1f}" height="15" rx="7.5" fill="{T["chip"]}"/>'
                        f'<text x="{x + 14 + kw / 2:.1f}" y="{cy + 3}" text-anchor="middle" font-size="8" font-weight="700" fill="{T["sub"]}">{esc(key)}</text>')
                add(f'<text x="{x + 14 + kw + 8:.1f}" y="{cy + 3.5}" font-size="10.5" fill="{T["colname"]}" font-family="{MONO}">{esc(c["name"])}</text>')
                if c.get("type"):
                    add(f'<text x="{x + w - 14}" y="{cy + 3.5}" text-anchor="end" font-size="9.5" fill="{T["coltype"]}" font-family="{MONO}">{esc(c["type"])}</text>')
        add('</g>')

    for px, py, text, state in pills:
        w = len(text) * 5.9 + 16
        add(f'<g><rect x="{px - w / 2:.1f}" y="{py - 8.5:.1f}" width="{w:.1f}" height="17" rx="8.5" fill="{T["pill"]}" stroke="{T["pill_stroke"]}"/>'
            f'<text x="{px:.1f}" y="{py + 3.2:.1f}" text-anchor="middle" font-size="9" font-weight="600" fill="{P[state][2]}">{esc(text)}</text></g>')
    add('</g></svg>')
    open(args.out, "w").write("\n".join(s))
    print(f"wrote {args.out} ({total_w}x{total_h}, theme={opt['theme']}, animate={opt['animate']})")
    for w_ in sorted(set(warnings)):
        print("WARNING:", w_)


if __name__ == "__main__":
    main()
