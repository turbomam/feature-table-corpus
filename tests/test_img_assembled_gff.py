"""The IMG 4.14 assembled GFF dialect accepts its known shapes and rejects edits."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("img_assembled_gff", ROOT / "scripts/img_assembled_gff.py")
dialect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect)
FIXTURE = ROOT / "tests/fixtures/img-assembled-gff/constructed.assembled.gff"
BUNDLE = ROOT / "corpus/sources/jgi-img/IMG_AP-1121004"
REAL = BUNDLE / "106476.assembled.gff"
TAXON = BUNDLE / "2708743150.gff"


def lines():
    return FIXTURE.read_text().splitlines()


class ParseTests(unittest.TestCase):
    def test_values_are_typed_and_repeats_kept(self):
        rows = dialect.parse(FIXTURE)["rows"]
        cds = rows[1]
        self.assertEqual((cds["strand"], cds["phase"], cds["conf"], cds["gc_cont"]), ("-1", 0, 100.0, 0.45))
        self.assertNotIn("score", cds)
        self.assertNotIn("phase", rows[0])
        self.assertEqual(rows[7]["LowScore"], [0.526, 0.526])
        self.assertEqual(rows[7]["attribute_order"][:3], ["ID", "LowScore", "LowScore"])

    def test_fixture_and_real_file_write_back_byte_for_byte(self):
        for path in (FIXTURE, REAL):
            text = path.read_text()
            written = dialect.write(dialect.parse(path))
            self.assertEqual(written, text, path.name)
            self.assertEqual(dialect.parse_lines(io.StringIO(written, newline=""), path)["rows"],
                             dialect.parse(path)["rows"])


class ValidateTests(unittest.TestCase):
    def run_on(self, text, taxon=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.assembled.gff"
            path.write_text(text)
            taxon_path = None
            if taxon is not None:
                taxon_path = Path(tmp) / "taxon.gff"
                taxon_path.write_text(taxon)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = dialect.validate(path, taxon=taxon_path)
            return status, out.getvalue()

    def edited(self, index, old, new):
        rows = lines()
        self.assertIn(old, rows[index], "the edit must change the fixture")
        rows[index] = rows[index].replace(old, new, 1)
        return "\n".join(rows) + "\n"

    def assert_text_rejected(self, text, expected, taxon=None):
        status, out = self.run_on(text, taxon)
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)

    def assert_rejected(self, index, old, new, expected):
        self.assert_text_rejected(self.edited(index, old, new), expected)

    def test_fixture_and_real_file_are_valid(self):
        status, out = self.run_on(FIXTURE.read_text())
        self.assertEqual(status, 0, out)
        status, out = self.run_on(REAL.read_text(), TAXON.read_text())
        self.assertEqual(status, 0, out)

    def test_columns(self):
        self.assert_rejected(1, "\t.\t-1\t0\t", "\t9.5\t-1\t0\t", "score '9.5'")
        self.assert_rejected(1, "\t.\t-1\t0\t", "\t.\t-\t0\t", "'-'")
        self.assert_rejected(1, "\t.\t-1\t0\t", "\t.\t-1\t.\t", "phase present on CDS or missing on CDS")
        self.assert_rejected(0, "\t1\t.\tID", "\t1\t0\tID", "phase present on rRNA")
        self.assert_rejected(1, "\t300\t950\t", "\t300\t951\t", "not a multiple of 3")
        self.assert_rejected(1, "\t300\t950\t", "\t951\t950\t", "start > end")
        self.assert_rejected(1, "Prodigal V2.6.3", "GeneMark 1.0", "is not what writes CDS rows")
        self.assert_rejected(1, "\tCDS\t", "\tgene\t", "'gene'")

    def test_column_nine(self):
        self.assert_rejected(1, "locus_tag=Ga0000001_1012;", "locus_tag=Ga0000001_1012", "does not end with ';'")
        self.assert_rejected(1, "conf=100.00;gc_cont=0.450;", "gc_cont=0.450;conf=100.00;", "are not a CDS key order")
        self.assert_rejected(1, "conf=100.00;", "conf=100.00;conf=100.00;", "conf repeats")
        self.assert_rejected(1, "conf=100.00;", "conf=100.0;", "is not written with 2 decimals")
        self.assert_rejected(1, "gc_cont=0.450;", "gc_cont=1.450;", "1.45")
        self.assert_rejected(1, "conf=100.00;", "conf=100.00;made_up=1;", "made_up")
        self.assert_rejected(1, "conf=100.00;", "start=5;", "names a column")

    def test_ids_and_locus_tags(self):
        self.assert_rejected(1, "ID=Ga0000001_101.2;", "ID=Ga0000001_102.2;", "does not start with its contig")
        self.assert_rejected(3, "ID=Ga0000001_101.4;", "ID=Ga0000001_101.2;", "ID number does not increase")
        self.assert_rejected(3, "ID=Ga0000001_101.4;", "ID=Ga0000001_101.2;", "'Ga0000001_101.2' repeats")
        self.assert_rejected(3, "locus_tag=Ga0000001_1014;", "locus_tag=Ga0000001_1015;", "is not Ga0000001_1014")

    def test_row_order(self):
        rows = lines()
        self.assert_text_rejected("\n".join(rows[:1] + rows[6:7] + rows[1:6] + rows[7:]) + "\n",
                                  "rows are not in one block")
        # Same length, so still a multiple of 3, but it starts before the misc_bind row above it.
        self.assert_rejected(3, "\t1120\t1551\t", "\t900\t1331\t", "start is before the previous row's")

    def test_values_that_must_agree(self):
        self.assert_rejected(6, "codon=CAA;", "codon=CAG;", "is not the reverse complement of 'TTG'")
        self.assert_rejected(0, "Type=23S rRNA. Bacterial LSU;", "Type=23S rRNA;", "Name, Type and product differ")
        self.assert_rejected(7, "LowScore=0.526;LowScore=0.526;", "LowScore=0.526;LowScore=0.6;", "LowScore values differ")
        self.assert_rejected(5, "Model=cspA;", "Model=TPP;", "Model 'TPP' has two accessions")

    def test_taxon_gff_must_match(self):
        row = "Ga0000001_101\timg_core_v400\tCDS\t300\t950\t.\t-\t0\tID=1;locus_tag=Ga0000001_1012;product=x\n"
        status, out = self.run_on(FIXTURE.read_text(), "##gff-version 3\n" + row)
        self.assertEqual(status, 0, out)
        self.assert_text_rejected(FIXTURE.read_text(), "has other coordinates or strand here",
                                  "##gff-version 3\n" + row.replace("\t-\t", "\t+\t"))
        self.assert_text_rejected(FIXTURE.read_text(), "locus_tag Ga0000001_9999 is not in this file",
                                  "##gff-version 3\n" + row.replace("_1012;", "_9999;"))
        self.assert_text_rejected(FIXTURE.read_text(), "has no rows with a locus_tag", "##gff-version 3\n")

    def test_line_shape(self):
        text = FIXTURE.read_text()
        self.assert_text_rejected(text.replace("\n", "\r\n"), "line 1: carriage return")
        self.assert_text_rejected(text[:-1], "no final newline")
        self.assert_text_rejected(text.replace("\n", "\n\n", 1), "line 2: blank line")
        self.assert_text_rejected("##gff-version 3\n" + text, "comment or directive")
        self.assert_text_rejected("", "no rows")
        self.assert_rejected(1, "\t300\t", "\t+300\t", "start '+300' is not a number")

    def test_parse_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing.json"
            existing.write_text("keep")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                status = dialect.main(["parse", str(FIXTURE), "--output", str(existing)])
            self.assertEqual(status, 2)
            self.assertEqual(existing.read_text(), "keep")
            self.assertIn("exists", err.getvalue())


if __name__ == "__main__":
    unittest.main()
