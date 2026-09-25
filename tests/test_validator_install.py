"""The QC source must pass its checksum before extraction or execution."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_gff3toolkit as installer


class ValidatorInstallTests(unittest.TestCase):
    def test_corrupt_cached_archive_is_never_extracted_or_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "local/tools"
            tools.mkdir(parents=True)
            (tools / f"gff3toolkit-{installer.VERSION}.tar.gz").write_bytes(b"corrupt")
            with patch.object(installer, "ROOT", root), \
                 patch.object(installer.sys, "version_info", installer.PYTHON_VERSION), \
                 patch.object(installer.tarfile, "open") as extract, \
                 patch.object(installer.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                    installer.install()
                extract.assert_not_called()
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
