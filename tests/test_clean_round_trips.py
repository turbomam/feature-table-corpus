"""Every dialect has a vendored real input that round-trips byte for byte, or a gap with its issue.

model/examples/clean-round-trips.yaml lists them; https://github.com/turbomam/feature-table-corpus/issues/107.
"""
import importlib
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MANIFEST = ROOT / "model/examples/clean-round-trips.yaml"
ISSUE = "https://github.com/turbomam/feature-table-corpus/issues/"


def resolved(argument):
    return [ROOT / p for p in argument] if isinstance(argument, list) else ROOT / argument


class CleanRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = yaml.safe_load(MANIFEST.read_text())["dialects"]

    def test_every_dialect_has_an_entry(self):
        dialects = sorted(p.stem for p in (ROOT / "model/dialects").glob("*.yaml"))
        self.assertEqual(sorted(self.entries), dialects)

    def test_a_gap_names_its_issue_and_has_no_input(self):
        for name, entry in self.entries.items():
            with self.subTest(name):
                self.assertIn(entry["status"], ("clean", "gap"))
                if entry["status"] == "gap":
                    self.assertTrue(entry.get("issue", "").startswith(ISSUE), entry)
                    self.assertNotIn("inputs", entry)

    def test_every_clean_input_is_vendored_and_round_trips_byte_for_byte(self):
        for name, entry in self.entries.items():
            if entry["status"] != "clean":
                continue
            with self.subTest(name):
                arguments = [resolved(a) for a in entry["inputs"]]
                for path in (p for a in arguments for p in (a if isinstance(a, list) else [a])):
                    self.assertTrue(path.is_file(), path)
                problems, report = importlib.import_module(entry["mapping"]).roundtrip(*arguments)
                self.assertEqual(problems, [])
                # Nothing skipped: the taxon bundle is the one mapping that can skip rows.
                self.assertEqual(report.get("skipped_crispr_rows", 0), 0)


if __name__ == "__main__":
    unittest.main()
