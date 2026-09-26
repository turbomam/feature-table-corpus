"""Offline checks that vendored JGI index entries agree with the JGI input manifest."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class JgiManifestCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index = yaml.safe_load((ROOT / "corpus/index.yaml").read_text())
        cls.entries = [e for e in index["entries"]
                       if (e.get("path") or "").startswith(verify.JGI_SOURCES)]
        assert cls.entries

    def run_check(self, entries, root=ROOT):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bad = verify.check_jgi_manifest(entries, root)
        return bad, out.getvalue()

    def test_retained_entries_pass(self):
        bad, out = self.run_check(self.entries)
        self.assertEqual(bad, 0, out)

    def test_record_level_drift_fails(self):
        for field, value in [("dataset_doi", "10.25585/0000000"),
                             ("proposal_acceptance_date", "2099-01-01")]:
            with self.subTest(field=field):
                entries = copy.deepcopy(self.entries)
                entries[0][field] = value
                bad, out = self.run_check(entries)
                self.assertEqual(bad, 1, out)
                self.assertIn(f"JGI-MISMATCH    {entries[0]['id']}  {field}:", out)

    def test_attribution_must_name_the_doi(self):
        entries = copy.deepcopy(self.entries)
        entries[0]["attribution"] = entries[0]["attribution"].replace(entries[0]["dataset_doi"], "10.25585/0")
        bad, out = self.run_check(entries)
        self.assertEqual(bad, 1, out)
        self.assertIn("attribution does not name dataset DOI", out)

    def test_dotfiles_are_ignored_but_other_unindexed_files_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / verify.JGI_MANIFEST
            manifest.parent.mkdir(parents=True)
            shutil.copy(ROOT / verify.JGI_MANIFEST, manifest)
            for e in self.entries:
                path = root / e["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            record_dir = root / self.entries[0]["path"]
            (record_dir.parent / ".DS_Store").write_bytes(b"\0")
            bad, out = self.run_check(self.entries, root)
            self.assertEqual(bad, 0, out)
            (record_dir.parent / "unindexed.gff").write_text("x\n")
            bad, out = self.run_check(self.entries, root)
            self.assertEqual(bad, 1, out)
            self.assertIn("JGI-UNINDEXED", out)


if __name__ == "__main__":
    unittest.main()
