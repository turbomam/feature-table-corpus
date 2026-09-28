"""IMG per-method hits map to protein-coordinate Features on their CDS and back, and loss is refused."""
from collections import Counter
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
import img_functional_gff as functional_dialect  # noqa: E402
import img_per_method_gff as dialect  # noqa: E402
import img_per_method_map as mapping  # noqa: E402

FUNCTIONAL = ROOT / "tests/fixtures/img-functional-gff/constructed.gff"
HITS = ROOT / "tests/fixtures/img-per-method-gff"
METHODS = ("pfam", "cog", "ko_ec", "tigrfam", "smart", "supfam", "cath_funfam")
# Three per-method fixtures have hits on a gene the functional fixture lacks; one extra CDS covers it.
EXTRA_CDS = ("ctg_02\tProdigal v2.6.3\tCDS\t10\t900\t5.5\t+\t0\t"
             "ID=ctg_02_10_900;translation_table=11;start_type=ATG;product=hypothetical protein;"
             "product_source=Hypo-rule applied\n")
REAL = ROOT / "corpus/sources/jgi-img/IMG_AP-1268149"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.functional_path = Path(cls.tmp.name) / "genome_functional_annotation.gff"
        cls.functional_path.write_text(FUNCTIONAL.read_text() + EXTRA_CDS)
        cls.transformers = mapping._transformers()
        cls.functional = functional_dialect.parse(cls.functional_path)
        cls.pfam = dialect.parse(HITS / "constructed_pfam.gff")
        cls.dataset = mapping.forward(cls.functional, cls.pfam, cls.transformers)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def back(self, dataset):
        return mapping.reverse(dataset, "case", self.transformers)

    def test_every_method_fixture_round_trips(self):
        paths = [HITS / f"constructed_{method}.gff" for method in METHODS]
        problems, report = mapping.roundtrip(self.functional_path, paths)
        self.assertEqual(problems, [])
        self.assertEqual([f["method"] for f in report["files"]], list(METHODS))

    def test_vendored_isolate_round_trips_with_every_method_in_one_dataset(self):
        """Issue 98: all seven files of Ga0423362 share one Dataset, although 1,138 source IDs repeat."""
        paths = [REAL / f"Ga0423362_{method}.gff" for method in METHODS]
        problems, report = mapping.roundtrip(REAL / "Ga0423362_functional_annotation.gff", paths)
        self.assertEqual(problems, [])
        self.assertEqual([f["method"] for f in report["files"]], list(METHODS))
        self.assertEqual(sum(f["hits"] for f in report["files"]), 22872)
        counts = Counter(row["ID"] for path in paths for row in dialect.parse(path)["rows"])
        self.assertEqual(sum(1 for n in counts.values() if n > 1), 1138)

    def test_a_hit_is_on_its_cds(self):
        hits = [f for f in self.dataset["features"] if f["coordinate_system"] == "protein"]
        cds = {f["feature_id"] for f in self.dataset["features"] if f["type"] == "CDS"}
        self.assertEqual(len(hits), len(self.pfam["rows"]))
        for hit in hits:
            self.assertIn(hit["seqid"], cds)
            self.assertEqual(hit["parent"], [hit["seqid"]])
            self.assertEqual(hit["strand"], ".")
            self.assertTrue(hit["type"].startswith("PF"))
            self.assertNotIn("score_type", hit)
        first = hits[0]
        self.assertEqual([a["key"] for a in first["attributes"]][:2], ["ID", "Name"])

    def test_a_list_value_becomes_one_attribute_per_value(self):
        ko = dialect.parse(HITS / "constructed_ko_ec.gff")
        dataset = mapping.forward(self.functional, ko, self.transformers)
        hit = next(f for f in dataset["features"] if f["coordinate_system"] == "protein")
        ids = [a["value"] for a in hit["attributes"] if a["key"] == "subject_gene_ids"]
        self.assertEqual(ids, ko["rows"][0]["subject_gene_ids"])
        self.assertGreater(len(ids), 1)
        _, back = self.back(dataset)
        self.assertEqual([d["rows"] for d in back], [ko["rows"]])

    def test_one_dataset_holds_several_methods_with_qualified_ids(self):
        cog = dialect.parse(HITS / "constructed_cog.gff")
        both = mapping.forward(self.functional, [self.pfam, cog], self.transformers)
        hits = [f for f in both["features"] if f["coordinate_system"] == "protein"]
        self.assertEqual(len(hits), len(self.pfam["rows"]) + len(cog["rows"]))
        self.assertEqual(len({f["feature_id"] for f in both["features"]}), len(both["features"]))
        for hit in hits:
            source_id = next(a["value"] for a in hit["attributes"] if a["key"] == "ID")
            method = "pfam" if hit["type"].startswith("PF") else "cog"
            self.assertEqual(hit["feature_id"], f"{source_id}|{method}|{hit['type']}")
        _, back = self.back(both)
        self.assertEqual([d["method"] for d in back], ["pfam", "cog"])
        self.assertEqual([d["rows"] for d in back], [self.pfam["rows"], cog["rows"]])
        # A Dataset that interleaves methods and puts hits first is the same content: each method's
        # own order is what the files keep.
        pfam_hits, cog_hits = hits[:len(self.pfam["rows"])], hits[len(self.pfam["rows"]):]
        mixed = [f for pair in zip(pfam_hits, cog_hits) for f in pair]
        mixed += pfam_hits[len(cog_hits):] + cog_hits[len(pfam_hits):]
        interleaved = {**both, "features": mixed + [f for f in both["features"] if f["coordinate_system"] != "protein"]}
        _, back = self.back(interleaved)
        self.assertEqual([d["rows"] for d in back], [self.pfam["rows"], cog["rows"]])

    def test_reverse_refuses_what_the_dialects_cannot_hold(self):
        def hit(dataset):
            return next(f for f in dataset["features"] if f["coordinate_system"] == "protein")
        cases = {
            "parent": (lambda f: f.update(parent=["ctg_01_1400_1543"]), "is not its seqid"),
            "score_type": (lambda f: f.update(score_type="bit_score"), "without loss"),
            "product": (lambda f: f.update(product="kinase"), "without loss"),
            "type": (lambda f: f.update(type="Q12345"), "not an accession of any IMG method"),
            "feature_id": (lambda f: f.update(feature_id=f["feature_id"] + "x"), "feature_id should be"),
            "ID": (lambda f: f.update(attributes=[a for a in f["attributes"] if a["key"] != "ID"]),
                   "exactly one ID attribute"),
            "comma": (lambda f: f["attributes"][1].update(value="a,b"), "contains ','"),
            "semicolon": (lambda f: f["attributes"][1].update(value="a;b"), "contains ';'"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(hit(dataset))
                with self.assertRaisesRegex(Exception, expected):
                    self.back(dataset)
        no_cds = copy.deepcopy(self.dataset)
        no_cds["features"] = [f for f in no_cds["features"] if f["coordinate_system"] == "protein"]
        with self.assertRaisesRegex(ValueError, "CDS features are missing"):
            self.back(no_cds)

    def test_reverse_accepts_contigs_without_translation_table(self):
        # functional.reverse accepts a Dataset that leaves the derived slot unset; so must this.
        dataset = copy.deepcopy(self.dataset)
        for contig in dataset["contigs"]:
            contig.pop("translation_table", None)
        functional_back, hits_back = self.back(dataset)
        self.assertEqual(functional_back["rows"], self.functional["rows"])
        self.assertEqual([d["rows"] for d in hits_back], [self.pfam["rows"]])

    def test_a_hit_without_a_score_is_named(self):
        dataset = copy.deepcopy(self.dataset)
        hit = next(f for f in dataset["features"] if f["coordinate_system"] == "protein")
        del hit["score"]
        with self.assertRaisesRegex(ValueError, f"{hit['feature_id']}: a hit needs a score"):
            self.back(dataset)

    def test_conflicting_translation_tables_are_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            conflicting = Path(tmp) / "conflict_functional_annotation.gff"
            conflicting.write_text(self.functional_path.read_text().replace(
                "ID=ctg_01_1600_2199;translation_table=11;", "ID=ctg_01_1600_2199;translation_table=4;", 1))
            self.assertIn("translation_table=4", conflicting.read_text())
            hits = HITS / "constructed_pfam.gff"
            problems, _ = mapping.roundtrip(conflicting, [hits])
            self.assertTrue(problems and "translation" in problems[0], problems)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status = mapping.main(["forward", str(conflicting), str(hits), str(Path(tmp) / "out.json")])
            self.assertEqual(status, 1)
            self.assertIn("translation", err.getvalue())
            self.assertFalse((Path(tmp) / "out.json").exists())

    def test_commands_write_both_files_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset, prefix = Path(tmp) / "dataset.json", Path(tmp) / "genome"
            run = ["forward", self.functional_path, HITS / "constructed_pfam.gff", HITS / "constructed_cog.gff",
                   dataset]
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(mapping.main([str(a) for a in run]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(prefix)]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(prefix)]), 1)
            self.assertIn("already exists", err.getvalue())
            written = Path(tmp) / "genome_pfam.gff"
            self.assertEqual(dialect.parse(written)["rows"], self.pfam["rows"])
            cog = dialect.parse(HITS / "constructed_cog.gff")
            self.assertEqual(dialect.parse(Path(tmp) / "genome_cog.gff")["rows"], cog["rows"])
            self.assertEqual(functional_dialect.parse(Path(tmp) / "genome_functional_annotation.gff")["rows"],
                             self.functional["rows"])
            self.assertEqual(len(json.loads(dataset.read_text())["features"]),
                             len(self.functional["rows"]) + len(self.pfam["rows"]) + len(cog["rows"]))

    def test_the_spelling_file_brings_every_file_back_byte_for_byte(self):
        # The isolate's KO file writes scores as 1.22e+03 and its functional file pads 84.50.
        sources = [REAL / "Ga0423362_functional_annotation.gff", REAL / "Ga0423362_ko_ec.gff"]
        with tempfile.TemporaryDirectory() as tmp:
            dataset, spelling, prefix = Path(tmp) / "d.json", Path(tmp) / "s.json", Path(tmp) / "Ga0423362"
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(mapping.main(["forward", *map(str, sources), str(dataset), "--spelling", str(spelling)]),
                                 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(prefix), "--spelling", str(spelling)]),
                                 0, err.getvalue())
            self.assertEqual(json.loads(spelling.read_text())["Ga0423362_01_24852_26480_1_542|ko_ec|KO:K02343__EC:2.7.7.7"],
                             "1.22e+03")
            for source in sources:
                self.assertEqual((Path(tmp) / source.name).read_bytes(), source.read_bytes(), source.name)

    def test_clean_round_trip_prints_nothing_to_stderr(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/img_per_method_map.py"), "roundtrip",
                                 str(self.functional_path), str(HITS / "constructed_cog.gff")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
