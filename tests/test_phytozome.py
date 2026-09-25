"""The Phytozome gene_exons GFF3 and annotation_info dialects, and their join, reject single-row edits."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phytozome_annotation_info as table  # noqa: E402
import phytozome_gene_exons as gff3  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/phytozome"
GFF3 = FIXTURES / "constructed.gene_exons.gff3"
TABLE = FIXTURES / "constructed.annotation_info.txt"


def edited(path, index, old, new):
    """The file's text with one line changed; new=None removes the line."""
    lines = path.read_text().splitlines()
    if old not in lines[index]:
        raise AssertionError(f"the edit must change the fixture: {old!r} not in line {index + 1}")
    if new is None:
        del lines[index]
    else:
        lines[index] = lines[index].replace(old, new, 1)
    return "\n".join(lines) + "\n"


class Case(unittest.TestCase):
    def run_command(self, function, texts, suffixes):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for number, (text, suffix) in enumerate(zip(texts, suffixes)):
                path = Path(tmp) / f"case{number}{suffix}"
                path.write_text(text)
                paths.append(path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = function(*paths)
            return status, out.getvalue()

    def assert_rejected(self, function, texts, suffixes, expected):
        status, out = self.run_command(function, texts, suffixes)
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)


class GeneExonsParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = gff3.parse(GFF3)

    def test_header_and_types(self):
        self.assertEqual((self.document["gff_version"], self.document["annot_version"]), ("3", "EXv1"))
        mrna = self.document["rows"][1]
        self.assertEqual((mrna["line"], mrna["longest"], mrna["pacid"]), (4, 1, "90000001"))
        self.assertNotIn("phase", self.document["rows"][2])
        self.assertEqual(self.document["rows"][20]["phase"], 2)

    def test_writer_reproduces_the_fixture_and_refuses_what_it_cannot_write(self):
        self.assertEqual(gff3.write(self.document), GFF3.read_text())
        broken = copy.deepcopy(self.document)
        broken["rows"][0]["Name"] = "a;b"
        with self.assertRaisesRegex(gff3.DialectError, "doesn't write"):
            gff3.write(broken)

    def test_gzip_input_is_read_as_a_stream(self):
        import gzip
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.gff3.gz"
            with gzip.open(path, "wt") as handle:
                handle.write(GFF3.read_text())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(gff3.validate(path), 0)


class GeneExonsRuleTests(Case):
    def rejected(self, index, old, new, expected):
        self.assert_rejected(gff3.validate, [edited(GFF3, index, old, new)], [".gff3"], expected)

    def test_fixture_is_valid(self):
        status, out = self.run_command(gff3.validate, [GFF3.read_text()], [".gff3"])
        self.assertEqual(status, 0, out)

    def test_directives(self):
        self.rejected(0, "##gff-version 3", "##gff-version 3.1.26", "'3.1.26' does not match")
        self.rejected(1, "##annot-version EXv1", "##annot-version", "expected '##annot-version <value>'")
        self.rejected(5, "scaffold_1", "#scaffold_1", "comment or directive after the two opening directives")

    def test_line_shape(self):
        self.rejected(2, "\tgene\t", "\t", "8 columns, expected 9")
        self.rejected(4, "\t1000\t1300\t", "\tabc\t1300\t", "start 'abc' is not a number")
        self.rejected(4, "\t.\t+\t.\t", "\t12\t+\t.\t", "score '12'; this dialect writes none")
        self.rejected(4, "exon.1;", "exon.1;;", "empty attribute")
        self.rejected(4, "pacid=90000001", "pacid", "has no value")

    def test_blank_line(self):
        lines = GFF3.read_text().splitlines()
        self.assertTrue(lines[23])
        lines[23] = ""
        self.assert_rejected(gff3.validate, ["\n".join(lines) + "\n"], [".gff3"], "line 24: blank line")

    def test_column_nine_values(self):
        self.rejected(2, "Name=Exa01g00010", "Name=Exa01g00010%2C", "a percent escape")
        self.rejected(4, "Parent=Exa01g00010.1.EXv1", "Parent=Exa01g00010.1.EXv1,Exa01g00010.2.EXv1",
                      "a second value")
        self.rejected(3, "longest=1", "longest=x", "longest 'x' is not a integer")
        self.rejected(2, "Name=Exa01g00010", "Name=Exa01g00010;start=5", "names a column")
        self.rejected(2, "Name=Exa01g00010", "Name=Exa01g00010;Name=Exa01g00010", "Name repeats")

    def test_schema_rules(self):
        self.rejected(2, "Name=Exa01g00010", "Name=Exa01g00010;Note=x", "'Note' was unexpected")
        self.rejected(2, "phytozomev10", "phytozome", "'phytozome' does not match")
        self.rejected(4, "\texon\t", "\tncRNA\t", "'ncRNA' is not one of")
        self.rejected(2, "\t+\t", "\t.\t", "'.' is not one of")
        self.rejected(6, "\t+\t0\t", "\t+\t3\t", "3 is greater than the maximum of 2")
        self.rejected(3, "longest=1", "longest=2", "2 is greater than the maximum of 1")
        self.rejected(3, "pacid=90000001", "pacid=090000001", "'090000001' does not match")

    def test_schema_problems_name_the_source_line_across_chunks(self):
        with mock.patch.object(gff3, "CHUNK", 5):
            self.rejected(20, "phytozomev10", "phytozome", "/line 21")

    def test_key_order(self):
        self.rejected(3, "pacid=90000001;longest=1", "longest=1;pacid=90000001", "mRNA keys are")

    def test_row_rules(self):
        self.rejected(11, "exon.1;", "exon.2;", "is not 'Exa01g00010.2.EXv1.exon.1'")
        self.rejected(4, "\t1000\t1300\t", "\t1400\t1300\t", "start > end")
        self.rejected(4, "\t+\t.\tID", "\t+\t0\tID", "phase present on exon")
        self.rejected(6, "\t+\t0\tID", "\t+\t.\tID", "phase present on CDS or missing on CDS")

    def test_unique_ids_and_pacids(self):
        self.rejected(11, "ID=Exa01g00010.2.EXv1.exon.1", "ID=Exa01g00010.1.EXv1.exon.1", "repeats")
        self.rejected(10, "pacid=90000002", "pacid=90000001", "pacid '90000001' repeats")

    def test_gene_and_mrna_names(self):
        self.rejected(2, "Name=Exa01g00010", "Name=Exa01g00011", "gene ID 'Exa01g00010.EXv1' is not Name")
        self.rejected(3, "Name=Exa01g00010.1;", "Name=Exa01g00010.1a;", "is not its gene's Name plus a number")
        self.rejected(3, "ID=Exa01g00010.1.EXv1;", "ID=Exa01g00010.1.EXv2;", "mRNA ID 'Exa01g00010.1.EXv2'")

    def test_hierarchy(self):
        self.rejected(15, "Parent=Exa01g00020.EXv1", "Parent=Exa01g00010.EXv1", "is not the gene row before")
        self.rejected(11, "Parent=Exa01g00010.2.EXv1", "Parent=Exa01g00010.1.EXv1", "is not the mRNA row before")
        self.rejected(3, "\t1000\t2400\t", "\t1000\t2500\t", "mRNA is not inside its gene")
        self.rejected(23, "\t3000\t3100\t", "\t2990\t3100\t", "three_prime_UTR is not inside its mRNA")
        self.rejected(4, "pacid=90000001", "pacid=90000009", "differs from its mRNA's '90000001'")

    def test_parts_are_numbered_in_transcription_order(self):
        self.rejected(8, "CDS.2;", "CDS.3;", "is not 'Exa01g00010.1.EXv1.CDS.2'")
        self.rejected(18, "\t3800\t4000\t", "\t4300\t4400\t", "does not follow the previous exon")

    def test_block_rules(self):
        self.assert_rejected(gff3.validate, [edited(GFF3, 13, "\tCDS\t", None)], [".gff3"],
                             "line 11: mRNA has no exon or no CDS")
        self.assert_rejected(gff3.validate, [edited(GFF3, 15, "\tmRNA\t", None)], [".gff3"],
                             "line 15: gene has no mRNA")
        self.rejected(7, "\t1500\t2400\t", "\t1500\t2300\t", "mRNA span is not the span of its exons")
        self.rejected(8, "\t1500\t2200\t", "\t1450\t2200\t", "CDS is not inside one of its mRNA's exons")
        self.rejected(2, "\t1000\t2400\t", "\t1000\t2500\t", "gene span is not the span of its mRNAs")

    def test_one_representative_isoform_per_gene(self):
        self.rejected(10, "longest=0", "longest=1", "gene has 2 mRNAs with longest=1, expected 1")
        self.rejected(3, "longest=1", "longest=0", "gene has 0 mRNAs with longest=1, expected 1")


def table_row(index, old, new):
    return edited(TABLE, index, old, new)


class AnnotationInfoTests(Case):
    def rejected(self, index, old, new, expected):
        self.assert_rejected(table.validate, [table_row(index, old, new)], [".txt"], expected)

    def test_parse_and_write(self):
        document = table.parse(TABLE)
        first, second = document["rows"][:2]
        self.assertEqual(first["pacId"], "PAC:90000001")
        self.assertEqual(first["ec"], ["EC:2.7.11.1", "EC:PROLINE-MULTI"])
        self.assertEqual(first["best_hit_clamy_defline"], "(1 of 2) PTHR10000//PTHR10000:SF2 - EXAMPLE FAMILY, SUBFAMILY 2")
        self.assertNotIn("GO", second)
        self.assertEqual(table.write(document), TABLE.read_text())
        document["rows"][0]["Pfam"] = ["PF00001 PF00002"]
        with self.assertRaisesRegex(gff3.DialectError, "doesn't write"):
            table.write(document)

    def test_fixture_is_valid(self):
        status, out = self.run_command(table.validate, [TABLE.read_text()], [".txt"])
        self.assertEqual(status, 0, out)

    def test_file_shape(self):
        self.rejected(0, "#pacId", "pacId", "header is not the 14 Phytozome columns")
        self.rejected(1, "\tPF00001 PF00002\t", "\tPF00001 PF00002 ", "13 columns, expected 14")
        self.rejected(1, "PF00001 PF00002", "PF00001  PF00002", "has an empty value")
        self.rejected(3, "PAC:90000003", "#PAC:90000003", "comment after the header")
        lines = TABLE.read_text().splitlines()
        lines[2] = ""
        self.assert_rejected(table.validate, ["\n".join(lines) + "\n"], [".txt"], "line 3: blank line")
        self.assert_rejected(table.validate, [""], [".txt"], "empty file")

    def test_value_patterns(self):
        self.rejected(1, "PAC:90000001", "90000001", "'90000001' does not match")
        self.rejected(1, "PF00002", "PF2", "'PF2' does not match")
        self.rejected(1, "PTHR10000.SF1", "PTHR10000-SF1", "'PTHR10000-SF1' does not match")
        self.rejected(3, "EC:1.1.1.-", "1.1.1.-", "'1.1.1.-' does not match")
        self.rejected(1, "KOG0001", "KOG1", "'KOG1' does not match")
        self.rejected(1, "K00001", "KO:K00001", "'KO:K00001' does not match")
        self.rejected(3, "GO:0000003", "GO:3", "'GO:3' does not match")
        self.rejected(1, "(1 of 1) PF00001", "PF00001", "'PF00001 - Example domain' does not match")
        self.rejected(2, "Cre99.g999902", "Cre99 g999902", "'Cre99 g999902' does not match")
        self.rejected(1, "\tExa01g00010\t", "\tExa01 g00010\t", "'Exa01 g00010' does not match")

    def test_row_rules(self):
        self.rejected(3, "PAC:90000003", "PAC:90000001", "pacId 'PAC:90000001' repeats")
        self.rejected(2, "Exa01g00010.2\tExa01g00010.2", "Exa01g00010.1\tExa01g00010.1",
                      "transcriptName 'Exa01g00010.1' repeats")
        self.rejected(3, "Exa01g00020\t", "Exa01g00030\t", "does not start with locusName")
        self.rejected(1, "Exa01g00010.1\tPF00001", "Exa01g00010.9\tPF00001", "peptideName differs")
        self.rejected(1, "PF00001 PF00002", "PF00001 PF00001", "Pfam repeats a value")
        self.rejected(1, "Cre99.g999901\t", "\t", "Best-hit-clamy-defline without its name")


class JoinTests(Case):
    def joined(self, gff3_text, table_text):
        return self.run_command(table.join, [gff3_text, table_text], [".gff3", ".txt"])

    def test_fixtures_join(self):
        status, out = self.joined(GFF3.read_text(), TABLE.read_text())
        self.assertEqual(status, 0, out)

    def test_unmatched_pacid_is_reported_on_both_sides(self):
        status, out = self.joined(GFF3.read_text(), table_row(3, "PAC:90000003", "PAC:90000004"))
        self.assertEqual(status, 1, out)
        self.assertIn("'PAC:90000004' is not the pacid of any GFF3 mRNA row", out)
        self.assertIn("GFF3 line 16: mRNA 'Exa01g00020.1' pacid 90000003 has no table row", out)

    def test_names_must_agree(self):
        status, out = self.joined(GFF3.read_text(), table_row(2, "\tExa01g00010.2\t", "\tExa01g00010.3\t"))
        self.assertEqual(status, 1, out)
        self.assertIn("transcriptName 'Exa01g00010.3' is not GFF3 line 11 Name 'Exa01g00010.2'", out)
        status, out = self.joined(GFF3.read_text(), table_row(3, "\tExa01g00020\t", "\tExa01g00010\t"))
        self.assertEqual(status, 1, out)
        self.assertIn("locusName 'Exa01g00010' is not the gene Name 'Exa01g00020'", out)

    def test_a_gff3_that_does_not_parse_is_reported(self):
        status, out = self.joined(edited(GFF3, 0, "##gff-version 3", "gff"), TABLE.read_text())
        self.assertEqual(status, 1, out)
        self.assertIn("expected '##gff-version <value>'", out)


if __name__ == "__main__":
    unittest.main()
