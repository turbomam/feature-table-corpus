"""Independent validator results, label disagreement, and execution failures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import validate_corpus as validity


class CorpusValidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            available = validity.binary_path().is_file()
        except ValueError:
            available = False
        if not available:
            raise unittest.SkipTest("Install GenomeTools with just validity-install for real-tool tests; validity-check still requires it")
        (validity.ROOT / "local").mkdir(exist_ok=True)

    def test_real_files_and_retained_report(self):
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        report = validity.measure(index, validity.binary_path())
        self.assertEqual(report, json.loads(validity.REPORT.read_text()))
        fixtures = [r for r in report["records"] if r["path"].startswith("corpus/fixtures/")]
        self.assertEqual(len(fixtures), 9)
        self.assertEqual(sum(r["verdict"] == "rejected" for r in fixtures), 6)
        self.assertEqual(sum(r["verdict"] == "accepted" for r in fixtures), 3)
        # Biological phase and silently split Note are deliberately legal syntax.
        accepted = {r["id"] for r in fixtures if r["verdict"] == "accepted"}
        self.assertIn("derived-cds-phase-biologically-wrong", accepted)
        self.assertIn("derived-unescaped-semicolon-silent", accepted)
        selected = next(r for r in report["records"] if r["id"] == "derived-actinorhodin-excerpt")
        self.assertEqual(selected["verdict"], "accepted")
        self.assertEqual(selected["expected_from_validity"], "accepted")

    def test_flipped_label_is_rejected(self):
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        entry = copy.deepcopy(next(e for e in index["entries"] if e["id"] == "derived-cds-phase-illegal"))
        entry["validity"] = "VALID GFF3: deliberately false test label"
        with self.assertRaisesRegex(ValueError, "Validity mismatch"):
            validity.measure({"entries": [entry]}, validity.binary_path())

    def test_changed_fixture_and_changed_report_fail(self):
        # Repair a real invalid fixture but leave its invalid label unchanged.
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        entry = next(e for e in index["entries"] if e["id"] == "derived-no-version-pragma")
        with tempfile.TemporaryDirectory(dir=validity.ROOT / "local") as directory:
            root = Path(directory)
            path = root / entry["path"]
            path.parent.mkdir(parents=True)
            path.write_bytes(b"##gff-version 3\n" + (validity.ROOT / entry["path"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "Validity mismatch"):
                validity.measure({"entries": [entry]}, validity.binary_path(), root)
            bad_report = root / "report.json"
            bad_report.write_text("{}\n")
            with patch.object(validity, "REPORT", bad_report), patch.object(sys, "argv", ["validate_corpus", "--check"]):
                self.assertEqual(validity.main(), 1)

class ValidatorExecutionTests(unittest.TestCase):
    def test_tool_failures_are_not_invalid_verdicts(self):
        for code, stdout, stderr in [(1, "", "missing library"), (-11, "", "crash"), (0, "", "")]:
            with self.subTest(code=code, stderr=stderr), patch.object(validity.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], code, stdout, stderr)):
                with self.assertRaisesRegex(ValueError, "execution failed"):
                    validity.verdict(Path("gt"), "example.gff3")
        with patch.object(validity.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "gt (GenomeTools) 9.9\n", "")):
            with self.assertRaisesRegex(ValueError, "Expected GenomeTools"):
                validity.check_version(Path("gt"))


if __name__ == "__main__":
    unittest.main()
