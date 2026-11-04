"""Shared pieces of the plumbline renderers: themes, icons, line geometry, animation timing.

Imported by render_diagram.py and render_sequence.py. Not meant to be run directly.
"""
import copy
import html
import re

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
    # white page, no dot grid, darker strokes: for print, PDF and black-and-white photocopies
    "print": {
        "bg": "#ffffff", "dots": "rgba(0,0,0,0)", "lane": "rgba(0,0,0,.035)",
        "lane_label": "#2b2f33", "lane_sub": "#5b6269", "card": "#ffffff", "card_stroke": "#6b7280",
        "chip": "#eceef1", "glyph": "#2b2f33", "title": "#111418", "sub": "#3d434a",
        "colname": "#0f5c26", "coltype": "#3d434a", "sep": "#b8bec6", "pill": "#ffffff",
        "pill_stroke": "#8a919a", "shadow": "rgba(0,0,0,.10)", "packet_ring": "#ffffff",
        "group_fill": ["rgba(0,0,0,.03)", "rgba(0,0,0,.05)", "rgba(0,0,0,.075)"],
        "group_stroke": "#8a919a", "group_title": "#2b2f33",
        "states": {
            "added": ("#12602a", 0.9, "#0b4a1d", "#c9efd3"),
            "modified": ("#8a5a00", 0.9, "#5f3d00", "#ffe9a8"),
            "removed": ("#a4161f", 0.9, "#6e0b12", "#ffc9cd"),
            "unchanged": ("#4b525a", 1.0, "#2b2f33", "#eceef1"),
        },
    },
}

STATE_ALIASES = {"new": "added", "create": "added", "created": "added", "changed": "modified", "updated": "modified",
                 "deleted": "removed", "delete": "removed", "dropped": "removed", "same": "unchanged"}
STATES = ("added", "modified", "removed", "unchanged")
STATE_WORDS = {"added": "ADDED", "modified": "CHANGED", "removed": "REMOVED"}

_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9 ,.%]+\)|[a-zA-Z]{3,20})$")
_FONT = re.compile(r"^[\w ,'\-.]{1,200}$")
_PATH = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9 .,\-eE]{1,600}$")


def esc(s):
    return html.escape(str(s), quote=False)


def attr(s):
    """Text for use inside a double-quoted XML attribute."""
    return html.escape(str(s), quote=True)


def norm_state(state):
    """Accept the PR Lens words (added, modified, removed) and common synonyms (new, changed, deleted)."""
    if state is None:
        return None
    s = str(state).lower()
    return STATE_ALIASES.get(s, s)


def clean_color(value, where):
    if not isinstance(value, str) or not _COLOR.match(value.strip()):
        raise SystemExit(f"{where}: '{value}' is not a colour (use #rrggbb, rgb(), rgba() or a colour name)")
    return value.strip()


def build_theme(name, palette=None):
    """Return a copy of a built-in theme with the brand overrides in `palette` applied.

    palette: flat colour tokens (any key of the theme, for example bg, card, title, glyph), `states` mapping
    a state to {"line", "text", "fill", "stroke_opacity"}, and `group_fill` as a list of three colours.
    """
    if name not in THEMES:
        raise SystemExit(f"unknown theme '{name}'; built in: {', '.join(sorted(THEMES))}")
    theme = copy.deepcopy(THEMES[name])
    for key, value in (palette or {}).items():
        if key == "states":
            for st, spec in value.items():
                st = norm_state(st)
                if st not in theme["states"]:
                    raise SystemExit(f"palette.states: unknown state '{st}'")
                line, op, text, fill = theme["states"][st]
                if isinstance(spec, str):
                    spec = {"line": spec}
                line = clean_color(spec.get("line", line), f"palette.states.{st}.line")
                text = clean_color(spec.get("text", text), f"palette.states.{st}.text")
                fill = clean_color(spec.get("fill", fill), f"palette.states.{st}.fill")
                theme["states"][st] = (line, float(spec.get("stroke_opacity", op)), text, fill)
        elif key == "group_fill":
            if not isinstance(value, list) or not value:
                raise SystemExit("palette.group_fill must be a list of colours")
            theme["group_fill"] = [clean_color(v, "palette.group_fill") for v in value]
        elif key in theme:
            theme[key] = clean_color(value, f"palette.{key}")
        else:
            raise SystemExit(f"palette: unknown token '{key}'; known: {', '.join(sorted(k for k in theme if k != 'states'))}")
    return theme


def fonts(options):
    """(sans, mono) font-family strings, with optional overrides from options.font and options.mono."""
    out = []
    for key, default in (("font", SANS), ("mono", MONO)):
        v = options.get(key)
        if v is None:
            out.append(default)
        elif isinstance(v, str) and _FONT.match(v):
            out.append(html.escape(v, quote=True))
        else:
            raise SystemExit(f"options.{key}: use a plain font-family list such as \"Inter, Arial, sans-serif\"")
    return out


GLYPHS = ("db", "module", "table", "service", "ui", "queue", "file", "bucket", "warehouse", "orchestrator",
          "chart", "cloud", "api", "stream", "transform", "user", "clock")

# first match wins; used only when a node names no glyph and options.auto_glyph is not false
_WORD = r"(?<![a-z0-9])(?:%s)(?![a-z0-9])"      # whole word, where underscores and dots separate words
_INFER = [(glyph_name, re.compile(_WORD % words, re.I)) for glyph_name, words in [
    ("bucket", r"s3|gcs|blob|bucket|data ?lake|lakehouse|landing|adls"),
    ("queue", r"kafka|kinesis|pub ?sub|queue|rabbitmq|sqs|event ?hub"),
    ("orchestrator", r"airflow|dagster|prefect|orchestrat\w*|scheduler|cron"),
    ("chart", r"looker|tableau|power ?bi|metabase|superset|dashboards?|bi"),
    ("api", r"api|graphql|webhook|endpoint"),
    ("module", r"dbt|spark|flink|etl|elt|pipeline"),
    ("warehouse", r"snowflake|bigquery|redshift|databricks|synapse|warehouse|dwh|clickhouse"),
    ("file", r"csv|json|parquet|xlsx?|files?|export"),
]]


def infer_glyph(node):
    text = " ".join(str(node.get(k, "")) for k in ("id", "title", "sub"))
    for name, rx in _INFER:
        if rx.search(text):
            return name
    return None


def clean_path(d, where):
    if not isinstance(d, str) or not _PATH.match(d):
        raise SystemExit(f"{where}: icon must be SVG path data (letters MLHVCSQTAZ, numbers, spaces, commas) in a 24x24 box")
    return d


def glyph(kind, x, y, color, icon=None):
    """Icon inside a 26x26 chip whose top-left corner is (x, y). `icon` is custom path data in a 24x24 box."""
    s = f'stroke="{color}" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    cx, cy = x + 13, y + 13
    if icon:
        return f'<path {s} transform="translate({x + 1},{y + 1})" d="{icon}"/>'
    if kind == "db":
        return (f'<ellipse {s} cx="{cx}" cy="{cy - 4.5}" rx="6.5" ry="2.6"/>'
                f'<path {s} d="M{cx - 6.5},{cy - 4.5} v9 a6.5,2.6 0 0 0 13 0 v-9"/>')
    if kind == "warehouse":
        return (f'<ellipse {s} cx="{cx}" cy="{cy - 5}" rx="6.5" ry="2.4"/>'
                f'<path {s} d="M{cx - 6.5},{cy - 5} v10 a6.5,2.4 0 0 0 13 0 v-10 M{cx - 6.5},{cy} a6.5,2.4 0 0 0 13 0"/>')
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
    if kind == "bucket":
        return (f'<ellipse {s} cx="{cx}" cy="{cy - 4.5}" rx="6.5" ry="2.2"/>'
                f'<path {s} d="M{cx - 6.5},{cy - 4.5} l1.8,10.5 a4.7,1.8 0 0 0 9.4,0 l1.8,-10.5"/>')
    if kind == "orchestrator":
        return (f'<path {s} d="M{cx + 6},{cy - 1} a6,6 0 0 0 -11,-2.5 M{cx - 6},{cy + 1} a6,6 0 0 0 11,2.5 '
                f'M{cx - 6},{cy - 7} v3.5 h3.5 M{cx + 6},{cy + 7} v-3.5 h-3.5"/>')
    if kind == "chart":
        return f'<path {s} d="M{cx - 6},{cy + 6} h12 M{cx - 4},{cy + 6} v-5 M{cx},{cy + 6} v-11 M{cx + 4},{cy + 6} v-8"/>'
    if kind == "cloud":
        return f'<path {s} d="M{cx - 5.5},{cy + 4.5} a3.6,3.6 0 0 1 0.4,-7.2 a5.2,5.2 0 0 1 10,1.6 a2.8,2.8 0 0 1 -0.4,5.6 z"/>'
    if kind == "api":
        return (f'<text x="{cx}" y="{cy + 3.5}" text-anchor="middle" font-size="9.5" font-weight="700" fill="{color}" '
                f'font-family="{MONO}">&lt;/&gt;</text>')
    if kind == "stream":
        return (f'<path {s} d="M{cx - 7},{cy - 4} q3.5,-4 7,0 t7,0 M{cx - 7},{cy + 1} q3.5,-4 7,0 t7,0 '
                f'M{cx - 7},{cy + 6} q3.5,-4 7,0 t7,0"/>')
    if kind == "transform":
        return f'<path {s} d="M{cx - 7},{cy - 4} h4 l5,8 h5 M{cx - 7},{cy + 4} h4 l5,-8 h5 M{cx + 4},{cy - 6} l3,2 l-3,2"/>'
    if kind == "user":
        return (f'<circle {s} cx="{cx}" cy="{cy - 3}" r="2.8"/>'
                f'<path {s} d="M{cx - 6},{cy + 6.5} a6,5 0 0 1 12,0"/>')
    if kind == "clock":
        return f'<circle {s} cx="{cx}" cy="{cy}" r="6.5"/><path {s} d="M{cx},{cy - 3.5} V{cy} h3"/>'
    return ""


def rounded(points, r=8):
    """Orthogonal polyline with rounded corners."""
    d = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        sx, sy = _toward(x1, y1, x0, y0, r)
        ex, ey = _toward(x1, y1, x2, y2, r)
        d.append(f"L{sx:.1f},{sy:.1f} Q{x1:.1f},{y1:.1f} {ex:.1f},{ey:.1f}")
    d.append(f"L{points[-1][0]:.1f},{points[-1][1]:.1f}")
    return " ".join(d)


def _toward(ax, ay, bx, by, r):
    dx, dy = bx - ax, by - ay
    ln = (dx * dx + dy * dy) ** 0.5 or 1
    k = min(r, ln / 2) / ln
    return ax + dx * k, ay + dy * k


def flatten(points, r=8, steps=8):
    """The same rounded polyline as a dense list of points, so a frame can place a packet by distance."""
    out = [points[0]]
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        sx, sy = _toward(x1, y1, x0, y0, r)
        ex, ey = _toward(x1, y1, x2, y2, r)
        out.append((sx, sy))
        for k in range(1, steps):
            t = k / steps
            a, b = (sx + (x1 - sx) * t, sy + (y1 - sy) * t), (x1 + (ex - x1) * t, y1 + (ey - y1) * t)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append((ex, ey))
    out.append(points[-1])
    return out


def point_along(poly, frac):
    """Point at `frac` (0 to 1) of the length of a polyline."""
    lens = [((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5 for p, q in zip(poly, poly[1:])]
    target = max(0.0, min(1.0, frac)) * sum(lens)
    for (p, q), ln in zip(zip(poly, poly[1:]), lens):
        if target <= ln or ln == 0:
            k = target / ln if ln else 0
            return p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k
        target -= ln
    return poly[-1]


def packet(poly, t, dur, t0, t1, fade):
    """Where a travelling packet is at time `t` of a loop `dur` long: (x, y, opacity), or None when hidden.

    Mirrors the SMIL used in the animated SVGs: it waits at the start, moves between fractions t0 and t1 of the
    loop, and fades in and out over `fade`.
    """
    f = (t % dur) / dur
    if f < t0 or f > t1:
        return None
    k = 0 if t1 <= t0 else (f - t0) / (t1 - t0)
    op = min(1.0, (f - t0) / fade if fade else 1.0, (t1 - f) / fade if fade else 1.0)
    x, y = point_along(poly, k)
    return x, y, max(op, 0.0)
