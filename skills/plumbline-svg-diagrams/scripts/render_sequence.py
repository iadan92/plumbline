"""Sequence diagram renderer (who calls whom, in time order) in the plumbline / PR Lens look.

Called from render_diagram.py when the spec has "type": "sequence". Not meant to be run directly.

Spec in short: participants (columns), phases (labelled bands) holding messages in time order.
Message kinds: sync (default), return, async, self, note. Activation bars, lifelines and arrow
ends are computed from the message order, so the spec never states coordinates.
"""
from render_diagram import MONO, SANS, THEMES, esc, glyph, rounded

BAR_W = 12
BAR_SHIFT = 5          # nested activations step right by this much
STEP_Y = 44            # vertical distance between messages
SELF_H = 22            # height of a self-call loop
SELF_W = 34            # width of a self-call loop
PHASE_HEAD = 38        # phase title row
CARD_H = 62
STEP_SECONDS, TRAVEL_SECONDS, PAUSE_SECONDS = 0.8, 0.6, 1.6


def pill_w(text, extra=0):
    return (len(text) + extra) * 5.9 + 16


def expand(spec, warnings):
    """Normalise phases and messages: flat 'messages' become one phase, 'reply' becomes a return."""
    phases = spec.get("phases") or [{"id": "main", "messages": spec.get("messages", [])}]
    pids = {p["id"] for p in spec["participants"]}
    out, n = [], 0
    for ph in phases:
        msgs = []
        for m in ph.get("messages", []):
            m = dict(m)
            if "kind" not in m:
                m["kind"] = "self" if m.get("from") and m.get("from") == m.get("to") else "sync"
            if m["kind"] == "call":
                m["kind"] = "sync"
            kind = m["kind"]
            if kind not in ("sync", "return", "async", "self", "note"):
                raise SystemExit(f"message {m.get('id', n)}: unknown kind {kind}")
            if kind == "note":
                over = m.get("over", [])
                m["over"] = [over] if isinstance(over, str) else list(over)
                ids = m["over"]
            else:
                if kind == "self":
                    m["to"] = m["from"]
                ids = [m.get("from"), m.get("to")]
            for pid in ids:
                if pid not in pids:
                    raise SystemExit(f"message {m.get('id', n)}: unknown participant {pid}")
            if m.get("repeat"):
                m["label"] = f"{m.get('label', '')} ×{m['repeat']}".strip()
            if len(m.get("label", "")) > 48:
                warnings.append(f"message {m.get('id', n)}: label over 48 characters, shorten it")
            m["_n"] = n
            n += 1
            msgs.append(m)
            if m.get("reply"):
                msgs.append({"kind": "return", "from": m["to"], "to": m["from"], "label": m["reply"],
                             "state": m.get("state"), "_n": n,
                             **({"id": f"{m['id']}:reply"} if m.get("id") else {})})
                n += 1
        out.append({**ph, "messages": msgs})
    return out


def render_sequence(spec, opt, args_theme, args_animate, out_path):
    keys = ("theme", "animate", "x0", "gap", "numbers", "headers")
    opt = {"x0": 40, "gap": 190, "numbers": False, "headers": "top", "theme": "light", "animate": "none",
           **{k: v for k, v in opt.items() if k in keys}}
    if args_theme:
        opt["theme"] = args_theme
    if args_animate:
        opt["animate"] = args_animate
    T = THEMES[opt["theme"]]
    P = T["states"]
    warnings = []

    parts = [dict(p) for p in spec["participants"]]
    pidx = {p["id"]: i for i, p in enumerate(parts)}
    phases = expand(spec, warnings)
    default_state = spec.get("state", "unchanged")
    pre = 4 if opt["numbers"] else 0    # room for a "12. " call number in front of each label

    # participant card widths, then column centres wide enough for every label that crosses a gap
    for p in parts:
        p.setdefault("glyph", "service")
        p.setdefault("state", "unchanged")
        p["w"] = int(max(150, min(280, max(len(p["title"]) * 7 + 80, len(p.get("sub", "")) * 5.9 + 66))))
    gaps = [max(opt["gap"], (parts[i]["w"] + parts[i + 1]["w"]) / 2 + 24) for i in range(len(parts) - 1)]
    msgs_all = [m for ph in phases for m in ph["messages"]]
    spans = []
    for m in msgs_all:
        if m["kind"] == "note":
            continue
        i, j = sorted((pidx[m["from"]], pidx[m["to"]]))
        if m["kind"] == "self":
            if i < len(gaps):
                gaps[i] = max(gaps[i], SELF_W + 10 + pill_w(m.get("label", ""), pre) + 28)
            continue
        spans.append((j - i, i, j, pill_w(m.get("label", ""), pre) + 60))
    for _, i, j, need in sorted(spans):
        have = sum(gaps[i:j])
        if have < need:
            for k in range(i, j):
                gaps[k] += (need - have) / (j - i)
    cx = [opt["x0"] + parts[0]["w"] / 2]
    for g in gaps:
        cx.append(cx[-1] + g)
    last_self = [pill_w(m.get("label", ""), pre) for m in msgs_all
                 if m["kind"] == "self" and pidx[m["from"]] == len(parts) - 1]
    right_extent = max(cx[-1] + parts[-1]["w"] / 2, cx[-1] + SELF_W + 28 + max(last_self + [0]))
    total_w = int(right_extent + opt["x0"])

    # ---- vertical layout and activation spans
    y = 24
    head_top = opt["headers"] == "top"
    if head_top:
        y += CARD_H + 18
    bands, bars, ys = [], [], {}
    for ph in phases:
        band_top = y
        y += PHASE_HEAD
        used = set()
        for m in ph["messages"]:
            used |= {pidx[q] for q in (m["over"] if m["kind"] == "note" else (m["from"], m["to"]))}
        head_y = None
        if not head_top:
            head_y = y
            y += CARD_H + 18
        y += 14
        stack = {i: [] for i in range(len(parts))}   # open activations per participant: (start y, state)
        for m in ph["messages"]:
            kind = m["kind"]
            m["y"] = y
            ys[m["_n"]] = y
            if m.get("id"):
                ys[m["id"]] = y
            if kind == "note":
                y += 42
                continue
            f, t = pidx[m["from"]], pidx[m["to"]]
            st = m["st"] = m.get("state") or ph.get("state") or default_state
            m["depth_from"] = len(stack[f])
            m["depth_to"] = len(stack[t])    # for a sync call: the level the new bar will sit on
            if kind == "sync":
                stack[t].append((y - 5, st))
            elif kind == "return" and stack[f]:
                y0, bst = stack[f].pop()
                bars.append((f, len(stack[f]), y0, y + 5, bst))
            elif kind == "async":
                bars.append((t, len(stack[t]), y - 5, y + 12, st))
            y += STEP_Y + (SELF_H + 6 if kind == "self" else 0)
        for i, stk in stack.items():
            if stk:
                warnings.append(f"phase {ph.get('id', '?')}: {len(stk)} call(s) into {parts[i]['title']} never return; "
                                "add a reply or a return message, or use kind async for fire and forget")
            while stk:
                y0, bst = stk.pop()
                bars.append((i, len(stk), y0, y - 14, bst))
        y += 2
        bands.append({"ph": ph, "top": band_top, "bottom": y, "head_y": head_y, "used": used})
        y += 16
    total_h = int(y + 8)

    def bar_cx(i, level):
        return cx[i] + BAR_SHIFT * level

    def edge(i, level, side):
        return bar_cx(i, level) + side * BAR_W / 2

    # ---- message paths: leave the edge of an active bar, arrive at the edge of the callee's new bar
    paths = []
    for b in bands:
        for m in b["ph"]["messages"]:
            if m["kind"] == "note":
                continue
            f, t, my = pidx[m["from"]], pidx[m["to"]], m["y"]
            df, dt = m["depth_from"], m["depth_to"]
            if m["kind"] == "self":
                xe = edge(f, df - 1, 1) if df else cx[f]
                pts = [(xe, my), (xe + SELF_W, my), (xe + SELF_W, my + SELF_H), (xe, my + SELF_H)]
                label_at = (xe + SELF_W + 8 + pill_w(m.get("label", "")) / 2, my + SELF_H / 2)
            else:
                sgn = 1 if t > f else -1
                x0 = edge(f, df - 1, sgn) if df else cx[f]
                if m["kind"] == "sync":
                    x1 = edge(t, dt, -sgn)
                else:
                    x1 = edge(t, dt - 1, -sgn) if dt else cx[t]
                pts = [(x0, my), (x1, my)]
                label_at = ((x0 + x1) / 2, my)
            paths.append({"m": m, "pts": pts, "label_at": label_at})

    # ---- svg
    title = spec.get("title", "Sequence diagram")
    s = []
    add = s.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}" '
        f'role="img" aria-label="{esc(title)}" font-family="{SANS}">')
    add(f'<title>{esc(title)}</title>')
    defs = [f'<pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1" fill="{T["dots"]}"/></pattern>']
    for st in sorted({p["m"]["st"] for p in paths} | {"unchanged"}):
        defs.append(f'<marker id="mk-{st}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6.5" markerHeight="6.5" '
                    f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{P[st][0]}"/></marker>')
        defs.append(f'<marker id="mo-{st}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                    f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="{P[st][0]}" stroke-width="1.6" '
                    f'stroke-linecap="round" stroke-linejoin="round"/></marker>')
    add("<defs>" + "".join(defs) + "</defs>")
    add(f'<rect width="{total_w}" height="{total_h}" rx="12" fill="{T["bg"]}"/><rect width="{total_w}" height="{total_h}" rx="12" fill="url(#dots)"/>')

    def header(i, top):
        p = parts[i]
        x = cx[i] - p["w"] / 2
        stroke = T["card_stroke"] if p["state"] == "unchanged" else P[p["state"]][0]
        sop = 1 if p["state"] == "unchanged" else P[p["state"]][1]
        add(f'<g filter="drop-shadow(0 1px 2px {T["shadow"]})"><rect x="{x:.1f}" y="{top}" width="{p["w"]}" height="{CARD_H}" rx="10" '
            f'fill="{T["card"]}" stroke="{stroke}" stroke-opacity="{sop}"/>'
            f'<rect x="{x + 14:.1f}" y="{top + 18}" width="26" height="26" rx="7" fill="{T["chip"]}"/>{glyph(p["glyph"], x + 14, top + 18, T["glyph"])}'
            f'<text x="{x + 50:.1f}" y="{top + (27 if p.get("sub") else 35)}" font-size="11.5" font-weight="600" fill="{T["title"]}">{esc(p["title"])}</text>'
            + (f'<text x="{x + 50:.1f}" y="{top + 45}" font-size="9.5" fill="{T["sub"]}" font-family="{MONO}">{esc(p["sub"])}</text>' if p.get("sub") else "")
            + '</g>')

    # phase bands with titles
    for b in bands:
        ph = b["ph"]
        add(f'<rect x="16" y="{b["top"]}" width="{total_w - 32}" height="{b["bottom"] - b["top"]}" rx="12" fill="{T["lane"]}"/>')
        if ph.get("title"):
            add(f'<text x="34" y="{b["top"] + 24}" font-size="11" font-weight="700" fill="{T["lane_label"]}">{esc(ph["title"])}</text>')
            if ph.get("sub"):
                add(f'<text x="{34 + len(ph["title"]) * 6.6 + 10:.1f}" y="{b["top"] + 24}" font-size="9.5" fill="{T["lane_sub"]}">{esc(ph["sub"])}</text>')

    # frames (loop / alt boxes around a message range)
    for fr in spec.get("frames", []):
        try:
            first, last = ys[fr["from"]], ys[fr["to"]]
        except KeyError as exc:
            raise SystemExit(f"frame {fr.get('label')}: unknown message id {exc}")
        inside = [p for p in paths if first <= p["m"]["y"] <= last]
        if not inside:
            continue
        xs = [x for p in inside for x, _ in p["pts"]]
        x0_, x1_ = min(xs) - 36, max(xs) + 30
        for p in inside:
            if p["m"]["kind"] == "self":
                x1_ = max(x1_, p["label_at"][0] + pill_w(p["m"].get("label", "")) / 2 + 20)
        y0_ = first - 26
        y1_ = last + (SELF_H + 14 if inside[-1]["m"]["kind"] == "self" else 16)
        tag = fr.get("label", "")
        tw = pill_w(tag) + 6
        tx = x1_ - tw - 10     # tag on the right: the left edge is where the busy bars are
        add(f'<g><rect x="{x0_:.1f}" y="{y0_}" width="{x1_ - x0_:.1f}" height="{y1_ - y0_}" rx="8" fill="none" '
            f'stroke="{T["group_stroke"]}" stroke-dasharray="5 4"/>'
            f'<rect x="{tx:.1f}" y="{y0_ - 9}" width="{tw:.1f}" height="17" rx="8.5" fill="{T["pill"]}" stroke="{T["pill_stroke"]}"/>'
            f'<text x="{tx + tw / 2:.1f}" y="{y0_ + 3}" text-anchor="middle" font-size="9" font-weight="700" fill="{T["lane_label"]}">{esc(tag)}</text></g>')

    # lifelines and headers
    life = f'stroke="{T["sep"]}" stroke-width="1.2" stroke-dasharray="4 4"'
    if head_top:
        for i in range(len(parts)):
            add(f'<path d="M{cx[i]:.1f},{24 + CARD_H} V{total_h - 16}" {life}/>')
            header(i, 24)
    else:
        for b in bands:
            for i in sorted(b["used"]):
                add(f'<path d="M{cx[i]:.1f},{b["head_y"] + CARD_H} V{b["bottom"] - 8}" {life}/>')
                header(i, b["head_y"])

    # notes
    for b in bands:
        for m in b["ph"]["messages"]:
            if m["kind"] != "note":
                continue
            xs = [cx[pidx[o]] for o in m["over"]]
            w = max(pill_w(m.get("label", "")) + 24, max(xs) - min(xs) + 60)
            xm = (min(xs) + max(xs)) / 2
            add(f'<g><rect x="{xm - w / 2:.1f}" y="{m["y"] - 13}" width="{w:.1f}" height="26" rx="6" fill="{T["card"]}" '
                f'stroke="{T["card_stroke"]}" stroke-dasharray="3 3"/>'
                f'<text x="{xm:.1f}" y="{m["y"] + 3.5}" text-anchor="middle" font-size="9.5" fill="{T["sub"]}">{esc(m.get("label", ""))}</text></g>')

    for i, level, y0, y1, st in bars:
        add(f'<rect x="{bar_cx(i, level) - BAR_W / 2:.1f}" y="{y0}" width="{BAR_W}" height="{y1 - y0}" rx="3" '
            f'fill="{P[st][3]}" stroke="{P[st][0]}" stroke-width="1.2"/>')

    # arrows
    for p in paths:
        m = p["m"]
        dash = ' stroke-dasharray="5 4"' if m["kind"] == "return" else ""
        mk = f'mo-{m["st"]}' if m["kind"] == "async" else f'mk-{m["st"]}'
        add(f'<path d="{rounded(p["pts"], 6)}" marker-end="url(#{mk})" fill="none" stroke="{P[m["st"]][0]}" stroke-width="1.5"{dash}/>')

    # label pills, with optional call numbers
    n_call = 0
    for p in paths:
        m = p["m"]
        text = m.get("label", "")
        if opt["numbers"] and m["kind"] != "return":
            n_call += 1
            text = f"{n_call}. {text}"
        if not text:
            continue
        w = pill_w(text)
        px, py = p["label_at"]
        add(f'<g><rect x="{px - w / 2:.1f}" y="{py - 8.5:.1f}" width="{w:.1f}" height="17" rx="8.5" fill="{T["pill"]}" stroke="{T["pill_stroke"]}"/>'
            f'<text x="{px:.1f}" y="{py + 3.2:.1f}" text-anchor="middle" font-size="9" font-weight="600" fill="{P[m["st"]][2]}">{esc(text)}</text></g>')

    # packets: one dot per message, played in message order
    if opt["animate"] == "packets" and paths:
        dur = len(paths) * STEP_SECONDS + PAUSE_SECONDS
        fade = 0.06 / dur
        for k, p in enumerate(paths):
            t0 = k * STEP_SECONDS / dur
            t1 = (k * STEP_SECONDS + TRAVEL_SECONDS) / dur
            add(f'<circle r="3.6" fill="{P[p["m"]["st"]][0]}" stroke="{T["packet_ring"]}" stroke-width="1.4" opacity="0">'
                f'<animateMotion dur="{dur:.2f}s" repeatCount="indefinite" keyPoints="0;0;1;1" keyTimes="0;{t0:.4f};{t1:.4f};1" '
                f'calcMode="linear" path="{rounded(p["pts"], 6)}"/>'
                f'<animate attributeName="opacity" dur="{dur:.2f}s" repeatCount="indefinite" values="0;0;1;1;0;0" '
                f'keyTimes="0;{t0:.4f};{t0 + fade:.4f};{max(t1 - fade, t0 + fade):.4f};{t1:.4f};1"/></circle>')

    add('</svg>')
    open(out_path, "w").write("\n".join(s))
    print(f"wrote {out_path} ({total_w}x{total_h}, theme={opt['theme']}, animate={opt['animate']}, "
          f"{len(parts)} participants, {len(paths)} messages)")
    for w_ in sorted(set(warnings)):
        print("WARNING:", w_)
    if total_w > 1800:
        print(f"NOTE: {total_w}px wide; slides and READMEs shrink it. Lower options.gap or use fewer participants per diagram.")
