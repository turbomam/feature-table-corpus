"""The neighbors query, checked against gene rows read from the actinorhodin RefSeq excerpt."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bgc_example import EXCERPT, PROFILE, REFERENCE, SEQID, URI
from build_duckdb import build_database
from convert_features import import_source
from query_duckdb import neighbors

# Read from the gene rows of corpus/derived-examples/actinorhodin.gff3 (columns 4, 5 and 7),
# not from query output: old_locus_tag -> (start, end, strand).
GENES = {
    "SCO5086": (5528935, 5529720, "-"),
    "SCO5087": (5529801, 5531204, "+"),
    "SCO5088": (5531201, 5532424, "+"),
    "SCO5089": (5532449, 5532709, "+"),
    "SCO5090": (5532706, 5533656, "+"),
}


class NeighborQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        bundle = import_source(EXCERPT.read_bytes(), profile=PROFILE, reference_context=REFERENCE,
                               source_uri=URI, metadata_profile="ncbi")
        data, cls.db = Path(cls.tmp.name) / "dataset.json", Path(cls.tmp.name) / "features.duckdb"
        data.write_text(json.dumps(bundle["dataset"]))
        build_database(ROOT / "model/schema/ber_feature_model.yaml", data, cls.db)
        with duckdb.connect(str(cls.db), read_only=True) as con:
            cls.tags = dict(con.execute("""
                SELECT feature_id, list_filter(attributes, a -> a.key = 'old_locus_tag')[1].value
                FROM feature WHERE type = 'gene'""").fetchall())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def query(self, *args, **kwargs):
        with duckdb.connect(str(self.db), read_only=True) as con:
            return [{**row, "tag": self.tags.get(row["feature_id"])} for row in neighbors(con, *args, **kwargs)]

    def test_two_genes_each_side_of_a_position_inside_sco5088(self):
        rows = self.query(SEQID, 5531500)
        self.assertEqual([r["tag"] for r in rows], list(GENES))
        for row in rows:
            self.assertEqual((row["start"], row["end"], row["strand"]), GENES[row["tag"]])
        self.assertEqual([(r["side"], r["intervening_bases"]) for r in rows],
                         [("left", 1779), ("left", 295), ("contains", 0), ("right", 948), ("right", 1205)])

    def test_endpoints_are_inclusive_and_overlapping_genes_both_contain(self):
        # SCO5087 ends at 5,531,204 and SCO5088 starts at 5,531,201: a 4-base overlap.
        rows = self.query(SEQID, 5531204, count=0)
        self.assertEqual([(r["tag"], r["side"]) for r in rows], [("SCO5087", "contains"), ("SCO5088", "contains")])
        rows = self.query(SEQID, 5531205, count=1)
        self.assertEqual([(r["tag"], r["side"], r["intervening_bases"]) for r in rows],
                         [("SCO5087", "left", 0), ("SCO5088", "contains", 0), ("SCO5089", "right", 1243)])

    def test_type_and_sequence_select_what_is_counted(self):
        cds = self.query(SEQID, 5531500, count=1, feature_type="CDS")
        self.assertEqual([(r["start"], r["side"]) for r in cds],
                         [(5529801, "left"), (5531201, "contains"), (5532449, "right")])
        with duckdb.connect(str(self.db), read_only=True) as con:
            self.assertEqual(neighbors(con, "NC_003888.2", 5531500), [])

    def test_bad_input_and_circular_contigs_are_refused(self):
        with duckdb.connect(str(self.db), read_only=True) as con:
            for position in (0, -1, 1.5, True, "5531500", None):
                with self.assertRaises(ValueError):
                    neighbors(con, SEQID, position)
            for count in (-1, 1.0, False):
                with self.assertRaises(ValueError):
                    neighbors(con, SEQID, 5531500, count=count)
        with tempfile.TemporaryDirectory() as work:
            copy = Path(work) / "circular.duckdb"
            copy.write_bytes(self.db.read_bytes())
            with duckdb.connect(str(copy)) as con:
                con.execute("UPDATE contig SET topology = 'circular'")
                with self.assertRaisesRegex(ValueError, "circular"):
                    neighbors(con, SEQID, 5531500)


if __name__ == "__main__":
    unittest.main()
