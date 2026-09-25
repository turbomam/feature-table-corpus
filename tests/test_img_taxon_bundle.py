"""The IMG taxon bundle dialect accepts its known shapes and rejects single-row edits."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("img_taxon_bundle", ROOT / "scripts/img_taxon_bundle.py")
dialect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect)
FIXTURES = ROOT / "tests/fixtures/img-taxon-bundle"
TAXON = "9900000001"
FIXTURE = FIXTURES / f"{TAXON}.gff"
# Real bundles, checked when present: gitignored local downloads, and the copies that
# https://github.com/turbomam/feature-table-corpus/pull/63 vendors.
REAL = [
    ROOT / "local/jgi/IMG_AP-1121004/2708743150.gff",
    ROOT / "local/jgi/IMG_AP-1377582/645058785.gff",
    ROOT / "corpus/sources/jgi-img/IMG_AP-1121004/2708743150.gff",
]


def file_name(kind):
    return f"{TAXON}.gff" if kind == "gff" else f"{TAXON}.{kind}.tab.txt"


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = dialect.parse(FIXTURE)

    def test_free_text_keeps_commas_and_trailing_space(self):
        self.assertEqual(self.document["rows"][1]["product"], "peroxiredoxin, AhpC family ")

    def test_crispr_row_has_no_end_phase_or_keys(self):
        crispr = self.document["rows"][-1]
        self.assertEqual(crispr["type"], "CRISPR")
        for absent in ("end", "phase", "ID", "score"):
            self.assertNotIn(absent, crispr)
        self.assertEqual(crispr["attribute_order"], [])

    def test_table_cells_are_typed_and_empty_cells_absent(self):
        ko = self.document["ko"]
        self.assertNotIn("EC", ko[0])
        self.assertEqual(ko[1]["EC"], "EC:3.1.26.12")
        self.assertEqual(self.document["cog"][0]["bit_score"], 118.0)
        self.assertEqual(self.document["ipr"][3]["go_info"], ["GO:0006807", "GO:0016810"])

    def test_writer_reproduces_every_fixture_file_exactly(self):
        files = dialect.write(self.document)
        self.assertEqual(len(files), 9)
        for name, text in files.items():
            self.assertEqual(text, (FIXTURES / name).read_text(), name)

    def test_writer_refuses_a_value_it_cannot_write_back(self):
        document = dialect.parse(FIXTURE)
        document["rows"][1]["product"] = "a;b=c"
        with self.assertRaisesRegex(dialect.DialectError, "parses back differently"):
            dialect.write(document)

    def test_table_columns_follow_the_schema(self):
        names = [name for name, _ in dialect.class_columns("KoHit")]
        self.assertEqual(names[-2:], ["EC", "img_ko_flag"])


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bundle = Path(self.tmp.name)
        for path in FIXTURES.glob(f"{TAXON}.*"):
            shutil.copy(path, self.bundle / path.name)

    def run_validate(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = dialect.validate(self.bundle / f"{TAXON}.gff")
        return status, out.getvalue()

    def edit(self, kind, index, old, new):
        """Replace old with new in line `index` (0 is the header) of one file."""
        path = self.bundle / file_name(kind)
        lines = path.read_text().split("\n")
        self.assertIn(old, lines[index], "the edit must change the fixture")
        lines[index] = lines[index].replace(old, new, 1)
        path.write_text("\n".join(lines))

    def line(self, kind, index):
        return (self.bundle / file_name(kind)).read_text().split("\n")[index]

    def assert_status(self, path, expected):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = dialect.validate(path)
        self.assertEqual(status, 1, out.getvalue())
        self.assertIn(expected, out.getvalue())

    def assert_rejected(self, expected, *edits):
        for edit in edits:
            self.edit(*edit)
        status, out = self.run_validate()
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)

    def test_fixture_is_valid(self):
        status, out = self.run_validate()
        self.assertEqual(status, 0, out)

    def test_real_bundles_are_valid_when_present(self):
        present = [path for path in REAL if path.exists()]
        if not present:
            self.skipTest("no real IMG taxon bundle under local/jgi/ or corpus/sources/jgi-img/")
        for path in present:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = dialect.validate(path)
            self.assertEqual(status, 0, out.getvalue())

    def test_gff_alone_is_valid(self):
        for path in self.bundle.glob("*.tab.txt"):
            path.unlink()
        status, out = self.run_validate()
        self.assertEqual(status, 0, out)
        self.assertIn("no tables", out)

    # GFF file shape.
    def test_header_is_required(self):
        self.assert_rejected("is not '##gff-version 3'", ("gff", 0, "##gff-version 3", "##gff-version 2"))

    def test_comment_after_header_is_rejected(self):
        self.assert_rejected("comment or directive", ("gff", 1, "ctg_01", "#ctg_01"))

    def test_carriage_return_is_rejected(self):
        self.assert_rejected("carriage return", ("cog", 1, "\t157", "\t157\r"))

    # GFF columns.
    def test_numeric_score_is_rejected(self):
        self.assert_rejected("'score' was unexpected", ("gff", 2, "\t.\t+\t0\t", "\t5.1\t+\t0\t"))

    def test_other_database_version_is_rejected(self):
        self.assert_rejected("img_core_v400", ("gff", 2, "img_core_v400", "img_core_v500"))

    def test_pipeline_type_and_strand_spellings_are_rejected(self):
        # 106476.assembled.gff writes misc_RNA and strand 1; see the dialect schema's comments.
        self.assert_rejected("misc_RNA", ("gff", 5, "\tRNA\t", "\tmisc_RNA\t"))
        self.setUp()
        self.assert_rejected("'1' is not one of", ("gff", 5, "\t+\t0\t", "\t1\t0\t"))

    def test_phase_follows_type(self):
        self.assert_rejected("phase missing on CDS", ("gff", 2, "\t+\t0\t", "\t+\t.\t"))
        self.setUp()
        self.assert_rejected("phase present on CRISPR", ("gff", 7, "\t+\t.\t", "\t+\t0\t"))

    def test_end_is_missing_only_on_crispr(self):
        self.assert_rejected("end present on CRISPR", ("gff", 7, "\t5000\t\t", "\t5000\t5100\t"))
        self.setUp()
        self.assert_rejected("end missing on CDS", ("gff", 2, "\t300\t950\t", "\t300\t\t"))

    def test_start_after_end_is_rejected(self):
        self.assert_rejected("start > end", ("gff", 2, "\t300\t950\t", "\t951\t950\t"))

    def test_nonnumeric_coordinate_is_reported(self):
        self.assert_rejected("start 'x300' is not a number", ("gff", 2, "\t300\t", "\tx300\t"))

    # Column 9.
    def test_product_only_on_cds_and_rrna(self):
        self.assert_rejected("tRNA keys", ("gff", 4, "TEST_R0001", "TEST_R0001;product=tRNA-Gly"))
        self.setUp()
        self.assert_rejected("CDS keys", ("gff", 3, ";product=ribonuclease E", ""))

    def test_key_order_is_fixed(self):
        self.assert_rejected("CDS keys", ("gff", 3, "ID=9900000003;locus_tag=TEST_0003",
                                          "locus_tag=TEST_0003;ID=9900000003"))

    def test_unknown_and_repeated_keys_are_rejected(self):
        self.assert_rejected("Name", ("gff", 1, "product=23S", "product=23S;Name=23S rRNA"))
        self.setUp()
        self.assert_rejected("product repeats", ("gff", 1, "product=23S", "product=23S;product=5S"))
        self.setUp()
        self.assert_rejected("names a column", ("gff", 1, "product=23S", "product=23S;start=1"))

    def test_ids_and_locus_tags_are_unique_and_numeric(self):
        self.assert_rejected("ID '9900000002' repeats", ("gff", 3, "ID=9900000003", "ID=9900000002"))
        self.setUp()
        self.assert_rejected("locus_tag 'TEST_0002' repeats", ("gff", 3, "TEST_0003", "TEST_0002"))
        self.setUp()
        self.assert_rejected("does not match", ("gff", 5, "ID=9900000005", "ID=Ga0139071_101.5"))

    def test_row_needs_nine_columns(self):
        self.assert_rejected("8 columns, expected 9", ("gff", 4, "\t.\t-\t0\t", "\t.\t-0\t"))
        self.setUp()
        self.assert_rejected("10 columns, expected 9", ("gff", 4, "\t.\t-\t0\t", "\t.\t-\t0\t.\t"))

    def test_blank_lines_and_empty_files_are_rejected(self):
        self.assert_rejected("gff line 5: blank line", ("gff", 4, self.line("gff", 4), ""))
        self.setUp()
        self.assert_rejected("cog line 2: blank line", ("cog", 1, self.line("cog", 1), ""))
        self.setUp()
        (self.bundle / file_name("gff")).write_text("")
        self.assert_rejected("gff: empty file")

    def test_final_newline_is_required(self):
        path = self.bundle / file_name("xref")
        path.write_text(path.read_text().rstrip("\n"))
        self.assert_rejected("xref line 5: no final newline")

    def test_header_only_files_are_rejected(self):
        path = self.bundle / file_name("xref")
        path.write_text(path.read_text().split("\n")[0] + "\n")
        self.assert_rejected("xref: header only")
        self.setUp()
        (self.bundle / file_name("gff")).write_text("##gff-version 3\n")
        self.assert_rejected("gff: header only")

    def test_empty_attribute_and_missing_value_are_rejected(self):
        self.assert_rejected("empty attribute", ("gff", 1, ";product=23S", ";;product=23S"))
        self.setUp()
        self.assert_rejected("attribute 'product' has no value", ("gff", 1, "product=23S", "product"))

    # Numbers: ASCII digits, no leading zeros, no trailing fractional zeros.
    def test_leading_zeros_are_rejected(self):
        self.assert_rejected("start '0300' is not a number", ("gff", 2, "\t300\t", "\t0300\t"))
        self.setUp()
        self.assert_rejected("phase '00' is not a number", ("gff", 2, "\t+\t0\t", "\t+\t00\t"))
        self.setUp()
        self.assert_rejected("'0157' is not an integer", ("cog", 1, "\t157", "\t0157"))
        self.setUp()
        self.assert_rejected("does not match '^[1-9][0-9]*$'", ("xref", 1, "9900000002\tGI", "09900000002\tGI"))

    def test_trailing_fractional_zero_is_rejected(self):
        self.assert_rejected("'118.0' is not a decimal number", ("cog", 1, "\t118\t", "\t118.0\t"))
        self.setUp()
        self.assert_rejected("'110.10' is not a decimal number", ("pfam", 1, "\t110.1\t", "\t110.10\t"))

    def test_decimals_a_float_cannot_write_back_are_rejected(self):
        self.assert_rejected("'31.123456789012345678' is not a decimal number",
                             ("cog", 1, "\t31.98\t", "\t31.123456789012345678\t"))
        self.setUp()
        self.assert_rejected("'0.0000001' is not a decimal number", ("cog", 1, "\t31.98\t", "\t0.0000001\t"))

    def test_superscript_gene_oid_is_reported_not_raised(self):
        self.assert_rejected("'\u00b2' does not match", ("pfam", 2, "9900000006\t386\t20", "\u00b2\t386\t20"))

    def test_non_ascii_digits_are_rejected(self):
        # The first digit is ASCII, so a pattern that only checks it still fails here.
        arabic_indic = "3\u0660\u0660"
        full_width = "11\uff18"
        self.assert_rejected(f"start {arabic_indic!r} is not a number", ("gff", 2, "\t300\t", f"\t{arabic_indic}\t"))
        self.setUp()
        self.assert_rejected(f"{full_width!r} is not a decimal number", ("cog", 1, "\t118\t", f"\t{full_width}\t"))
        self.setUp()
        # The schema's patterns must not accept them either.
        self.assert_rejected("does not match '^[1-9][0-9]*$'",
                             ("gff", 5, "ID=9900000005", "ID=\uff19900000005"))
        self.setUp()
        self.assert_rejected("does not match '^COG[0-9]{4}$'", ("cog", 1, "COG1225", "COG\u0661225"))
        self.setUp()
        self.assert_rejected("does not match '^GO:[0-9]{7}$'", ("ipr", 2, "GO:0015035", "GO:001503\u0665"))
        self.setUp()
        self.assert_rejected("GI id '24176083\u0666'", ("xref", 1, "241760836", "24176083\u0666"))

    # Files that can't be read, and files beside the GFF.
    def test_unreadable_inputs_are_invalid_not_tracebacks(self):
        (self.bundle / file_name("xref")).write_bytes(b"gene_oid\tdb_name\tid\n9900000002\tGI\t\xe9\n")
        self.assert_rejected("not UTF-8")
        missing = self.bundle / "missing" / f"{TAXON}.gff"
        self.assert_status(missing, "No such file")
        directory = self.bundle / "d.gff"
        directory.mkdir()
        self.assert_status(directory, "Is a directory")
        self.assert_status(self.bundle / f"{TAXON}.gff3", "expected <taxon_oid>.gff")

    def test_unread_files_beside_the_gff_are_rejected(self):
        (self.bundle / f"{TAXON}.crispr.txt").write_text("contig_id\n")
        self.assert_rejected("9900000001.crispr.txt: documented in the bundle README but not yet measured")
        self.setUp()
        (self.bundle / f"{TAXON}.pfam.tab.txt.bak").write_text("x\n")
        self.assert_rejected("9900000001.pfam.tab.txt.bak: not a file this dialect reads")

    def test_sequence_files_are_allowed(self):
        for suffix in ("fna", "genes.fna", "genes.faa", "intergenic.fna", "tar.gz"):
            (self.bundle / f"{TAXON}.{suffix}").write_text(">x\nACGT\n")
        status, out = self.run_validate()
        self.assertEqual(status, 0, out)

    # Table shape and types.
    def test_table_header_must_match(self):
        self.assert_rejected("header is not", ("pfam", 0, "pfam_name", "pfam_desc"))

    def test_table_column_count_must_match(self):
        self.assert_rejected("12 columns, expected 11", ("pfam", 1, "\t124", "\t124\textra"))

    def test_table_numbers_are_strict(self):
        self.assert_rejected("'4a' is not an integer", ("cog", 1, "\t4\t155\t", "\t4a\t155\t"))
        self.setUp()
        self.assert_rejected("'nan' is not a decimal number", ("cog", 1, "\t31.98\t", "\tnan\t"))

    def test_evalue_spelling(self):
        self.assert_rejected("does not match", ("cog", 1, "3.0e-28", "3e-28"))

    def test_accession_patterns(self):
        self.assert_rejected("PF00578", ("pfam", 1, "pfam00578", "PF00578"))

    def test_unknown_table_kinds_are_rejected(self):
        (self.bundle / f"{TAXON}.kog.tab.txt").write_text("gene_oid\n")
        status, out = self.run_validate()
        self.assertEqual(status, 1, out)
        self.assertIn("documented in the bundle README but not yet measured", out)
        (self.bundle / f"{TAXON}.kog.tab.txt").rename(self.bundle / f"{TAXON}.smart.tab.txt")
        status, out = self.run_validate()
        self.assertIn("9900000001.smart.tab.txt: not a file this dialect reads", out)

    def test_superfamily_accession_has_five_or_six_digits(self):
        self.assert_rejected("SUPERFAMILY accession 'SSF1000000'", ("ipr", 5, "SSF100000", "SSF1000000"))
        self.setUp()
        self.assert_rejected("SUPERFAMILY accession 'SSF5283'", ("ipr", 1, "SSF52833", "SSF5283"))

    # Rules across tables.
    def test_gene_oid_must_be_a_cds(self):
        self.assert_rejected("is not a CDS ID in the GFF", ("signalp", 1, "9900000003", "9900000004"))

    def test_rows_are_sorted_by_gene_oid(self):
        self.assert_rejected("comes after", ("pfam", 3, "9900000006\t386\t120\t300", "9900000002\t216\t120\t200"))

    def test_gene_length_agrees_across_tables(self):
        self.assert_rejected("gene_length 217 differs from 216", ("pfam", 1, "\t216\t", "\t217\t"))

    def test_alignment_bounds(self):
        self.assert_rejected("query_start > query_end", ("tigrfam", 1, "\t13\t368\t", "\t369\t368\t"))
        self.setUp()
        self.assert_rejected("query_end > gene_length", ("tigrfam", 1, "\t13\t368\t", "\t13\t387\t"))
        self.setUp()
        self.assert_rejected("subj_end > cog_length", ("cog", 1, "\t155\t", "\t158\t"))

    def test_accession_has_one_name(self):
        self.assert_rejected("pfam02222 is named 'ATP-grasp_3' here", ("pfam", 3, "ATP-grasp", "ATP-grasp_3"))

    def test_signalp_site_is_two_residues_once_per_gene(self):
        self.assert_rejected("spans two adjacent residues", ("signalp", 1, "\t21\t22", "\t21\t23"))
        self.setUp()
        path = self.bundle / file_name("signalp")
        path.write_text(path.read_text() + "9900000003\t183\tcleavage\t30\t31\n")
        status, out = self.run_validate()
        self.assertIn("second cleavage site", out)

    def test_tmhmm_segments_tile_and_alternate(self):
        self.assert_rejected("segment starts at 29, not 28", ("tmhmm", 4, "\t28\t183", "\t29\t183"))
        self.setUp()
        self.assert_rejected("TMhelix follows TMhelix", ("tmhmm", 4, "inside", "TMhelix"))
        self.setUp()
        self.assert_rejected("not gene_length 216", ("tmhmm", 1, "\t1\t216", "\t1\t215"))

    def test_ko_rows_carry_the_ec_numbers_in_the_name(self):
        self.assert_rejected("but its name lists", ("ko", 3, "EC:3.1.-\t", "EC:3.1.-.-\t"))
        self.setUp()
        self.assert_rejected("but its name lists", ("ko", 1, "transposase\t\t", "transposase\tEC:2.7.7.-\t"))

    def test_ko_ec_rows_are_counted_not_just_collected(self):
        path = self.bundle / file_name("ko")
        rows = path.read_text().split("\n")
        path.write_text("\n".join(rows[:4] + [rows[4]] + rows[4:]))
        self.assert_rejected("KO:K01589 has EC rows ['EC:6.3.4.18', 'EC:6.3.4.18']")

    def test_img_ko_flag_value_is_not_yet_accepted(self):
        self.assert_rejected("'Yes' does not match", ("ko", 1, "transposase\t\t", "transposase\t\tYes"))

    def test_interpro_entry_rules(self):
        self.assert_rejected("iprid and iprdesc", ("ipr", 1, "\tThioredoxin-like superfamily\t", "\t\t"))
        self.setUp()
        self.assert_rejected("GO terms without an InterPro entry", ("ipr", 3, "SM00382\t\t\t", "SM00382\t\t\tGO:0005524"))
        self.setUp()
        self.assert_rejected("SMART accession 'SSF52833'", ("ipr", 3, "SM00382", "SSF52833"))
        self.setUp()
        self.assert_rejected("IPR003010 has a different description", ("ipr", 5, "GO:0006807|", ""))

    def test_xref_identifiers(self):
        self.assert_rejected("GI id 'ZP_04758925'", ("xref", 1, "241760836", "ZP_04758925"))
        self.setUp()
        self.assert_rejected("'RefSeq' is not one of", ("xref", 2, "GenBank/EMBL", "RefSeq"))
        self.setUp()
        self.assert_rejected("GenBank/EMBL id 'ZP04758925'", ("xref", 2, "ZP_04758925", "ZP04758925"))


class ParseOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_parse(self, output):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            status = dialect.main(["parse", str(FIXTURE), "--output", str(output)])
        return status, err.getvalue()

    def test_new_output_is_written(self):
        output = self.dir / "bundle.json"
        self.assertEqual(self.run_parse(output), (0, ""))
        self.assertIn('"taxon_oid": "9900000001"', output.read_text())

    def test_existing_output_is_refused(self):
        output = self.dir / "bundle.json"
        output.write_text("keep")
        status, err = self.run_parse(output)
        self.assertEqual(status, 1)
        self.assertIn("not written", err)
        self.assertEqual(output.read_text(), "keep")

    def test_directory_output_is_refused(self):
        status, err = self.run_parse(self.dir)
        self.assertEqual(status, 1)
        self.assertIn("not written", err)


if __name__ == "__main__":
    unittest.main()
