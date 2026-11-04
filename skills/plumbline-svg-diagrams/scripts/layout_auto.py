"""Automatic lane and row placement for nodes that the spec leaves unplaced.

Direct instructions win: a node with `lane` keeps that lane, a node with `row` keeps that row, and the nodes
that name neither are placed around them. Lanes come from the direction of the edges (a node sits one lane
right of its furthest-left input, a source sits just left of its first consumer), and rows from the rows of
a node's inputs, so a chain stays on one row and its line stays straight.

auto_layout(spec, warnings) fills in `lane` and `row` on the nodes, adds `lanes` when the spec has none, and
returns the ids it placed.
"""
import math


def needs_layout(spec):
    return any(n.get("lane") is None or n.get("row") is None for n in spec["nodes"])


def _dag(ids, edges, warnings):
    """Edges without the ones that close a cycle, so every node has a rank."""
    succs = {i: [] for i in ids}
    for a, b in edges:
        if a != b and b not in succs[a]:
            succs[a].append(b)
    state, back = {}, set()

    def visit(n):
        state[n] = 1
        for m in succs[n]:
            if state.get(m) == 1:
                back.add((n, m))
            elif m not in state:
                visit(m)
        state[n] = 2

    for i in ids:
        if i not in state:
            visit(i)
    for a, b in sorted(back):
        warnings.append(f"cycle: edge {a}->{b} is ignored when placing nodes (it still gets drawn)")
    preds = {i: [] for i in ids}
    for a in ids:
        for b in succs[a]:
            if (a, b) not in back:
                preds[b].append(a)
    order, seen = [], set()

    def topo(n):
        seen.add(n)
        for p in preds[n]:
            if p not in seen:
                topo(p)
        order.append(n)

    for i in ids:
        if i not in seen:
            topo(i)
    kept = {i: [m for m in succs[i] if (i, m) not in back] for i in ids}
    return order, preds, kept


def _nearest_free(want, used, ok=None):
    """Free row closest to `want`; `ok` can veto rows (a line would run through a card there)."""
    base = int(math.floor(want + 0.5))
    for strict in ((True, False) if ok else (False,)):
        for off in range(0, 400):
            for cand in ((base,) if off == 0 else (base + off, base - off)):
                if cand >= 0 and cand not in used and (not strict or ok(cand)):
                    return cand
    return len(used)


def _cost(edges, lane, row):
    """Total vertical run of the edges plus a penalty per crossing between the same pair of lanes."""
    total = sum(abs(row[a] - row[b]) for a, b in edges)
    by_pair = {}
    for a, b in edges:
        if lane[a] != lane[b]:
            by_pair.setdefault((lane[a], lane[b]), []).append((row[a], row[b]))
    for pairs in by_pair.values():
        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                if (pairs[i][0] - pairs[j][0]) * (pairs[i][1] - pairs[j][1]) < 0:
                    total += 3
    return total


def auto_layout(spec, warnings):
    nodes = spec["nodes"]
    by_id = {n["id"]: n for n in nodes}
    ids = [n["id"] for n in nodes]
    pos = {i: k for k, i in enumerate(ids)}
    edges = [(e["from"], e["to"]) for e in spec.get("edges", []) if e["from"] in by_id and e["to"] in by_id]
    order, preds, succs = _dag(ids, edges, warnings)

    given = [dict(l) for l in spec["lanes"]] if spec.get("lanes") else None
    lane_pos = {l["id"]: k for k, l in enumerate(given)} if given else {}
    pinned_lane = {i: lane_pos[n["lane"]] for i, n in by_id.items() if n.get("lane") is not None and given}
    pinned_row = {i: n["row"] for i, n in by_id.items() if n.get("row") is not None}
    placed = [i for i in ids if i not in pinned_lane or i not in pinned_row]

    # lanes: one right of the furthest-left input, then sources slide right up to their first consumer
    layered = given is None and all(n.get("layer") for n in nodes)
    if layered:
        # every node names its layer: one lane per layer, ordered by where the layer's nodes first appear in the flow
        first = {}
        rank = {}
        for n in order:
            rank[n] = max([rank[p] + 1 for p in preds[n]] or [0])
        for n in ids:
            layer = by_id[n]["layer"]
            first[layer] = min(first.get(layer, rank[n]), rank[n])
        names = sorted(first, key=lambda l: (first[l], [by_id[i]["layer"] for i in ids].index(l)))
        given = [{"id": f"layer-{k}", "label": name} for k, name in enumerate(names)]
        lane_pos = {name: k for k, name in enumerate(names)}
        pinned_lane = {i: lane_pos[by_id[i]["layer"]] for i in ids}
    idx = {}
    for n in order:
        idx[n] = pinned_lane[n] if n in pinned_lane else max([idx[p] + 1 for p in preds[n]] or [0])
    for n in ids:
        if n not in pinned_lane and not preds[n] and succs[n]:
            idx[n] = max(idx[n], min(idx[s] for s in succs[n]) - 1)
    if not given:
        used = sorted(set(idx.values()))
        remap = {old: new for new, old in enumerate(used)}
        idx = {n: remap[k] for n, k in idx.items()}
    count = max(idx.values()) + 1
    if given is None:
        labels = {}
        for n in nodes:
            if n.get("layer"):
                labels.setdefault(idx[n["id"]], {}).setdefault(n["layer"], 0)
                labels[idx[n["id"]]][n["layer"]] += 1
        lanes = [{"id": f"stage{k + 1}", "label": max(labels[k], key=labels[k].get) if k in labels else f"stage {k + 1}"}
                 for k in range(count)]
    else:
        lanes = given
        if count > len(lanes):
            warnings.append(f"{count - len(lanes)} lane(s) added after '{lanes[-1]['id']}' because nodes flow further right than the lanes given")
            lanes += [{"id": f"stage{k + 1}", "label": f"stage {k + 1}"} for k in range(len(lanes), count)]
    lane_of = {n: lanes[k]["id"] for n, k in idx.items()}
    if layered:
        spec["lanes"] = lanes
        for n in nodes:
            n["lane"] = lane_of[n["id"]]

    # rows: each lane in turn, a node near the mean row of its inputs; sources then follow their consumers
    in_lane = [[i for i in ids if idx[i] == k] for k in range(len(lanes))]
    row = {i: pinned_row[i] for i in pinned_row}

    def clear(i, k, r):
        """True when a row-`r` card for node i in lane k blocks no line, and no line of i runs through a card."""
        for a, b in edges:
            if idx[a] < k < idx[b] and a in row and row[a] == r and a != i:
                return False             # a line from a lane further left runs straight across lane k on row r
        for b in succs[i]:
            for m in range(k + 1, idx[b]):
                if any(idx[j] == m and row.get(j) == r for j in ids if j != i):
                    return False         # i's own line would run through a card in a lane between
        return True

    def place_lane(k, members, neighbours):
        taken = {row[i] for i in in_lane[k] if i in row and i not in members}
        want = {}
        for i in members:
            rs = [row[m] for m in neighbours[i] if m in row]
            want[i] = sum(rs) / len(rs) if rs else None
        later = max([w for w in want.values() if w is not None] + [-1])
        for i in sorted(members, key=lambda m: (want[m] is None, want[m] if want[m] is not None else 0, pos[m])):
            if want[i] is None:
                later += 1
                want[i] = later
            row[i] = _nearest_free(want[i], taken, lambda r, i=i: clear(i, k, r))
            taken.add(row[i])

    best, best_cost = None, None
    for sweep in range(4):
        for k in (range(len(lanes)) if sweep % 2 == 0 else reversed(range(len(lanes)))):
            if sweep % 2 == 0:
                members = [i for i in in_lane[k] if i not in pinned_row and (sweep == 0 or preds[i])]
                place_lane(k, members, preds)
            else:
                members = [i for i in in_lane[k] if i not in pinned_row and not preds[i] and succs[i]]
                if members:
                    place_lane(k, members, succs)
        cost = _cost(edges, idx, row) if all(i in row for i in ids) else None
        if cost is not None and (best_cost is None or cost < best_cost):
            best, best_cost = dict(row), cost
    row = best if best is not None else row
    for n in nodes:
        if n.get("lane") is None or not given:
            n["lane"] = lane_of[n["id"]]
        if n.get("row") is None:
            n["row"] = row[n["id"]]
    spec["lanes"] = lanes
    return placed
