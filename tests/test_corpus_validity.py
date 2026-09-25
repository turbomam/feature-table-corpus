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
            available = validity.binary_path().is_file() and validity.toolkit.default_binary().is_file()
        except ValueError:
            available = False
        if not available:
            raise unittest.SkipTest("Run just validity-install for real-tool tests; validity-check still requires both tools")
        (validity.ROOT / "local").mkdir(exist_ok=True)

    def test_real_files_and_retained_report(self):
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        report = validity.measure(index, validity.binary_path())
        self.assertEqual(report, json.loads(validity.REPORT.read_text()))
        fixtures = [r for r in report["records"] if r["path"].startswith("corpus/fixtures/")]
        self.assertEqual(len(fixtures), 9)
        self.assertEqual(sum(r["validators"]["genometools"]["verdict"] == "rejected" for r in fixtures), 6)
        self.assertEqual(sum(r["validators"]["genometools"]["verdict"] == "accepted" for r in fixtures), 3)
        # Biological phase and silently split Note are deliberately legal syntax.
        accepted = {r["id"] for r in fixtures if r["validators"]["genometools"]["verdict"] == "accepted"}
        self.assertIn("derived-cds-phase-biologically-wrong", accepted)
        self.assertIn("derived-unescaped-semicolon-silent", accepted)
        selected = next(r for r in report["records"] if r["id"] == "derived-actinorhodin-excerpt")
        self.assertEqual(selected["validators"]["genometools"]["verdict"], "accepted")
        self.assertEqual(selected["validators"]["genometools"]["expected_from_validity"], "accepted")
        dangling = next(r for r in fixtures if r["id"] == "derived-dangling-parent")
        self.assertEqual(dangling["validators"]["gff3toolkit"]["rules"], [])
        self.assertEqual(dangling["validators"]["genometools"]["rules"], ["unresolved-parent"])
        self.assertEqual(dangling["validators"]["agat"]["verdict"], "blocked")

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

    def test_repaired_dialect_failure_and_new_failure_both_fail(self):
        # A producer file has no fixture validity label to enforce. The profile
        # must independently catch repair of its expected missing-version rule.
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        entry = next(e for e in index["entries"] if e["id"] == "nmdc-functional-annotation")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / entry["path"]
            path.parent.mkdir(parents=True)
            path.write_bytes(b"##gff-version 3\n" + (validity.ROOT / entry["path"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "disappeared=.*missing-version"):
                validity.measure({"entries": [entry]}, validity.binary_path(), root)

            # GenomeTools stops at the missing version, but QC sees a new illegal
            # phase as well. A rejection-to-rejection change must still fail.
            original = (validity.ROOT / entry["path"]).read_text()
            fields = original.splitlines()[0].split("\t")
            self.assertEqual(fields[2], "CDS")
            fields[7] = "3"
            path.write_text("\t".join(fields) + "\n")
            with self.assertRaisesRegex(ValueError, "gff3toolkit: unexpected=.*Esf0026"):
                validity.measure({"entries": [entry]}, validity.binary_path(), root)

    def test_toolkit_disappearing_rule_is_not_a_pass(self):
        index = yaml.safe_load((validity.ROOT / "corpus/index.yaml").read_text())
        entry = next(e for e in index["entries"] if e["id"] == "nmdc-pfam")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / entry["path"]
            path.parent.mkdir(parents=True)
            rows = []
            for line in (validity.ROOT / entry["path"]).read_text().splitlines():
                fields = line.split("\t")
                fields[6] = "+"  # Remove only Esf0003; missing-version remains.
                rows.append("\t".join(fields))
            path.write_text("\n".join(rows) + "\n")
            with self.assertRaisesRegex(ValueError, "gff3toolkit: unexpected=\\[\\], disappeared=.*Esf0003"):
                validity.measure({"entries": [entry]}, validity.binary_path(), root)

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

    def test_qc_exit_zero_without_report_is_an_execution_failure(self):
        for code, stderr in [(0, ""), (1, "missing library"), (-11, "crash")]:
            with self.subTest(code=code), patch.object(validity.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], code, "", stderr)):
                with self.assertRaisesRegex(ValueError, "execution failed"):
                    validity.toolkit_verdict(Path("gff3_QC"), "example.gff3")
        with patch.object(validity.subprocess, "run", side_effect=subprocess.TimeoutExpired("gff3_QC", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                validity.toolkit_verdict(Path("gff3_QC"), "example.gff3")

    def test_qc_rules_include_warnings_and_are_independent_of_row_order(self):
        header = "Line_num\tError_code\tError_level\tError_tag\n"
        rows = ["['Line 2']\tEsf0014\tWarning\t[missing version]\n",
                "['Line 3']\tEsf0014\tError\t[missing version]\n"]
        actual = validity.parse_qc_report(header + "".join(rows))
        self.assertEqual(actual["rules"], ["Esf0014"])
        self.assertEqual(actual["verdict"], "rejected")
        self.assertEqual(actual["diagnostics"][0]["count"], 2)
        self.assertEqual(actual, validity.parse_qc_report(header + "".join(reversed(rows))))
        for malformed in ("", "Error_code\n", header + "broken\n", header + rows[0].replace("Esf0014", "garbage")):
            with self.subTest(malformed=malformed), self.assertRaisesRegex(ValueError, "execution failed"):
                validity.parse_qc_report(malformed)

    def test_qc_version_mismatch_and_unknown_gt_rejection_fail(self):
        with patch.object(validity.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "gff3_QC 9.9\n", "")):
            with self.assertRaisesRegex(ValueError, "Expected GFF3toolkit"):
                validity.check_toolkit_version(Path("gff3_QC"))
        with patch.object(validity.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "gt gff3validator: error: new rule")):
            with self.assertRaisesRegex(ValueError, "Unrecognized GenomeTools"):
                validity.verdict(Path("gt"), "example.gff3")

    def test_all_profiles_declare_expectations_and_duplicates_fail(self):
        cases = validity.load_expectations()
        self.assertEqual(cases["nmdc-pfam"]["profile"], "nmdc-pfam-protein/1.0.0")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = (validity.PROFILES / "nmdc-pfam-protein.yaml").read_text()
            (root / "one.yaml").write_text(source)
            (root / "two.yaml").write_text(source)
            with self.assertRaisesRegex(ValueError, "Duplicate validator case"):
                validity.load_expectations(root)
            (root / "two.yaml").write_text("id: undeclared\n")
            with self.assertRaisesRegex(ValueError, "Missing validator expectations"):
                validity.load_expectations(root)

    def test_regeneration_does_not_bless_rule_drift(self):
        # Both CLI modes reject independently of the saved report.
        for args in ([], ["--check"]):
            with tempfile.TemporaryDirectory() as directory:
                report = Path(directory) / "report.json"
                report.write_text("unchanged\n")
                with patch.object(validity, "REPORT", report), \
                     patch.object(validity, "measure", side_effect=ValueError("Rule mismatch: disappeared=['Esf0014']")), \
                     patch.object(sys, "argv", ["validate_corpus", *args]):
                    self.assertEqual(validity.main(), 1)
                self.assertEqual(report.read_text(), "unchanged\n")


if __name__ == "__main__":
    unittest.main()
