"""The flat scalar-only profile is derived from the model, rejects nothing, and round-trips Datasets.

https://github.com/turbomam/feature-table-corpus/issues/45; scripts/flat_profile.py.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import flat_profile  # noqa: E402

EVERY_SLOT = ROOT / "tests/fixtures/flat-profile/every-slot.json"
EXAMPLES = [ROOT / "model/examples/one-biosample-sequencing/harmonized.yaml",
            ROOT / "model/examples/multiple-pfams/harmonized.yaml",
            ROOT / "model/examples/conversions/blat-bed12.json",
            ROOT / "model/examples/conversions/nmdc-pfam-context.json"]


class FlatProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = flat_profile.plan()
        cls.every = json.loads(EVERY_SLOT.read_text())

    def test_the_committed_schema_is_the_derived_one(self):
        self.assertEqual(flat_profile.FLAT.read_text(), flat_profile.schema_text(),
                         "run: just flat-profile")

    def test_the_audit_rejects_nothing(self):
        from linkml_runtime import SchemaView
        import flat_profile_audit
        rows = flat_profile_audit.audit(SchemaView(str(flat_profile.FLAT)))
        self.assertGreater(len(rows), 50)
        self.assertEqual([r for r in rows if r[5] != "admissible"], [])

    def test_the_fixture_sets_every_column_and_child_table(self):
        # A new model slot fails here until the fixture covers it, so the round trip below
        # keeps exercising every column.
        flat = flat_profile.flatten(self.every, self.tables)
        for table, _, _, columns, children in self.tables:
            with self.subTest(table):
                filled = {name for row in flat[table] for name in row}
                self.assertEqual(sorted({name for name, _, _ in columns} - filled), [])
                for child, _, _, _ in children:
                    self.assertTrue(flat.get(child), f"{child} has no row")

    def test_every_dataset_round_trips(self):
        for path in [EVERY_SLOT] + EXAMPLES:
            with self.subTest(path.name):
                self.assertEqual(flat_profile.roundtrip(flat_profile.load(path), self.tables), [])

    def test_value_objects_expand_and_lists_become_child_tables(self):
        flat = flat_profile.flatten(self.every, self.tables)
        hit = next(r for r in flat["feature"] if r["feature_id"] == "gene_1|pfam|PF00001")
        self.assertEqual((hit["target_id"], hit["target_start"], hit["target_gap"]), ("PF00001", 1, "M86"))
        self.assertEqual(flat["feature_attributes"][0], {"feature_id": "gene_1", "ordinal": 0, "key": "ID",
                                                         "value": "gene_1"})
        self.assertEqual([r["parent"] for r in flat["feature_parent"]], ["locus_1", "gene_1"])
        self.assertEqual([(r["ordinal"], r["start"]) for r in flat["feature_location_parts"]], [(0, 101), (1, 251)])

    def test_loss_is_refused_both_ways(self):
        dataset = copy.deepcopy(self.every)
        dataset["features"][0]["made_up"] = 1
        with self.assertRaisesRegex(ValueError, "not slots of the model"):
            flat_profile.flatten(dataset, self.tables)
        with self.assertRaisesRegex(ValueError, "is this a Dataset"):
            flat_profile.flatten({"artifacts": []}, self.tables)
        flat = flat_profile.flatten(self.every, self.tables)
        swapped = copy.deepcopy(flat)
        swapped["feature_note"].reverse()
        with self.assertRaisesRegex(ValueError, "out of order"):
            flat_profile.unflatten(swapped, self.tables)
        orphan = copy.deepcopy(flat)
        orphan["feature_dbxref"][0]["feature_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "has no feature row"):
            flat_profile.unflatten(orphan, self.tables)

    def test_commands_round_trip_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat, back = Path(tmp) / "flat.json", Path(tmp) / "back.json"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(flat_profile.main(["flatten", str(EVERY_SLOT), str(flat)]), 0, err.getvalue())
                self.assertEqual(flat_profile.main(["unflatten", str(flat), str(back)]), 0, err.getvalue())
                self.assertEqual(flat_profile.main(["flatten", str(EVERY_SLOT), str(flat)]), 1)
                self.assertEqual(flat_profile.main(["check"]), 0)
            self.assertIn("already exists", err.getvalue())
            self.assertEqual(json.loads(back.read_text()), self.every)


if __name__ == "__main__":
    unittest.main()
