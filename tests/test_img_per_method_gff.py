"""The IMG per-method hit dialect accepts its known shapes and rejects edits."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("img_per_method_gff", ROOT / "scripts/img_per_method_gff.py")
dialect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect)
FIXTURES = ROOT / "tests/fixtures/img-per-method-gff"
METHODS = ("pfam", "cog", "ko_ec", "tigrfam", "smart", "supfam", "cath_funfam")
NMDC = sorted(path for method in METHODS for path in (ROOT / "corpus/sources/nmdc").glob(f"*_{method}.gff"))


def fixture(method):
    return FIXTURES / f"constructed_{method}.gff"


def lines(method):
    return fixture(method).read_text().splitlines()


class ParseTests(unittest.TestCase):
    def test_method_is_inferred_from_column_3(self):
        for method in METHODS:
            self.assertEqual(dialect.parse(fixture(method))["method"], method)

    def test_values_are_typed_and_keys_mapped(self):
        first, second, _ = dialect.parse(fixture("ko_ec"))["rows"]
        self.assertEqual(first["score"], 1220.0)
        self.assertEqual(first["subject_gene_ids"], ["637175796", "650950158"])
        self.assertEqual(second["type"], "KO:K01990_KO:K01992__EC:7.6.2.-_EC:3.6.3.-")
        cog = dialect.parse(fixture("cog"))["rows"][0]
        self.assertEqual(cog["source"], "")
        self.assertEqual(cog["independent_domain_e_value"], "1.1e-75")
        self.assertIn("independent_domain_e-value", cog["attribute_order"])
        self.assertNotIn("phase", cog)

    def test_written_text_parses_back_to_the_same_rows(self):
        for method in METHODS:
            document = dialect.parse(fixture(method))
            again = dialect.parse_lines(dialect.write(document).splitlines(keepends=True), fixture(method))
            self.assertEqual(again["rows"], document["rows"])


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

    def assert_rejected(self, method, index, old, new, expected, name=None):
        status, out = self.run_on(self.edited(method, index, old, new), name or f"case_{method}.gff")
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)

    def test_fixtures_and_vendored_nmdc_files_are_valid(self):
        self.assertEqual(len(NMDC), 8)
        for path in [fixture(method) for method in METHODS] + NMDC:
            status, out = self.run_on(path.read_text(), path.name)
            self.assertEqual(status, 0, out)

    def test_unknown_key_is_rejected(self):
        self.assert_rejected("pfam", 0, "model_end=339", "model_end=339;made_up=1", "made_up")

    def test_accession_of_another_method_is_rejected(self):
        self.assert_rejected("pfam", 1, "PF00005", "COG0001", "'COG0001' is not a pfam accession")

    def test_malformed_accession_is_rejected(self):
        self.assert_rejected("pfam", 1, "PF00005", "PF5", "PF5")
        self.assert_rejected("pfam", 0, "PF00202", "PF202", "not an accession of any known method")

    def test_ko_ec_packing_is_exact(self):
        # One underscore joins KOs and ECs within a list; two separate the lists.
        self.assert_rejected("ko_ec", 1, "KO:K01990_KO:K01992", "KO:K01990,KO:K01992", "KO:K01990,KO:K01992")
        self.assert_rejected("ko_ec", 0, "KO:K01845__EC", "KO:K01845_EC", "KO:K01845_EC:5.4.3.8")

    def test_source_follows_the_method(self):
        self.assert_rejected("cog", 0, "ctg_01_1600_2199\t\t", "ctg_01_1600_2199\t.\t", "is not what cog files write")
        self.assert_rejected("pfam", 1, "HMMER 3.1b2 (February 2015)", "", "is not what pfam files write")

    def test_key_order_is_fixed_per_method(self):
        self.assert_rejected("pfam", 0, "Name=Aminotran_3;fake_percent_id=99.10",
                             "fake_percent_id=99.10;Name=Aminotran_3", "are not the pfam order")
        self.assert_rejected("tigrfam", 0, "e-value=0;", "", "are not the tigrfam order")
        self.assert_rejected("pfam", 0, "e-value=13", "evalue=13", "are not the pfam order")

    def test_id_must_match_columns(self):
        self.assert_rejected("cog", 0, "ID=ctg_01_1600_2199_3_198", "ID=ctg_01_1600_2199_3_199",
                             "is not 'ctg_01_1600_2199_3_198'")

    def test_repeated_id_is_rejected(self):
        rows = lines("cath_funfam")
        text = "\n".join(rows + rows[:1]) + "\n"
        status, out = self.run_on(text, "case_cath_funfam.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("line 3: ID 'ctg_01_100_1299_40_300' repeats", out)

    def test_alignment_length_must_span_the_hit(self):
        self.assert_rejected("smart", 0, "alignment_length=151", "alignment_length=150", "is not end - start + 1")

    def test_hit_must_end_within_the_protein(self):
        # Gene 1600..2199 is 600 nt, so its protein has at most 200 residues.
        self.assert_rejected("cog", 1, "\t10\t190\t44.0\t.\t.\tID=ctg_01_1600_2199_10_190;fake_percent_id=40.20;alignment_length=181",
                             "\t10\t201\t44.0\t.\t.\tID=ctg_01_1600_2199_10_201;fake_percent_id=40.20;alignment_length=192",
                             "end 201 is past the 200 codons")

    def test_start_after_end_is_rejected(self):
        self.assert_rejected("tigrfam", 0, "\t8\t396\t", "\t397\t396\t", "start > end")

    def test_model_and_subject_positions_are_ordered(self):
        self.assert_rejected("supfam", 0, "model_start=1;", "model_start=400;", "model_start > model_end")
        self.assert_rejected("ko_ec", 1, "subject_start=5;", "subject_start=204;", "subject_start > subject_end")
        self.assert_rejected("ko_ec", 1, "subject_gene_length=240", "subject_gene_length=202",
                             "subject_end is past subject_gene_length")
        self.assert_rejected("ko_ec", 2, "query_gene_length=296", "query_gene_length=295",
                             "end is past query_gene_length")

    def test_protein_rows_have_no_strand_or_phase(self):
        self.assert_rejected("supfam", 0, "372.9\t.\t.", "372.9\t+\t.", "'+' is not one of")
        self.assert_rejected("supfam", 0, "372.9\t.\t.", "372.9\t.\t0", "'phase' was unexpected")

    def test_value_ranges_and_forms(self):
        self.assert_rejected("cath_funfam", 0, "fake_percent_id=96.00", "fake_percent_id=100.5", "100.5")
        self.assert_rejected("smart", 0, "full_sequence_e-value=2.9e-26", "full_sequence_e-value=2.9e+26", "2.9e+26")
        self.assert_rejected("ko_ec", 0, "subject_gene_ids=637175796,650950158", "subject_gene_ids=637175796,x",
                             "'x'")
        self.assert_rejected("ko_ec", 0, "\t1.22e+03\t", "\thigh\t", "score 'high' is not a number")
        self.assert_rejected("pfam", 2, "Name=zf-CCHC", "Name=zf CCHC", "zf CCHC")

    def test_only_source_spellings_of_hyphenated_keys_are_accepted(self):
        self.assert_rejected("pfam", 0, "e-value=13", "e_value=13", "is spelled 'e-value'")

    def test_repeated_key_is_rejected(self):
        self.assert_rejected("pfam", 0, "Name=Aminotran_3", "Name=Aminotran_3;Name=x", "Name repeats")

    def test_file_name_must_agree_with_rows(self):
        status, out = self.run_on(fixture("pfam").read_text(), "case_cog.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("file name says cog but rows are pfam", out)

    def test_comment_line_and_empty_file_are_rejected(self):
        status, out = self.run_on("##gff-version 3\n" + fixture("pfam").read_text(), "case_pfam.gff")
        self.assertIn("comment or directive", out)
        status, out = self.run_on("", "case_pfam.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("no rows", out)

    def test_numbers_must_be_plain_ascii(self):
        self.assert_rejected("pfam", 0, "\t12\t395\t", "\t1_2\t395\t", "start '1_2' is not a number")
        self.assert_rejected("pfam", 0, "\t12\t395\t", "\t12\t+395\t", "end '+395' is not a number")
        self.assert_rejected("pfam", 0, "\t410.5\t", "\t+410.5\t", "score '+410.5' is not a number")
        self.assert_rejected("pfam", 0, "\t410.5\t", "\t\uff14\uff11\uff10.5\t", "is not a number")
        self.assert_rejected("pfam", 0, "\t12\t395\t", "\t 12\t395\t", "start ' 12' is not a number")
        self.assert_rejected("pfam", 0, "alignment_length=384", "alignment_length=+3_84", "'+3_84' is not a integer")

    def test_score_must_be_finite(self):
        self.assert_rejected("pfam", 0, "\t410.5\t", "\tnan\t", "score 'nan' is not a number")
        self.assert_rejected("pfam", 0, "\t410.5\t", "\tinf\t", "score 'inf' is not a number")
        # Matches the ASCII pattern but overflows to inf.
        self.assert_rejected("pfam", 0, "\t410.5\t", "\t1e999\t", "score '1e999' is not a number")

    def test_row_shape_is_exact(self):
        self.assert_rejected("pfam", 0, "model_end=339", "model_end=339\textra", "10 columns, expected 9")
        self.assert_rejected("pfam", 0, "model_end=339", "model_end=339;start=1", "names a column")
        self.assert_rejected("pfam", 0, "model_end=339", "model_end=339;", "empty attribute")
        self.assert_rejected("pfam", 0, "model_end=339", "model_end=339;flag", "attribute 'flag' has no value")

    def test_blank_line_is_rejected(self):
        status, out = self.run_on(fixture("pfam").read_text() + "\n", "case_pfam.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("line 4: blank line", out)

    def test_line_ends_are_lf_with_a_final_newline(self):
        status, out = self.run_on(fixture("pfam").read_text().replace("\n", "\r\n", 1), "case_pfam.gff")
        self.assertIn("line 1: carriage return", out)
        status, out = self.run_on(fixture("pfam").read_text().replace("\n", "\r", 1), "case_pfam.gff")
        self.assertIn("line 1: carriage return", out)
        status, out = self.run_on(fixture("pfam").read_text().rstrip("\n") + "\r", "case_pfam.gff")
        self.assertIn("line 3: carriage return", out)
        status, out = self.run_on(fixture("pfam").read_text().rstrip("\n"), "case_pfam.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("line 3: no final newline", out)

    def test_e_value_patterns(self):
        self.assert_rejected("pfam", 1, "e-value=2.1e-30", "e-value=2.1e+30", "2.1e+30")
        self.assert_rejected("ko_ec", 1, "evalue=1.2e-120", "evalue=1.2E-120", "1.2E-120")
        self.assert_rejected("cog", 0, "independent_domain_e-value=1.1e-75", "independent_domain_e-value=1.1e75",
                             "1.1e75")

    def test_seqid_must_be_a_gene_id(self):
        self.assert_rejected("tigrfam", 0, "ctg_01_100_1299\t", "ctg_01_100_x\t", "/rows/0/seqid")

    def test_percent_identity_is_at_most_100(self):
        self.assert_rejected("ko_ec", 0, "percent_identity=100.00", "percent_identity=100.5", "100.5")

    def test_file_name_with_extra_underscores_is_checked(self):
        status, out = self.run_on(fixture("pfam").read_text(), "my_sample_cog.gff")
        self.assertEqual(status, 1, out)
        self.assertIn("file name says cog but rows are pfam", out)

    def test_unreadable_input_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            latin = Path(tmp) / "latin_pfam.gff"
            latin.write_bytes(b"caf\xe9\n")
            for path, expected in ((latin, "not UTF-8"), (Path(tmp) / "missing.gff", "can't read")):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(dialect.validate(path), 1)
                    self.assertEqual(dialect.main(["parse", str(path)]), 1)
                self.assertIn(expected, out.getvalue())

    def test_parse_refuses_an_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            output.write_text("keep")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(dialect.main(["parse", str(fixture("pfam")), "--output", str(output)]), 2)
            self.assertEqual(output.read_text(), "keep")
            missing = Path(tmp) / "no-such-directory" / "out.json"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(dialect.main(["parse", str(fixture("pfam")), "--output", str(missing)]), 2)
            self.assertIn("can't write", err.getvalue())
            fresh = Path(tmp) / "new.json"
            self.assertEqual(dialect.main(["parse", str(fixture("pfam")), "--output", str(fresh)]), 0)
            self.assertIn('"method": "pfam"', fresh.read_text())


if __name__ == "__main__":
    unittest.main()
