#!/usr/bin/env python3
"""Turn a dbt manifest.json into a lineage spec for render_diagram.py.

Usage: import_dbt.py target/manifest.json -o spec.json [--select "+fct_orders"] [--exclude "tag:legacy"]
                     [--columns 8] [--title "Orders lineage"] [--max-nodes 60]

Run `dbt compile` or `dbt docs generate` first so target/manifest.json is current. Sources, seeds, snapshots,
models and exposures become nodes; the references between them become edges. Nodes land in lanes by layer
(sources, staging, intermediate, marts, exposures; guessed from the folder and the name prefix), and rows are
left to the automatic layout, so the output renders as it is. Edit the spec afterwards to pin a lane or row.

--select and --exclude use dbt's graph syntax: a model name, `+name` (with all its ancestors), `name+`
(descendants), `2+name+1` (two ancestor levels, one descendant level), `tag:finance`, `path:models/marts`,
`source:shop`, `resource_type:seed`, a name with `*`. Space means union, comma means intersection.
--columns N lists up to N documented columns per model, with PK from unique plus not_null tests and FK from
relationships tests.
"""
import argparse
import fnmatch
import json
import re
import sys

LAYERS = [("sources", "sources", "sources and seeds"), ("staging", "staging", "cleaned 1:1 with sources"), ("intermediate", "intermediate", "joins and logic"),
          ("marts", "marts", "business facts and dimensions"), ("exposures", "exposures", "dashboards and apps")]
KEYWORDS = [("staging", re.compile(r"(^|[/_.])(staging|stg)($|[/_.])", re.I)),
            ("intermediate", re.compile(r"(^|[/_.])(intermediate|int)($|[/_.])", re.I)),
            ("marts", re.compile(r"(^|[/_.])(marts?|core|reporting|fct|fact|dim|agg|rpt)($|[/_.])", re.I))]
EXPOSURE_GLYPH = {"dashboard": "chart", "analysis": "chart", "application": "ui", "notebook": "file", "ml": "transform"}


def layer_of(node):
    rt = node["resource_type"]
    if rt == "source":
        return "sources"
    if rt == "seed":
        return "sources"
    if rt == "exposure":
        return "exposures"
    path = node.get("original_file_path") or node.get("path") or ""
    for layer, rx in KEYWORDS:
        if rx.search(path) or rx.search(node["name"]):
            return layer
    return None


class Project:
    def __init__(self, manifest):
        self.items = {}
        for uid, n in manifest.get("nodes", {}).items():
            if n.get("resource_type") in ("model", "seed", "snapshot") and n.get("config", {}).get("enabled", True):
                self.items[uid] = n
        for uid, n in manifest.get("sources", {}).items():
            self.items[uid] = n
        for uid, n in manifest.get("exposures", {}).items():
            self.items[uid] = n
        self.tests = [n for n in manifest.get("nodes", {}).values() if n.get("resource_type") == "test"]
        self.parents = {u: [d for d in n.get("depends_on", {}).get("nodes", []) if d in self.items] for u, n in self.items.items()}
        self.children = {u: [] for u in self.items}
        for u, ps in self.parents.items():
            for p in ps:
                self.children[p].append(u)

    def walk(self, start, edges, depth):
        seen, frontier, level = set(start), set(start), 0
        while frontier and (depth is None or level < depth):
            frontier = {n for u in frontier for n in edges[u]} - seen
            seen |= frontier
            level += 1
        return seen

    def base(self, token):
        kind, _, value = token.partition(":") if ":" in token else ("name", "", token)
        out = set()
        for uid, n in self.items.items():
            tags = set(n.get("tags", []) + n.get("config", {}).get("tags", []))
            path = n.get("original_file_path") or n.get("path") or ""
            label = n["name"] if n["resource_type"] != "source" else f"{n.get('source_name')}.{n['name']}"
            if kind == "tag":
                hit = value in tags
            elif kind == "path":
                hit = path.startswith(value.rstrip("/"))
            elif kind == "source":
                hit = n["resource_type"] == "source" and fnmatch.fnmatch(label, value if "." in value else value + ".*")
            elif kind == "resource_type":
                hit = n["resource_type"] == value
            else:
                hit = fnmatch.fnmatch(n["name"], value) or fnmatch.fnmatch(label, value) or uid == value
            if hit:
                out.add(uid)
        return out

    def select(self, expr):
        chosen = set()
        for union_part in expr.split():
            part = None
            for token in union_part.split(","):
                m = re.match(r"^(?:(\d*)(\+))?(.*?)(?:(\+)(\d*))?$", token)
                up, plus_up, name, plus_down, down = m.groups()
                found = self.base(name)
                grown = set(found)
                if plus_up:
                    grown |= self.walk(found, self.parents, int(up) if up else None)
                if plus_down:
                    grown |= self.walk(found, self.children, int(down) if down else None)
                part = grown if part is None else part & grown
            chosen |= part or set()
        return chosen


def column_marks(project, uid):
    """PK and FK marks for a model, read from its unique, not_null and relationships tests."""
    marks, seen = {}, {}
    for t in project.tests:
        if uid not in t.get("depends_on", {}).get("nodes", []):
            continue
        col, name = t.get("column_name"), t.get("test_metadata", {}).get("name")
        if not col:
            continue
        seen.setdefault(col, set()).add(name)
        if name == "relationships":
            marks[col] = "FK"
    for col, names in seen.items():
        if {"unique", "not_null"} <= names:
            marks[col] = "PK,FK" if marks.get(col) == "FK" else "PK"
    return marks


def build(manifest, select=None, exclude=None, columns=0, title=None):
    project = Project(manifest)
    keep = set(project.items)
    if select:
        keep &= project.select(select)
    if exclude:
        keep -= project.select(exclude)
    nodes, ids, used_layers = [], {}, set()
    for uid in sorted(keep):
        n = project.items[uid]
        layer = layer_of(n)
        rt = n["resource_type"]
        nid = re.sub(r"[^A-Za-z0-9_]", "_", n["name"] if rt != "source" else f"{n.get('source_name')}_{n['name']}")
        while nid in ids.values():
            nid += "_"
        ids[uid] = nid
        node = {"id": nid, "title": n["name"] if rt != "source" else f"{n.get('source_name')}.{n['name']}"}
        if rt == "source":
            node.update(sub=n.get("schema") or "source", glyph="db")
        elif rt == "seed":
            node.update(sub="seed", glyph="file")
        elif rt == "exposure":
            node.update(sub=n.get("type", "exposure"), glyph=EXPOSURE_GLYPH.get(n.get("type"), "chart"))
        else:
            mat = n.get("config", {}).get("materialized", "")
            node.update(sub=" · ".join(x for x in (mat, n.get("schema")) if x), glyph="table" if layer == "marts" else "module")
        if layer:
            node["lane"] = layer
            used_layers.add(layer)
        cols = n.get("columns") or {}
        if columns and cols and rt in ("model", "seed", "snapshot", "source"):
            marks = column_marks(project, uid)
            listed = sorted(cols.values(), key=lambda c: (c["name"] not in marks, 0))[:columns]
            node["columns"] = [{"name": c["name"], "type": c.get("data_type") or "", "key": marks.get(c["name"])} for c in listed]
            node["sub"] = node.get("sub") or f"{len(cols)} columns"
        nodes.append(node)
    edges = [{"from": ids[p], "to": ids[u]} for u in sorted(keep) for p in project.parents[u] if p in keep]
    lanes = [{"id": lid, "label": label, "sub": sub} for lid, label, sub in LAYERS if lid in used_layers]
    spec = {"title": title or "dbt lineage", "options": {"fit_width": 1700}, "lanes": lanes, "nodes": nodes, "edges": edges}
    counts = {lid: sum(1 for n in nodes if n.get("lane") == lid) for lid, _, _ in LAYERS if lid in used_layers}
    counts["unclassified"] = sum(1 for n in nodes if "lane" not in n)
    return spec, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--select")
    ap.add_argument("--exclude")
    ap.add_argument("--columns", type=int, default=0)
    ap.add_argument("--title")
    ap.add_argument("--max-nodes", type=int, default=60, help="refuse larger diagrams unless --force (default 60)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    manifest = json.load(open(args.manifest))
    spec, counts = build(manifest, args.select, args.exclude, args.columns, args.title)
    detail = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
    if not spec["nodes"]:
        raise SystemExit("nothing selected; check --select against the model names in the manifest")
    if len(spec["nodes"]) > args.max_nodes and not args.force:
        raise SystemExit(f"{len(spec['nodes'])} nodes ({detail}) is too many for one readable diagram. Narrow it with "
                         "--select (for example \"+fct_orders\" or \"path:models/marts/finance\") or pass --force.")
    with open(args.out, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"wrote {args.out}: {len(spec['nodes'])} nodes, {len(spec['edges'])} edges ({detail})")
    if counts.get("unclassified"):
        print(f"{counts['unclassified']} node(s) matched no layer; they are placed by the direction of their edges.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
