---
name: plumbline-svg-diagrams
description: >-
  Draws data diagrams as clean SVG, PNG or GIF: dbt lineage and DAGs, ETL and pipeline data flow,
  warehouse, lakehouse and platform architecture, sequence diagrams of a pipeline run, ERDs, star
  and snowflake schemas, and before/after diffs of a diagram. Use it instead of Excalidraw, Mermaid,
  draw.io or hand-written SVG whenever the user asks to draw, diagram, sketch, map or visualise
  anything about data: pipelines, ingestion, orchestration, warehouse layers, dbt models, tables,
  keys, schemas, BI. Use it even for short or vague requests ("ERD for these tables", "star schema
  for sales"): the skill explains how to proceed on sensible assumptions. Reads dbt manifest.json
  and SQL DDL.
---

# SVG data diagrams

Paths in this file (`scripts/`, `assets/`, `references/`) are relative to the directory that contains this SKILL.md. The agent runs in the user's project, so call the scripts by absolute path, for example `python3 <skill-dir>/scripts/render_diagram.py spec.json out.svg`. Requires Python 3.8 or newer and no packages. Only `export.py` (PNG, PDF, GIF) also needs Node.js 18 or newer.

Produce data diagrams where nodes sit in a grid of lanes and rows, and lines are short, straight and predictable. You can place every node yourself, or leave placement to the renderer and pin only what the user wants somewhere specific; a pinned lane or row always wins over automatic placement. The bundled renderer draws in the PR Lens visual style (dotted background, soft lanes, white cards with icon chips, green/amber/red/grey state colors), and can read dbt manifests and SQL DDL, compare two versions of a diagram, apply a brand theme and export PNG, PDF and GIF.

Why a renderer instead of PR Lens or Mermaid: general auto-layout engines stagger nodes, wrap them two per row, reorder them, and route lines around the outside. Data people read a lineage by stage, with every chain on one row. This renderer's automatic placement works that way (a stage per column, a chain per row), and explicit placement overrides it wherever the user cares.

## 1. Pick the tool

| Situation | Use |
|---|---|
| Lineage, architecture or data model where layout matters; aligned stage columns; vertical column lists in tables; left-to-right flow | This skill's renderer (`scripts/render_diagram.py`) |
| A diagram for a pull request or a code change, about 8 nodes or fewer, no layout demands | PR Lens (`npx @coldtea/pr-lens-cli@latest ...`); read `references/pr-lens-notes.md` first |
| A request/response sequence with participants (lifelines), for example "who calls whom" across a nightly run | This skill's renderer with `"type": "sequence"` (section 3b) |
| A dbt project | `scripts/import_dbt.py target/manifest.json` writes the lineage spec for you (section 3c). Select a slice with `--select`; do not draw dbt models by hand |
| A database schema as SQL (`CREATE TABLE ...`) | `scripts/import_ddl.py schema.sql`, which finds keys and foreign keys and picks star or lanes (section 3c) |
| "What changed between these two versions", a schema or lineage diff, a review diagram | `scripts/diff_specs.py old.json new.json` (section 3d) |
| A PNG, PDF or animated GIF, for a slide, ticket or chat | `scripts/export.py` (section 3f) |
| A whole warehouse, hundreds of models | Import with a narrow `--select`; one diagram should show about 60 nodes at most |
| User explicitly wants Mermaid, draw.io or Excalidraw | Use those |

If PR Lens output is messy, do not keep tuning it. Its layout hints (`direction`, `rank`, `group`) were tested and have no effect on these cases. Switch to the renderer.

## 2. Workflow

1. Work out what is being shown and for whom (lineage, architecture, data model, flow). Do not interview the user first. When the request is short or vague ("star schema for sales", "ERD for these tables", "diagram our data flow"), pick conventional generic assumptions (for a sales star: a `fct_sales` fact with date, product, customer and store dimensions), draw a first version, state the assumptions in one line, and invite corrections. Ask a question only when a wrong guess would waste the user's time, for example which of two real projects to read.
2. List the nodes and edges. Decide how much layout the user cares about:
   - **No layout wishes:** leave `lane` and `row` out. The renderer puts each node one lane right of its inputs and keeps chains on one row (section 3a).
   - **Named stages, automatic rows:** give `lanes` and a `lane` on every node, and leave out `row`.
   - **Exact placement:** give both. **Lanes** are columns in reading order (left to right): stages such as raw, staging, dimensions, facts, aggregates, or tiers such as sources, ingestion, storage, transform, serving. **Rows** align chains: everything about one entity (orders, customers, products) shares a row index across lanes, so its line between stages is perfectly straight.
   - When the user asks to move something ("put payments on the top row", "move the dashboard to its own column"), set that node's `lane` or `row` and render again. Do not rewrite the layout.
3. Write a JSON spec (fields below; examples in `assets/examples/`). Start from the closest example, or import one (section 3c).
4. Render: `python3 scripts/render_diagram.py spec.json out.svg [--theme light|dark|print] [--animate none|packets|dashes]`. Fix every `WARNING` it prints; they mean a line crosses a card or a label does not fit. `--validate` checks a spec without drawing and names the exact field that is wrong, with a suggestion; a bad spec fails with the full list at once, so read all of it before fixing.
   - `--theme dark` uses the PR Lens dark palette, `print` a white, high-contrast one for documents. Render both light and dark when the diagram goes into docs that support both.
   - `--animate packets` sends a dot along each connection, stage by stage, looping every few seconds (the same technique PR Lens uses for flows). `dashes` makes the lines march continuously. Use animation for READMEs, slides and walkthroughs; keep `none` for printed or archived diagrams. Set `"step": n` on an edge to control the order; edges with the same step move together, and by default the step is the lane the data arrives in. Animation is SMIL, so it plays in browsers and in GitHub-rendered images but not in every viewer, and it is not checked by `preview_slices.py` (which shows the first frame).
5. Look at the result. On any system, `python3 scripts/export.py out.svg out.png` gives a PNG you can open with an image viewer (section 3f). On macOS a single Quick Look call crops wide or tall SVGs, so `python3 scripts/preview_slices.py out.svg <outdir>` is the alternative. It tiles a wide diagram left to right into `slice-0.svg.png`, `slice-1.svg.png` and so on; view every tile, since each shows only one part. Check: no crossing lines, labels readable, arrows land on the right card, nothing clipped.
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

- `lanes`: ordered left to right. `label` (defaults to the id) is upper-cased; `sub` is optional small text. Optional when nodes are placed automatically.
- `nodes`: `lane` and `row` are optional (section 3a); `row` is a number, equal rows align horizontally, and rows may be fractional to nudge a card between two rows. `glyph` is one of `db`, `warehouse`, `module`, `table`, `service`, `ui`, `queue`, `file`, `bucket`, `orchestrator`, `chart`, `cloud`, `api`, `stream`, `transform`, `user`, `clock`; leave it out and the renderer picks one from the name (s3 or landing gives `bucket`, kafka `queue`, airflow `orchestrator`, looker or dashboard `chart`, dbt `module`, snowflake `warehouse`, tables with columns `table`, otherwise `db`; `options.auto_glyph: false` turns that off). `icon` is custom SVG path data in a 24 by 24 box, drawn as the icon instead (put a company's own logo path here). `state` is `unchanged` (grey, default), `added` (green), `modified` (amber) or `removed` (red); `new`, `changed` and `deleted` are accepted too. `badge` adds a small chip text; `show_new: true` shows NEW on added nodes (off by default because it is noise outside a diff).
- Table nodes: give `columns: [{"name","type","key"}]` with `key` of `"PK"`, `"FK"`, `"PK,FK"` (a column that is both, such as part of a composite key that is also a foreign key) or null. The card then lists columns vertically and shows `N columns`. Edges can attach to a specific column with `from_col` and `to_col`, which is how FK lines land on the exact key row.
- `edges`: `label` should be one or two short words. `style: "dotted"` for derived or optional links. `state` overrides the color, otherwise it follows the nodes.
- `groups` draw nested boxes (box in box in box) around nodes or other groups: `{"id","title","sub","members":[node or group ids],"state","style":"dashed"}`. Use them for containers such as an orchestrator around a pipeline, a warehouse around its schemas, or a platform around everything. Members keep their lane and row; the box is computed around them, so give rows room (`row_gap` 50 to 70, `show_lanes: false` for a cleaner container look). Boxes nest to any depth; deeper boxes are drawn darker.
- `options.fit_width: 1700` shrinks card width and gap until the diagram fits that many pixels, keeping room for the longest label. Use it instead of hand-tuning `card_w` and `gap` when a diagram has six or more lanes.
- `options.lines`: `"merge"` (default) joins all lines into one target through one shared trunk, which suits lineage; `"lanes"` gives every line its own vertical lane in the gap, which is required for ERDs and star schemas so each FK line can be followed to its column. Lines may cross, but each keeps a clear lane.
- **Automatic star / snowflake layout:** set `"layout": "star"` and give only `nodes` (tables with `columns`, no `lane` or `row`) and `edges` (FK holder to referenced table, with `from_col` and `to_col`). The renderer puts the centre table in the middle (`"center": "id"` to choose it, otherwise the table with the most outgoing FKs), balances the tables it references between a left and a right column, uses a slot above or below the fact when that makes the diagram more compact, and places tables that only a dimension references (snowflake sub-dimensions) one column further out beside their parent. Everything sits in one box (`"box_title"`), no lanes, each FK line in its own vertical lane. See `assets/examples/star-auto.json`. Use this for a true star or snowflake; use explicit lanes (below) when the user wants several fact tables, aggregates, or control over which side each table is on.
- `options.flip: true` mirrors the lane order left to right. Lane order is the layout: put the fact lane first, last or in the middle (dimension lanes on both sides) and the arrows keep pointing from the FK to the PK. A table in the same lane as the fact gets a short vertical line from the fact's bottom or top edge.
- Routing is automatic and follows one rule set: a line leaves the right side of the source and enters the left side of the target; if the target lane is to the left, it leaves the left side and enters the right side; within one lane it runs bottom to top vertically. Lines to the same target merge into one vertical trunk just before it, and lines from one source to several targets split from a shared trunk.

## 3a. Automatic layout, and tweaking it

A node without `lane` or `row` is placed by the renderer; a node that has them stays exactly there. Mix freely. The rules, so you can predict and correct the result:

- **Lane:** one right of the furthest-right lane among its inputs. A source with no inputs sits just left of its first consumer, so no line crosses empty lanes. If `lanes` is absent they are created, unlabelled (a column of cards needs no name; give `layer` to name them). Give every node a `layer` such as `raw` or `marts` and the layers become the lanes, in flow order, with those names. If the nodes flow further right than the given `lanes`, extra lanes are added and the renderer says so.
- **Row:** near the average row of its inputs, so a chain stays on one row; sources then line up with their consumers; a card is never put where a line from further left would run through it. Edges that point backwards (cycles) are ignored for placement and still drawn, with a warning.
- **Pins win:** `"lane": "marts"` or `"row": 0` on a node is a direct instruction. Free nodes are placed around it, and two pinned nodes in one cell are rejected. For "put X on the top row" set `row: 0` on X (and on the nodes of its chain, to keep the line straight); for "move X to the aggregates stage" set `lane`.
- **Freeze and edit:** `render_diagram.py spec.json out.svg --resolve resolved.json` also writes the spec with every automatic lane and row filled in. Render `resolved.json` and it looks identical, but now every node is pinned and a hand edit moves only that node.
- Not for stars: `"layout": "star"` below still does its own placement.

## 3b. Sequence diagrams

Set `"type": "sequence"` to draw participants as columns with lifelines and messages in time order. Use it for runtime behaviour (orchestrator calls extractor, extractor calls API, API returns a page); use the lane and row spec above for structure (what feeds what). Coordinates are never given: columns follow participant order, rows follow message order, and activation bars, arrow ends, column widths and label room are computed.

```json
{
  "type": "sequence",
  "title": "Nightly pipeline",
  "options": {"numbers": true, "headers": "top"},
  "participants": [{"id": "dagster", "title": "Dagster", "sub": "assets and daily schedule", "glyph": "service"},
                   {"id": "dlt", "title": "dlt pipeline", "glyph": "module"},
                   {"id": "api", "title": "Shop REST API", "glyph": "service"}],
  "phases": [{"id": "extract", "title": "1. Extract and load", "state": "added",
              "messages": [{"id": "run", "from": "dagster", "to": "dlt", "label": "run extract asset"},
                           {"id": "page", "from": "dlt", "to": "api", "label": "GET /orders", "reply": "200 OrderPage", "repeat": 5},
                           {"from": "dlt", "to": "dagster", "kind": "return", "label": "extract succeeded"}]}],
  "frames": [{"label": "loop: each page", "from": "page", "to": "page:reply"}]
}
```

- `participants`: same fields as nodes (`title`, `sub`, `glyph`, `state`). Order is left to right; put the initiator first. Card width adapts to the text. A participant can take part in any number of messages and phases; it keeps one column. Order columns so chatty pairs sit next to each other, because a call across other lifelines is drawn straight over them.
- `phases`: labelled bands (`title`, `sub`, optional `state` colouring its messages). Omit `phases` and give a flat `messages` list for one band. Keep a phase to about 10 messages, so each stays readable.
- Message `kind`: `sync` (default, solid arrow, opens an activation bar on the receiver), `return` (dashed, closes the sender's bar), `async` (open arrowhead, short bar), `self` (loop on one participant, set `from` equal to `to`), `note` (`over`: one id or a list, `label`). `reply: "text"` adds the return straight after a call. `repeat: n` appends a multiplication sign and n to the label; use it with a `loop` frame instead of drawing the same call n times. Number only calls: a reply stays unnumbered. `state` colours a message (grey by default; use green, amber, red only for added, changed, removed).
- `frames`: dashed loop or alt boxes around a message range, by message `id` (a reply is `<id>:reply`).
- `options.headers`: `top` (default) draws participant cards once with continuous lifelines; `phase` repeats the cards inside every band for the participants that band uses, which is the PR Lens look and suits long diagrams. `options.numbers: true` numbers calls (not returns). `options.gap` sets the minimum distance between columns; it widens by itself when a label needs room.
- Theme and `--animate packets` work as elsewhere: packets play message by message in order.

## 3c. Import from a dbt project or a SQL schema

Do not copy model or table names by hand when the project exists; import, then render.

```bash
python3 scripts/import_dbt.py target/manifest.json -o spec.json --select "+fct_orders" --columns 6
python3 scripts/render_diagram.py spec.json lineage.svg
python3 scripts/import_ddl.py schema.sql -o spec.json          # or: pg_dump --schema-only db | import_ddl.py - -o spec.json
```

- `import_dbt.py` reads sources, seeds, snapshots, models and exposures and the references between them. Lanes are sources, staging, intermediate, marts, exposures (guessed from the folder and name prefix); rows are automatic. `--select` and `--exclude` use dbt's syntax: `name`, `+name`, `name+`, `2+name+1`, `tag:finance`, `path:models/marts`, `source:shop`, `resource_type:seed`, `*` wildcards, space for union, comma for intersection. `--columns N` lists N documented columns per model and marks PK (unique plus not_null tests) and FK (relationships tests). It refuses more than 60 nodes (`--max-nodes`, `--force`) and tells you to narrow the selection. Run `dbt compile` first so `manifest.json` is current. Ask the user where the manifest is; never invent one.
- `import_ddl.py` reads CREATE TABLE and ALTER TABLE from Postgres, MySQL, Snowflake, BigQuery, SQL Server and ANSI DDL: columns, types (shortened, for example `timestamptz`), primary keys, foreign keys inline, as constraints or added later. A star or snowflake shape becomes `layout: star`; any other schema is laid out by the direction of its foreign keys. `--tables a,b` keeps some tables, `--max-columns` caps columns per table (keys are kept first).
- The result is an ordinary spec. Add `lane` or `row` to pin a node, set `state`, rename titles, add `groups`, then render. `assets/examples/dbt-manifest-sample.json` and `billing-schema.sql` are small inputs to try.

## 3d. Compare two versions

`python3 scripts/diff_specs.py old.json new.json -o diff.json --summary`, or `--git HEAD~1 spec.json` to compare the working copy with a commit. Render `diff.json` as usual. Added elements are green, changed amber, removed red, dashed and struck through, left where they were so the reader sees what is gone. Cards carry ADDED, CHANGED or REMOVED chips, tables mark each column (new in green, removed struck through, changed type or key in amber), and a key at the bottom right counts the nodes and connections in each state. `--summary` prints the same changes as a list for a pull request description. Works for lineage, architecture, data models and sequence diagrams. Elements match by `id` (edges by their two ends and columns, messages by `id` or by sender, receiver and label), so keep ids stable between versions. To mark a diff by hand instead, set `state` on elements and `options: {"diff_labels": true, "legend": true}`.

## 3e. Brand themes

For a client or company look, put colours in a theme file and pass `--theme-file brand.json` (also accepted by `export.py`), or put the same `palette`, `font` and `mono` under `options` in the spec. See `assets/examples/theme-brand.json`.

```json
{"theme": "light", "font": "Inter, Arial, sans-serif",
 "palette": {"bg": "#fbf7f0", "card": "#fffdf9", "title": "#2b1d0e", "glyph": "#7a5b2e",
             "states": {"unchanged": {"line": "#b07d2b", "text": "#7a5b2e", "fill": "#f3eadb"}}}}
```

`palette` keys are the theme tokens: `bg`, `dots`, `lane`, `lane_label`, `lane_sub`, `card`, `card_stroke`, `chip`, `glyph`, `title`, `sub`, `colname`, `coltype`, `sep`, `pill`, `pill_stroke`, `shadow`, `packet_ring`, `group_fill` (three colours), `group_stroke`, `group_title`, and `states` (`added`, `modified`, `removed`, `unchanged`, each with `line`, `text`, `fill`, `stroke_opacity`). Colours must be hex, `rgb()` or `rgba()`; anything else is rejected. `unchanged` colours the lines of a plain diagram, so setting it is how a brand colour reaches the connections.

## 3f. Export PNG, PDF and GIF

```bash
python3 scripts/export.py diagram.svg diagram.png              # 2x PNG
python3 scripts/export.py diagram.svg diagram.pdf              # one page, raster
python3 scripts/export.py spec.json flow.gif [--animate packets|dashes] [--fps 12] [--max-width 1200]
```

Needs Node.js 18 or newer; the first run installs two npm packages into `~/.cache/plumbline` (needs network once). Works on macOS, Linux and Windows. A GIF is drawn from the spec, not from an SVG: it samples the animation frame by frame, loops forever, and stores only the pixels that change, so a 12 second loop is typically a few hundred KB. Use `--theme dark`, `--theme-file` and `--at 2.5` (a still taken at that second of the animation) with a spec input. Text is drawn with the fonts installed on the machine. Use GIF where SVG animation does not play (Slack, email, slides, some wikis) and the animated SVG where it does (browsers, GitHub READMEs).

## 4. Layout rules that keep diagrams readable

These come from iterating on real lineage and star-schema diagrams until the user accepted them.

- **Flow reads left to right.** Stage columns, one table per cell, listed vertically.
- **Put the primary entity on the top row** (for example orders) so the main chain is the first thing the eye follows, and its line to the fact runs straight across.
- **Keep chains aligned.** If dimensions sit between raw and the fact, leave the empty cell on the fact's row empty so the straight line passes through it. Do not place a card on a straight line's path; the renderer warns when it happens.
- **Do not invent upstream tables.** A generated table (a date dimension built from a date spine, a seed) has no raw or staging node. Show it alone in its stage and say "generated" in its subtitle.
- **Keep labels short** (`rename`, `build facts`, `customer_id`, `sum`, `FK`). The gap between lanes must exceed the label width; widen `options.gap` when the warning says so. Long labels are the usual reason lines get pushed into loops in auto-layout tools.
- **One state vocabulary.** Use grey for reference documentation. Use green, amber and red only when something is new, changed or removed; otherwise colour carries no meaning.
- **Data models:** facts and aggregates are fact tables that reuse the same dimensions. Draw FK lines from each fact's FK column to the dimension's PK row, with `"lines": "lanes"` so no two lines share a vertical. For a true star, put the fact lane in the middle with dimension lanes on both sides (`assets/examples/star-center.json`, or the automatic `layout: star`), or put one dimension in the fact's lane below it. Put each fact table in its own lane next to the dimensions, so every FK line stays in one gap. See `references/modeling-notes.md` for what reviewers expect.
- **Width:** a slide or README shows about 1400 to 1800px well. With six or more stage columns set `options.fit_width` to 1700 (or `card_w` about 170 and `gap` about 110; the gap must stay wider than the longest label, or the renderer warns). The renderer prints a NOTE above 1800px.
- **Containers:** use `groups` when the user describes wrapping ("Airflow around the pipeline"). A container is a box, not a node; edges still go between the nodes inside.
- **Show derivation separately from keys.** FK lines belong in the model diagram; "built from" arrows (fact to aggregate, staging to mart) belong in the lineage diagram. Two diagrams are clearer than one that mixes both.

- **Sequence diagrams:** give every call a `reply` or a `return` message, or mark it `async`; an unanswered call keeps its activation bar open to the end of the phase and the renderer warns. Keep labels to a few words, name messages by what is sent (`GET /orders`) and returns by what comes back (`200 OrderPage`), and split a long run into phases instead of 25 messages in one band.

## 5. Limits to state honestly

- Light, dark and print themes plus brand palettes, optional packet or dash animation, no hover or click behaviour. Automatic placement is a readable default, not an optimiser: it handles flows of up to roughly 60 nodes, ignores cycles, and for a dense graph the user may need to pin a few nodes. Lines are routed, not searched, so a very dense graph can still have crossings; the renderer warns when a line would run through a card.
- A spec is a drawing, not live. If the models change, re-import or edit the spec. The importers read a manifest or DDL file; they do not connect to a warehouse.
- PDF export is a 2x raster page, not vector. GIF is limited to 128 colours, which suits these flat diagrams.
- A table row is about 20px tall; a lane fits about 230px of text. Truncate subtitles with `...` rather than overflowing.

## 6. Confidentiality

Use generic, anonymized table and system names unless the user supplied real ones and wants them shown. Never upload a diagram to an external service (for example `pr-lens canvas push`, which creates a public link) without the user's explicit go-ahead.
