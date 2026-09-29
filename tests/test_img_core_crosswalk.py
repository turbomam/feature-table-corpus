"""The IMG core crosswalk names only slots the model has, by their own URIs, with SSSOM predicates.

The objects, img_core_v400 columns, were checked against the bridge-schemas view on 2026-09-29;
that view isn't vendored, so this test checks the model side. docs/img-core-crosswalk.md.
"""
import csv
from pathlib import Path
import unittest

from linkml_runtime import SchemaView

ROOT = Path(__file__).resolve().parents[1]
CROSSWALK = ROOT / "model/crosswalks/img-core-v400.sssom.tsv"
PREDICATES = {"skos:exactMatch", "skos:closeMatch", "skos:relatedMatch"}


def rows():
    with open(CROSSWALK, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader((line for line in handle if not line.startswith("#")), delimiter="\t"))


class ImgCoreCrosswalkTests(unittest.TestCase):
    def test_every_subject_is_a_slot_of_its_class(self):
        view = SchemaView(str(ROOT / "model/schema/ber_feature_model.yaml"))
        found = rows()
        self.assertGreater(len(found), 30)
        for row in found:
            with self.subTest(row["subject_id"], table=row["object_id"]):
                # subject_category is the class's own CURIE, resolved to its local name.
                category = row["subject_category"].split(":", 1)[1]
                self.assertEqual(row["subject_category"], view.get_uri(view.get_class(category), expand=False))
                slots = {s.name: s for s in view.class_induced_slots(category)}
                name = row["subject_id"].split(":", 1)[1]
                self.assertIn(name, slots)
                # The CURIE must be the slot's own URI: Attribute's slots are battr:, not bfm:.
                self.assertEqual(row["subject_id"], view.get_uri(slots[name], expand=False))
                self.assertIn(row["predicate_id"], PREDICATES)
                self.assertRegex(row["object_id"], r"^img_core:[a-z_]+\.[a-z_]+$")

    def test_rows_are_unique(self):
        keys = [(r["subject_category"], r["subject_id"], r["object_id"]) for r in rows()]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
