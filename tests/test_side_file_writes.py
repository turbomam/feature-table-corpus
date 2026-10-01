"""A mapping command whose side file (--spelling or --header) fails to write leaves no output behind.

https://github.com/turbomam/feature-table-corpus/issues/147: a partly written side file used to stay,
and because outputs open with "x", a retry then failed on it.
"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import img_functional_map  # noqa: E402
import img_per_method_map  # noqa: E402
import img_tmhmm_signalp_map  # noqa: E402
import phytozome_annotation_map  # noqa: E402
import phytozome_gene_exons_map  # noqa: E402

IMG = ROOT / "tests/fixtures/img-functional-gff/constructed.gff"
REAL = ROOT / "corpus/sources/jgi-img/IMG_AP-1268149"
PHYTOZOME = ROOT / "tests/fixtures/phytozome/constructed.gene_exons.gff3"
TABLE = ROOT / "tests/fixtures/phytozome/constructed.annotation_info.txt"


def commands(tmp):
    """(name, module, argv) for each command that writes a Dataset and a side file."""
    side = str(Path(tmp) / "side.json")
    out = str(Path(tmp) / "d.json")
    return [
        ("functional", img_functional_map, ["forward", str(IMG), out, "--spelling", side]),
        ("per-method", img_per_method_map, ["forward", str(REAL / "Ga0423362_functional_annotation.gff"),
                                            str(REAL / "Ga0423362_cog.gff"), out, "--spelling", side]),
        ("tmhmm-signalp", img_tmhmm_signalp_map, ["forward", str(REAL / "Ga0423362_functional_annotation.gff"),
                                                  str(REAL / "Ga0423362_cleavage_sites.gff"), out, "--spelling", side]),
        ("gene-exons", phytozome_gene_exons_map, ["forward", str(PHYTOZOME), out, "--header", side]),
        ("annotation", phytozome_annotation_map, ["forward", str(PHYTOZOME), str(TABLE), out, "--header", side]),
    ]


class SideFileWriteTests(unittest.TestCase):
    def test_a_failed_side_file_write_leaves_neither_file(self):
        real = img_functional_map.write_new
        for name in [c[0] for c in commands("x")]:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                calls = []

                def fail_second(path, text):
                    calls.append(path)
                    if len(calls) == 2:  # the side file: created, then the write fails
                        Path(path).write_text("partial")
                        return False, True
                    return real(path, text)
                _, module, argv = next(c for c in commands(tmp) if c[0] == name)
                with mock.patch.object(img_functional_map, "write_new", fail_second), \
                        contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(argv), 1)
                self.assertEqual(len(calls), 2)
                self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), [])

    def test_a_file_another_process_made_first_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "side.json").write_text("theirs")
            _, module, argv = commands(tmp)[0]
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(argv), 1)
            self.assertEqual(Path(tmp, "side.json").read_text(), "theirs")
            self.assertFalse(Path(tmp, "d.json").exists())


if __name__ == "__main__":
    unittest.main()
