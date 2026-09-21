"""Publication boundaries and failures in the rendered-site link check."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_docs
import check_site


class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (prepare_docs.ROOT / "local").mkdir(exist_ok=True)

    def test_only_tracked_allowed_artifacts_are_staged(self):
        with tempfile.TemporaryDirectory(dir=prepare_docs.ROOT / "local") as directory:
            root = Path(directory)
            files = {"README.md": "# Example\n\n[Sources](corpus/)\n", "corpus/example.gff3": "##gff-version 3\n",
                     "local/private.md": "private", "docs/.env": "private", "docs/cache.duckdb": "database",
                     "docs/untracked.md": "private", "other/private.md": "private"}
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            tracked = "\0".join(n for n in files if n != "docs/untracked.md").encode()
            dest = root / "local/site-src"
            with patch.object(prepare_docs, "ROOT", root), patch.object(prepare_docs, "DEST", dest), patch.object(prepare_docs.subprocess, "check_output", return_value=tracked):
                prepare_docs.prepare()
                self.assertTrue((dest / "corpus/example.gff3").is_file())
                self.assertIn("corpus/README.md", (dest / "README.md").read_text())
                for name in files:
                    if name not in ("README.md", "corpus/example.gff3"):
                        self.assertFalse((dest / name).exists(), name)
                # Rebuilding removes stale publication output as well.
                stale = dest / "stale.txt"
                stale.write_text("old")
                prepare_docs.prepare()
                self.assertFalse(stale.exists())

    def test_external_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=prepare_docs.ROOT / "local") as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs/example.md").symlink_to(prepare_docs.ROOT / "README.md")
            with patch.object(prepare_docs, "ROOT", root), patch.object(prepare_docs, "DEST", root / "local/site-src"), patch.object(prepare_docs.subprocess, "check_output", return_value=b"docs/example.md\0"):
                with self.assertRaisesRegex(ValueError, "Refusing linked"):
                    prepare_docs.prepare()

    def test_symlinked_scratch_parent_is_rejected_before_deletion(self):
        with tempfile.TemporaryDirectory(dir=prepare_docs.ROOT / "local") as directory:
            outer = Path(directory)
            root = outer / "repo"; root.mkdir()
            elsewhere = outer / "elsewhere"; elsewhere.mkdir()
            (elsewhere / "site-src").mkdir()
            sentinel = elsewhere / "site-src/keep.txt"; sentinel.write_text("keep")
            (root / "local").symlink_to(elsewhere, target_is_directory=True)
            with patch.object(prepare_docs, "ROOT", root), patch.object(prepare_docs, "DEST", root / "local/site-src"), patch.object(prepare_docs.subprocess, "check_output", return_value=b""):
                with self.assertRaisesRegex(ValueError, "Refusing a symlink"):
                    prepare_docs.prepare()
            self.assertEqual(sentinel.read_text(), "keep")

    def test_broken_links_and_fragments_fail(self):
        with tempfile.TemporaryDirectory(dir=prepare_docs.ROOT / "local") as directory:
            root = Path(directory)
            (root / "index.html").write_text('<a href="child/#target">Child</a>')
            (root / "child").mkdir()
            child = root / "child/index.html"
            child.write_text('<h1 id="target">Target</h1><a href="/feature-table-corpus/">Home</a>')
            check_site.check(root)
            child.write_text('<h1 id="other">Other</h1>')
            with self.assertRaisesRegex(ValueError, "missing fragment"):
                check_site.check(root)
            child.write_text('<h1 id="target">Target</h1><img src="missing.png">')
            with self.assertRaisesRegex(ValueError, "missing target"):
                check_site.check(root)


if __name__ == "__main__":
    unittest.main()
