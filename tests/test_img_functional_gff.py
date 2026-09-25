"""The IMG functional annotation dialect accepts its known shapes and rejects edits."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("img_functional_gff", ROOT / "scripts/img_functional_gff.py")
dialect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dialect)
FIXTURE = ROOT / "tests/fixtures/img-functional-gff/constructed.gff"
NMDC = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-hrn8ep39.1_functional_annotation.gff"


def lines():
    return FIXTURE.read_text().splitlines()


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = dialect.parse(FIXTURE)["rows"]

    def test_commas_split_lists_but_not_free_text(self):
        first, _, third = self.rows[:3]
        self.assertEqual(first["product"], "glutamate-1-semialdehyde 2,1-aminomutase")
        self.assertEqual(first["cath_funfam"], ["3.40.640.10", "3.90.1150.10"])
        self.assertEqual(third["ko"], ["KO:K01990", "KO:K01992"])
        self.assertEqual(third["product_source"], "COG1131/COG4152")

    def test_repeated_key_and_order_are_kept(self):
        second = self.rows[1]
        self.assertEqual(second["shortened"], ["original end 2500", "original end 1750"])
        self.assertEqual(second["attribute_order"][:3], ["ID", "translation_table", "shortened"])
        self.assertEqual(second["attribute_order"].count("shortened"), 2)

    def test_missing_score_and_phase_are_absent_not_dot(self):
        crispr = self.rows[7]
        self.assertNotIn("score", crispr)
        self.assertNotIn("phase", crispr)
        self.assertEqual(crispr["strand"], ".")

    def test_hyphenated_key_maps_to_slot(self):
        self.assertEqual(self.rows[5]["e_value"], "0")
        self.assertIn("e-value", self.rows[5]["attribute_order"])


class ValidateTests(unittest.TestCase):
    def run_on(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.gff"
            path.write_text(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = dialect.validate(path)
            return status, out.getvalue()

    def edited(self, index, old, new):
        rows = lines()
        self.assertIn(old, rows[index], "the edit must change the fixture")
        rows[index] = rows[index].replace(old, new, 1)
        return "\n".join(rows) + "\n"

    def assert_rejected(self, text, expected):
        status, out = self.run_on(text)
        self.assertEqual(status, 1, out)
        self.assertIn(expected, out)

    def test_fixture_and_vendored_nmdc_file_are_valid(self):
        for path in (FIXTURE, NMDC):
            status, out = self.run_on(path.read_text())
            self.assertEqual(status, 0, out)

    def test_unknown_key_is_rejected(self):
        self.assert_rejected(self.edited(0, "cog=COG0001", "cog=COG0001;made_up=1"), "made_up")

    def test_malformed_accessions_are_rejected(self):
        self.assert_rejected(self.edited(0, "pfam=PF00202", "pfam=PF202"), "PF202")
        self.assert_rejected(self.edited(0, "ec_number=EC:5.4.3.8", "ec_number=5.4.3.8"), "5.4.3.8")

    def test_packed_ko_pair_is_rejected(self):
        # Older NMDC runs pack two KOs with one underscore (nmdc-lakehouse docs/nmdc_feature_tables.md).
        self.assert_rejected(
            self.edited(2, "ko=KO:K01990,KO:K01992", "ko=KO:K01990_KO:K01992"), "KO:K01990_KO:K01992")

    def test_phase_on_trna_is_rejected(self):
        self.assert_rejected(self.edited(3, "+\t.\tID=ctg_01_2300_2375", "+\t0\tID=ctg_01_2300_2375"),
                             "phase present on tRNA")

    def test_unstranded_cds_is_rejected(self):
        self.assert_rejected(self.edited(0, "154.2\t+\t0", "154.2\t.\t0"), "CDS is unstranded")

    def test_id_must_match_columns(self):
        self.assert_rejected(self.edited(0, "ID=ctg_01_100_1299", "ID=ctg_01_100_1300"), "is not 'ctg_01_100_1299'")

    def test_repeat_unit_ids_follow_their_crispr_in_order(self):
        self.assert_rejected(self.edited(9, "_DR2;", "_DR3;"), "is not 'ctg_02_500_620_DR2'")
        self.assert_rejected(self.edited(9, "Parent=ctg_02_500_620", "Parent=ctg_02_1_2"), "is not a CRISPR row")

    def test_single_valued_key_may_not_repeat(self):
        self.assert_rejected(self.edited(0, "product=", "product=x;product="), "repeats but is single-valued")

    def test_nonnumeric_columns_and_values_are_reported_not_raised(self):
        self.assert_rejected(self.edited(0, "\t100\t1299\t", "\tabc\t1299\t"), "start 'abc' is not a number")
        self.assert_rejected(self.edited(0, "\t154.2\t", "\thigh\t"), "score 'high' is not a number")
        self.assert_rejected(self.edited(0, "translation_table=11", "translation_table=x"),
                             "translation_table 'x' is not a integer")

    def test_only_the_source_spelling_of_e_value_is_accepted(self):
        self.assert_rejected(self.edited(5, "e-value=0", "e_value=0"), "is spelled 'e-value'")
        self.assert_rejected(self.edited(0, "cog=COG0001", "cog=COG0001;model-start=1"), "model-start")

    def test_attribute_named_like_a_column_is_rejected(self):
        self.assert_rejected(self.edited(0, "cog=COG0001", "cog=COG0001;start=999"), "names a column")

    def test_comment_line_is_rejected(self):
        self.assert_rejected("##gff-version 3\n" + FIXTURE.read_text(), "comment or directive")


if __name__ == "__main__":
    unittest.main()
