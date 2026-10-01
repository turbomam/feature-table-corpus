"""The Populus excerpt keeps whole gene blocks up to the limit and adds the four provenance lines."""
import contextlib
import gzip
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import populus_excerpt  # noqa: E402

HEAD = "##gff-version 3\n##annot-version v4.1\n##species Populus trichocarpa\n"


def gene(n, chrom="Chr01"):
    gid = f"Potri.001G{n:06d}"
    return (f"{chrom}\tphytozomev13\tgene\t{n}00\t{n}99\t.\t+\t.\tID={gid}.v4.1;Name={gid}\n"
            f"{chrom}\tphytozomev13\tmRNA\t{n}00\t{n}99\t.\t+\t.\tID={gid}.1.v4.1;Name={gid}.1;pacid={n};longest=1;"
            f"Parent={gid}.v4.1\n")


class ExcerptTests(unittest.TestCase):
    def write(self, tmp, text):
        path = Path(tmp) / "source.gff3.gz"
        with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def test_whole_blocks_up_to_the_limit_and_four_provenance_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.write(tmp, HEAD + gene(1) + gene(2) + gene(3))
            text = populus_excerpt.excerpt(source, genes=2, digest="abc")
        lines = text.splitlines(keepends=True)
        self.assertEqual("".join(lines[:3]), HEAD)
        self.assertEqual([line.split(":")[0] for line in lines[3:7]], ["# derived-from", "# single-change", "# validity", "# cite"])
        self.assertIn("md5 abc", lines[3])
        self.assertIn("doi:10.1126/science.1128691", lines[6])
        self.assertEqual("".join(lines[7:]), gene(1) + gene(2))

    def test_the_table_excerpt_keeps_the_excerpts_genes_in_table_order(self):
        header = "#pacId\tlocusName\ttranscriptName\tpeptideName\tPfam\n"
        rows = ["PAC:1\tPotri.001G000001\tPotri.001G000001.1\tPotri.001G000001.1.p\t\n",
                "PAC:2\tPotri.001G000002\tPotri.001G000002.1\tPotri.001G000002.1.p\t\n",
                "PAC:3\tPotri.001G000003\tPotri.001G000003.1\tPotri.001G000003.1.p\t\n"]
        with tempfile.TemporaryDirectory() as tmp:
            table = Path(tmp) / "table.txt"
            table.write_text(header + "".join(rows))
            text = populus_excerpt.table_excerpt(table, HEAD + gene(1) + gene(2), digest="def")
            lines = text.splitlines(keepends=True)
            self.assertEqual(lines[0], header)
            self.assertEqual([line.split(":")[0] for line in lines[1:5]], ["# derived-from", "# single-change", "# validity", "# cite"])
            self.assertEqual("".join(lines[5:]), "".join(rows[:2]))
            with self.assertRaisesRegex(ValueError, "no rows for 1 of the excerpt's genes"):
                populus_excerpt.table_excerpt(table, HEAD + gene(1) + gene(4))

    def test_too_few_genes_on_chr01_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.write(tmp, HEAD + gene(1) + gene(2, chrom="Chr02"))
            with self.assertRaisesRegex(ValueError, "reached Chr02 before 2 genes on Chr01"):
                populus_excerpt.excerpt(source, genes=2)

    def test_a_missing_or_wrong_source_is_an_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            for source, expected in ((Path(tmp) / "missing.gz", "No such file"),
                                     (self.write(tmp, HEAD + gene(1)), "expected 3fdcfdd5")):
                err = io.StringIO()
                with self.subTest(source.name), contextlib.redirect_stderr(err):
                    self.assertEqual(populus_excerpt.main([str(source), str(Path(tmp) / "out.gff3")]), 1)
                self.assertIn(expected, err.getvalue())
                self.assertFalse((Path(tmp) / "out.gff3").exists())


if __name__ == "__main__":
    unittest.main()
