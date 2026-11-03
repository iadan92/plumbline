---
name: plumbline
description: >-
  Draw clean, hand-laid SVG diagrams for data work in a PR Lens look: data lineage (raw to staging
  to marts), pipeline data flow including animated pipeline SVGs, architecture diagrams with
  nested boxes, and data models (ERDs, true star and snowflake schemas with vertical column lists
  and PK/FK lines). Use this whenever the user asks to draw, diagram, visualize or map a pipeline,
  dbt lineage or DAG, warehouse layers, data model, ERD, star or snowflake schema, fact and
  dimension tables, or system architecture, including redoing or fixing an existing diagram,
  adding animation or dark mode, or when PR Lens output is tangled, staggered, crossing or too
  wide. Use it before hand-writing any data-diagram SVG, and prefer it over Mermaid or PlantUML
  when layout or line routing matters. For a diagram of a code change or pull request, PR Lens
  itself may fit better.
---

# SVG data diagrams

Paths in this file (`scripts/`, `assets/`, `references/`) are relative to the directory that contains this SKILL.md. The agent runs in the user's project, so call the scripts by absolute path, for example `python3 <skill-dir>/scripts/render_diagram.py spec.json out.svg`. Requires Python 3.8 or newer and no packages.

Produce data diagrams where every node sits exactly where you put it, and lines are short, straight and predictable. The bundled renderer draws in the PR Lens visual style (dotted background, soft lanes, white cards with icon chips, green/amber/red/grey state colors).

Why a renderer instead of PR Lens or Mermaid: auto-layout engines decide placement themselves, and for data stages they tend to stagger nodes, wrap them two per row, reorder them, and route lines around the outside. Data people read a lineage by stage, with every chain on one row. Explicit placement gives that every time.

## 1. Pick the tool

| Situation | Use |
|---|---|
| Lineage, architecture or data model where layout matters; aligned stage columns; vertical column lists in tables; left-to-right flow | This skill's renderer (`scripts/render_diagram.py`) |
| A diagram for a pull request or a code change, about 8 nodes or fewer, no layout demands | PR Lens (`npx @coldtea/pr-lens-cli@latest ...`); read `references/pr-lens-notes.md` first |
| A request/response sequence with participants (lifelines) | PR Lens flow, split into phases of at most 5 participants; see notes |
| Dozens of dbt models, a whole warehouse | Generate from the project instead (`dbt docs generate`, or a tool reading `manifest.json`). Hand-placed diagrams do not scale past roughly 15 nodes per stage |
| User explicitly wants Mermaid, draw.io or Excalidraw | Use those |

If PR Lens output is messy, do not keep tuning it. Its layout hints (`direction`, `rank`, `group`) were tested and have no effect on these cases. Switch to the renderer.

## 2. Workflow

1. Clarify what is being shown and for whom (lineage, architecture, data model, flow). Ask only what you cannot infer.
2. List the nodes, then decide the grid:
   - **Lanes** are columns, in reading order (left to right): stages such as raw, staging, dimensions, facts, aggregates, or tiers such as sources, ingestion, storage, transform, serving.
   - **Rows** align chains: everything about one entity (orders, customers, products) shares a row index across lanes, so its line between stages is perfectly straight.
3. Write a JSON spec (fields below; examples in `assets/examples/`). Start from the closest example.
4. Render: `python3 scripts/render_diagram.py spec.json out.svg [--theme light|dark] [--animate none|packets|dashes]`. Fix every `WARNING` it prints; they mean a line crosses a card or a label does not fit.
   - `--theme dark` uses the PR Lens dark palette. Render both themes when the diagram goes into docs that support light and dark mode.
   - `--animate packets` sends a dot along each connection, stage by stage, looping every few seconds (the same technique PR Lens uses for flows). `dashes` makes the lines march continuously. Use animation for READMEs, slides and walkthroughs; keep `none` for printed or archived diagrams. Set `"step": n` on an edge to control the order; edges with the same step move together, and by default the step is the lane the data arrives in. Animation is SMIL, so it plays in browsers and in GitHub-rendered images but not in every viewer, and it is not checked by `preview_slices.py` (which shows the first frame).
5. Look at the result. A single Quick Look call crops wide or tall SVGs, so run `python3 scripts/preview_slices.py out.svg <outdir>` (macOS) and view every slice. Check: no crossing lines, labels readable, arrows land on the right card, nothing clipped.
6. Iterate on the spec, not the SVG. Deliver the path and, if the user wants to look at it, `open` it in their browser. Say what you did not visually check.

## 3. Spec reference

```json
{
  "title": "Lineage by stage",
  "options": {"card_w": 230, "gap": 150, "row_gap": 30, "trunk": 40, "show_new": false, "theme": "light", "animate": "none",
              "lines": "merge", "show_lanes": true, "flip": false, "group_pad": 20},
  "lanes": [{"id": "raw", "label": "raw", "sub": "loaded by ingestion"}],
  "nodes": [{"id": "raw_orders", "title": "raw.orders", "lane": "raw", "row": 0,
             "sub": "PK id, FK customer_id, ...", "glyph": "db", "state": "added"}],
  "edges": [{"from": "raw_orders", "to": "stg_orders", "label": "cast and rename"}]
}
```

- `lanes`: ordered left to right. `label` is upper-cased; `sub` is optional small text.
- `nodes`: `row` is a number; equal rows align horizontally, and rows may be fractional to nudge a card between two rows. `glyph` is one of `db`, `module`, `table`, `service`, `ui`, `queue`, `file`. `state` is `unchanged` (grey, default), `added` (green), `modified` (amber) or `removed` (red). `badge` adds a small chip text; `show_new: true` shows NEW on added nodes (off by default because it is noise outside a diff).
- Table nodes: give `columns: [{"name","type","key"}]` with `key` of `"PK"`, `"FK"`, `"PK,FK"` (a column that is both, such as part of a composite key that is also a foreign key) or null. The card then lists columns vertically and shows `N columns`. Edges can attach to a specific column with `from_col` and `to_col`, which is how FK lines land on the exact key row.
- `edges`: `label` should be one or two short words. `style: "dotted"` for derived or optional links. `state` overrides the color, otherwise it follows the nodes.
- `groups` draw nested boxes (box in box in box) around nodes or other groups: `{"id","title","sub","members":[node or group ids],"state","style":"dashed"}`. Use them for containers such as an orchestrator around a pipeline, a warehouse around its schemas, or a platform around everything. Members keep their lane and row; the box is computed around them, so give rows room (`row_gap` 50 to 70, `show_lanes: false` for a cleaner container look). Boxes nest to any depth; deeper boxes are drawn darker.
- `options.lines`: `"merge"` (default) joins all lines into one target through one shared trunk, which suits lineage; `"lanes"` gives every line its own vertical lane in the gap, which is required for ERDs and star schemas so each FK line can be followed to its column. Lines may cross, but each keeps a clear lane.
- **Automatic star / snowflake layout:** set `"layout": "star"` and give only `nodes` (tables with `columns`, no `lane` or `row`) and `edges` (FK holder to referenced table, with `from_col` and `to_col`). The renderer puts the centre table in the middle (`"center": "id"` to choose it, otherwise the table with the most outgoing FKs), balances the tables it references between a left and a right column, uses a slot above or below the fact when that makes the diagram more compact, and places tables that only a dimension references (snowflake sub-dimensions) one column further out beside their parent. Everything sits in one box (`"box_title"`), no lanes, each FK line in its own vertical lane. See `assets/examples/star-auto.json`. Use this for a true star or snowflake; use explicit lanes (below) when the user wants several fact tables, aggregates, or control over which side each table is on.
- `options.flip: true` mirrors the lane order left to right. Lane order is the layout: put the fact lane first, last or in the middle (dimension lanes on both sides) and the arrows keep pointing from the FK to the PK. A table in the same lane as the fact gets a short vertical line from the fact's bottom or top edge.
- Routing is automatic and follows one rule set: a line leaves the right side of the source and enters the left side of the target; if the target lane is to the left, it leaves the left side and enters the right side; within one lane it runs bottom to top vertically. Lines to the same target merge into one vertical trunk just before it, and lines from one source to several targets split from a shared trunk.

## 4. Layout rules that keep diagrams readable

These come from iterating on real lineage and star-schema diagrams until the user accepted them.

- **Flow reads left to right.** Stage columns, one table per cell, listed vertically.
- **Put the primary entity on the top row** (for example orders) so the main chain is the first thing the eye follows, and its line to the fact runs straight across.
- **Keep chains aligned.** If dimensions sit between raw and the fact, leave the empty cell on the fact's row empty so the straight line passes through it. Do not place a card on a straight line's path; the renderer warns when it happens.
- **Do not invent upstream tables.** A generated table (a date dimension built from a date spine, a seed) has no raw or staging node. Show it alone in its stage and say "generated" in its subtitle.
- **Keep labels short** (`rename`, `build facts`, `customer_id`, `sum`, `FK`). The gap between lanes must exceed the label width; widen `options.gap` when the warning says so. Long labels are the usual reason lines get pushed into loops in auto-layout tools.
- **One state vocabulary.** Use grey for reference documentation. Use green, amber and red only when something is new, changed or removed; otherwise colour carries no meaning.
- **Data models:** facts and aggregates are fact tables that reuse the same dimensions. Draw FK lines from each fact's FK column to the dimension's PK row, with `"lines": "lanes"` so no two lines share a vertical. For a true star, put the fact lane in the middle with dimension lanes on both sides (`assets/examples/star-center.json`, or the automatic `layout: star`), or put one dimension in the fact's lane below it. Put each fact table in its own lane next to the dimensions, so every FK line stays in one gap. See `references/modeling-notes.md` for what reviewers expect.
- **Containers:** use `groups` when the user describes wrapping ("Airflow around the pipeline"). A container is a box, not a node; edges still go between the nodes inside.
- **Show derivation separately from keys.** FK lines belong in the model diagram; "built from" arrows (fact to aggregate, staging to mart) belong in the lineage diagram. Two diagrams are clearer than one that mixes both.

## 5. Limits to state honestly

- Light and dark themes, optional packet or dash animation, no hover or click behaviour. The renderer cannot lay out cycles or very dense graphs; it only routes what you place.
- It is a drawing, not generated from the code or the warehouse. If the models change, the spec must change.
- A table row is about 20px tall; a lane fits about 230px of text. Truncate subtitles with `...` rather than overflowing.

## 6. Confidentiality

Use generic, anonymized table and system names unless the user supplied real ones and wants them shown. Never upload a diagram to an external service (for example `pr-lens canvas push`, which creates a public link) without the user's explicit go-ahead.
