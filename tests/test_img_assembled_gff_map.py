"""The IMG 4.14 assembled GFF maps to the feature model and back, byte for byte, and loss is refused."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import img_assembled_gff as dialect  # noqa: E402
import img_assembled_gff_map as mapping  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/img-assembled-gff/constructed.assembled.gff"
REAL = ROOT / "corpus/sources/jgi-img/IMG_AP-1121004/106476.assembled.gff"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = mapping._transformers()
        cls.document = dialect.parse(FIXTURE)
        cls.dataset = mapping.forward(cls.document, cls.transformers)

    def back(self, dataset):
        return mapping.reverse(dataset, str(FIXTURE), self.transformers)

    def test_fixture_and_real_file_round_trip_byte_for_byte(self):
        for path, rows in ((FIXTURE, 8), (REAL, 4693)):
            problems, report = mapping.roundtrip(path)
            self.assertEqual(problems, [], path.name)
            self.assertEqual(report["rows"], rows)
            self.assertTrue(report["byte_identical"])

    def test_forward_shape(self):
        features = {f["feature_id"]: f for f in self.dataset["features"]}
        cds = features["Ga0000001_101.2"]
        self.assertEqual((cds["strand"], cds["phase"], cds["coordinate_system"]), ("-", 0, "contig"))
        self.assertNotIn("product", cds)
        # Attribute values keep the file's spelling, so conf keeps its two decimals.
        self.assertIn({"key": "conf", "value": "100.00"}, cds["attributes"])
        self.assertIn({"key": "gc_cont", "value": "0.450"}, cds["attributes"])
        rrna = features["Ga0000001_102.4"]
        self.assertEqual([a["key"] for a in rrna["attributes"]].count("LowScore"), 2)
        self.assertEqual(rrna["product"], "16S rRNA. Bacterial SSU")
        self.assertEqual(features["Ga0000001_101.1"]["strand"], "+")
        self.assertEqual([c["contig_id"] for c in self.dataset["contigs"]], ["Ga0000001_101", "Ga0000001_102"])

    def test_reverse_of_forward_is_the_file(self):
        back = self.back(self.dataset)
        self.assertEqual(dialect.write(back), FIXTURE.read_text())

    def test_reverse_refuses_what_the_dialect_cannot_hold(self):
        def cds(dataset):
            return next(f for f in dataset["features"] if f["feature_id"] == "Ga0000001_101.2")
        cases = {
            "score": (lambda f: f.update(score=1.5), "without loss"),
            "coordinate_system": (lambda f: f.update(coordinate_system="protein"), "only contig"),
            "strand": (lambda f: f.update(strand="."), "loses or changes \\['strand'\\]"),
            "ID": (lambda f: f.update(feature_id="Ga0000001_101.9"), "feature_id is"),
            "product": (lambda f: f.update(product="kinase"), "product is 'kinase' in the Feature"),
            "conf spelling": (lambda f: f["attributes"][1].update(value="100.0"), "decimals"),
            "semicolon": (lambda f: f["attributes"][1].update(value="1;2"), "contains ';'"),
            "unknown key": (lambda f: f["attributes"].append({"key": "Note", "value": "x"}), "Note|without loss"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(cds(dataset))
                with self.assertRaisesRegex(Exception, expected):
                    document = self.back(dataset)
                    found = dialect.problems(document)
                    if found:
                        raise ValueError("; ".join(found))

    def test_commands_never_overwrite_and_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset, back = Path(tmp) / "dataset.json", Path(tmp) / "back.gff"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(FIXTURE), str(dataset)]), 0, err.getvalue())
                self.assertEqual(mapping.main(["forward", str(FIXTURE), str(dataset)]), 1)
                self.assertEqual(mapping.main(["reverse", str(dataset), str(back)]), 0, err.getvalue())
            self.assertIn("exists", err.getvalue())
            self.assertEqual(back.read_text(), FIXTURE.read_text())
            self.assertEqual(len(json.loads(dataset.read_text())["features"]), 8)

    def test_clean_round_trip_prints_nothing_to_stderr(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/img_assembled_gff_map.py"), "roundtrip",
                                 str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
