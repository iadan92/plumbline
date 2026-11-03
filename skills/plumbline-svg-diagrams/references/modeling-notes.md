# Data-model notes for diagrams

Guidance gathered while building and reviewing a sales star schema. Conventions vary by team (Kimball-style dimensional modelling is the common default, wide denormalized tables are another school). Treat as guidance and confirm against the team's standards; none of this is legal or compliance advice.

## What a reviewer checks first

1. **Grain.** State what one fact row is. A fact with one `product_id` per order implies one product per order, which is rarely true. Use an order-line fact (for example `fct_order_items`, grain: one row per order line) with `order_id` + `line_number` as a composite primary key, plus `quantity` and `amount`. `order_id` alone is no longer unique. A single surrogate key (`order_item_id`) is the alternative.
2. **Conformed dimensions.** Facts and aggregates share the same dimensions. Draw FK lines from each fact table's FK columns to the dimension's PK.
3. **Aggregates are fact tables.** An aggregate keeps the dimensions it still carries (daily customer totals link to the customer and date dimensions). Draw its derivation from the base fact in the lineage diagram, not as an FK. An aggregate with no links at all reads as an orphan.
4. **Time grain on aggregates.** An all-time total is a snapshot. Daily or monthly aggregates carry a `date_key` as part of their key, can be built incrementally, and can be filtered by period.
5. **No duplicated metrics.** If `dim_customers.lifetime_value` and `agg_customer_totals.total_amount` are the same number, they will drift. Keep it in one place.
6. **Keys.** Natural keys break when source systems change. Many teams use surrogate keys for dimensions and decide how to handle history for slowly changing attributes. State the choice in the diagram or the notes.
7. **Generated dimensions.** A calendar dimension is generated (date spine), not extracted. It has no raw or staging table.

## Marts

A mart is a subject area (sales, finance, marketing) that holds its facts, dimensions and aggregates. Two aggregates of the same subject area belong in one mart, not one mart per table. Split marts only when consumers, owners or domain differ. In dbt this is one folder, for example `models/marts/sales/` with `fct_`, `dim_` and `agg_` models.

## Layers for a lineage

raw (as extracted, never edited) -> staging (rename, cast, deduplicate; one view per source table) -> marts (facts, dimensions, aggregates) with tests (not null, unique, relationships) after each layer is built.

## Label semantics

- count vs sum: an item count is a sum of `quantity`, not a count of lines, unless every line is one unit. Decide before labelling an edge.
- FK arrows conventionally point from the fact (child) to the dimension (parent).
