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
                for child, _, slot, fields in children:
                    self.assertTrue(flat.get(child), f"{child} has no row")
                    wanted = {slot.name} if fields is None else {name for name, _ in fields}
                    filled = {name for row in flat[child] for name in row}
                    self.assertEqual(sorted(wanted - filled), [], child)

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
        nested = copy.deepcopy(self.every)
        nested["features"][-1]["target"]["typo"] = "lost"
        with self.assertRaisesRegex(ValueError, r"\['target.typo'\] are not slots"):
            flat_profile.flatten(nested, self.tables)
        flat = flat_profile.flatten(self.every, self.tables)
        swapped = copy.deepcopy(flat)
        swapped["feature_note"].reverse()
        with self.assertRaisesRegex(ValueError, "out of order"):
            flat_profile.unflatten(swapped, self.tables)
        orphan = copy.deepcopy(flat)
        orphan["feature_dbxref"][0]["feature_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "has no feature row"):
            flat_profile.unflatten(orphan, self.tables)
        misspelled = copy.deepcopy(flat)
        misspelled["feature"][-1]["target_strat"] = 1
        with self.assertRaisesRegex(ValueError, r"\['target_strat'\] are not its columns"):
            flat_profile.unflatten(misspelled, self.tables)
        with self.assertRaisesRegex(ValueError, "not tables of the flat profile"):
            flat_profile.unflatten({**flat, "feature_notes": []}, self.tables)
        cases = {
            "top-level required": (lambda f: f["feature"][0].pop("seqid"), r"required \['seqid'\] missing"),
            "identifier": (lambda f: f["feature"][0].pop("feature_id"), r"required \['feature_id'\] missing"),
            "ordinal": (lambda f: f["feature_note"][0].pop("ordinal"), r"required \['ordinal'\] missing"),
            "child value": (lambda f: f["feature_note"][0].pop("note"), r"required \['note'\] missing"),
            "struct field": (lambda f: f["feature"][-1].pop("target_id"), r"required \['target_id'\] missing"),
            "item field": (lambda f: f["feature_attributes"][0].pop("value"), r"required \['value'\] missing"),
            "required list in a struct": (lambda f: f.update(feature_location_parts=[]), "location.parts is required"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                broken = copy.deepcopy(flat)
                change(broken)
                with self.assertRaisesRegex(ValueError, expected):
                    flat_profile.unflatten(broken, self.tables)
        twice = copy.deepcopy(flat)
        twice["feature"].append(dict(twice["feature"][1], product="other"))
        with self.assertRaisesRegex(ValueError, "'gene_1' is on more than one row"):
            flat_profile.unflatten(twice, self.tables)

    def test_the_flat_schema_keeps_the_model_constraints(self):
        import yaml
        classes = yaml.safe_load(flat_profile.FLAT.read_text())["classes"]
        feature, parts = classes["Feature"]["attributes"], classes["FeatureLocationParts"]["attributes"]
        self.assertTrue(all(feature[n].get("required") for n in ("feature_id", "seqid", "start", "end",
                                                                 "coordinate_system")))
        self.assertEqual((feature["start"]["minimum_value"], feature["phase"]["maximum_value"]), (1, 2))
        self.assertEqual(parts["start"]["minimum_value"], 1)
        self.assertNotIn("required", feature["target_id"])
        # ...but a struct's required fields are required once any of its columns is present.
        rules = classes["Feature"]["rules"]
        start = next(r for r in rules if list(r["preconditions"]["slot_conditions"]) == ["target_start"])
        self.assertEqual(sorted(start["postconditions"]["slot_conditions"]), ["target_end", "target_id"])
        # The model's rule that a score_type needs a score names two direct columns, so it is kept.
        rule = next(r for r in classes["Feature"]["rules"] if "score_type" in r["preconditions"]["slot_conditions"])
        self.assertEqual((list(rule["preconditions"]["slot_conditions"]), list(rule["postconditions"]["slot_conditions"])),
                         (["score_type"], ["score"]))

    def test_an_empty_list_round_trips_as_absent(self):
        dataset = copy.deepcopy(self.every)
        dataset["features"][0]["parent"] = []
        dataset["features"][0]["note"] = []
        self.assertEqual(flat_profile.roundtrip(dataset, self.tables), [])

    def test_unflatten_refuses_a_dataset_the_model_rejects(self):
        flat = flat_profile.flatten(self.every, self.tables)
        flat["feature"][0].update(start=10, end=5)
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "flat.json", Path(tmp) / "back.json"
            source.write_text(json.dumps(flat))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(flat_profile.main(["unflatten", str(source), str(out)]), 1)
            self.assertIn("start", err.getvalue())
            self.assertFalse(out.exists())

    def test_non_finite_numbers_are_refused_both_ways(self):
        # https://github.com/turbomam/feature-table-corpus/issues/121: 1e400 parses as infinity.
        dataset = copy.deepcopy(self.every)
        dataset["features"][1]["score"] = json.loads("1e400")
        with self.assertRaisesRegex(ValueError, r"\['features\[1\]\.score'\] is not a finite number"):
            flat_profile.flatten(dataset, self.tables)
        flat = flat_profile.flatten(self.every, self.tables)
        flat["contig"][0]["lineage_confidence"] = float("nan")
        with self.assertRaisesRegex(ValueError, r"contig\[0\]\.lineage_confidence"):
            flat_profile.unflatten(flat, self.tables)
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "d.json", Path(tmp) / "flat.json"
            source.write_text(EVERY_SLOT.read_text().replace('"score": 55.5', '"score": 1e400'))
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(flat_profile.main(["flatten", str(source), str(out)]), 1)
            self.assertIn("not a finite number", err.getvalue())
            self.assertFalse(out.exists())

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
