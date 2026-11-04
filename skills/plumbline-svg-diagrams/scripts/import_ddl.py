#!/usr/bin/env python3
"""Turn SQL DDL (CREATE TABLE and ALTER TABLE statements) into a data-model spec for render_diagram.py.

Usage: import_ddl.py schema.sql -o spec.json [--tables a,b,c] [--max-columns 12] [--title "Billing schema"]

Reads columns, types, primary keys and foreign keys, inline or as table or ALTER TABLE constraints, from
Postgres, MySQL, Snowflake, BigQuery, SQL Server and ANSI style DDL (quoted names, schema prefixes and
IF NOT EXISTS are handled; views, indexes and other statements are skipped). A star or snowflake shape (one
table holding the foreign keys, every other table a dimension) becomes `"layout": "star"`; anything else is
placed by the direction of the foreign keys, so referenced tables sit to the right of the tables that
point at them. Pipe `pg_dump --schema-only` or `SHOW CREATE TABLE` output straight in.
"""
import argparse
import json
import re
import sys

STOP = {"NOT", "NULL", "DEFAULT", "PRIMARY", "REFERENCES", "UNIQUE", "CHECK", "CONSTRAINT", "GENERATED", "AUTO_INCREMENT",
        "AUTOINCREMENT", "COLLATE", "COMMENT", "IDENTITY", "ON", "ENCODE", "DISTKEY", "SORTKEY", "OPTIONS", "AS"}
TABLE_ITEMS = ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "EXCLUDE", "LIKE", "PERIOD", "FULLTEXT", "SPATIAL")


def strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def split_top(text, sep):
    """Split on `sep` outside parentheses and quotes."""
    parts, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            cur.append(ch)
        elif ch == "[" and sep == ",":
            quote = "]"
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def is_table_item(item):
    """A constraint or index line inside CREATE TABLE, as opposed to a column definition."""
    first = item.split(None, 1)[0].upper()
    if first in TABLE_ITEMS:
        return True
    return first in ("KEY", "INDEX") and bool(re.match(r"\w+\s+(?:[\w$\"`]+\s*)?\(", item))


def unquote(name):
    return name.strip().strip('"`[]')


def table_name(raw):
    """Last part of a possibly quoted and schema-qualified name."""
    parts = re.findall(r'"[^"]+"|`[^`]+`|\[[^\]]+\]|[\w$]+', raw)
    return unquote(parts[-1]) if parts else raw.strip()


def name_list(text):
    return [unquote(c) for c in split_top(text, ",")]


SHORT = [("timestamp with time zone", "timestamptz"), ("timestamp without time zone", "timestamp"), ("time with time zone", "timetz"),
         ("time without time zone", "time"), ("double precision", "double"), ("character varying", "varchar"), ("character", "char")]


def short_type(text):
    t = re.sub(r"\s+", " ", text).lower().replace(" (", "(")
    for long, short in SHORT:
        t = t.replace(long, short)
    return t


def parse_column(item):
    m = re.match(r'\s*("[^"]+"|`[^`]+`|\[[^\]]+\]|[\w$]+)\s*(.*)$', item, re.S)
    name, rest = unquote(m.group(1)), m.group(2)
    type_parts, i = [], 0
    tokens = re.findall(r"[\w$]+(?:\([^)]*\))?(?:\[\])*|\([^)]*\)|\S", rest)
    for tok in tokens:
        if tok.upper().split("(")[0] in STOP:
            break
        type_parts.append(tok)
    col = {"name": name, "type": short_type(" ".join(type_parts))}
    up = rest.upper()
    pk = bool(re.search(r"\bPRIMARY\s+KEY\b", up))
    ref = re.search(r"\bREFERENCES\s+((?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))*)\s*(?:\(([^)]*)\))?", rest, re.I)
    return col, pk, ref


def parse(sql):
    tables, order = {}, []
    stmts = split_top(strip_comments(sql), ";")
    for st in stmts:
        m = re.match(r"\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:GLOBAL\s+|LOCAL\s+)?(?:TEMP|TEMPORARY)\s+|UNLOGGED\s+|TRANSIENT\s+|EXTERNAL\s+)?TABLE\s+"
                     r"(?:IF\s+NOT\s+EXISTS\s+)?((?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))*)\s*\(", st, re.I)
        if m:
            name = table_name(m.group(1))
            body = st[m.end():st.rindex(")")]
            t = {"id": name, "columns": [], "pk": [], "fks": []}
            for item in split_top(body, ","):
                if is_table_item(item):
                    pk = re.search(r"PRIMARY\s+KEY\s*(?:\w+\s*)?\(([^)]*)\)", item, re.I)
                    fk = re.search(r"FOREIGN\s+KEY\s*(?:\w+\s*)?\(([^)]*)\)\s*REFERENCES\s+((?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))*)\s*(?:\(([^)]*)\))?", item, re.I)
                    if pk:
                        t["pk"] += name_list(pk.group(1))
                    if fk:
                        t["fks"].append((name_list(fk.group(1)), table_name(fk.group(2)), name_list(fk.group(3)) if fk.group(3) else []))
                    continue
                col, pk, ref = parse_column(item)
                t["columns"].append(col)
                if pk:
                    t["pk"].append(col["name"])
                if ref:
                    t["fks"].append(([col["name"]], table_name(ref.group(1)), name_list(ref.group(2)) if ref.group(2) else []))
            tables[name] = t
            order.append(name)
            continue
        m = re.match(r"\s*ALTER\s+TABLE\s+(?:ONLY\s+|IF\s+EXISTS\s+)*((?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))*)\s+(.*)$", st, re.I | re.S)
        if m and table_name(m.group(1)) in tables:
            t = tables[table_name(m.group(1))]
            for pk in re.finditer(r"PRIMARY\s+KEY\s*\(([^)]*)\)", m.group(2), re.I):
                t["pk"] += name_list(pk.group(1))
            for fk in re.finditer(r"FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+((?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))*)\s*(?:\(([^)]*)\))?", m.group(2), re.I):
                t["fks"].append((name_list(fk.group(1)), table_name(fk.group(2)), name_list(fk.group(3)) if fk.group(3) else []))
    return tables, order


def build(sql, only=None, max_columns=12, title=None):
    tables, order = parse(sql)
    if only:
        order = [t for t in order if t in only]
    keep = set(order)
    edges, fk_cols = [], {t: set() for t in order}
    for name in order:
        for cols, target, refcols in tables[name]["fks"]:
            if target not in keep:
                continue
            if not refcols:
                refcols = tables[target]["pk"][:len(cols)] or cols
            for c, rc in zip(cols, refcols):
                edges.append({"from": name, "to": target, "label": "FK", "from_col": c, "to_col": rc})
                fk_cols[name].add(c)
    nodes = []
    for name in order:
        t = tables[name]
        cols = []
        for c in t["columns"]:
            is_pk, is_fk = c["name"] in t["pk"], c["name"] in fk_cols[name]
            cols.append({"name": c["name"], "type": c["type"], "key": "PK,FK" if is_pk and is_fk else "PK" if is_pk else "FK" if is_fk else None})
        if len(cols) > max_columns:
            keyed = [c for c in cols if c["key"]]
            rest = [c for c in cols if not c["key"]][:max(max_columns - len(keyed), 0)]
            cols = [c for c in cols if c in keyed or c in rest]
        nodes.append({"id": name, "title": name, "columns": cols})
    out = {}
    names = {n["id"] for n in nodes}
    for e in edges:   # the referenced column must be on the card, or the line cannot land on its row
        target = next(n for n in nodes if n["id"] == e["to"])
        if e["to_col"] not in [c["name"] for c in target["columns"]]:
            e["to_col"] = None
    for e in edges:
        for k in ("from_col", "to_col"):
            if e[k] is None:
                del e[k]
    spec = {"title": title or "Data model", "options": {"fit_width": 1700}, "nodes": nodes, "edges": edges}
    out_deg = {n: 0 for n in names}
    adj = {n: set() for n in names}
    for e in edges:
        out_deg[e["from"]] += 1
        adj[e["from"]].add(e["to"])
        adj[e["to"]].add(e["from"])
    centre = max(names, key=lambda n: (out_deg[n], len(adj[n]))) if names else None
    dist, queue = ({centre: 0}, [centre]) if names else ({}, [])
    while queue:
        cur = queue.pop(0)
        for nb in sorted(adj[cur]):
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                queue.append(nb)
    pairs = {(e["from"], e["to"]) for e in edges}
    # a star or snowflake: connected, a tree, and every foreign key points away from the centre
    if names and len(dist) == len(names) and out_deg[centre] >= 2 and len(pairs) == len(names) - 1 \
            and all(dist[b] == dist[a] + 1 for a, b in pairs) and len(names) <= 9:
        spec["layout"] = "star"
        spec["center"] = centre
        spec["box_title"] = spec["title"]
    return spec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sql", help="a .sql file, or - for standard input")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--tables", help="comma separated table names to keep")
    ap.add_argument("--max-columns", type=int, default=12)
    ap.add_argument("--title")
    args = ap.parse_args()
    text = sys.stdin.read() if args.sql == "-" else open(args.sql).read()
    spec = build(text, set(args.tables.split(",")) if args.tables else None, args.max_columns, args.title)
    if not spec["nodes"]:
        raise SystemExit("no CREATE TABLE statements found")
    with open(args.out, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"wrote {args.out}: {len(spec['nodes'])} tables, {len(spec['edges'])} foreign key columns"
          + (f", star layout around {spec['center']}" if spec.get("layout") == "star" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
