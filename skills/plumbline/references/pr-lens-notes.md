# PR Lens notes (observed behavior)

Findings from many renders with `@coldtea/pr-lens-cli` 0.14 (renderer 0.4.1). These are observations, not documented guarantees; re-test if the version changed. Official workflow: `npx @coldtea/pr-lens-cli@latest skill` and `... skill references`.

## Basic workflow

1. Write `.pr-lens/graph.json` (document fields: `schemaVersion "0.3.0"`, `kind "graph"`, `title`, `summary`, `lenses`, `provenance`, `lanes`, `nodes`, `edges`, optional `flows`, `dataModel`, `views`).
2. `validate`, then `render <file> --theme light`.
3. Run the CLI from the repository root. Output goes to `.pr-lens/<title-slug>/`, resolved against the current directory, so running it from inside `.pr-lens/` creates a nested `.pr-lens/.pr-lens/`.
4. Changing the title makes a new output folder; old folders and their SVGs stay behind. Clean up.

## Required quirks

- `provenance` (repo, base sha, head sha) is mandatory even for a concept diagram. Use a placeholder such as owner `local` and sha `0000000`, and say so.
- A document with no git commits still works with those placeholders.
- `validate` can pass documents that render with `viewBox="0 0 NaN NaN"`. Always check the rendered `viewBox`. Seen when a data-model relation did not follow the pattern "source is a non-first column, target is the first (PK) column of its table"; not fully understood.

## Layout behavior

- Lanes are columns. A single lane stacks nodes top-down and always stops at two per row, whether it holds 3, 4 or 6 nodes. Unconnected siblings sit side by side.
- Across lanes, downstream nodes are staggered one step lower, so chains do not stay on one row, and lines turn diagonal-looking elbows.
- The renderer reorders nodes inside a lane to suit its edges, ignoring declaration order.
- `layout.direction` (only `right` or `down` are valid), `layout.rank`, and node `group` made no difference to the output. `layout.laneOrder` accepts only document lane ids, not data-model stores.
- Data-model stores (lanes of tables) are ordered by the renderer from relation direction and the `enforced` flag, not by declaration order. Adding a lone disconnected store can flip the order of the other two. Solid FK arrows with the fact on the left and dimensions in the middle came out reliably; "dimensions, facts, aggregates" with solid lines did not.
- A relation with `enforced: false` is drawn dotted.

## Why lines loop around the outside

- In the data-model lens, a relation label longer than the gap between lanes makes the renderer route the line over the top of the whole diagram to fit the label. Labels like `FK` or `ref` keep lines inside the gap.
- Long labels were the main cause of the "messy loops"; relation direction and lane order were secondary.

## Colors and badges

- Color and the NEW badge both come from the element's `delta`: `added` is green with NEW, `modified` amber, `removed` red, `unchanged` grey with no badge. They cannot be separated. For a neutral reference diagram set everything to `unchanged`.

## Data flows (sequence diagrams)

- Width grows with the number of participants (9 participants gave about 3300px). Split into phases of 3 to 5 participants, one flow per phase.
- A request needs an explicit `return` message to show the response arrow; a payload alone does not draw one.
- Model the true order of steps. Example: in a dbt build each layer is built and then tested before the next layer builds, so tests run after the model they check and before downstream models.
- `payload` samples render only on a prlens.dev canvas, not in the SVG.

## Canvas

- `canvas push` uploads to prlens.dev and returns a public view link (no login). Ask before doing it.

## Previewing

- macOS Quick Look (`qlmanage -t`) renders a square thumbnail from the top-left and crops everything else. Use `scripts/preview_slices.py` to inspect all of a wide or tall SVG.
