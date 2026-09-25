"""Offline checks for the JGI login-only input manifest and its verifier."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("jgi_inputs", ROOT / "scripts/jgi_inputs.py")
jgi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jgi)


def manifest_for(content):
    return {"records": [{"record_id": "IMG_AP-1", "files": [
        {"name": "a.gff", "file_id": "f1", "bytes": len(content),
         "md5": hashlib.md5(content).hexdigest()}]}]}


class VerifyTests(unittest.TestCase):
    def run_verify(self, manifest, write=None):
        with tempfile.TemporaryDirectory() as tmp:
            if write is not None:
                target = Path(tmp) / "IMG_AP-1" / "a.gff"
                target.parent.mkdir()
                target.write_bytes(write)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = jgi.verify(manifest, tmp)
            return status, out.getvalue()

    def test_matching_file_passes(self):
        status, out = self.run_verify(manifest_for(b"x\n"), b"x\n")
        self.assertEqual(status, 0)
        self.assertIn("OK      IMG_AP-1/a.gff", out)

    def test_missing_file_is_reported_but_passes(self):
        status, out = self.run_verify(manifest_for(b"x\n"))
        self.assertEqual(status, 0)
        self.assertIn("MISSING IMG_AP-1/a.gff", out)

    def test_wrong_size_fails(self):
        status, out = self.run_verify(manifest_for(b"x\n"), b"xy\n")
        self.assertEqual(status, 1)
        self.assertIn("SIZE", out)

    def test_same_size_wrong_content_fails(self):
        status, out = self.run_verify(manifest_for(b"x\n"), b"y\n")
        self.assertEqual(status, 1)
        self.assertIn("MD5", out)


class ManifestTests(unittest.TestCase):
    def test_retained_manifest_has_one_entry_per_local_path(self):
        manifest = jgi.load()
        for record in manifest["records"]:
            names = [f["name"] for f in record["files"]]
            self.assertEqual(len(names), len(set(names)), record["record_id"])
            for f in record["files"]:
                self.assertRegex(f["md5"], r"^[0-9a-f]{32}$")
                self.assertGreater(f["bytes"], 0)

    def test_download_url_escapes_the_name(self):
        url = jgi.download_url({"file_id": "abc", "name": "a b.gff"})
        self.assertEqual(url, "https://files.jgi.doe.gov/filedownload/abc/a%20b.gff")

    def test_identical_duplicates_merge_and_conflicts_fail(self):
        row = {"file_name": "a.gff", "file_size": 3, "md5sum": "m", "file_status": "RESTORED"}
        merged = jgi.merge_duplicates("r", [dict(row, _id="2"), dict(row, _id="1")])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["file_id"], "1")
        self.assertEqual(merged[0]["duplicate_file_ids"], ["2"])
        with self.assertRaises(ValueError):
            jgi.merge_duplicates("r", [dict(row, _id="1"), dict(row, _id="2", md5sum="other")])


def api_file(name, file_id, md5="0" * 32, size=3):
    return {"file_name": name, "_id": file_id, "file_size": size, "md5sum": md5,
            "file_status": "RESTORED"}


class CollectTests(unittest.TestCase):
    """collect() against canned search pages; no network."""

    def record(self, **fields):
        base = {"record_id": "IMG_AP-2", "query": "q", "file_name_pattern": r"Ga1_.*\.gff",
                "kind": "hand-written", "citation": "hand-written"}
        return {**base, **fields}

    def run_collect(self, pages, record):
        calls = []

        def fake_search(query, page):
            calls.append(page)
            return pages[page]

        manifest = {"records": [record]}
        with tempfile.TemporaryDirectory() as tmp, \
                unittest.mock.patch.object(jgi, "search", fake_search), \
                contextlib.redirect_stderr(io.StringIO()):
            jgi.collect(manifest, Path(tmp) / "out.yaml")
            written = jgi.load(Path(tmp) / "out.yaml")
        return written["records"][0], calls

    def test_finds_record_on_a_later_page_and_selects_by_full_match(self):
        pages = {
            1: {"organisms": [{"id": "other"}], "next_page": 2},
            2: {"organisms": [{"id": "IMG_AP-2", "name": "Isolate", "data_utilization_status": "Unrestricted",
                               "files": [api_file("Ga1_pfam.gff", "b"), api_file("Ga1_cog.gff", "a"),
                                         api_file("Ga1_pfam.gff.gz", "c"), api_file("x_Ga1_a.gff", "d")]}],
                "next_page": None},
        }
        written, calls = self.run_collect(pages, self.record())
        self.assertEqual(calls, [1, 2])
        self.assertEqual([f["name"] for f in written["files"]], ["Ga1_cog.gff", "Ga1_pfam.gff"])
        self.assertEqual(written["name"], "Isolate")
        self.assertEqual((written["kind"], written["citation"]), ("hand-written", "hand-written"))

    def test_no_matching_file_fails(self):
        pages = {1: {"organisms": [{"id": "IMG_AP-2", "name": "n", "files": [api_file("other.txt", "a")]}]}}
        with self.assertRaises(LookupError):
            self.run_collect(pages, self.record())

    def test_record_missing_from_every_page_fails(self):
        pages = {1: {"organisms": [{"id": "other"}], "next_page": 2}, 2: {"organisms": [], "next_page": None}}
        with self.assertRaises(LookupError):
            self.run_collect(pages, self.record())

    def test_non_advancing_next_page_fails_instead_of_looping(self):
        pages = {1: {"organisms": [{"id": "other"}], "next_page": 1}}
        with self.assertRaises(LookupError):
            self.run_collect(pages, self.record())

    def test_duplicates_merge_and_conflicts_fail_through_collect(self):
        same = {1: {"organisms": [{"id": "IMG_AP-2", "name": "n", "files": [
            api_file("Ga1_a.gff", "2"), api_file("Ga1_a.gff", "1")]}]}}
        written, _ = self.run_collect(same, self.record())
        self.assertEqual(written["files"][0]["duplicate_file_ids"], ["2"])
        conflict = {1: {"organisms": [{"id": "IMG_AP-2", "name": "n", "files": [
            api_file("Ga1_a.gff", "1"), api_file("Ga1_a.gff", "2", md5="1" * 32)]}]}}
        with self.assertRaises(ValueError):
            self.run_collect(conflict, self.record())


if __name__ == "__main__":
    unittest.main()
