"""An IMG taxon bundle maps to the feature model and back, every file byte for byte, and loss is refused."""
import contextlib
import copy
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import img_taxon_bundle as dialect  # noqa: E402
import img_taxon_bundle_map as mapping  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/img-taxon-bundle/9900000001.gff"
BACILLUS = ROOT / "corpus/sources/jgi-img/IMG_AP-1121004/2708743150.gff"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = mapping._transformers()
        cls.document = dialect.parse(FIXTURE)
        cls.dataset = mapping.forward(cls.document, cls.transformers)

    def back(self, dataset):
        return mapping.reverse(dataset, FIXTURE, self.transformers)

    def feature(self, dataset, feature_id):
        return next(f for f in dataset["features"] if f["feature_id"] == feature_id)

    def test_bacillus_bundle_round_trips_every_file_byte_for_byte(self):
        problems, report = mapping.roundtrip(BACILLUS)
        self.assertEqual(problems, [])
        self.assertEqual((report["hits"], report["skipped_crispr_rows"]), (36555, 0))
        self.assertEqual(len(report["files"]), 8)

    def test_fixture_round_trips_less_its_crispr_rows(self):
        problems, report = mapping.roundtrip(FIXTURE)
        self.assertEqual(problems, [])
        self.assertEqual(report["skipped_crispr_rows"], 2)
        self.assertNotIn("CRISPR", {f["type"] for f in self.dataset["features"]})

    def test_xref_rows_are_curies_on_their_cds(self):
        cds = self.feature(self.dataset, "9900000002")
        self.assertEqual(cds["stable_identifiers"], ["ncbigi:241760836", "genbank:ZP_04758925"])

    def test_a_hit_is_on_its_cds_with_an_issue_98_id(self):
        cog = next(f for f in self.dataset["features"] if f["feature_id"].split("|")[1:2] == ["cog"])
        gene, method, accession = cog["feature_id"].split("|")
        self.assertEqual((method, accession), ("cog", cog["type"]))
        self.assertTrue(gene.startswith(f"{cog['seqid']}_{cog['start']}_{cog['end']}"))
        self.assertEqual((cog["parent"], cog["coordinate_system"], cog["score_type"]),
                         ([cog["seqid"]], "protein", "bit_score"))
        tmhmm = next(f for f in self.dataset["features"] if "|tmhmm|" in f["feature_id"])
        self.assertNotIn("score_type", tmhmm)
        self.assertNotIn("score", tmhmm)

    def test_a_ko_hit_with_several_ec_numbers_is_one_feature(self):
        ko = self.feature(self.dataset, "9900000003_1_183|ko|KO:K08300")
        self.assertEqual([a["value"] for a in ko["attributes"] if a["key"] == "EC"], ["EC:3.1.26.12", "EC:3.1.-"])
        single = self.feature(self.dataset, "9900000002_1_216|ko|KO:K07492")
        self.assertNotIn("EC", [a["key"] for a in single["attributes"]])
        back = self.back(self.dataset)
        self.assertEqual(back["ko"], self.document["ko"])

    def test_ko_repeats_must_be_adjacent_and_agree(self):
        document = copy.deepcopy(self.document)
        rows = document["ko"]
        rows.append(rows.pop(2))  # the second EC row of KO:K08300 now follows another gene's hit
        with self.assertRaisesRegex(ValueError, "not adjacent"):
            mapping.forward(document, self.transformers)
        document = copy.deepcopy(self.document)
        document["ko"][2]["bit_score"] = 350
        with self.assertRaisesRegex(ValueError, "differs in \\['bit_score'\\]"):
            mapping.forward(document, self.transformers)

    def test_reverse_refuses_what_the_bundle_cannot_hold(self):
        def hit(dataset):
            return next(f for f in dataset["features"] if "|cog|" in f["feature_id"])
        cases = {
            "feature_id": (lambda d: hit(d).update(feature_id=hit(d)["feature_id"] + "x"), "feature_id should be|known table"),
            "score_type": (lambda d: hit(d).pop("score_type"), "score_type should be bit_score"),
            "parent": (lambda d: hit(d).update(parent=["9900000006"]), "only parent is its CDS"),
            "unknown column": (lambda d: hit(d)["attributes"].append({"key": "made_up", "value": "1"}),
                               "not a cog column"),
            "xref prefix": (lambda d: self.feature(d, "9900000002")["stable_identifiers"].append("uniprot:P1"),
                            "not an ncbigi: or genbank: CURIE"),
            "product": (lambda d: self.feature(d, "9900000002").update(product="kinase"), "disagrees"),
            "no table": (lambda d: hit(d).update(feature_id="9900000002_1_10"), "not a GFF row or a hit of a known table"),
            "tab": (lambda d: next(a for a in hit(d)["attributes"] if a["key"] == "cog_name").update(value="a\tb"),
                    "cog_name value .* contains"),
            "contig length": (lambda d: d["contigs"][0].update(length_bp=10**6), "without loss"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(dataset)
                with self.assertRaisesRegex(ValueError, expected):
                    self.back(dataset)

    def test_an_xref_needs_a_cds(self):
        document = copy.deepcopy(self.document)
        document["xref"][0]["gene_oid"] = 9900000001  # the rRNA row
        with self.assertRaisesRegex(ValueError, "gene_oid 9900000001 is not a CDS"):
            mapping.forward(document, self.transformers)

    def test_commands_write_every_file_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in"
            source.mkdir()
            for path in BACILLUS.parent.glob("2708743150.*"):
                shutil.copy(path, source / path.name)
            dataset, out = Path(tmp) / "d.json", Path(tmp) / "out" / "2708743150.gff"
            out.parent.mkdir()
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(source / "2708743150.gff"), str(dataset)]), 0,
                                 err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(out)]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(out)]), 1)
            self.assertIn("already exists", err.getvalue())
            written = sorted(p.name for p in out.parent.iterdir())
            self.assertEqual(written, sorted(p.name for p in source.iterdir() if p.name.endswith((".gff", ".tab.txt"))))
            for name in written:
                self.assertEqual((out.parent / name).read_bytes(), (source / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
