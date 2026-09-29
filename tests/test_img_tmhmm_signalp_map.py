"""IMG TMHMM and SignalP files map to the feature model and back, byte for byte, and loss is refused."""
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
import img_tmhmm_signalp_map as mapping  # noqa: E402

REAL = ROOT / "corpus/sources/jgi-img/IMG_AP-1268149"
FUNCTIONAL = REAL / "Ga0423362_functional_annotation.gff"
TMH = REAL / "Ga0423362_tmh.gff"
SIGNALP = REAL / "Ga0423362_cleavage_sites.gff"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = mapping._transformers()
        cls.functional, cls.documents, problems = mapping.parse_inputs(FUNCTIONAL, [TMH, SIGNALP])
        assert not problems, problems
        cls.spellings = mapping.source_spellings(cls.functional, cls.documents)
        cls.dataset = mapping.forward(cls.functional, cls.documents, cls.transformers, cls.spellings)
        cls.scores = mapping.functional.score_spellings(cls.dataset, cls.spellings)

    def feature(self, dataset, feature_id):
        return next(f for f in dataset["features"] if f["feature_id"] == feature_id)

    def back(self, dataset):
        return mapping.reverse(dataset, "out", self.transformers, self.scores)

    def test_vendored_files_round_trip_byte_for_byte(self):
        problems, report = mapping.roundtrip(FUNCTIONAL, [TMH, SIGNALP])
        self.assertEqual(problems, [])
        self.assertEqual([(f["method"], f["rows"]) for f in report["files"]],
                         [("tmh", 9710), ("cleavage_sites", 146)])

    def test_a_segment_and_a_site_are_on_their_cds(self):
        helix = self.feature(self.dataset, "Ga0423362_01_7361_8026_10_29|tmh|TMhelix")
        self.assertEqual((helix["seqid"], helix["start"], helix["end"], helix["coordinate_system"], helix["parent"]),
                         ("Ga0423362_01_7361_8026", 10, 29, "protein", ["Ga0423362_01_7361_8026"]))
        self.assertNotIn("score", helix)
        self.assertEqual(helix["attributes"], [{"key": "ID", "value": "Ga0423362_01_7361_8026_10_29"}])
        site = self.feature(self.dataset, "Ga0423362_01_39667_41136_21_22|cleavage_sites|cleavage_site")
        self.assertEqual(site["score"], 0.181)
        self.assertNotIn("score_type", site)
        # The source spells the D-score 0.670; the Attribute keeps it.
        self.assertEqual(site["attributes"][0], {"key": "D-score", "value": "0.670"})

    def test_reverse_refuses_what_the_files_cannot_hold(self):
        site_id = "Ga0423362_01_39667_41136_21_22|cleavage_sites|cleavage_site"
        helix_id = "Ga0423362_01_7361_8026_10_29|tmh|TMhelix"
        cases = {
            "feature_id": (lambda d: self.feature(d, site_id).update(feature_id=site_id + "x"), "feature_id should be"),
            "parent": (lambda d: self.feature(d, site_id).update(parent=["Ga0423362_01_1_2"]), "only parent"),
            "score_type": (lambda d: self.feature(d, site_id).update(score_type="bit_score"), "no stable_identifiers or score_type"),
            "type": (lambda d: self.feature(d, helix_id).update(type="Pfam"), "not a TMHMM segment"),
            "unknown key": (lambda d: self.feature(d, helix_id)["attributes"].append({"key": "made_up", "value": "1"}),
                            "not the tmh keys"),
            "semicolon": (lambda d: self.feature(d, site_id)["attributes"][1].update(value="a;b"), "contains ';'"),
            "no hits": (lambda d: d.update(features=[f for f in d["features"] if f["coordinate_system"] != "protein"]),
                        "needs some"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(dataset)
                with self.assertRaisesRegex(ValueError, expected):
                    self.back(dataset)

    def test_an_edited_score_is_written_not_its_old_spelling(self):
        site_id = "Ga0423362_01_39667_41136_21_22|cleavage_sites|cleavage_site"
        dataset = copy.deepcopy(self.dataset)
        self.feature(dataset, site_id)["score"] = 0.5
        functional_document, documents = self.back(dataset)
        spellings = mapping.write_spellings(dataset, [functional_document] + documents, self.scores)
        text = mapping.dialect.write(documents[1], spellings[2])
        self.assertIn("\t21\t22\t0.5\t", text)

    def test_commands_write_every_file_byte_for_byte_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset, spelling, prefix = Path(tmp) / "d.json", Path(tmp) / "s.json", Path(tmp) / "Ga0423362"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                run = ["forward", FUNCTIONAL, TMH, SIGNALP, dataset, "--spelling", spelling]
                self.assertEqual(mapping.main([str(a) for a in run]), 0, err.getvalue())
                back = ["reverse", dataset, prefix, "--spelling", spelling]
                self.assertEqual(mapping.main([str(a) for a in back]), 0, err.getvalue())
                self.assertEqual(mapping.main([str(a) for a in back]), 1)
            self.assertIn("already exists", err.getvalue())
            self.assertEqual(len(json.loads(dataset.read_text())["features"]), 14295)
            for source in (FUNCTIONAL, TMH, SIGNALP):
                self.assertEqual((Path(tmp) / source.name).read_bytes(), source.read_bytes(), source.name)

    def test_a_failed_write_removes_the_partial_file_and_the_earlier_ones(self):
        from unittest import mock
        real, calls = mapping.write_new, []
        def fail_second(path, text):
            calls.append(path)
            if len(calls) == 2:
                Path(path).write_text("partial")
                return False, True
            return real(path, text)
        with tempfile.TemporaryDirectory() as tmp:
            dataset, out = Path(tmp) / "d.json", Path(tmp) / "out"
            out.mkdir()
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main([str(a) for a in ["forward", FUNCTIONAL, TMH, dataset]]), 0)
                with mock.patch.object(mapping, "write_new", fail_second):
                    self.assertEqual(mapping.main(["reverse", str(dataset), str(out / "g")]), 1)
            self.assertEqual(list(out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
