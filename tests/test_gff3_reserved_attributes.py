"""Every GFF3 reserved tag the feature model maps to is one the GFF3 spec reserves.

model/schema/gff3_reserved_attributes.yaml transcribes the spec's eleven reserved column 9 tags.
Tags start with an uppercase letter; the column names the model also maps (gff3:seqid,
gff3:start ...) start with a lowercase one, so they are not checked here.
"""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
RESERVED = ROOT / "model/schema/gff3_reserved_attributes.yaml"
SCHEMAS = [ROOT / "model/schema/ber_feature_model.yaml", ROOT / "model/schema/attributes.yaml"]
MAPPING = re.compile(r"\bgff3:([A-Z][A-Za-z_]*)")


class ReservedAttributeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tags = [entry["tag"] for entry in yaml.safe_load(RESERVED.read_text())["reserved_attributes"]]

    def test_the_file_lists_the_eleven_reserved_tags(self):
        self.assertEqual(self.tags, ["ID", "Name", "Alias", "Parent", "Target", "Gap", "Derives_from",
                                     "Note", "Dbxref", "Ontology_term", "Is_circular"])

    def test_every_uppercase_gff3_mapping_is_a_reserved_tag(self):
        found = {schema.name: set(MAPPING.findall(schema.read_text())) for schema in SCHEMAS}
        # A negative control: the feature model maps ID, Parent, Name and others, so an empty
        # result would mean the pattern stopped matching, not that every tag is right.
        self.assertIn("Parent", found["ber_feature_model.yaml"])
        for name, tags in found.items():
            with self.subTest(name):
                self.assertEqual(sorted(tags - set(self.tags)), [])

    def test_the_check_catches_a_misspelled_tag(self):
        self.assertEqual(set(MAPPING.findall("exact_mappings:\n  - gff3:DBxref\n")) - set(self.tags), {"DBxref"})


if __name__ == "__main__":
    unittest.main()
