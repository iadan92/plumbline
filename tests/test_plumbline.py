"""Tests for the plumbline renderer, layout, importers, diff and export.

Run from the repository root:  python3 -m unittest discover -s tests -v
Standard library only. The export tests need Node.js and network access on first run (they install two npm
packages into a temporary cache) and are skipped when node is missing or PLUMBLINE_SKIP_EXPORT is set.
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "plumbline-svg-diagrams"
SCRIPTS = SKILL / "scripts"
EXAMPLES = SKILL / "assets" / "examples"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

import build_examples  # noqa: E402
import diff_specs  # noqa: E402
import import_ddl  # noqa: E402
import import_dbt  # noqa: E402
from layout_auto import auto_layout  # noqa: E402
from render_diagram import render  # noqa: E402
from spec_check import check  # noqa: E402


def example(name):
    return json.load(open(EXAMPLES / f"{name}.json"))


def run(script, *args, **kw):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, **kw)


def lineage(nodes, edges, **extra):
    return {"title": "t", "nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges], **extra}


class Examples(unittest.TestCase):
    def test_every_example_is_reproducible_and_clean(self):
        """Committed example SVGs match a fresh render byte for byte, and no spec warns."""
        self.assertEqual(build_examples.main(["--check"]), 0)

    def test_render_is_deterministic(self):
        spec = example("lineage-by-stage")
        self.assertEqual(render(spec, animate="packets")["svg"], render(spec, animate="packets")["svg"])

    def test_render_does_not_change_its_input(self):
        spec = example("lineage-auto")
        before = copy.deepcopy(spec)
        render(spec)
        self.assertEqual(spec, before)

    def test_every_example_spec_validates_without_warnings(self):
        for path in EXAMPLES.glob("*.json"):
            if path.name == "theme-brand.json" or path.name.endswith("manifest-sample.json"):
                continue
            errors, warnings = check(json.load(open(path)))
            self.assertEqual((errors, warnings), ([], []), path.name)


class Escaping(unittest.TestCase):
    def test_text_with_markup_stays_well_formed(self):
        hostile = 'x"><script>alert(1)</script> & <b>'
        for spec in (lineage([{"id": "a", "title": hostile, "sub": hostile, "columns": [{"name": hostile, "type": hostile}]}], [], title=hostile),
                     {"type": "sequence", "title": hostile, "participants": [{"id": "a", "title": hostile}, {"id": "b"}],
                      "messages": [{"from": "a", "to": "b", "label": hostile, "reply": hostile}]}):
            svg = render(spec)["svg"]
            root = ET.fromstring(svg)
            self.assertFalse(any(el.tag.endswith("script") for el in root.iter()))


class Validation(unittest.TestCase):
    def test_names_the_field_and_suggests_a_fix(self):
        spec = lineage([{"id": "a", "lane": "stagging"}], [], lanes=[{"id": "staging"}])
        errors, _ = check(spec)
        self.assertTrue(any("nodes[0].lane" in e and "Did you mean 'staging'" in e for e in errors), errors)

    def test_reports_every_problem_at_once(self):
        spec = {"nodes": [{"id": "a"}, {"id": "a", "glyph": "cyllinder"}], "edges": [{"from": "a", "to": "zzz"}], "options": {"theme": "darc"}}
        errors, _ = check(spec)
        self.assertEqual(len(errors), 4, errors)

    def test_typos_in_field_names_warn(self):
        _, warnings = check(lineage([{"id": "a", "titel": "x"}], []))
        self.assertTrue(any("titel" in w and "title" in w for w in warnings), warnings)

    def test_unknown_column_in_an_edge_is_an_error(self):
        spec = lineage([{"id": "a", "columns": [{"name": "id"}]}, {"id": "b", "columns": [{"name": "id"}]}], [])
        spec["edges"] = [{"from": "a", "to": "b", "from_col": "idd"}]
        errors, _ = check(spec)
        self.assertTrue(any("edges[0].from_col" in e for e in errors), errors)

    def test_overlapping_pins_are_an_error(self):
        spec = lineage([{"id": "a", "lane": "x", "row": 0}, {"id": "b", "lane": "x", "row": 0}], [], lanes=[{"id": "x"}])
        self.assertTrue(any("overlap" in e for e in check(spec)[0]))

    def test_bad_spec_exits_with_the_list(self):
        with self.assertRaises(SystemExit) as cm:
            render({"nodes": [{"id": "a", "lane": "q"}], "lanes": [{"id": "x"}]})
        self.assertIn("nodes[0].lane", str(cm.exception))

    def test_cli_validate_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "g.json"
            good.write_text(json.dumps(example("lineage-by-stage")))
            self.assertEqual(run("render_diagram.py", good, "--validate").returncode, 0)
            bad = Path(tmp) / "b.json"
            bad.write_text('{"nodes": []}')
            self.assertEqual(run("render_diagram.py", bad, "--validate").returncode, 1)

    def test_sequence_unknown_participant(self):
        spec = {"type": "sequence", "participants": [{"id": "a"}], "messages": [{"from": "a", "to": "b", "label": "x"}]}
        self.assertTrue(any("unknown participant 'b'" in e for e in check(spec)[0]))


class AutoLayout(unittest.TestCase):
    def placed(self, spec):
        res = render(spec)
        return {n["id"]: (n["lane"], n["row"]) for n in res["spec"]["nodes"]}, res

    def test_lanes_follow_edge_direction(self):
        pos, res = self.placed(lineage([{"id": i} for i in "abcd"], [("a", "b"), ("b", "c"), ("c", "d")]))
        lanes = [l["id"] for l in res["spec"]["lanes"]]
        self.assertEqual([lanes.index(pos[i][0]) for i in "abcd"], [0, 1, 2, 3])

    def test_a_chain_stays_on_one_row(self):
        pos, _ = self.placed(lineage([{"id": i} for i in "abcd"], [("a", "b"), ("b", "c"), ("c", "d")]))
        self.assertEqual({row for _, row in pos.values()}, {0})

    def test_no_two_nodes_share_a_cell(self):
        for name in ("lineage-auto", "lineage-auto-pinned"):
            pos, _ = self.placed(example(name))
            self.assertEqual(len(set(pos.values())), len(pos), name)

    def test_pinned_lane_and_row_win(self):
        spec = lineage([{"id": "a"}, {"id": "b", "lane": "L2", "row": 5}, {"id": "c", "row": 3}], [("a", "b"), ("a", "c")],
                       lanes=[{"id": "L1"}, {"id": "L2"}, {"id": "L3"}])
        pos, _ = self.placed(spec)
        self.assertEqual(pos["b"], ("L2", 5))
        self.assertEqual(pos["c"][1], 3)

    def test_pinned_row_does_not_collide_with_free_nodes(self):
        spec = lineage([{"id": "a"}, {"id": "b"}, {"id": "c", "lane": "L1", "row": 0}], [("a", "b")], lanes=[{"id": "L1"}, {"id": "L2"}])
        pos, _ = self.placed(spec)
        self.assertEqual(pos["c"], ("L1", 0))
        self.assertNotEqual(pos["a"], pos["c"])

    def test_sources_sit_next_to_their_consumer(self):
        spec = lineage([{"id": i} for i in ("s1", "x", "y", "z", "late")], [("s1", "x"), ("x", "y"), ("y", "z"), ("late", "z")])
        pos, res = self.placed(spec)
        lanes = [l["id"] for l in res["spec"]["lanes"]]
        self.assertEqual(lanes.index(pos["late"][0]), lanes.index(pos["z"][0]) - 1)

    def test_a_single_node_without_edges(self):
        res = render({"nodes": [{"id": "solo", "title": "Solo"}]})
        self.assertEqual(res["warnings"], [])
        ET.fromstring(res["svg"])

    def test_a_cycle_warns_and_still_renders(self):
        res = render(lineage([{"id": "a"}, {"id": "b"}], [("a", "b"), ("b", "a")]))
        self.assertTrue(any("cycle" in w for w in res["warnings"]), res["warnings"])
        ET.fromstring(res["svg"])

    def test_extra_lanes_are_added_when_the_given_ones_run_out(self):
        spec = lineage([{"id": i} for i in "abc"], [("a", "b"), ("b", "c")], lanes=[{"id": "only"}])
        res = render(spec)
        self.assertEqual(len(res["spec"]["lanes"]), 3)
        self.assertTrue(any("lane(s) added" in w for w in res["warnings"]))

    def test_layer_names_the_generated_lanes(self):
        _, res = self.placed(example("lineage-auto"))
        self.assertEqual([l["label"] for l in res["spec"]["lanes"]], ["raw", "staging", "marts", "aggregates", "dashboards"])

    def test_no_line_runs_through_a_card(self):
        for name in ("lineage-auto", "lineage-auto-pinned"):
            self.assertEqual(render(example(name))["warnings"], [], name)

    def test_resolve_output_is_a_fully_pinned_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec, resolved, out = Path(tmp) / "s.json", Path(tmp) / "r.json", Path(tmp) / "o.svg"
            spec.write_text(json.dumps(example("lineage-auto")))
            self.assertEqual(run("render_diagram.py", spec, out, "--resolve", resolved).returncode, 0)
            data = json.load(open(resolved))
            self.assertTrue(all("lane" in n and "row" in n for n in data["nodes"]))
            again = Path(tmp) / "o2.svg"
            self.assertEqual(run("render_diagram.py", resolved, again).returncode, 0)
            self.assertEqual(out.read_bytes(), again.read_bytes())    # pinning changes nothing until someone edits it


class Themes(unittest.TestCase):
    def test_palette_overrides_a_token(self):
        spec = example("lineage-by-stage")
        spec["options"]["palette"] = {"bg": "#123456"}
        self.assertIn('fill="#123456"', render(spec)["svg"])

    def test_state_colour_override(self):
        spec = example("lineage-by-stage")
        spec["options"]["palette"] = {"states": {"unchanged": {"line": "#ff00aa"}}}
        self.assertIn("#ff00aa", render(spec)["svg"])

    def test_a_bad_colour_is_rejected(self):
        spec = example("lineage-by-stage")
        spec["options"]["palette"] = {"bg": '#fff" onload="x'}
        with self.assertRaises(SystemExit):
            render(spec)

    def test_unknown_token_is_rejected(self):
        spec = example("lineage-by-stage")
        spec["options"]["palette"] = {"backround": "#fff"}
        with self.assertRaises(SystemExit):
            render(spec)

    def test_font_override_is_escaped(self):
        spec = example("lineage-by-stage")
        spec["options"]["font"] = "Inter, Arial, sans-serif"
        self.assertIn('font-family="Inter, Arial, sans-serif"', render(spec)["svg"])
        spec["options"]["font"] = 'x"><script>'
        with self.assertRaises(SystemExit):
            render(spec)

    def test_icon_path_is_checked(self):
        spec = lineage([{"id": "a", "lane": "x", "row": 0, "icon": "M2,2 L20,20"}], [], lanes=[{"id": "x"}])
        self.assertIn("M2,2 L20,20", render(spec)["svg"])
        spec["nodes"][0]["icon"] = 'M0 0"/><script>'
        with self.assertRaises(SystemExit):
            render(spec)

    def test_glyph_is_inferred_from_the_name(self):
        res = render(lineage([{"id": "s3_landing"}, {"id": "looker_dash"}], [("s3_landing", "looker_dash")]))
        glyphs = {n["id"]: n["glyph"] for n in res["spec"]["nodes"]}
        self.assertEqual(glyphs, {"s3_landing": "bucket", "looker_dash": "chart"})

    def test_every_theme_renders_valid_xml(self):
        for theme in ("light", "dark", "print"):
            for name in ("lineage-by-stage", "sequence-pipeline", "star-auto"):
                ET.fromstring(render(example(name), theme=theme)["svg"])

    def test_cli_theme_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.svg"
            proc = run("render_diagram.py", EXAMPLES / "lineage-by-stage.json", out, "--theme-file", EXAMPLES / "theme-brand.json")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("#fbf7f0", out.read_text())


class Frames(unittest.TestCase):
    def test_frozen_frames_have_no_smil_and_the_packet_moves(self):
        spec = example("lineage-by-stage")
        a = render(spec, animate="packets", t=0.3)
        b = render(spec, animate="packets", t=0.9)
        self.assertNotIn("animateMotion", a["svg"])
        self.assertIsNotNone(a["loop"])
        dots = lambda svg: re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)    # noqa: E731
        self.assertTrue(dots(a["svg"]) and dots(b["svg"]))
        self.assertNotEqual(dots(a["svg"]), dots(b["svg"]))

    def test_the_loop_repeats(self):
        spec = example("sequence-pipeline")
        loop = render(spec, animate="packets", t=0)["loop"]
        self.assertEqual(render(spec, animate="packets", t=1.1)["svg"], render(spec, animate="packets", t=1.1 + loop)["svg"])

    def test_still_diagrams_have_no_loop(self):
        self.assertIsNone(render(example("lineage-by-stage"))["loop"])

    def test_packets_stay_on_their_line(self):
        res = render(example("sequence-pipeline"), animate="packets", t=0.4)
        for cx, cy in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', res["svg"]):
            self.assertTrue(0 <= float(cx) <= res["width"] and 0 <= float(cy) <= res["height"])


class DbtImport(unittest.TestCase):
    manifest = json.load(open(EXAMPLES / "dbt-manifest-sample.json"))

    def test_nodes_edges_and_layers(self):
        spec, counts = import_dbt.build(self.manifest)
        self.assertEqual(counts["sources"], 6)           # five sources and one seed
        self.assertEqual(counts["marts"], 5)
        self.assertEqual(counts["exposures"], 1)
        ids = {n["id"] for n in spec["nodes"]}
        self.assertIn("shop_orders", ids)
        self.assertIn({"from": "stg_orders", "to": "int_order_payments"}, spec["edges"])
        self.assertNotIn("country_codes", [n["id"] for n in spec["nodes"] if "lane" in n and n["lane"] != "sources"])
        self.assertEqual(check(spec)[0], [])

    def test_ancestors_selector(self):
        spec, _ = import_dbt.build(self.manifest, select="+fct_orders")
        ids = {n["id"] for n in spec["nodes"]}
        self.assertIn("shop_orders", ids)
        self.assertIn("dim_customers", ids)
        self.assertNotIn("agg_daily_revenue", ids)
        self.assertNotIn("revenue_dashboard", ids)

    def test_depth_limited_selector(self):
        spec, _ = import_dbt.build(self.manifest, select="1+fct_orders")
        self.assertEqual({n["id"] for n in spec["nodes"]}, {"fct_orders", "int_order_payments", "dim_customers"})

    def test_descendants_tag_and_exclude(self):
        spec, _ = import_dbt.build(self.manifest, select="fct_orders+ tag:core", exclude="tag:legacy")
        ids = {n["id"] for n in spec["nodes"]}
        self.assertIn("agg_daily_revenue", ids)
        self.assertIn("dim_products", ids)
        self.assertNotIn("legacy_report", ids)

    def test_intersection(self):
        spec, _ = import_dbt.build(self.manifest, select="tag:core,tag:finance")
        self.assertEqual({n["id"] for n in spec["nodes"]}, {"fct_orders"})

    def test_columns_carry_pk_and_fk_from_tests(self):
        spec, _ = import_dbt.build(self.manifest, select="fct_orders", columns=6)
        cols = {c["name"]: c["key"] for c in spec["nodes"][0]["columns"]}
        self.assertEqual(cols["order_id"], "PK")
        self.assertEqual(cols["customer_id"], "FK")

    def test_imported_spec_renders_without_warnings(self):
        spec, _ = import_dbt.build(self.manifest, exclude="tag:legacy", columns=4)
        self.assertEqual(render(spec)["warnings"], [])

    def test_too_many_nodes_is_refused_with_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "s.json"
            proc = run("import_dbt.py", EXAMPLES / "dbt-manifest-sample.json", "-o", out, "--max-nodes", "5")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--select", proc.stderr)


class DdlImport(unittest.TestCase):
    sql = (EXAMPLES / "billing-schema.sql").read_text()

    def test_tables_keys_and_foreign_keys(self):
        spec = import_ddl.build(self.sql)
        by_id = {n["id"]: n for n in spec["nodes"]}
        self.assertEqual(set(by_id), {"customers", "plans", "subscriptions", "invoices", "payments"})
        keys = {c["name"]: c["key"] for c in by_id["subscriptions"]["columns"]}
        self.assertEqual(keys, {"subscription_id": "PK", "customer_id": "FK", "plan_id": "FK", "started_on": None})
        edges = {(e["from"], e["to"], e["from_col"], e["to_col"]) for e in spec["edges"]}
        self.assertEqual(edges, {("subscriptions", "customers", "customer_id", "customer_id"),
                                 ("subscriptions", "plans", "plan_id", "plan_id"),
                                 ("invoices", "subscriptions", "subscription_id", "subscription_id"),
                                 ("payments", "invoices", "invoice_id", "invoice_id")})

    def test_long_types_are_shortened(self):
        types = {c["name"]: c["type"] for n in import_ddl.build(self.sql)["nodes"] for c in n["columns"]}
        self.assertEqual(types["created_at"], "timestamptz")
        self.assertEqual(types["price"], "numeric(10,2)")

    def test_views_and_indexes_are_skipped(self):
        self.assertEqual(len(import_ddl.build(self.sql)["nodes"]), 5)

    def test_a_star_is_detected(self):
        sql = """CREATE TABLE dim_a (a_id int PRIMARY KEY); CREATE TABLE dim_b (b_id int PRIMARY KEY);
                 CREATE TABLE dim_c (c_id int PRIMARY KEY, d_id int REFERENCES dim_d(d_id)); CREATE TABLE dim_d (d_id int PRIMARY KEY);
                 CREATE TABLE fct (id int PRIMARY KEY, a_id int REFERENCES dim_a(a_id), b_id int REFERENCES dim_b(b_id),
                                   c_id int REFERENCES dim_c(c_id));"""
        spec = import_ddl.build(sql)
        self.assertEqual((spec.get("layout"), spec.get("center")), ("star", "fct"))
        self.assertEqual(render(spec)["warnings"], [])

    def test_a_chain_is_not_a_star(self):
        self.assertNotIn("layout", import_ddl.build(self.sql))

    def test_dialect_quoting(self):
        sql = 'CREATE TABLE IF NOT EXISTS `db`.`Orders` (`Id` INT, `Total` DECIMAL(10,2), PRIMARY KEY (`Id`)) ENGINE=InnoDB;'
        node = import_ddl.build(sql)["nodes"][0]
        self.assertEqual((node["id"], node["columns"][0]), ("Orders", {"name": "Id", "type": "int", "key": "PK"}))

    def test_composite_foreign_key_makes_one_edge_per_column(self):
        sql = """CREATE TABLE a (x int, y int, PRIMARY KEY (x, y));
                 CREATE TABLE b (id int PRIMARY KEY, x int, y int, FOREIGN KEY (x, y) REFERENCES a (x, y));"""
        self.assertEqual(len(import_ddl.build(sql)["edges"]), 2)

    def test_imported_spec_renders_without_warnings(self):
        self.assertEqual(render(import_ddl.build(self.sql))["warnings"], [])


class Diff(unittest.TestCase):
    def test_nodes_added_removed_changed(self):
        out, stats = diff_specs.diff(example("lineage-by-stage"), example("lineage-by-stage-v2"))
        states = {n["id"]: n["state"] for n in out["nodes"]}
        self.assertEqual((states["raw_stores"], states["dim_stores"], states["agg_p"], states["fct"], states["stg_orders"]),
                         ("added", "added", "removed", "modified", "unchanged"))
        self.assertEqual(stats["nodes"], [2, 1, 1])

    def test_edges_added_and_removed(self):
        out, _ = diff_specs.diff(example("lineage-by-stage"), example("lineage-by-stage-v2"))
        edge = {(e["from"], e["to"]): e["state"] for e in out["edges"]}
        self.assertEqual(edge[("dim_stores", "fct")], "added")
        self.assertEqual(edge[("fct", "agg_p")], "removed")
        self.assertEqual(edge[("raw_orders", "stg_orders")], "unchanged")

    def test_column_level_changes(self):
        out, _ = diff_specs.diff(example("star-schema"), example("star-schema-v2"))
        fact = next(n for n in out["nodes"] if n["id"] == "fct")
        states = {c["name"]: c["state"] for c in fact["columns"]}
        self.assertEqual((states["discount_amount"], states["line_number"], states["order_id"]), ("added", "removed", "unchanged"))
        self.assertEqual(fact["state"], "modified")

    def test_removed_column_keeps_its_place(self):
        out, _ = diff_specs.diff(example("star-schema"), example("star-schema-v2"))
        names = [c["name"] for c in next(n for n in out["nodes"] if n["id"] == "fct")["columns"]]
        self.assertEqual(names[:2], ["order_id", "line_number"])

    def test_diff_turns_labels_and_legend_on(self):
        out, _ = diff_specs.diff(example("lineage-by-stage"), example("lineage-by-stage-v2"))
        svg = render(out)["svg"]
        for word in ("ADDED", "CHANGED", "REMOVED", "Added 4", "Changed 1", "Removed 2"):
            self.assertIn(word, svg)

    def test_removed_node_never_lands_on_a_new_one(self):
        old = {"nodes": [{"id": "a", "lane": "x", "row": 0}], "lanes": [{"id": "x"}], "edges": []}
        new = {"nodes": [{"id": "b", "lane": "x", "row": 0}], "lanes": [{"id": "x"}], "edges": []}
        out, _ = diff_specs.diff(old, new)
        cells = [(n["lane"], n["row"]) for n in out["nodes"]]
        self.assertEqual(len(set(cells)), 2)
        self.assertEqual(check(out)[0], [])

    def test_identical_specs_show_no_change(self):
        out, stats = diff_specs.diff(example("star-schema"), example("star-schema"))
        self.assertEqual(stats["details"], [])
        self.assertTrue(all(n["state"] == "unchanged" for n in out["nodes"]))

    def test_state_synonyms_are_accepted(self):
        spec = lineage([{"id": "a", "state": "deleted"}, {"id": "b", "state": "new"}, {"id": "c", "state": "changed"}], [("a", "b")])
        self.assertEqual({n["id"]: n["state"] for n in render(spec)["spec"]["nodes"]}, {"a": "removed", "b": "added", "c": "modified"})

    def test_sequence_diff(self):
        out, stats = diff_specs.diff(example("sequence-pipeline"), example("sequence-pipeline-v2"))
        self.assertEqual(stats["edges"], [1, 1, 1])
        states = [m["state"] for ph in out["phases"] for m in ph["messages"]]
        self.assertEqual((states.count("added"), states.count("removed"), states.count("modified")), (1, 1, 1))
        self.assertEqual(render(out)["warnings"], [])

    def test_cannot_compare_different_kinds(self):
        with self.assertRaises(SystemExit):
            diff_specs.diff(example("lineage-by-stage"), example("sequence-pipeline"))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_git_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = Path(tmp) / "spec.json"
            git = lambda *a: subprocess.run(["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, check=True)  # noqa: E731
            git("init", "-q")
            spec.write_text(json.dumps(example("star-schema")))
            git("add", "spec.json")
            git("commit", "-q", "-m", "v1")
            spec.write_text(json.dumps(example("star-schema-v2")))
            out = Path(tmp) / "diff.json"
            proc = run("diff_specs.py", "--git", "HEAD", spec, "-o", out, "--summary")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("columns", proc.stdout)
            self.assertTrue(any(c.get("state") == "added" for n in json.load(open(out))["nodes"] for c in n.get("columns", [])))


class SkillPackage(unittest.TestCase):
    def test_front_matter(self):
        text = (SKILL / "SKILL.md").read_text()
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(m)
        front = m.group(1)
        self.assertEqual(re.search(r"^name: (\S+)$", front, re.M).group(1), SKILL.name)
        desc = re.search(r"^description: >-\n((?:  .*\n?)+)", front + "\n", re.M).group(1)
        self.assertLessEqual(len(" ".join(desc.split())), 1024)
        try:
            import yaml
        except ImportError:
            return
        data = yaml.safe_load(front)
        self.assertEqual(set(data), {"name", "description"})

    def test_files_named_in_skill_md_exist(self):
        text = (SKILL / "SKILL.md").read_text()
        for rel in set(re.findall(r"`((?:scripts|assets|references)/[\w./-]+)`", text)):
            self.assertTrue((SKILL / rel).exists(), rel)

    def test_scripts_run_under_isolated_python(self):
        for script in ("render_diagram.py", "export.py", "diff_specs.py", "import_dbt.py", "import_ddl.py"):
            self.assertEqual(run(script, "--help").returncode, 0, script)

    def test_no_python_newer_than_3_8_syntax(self):
        import ast
        for path in list(SCRIPTS.glob("*.py")) + list((ROOT / "tools").glob("*.py")) + list((ROOT / "hooks").glob("*.py")):
            ast.parse(path.read_text(), feature_version=(3, 8))


class RoutingHook(unittest.TestCase):
    """hooks/route_to_skill.py adds a reminder to data-diagram prompts and stays silent otherwise."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "hooks"))
        import route_to_skill
        cls.hook = route_to_skill

    def labelled(self):
        for name in ("trigger-evals.json", "trigger-holdout.json"):
            yield from json.load(open(ROOT / "evals" / name))

    def test_matches_every_query_that_should_use_the_skill(self):
        missed = [e["query"] for e in self.labelled() if e["should_trigger"] and not self.hook.wants_diagram(e["query"])]
        self.assertEqual(missed, [])

    def test_stays_quiet_on_near_misses(self):
        wrong = [e["query"] for e in self.labelled() if not e["should_trigger"] and self.hook.wants_diagram(e["query"])]
        self.assertEqual(wrong, [])

    def test_explicit_other_tools_are_respected(self):
        for prompt in ("draw the data lineage in mermaid", "make an excalidraw of our warehouse", "plantuml sequence diagram of the etl"):
            self.assertFalse(self.hook.wants_diagram(prompt), prompt)

    def test_hook_protocol(self):
        proc = subprocess.run([sys.executable, "-I", str(ROOT / "hooks" / "route_to_skill.py")], input=json.dumps({"prompt": "draw an ERD from schema.sql"}),
                              capture_output=True, text=True)
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("plumbline-svg-diagrams", out["additionalContext"])
        quiet = subprocess.run([sys.executable, "-I", str(ROOT / "hooks" / "route_to_skill.py")], input=json.dumps({"prompt": "write a sql query"}),
                               capture_output=True, text=True)
        self.assertEqual((quiet.returncode, quiet.stdout), (0, ""))
        bad = subprocess.run([sys.executable, "-I", str(ROOT / "hooks" / "route_to_skill.py")], input="not json", capture_output=True, text=True)
        self.assertEqual((bad.returncode, bad.stdout), (0, ""))

    def test_plugin_files_are_consistent(self):
        plugin = json.load(open(ROOT / ".claude-plugin" / "plugin.json"))
        market = json.load(open(ROOT / ".claude-plugin" / "marketplace.json"))
        hooks = json.load(open(ROOT / "hooks" / "hooks.json"))
        self.assertEqual(plugin["name"], market["plugins"][0]["name"])
        command = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertIn("route_to_skill.py", command)
        self.assertTrue((ROOT / "hooks" / "route_to_skill.py").exists())


@unittest.skipUnless(shutil.which("node") and not os.environ.get("PLUMBLINE_SKIP_EXPORT"), "needs Node.js")
class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="plumbline-test-")
        cls.env = {**os.environ, "PLUMBLINE_CACHE": os.environ.get("PLUMBLINE_CACHE", os.path.join(cls.tmp, "cache"))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def export(self, src, name, *args):
        out = Path(self.tmp) / name
        proc = run("export.py", src, out, *args, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return out

    def test_png(self):
        data = self.export(ROOT / "examples" / "star-auto.svg", "a.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width = int.from_bytes(data[16:20], "big")
        self.assertEqual(width, 2 * int(re.search(r'width="(\d+)"', (ROOT / "examples" / "star-auto.svg").read_text()).group(1)))

    def test_pdf(self):
        data = self.export(ROOT / "examples" / "lineage-by-stage.svg", "a.pdf").read_bytes()
        self.assertTrue(data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/MediaBox", data)

    def test_gif_has_many_frames_and_loops(self):
        out = self.export(EXAMPLES / "lineage-by-stage.json", "a.gif", "--fps", "6", "--max-width", "600")
        data = out.read_bytes()
        self.assertEqual(data[:6], b"GIF89a")
        self.assertGreaterEqual(data.count(b"\x21\xf9\x04"), 40)       # one graphic control block per frame
        self.assertIn(b"NETSCAPE2.0", data)                              # loop forever

    def test_gif_needs_a_spec(self):
        out = Path(self.tmp) / "b.gif"
        proc = run("export.py", ROOT / "examples" / "lineage-by-stage.svg", out, env=self.env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("spec", proc.stderr)

    def test_png_from_a_spec_with_a_brand_theme(self):
        self.export(EXAMPLES / "lineage-by-stage.json", "c.png", "--theme-file", EXAMPLES / "theme-brand.json")


if __name__ == "__main__":
    unittest.main()
