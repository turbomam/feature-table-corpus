"""The actinorhodin comparator must refuse changed rows, order, schema metadata and corrupt files."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import actinorhodin_parquet
from actinorhodin_parquet import DATASET, PARQUET, TARGET, differences, same_parquet

FEATURES = TARGET / "parquet" / "features.parquet"


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.table = pq.read_table(FEATURES)

    def write(self, table, name="candidate.parquet"):
        path = self.work / name
        pq.write_table(table, path)
        return path

    def test_committed_file_equals_itself(self):
        self.assertTrue(same_parquet(FEATURES, FEATURES))

    def test_same_rows_rewritten_are_equal(self):
        self.assertTrue(same_parquet(self.write(self.table), FEATURES))

    def test_dropped_row_differs(self):
        self.assertFalse(same_parquet(self.write(self.table.slice(0, self.table.num_rows - 1)), FEATURES))

    def test_reordered_rows_differ(self):
        reversed_rows = self.table.take(list(range(self.table.num_rows - 1, -1, -1)))
        self.assertFalse(same_parquet(self.write(reversed_rows), FEATURES))

    def test_changed_value_differs(self):
        column = self.table.column("feature_id").to_pylist()
        column[0] = column[0] + "-changed"
        changed = self.table.set_column(self.table.schema.get_field_index("feature_id"),
                                        "feature_id", pa.array(column))
        self.assertFalse(same_parquet(self.write(changed), FEATURES))

    def test_changed_schema_metadata_differs(self):
        metadata = dict(self.table.schema.metadata or {})
        metadata[b"note"] = b"changed"
        self.assertFalse(same_parquet(self.write(self.table.replace_schema_metadata(metadata)), FEATURES))

    def test_corrupt_committed_file_differs_without_raising(self):
        corrupt = self.work / "corrupt.parquet"
        corrupt.write_bytes(FEATURES.read_bytes() + b"x")
        self.assertFalse(same_parquet(FEATURES, corrupt))

    def test_differences_names_each_changed_file(self):
        target = self.work / "target"
        shutil.copytree(TARGET, target)
        generated = self.work / "generated"
        shutil.copytree(TARGET, generated)
        with patch.object(actinorhodin_parquet, "TARGET", target):
            self.assertEqual(differences(generated), [])
            (target / DATASET).write_text((target / DATASET).read_text() + " ")
            pq.write_table(self.table.slice(1), target / PARQUET[-1])
            self.assertEqual(differences(generated), [DATASET, PARQUET[-1]])


if __name__ == "__main__":
    unittest.main()
