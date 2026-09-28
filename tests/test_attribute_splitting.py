"""One rule for multivalued attributes, checked against every converter that splits them.

Each value of a multivalued attribute is its own Attribute entry, in source order.
Splitting happens before percent-decoding, so an encoded %2C stays inside one value.
Which keys are multivalued belongs to the source profile: gff3-contig treats every
key as a comma list, as GFF3 requires; a dialect whose writers don't percent-encode
declares its multivalued keys and keeps every other value whole, literal commas
included. See docs/attributes.md and
https://github.com/turbomam/feature-table-corpus/issues/39.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from convert_features import ConversionError, export_source, import_source  # noqa: E402
import phytozome_gene_exons as phytozome  # noqa: E402

SPEC = importlib.util.spec_from_file_location("img_functional_map", ROOT / "scripts/img_functional_map.py")
img_map = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(img_map)
SPEC = importlib.util.spec_from_file_location("img_per_method_gff", ROOT / "scripts/img_per_method_gff.py")
per_method = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(per_method)

FIXTURES = ROOT / "tests/fixtures/attribute-splitting"
GFF3 = FIXTURES / "gff3-contig.gff3"
IMG = FIXTURES / "img-functional.gff"
LITERAL_COMMA = "glutamate-1-semialdehyde 2,1-aminomutase"


def values(feature, key):
    return [a["value"] for a in feature["attributes"] if a["key"] == key]


def gff3_bundle(content):
    return import_source(content, profile="gff3-contig/3.0.0", reference_context="test:reference",
                         source_uri="https://example.org/attribute-splitting")


class Gff3ContigTests(unittest.TestCase):
    """convert_features.py: every key is a comma list, split before decoding."""

    @classmethod
    def setUpClass(cls):
        cls.content = GFF3.read_bytes()
        cls.bundle = gff3_bundle(cls.content)
        cls.feature = next(f for f in cls.bundle["dataset"]["features"] if f["feature_id"] == "m")

    def test_each_comma_separated_value_is_its_own_attribute(self):
        self.assertEqual(values(self.feature, "Parent"), ["a", "b"])
        self.assertEqual(self.feature["parent"], ["a", "b"])
        self.assertEqual(values(self.feature, "Dbxref"), ["A:1", "B:2"])

    def test_an_encoded_comma_stays_inside_one_value(self):
        self.assertEqual(values(self.feature, "Note"), ["x,y"])
        self.assertEqual(values(self.feature, "product"), [LITERAL_COMMA])
        self.assertEqual(self.feature["product"], LITERAL_COMMA)

    def test_attributes_keep_source_order(self):
        self.assertEqual([a["key"] for a in self.feature["attributes"]],
                         ["ID", "Parent", "Parent", "Dbxref", "Dbxref", "Note", "product"])

    def test_a_literal_comma_in_product_is_two_values_and_refused(self):
        content = self.content.replace(b"2%2C1-aminomutase", b"2,1-aminomutase")
        with self.assertRaises(ConversionError) as raised:
            gff3_bundle(content)
        self.assertEqual(raised.exception.code, "product-cardinality")

    def test_round_trips_keep_the_grouping(self):
        self.assertEqual(export_source(self.bundle, mode="exact", original_bytes=self.content), self.content)
        again = gff3_bundle(export_source(self.bundle, mode="reconstruct"))
        self.assertEqual(again["dataset"], self.bundle["dataset"])
        self.assertEqual(again["mappings"], self.bundle["mappings"])


class ImgFunctionalTests(unittest.TestCase):
    """img_functional_gff.py plus img_functional_map.py: declared keys split, others whole."""

    @classmethod
    def setUpClass(cls):
        cls.document = img_map.dialect.parse(IMG)
        cls.dataset = img_map.forward(cls.document)
        cls.cds, cls.trna = cls.dataset["features"]

    def test_declared_multivalued_keys_give_one_attribute_per_value(self):
        self.assertEqual(values(self.cds, "pfam"), ["PF00005", "PF13732"])
        self.assertEqual(values(self.cds, "ko"), ["KO:K01990", "KO:K01992"])
        self.assertEqual(values(self.cds, "cog"), ["COG1131", "COG4152"])

    def test_free_text_keeps_its_literal_comma(self):
        self.assertEqual(values(self.cds, "product"), [LITERAL_COMMA])
        self.assertEqual(self.cds["product"], LITERAL_COMMA)

    def test_no_percent_decoding_since_the_writer_encodes_nothing(self):
        # IMG writes no escapes, so %2C in its output is three literal characters.
        self.assertEqual(values(self.trna, "note"), ["x%2Cy"])

    def test_attributes_keep_source_order(self):
        self.assertEqual([a["key"] for a in self.cds["attributes"]],
                         ["ID", "translation_table", "start_type", "product", "product_source",
                          "cog", "cog", "ko", "ko", "pfam", "pfam"])

    def test_round_trip_reproduces_the_rows_and_text(self):
        problems, report = img_map.roundtrip(IMG)
        self.assertEqual(problems, [])
        self.assertEqual((report["rows"], report["attributes"]), (2, 16))
        self.assertEqual(report["lines_differing_only_in_number_spelling"], 0)


class OtherDialectTests(unittest.TestCase):
    """Dialects with no mapping to Feature yet, checked at the row level."""

    def test_img_per_method_splits_its_declared_list(self):
        document = per_method.parse(ROOT / "tests/fixtures/img-per-method-gff/constructed_ko_ec.gff")
        self.assertEqual(document["rows"][0]["subject_gene_ids"], ["637175796", "650950158"])

    def test_phytozome_refuses_a_comma_or_escape_rather_than_guess(self):
        text = (ROOT / "tests/fixtures/phytozome/constructed.gene_exons.gff3").read_text()
        header, mrna_row = text.splitlines()[:2], text.splitlines()[3]
        slots = phytozome.row_slots()
        for edit, meaning in (("Parent=Exa01g00010.EXv1,b", "a second value"),
                              ("Parent=Exa01g00010.EXv1%2Cb", "a percent escape")):
            row = mrna_row.replace("Parent=Exa01g00010.EXv1", edit)
            self.assertNotEqual(row, mrna_row)
            with self.assertRaisesRegex(phytozome.DialectError, meaning):
                phytozome.parse_lines([line + "\n" for line in (*header, row)], "edited", slots)


if __name__ == "__main__":
    unittest.main()
