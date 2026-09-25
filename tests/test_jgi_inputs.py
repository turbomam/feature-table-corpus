"""Offline checks for the JGI login-only input manifest and its verifier."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
