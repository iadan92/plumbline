"""Check a plumbline spec before rendering and name the exact field that is wrong.

check(spec) returns (errors, warnings), each a list of strings such as
`nodes[3].lane: unknown lane 'stagging'. Did you mean 'staging'?`. Errors stop the render; warnings do not.
Run it alone with `render_diagram.py spec.json --validate`.
"""
import difflib

from common import GLYPHS, STATE_ALIASES, STATES, THEMES

TOP = {"title", "type", "options", "lanes", "nodes", "edges", "groups", "layout", "center", "box_title",
       "participants", "phases", "messages", "frames", "state", "description", "summary"}
OPTIONS = {"card_w", "gap", "row_gap", "trunk", "x0", "y0", "lane_pad", "show_new", "theme", "animate", "lines",
           "show_lanes", "group_pad", "group_head", "flip", "fit_width", "auto_glyph", "diff_labels", "legend",
           "palette", "font", "mono", "numbers", "headers", "lines_set"}
NODE = {"id", "title", "sub", "lane", "row", "w", "y", "glyph", "icon", "state", "badge", "columns", "layer", "note"}
EDGE = {"from", "to", "label", "style", "state", "step", "from_col", "to_col"}
COLUMN = {"name", "type", "key", "state", "note"}
GROUP = {"id", "title", "sub", "members", "state", "style"}
PART = {"id", "title", "sub", "glyph", "icon", "state", "note"}
PHASE = {"id", "title", "sub", "state", "messages"}
MESSAGE = {"id", "from", "to", "label", "kind", "reply", "repeat", "state", "over"}
FRAME = {"label", "from", "to"}
KEYS = ("PK", "FK", "PK,FK", None)


def _near(word, options):
    m = difflib.get_close_matches(str(word), sorted(str(o) for o in options), 1, 0.6)
    return f" Did you mean '{m[0]}'?" if m else ""


def _keys(obj, allowed, path, warnings):
    for k in obj:
        if k not in allowed:
            warnings.append(f"{path}.{k}: unknown field, ignored.{_near(k, allowed)}")


def _state(value, path, errors):
    if value is None:
        return
    s = STATE_ALIASES.get(str(value).lower(), str(value).lower())
    if s not in STATES:
        errors.append(f"{path}: unknown state '{value}'. Use added, modified (or changed), removed (or deleted), unchanged.")


def check(spec):
    errors, warnings = [], []
    if not isinstance(spec, dict):
        return ["spec: the file must hold one JSON object"], warnings
    _keys(spec, TOP, "spec", warnings)
    opts = spec.get("options", {})
    if not isinstance(opts, dict):
        errors.append("options: must be an object")
        opts = {}
    _keys(opts, OPTIONS, "options", warnings)
    if opts.get("theme") is not None and opts["theme"] not in THEMES:
        errors.append(f"options.theme: unknown theme '{opts['theme']}'. Use {', '.join(sorted(THEMES))}.")
    if opts.get("animate") not in (None, "none", "packets", "dashes"):
        errors.append(f"options.animate: '{opts['animate']}' is not none, packets or dashes")
    if opts.get("lines") not in (None, "merge", "lanes"):
        errors.append(f"options.lines: '{opts['lines']}' is not merge or lanes")
    if opts.get("headers") not in (None, "top", "phase"):
        errors.append(f"options.headers: '{opts['headers']}' is not top or phase")
    if spec.get("type") == "sequence":
        _sequence(spec, errors, warnings)
    else:
        _flow(spec, errors, warnings)
    return errors, warnings


def _flow(spec, errors, warnings):
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes: give at least one node, for example {\"id\": \"raw_orders\", \"title\": \"raw.orders\"}")
        return
    lanes = spec.get("lanes")
    lane_ids = []
    if lanes is not None:
        for i, ln in enumerate(lanes):
            if not isinstance(ln, dict) or "id" not in ln:
                errors.append(f"lanes[{i}]: needs an id")
            else:
                lane_ids.append(ln["id"])
        if len(set(lane_ids)) != len(lane_ids):
            errors.append("lanes: duplicate lane ids")
    star = spec.get("layout") == "star"
    ids, seen_cells = {}, {}
    for i, n in enumerate(nodes):
        p = f"nodes[{i}]"
        if not isinstance(n, dict) or "id" not in n:
            errors.append(f"{p}: every node needs an id")
            continue
        _keys(n, NODE, p, warnings)
        if n["id"] in ids:
            errors.append(f"{p}.id: duplicate id '{n['id']}'")
        ids[n["id"]] = n
        if n.get("glyph") is not None and n["glyph"] not in GLYPHS:
            errors.append(f"{p}.glyph: unknown glyph '{n['glyph']}'.{_near(n['glyph'], GLYPHS)} Known: {', '.join(GLYPHS)}.")
        _state(n.get("state"), f"{p}.state", errors)
        if n.get("lane") is not None:
            if lanes is None and not star:
                errors.append(f"{p}.lane: '{n['lane']}' given but the spec has no lanes list; add lanes or drop the lane")
            elif lanes is not None and n["lane"] not in lane_ids:
                errors.append(f"{p}.lane: unknown lane '{n['lane']}'.{_near(n['lane'], lane_ids)} Lanes: {', '.join(map(str, lane_ids))}.")
        if n.get("row") is not None and not isinstance(n["row"], (int, float)):
            errors.append(f"{p}.row: must be a number, not '{n['row']}'")
        if n.get("lane") is not None and n.get("row") is not None and "y" not in n:
            cell = (n["lane"], n["row"])
            if cell in seen_cells:
                errors.append(f"{p}: '{n['id']}' and '{seen_cells[cell]}' are both in lane '{n['lane']}' row {n['row']} and would overlap")
            seen_cells[cell] = n["id"]
        cols = n.get("columns")
        if cols is not None:
            names = set()
            for j, c in enumerate(cols):
                cp = f"{p}.columns[{j}]"
                if not isinstance(c, dict) or "name" not in c:
                    errors.append(f"{cp}: every column needs a name")
                    continue
                _keys(c, COLUMN, cp, warnings)
                if c["name"] in names:
                    errors.append(f"{cp}.name: duplicate column '{c['name']}' in {n['id']}")
                names.add(c["name"])
                if c.get("key") not in KEYS:
                    errors.append(f"{cp}.key: '{c['key']}' is not PK, FK, PK,FK or null")
                _state(c.get("state"), f"{cp}.state", errors)
    for i, e in enumerate(spec.get("edges", [])):
        p = f"edges[{i}]"
        if not isinstance(e, dict) or "from" not in e or "to" not in e:
            errors.append(f"{p}: every edge needs from and to")
            continue
        _keys(e, EDGE, p, warnings)
        for end in ("from", "to"):
            if e[end] not in ids:
                errors.append(f"{p}.{end}: unknown node '{e[end]}'.{_near(e[end], ids)}")
        for end, col in (("from", "from_col"), ("to", "to_col")):
            n = ids.get(e.get(end))
            if e.get(col) and n is not None:
                names = [c["name"] for c in (n.get("columns") or []) if isinstance(c, dict) and "name" in c]
                if e[col] not in names:
                    errors.append(f"{p}.{col}: node '{n['id']}' has no column '{e[col]}'.{_near(e[col], names)}")
        if e.get("style") not in (None, "solid", "dotted"):
            errors.append(f"{p}.style: '{e['style']}' is not solid or dotted")
        _state(e.get("state"), f"{p}.state", errors)
    gids = {g.get("id") for g in spec.get("groups", []) if isinstance(g, dict)}
    for i, g in enumerate(spec.get("groups", [])):
        p = f"groups[{i}]"
        if not isinstance(g, dict) or "id" not in g or "members" not in g:
            errors.append(f"{p}: every group needs an id and members")
            continue
        _keys(g, GROUP, p, warnings)
        for m in g["members"]:
            if m not in ids and m not in gids:
                errors.append(f"{p}.members: '{m}' is neither a node nor a group.{_near(m, list(ids) + list(gids))}")
        _state(g.get("state"), f"{p}.state", errors)


def _sequence(spec, errors, warnings):
    parts = spec.get("participants")
    if not isinstance(parts, list) or not parts:
        errors.append("participants: give at least one participant")
        return
    pids = set()
    for i, p in enumerate(parts):
        if not isinstance(p, dict) or "id" not in p:
            errors.append(f"participants[{i}]: needs an id")
            continue
        _keys(p, PART, f"participants[{i}]", warnings)
        if p["id"] in pids:
            errors.append(f"participants[{i}].id: duplicate id '{p['id']}'")
        pids.add(p["id"])
        if p.get("glyph") is not None and p["glyph"] not in GLYPHS:
            errors.append(f"participants[{i}].glyph: unknown glyph '{p['glyph']}'.{_near(p['glyph'], GLYPHS)}")
        _state(p.get("state"), f"participants[{i}].state", errors)
    phases = spec.get("phases") or [{"id": "main", "messages": spec.get("messages", [])}]
    msg_ids = set()
    for pi, ph in enumerate(phases):
        pp = f"phases[{pi}]" if spec.get("phases") else "spec"
        if spec.get("phases"):
            _keys(ph, PHASE, pp, warnings)
        _state(ph.get("state"), f"{pp}.state", errors)
        for mi, m in enumerate(ph.get("messages", [])):
            p = f"{pp}.messages[{mi}]"
            _keys(m, MESSAGE, p, warnings)
            if m.get("id"):
                if m["id"] in msg_ids:
                    errors.append(f"{p}.id: duplicate message id '{m['id']}'")
                msg_ids.add(m["id"])
                if m.get("reply"):
                    msg_ids.add(f"{m['id']}:reply")
            if m.get("kind") not in (None, "sync", "call", "return", "async", "self", "note"):
                errors.append(f"{p}.kind: '{m['kind']}' is not sync, return, async, self or note")
            ends = m.get("over", []) if m.get("kind") == "note" else [m.get("from"), m.get("to") if m.get("kind") != "self" else m.get("from")]
            for pid in ([ends] if isinstance(ends, str) else ends):
                if pid not in pids:
                    errors.append(f"{p}: unknown participant '{pid}'.{_near(pid, pids)}")
            _state(m.get("state"), f"{p}.state", errors)
    for i, fr in enumerate(spec.get("frames", [])):
        _keys(fr, FRAME, f"frames[{i}]", warnings)
        for end in ("from", "to"):
            if fr.get(end) not in msg_ids:
                errors.append(f"frames[{i}].{end}: unknown message id '{fr.get(end)}'.{_near(fr.get(end), msg_ids)}")
