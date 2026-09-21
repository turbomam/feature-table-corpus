"""Semantic regressions and real-data query controls for the harmonized profile."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import duckdb
import yaml
from linkml_runtime.utils.schemaview import SchemaView

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_duckdb import build_database
from flat_profile_audit import audit
from query_duckdb import by_attribute, interval_overlap, multiple_pfams
from validate_closed import make_validator, validation_errors

SCHEMA = ROOT / "schema/ber_feature_model.yaml"
EXAMPLE = ROOT / "examples/one-biosample-sequencing/harmonized.yaml"
PFAMS = ROOT / "examples/multiple-pfams/harmonized.yaml"


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = make_validator(SCHEMA)
        cls.example = yaml.safe_load(EXAMPLE.read_text())

    def reject(self, change, expected):
        data = copy.deepcopy(self.example)
        change(data)
        errors = validation_errors(data, self.validator)
        self.assertTrue(any(expected in e for e in errors), errors)

    def test_real_examples_and_source_manifest(self):
        manifest = yaml.safe_load((ROOT / "examples/source-artifacts.yaml").read_text())
        artifacts = {a["url"]: a for a in manifest["artifacts"]}
        self.assertEqual(len(artifacts), len(manifest["artifacts"]))
        cited = set()
        for path in ROOT.glob("examples/*/harmonized.yaml"):
            with self.subTest(example=path):
                data = yaml.safe_load(path.read_text())
                self.assertEqual(validation_errors(data, self.validator), [])
                for row in data["contigs"] + data["features"]:
                    self.assertTrue(row["generated_by"])
                    self.assertTrue(row["source_files"])
                    for url in row["source_files"]:
                        artifact = artifacts[url]
                        self.assertRegex(artifact["md5"], r"^[0-9a-f]{32}$")
                        self.assertIn(artifact["workflow_execution"], url)
                        cited.add(url)
                    self.assertIn(row["generated_by"],
                                  {artifacts[u]["workflow_execution"] for u in row["source_files"]})
        self.assertEqual(cited, set(artifacts))

    def test_shape_constraints(self):
        for field, value, expected in (
            ("start", 0, "minimum"), ("end", 0, "minimum"),
            ("phase", -1, "minimum"), ("phase", 3, "maximum"),
            ("phase", 1.5, "integer"), ("coordinate_system", "genomic", "not one of"),
            ("typo_field", "x", "Additional properties"),
        ):
            with self.subTest(field=field, value=value):
                self.reject(lambda d: d["features"][0].__setitem__(field, value), expected)
        for field in ("start", "end", "feature_id", "seqid", "coordinate_system"):
            with self.subTest(missing=field):
                self.reject(lambda d: d["features"][0].pop(field), "required")
        self.reject(lambda d: d["contigs"][0].__setitem__("length_bp", 0), "minimum")

    def test_semantic_constraints(self):
        cases = (
            (lambda d: d["features"][0].update(start=854), "start must be <= end"),
            (lambda d: d["features"][0].update(end=99999), "contig length"),
            (lambda d: d["features"][0].update(seqid="missing"), "unknown seqid"),
            (lambda d: d["features"][1].update(parent=["missing"]), "unknown parent"),
            (lambda d: d["features"][1].pop("parent"), "require a parent CDS"),
            (lambda d: d["features"][1].update(end=250), "translated_sequence length"),
            (lambda d: d["features"][1].update(seqid=d["contigs"][1]["contig_id"]), "different contig"),
            (lambda d: d["features"][0].update(type="gene"), "must be a contig-relative CDS"),
            (lambda d: d["features"][1]["parent"].append(d["features"][0]["feature_id"]), "duplicate parent"),
            (lambda d: d["features"].append(copy.deepcopy(d["features"][0])), "duplicate feature_id"),
            (lambda d: d["contigs"].append(copy.deepcopy(d["contigs"][0])), "duplicate contig_id"),
            (lambda d: d["features"][0].update(parent=[d["features"][0]["feature_id"]]), "parent cycle"),
            (lambda d: d["features"][0].update(parent=[d["features"][1]["feature_id"]]), "parent cycle"),
        )
        for change, expected in cases:
            with self.subTest(expected=expected):
                self.reject(change, expected)

    def test_legitimate_absence_and_boundary_values(self):
        data = copy.deepcopy(self.example)
        data["features"][0].pop("translated_sequence")
        for phase in (0, 1, 2):
            data["features"][0]["phase"] = phase
            self.assertEqual(validation_errors(data, self.validator), [])
        data["features"][0].update(start=1, end=1)
        self.assertEqual(validation_errors(data, self.validator), [])
        self.assertEqual(validation_errors({}, self.validator), [])

    def test_standalone_generic_attribute_module(self):
        validator = make_validator(ROOT / "schema/attributes.yaml", "Attribute")
        for key, value in (("instrument", "NovaSeq"), ("evalue", "1e-42"), ("note", "a=b;c,d")):
            self.assertEqual(validation_errors({"key": key, "value": value}, validator, "Attribute"), [])
        self.assertTrue(validation_errors({"key": "incomplete"}, validator, "Attribute"))
        data = copy.deepcopy(self.example)
        data["features"][0]["attributes"] = [
            {"key": "note", "value": "first"}, {"key": "note", "value": "second"}
        ]
        self.assertEqual(validation_errors(data, self.validator), [])

    def test_flat_audit_follows_imports_and_inheritance(self):
        rows = {(r[0], r[1]): r for r in audit(SchemaView(str(SCHEMA)))}
        self.assertEqual(rows['Feature', 'attributes'][5], 'multivalued class reference')
        self.assertEqual(rows['Feature', 'seqid'][5], 'identified class reference')
        self.assertIn(('Attribute', 'key'), rows)
        view = SchemaView('''
id: https://example.org/test
name: audit-test
imports: [linkml:types]
prefixes:
  linkml: https://w3id.org/linkml/
default_range: string
slots:
  id:
    identifier: true
  many_mixin:
    mixin: true
    multivalued: true
  many:
    mixins: [many_mixin]
  class_mixin:
    mixin: true
    range: Child
  mixed_ref:
    mixins: [class_mixin]
  ref:
    range: Child
classes:
  Base:
    slots: [id]
  Mixin:
    mixin: true
    slots: [many]
  Child:
    is_a: Base
    mixins: [Mixin]
  Holder:
    slots: [mixed_ref]
    attributes:
      ref:
        range: Child
      inline_many:
        is_a: many_mixin
  Unrelated:
    attributes:
      inline_many:
        range: string
''')
        rows = {(r[0], r[1]): r for r in audit(view)}
        self.assertEqual(rows['Child', 'many'][5], 'multivalued scalar')
        self.assertEqual(rows['Holder', 'ref'][5], 'identified class reference')
        self.assertEqual(rows['Holder', 'mixed_ref'][5], 'identified class reference')
        self.assertEqual(rows['Holder', 'inline_many'][5], 'multivalued scalar')
        self.assertEqual(rows['Unrelated', 'inline_many'][5], 'admissible')
        view.get_slot('mixed_ref').range = 'UndefinedClass'
        with self.assertRaisesRegex(ValueError, 'unresolved range'):
            audit(SchemaView(view.schema))
        view.get_slot('mixed_ref').range = None
        view.get_class('Holder').attributes['ref'].any_of = [dict(range='string')]
        with self.assertRaisesRegex(ValueError, 'range expressions'):
            audit(SchemaView(view.schema))

    def test_missing_import_is_reported_without_traceback(self):
        scratch = ROOT / 'local/test-tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as work:
            path = Path(work) / 'missing-import.yaml'
            path.write_text('id: https://example.org/missing\nname: missing\nimports: [absent]\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/flat_profile_audit.py'), str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('REFUSING to audit', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.db = self.work / "example.duckdb"
        build_database(SCHEMA, EXAMPLE, self.db)

    def connect(self):
        con = duckdb.connect(str(self.db))
        self.addCleanup(con.close)
        return con

    def test_mixed_evidence_and_crispr_are_not_multiple_pfams(self):
        self.assertEqual(multiple_pfams(self.connect()), [])

    def test_real_multiple_pfams_and_distinctness(self):
        build_database(SCHEMA, PFAMS, self.db)
        con = self.connect()
        rows = multiple_pfams(con)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091")
        self.assertEqual(rows[0][2:], (3, ["PF13358", "PF13518", "PF13592"]))
        self.assertEqual(multiple_pfams(con, ["PF13358", "PF13592"])[0][2], 2)
        self.assertEqual(multiple_pfams(con, ["PF04183", "PF06276"]), [])
        # Synthetic negative control: repeated copies of one domain are not distinct Pfams.
        con.execute("UPDATE feature SET type = 'PF13358' WHERE coordinate_system = 'protein'")
        self.assertEqual(multiple_pfams(con), [])

    def test_coordinate_spaces_and_inclusive_endpoints(self):
        con = self.connect()
        gene = "nmdc:wfmgas-11-19jh9v28.1_scf_1_c1_104_853"
        contig = "nmdc:wfmgas-11-19jh9v28.1_scf_1_c1"
        rows = interval_overlap(con, contig, 104, 104)
        self.assertEqual([r[0] for r in rows], [gene])
        self.assertEqual([r[0] for r in interval_overlap(con, contig, 853, 853)], [gene])
        self.assertEqual(interval_overlap(con, contig, 854, 854), [])
        self.assertEqual(len(interval_overlap(con, gene, 13, 13, "protein")), 5)
        self.assertEqual(interval_overlap(con, contig, 13, 13, "protein"), [])
        self.assertEqual(interval_overlap(con, gene, 13, 13, "contig"), [])
        self.assertEqual(interval_overlap(con, gene, 250, 250, "protein"), [])
        for start, end in ((0, 1), (2, 1)):
            with self.assertRaises(ValueError):
                interval_overlap(con, contig, start, end)

    def test_attribute_lookup_and_source_round_trip(self):
        con = self.connect()
        gene = "nmdc:wfmgas-11-19jh9v28.1_scf_1_c1_104_853"
        self.assertEqual(by_attribute(con, "Name", "adh_short_C2"), [(gene + "_pfam",)])
        self.assertEqual(by_attribute(con, "Name", "' OR true --"), [])
        data = yaml.safe_load(EXAMPLE.read_text())
        row = con.execute("SELECT generated_by, source_files, attributes FROM feature WHERE feature_id = ?", [gene]).fetchone()
        self.assertEqual(row, tuple(data["features"][0][k] for k in ("generated_by", "source_files", "attributes")))

    def test_failed_validation_preserves_existing_database(self):
        data = yaml.safe_load(EXAMPLE.read_text())
        data["features"][0]["start"] = 9999
        bad = self.work / "invalid.yaml"
        bad.write_text(yaml.safe_dump(data))
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, "start must be <= end"):
            build_database(SCHEMA, bad, self.db)
        self.assertEqual(self.db.read_bytes(), before)
        fresh = self.work / "should-not-exist.duckdb"
        with self.assertRaises(ValueError):
            build_database(SCHEMA, bad, fresh)
        self.assertFalse(fresh.exists())
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_closed.py"),
                                 str(SCHEMA), str(bad), "Dataset"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("start must be <= end", result.stdout)

    def test_valid_rebuild_and_query_cli(self):
        self.assertEqual(build_database(SCHEMA, EXAMPLE, self.db), (3, 15))
        build_database(SCHEMA, PFAMS, self.db)
        result = subprocess.run([sys.executable, str(ROOT / "scripts/query_duckdb.py"),
                                 str(self.db), "pfams", "PF13358", "PF13592"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0][2:], [2, ["PF13358", "PF13592"]])

    def test_database_error_rolls_back_table_replacement(self):
        # LinkML integer permits an arbitrarily large value; this physical BIGINT mapping does not.
        data = yaml.safe_load(EXAMPLE.read_text())
        data["contigs"][0]["length_bp"] = 2**100
        oversized = self.work / "oversized.yaml"
        oversized.write_text(yaml.safe_dump(data))
        with self.assertRaises(duckdb.Error):
            build_database(SCHEMA, oversized, self.db)
        con = self.connect()
        self.assertEqual(con.execute("SELECT count(*) FROM feature").fetchone(), (15,))
        self.assertEqual(con.execute("SELECT length_bp FROM contig ORDER BY contig_id LIMIT 1").fetchone(), (1754,))


if __name__ == "__main__":
    unittest.main()
