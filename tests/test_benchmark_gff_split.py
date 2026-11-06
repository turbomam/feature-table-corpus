"""The GFF split benchmark runs end to end on one tiny file and reports every field; timings are not checked."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TINY = "corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3"
SPEC = importlib.util.spec_from_file_location("benchmark_gff_split", ROOT / "scripts/benchmark_gff_split.py")
benchmark_gff_split = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark_gff_split)


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

    def test_relative_work_dir_is_resolved_against_the_callers_directory(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/benchmark_gff_split.py"), "--case", TINY, "ncbi",
                 "--repeats", "1", "--work-dir", "relative-work"],
                cwd=temp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((Path(temp) / "relative-work" / f"{Path(TINY).name}.duckdb").exists())
        self.assertFalse((ROOT / "relative-work").exists())

    def test_line_count_matches_splitlines_across_chunk_boundaries(self):
        samples = [b"", b"a", b"a\n", b"a\nb", b"a\r\nb\r\n", b"a\rb\r", b"\r\n\r\n", b"a\r\r\nb\n\n"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample"
            for data in samples:
                path.write_bytes(data)
                for chunk_size in (1, 2, 3, 1 << 20):
                    self.assertEqual(benchmark_gff_split.file_size_and_lines(path, chunk_size),
                                     (len(data), len(data.splitlines())), (data, chunk_size))

    def test_controller_does_not_read_whole_input(self):
        run = {"seconds": 0.0, "peak_rss_mb": 1.0, "peak_rss_mb_after_imports": 1.0, "rebuilt_identical": True,
               "model_tables_written": True, "gff3_contig_refusal": None}
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.object(benchmark_gff_split, "measure", return_value=run), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("controller read the whole file")):
            report = benchmark_gff_split.benchmark([(TINY, "ncbi")], 1, Path(temp))
        (item,) = report["files"]
        data = (ROOT / TINY).read_bytes()
        self.assertEqual([item["bytes"], item["lines"]], [len(data), len(data.splitlines())])


if __name__ == "__main__":
    unittest.main()
