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
                # A subject is a slot, an rdf property; subject_label names the class it is used on.
                self.assertEqual((row["subject_type"], row["object_type"]), ("rdf property", "rdf property"))
                category, name = row["subject_label"].split(".")
                slots = {s.name: s for s in view.class_induced_slots(category)}
                self.assertIn(name, slots)
                # The CURIE must be the slot's own URI: Attribute's slots are battr:, not bfm:.
                self.assertEqual(row["subject_id"], view.get_uri(slots[name], expand=False))
                self.assertIn(row["predicate_id"], PREDICATES)
                self.assertRegex(row["object_id"], r"^img_core:[a-z_]+\.[a-z_]+$")
                # A list of objects is not one column: map its item's slots instead.
                self.assertFalse(slots[name].multivalued and slots[name].range in view.all_classes()
                                 and not any(s.identifier for s in view.class_induced_slots(slots[name].range)),
                                 "a list of structs mapped to one column")

    def test_every_hit_table_has_its_own_rows(self):
        # A comment saying "the same column in the other tables" is not a mapping; each table
        # a consumer might query needs rows of its own.
        tables = ("gene_pfam_families", "gene_cog_groups", "gene_ko_terms", "gene_superfam", "gene_smart",
                  "gene_cathfam", "gene_tigrfams", "gene_img_interpro_hits", "gene_sig_peptides")
        mapped = {(r["object_id"].split(":")[1].split(".")[0], r["subject_id"]) for r in rows()}
        for table in tables:
            with self.subTest(table):
                self.assertIn((table, "bfm:seqid"), mapped)
                self.assertIn((table, "bfm:type"), mapped)
                self.assertIn((table, "bfm:parent"), mapped)
        for table in ("gene_pfam_families", "gene_cog_groups", "gene_ko_terms", "gene_superfam", "gene_smart",
                      "gene_cathfam", "gene_tigrfams"):
            self.assertIn((table, "bfm:score"), mapped)

    def test_a_table_mapping_a_struct_maps_its_required_fields(self):
        # A consumer builds a struct (AlignmentTarget, Attribute ...) from one table's rows, so every
        # required slot of that struct needs a column in each table that maps any of its slots.
        view = SchemaView(str(ROOT / "model/schema/ber_feature_model.yaml"))
        by_table = {}
        for r in rows():
            owner = r["subject_label"].split(".")[0]
            if owner not in ("Feature", "Contig", "ContigCollection"):
                table = r["object_id"].split(":")[1].split(".")[0]
                by_table.setdefault((owner, table), set()).add(r["subject_label"].split(".")[1])
        self.assertIn(("AlignmentTarget", "gene_pfam_families"), by_table)
        for (owner, table), slots in by_table.items():
            with self.subTest(owner=owner, table=table):
                required = {s.name for s in view.class_induced_slots(owner) if s.required}
                self.assertEqual(sorted(required - slots), [])

    def test_rows_are_unique(self):
        keys = [(r["subject_label"], r["object_id"]) for r in rows()]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
