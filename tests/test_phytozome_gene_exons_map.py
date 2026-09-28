"""Phytozome gene_exons GFF3 maps to the feature model and back, byte for byte, and loss is refused."""
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
import phytozome_gene_exons as dialect  # noqa: E402
import phytozome_gene_exons_map as mapping  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/phytozome/constructed.gene_exons.gff3"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = mapping._transformers()
        cls.document = dialect.parse(FIXTURE)
        cls.dataset = mapping.forward(cls.document, cls.transformers)

    def back(self, dataset):
        return mapping.reverse(dataset, str(FIXTURE), self.transformers)

    def test_fixture_round_trips_byte_for_byte(self):
        problems, report = mapping.roundtrip(FIXTURE)
        self.assertEqual(problems, [])
        self.assertEqual((report["rows"], report["contigs"], report["attributes"]), (22, 1, 70))
        self.assertTrue(report["byte_identical"])

    def test_forward_shape(self):
        mrna = next(f for f in self.dataset["features"] if f["type"] == "mRNA")
        self.assertEqual(mrna["parent"], ["Exa01g00010.EXv1"])
        self.assertEqual(mrna["coordinate_system"], "contig")
        self.assertEqual([a["key"] for a in mrna["attributes"]], ["ID", "Name", "pacid", "longest", "Parent"])
        self.assertEqual(next(a["value"] for a in mrna["attributes"] if a["key"] == "longest"), "1")
        self.assertNotIn("phase", next(f for f in self.dataset["features"] if f["type"] == "exon"))
        self.assertEqual(self.dataset["contigs"], [{"contig_id": "scaffold_1"}])

    def test_longest_sets_is_representative(self):
        by_type = {}
        for feature in self.dataset["features"]:
            by_type.setdefault(feature["type"], []).append(feature)
        flags = {f["feature_id"]: f["is_representative"] for f in by_type["mRNA"]}
        longest = {f["feature_id"]: next(a["value"] for a in f["attributes"] if a["key"] == "longest")
                   for f in by_type["mRNA"]}
        self.assertEqual(flags, {k: v == "1" for k, v in longest.items()})
        self.assertEqual(sorted(set(flags.values())), [False, True])
        # Rows without longest say nothing, so the slot stays unset.
        for kind in ("gene", "exon", "CDS"):
            self.assertTrue(all("is_representative" not in f for f in by_type[kind]), kind)

    def test_reverse_refuses_is_representative_that_disagrees_with_longest(self):
        for change, expected in ((lambda f: f.update(is_representative=not f["is_representative"]), "longest attribute gives"),
                                 (lambda f: f.pop("is_representative"), "is None but"),):
            dataset = copy.deepcopy(self.dataset)
            change(next(f for f in dataset["features"] if f["type"] == "mRNA"))
            with self.subTest(expected), self.assertRaisesRegex(ValueError, expected):
                self.back(dataset)
        dataset = copy.deepcopy(self.dataset)
        next(f for f in dataset["features"] if f["type"] == "exon")["is_representative"] = False
        with self.assertRaisesRegex(ValueError, "longest attribute gives None"):
            self.back(dataset)

    def test_annot_version_is_recovered_from_gene_ids(self):
        self.assertEqual(self.back(self.dataset)["annot_version"], "EXv1")
        genes_only_parts = copy.deepcopy(self.dataset)
        genes_only_parts["features"] = [f for f in genes_only_parts["features"] if f["type"] != "gene"]
        for feature in genes_only_parts["features"]:
            if feature["type"] == "mRNA":
                feature.pop("parent")
                feature["attributes"] = [a for a in feature["attributes"] if a["key"] != "Parent"]
        with self.assertRaisesRegex(ValueError, "can't recover annot-version"):
            self.back(genes_only_parts)

    def test_reverse_refuses_what_the_dialect_cannot_hold(self):
        cases = {
            "score": lambda f: f.update(score=1.5),
            "product": lambda f: f.update(product="kinase"),
            "coordinate_system": lambda f: f.update(coordinate_system="protein"),
            "ID": lambda f: f.update(feature_id=f["feature_id"] + "x"),
            "unknown key": lambda f: f["attributes"].append({"key": "Note", "value": "x"}),
            "value with ;": lambda f: f["attributes"][1].update(value="a;longest=1"),
        }
        expected = {"score": "without loss", "product": "without loss", "coordinate_system": "only contig",
                    "ID": "ID is", "unknown key": "without loss|Note", "value with ;": "contains ';'"}
        for name, change in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(dataset["features"][1])
                with self.assertRaisesRegex(Exception, expected[name]):
                    document = self.back(dataset)
                    problems = dialect.problems(document)
                    if problems:
                        raise ValueError("; ".join(problems))

    def test_parent_needs_its_attribute_copy(self):
        dataset = copy.deepcopy(self.dataset)
        mrna = next(f for f in dataset["features"] if f["type"] == "mRNA")
        mrna["attributes"] = [a for a in mrna["attributes"] if a["key"] != "Parent"]
        with self.assertRaisesRegex(ValueError, "Parent is 'Exa01g00010.EXv1' in the Feature but None"):
            self.back(dataset)

    def test_reverse_of_forward_is_the_document(self):
        back = self.back(self.dataset)
        self.assertEqual(back["rows"], self.document["rows"])
        self.assertEqual(dialect.write(back), FIXTURE.read_text())

    def run_cli(self, *args):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            status = mapping.main([str(a) for a in args])
        return status, err.getvalue()

    def test_commands_never_overwrite_and_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset, back = Path(tmp) / "dataset.json", Path(tmp) / "back.gff3"
            self.assertEqual(self.run_cli("forward", FIXTURE, dataset)[0], 0)
            self.assertEqual(len(json.loads(dataset.read_text())["features"]), 22)
            status, err = self.run_cli("forward", FIXTURE, dataset)
            self.assertEqual(status, 1)
            self.assertIn("exists", err)
            self.assertEqual(self.run_cli("reverse", dataset, back)[0], 0)
            self.assertEqual(back.read_text(), FIXTURE.read_text())
            bad = Path(tmp) / "bad.gff3"
            bad.write_text("##gff-version 3\n")
            status, err = self.run_cli("forward", bad, Path(tmp) / "never.json")
            self.assertEqual(status, 1)
            self.assertFalse((Path(tmp) / "never.json").exists())

    def test_clean_round_trip_prints_nothing_to_stderr(self):
        # linkml-map logs a warning per record, and a bare-string schema reference is
        # deprecated; neither may reach the terminal on a clean run.
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / "scripts/phytozome_gene_exons_map.py"), "roundtrip", str(FIXTURE)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stderr, "")

if __name__ == "__main__":
    unittest.main()
