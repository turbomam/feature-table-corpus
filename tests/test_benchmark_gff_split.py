"""The GFF split benchmark runs end to end on one tiny file and reports every field; timings are not checked."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TINY = "corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3"


class BenchmarkTests(unittest.TestCase):
    def test_one_tiny_file_reports_expected_keys(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            output = Path(temp) / "report.json"
            result = subprocess.run(
                [sys.executable, "scripts/benchmark_gff_split.py", "--case", TINY, "ncbi", "--repeats", "1",
                 "--json", str(output), "--work-dir", temp],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output.read_text())
        self.assertEqual(set(report), {"machine", "repeats", "files"})
        self.assertLessEqual({"platform", "cpu", "python", "date"}, set(report["machine"]))
        (item,) = report["files"]
        self.assertLessEqual({"file", "profile", "bytes", "lines", "parse_s", "split_s", "parse_peak_mb",
                              "split_peak_mb", "rebuilt_identical", "runs"}, set(item))
        self.assertEqual(item["bytes"], (ROOT / TINY).stat().st_size)
        self.assertTrue(item["rebuilt_identical"])
        self.assertEqual([len(item["runs"]["parse"]), len(item["runs"]["split"])], [1, 1])
        self.assertIn("| file | bytes | lines | parse s | split s | peak MB | notes |", result.stdout)


if __name__ == "__main__":
    unittest.main()
