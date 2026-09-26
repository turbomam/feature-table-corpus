"""Parquet written through linkml-store reads back equal to the Dataset, and the checks can fail."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import sqlalchemy as sqla
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
REAL_MKDIR = os.mkdir


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

    def rewrite(self, path, change):
        """Replace a Parquet file with change(rows, schema) -> Table."""
        table = pq.read_table(path)
        pq.write_table(change(table.to_pylist(), table.schema), path)

    def export_with(self, change, name="changed"):
        """Run export() with the features file rewritten after writing."""
        real = lakehouse.write_parquet

        def write_then_change(view, data, out_dir):
            written = real(view, data, out_dir)
            self.rewrite(written["features"], change)
            return written
        with patch.object(lakehouse, "write_parquet", write_then_change):
            return lakehouse.export(SCHEMA, EXAMPLE, self.work / name)

    def test_export_refuses_a_row_count_that_differs_from_build_duckdb(self):
        # The value check is switched off, so only the build_duckdb.py count can fail.
        with patch.object(lakehouse, "value_mismatches", return_value=[]):
            with self.assertRaisesRegex(ValueError, "features: 14 Parquet rows, build_duckdb.py feature has 15"):
                self.export_with(lambda rows, schema: pa.Table.from_pylist(rows[1:], schema=schema))
        self.assertFalse((self.work / "changed").exists())

    def test_export_refuses_a_column_type_the_schema_does_not_give(self):
        # An int64 is_selected compares equal to the booleans (True == 1), so only
        # the type check can see it.
        def as_int(rows, schema):
            table = pa.Table.from_pylist(rows, schema=schema)
            index = table.schema.get_field_index("is_selected")
            values = [None if v is None else int(v) for v in table.column(index).to_pylist()]
            return table.set_column(index, "is_selected", pa.array(values, pa.int64()))
        data = load_validated(SCHEMA, EXAMPLE)
        with self.assertRaisesRegex(ValueError, r"features: column types differ: \('is_selected', 'BOOLEAN'\) "
                                                r"!= \('is_selected', 'BIGINT'\)"):
            self.export_with(as_int)
        _, out = self.exported(EXAMPLE)
        written = {name: out / f"{name}.parquet" for name, _ in lakehouse.collections(self.view)}
        self.rewrite(written["features"], as_int)
        self.assertEqual(lakehouse.value_mismatches(self.view, data, written), [])

    def test_coordinates_above_32_bits(self):
        dataset = mapping.forward(mapping.dialect.parse(IMG_FIXTURE))
        dataset["features"][0].update(start=2**33, end=2**33 + 99)
        path = self.write_json("big.json", dataset)
        _, out = self.exported(path)
        first = pq.read_table(out / "features.parquet").to_pylist()[0]
        self.assertEqual((first["start"], first["end"]), (2**33, 2**33 + 99))
        # Negative control: linkml-store's own 4-byte INTEGER refuses the value.
        data = load_validated(SCHEMA, path)
        previous = lakehouse.widen_store_types({"float": sqla.Double})
        try:
            with self.assertRaisesRegex(Exception, "out of range"):
                lakehouse.write_parquet(self.view, data, self.work)
        finally:
            lakehouse.restore_store_types(previous)

    def test_type_table_guard(self):
        store_mappings.TMAP["float"] = sqla.Double
        try:
            with self.assertRaisesRegex(ValueError, "type table changed"):
                lakehouse.export(SCHEMA, EXAMPLE, self.work / "new" / "guarded")
        finally:
            store_mappings.TMAP["float"] = sqla.Float
        self.assertEqual([p.name for p in self.work.iterdir()], [])

    def notes(self, error):
        return "\n".join(getattr(error, "__notes__", []))

    def test_failures_leave_only_reported_new_directories(self):
        # Validation runs before any mkdir, so an invalid Dataset creates nothing.
        invalid = self.write_json("invalid.json", {"features": [{"feature_id": "x"}]})
        with self.assertRaises(ValueError):
            lakehouse.export(SCHEMA, invalid, self.work / "a" / "b" / "out")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["invalid.json"])
        # A failed check removes the staging directory, but leaves the parents it
        # made and names them.
        with patch.object(lakehouse, "value_mismatches", return_value=["features[0]: differs"]):
            with self.assertRaises(ValueError) as caught:
                lakehouse.export(SCHEMA, EXAMPLE, self.work / "c" / "d" / "out")
        self.assertEqual(list((self.work / "c" / "d").iterdir()), [])
        notes = self.notes(caught.exception)
        for made in (self.work / "c", self.work / "c" / "d"):
            self.assertIn(f"left behind, remove if unwanted: {made.resolve()}", notes)

    def test_make_parents_failure_reports_what_it_made(self):
        blocked = (self.work / "p1" / "p2").resolve()

        def mkdir(path, *args, **kwargs):
            if Path(path) == blocked:
                raise PermissionError("injected")
            return REAL_MKDIR(path, *args, **kwargs)
        with patch.object(os, "mkdir", mkdir):
            with self.assertRaises(PermissionError) as caught:
                lakehouse.export(SCHEMA, EXAMPLE, blocked / "out")
        self.assertTrue((self.work / "p1").is_dir())
        self.assertEqual(self.notes(caught.exception).count("left behind"), 1)
        self.assertIn(f"left behind, remove if unwanted: {blocked.parent}", self.notes(caught.exception))

    def test_dot_dot_in_the_output_path(self):
        keep = self.work / "keep"
        (keep / "out").mkdir(parents=True)
        # "new" does not exist, so an unresolved path would not see keep/out.
        with self.assertRaisesRegex(ValueError, "already exists"):
            lakehouse.export(SCHEMA, EXAMPLE, self.work / "new" / ".." / "keep" / "out")
        (keep / "out").rmdir()
        # On a failed check, the pre-existing empty keep stays and nothing else appears.
        with patch.object(lakehouse, "value_mismatches", return_value=["features[0]: differs"]):
            with self.assertRaises(ValueError):
                lakehouse.export(SCHEMA, EXAMPLE, self.work / "new" / ".." / "keep" / "out")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["keep"])
        self.assertEqual(list(keep.iterdir()), [])

    def test_directory_created_during_export_is_not_replaced(self):
        # Another process makes the empty target after the exists check and before
        # publication. A plain rename would silently replace it.
        target = self.work / "raced"
        real = lakehouse.write_parquet

        def write_then_race(view, data, out_dir):
            written = real(view, data, out_dir)
            target.mkdir()
            return written
        with patch.object(lakehouse, "write_parquet", write_then_race):
            with self.assertRaisesRegex(ValueError, "already exists"):
                lakehouse.export(SCHEMA, EXAMPLE, target)
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["raced"])

    def mkdir_with_race(self, when, race):
        """Patch os.mkdir so race() runs just before this call's mkdir of `when`."""
        def mkdir(path, *args, **kwargs):
            if Path(path) == when:
                race()
            return REAL_MKDIR(path, *args, **kwargs)
        return patch.object(os, "mkdir", mkdir)

    def test_file_added_to_the_new_directory_is_not_replaced(self):
        # Another process writes features.parquet into the output directory right
        # after this call creates it and before the files are linked in.
        target = self.work / "raced-file"
        theirs = target / "features.parquet"
        def mkdir(path, *args, **kwargs):
            result = REAL_MKDIR(path, *args, **kwargs)
            if Path(path) == target:
                theirs.write_bytes(b"theirs")
            return result
        with patch.object(os, "mkdir", mkdir):
            with self.assertRaisesRegex(ValueError, "already exists"):
                lakehouse.export(SCHEMA, EXAMPLE, target)
        self.assertEqual(theirs.read_bytes(), b"theirs")
        # contigs.parquet was linked before the conflict; it stays, and is reported.
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["contigs.parquet", "features.parquet"])

    def failing_link(self, target, replace_first=False):
        """Patch os.link to fail on features.parquet, after contigs.parquet is linked."""
        real_link = os.link

        def link(source, destination, *args, **kwargs):
            if Path(destination).name == "features.parquet":
                if replace_first:
                    theirs = target / "contigs.parquet"
                    os.unlink(theirs)
                    theirs.write_bytes(b"theirs")
                raise OSError("injected failure")
            return real_link(source, destination, *args, **kwargs)
        return patch.object(os, "link", link)

    def test_failure_after_partial_publication_leaves_and_reports(self):
        target = self.work / "partial"
        with self.failing_link(target):
            with self.assertRaisesRegex(OSError, "injected failure") as caught:
                lakehouse.export(SCHEMA, EXAMPLE, target)
        # Nothing in the target is deleted; the staging directory is gone.
        self.assertEqual(pq.read_metadata(target / "contigs.parquet").num_rows, 3)
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["partial"])
        notes = self.notes(caught.exception)
        for path in (target, target / "contigs.parquet"):
            self.assertIn(f"left behind, remove if unwanted: {path.resolve()}", notes)
        self.assertNotIn("features.parquet", notes)

    def test_staging_cleanup_failure_after_publication_reports_everything(self):
        # Publication succeeds, then removing the staging directory fails. The
        # complete target, its files and the staging directory are all named.
        target = self.work / "late"
        real_cleanup = tempfile.TemporaryDirectory.cleanup

        def cleanup(directory):
            if Path(directory.name).name.startswith(".late."):
                raise OSError("injected cleanup")
            return real_cleanup(directory)
        with patch.object(tempfile.TemporaryDirectory, "cleanup", cleanup):
            with self.assertRaisesRegex(OSError, "injected cleanup") as caught:
                lakehouse.export(SCHEMA, EXAMPLE, target)
        notes = self.notes(caught.exception)
        published = [target, *sorted(target.iterdir())]
        self.assertEqual([p.name for p in published[1:]], ["contigs.parquet", "features.parquet"])
        for path in published:
            self.assertIn(f"left behind, remove if unwanted: {path.resolve()}", notes)
        # The staging directory is named too. Its finalizer may remove it later,
        # so the note is checked rather than the disk.
        staging = [line for line in notes.splitlines() if f"{self.work.resolve()}/.late." in line]
        self.assertEqual(len(staging), 1)

    def test_concurrent_replacement_survives_a_failure(self):
        # Another process replaces the published contigs.parquet, then publication
        # fails. The export deletes nothing in the target, so theirs survives.
        target = self.work / "replaced"
        with self.failing_link(target, replace_first=True):
            with self.assertRaisesRegex(OSError, "injected failure"):
                lakehouse.export(SCHEMA, EXAMPLE, target)
        self.assertEqual((target / "contigs.parquet").read_bytes(), b"theirs")
        self.assertEqual([p.name for p in target.iterdir()], ["contigs.parquet"])

    def test_parent_made_by_another_process_is_not_reported_as_ours(self):
        # "shared" is absent when the export starts; another process creates it just
        # before this call's mkdir. Only "mine" is this run's and reported.
        shared = self.work / "shared"
        with self.mkdir_with_race(shared.resolve(), lambda: REAL_MKDIR(shared)):
            with patch.object(lakehouse, "value_mismatches", return_value=["features[0]: differs"]):
                with self.assertRaises(ValueError) as caught:
                    lakehouse.export(SCHEMA, EXAMPLE, shared / "mine" / "out")
        self.assertEqual([p.name for p in shared.iterdir()], ["mine"])
        notes = self.notes(caught.exception)
        self.assertIn(f"left behind, remove if unwanted: {(shared / 'mine').resolve()}", notes)
        self.assertNotIn(f"{shared.resolve()}\n", notes + "\n")

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
        outside_parent = Path(tempfile.mkdtemp(prefix="ftc-lakehouse-outside-"))
        self.addCleanup(shutil.rmtree, outside_parent, ignore_errors=True)
        outside = outside_parent / "out"
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
        malformed = self.work / "malformed.yaml"
        malformed.write_text("contigs: [1, 2\n")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/lakehouse_export.py"), str(SCHEMA),
                                 str(malformed), str(self.work / "from malformed")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.work / "from malformed").exists())


if __name__ == "__main__":
    unittest.main()
