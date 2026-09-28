"""The IMG TMHMM and SignalP dialect accepts its known shapes and rejects edits."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("img_tmhmm_signalp_gff", ROOT / "scripts/img_tmhmm_signalp_gff.py")
dialect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect)
FIXTURES = ROOT / "tests/fixtures/img-tmhmm-signalp-gff"
METHODS = ("tmh", "cleavage_sites")
VENDORED = [ROOT / f"corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_{method}.gff" for method in METHODS]


def fixture(method):
    return FIXTURES / f"constructed_{method}.gff"


def lines(method):
    return fixture(method).read_text().splitlines()


class ParseTests(unittest.TestCase):
    def test_method_is_inferred_from_column_3(self):
        for method in METHODS:
            self.assertEqual(dialect.parse(fixture(method))["method"], method)

    def test_values_are_typed_and_keys_mapped(self):
        helix = dialect.parse(fixture("tmh"))["rows"][1]
        self.assertEqual((helix["type"], helix["start"], helix["end"]), ("TMhelix", 21, 43))
        self.assertNotIn("score", helix)
        site = dialect.parse(fixture("cleavage_sites"))["rows"][1]
        self.assertEqual((site["score"], site["D_score"], site["network"]), (0.45, 0.71, "SignalP-TM"))
        self.assertEqual(site["attribute_order"], ["D-score", "network", "organism_type"])
        self.assertNotIn("ID", site)

    def test_written_text_parses_back_to_the_same_rows(self):
        for method in METHODS:
            document = dialect.parse(fixture(method))
            text = dialect.write(document)
            again = dialect.parse_lines(io.StringIO(text, newline=""), fixture(method))
            self.assertEqual(again["rows"], document["rows"])
        # Only a trailing zero is respelled, as in the other IMG dialects.
        self.assertEqual(dialect.write(dialect.parse(fixture("tmh"))), fixture("tmh").read_text())
        self.assertIn("\t0.45\t.\t.\tD-score=0.71;", dialect.write(dialect.parse(fixture("cleavage_sites"))))


class ValidateTests(unittest.TestCase):
    def run_on(self, text, name):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / name
            path.write_text(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = dialect.validate(path)
            return status, out.getvalue()

    def edited(self, method, index, old, new):
        rows = lines(method)
        self.assertIn(old, rows[index], "the edit must change the fixture")
        rows[index] = rows[index].replace(old, new, 1)
        return "\n".join(rows) + "\n"

    def assert_text_rejected(self, text, expected, name="case_tmh.gff"):
        status, out = self.run_on(text, name)
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)

    def assert_rejected(self, method, index, old, new, expected):
        self.assert_text_rejected(self.edited(method, index, old, new), expected, f"case_{method}.gff")

    def test_fixtures_and_vendored_files_are_valid(self):
        for path in [fixture(method) for method in METHODS] + VENDORED:
            status, out = self.run_on(path.read_text(), path.name)
            self.assertEqual(status, 0, out)

    def test_unknown_key_is_rejected(self):
        self.assert_rejected("tmh", 0, "ID=ctg_01_100_1299_1_20", "ID=ctg_01_100_1299_1_20;made_up=1", "made_up")

    def test_method_must_be_known_and_agree(self):
        self.assert_rejected("tmh", 0, "\tOutside\t", "\tloop\t", "is not a TMHMM segment or SignalP site")
        self.assert_rejected("tmh", 1, "\tTMhelix\t", "\tcleavage_site\t", "is not a tmh row")
        self.assert_rejected("tmh", 1, "decodeanhmm 1.1g", "signalp 4.1", "is not what tmh files write")
        self.assert_text_rejected(fixture("tmh").read_text(), "file name says cleavage_sites but rows are tmh",
                                  "case_cleavage_sites.gff")

    def test_key_order_and_score_follow_the_method(self):
        self.assert_rejected("cleavage_sites", 0, "network=SignalP-noTM;organism_type=gram-",
                             "organism_type=gram-;network=SignalP-noTM", "are not the cleavage_sites order")
        self.assert_rejected("tmh", 0, "\t.\t.\t.\tID", "\t0.5\t.\t.\tID", "TMHMM rows have no score")
        self.assert_rejected("cleavage_sites", 0, "\t0.231\t", "\t.\t", "SignalP rows need a score")

    def test_ids_and_positions(self):
        self.assert_rejected("tmh", 0, "ID=ctg_01_100_1299_1_20", "ID=ctg_01_100_1299_1_21", "is not 'ctg_01_100_1299_1_20'")
        self.assert_rejected("tmh", 4, "\t84\t399\t.\t.\t.\tID=ctg_01_100_1299_84_399",
                             "\t84\t401\t.\t.\t.\tID=ctg_01_100_1299_84_401", "past the 400 codons")
        self.assert_rejected("cleavage_sites", 0, "\t25\t26\t", "\t25\t27\t", "end is start + 1")
        self.assert_rejected("cleavage_sites", 0, "\t25\t26\t", "\t27\t26\t", "start > end")
        rows = lines("tmh")
        self.assert_text_rejected("\n".join(rows[:2] + rows[1:]) + "\n", "ID 'ctg_01_100_1299_21_43' repeats")

    def test_segments_tile_the_protein(self):
        self.assert_rejected("tmh", 0, "\t1\t20\t.\t.\t.\tID=ctg_01_100_1299_1_20",
                             "\t2\t20\t.\t.\t.\tID=ctg_01_100_1299_2_20", "starts at 2, not 1")
        self.assert_rejected("tmh", 2, "\t44\t60\t.\t.\t.\tID=ctg_01_100_1299_44_60",
                             "\t45\t60\t.\t.\t.\tID=ctg_01_100_1299_45_60", "does not start right after")
        self.assert_rejected("tmh", 2, "\tInside\t", "\tTMhelix\t", "two helix or two non-helix segments")
        self.assert_rejected("tmh", 0, "\tOutside\t", "\tTMhelix\t", "begins or ends with a helix")
        self.assert_rejected("tmh", 4, "\tOutside\t", "\tInside\t", "Inside on both sides of a helix")
        self.assert_rejected("tmh", 4, "\t84\t399\t.\t.\t.\tID=ctg_01_100_1299_84_399",
                             "\t84\t398\t.\t.\t.\tID=ctg_01_100_1299_84_398", "ends at residue 398, not at its protein's end")
        rows = lines("tmh")
        self.assert_text_rejected("\n".join(rows[:3]) + "\n", "line 3: gene ctg_01_100_1299 ends at residue 60")

    def test_each_gene_is_one_block_with_a_helix(self):
        rows = lines("tmh")
        self.assert_text_rejected("\n".join(rows[1:] + rows[:1]) + "\n", "segments are not in one block")
        no_helix = rows[:5] + ["ctg_01_1600_2199\tdecodeanhmm 1.1g\tInside\t1\t200\t.\t.\t.\tID=ctg_01_1600_2199_1_200"]
        self.assert_text_rejected("\n".join(no_helix) + "\n", "no TMhelix")
        sites = lines("cleavage_sites")
        again = sites + [sites[0].replace("\t25\t26\t", "\t30\t31\t")]
        self.assert_text_rejected("\n".join(again) + "\n", "has more than one cleavage site", "case_cleavage_sites.gff")
        adjacent = sites[:1] + [sites[0].replace("\t25\t26\t", "\t30\t31\t")] + sites[1:]
        self.assert_text_rejected("\n".join(adjacent) + "\n", "line 2: gene ctg_01_100_1299 has more than one cleavage site",
                                  "case_cleavage_sites.gff")

    def test_schema_values(self):
        self.assert_rejected("cleavage_sites", 0, "network=SignalP-noTM", "network=SignalP-XX", "SignalP-XX")
        self.assert_rejected("cleavage_sites", 0, "organism_type=gram-", "organism_type=gram+", "gram+")
        self.assert_rejected("cleavage_sites", 0, "D-score=0.646", "D-score=1.5", "1.5")
        self.assert_rejected("tmh", 0, "\t.\t.\tID", "\t+\t.\tID", "'+'")

    def test_numbers_must_be_plain_ascii(self):
        self.assert_rejected("tmh", 0, "\t1\t20\t", "\t+1\t20\t", "start '+1' is not a number")
        self.assert_rejected("cleavage_sites", 0, "D-score=0.646", "D-score=0.6_46", "is not a float")

    def test_line_shape(self):
        text = fixture("tmh").read_text()
        self.assert_text_rejected(text.replace("\n", "\r\n"), "line 1: carriage return")
        self.assert_text_rejected(text[:-1], "no final newline")
        self.assert_text_rejected(text.replace("\n", "\n\n", 1), "line 2: blank line")
        self.assert_text_rejected("# comment\n" + text, "comment or directive")
        self.assert_text_rejected("", "no rows")
        self.assert_rejected("tmh", 0, "\t.\tID", "\tID", "8 columns, expected 9")

    def test_parse_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing.json"
            existing.write_text("keep")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status = dialect.main(["parse", str(fixture("tmh")), "--output", str(existing)])
            self.assertEqual(status, 2)
            self.assertEqual(existing.read_text(), "keep")
            self.assertIn("exists", err.getvalue())


if __name__ == "__main__":
    unittest.main()
