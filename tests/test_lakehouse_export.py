"""Parquet written through linkml-store reads back equal to the Dataset, and the checks can fail."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from linkml_runtime import SchemaView
from linkml_store.api.stores.duckdb import mappings as store_mappings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lakehouse_export as lakehouse
import img_functional_map as mapping
from convert_features import import_source
from insdc_profile import PROFILE
from validate_closed import load_validated

SCHEMA = ROOT / "model/schema/ber_feature_model.yaml"
EXAMPLE = ROOT / "model/examples/one-biosample-sequencing/harmonized.yaml"
IMG_FIXTURE = ROOT / "tests/fixtures/img-functional-gff/constructed.gff"
PHIX = ROOT / "corpus/sources/ncbi-refseq/NC_001422.1_2026-09-21.gb"


class LakehouseExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = SchemaView(str(SCHEMA))

    def setUp(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="lakehouse ", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def write_json(self, name, data):
        path = self.work / name
        path.write_text(json.dumps(data))
        return path

    def exported(self, data_path, name="out"):
        summary = lakehouse.export(SCHEMA, data_path, self.work / name)
        return summary, self.work / name

    def test_example_reads_back_with_schema_types(self):
        summary, out = self.exported(EXAMPLE)
        self.assertEqual({k: v["rows"] for k, v in summary["collections"].items()},
                         {name: len(load_validated(SCHEMA, EXAMPLE).get(name) or [])
                          for name, _ in lakehouse.collections(self.view)})
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["contigs.parquet", "features.parquet"])
        features = pq.read_table(out / "features.parquet")
        self.assertEqual(features.column_names, list(self.view.class_slots("Feature")))
        schema = features.schema
        self.assertEqual(schema.field("score").type, pa.float64())
        self.assertEqual(schema.field("start").type, pa.int64())
        self.assertEqual(schema.field("is_selected").type, pa.bool_())
        self.assertEqual(schema.field("attributes").type,
                         pa.list_(pa.struct([("key", pa.string()), ("value", pa.string())])))
        rows = {r["feature_id"]: r for r in features.to_pylist()}
        self.assertIn(239.1, [r["score"] for r in rows.values()])
        self.assertEqual(sorted({r["is_selected"] for r in rows.values()}, key=str), [False, None, True])
        # Attributes flatten with one UNNEST; the count must equal the input's.
        expected = sum(len(f.get("attributes") or []) for f in load_validated(SCHEMA, EXAMPLE)["features"])
        flat = duckdb.sql(f"SELECT count(*) FROM (SELECT feature_id, unnest(attributes) "
                          f"FROM '{out / 'features.parquet'}')").fetchone()[0]
        self.assertEqual(flat, expected)
        self.assertGreater(expected, 0)

    def test_nested_locations_from_real_circular_record_round_trip(self):
        dataset = import_source(PHIX.read_bytes(), profile=PROFILE, reference_context="insdc:retained-records",
                                source_uri="urn:ftc:lakehouse")["dataset"]
        self.assertTrue(any(f.get("location", {}).get("crosses_origin") for f in dataset["features"]))
        _, out = self.exported(self.write_json("phix.json", dataset))
        read = pq.read_table(out / "features.parquet").to_pylist()
        self.assertEqual(len(read), 32)
        joined = next(r for r in read if r["location"] and r["location"]["crosses_origin"])
        self.assertEqual(len(joined["location"]["parts"]), 2)

    def test_img_mapped_dataset_and_empty_collection(self):
        dataset = mapping.forward(mapping.dialect.parse(IMG_FIXTURE))
        summary, out = self.exported(self.write_json("img.json", dataset))
        self.assertEqual(summary["collections"]["features"]["rows"], 10)
        # A Dataset with no features still gets a features file with every column.
        _, empty = self.exported(self.write_json("contigs-only.json", {"contigs": dataset["contigs"]}), "empty")
        table = pq.read_table(empty / "features.parquet")
        self.assertEqual(table.num_rows, 0)
        self.assertEqual(table.column_names, list(self.view.class_slots("Feature")))

    def test_checks_fail_on_changed_or_missing_rows(self):
        data = load_validated(SCHEMA, EXAMPLE)
        _, out = self.exported(EXAMPLE)
        written = {name: out / f"{name}.parquet" for name, _ in lakehouse.collections(self.view)}
        self.assertEqual(lakehouse.value_mismatches(self.view, data, written), [])
        self.assertEqual(lakehouse.count_mismatches(self.view, SCHEMA, EXAMPLE, written, self.work), [])
        # Negative control 1: change one attribute value in the Parquet file.
        rows = pq.read_table(written["features"]).to_pylist()
        rows[0]["attributes"][0]["value"] += " changed"
        pq.write_table(pa.Table.from_pylist(rows, schema=pq.read_schema(written["features"])), written["features"])
        self.assertEqual(lakehouse.value_mismatches(self.view, data, written), ["features[0]: differs in ['attributes']"])
        # Negative control 2: drop a row; both checks report it.
        pq.write_table(pa.Table.from_pylist(rows[1:], schema=pq.read_schema(written["features"])), written["features"])
        self.assertIn("features: 14 Parquet rows, build_duckdb.py feature has 15",
                      lakehouse.count_mismatches(self.view, SCHEMA, EXAMPLE, written, self.work))
        self.assertEqual(lakehouse.value_mismatches(self.view, data, written),
                         ["features: 14 rows read back, 15 expected"])

    def test_linkml_store_default_types_lose_values(self):
        # Negative control 3: without the type fixes, linkml-store's 4-byte FLOAT
        # changes scores, and the value check says so.
        data = load_validated(SCHEMA, EXAMPLE)
        written = lakehouse.write_parquet(self.view, data, self.work)
        problems = lakehouse.value_mismatches(self.view, data, written)
        self.assertIn("contigs[0]: differs in ['lineage_confidence']", problems)
        self.assertTrue(any("['score']" in p for p in problems))

    def test_failed_check_publishes_nothing_and_restores_types(self):
        before = dict(store_mappings.TMAP)
        with patch.object(lakehouse, "value_mismatches", return_value=["features[0]: differs"]):
            with self.assertRaisesRegex(ValueError, "failed its checks"):
                lakehouse.export(SCHEMA, EXAMPLE, self.work / "refused")
        self.assertFalse((self.work / "refused").exists())
        self.assertEqual([p.name for p in self.work.iterdir()], [])
        self.assertEqual(store_mappings.TMAP, before)
        self.exported(EXAMPLE, "again")
        with self.assertRaisesRegex(ValueError, "already exists"):
            lakehouse.export(SCHEMA, EXAMPLE, self.work / "again")

    def test_command_line_requires_output_under_local(self):
        outside = Path(tempfile.gettempdir()) / "ftc-lakehouse-outside"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/lakehouse_export.py"), str(SCHEMA),
                                 str(EXAMPLE), str(outside)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("must be under", result.stderr)
        self.assertFalse(outside.exists())
        inside = self.work / "cli out"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/lakehouse_export.py"), str(SCHEMA),
                                 str(EXAMPLE), str(inside)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["collections"]["features"]["rows"], 15)


if __name__ == "__main__":
    unittest.main()
