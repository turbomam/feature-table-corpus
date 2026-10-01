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
        with self.assertRaisesRegex(ValueError, "peptideName is not the mRNA's Name"):
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
                         "name 2 different table URLs"),
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

    def test_rows_sort_by_locus_then_transcript_number_not_text(self):
        # TAIR10 has a gene with a .10 transcript; as text it would sort before .9.
        rows = [{"locusName": "AT1G1", "transcriptName": f"AT1G1.{n}"} for n in (10, 9, 2, 1)]
        rows.append({"locusName": "AT1G0", "transcriptName": "AT1G0.1"})
        self.assertEqual([r["transcriptName"] for r in sorted(rows, key=mapping.table_order)],
                         ["AT1G0.1", "AT1G1.1", "AT1G1.2", "AT1G1.9", "AT1G1.10"])

    def test_reverse_refuses_one_path_for_both_files_and_leaves_nothing_half_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "d.json"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(GFF3), str(TABLE), str(dataset)]), 0)
                same = Path(tmp) / "same.out"
                self.assertEqual(mapping.main(["reverse", str(dataset), str(same), str(same)]), 1)
                self.assertFalse(same.exists())
                first = Path(tmp) / "part.gff3"
                self.assertEqual(mapping.main(["reverse", str(dataset), str(first),
                                               str(Path(tmp) / "no-such-dir" / "t.txt")]), 1)
                self.assertFalse(first.exists())
            self.assertIn("different paths", err.getvalue())

    def test_a_failed_write_leaves_neither_file(self):
        # A write that fails after creating its file (a full disk, say) must not leave it behind.
        from unittest import mock
        real = mapping.write_new
        def fail_second(path, text):
            if str(path).endswith(".txt"):
                Path(path).write_text("partial")
                return False, True
            return real(path, text)
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "d.json"
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(GFF3), str(TABLE), str(dataset)]), 0)
                with mock.patch.object(mapping, "write_new", fail_second):
                    self.assertEqual(mapping.main(["reverse", str(dataset), str(Path(tmp) / "g.gff3"),
                                                   str(Path(tmp) / "t.txt")]), 1)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["d.json"])

    def test_a_file_another_process_made_first_is_left_alone(self):
        # The table path appears between the existence check and the write: its exclusive
        # open fails, and the cleanup must remove only the GFF3 this call wrote.
        from unittest import mock
        real = mapping.write_new
        def race(path, text):
            if str(path).endswith(".txt"):
                Path(path).write_text("theirs")
            return real(path, text)
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "d.json"
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(GFF3), str(TABLE), str(dataset)]), 0)
                with mock.patch.object(mapping, "write_new", race):
                    self.assertEqual(mapping.main(["reverse", str(dataset), str(Path(tmp) / "g.gff3"),
                                                   str(Path(tmp) / "t.txt")]), 1)
            self.assertEqual((Path(tmp) / "t.txt").read_text(), "theirs")
            self.assertFalse((Path(tmp) / "g.gff3").exists())

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


class HeaderExtraTests(unittest.TestCase):
    def test_the_commands_keep_species_and_provenance_lines(self):
        lines = GFF3.read_text().splitlines(keepends=True)
        extra = ["##species Exemplum fictum\n", "# derived-from: x\n", "# single-change: y\n", "# validity: z\n"]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "with-extra.gene_exons.gff3"
            source.write_text("".join(lines[:2] + extra + lines[2:]))
            dataset, header = Path(tmp) / "d.json", Path(tmp) / "h.json"
            gff3, table = Path(tmp) / "back.gff3", Path(tmp) / "back.txt"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mapping.main(["forward", str(source), str(TABLE), str(dataset), "--table-url", URL,
                                               "--header", str(header)]), 0, err.getvalue())
                self.assertEqual(mapping.main(["reverse", str(dataset), str(gff3), str(table),
                                               "--header", str(header)]), 0, err.getvalue())
            self.assertEqual(gff3.read_bytes(), source.read_bytes())
            self.assertEqual(table.read_bytes(), TABLE.read_bytes())


def populus_table(text, other_peptide=False):
    """The constructed table rewritten in Populus's arabi layout: twelve columns, the ec and KOG
    values where TAIR10 has them (under swapped labels), and peptideName the Name plus ".p"."""
    lines = text.splitlines()
    rows = []
    for number, line in enumerate(lines[1:]):
        cells = line.split("\t")
        cells[3] = (cells[2].rsplit(".", 1)[0] + ".9.p") if other_peptide and number == 0 else cells[2] + ".p"
        rows.append("\t".join(cells[:10] + ["AT1G01010", "a defline"]))
    return "\n".join(["\t".join(table_dialect.LAYOUTS["arabi"])] + rows) + "\n"


class PopulusLayoutTests(unittest.TestCase):
    def test_the_arabi_layout_round_trips_byte_for_byte(self):
        for other in (False, True):
            with self.subTest(other_peptide=other), tempfile.TemporaryDirectory() as tmp:
                table = Path(tmp) / "populus.annotation_info.txt"
                table.write_text(populus_table(TABLE.read_text(), other))
                problems, report = mapping.roundtrip(GFF3, table)
                self.assertEqual(problems, [])

    def test_values_are_keyed_by_what_they_are_and_odd_peptides_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            table = Path(tmp) / "populus.annotation_info.txt"
            table.write_text(populus_table(TABLE.read_text(), other_peptide=True))
            gff3, populus = gff3_dialect.parse(GFF3), table_dialect.parse(table)
        tair = mapping.forward(gff3, table_dialect.parse(TABLE), URL)
        dataset = mapping.forward(gff3, populus, URL)
        def values(ds, key):
            return [a["value"] for f in ds["features"] for a in f.get("attributes", []) if a["key"] == key]
        self.assertEqual(values(dataset, "ec"), values(tair, "ec"))
        self.assertEqual(values(dataset, "KOG"), values(tair, "KOG"))
        self.assertEqual(len(values(dataset, "peptideName")), 1)
        self.assertEqual(mapping.table_layout(dataset), "arabi")
        self.assertEqual(mapping.table_layout(tair), "clamy_rice")

if __name__ == "__main__":
    unittest.main()
