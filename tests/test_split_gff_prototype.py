"""The split prototype stores embedded FASTA sequences in DuckDB and rebuilds the file byte for byte."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/split_gff_prototype.py"
HEAD = b"##gff-version 3\n##FASTA\n"

# Small GFF3 files for the four cases in the review of
# https://github.com/turbomam/feature-table-corpus/pull/188, plus a regular sequence.
CASES = {
    "space inside a sequence line": HEAD + b">s1\nAC GT\n",
    "no final newline": HEAD + b">s1\nAA\nCC",
    "mixed CRLF and LF": HEAD + b">s1\nAA\r\nCC\nGG\n",
    "header only": HEAD + b">s1\n>s2\nAC\n",
    "blank lines between sequence lines": HEAD + b">s1\nAA\n\nCC\n\nGG\n",
    "regular layout": HEAD + b">s1 description\nACGT\nACGT\nAC\n>s2\nGG\n",
}


class SplitPrototypeTests(unittest.TestCase):
    def split(self, content):
        """Run the prototype on content; return its JSON summary and the biosequence rows."""
        with tempfile.TemporaryDirectory() as directory:
            gff, database = Path(directory, "input.gff3"), Path(directory, "split.duckdb")
            gff.write_bytes(content)
            result = subprocess.run([sys.executable, str(SCRIPT), str(gff), str(database)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            con = duckdb.connect(str(database), read_only=True)
            columns = [d[0] for d in con.execute("SELECT * FROM biosequence").description]
            rows = [dict(zip(columns, values)) for values in
                    con.execute("SELECT * FROM biosequence ORDER BY header_line_number").fetchall()]
            con.close()
        return json.loads(result.stdout), rows

    def test_residues_and_length_leave_out_spaces(self):
        _, rows = self.split(CASES["space inside a sequence line"])
        self.assertEqual((rows[0]["residues"], rows[0]["length"]), ("ACGT", 4))

    def test_sequence_without_final_newline_or_with_mixed_endings_rebuilds(self):
        for name in ("no final newline", "mixed CRLF and LF"):
            with self.subTest(name):
                self.assertTrue(self.split(CASES[name])[0]["rebuilt_identical"])

    def test_header_only_sequence_rebuilds(self):
        summary, rows = self.split(CASES["header only"])
        self.assertTrue(summary["rebuilt_identical"])
        self.assertEqual(rows[0]["length"], 0)

    def test_blank_lines_between_sequence_lines_stay_in_place(self):
        self.assertTrue(self.split(CASES["blank lines between sequence lines"])[0]["rebuilt_identical"])

    def test_byte_order_mark_is_not_part_of_the_sequence_id(self):
        summary, rows = self.split(b"\xef\xbb\xbf>s1\nAC\n")
        self.assertTrue(summary["rebuilt_identical"])
        self.assertEqual(rows[0]["sequence_id"], "s1")

    def test_refuses_to_write_the_database_over_the_input(self):
        with tempfile.TemporaryDirectory() as directory:
            gff = Path(directory, "input.gff3")
            gff.write_bytes(CASES["regular layout"])
            result = subprocess.run([sys.executable, str(SCRIPT), str(gff), str(gff)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(gff.read_bytes(), CASES["regular layout"])

    def test_every_case_round_trips(self):
        for name, content in CASES.items():
            with self.subTest(name):
                self.assertTrue(self.split(content)[0]["rebuilt_identical"])

    def test_regular_layout_uses_faidx_columns(self):
        _, rows = self.split(CASES["regular layout"])
        first = rows[0]
        self.assertEqual((first["residues"], first["length"]), ("ACGTACGTAC", 10))
        # samtools faidx LINEBASES, LINEWIDTH and OFFSET (byte of the first base).
        offset = len(HEAD + b">s1 description\n")
        self.assertEqual((first["line_bases"], first["line_bytes"], first["offset"]), (4, 5, offset))
        self.assertIsNone(first["lines"])


if __name__ == "__main__":
    unittest.main()
