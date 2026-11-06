"""The counts stated in corpus/README.md must agree with corpus/index.yaml, and each kind of
drift is reported."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class ReadmeCountTests(unittest.TestCase):
    def setUp(self):
        self.doc = yaml.safe_load((ROOT / "corpus/index.yaml").read_text())
        self.text = (ROOT / verify.CORPUS_README).read_text()

    def check(self, text):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bad = verify.check_counts(self.doc, text)
        return bad, out.getvalue()

    def test_the_corpus_readme_passes(self):
        self.assertEqual(verify.CORPUS_README, "corpus/README.md")
        bad, out = self.check(self.text)
        self.assertEqual(bad, 0, out)

    def test_check_readme_reads_the_corpus_readme(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(verify.check_readme(self.doc), 0)

    def test_a_wrong_total_is_reported(self):
        bad, out = self.check(self.text.replace(f"{len(self.doc['entries'])} entries in ", "999 entries in "))
        self.assertGreater(bad, 0)
        self.assertIn("README-COUNT    total", out)

    def test_a_wrong_tier_row_is_reported(self):
        bad, out = self.check(self.text.replace("| vendored | ", "| vendored | 9999 | was "))
        self.assertGreater(bad, 0)
        self.assertIn("README-COUNT    tier vendored", out)

    def test_a_missing_specification_count_is_reported(self):
        bad, out = self.check(self.text.replace("specifications are recorded", "specifications"))
        self.assertGreater(bad, 0)
        self.assertIn("specification count", out)

    def test_a_wrong_specification_count_is_reported(self):
        stated = next(w for w in ("nine", "ten", "eleven", "twelve", "thirteen", "fourteen")
                      if f"{w.capitalize()} specifications are recorded" in self.text)
        other = "nine" if stated != "nine" else "ten"
        bad, out = self.check(self.text.replace(f"{stated.capitalize()} specifications", f"{other.capitalize()} specifications"))
        self.assertGreater(bad, 0)
        self.assertIn("README-COUNT    specifications", out)


if __name__ == "__main__":
    unittest.main()
