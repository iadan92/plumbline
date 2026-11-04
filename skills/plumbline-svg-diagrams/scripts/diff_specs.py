#!/usr/bin/env python3
"""Compare two versions of a diagram spec and write a spec that shows what changed, as PR Lens does.

Usage: diff_specs.py old.json new.json -o diff.json [--summary]
       diff_specs.py --git REV spec.json -o diff.json      (old = the spec as committed at REV)

Added elements turn green, changed ones amber, removed ones red (dashed, struck through, kept where they were).
Tables also get column-level marks: a new column in green, a removed one struck through, a changed type or key
in amber. The result has options.diff_labels and options.legend on, so cards carry ADDED, CHANGED or REMOVED
chips and a key sits at the bottom right. Render it like any other spec. States the inputs carry are ignored:
the comparison decides them.

Works on lineage, architecture and data-model specs (nodes, edges, groups) and on sequence specs
(participants, messages). Elements match by id; an edge matches by its two ends and columns; a message
without an id matches by sender, receiver, kind and label.
"""
import argparse
import copy
import difflib
import json
import os
import subprocess
import sys

FIELDS = ("title", "sub", "glyph", "icon", "lane", "row", "badge")


def _edge_key(e):
    return (e["from"], e["to"], e.get("from_col"), e.get("to_col"))


def _diff_columns(old, new):
    """New column list carrying a state per column, plus (added, removed, changed) counts."""
    old_by = {c["name"]: c for c in old}
    out, counts = [], [0, 0, 0]
    for c in new:
        c = dict(c)
        prev = old_by.get(c["name"])
        if prev is None:
            c["state"], counts[0] = "added", counts[0] + 1
        elif (prev.get("type"), prev.get("key")) != (c.get("type"), c.get("key")):
            c["state"], counts[2] = "modified", counts[2] + 1
        else:
            c["state"] = "unchanged"
        out.append(c)
    new_names = [c["name"] for c in out]
    for i, c in enumerate(old):
        if c["name"] in new_names:
            continue
        c = dict(c, state="removed")
        counts[1] += 1
        at = 0
        for p in reversed(old[:i]):
            if p["name"] in new_names:
                at = new_names.index(p["name"]) + 1
                break
        out.insert(at, c)
        new_names = [x["name"] for x in out]
    return out, counts


def _free_row(taken, lane, row):
    while (lane, row) in taken:
        row += 0.5
    return row


def diff_flow(old, new):
    out = copy.deepcopy(new)
    stats = {"nodes": [0, 0, 0], "edges": [0, 0, 0], "details": []}     # added, removed, changed
    old_nodes = {n["id"]: n for n in old.get("nodes", [])}
    new_ids = {n["id"] for n in new.get("nodes", [])}
    for n in out["nodes"]:
        prev = old_nodes.get(n["id"])
        if prev is None:
            n["state"] = "added"
            stats["nodes"][0] += 1
            stats["details"].append(f"added node {n['id']}")
            continue
        why = [f for f in FIELDS if f not in ("lane", "row") and prev.get(f) != n.get(f)]
        if n.get("columns") is not None or prev.get("columns") is not None:
            n["columns"], (a, r, c) = _diff_columns(prev.get("columns") or [], n.get("columns") or [])
            if a or r or c:
                why.append("columns")
                parts = [f"+{a}" if a else "", f"-{r}" if r else "", f"~{c}" if c else ""]
                if not n.get("sub"):
                    n["sub"] = f"{len([x for x in n['columns'] if x['state'] != 'removed'])} columns, " + " ".join(p for p in parts if p)
                stats["details"].append(f"changed {n['id']}: columns {' '.join(p for p in parts if p)}")
        if why:
            n["state"] = "modified"
            stats["nodes"][2] += 1
            if "columns" not in why:
                stats["details"].append(f"changed {n['id']}: {', '.join(why)}")
        else:
            n["state"] = "unchanged"
    lanes = list(out.get("lanes") or [])
    lane_ids = {l["id"] for l in lanes}
    taken = {(n.get("lane"), n.get("row")) for n in out["nodes"] if n.get("lane") is not None}
    for nid, prev in old_nodes.items():
        if nid in new_ids:
            continue
        n = dict(copy.deepcopy(prev), state="removed")
        for c in n.get("columns") or []:
            c["state"] = "removed"
        if n.get("lane") is not None and n.get("row") is not None:
            if n["lane"] not in lane_ids:
                lanes.append(next((l for l in old.get("lanes", []) if l["id"] == n["lane"]), {"id": n["lane"], "label": n["lane"]}))
                lane_ids.add(n["lane"])
            n["row"] = _free_row(taken, n["lane"], n["row"])
            taken.add((n["lane"], n["row"]))
        out["nodes"].append(n)
        stats["nodes"][1] += 1
        stats["details"].append(f"removed node {nid}")
    if lanes:
        out["lanes"] = lanes

    old_edges = {_edge_key(e): e for e in old.get("edges", [])}
    seen = set()
    for e in out.get("edges", []):
        k = _edge_key(e)
        seen.add(k)
        prev = old_edges.get(k)
        e.pop("state", None)
        if prev is None:
            e["state"] = "added"
            stats["edges"][0] += 1
            stats["details"].append(f"added edge {e['from']} -> {e['to']}")
        elif (prev.get("label"), prev.get("style")) != (e.get("label"), e.get("style")):
            e["state"] = "modified"
            stats["edges"][2] += 1
            stats["details"].append(f"changed edge {e['from']} -> {e['to']}: label or style")
        else:
            e["state"] = "unchanged"
    for k, e in old_edges.items():
        if k not in seen:
            out.setdefault("edges", []).append(dict(copy.deepcopy(e), state="removed"))
            stats["edges"][1] += 1
            stats["details"].append(f"removed edge {e['from']} -> {e['to']}")

    old_groups = {g["id"]: g for g in old.get("groups", [])}
    groups = out.get("groups", [])
    for g in groups:
        prev = old_groups.get(g["id"])
        g["state"] = "added" if prev is None else (
            "modified" if (prev.get("title"), sorted(prev["members"])) != (g.get("title"), sorted(g["members"])) else "unchanged")
    for gid, g in old_groups.items():
        if gid not in {x["id"] for x in groups}:
            members = [m for m in g["members"] if m in {n["id"] for n in out["nodes"]}]
            if members:
                groups.append(dict(copy.deepcopy(g), members=members, state="removed", style="dashed"))
    if groups:
        out["groups"] = groups
    return out, stats


def _msg_key(m):
    return m.get("id") or f"{m.get('from')}>{m.get('to')}:{m.get('kind', 'sync')}:{m.get('label', '')}"


def diff_sequence(old, new):
    out = copy.deepcopy(new)
    stats = {"nodes": [0, 0, 0], "edges": [0, 0, 0], "details": []}
    old_p = {p["id"]: p for p in old.get("participants", [])}
    new_p = {p["id"] for p in out["participants"]}
    for p in out["participants"]:
        prev = old_p.get(p["id"])
        if prev is None:
            p["state"] = "added"
            stats["nodes"][0] += 1
            stats["details"].append(f"added participant {p['id']}")
        elif any(prev.get(f) != p.get(f) for f in ("title", "sub", "glyph")):
            p["state"] = "modified"
            stats["nodes"][2] += 1
            stats["details"].append(f"changed participant {p['id']}")
        else:
            p["state"] = "unchanged"
    for pid, p in old_p.items():
        if pid not in new_p:
            out["participants"].append(dict(copy.deepcopy(p), state="removed"))
            stats["nodes"][1] += 1
            stats["details"].append(f"removed participant {pid}")

    def phases_of(spec):
        return spec.get("phases") or [{"id": "main", "messages": spec.get("messages", [])}]

    old_ph = {ph["id"]: ph for ph in phases_of(old)}
    new_phases = phases_of(out)
    for ph in new_phases:
        prev = old_ph.get(ph["id"], {"messages": []})
        a, b = prev.get("messages", []), ph.get("messages", [])
        ops = difflib.SequenceMatcher(None, [_msg_key(m) for m in a], [_msg_key(m) for m in b], autojunk=False).get_opcodes()
        merged = []
        for tag, i1, i2, j1, j2 in ops:
            if tag == "equal":
                for m_old, m_new in zip(a[i1:i2], b[j1:j2]):
                    m = dict(m_new)
                    changed = any(m_old.get(f) != m_new.get(f) for f in ("from", "to", "label", "reply", "repeat", "kind"))
                    m["state"] = "modified" if changed else "unchanged"
                    if changed:
                        stats["edges"][2] += 1
                        stats["details"].append(f"changed message {_msg_key(m_new)}")
                    merged.append(m)
            else:
                gone, fresh = list(a[i1:i2]), list(b[j1:j2])
                # a replaced message between the same two participants with the same kind is a changed message, not a swap
                for m_old, m_new in zip(gone[:], fresh[:]):
                    if tag == "replace" and (m_old.get("from"), m_old.get("to"), m_old.get("kind", "sync")) == \
                            (m_new.get("from"), m_new.get("to"), m_new.get("kind", "sync")):
                        merged.append(dict(m_new, state="modified"))
                        stats["edges"][2] += 1
                        stats["details"].append(f"changed message {_msg_key(m_old)} -> {_msg_key(m_new)}")
                        gone.remove(m_old)
                        fresh.remove(m_new)
                    else:
                        break
                for m_old in gone:
                    merged.append(dict(m_old, state="removed"))
                    stats["edges"][1] += 1
                    stats["details"].append(f"removed message {_msg_key(m_old)}")
                for m_new in fresh:
                    merged.append(dict(m_new, state="added"))
                    stats["edges"][0] += 1
                    stats["details"].append(f"added message {_msg_key(m_new)}")
        ph["messages"] = merged
        ph.pop("state", None)
    if "phases" in out:
        out["phases"] = new_phases
        have = {ph["id"] for ph in new_phases}
        for pid, ph in old_ph.items():
            if pid not in have:
                gone = dict(copy.deepcopy(ph), messages=[dict(m, state="removed") for m in ph.get("messages", [])])
                out["phases"].append(gone)
                stats["details"].append(f"removed phase {pid}")
    else:
        out["messages"] = new_phases[0]["messages"]
    return out, stats


def diff(old, new):
    kind = lambda s: "sequence" if s.get("type") == "sequence" else "flow"     # noqa: E731
    if kind(old) != kind(new):
        raise SystemExit("cannot compare a sequence spec with a lineage, architecture or data-model spec")
    out, stats = (diff_sequence if kind(new) == "sequence" else diff_flow)(old, new)
    opts = out.setdefault("options", {})
    opts["diff_labels"] = True
    opts["legend"] = True
    return out, stats


def summary(stats):
    n, e = stats["nodes"], stats["edges"]
    head = (f"nodes: {n[0]} added, {n[2]} changed, {n[1]} removed; "
            f"connections: {e[0]} added, {e[2]} changed, {e[1]} removed")
    return "\n".join([head] + [f"- {d}" for d in stats["details"]]) if stats["details"] else head + "\nNo differences."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="old.json new.json, or with --git just the spec path")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--git", metavar="REV", help="take the old version from this git revision (for example HEAD~1 or main)")
    ap.add_argument("--summary", action="store_true", help="print a list of the changes")
    args = ap.parse_args()
    if args.git:
        if len(args.files) != 1:
            ap.error("with --git give one spec path")
        path = os.path.abspath(args.files[0])
        proc = subprocess.run(["git", "show", f"{args.git}:./{os.path.basename(path)}"], cwd=os.path.dirname(path),
                              capture_output=True, text=True)
        if proc.returncode:
            raise SystemExit(f"git could not read {os.path.basename(path)} at {args.git}: {proc.stderr.strip()}")
        old, new = json.loads(proc.stdout), json.load(open(path))
    else:
        if len(args.files) != 2:
            ap.error("give old.json and new.json")
        old, new = (json.load(open(f)) for f in args.files)
    out, stats = diff(old, new)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {args.out}")
    if args.summary:
        print(summary(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
