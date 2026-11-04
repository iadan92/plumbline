#!/usr/bin/env python3
"""UserPromptSubmit hook: when a prompt asks for a data diagram, tell the agent to use the plumbline skill.

Why a hook: an agent decides whether to open a skill from its one-line description, and for short requests
it often starts writing SVG, or asks questions, without opening any skill. A hook runs on every prompt, so
the reminder arrives with the request. It adds one short paragraph of context and nothing else, and stays
silent when the prompt names another tool (Mermaid, PlantUML, Excalidraw, draw.io) or is not about a diagram.

Reads the hook JSON on stdin. Standard library only; works on Python 3.8 or newer.
"""
import json
import re
import sys

DRAW = re.compile(
    r"\b(draw|drawn|drawing|diagram|diagrams|sketch|visuali[sz]e|visuali[sz]ation|visual|illustrate|depict|picture|erd|erds|chart (the|our|how)|"
    r"lineage (graph|picture|view|chart|map)|entity[- ]relationship|svg|png|gif|map out|lay out)\b", re.I)
DATA = re.compile(
    r"\b(dbt|lineage|erd|erds|star schema|snowflake schema|data model|data models|data flow|dataflow|data pipeline|data platform|"
    r"data architecture|data stack|data warehouse|warehouse|lakehouse|data lake|medallion|bronze|silver|gold|pipeline|pipelines|etl|elt|ingestion|ingest|"
    r"airflow|dagster|prefect|airbyte|fivetran|dlt|kafka|kinesis|spark|flink|snowflake|bigquery|redshift|databricks|"
    r"clickhouse|postgres|mysql|duckdb|looker|tableau|metabase|power ?bi|superset|manifest\.json|ddl|schema\.sql|"
    r"create table|fact table|fact tables|dimension table|dimension tables|dim_\w+|fct_\w+|stg_\w+|"
    r"tables?|schemas?|columns?|primary key|foreign key|feature store|data mart|marts?|dashboards?)\b", re.I)
OTHER_TOOL = re.compile(r"\b(mermaid|plantuml|excalidraw|draw\.io|drawio|graphviz|dot file|lucidchart|miro|figma)\b", re.I)
NOT_A_DIAGRAM = re.compile(r"\b(no diagrams?|without (a )?diagrams?|don'?t (need|want) (a )?diagrams?|bar chart|line chart|pie chart|histogram|scatter|org chart|flowchart of (our )?(login|checkout|sign))", re.I)

MESSAGE = (
    "This request is about a data diagram (lineage, data flow, architecture, sequence diagram or data model). "
    "Your first action must be to call the Skill tool for plumbline-svg-diagrams (listed as plumbline:plumbline-svg-diagrams "
    "when installed as a plugin), before writing any SVG by hand, before reading files and before asking the user questions. "
    "The skill says how to find the input (a manifest.json or .sql file in the project), and how to proceed on sensible "
    "assumptions when details are missing."
)


def wants_diagram(prompt):
    if not prompt or OTHER_TOOL.search(prompt) or NOT_A_DIAGRAM.search(prompt):
        return False
    return bool(DRAW.search(prompt) and DATA.search(prompt))


def main():
    try:
        prompt = json.load(sys.stdin).get("prompt", "")
    except ValueError:
        return 0
    if wants_diagram(prompt):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": MESSAGE}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
