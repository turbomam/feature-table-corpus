"""A Phytozome GFF3 and its annotation_info.txt map together to the feature model and back, byte for byte."""
import contextlib
import copy
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phytozome_annotation_info as table_dialect  # noqa: E402
import phytozome_annotation_map as mapping  # noqa: E402
import phytozome_gene_exons as gff3_dialect  # noqa: E402
import phytozome_gene_exons_map as gff3_map  # noqa: E402

GFF3 = ROOT / "tests/fixtures/phytozome/constructed.gene_exons.gff3"
TABLE = ROOT / "tests/fixtures/phytozome/constructed.annotation_info.txt"
URL = "https://example.org/constructed.annotation_info.txt"


class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.transformers = gff3_map._transformers()
        cls.gff3 = gff3_dialect.parse(GFF3)
        cls.table = table_dialect.parse(TABLE)
        cls.dataset = mapping.forward(cls.gff3, cls.table, URL, cls.transformers)

    def back(self, dataset):
        return mapping.reverse(dataset, "out.gff3", "out.txt", self.transformers)

    def mrna(self, dataset, index=0):
        return [f for f in dataset["features"] if f["type"] == "mRNA"][index]

    def test_fixture_round_trips_byte_for_byte(self):
        problems, report = mapping.roundtrip(GFF3, TABLE)
        self.assertEqual(problems, [])
        self.assertEqual((report["mRNA"], report["table_attributes"]), (3, 20))

    def test_table_values_become_attributes_on_the_mrna(self):
        mrna = self.mrna(self.dataset)
        keys = [a["key"] for a in mrna["attributes"]]
        self.assertEqual(keys[:5], ["ID", "Name", "pacid", "longest", "Parent"])
        self.assertEqual([a["value"] for a in mrna["attributes"] if a["key"] == "Pfam"], ["PF00001", "PF00002"])
        self.assertIn({"key": "Best-hit-clamy-name", "value": "Cre99.g999901"}, mrna["attributes"])
        self.assertEqual(mrna["source_files"], [URL])
        self.assertTrue(all("source_files" not in f for f in self.dataset["features"] if f["type"] != "mRNA"))

    def test_reverse_gives_both_documents_back(self):
        gff3, table = self.back(self.dataset)
        self.assertEqual(gff3_dialect.write(gff3), GFF3.read_text())
        self.assertEqual(table_dialect.write(table), TABLE.read_text())

    def test_forward_refuses_what_it_cannot_reproduce(self):
        table = copy.deepcopy(self.table)
        table["rows"].reverse()
        with self.assertRaisesRegex(ValueError, "not sorted by locusName"):
            mapping.forward(self.gff3, table, URL, self.transformers)
        table = copy.deepcopy(self.table)
        table["rows"][0]["peptideName"] = "Exa01g00010.1.p"
        with self.assertRaisesRegex(ValueError, "peptideName are not"):
            mapping.forward(self.gff3, table, URL, self.transformers)
        table = copy.deepcopy(self.table)
        del table["rows"][1]
        with self.assertRaisesRegex(ValueError, "1 GFF3 mRNA have no table row"):
            mapping.forward(self.gff3, table, URL, self.transformers)
        gff3 = copy.deepcopy(self.gff3)
        mrna = next(r for r in gff3["rows"] if r["type"] == "mRNA")
        mrna["attribute_order"].append("GO")
        mrna["GO"] = "GO:1"
        with self.assertRaisesRegex(ValueError, "already has \\['GO'\\]"):
            mapping.forward(gff3, self.table, URL, self.transformers)

    def test_reverse_refuses_what_the_files_cannot_hold(self):
        cases = {
            "no url": (lambda d: self.mrna(d).pop("source_files"), "exactly one source_files"),
            "two urls": (lambda d: self.mrna(d, 1).update(source_files=["https://example.org/other"]),
                         "different table URLs"),
            "value on a gene": (lambda d: next(f for f in d["features"] if f["type"] == "gene")["attributes"]
                                .append({"key": "GO", "value": "GO:1"}), "only an mRNA"),
            "order": (lambda d: self.mrna(d)["attributes"].reverse(), "not all after|not in table column order"),
            "two best hits": (lambda d: self.mrna(d)["attributes"].append(
                {"key": "Best-hit-clamy-name", "value": "x"}), "not in table column order|has 2 values"),
            "space in a list value": (lambda d: next(a for a in self.mrna(d)["attributes"] if a["key"] == "Pfam")
                                      .update(value="PF 1"), "contains ' '"),
        }
        for name, (change, expected) in cases.items():
            with self.subTest(name):
                dataset = copy.deepcopy(self.dataset)
                change(dataset)
                with self.assertRaisesRegex(ValueError, expected):
                    self.back(dataset)

    def test_forward_refuses_a_table_row_with_no_mrna(self):
        table = copy.deepcopy(self.table)
        table["rows"][0]["pacId"] = "PAC:99999999"
        with self.assertRaisesRegex(ValueError, "PAC:99999999 is not one mRNA of the GFF3"):
            mapping.forward(self.gff3, table, URL, self.transformers)

    def test_reverse_checks_where_table_values_sit(self):
        def attributes(dataset):
            return self.mrna(dataset)["attributes"]
        dataset = copy.deepcopy(self.dataset)
        attrs = attributes(dataset)
        attrs.insert(0, attrs.pop(next(i for i, a in enumerate(attrs) if a["key"] == "Panther")))
        with self.assertRaisesRegex(ValueError, "not all after the GFF3's own attributes"):
            self.back(dataset)
        dataset = copy.deepcopy(self.dataset)
        attrs = attributes(dataset)
        go = attrs.pop(next(i for i, a in enumerate(attrs) if a["key"] == "GO"))
        attrs.insert(next(i for i, a in enumerate(attrs) if a["key"] == "Pfam"), go)
        with self.assertRaisesRegex(ValueError, "not in table column order"):
            self.back(dataset)
        dataset = copy.deepcopy(self.dataset)
        attrs = attributes(dataset)
        at = next(i for i, a in enumerate(attrs) if a["key"] == "Best-hit-clamy-name")
        attrs.insert(at + 1, {"key": "Best-hit-clamy-name", "value": "Cre99.g999999"})
        with self.assertRaisesRegex(ValueError, "Best-hit-clamy-name has 2 values"):
            self.back(dataset)

    def test_commands_write_both_files_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset, gff3, table = Path(tmp) / "d.json", Path(tmp) / "back.gff3", Path(tmp) / "back.txt"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(GFF3), str(TABLE), str(dataset),
                                               "--table-url", URL]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(gff3), str(table)]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(gff3), str(table)]), 1)
            self.assertIn("already exists", err.getvalue())
            self.assertEqual(gff3.read_text(), GFF3.read_text())
            self.assertEqual(table.read_text(), TABLE.read_text())

    def test_clean_round_trip_prints_nothing_to_stderr(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/phytozome_annotation_map.py"), "roundtrip",
                                 str(GFF3), str(TABLE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
