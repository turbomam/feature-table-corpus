"""The linkml-map round trip for IMG functional annotation holds, and fails when it should."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("img_functional_map", ROOT / "scripts/img_functional_map.py")
mapping = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mapping)
dialect = mapping.dialect
FIXTURE = ROOT / "tests/fixtures/img-functional-gff/constructed.gff"
NMDC = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-hrn8ep39.1_functional_annotation.gff"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = mapping._transformers()
        cls.document = dialect.parse(FIXTURE)
        cls.dataset = mapping.forward(cls.document, cls.transformers)

    def feature(self, feature_id, dataset=None):
        return next(f for f in (dataset or self.dataset)["features"] if f["feature_id"] == feature_id)

    def back(self, dataset):
        return mapping.reverse(dataset, str(FIXTURE), self.transformers)

    def test_fixture_and_vendored_nmdc_file_round_trip(self):
        problems, report = mapping.roundtrip(FIXTURE)
        self.assertEqual(problems, [])
        self.assertEqual((report["rows"], report["contigs"], report["attributes"]), (10, 2, 75))
        self.assertEqual(report["lines_differing_only_in_number_spelling"], 1)
        problems, _ = mapping.roundtrip(NMDC)
        self.assertEqual(problems, [])

    def test_roundtrip_reports_instead_of_raising(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            unknown = Path(tmp) / "unknown.gff"
            unknown.write_text(FIXTURE.read_text().replace("cog=COG0001", "cog=COG0001;new_key=1", 1))
            problems, report = mapping.roundtrip(unknown)
            self.assertTrue(problems and all(p.startswith("dialect: ") for p in problems), problems)
            self.assertNotIn("rows", report)
            unparsable = Path(tmp) / "unparsable.gff"
            unparsable.write_text("##gff-version 3\n" + FIXTURE.read_text())
            problems, _ = mapping.roundtrip(unparsable)
            self.assertIn("comment or directive", problems[0])
            problems, _ = mapping.roundtrip(Path(tmp) / "missing.gff")
            self.assertTrue(problems[0].startswith("input: "), problems)
            binary = Path(tmp) / "binary.gff"
            binary.write_bytes(b"\xff\xfe\x00")
            problems, _ = mapping.roundtrip(binary)
            self.assertTrue(problems[0].startswith("input: "), problems)

    def test_core_columns_and_constant(self):
        cds = self.feature("ctg_01_100_1299")
        self.assertEqual((cds["seqid"], cds["start"], cds["end"], cds["strand"], cds["phase"]),
                         ("ctg_01", 100, 1299, "+", 0))
        self.assertEqual(cds["product"], "glutamate-1-semialdehyde 2,1-aminomutase")
        self.assertEqual(cds["coordinate_system"], "contig")
        self.assertEqual(self.feature("ctg_02_500_620_DR1")["parent"], ["ctg_02_500_620"])
        self.assertEqual([c["contig_id"] for c in self.dataset["contigs"]], ["ctg_01", "ctg_02"])

    def test_one_attribute_per_value_in_file_order(self):
        pairs = [(a["key"], a["value"]) for a in self.feature("ctg_01_1600_2199")["attributes"]]
        self.assertEqual(pairs[pairs.index(("ko", "KO:K01990")) + 1], ("ko", "KO:K01992"))
        self.assertIn(("product_source", "COG1131/COG4152"), pairs)
        shortened = [v for k, v in (
            (a["key"], a["value"]) for a in self.feature("ctg_01_1400_1543")["attributes"]) if k == "shortened"]
        self.assertEqual(shortened, ["original end 2500", "original end 1750"])

    def test_edited_attribute_value_changes_the_row(self):
        edited = copy.deepcopy(self.dataset)
        attribute = next(a for a in self.feature("ctg_01_100_1299", edited)["attributes"] if a["key"] == "pfam")
        attribute["value"] = "PF99999"
        self.assertNotEqual(self.back(edited)["rows"][0], self.document["rows"][0])

    def test_feature_and_attribute_copies_must_agree(self):
        edited = copy.deepcopy(self.dataset)
        self.feature("ctg_01_100_1299", edited)["product"] = "something else"
        with self.assertRaises(ValueError):
            self.back(edited)

    def test_unknown_attribute_key_is_reported(self):
        edited = copy.deepcopy(self.dataset)
        self.feature("ctg_01_100_1299", edited)["attributes"].append({"key": "new_key", "value": "x"})
        with self.assertRaisesRegex(ValueError, "not a column 9 key"):
            self.back(edited)

    def test_non_contiguous_list_values_are_rejected(self):
        edited = copy.deepcopy(self.dataset)
        attributes = self.feature("ctg_01_1600_2199", edited)["attributes"]
        second_ko = next(i for i, a in enumerate(attributes) if a["value"] == "KO:K01992")
        attributes.append(attributes.pop(second_ko))
        with self.assertRaisesRegex(ValueError, "ko values are not contiguous"):
            self.back(edited)

    def test_attribute_needs_its_feature_copy(self):
        for slot, dialect_name in (("product", "product"), ("product_source", "product_source")):
            edited = copy.deepcopy(self.dataset)
            del self.feature("ctg_01_100_1299", edited)[slot]
            with self.assertRaisesRegex(ValueError, f"{dialect_name} is an attribute but not set"):
                self.back(edited)

    def test_promoted_field_needs_its_attribute_copy(self):
        edited = copy.deepcopy(self.dataset)
        feature = self.feature("ctg_01_100_1299", edited)
        feature["attributes"] = [a for a in feature["attributes"] if a["key"] != "ID"]
        with self.assertRaisesRegex(ValueError, "ID has no attribute copy"):
            self.back(edited)

    def test_two_parents_do_not_fit_the_dialect(self):
        from linkml_map.transformer.errors import TransformationError
        edited = copy.deepcopy(self.dataset)
        self.feature("ctg_02_500_620_DR1", edited)["parent"] = ["ctg_02_500_620", "ctg_01_100_1299"]
        with self.assertRaises(TransformationError):
            self.back(edited)

    def errors(self, dataset):
        return mapping.validation_errors(dataset, mapping.make_validator(str(mapping.MODEL)))

    def test_model_validation_catches_a_bad_value(self):
        edited = copy.deepcopy(self.dataset)
        self.feature("ctg_01_100_1299", edited)["phase"] = 5
        self.assertTrue(any("phase" in e for e in self.errors(edited)))

    def test_model_validation_catches_a_dangling_parent(self):
        # Cross-record checks run only once the shape is valid, so this edit is alone.
        edited = copy.deepcopy(self.dataset)
        self.feature("ctg_02_500_620_DR1", edited)["parent"] = ["no_such_feature"]
        self.assertTrue(any("no_such_feature" in e for e in self.errors(edited)), self.errors(edited))


class CommandTests(unittest.TestCase):
    """The command line refuses invalid input in either direction and writes nothing."""

    def run_cli(self, *args):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status = mapping.main([str(a) for a in args])
        return status, err.getvalue()

    def test_forward_refuses_input_outside_the_dialect(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.gff"
            source.write_text(FIXTURE.read_text().replace("+\t.\tID=ctg_01_2300_2375", "+\t0\tID=ctg_01_2300_2375", 1))
            out = Path(tmp) / "out.json"
            status, err = self.run_cli("forward", source, out)
            self.assertEqual(status, 1)
            self.assertIn("phase present on tRNA", err)
            self.assertFalse(out.exists())

    def test_reverse_refuses_an_invalid_dataset(self):
        import json
        import tempfile
        dataset = mapping.forward(dialect.parse(FIXTURE))
        next(f for f in dataset["features"] if f["feature_id"] == "ctg_02_500_620_DR1")["parent"] = ["gone"]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "dataset.json"
            source.write_text(json.dumps(dataset))
            out = Path(tmp) / "out.gff"
            status, err = self.run_cli("reverse", source, out)
            self.assertEqual(status, 1)
            self.assertIn("gone", err)
            self.assertFalse(out.exists())

    def test_unreadable_input_is_reported_in_both_directions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad_gff, bad_json, out = Path(tmp) / "bad.gff", Path(tmp) / "bad.json", Path(tmp) / "out"
            bad_gff.write_text("##gff-version 3\n")
            bad_json.write_text("{not json")
            for args in (("forward", bad_gff, out), ("reverse", bad_json, out), ("reverse", Path(tmp) / "none", out)):
                status, err = self.run_cli(*args)
                self.assertEqual(status, 1, args)
                self.assertIn("input: ", err)
                self.assertFalse(out.exists())

    def test_unwritable_output_is_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "d.json"
            self.assertEqual(self.run_cli("forward", FIXTURE, dataset)[0], 0)
            for args in (("forward", FIXTURE, Path(tmp) / "no/such/dir/out.json"),
                         ("reverse", dataset, Path(tmp) / "no/such/dir/out.gff")):
                status, err = self.run_cli(*args)
                self.assertEqual(status, 1, args)
                self.assertIn("output: ", err)

    def test_both_directions_write_valid_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dataset, back = Path(tmp) / "d.json", Path(tmp) / "back.gff"
            self.assertEqual(self.run_cli("forward", FIXTURE, dataset)[0], 0)
            self.assertEqual(self.run_cli("reverse", dataset, back)[0], 0)
            self.assertEqual(dialect.parse(back)["rows"], dialect.parse(FIXTURE)["rows"])


class AgreementTests(unittest.TestCase):
    def test_matches_gff3_contig_on_the_vendored_nmdc_file(self):
        """Both paths accept the NMDC file; they differ only in promoting product_source."""
        import json
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            subprocess.run([sys.executable, str(ROOT / "scripts/convert_features.py"), "import", str(NMDC),
                            "--profile", "gff3-contig/1.0.0", "--reference-context", "nmdc:test",
                            "--output", str(bundle)], check=True, capture_output=True)
            reference = json.loads(bundle.read_text())["dataset"]
        mapped = mapping.forward(dialect.parse(NMDC))
        self.assertEqual(mapped["contigs"], reference["contigs"])
        for ours, theirs in zip(mapped["features"], reference["features"], strict=True):
            self.assertEqual(ours.pop("product_source"), "KO:K04523")
            self.assertNotIn("product_source", theirs)
            self.assertEqual(ours, theirs)


if __name__ == "__main__":
    unittest.main()
