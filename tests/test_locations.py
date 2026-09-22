"""Real joined/partial/circular locations, independent parsing and gap controls."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from Bio import SeqIO
import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from convert_features import ConversionError, import_source, export_source, dataset_validator
from insdc_profile import PROFILE, parse_location, reconstruct_feature, semantic_mappings, nonfeature_text
from validate_closed import validation_errors
from feature_locations import overlap, distance
from build_duckdb import build_database
from query_duckdb import interval_overlap

PLANT = ROOT / "corpus/sources/biopython/cor6_6.gb"
PHIX = ROOT / "corpus/sources/ncbi-refseq/NC_001422.1_2026-09-21.gb"


def imported(content):
    return import_source(content, profile=PROFILE, reference_context="insdc:retained-records", source_uri="urn:ftc:locations")


def constructed(location, qualifiers="", topology="linear"):
    return (f"LOCUS       TEST                      100 bp    DNA     {topology} PLN 01-JAN-2000\n"
            "DEFINITION  Constructed parser control, not observed biological evidence.\n"
            "ACCESSION   TEST0001\nVERSION     TEST0001.1\nFEATURES             Location/Qualifiers\n"
            f"     misc_feature    {location}\n{qualifiers}ORIGIN\n        1 {'a' * 100}\n//\n").encode()


class LocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "local").mkdir(exist_ok=True)
        cls.plant = imported(PLANT.read_bytes())
        cls.phix = imported(PHIX.read_bytes())

    def test_real_roundtrips_and_independent_biopython_meaning(self):
        for path, expected_count in ((PLANT, 38), (PHIX, 32)):
            with self.subTest(path=path.name):
                content = path.read_bytes(); bundle = imported(content)
                self.assertEqual(len(bundle["dataset"]["features"]), expected_count)
                self.assertEqual(export_source(bundle, mode="exact", original_bytes=content), content)
                canonical = export_source(bundle, mode="reconstruct", original_bytes=content)
                again = imported(canonical)
                self.assertEqual(again["dataset"], bundle["dataset"])
                self.assertEqual(semantic_mappings(again), semantic_mappings(bundle))
                self.assertEqual(nonfeature_text(again), nonfeature_text(bundle))
                original_records = list(SeqIO.parse(StringIO(content.decode()), "genbank"))
                new_records = list(SeqIO.parse(StringIO(canonical.decode()), "genbank"))
                self.assertEqual(len(original_records), len(new_records))
                for before, after in zip(original_records, new_records):
                    self.assertEqual((before.id, str(before.seq)), (after.id, str(after.seq)))
                    self.assertEqual([(f.type, f.location, f.qualifiers) for f in before.features],
                                     [(f.type, f.location, f.qualifiers) for f in after.features])
                self.assertEqual(path.read_bytes(), content)

    def test_known_plant_parts_uncertainty_and_repeated_qualifiers(self):
        data = self.plant["dataset"]
        cds = next(f for f in data["features"] if f["seqid"] == "insdc:X62281.1" and f["type"] == "CDS")
        self.assertEqual([(p["start"], p["end"]) for p in cds["location"]["parts"]], [(104, 160), (320, 390), (504, 579)])
        self.assertEqual((cds["start"], cds["end"]), (104, 579))
        self.assertFalse(cds.get("parent"))
        self.assertNotIn("phase", cds)
        self.assertEqual([a["value"] for a in cds["attributes"] if a["key"] == "db_xref"], ["GI:16354", "SWISS-PROT:P31169"])
        mrna = next(f for f in data["features"] if f["seqid"] == "insdc:AJ237582.1" and f["type"] == "mRNA")
        self.assertEqual(mrna["location"]["parts"][0]["start_status"], "before")
        self.assertEqual(mrna["location"]["parts"][-1]["end_status"], "after")
        with self.assertRaisesRegex(ValueError, "uncertain"):
            overlap(data, mrna["seqid"], 1, 1)
        hits = overlap(data, mrna["seqid"], 1, 1, mode="reported")
        self.assertIn({"feature_id": mrna["feature_id"], "bounds": "partial-reported"}, hits)
        self.assertNotIn(mrna["feature_id"], [f["feature_id"] for f in overlap(data, mrna["seqid"], 60, 70, mode="reported")])
        with self.assertRaisesRegex(ValueError, "qualified reference"):
            overlap(data, "AJ237582.1", 1, 1, mode="reported")

    def test_duckdb_overlap_uses_parts_not_envelope(self):
        cds = next(f for f in self.plant["dataset"]["features"] if f["seqid"] == "insdc:X62281.1" and f["type"] == "CDS")
        contig = next(c for c in self.plant["dataset"]["contigs"] if c["contig_id"] == cds["seqid"])
        data = {"contigs": [contig], "features": [cds]}
        point = {"seqid": cds["seqid"], "coordinate_system": "contig", "start": 200, "end": 200}
        self.assertEqual(distance(cds, point, contig), 39)
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as work:
            path, db = Path(work) / "dataset.json", Path(work) / "features.duckdb"
            path.write_text(json.dumps(data)); build_database(ROOT / "model/schema/ber_feature_model.yaml", path, db)
            with duckdb.connect(str(db), read_only=True) as con:
                self.assertEqual(interval_overlap(con, cds["seqid"], 200, 210), [])
                self.assertEqual(interval_overlap(con, cds["seqid"], 160, 160)[0][0], cds["feature_id"])
            partial = deepcopy(cds); partial["location"]["parts"][0]["start_status"] = "before"
            data["features"] = [partial]
            path.write_text(json.dumps(data)); build_database(ROOT / "model/schema/ber_feature_model.yaml", path, db)
            with duckdb.connect(str(db), read_only=True) as con:
                with self.assertRaisesRegex(ValueError, "uncertain"):
                    interval_overlap(con, cds["seqid"], 200, 210)

    def test_real_circular_origin_and_gap_queries(self):
        data = self.phix["dataset"]; contig = data["contigs"][0]
        self.assertEqual((contig["length_bp"], contig["topology"]), (5386, "circular"))
        self.assertEqual(sum(f["location"]["crosses_origin"] for f in data["features"]), 6)
        gene = data["features"][1]
        self.assertEqual([(p["start"], p["end"]) for p in gene["location"]["parts"]], [(3981, 5386), (1, 136)])
        for point in (1, 136, 3981, 5386):
            self.assertIn(gene["feature_id"], [r["feature_id"] for r in overlap(data, contig["contig_id"], point, point)])
        self.assertNotIn(gene["feature_id"], [r["feature_id"] for r in overlap(data, contig["contig_id"], 2000, 2000)])
        left = {"seqid": contig["contig_id"], "coordinate_system": "contig", "start": 5380, "end": 5384}
        right = {**left, "start": 2, "end": 5}
        self.assertEqual(distance(left, right, contig), 3)  # bases 5385, 5386, 1
        self.assertEqual(distance(left, right, {**contig, "topology": "linear"}), 5374)
        with self.assertRaisesRegex(ValueError, "qualified reference"):
            distance(left, {**right, "seqid": "insdc:NC_001422.2"}, contig)

    def test_complement_order_and_generic_qualifier_reconstruction(self):
        qualifiers = ('                     /note="first; key=value"\n'
                      '                     /pseudo\n                     /codon_start=2\n'
                      '                     /note="second with ""quotes"""\n'
                      '                     /unrecognized=""\n')
        for location in ("complement(join(10..20,40..50))", "order(<1..10,30..>90)", "join(90..100,1..5)"):
            with self.subTest(location=location):
                bundle = imported(constructed(location, qualifiers, topology="circular"))
                feature = bundle["dataset"]["features"][0]
                mapping = bundle["mappings"][0]
                rebuilt_block = reconstruct_feature(feature, {k: v for k, v in mapping.items() if k != "source_span"})
                self.assertIn('/note="first; key=value"', rebuilt_block)
                canonical = export_source(bundle, mode="reconstruct")
                self.assertEqual(imported(canonical)["dataset"], bundle["dataset"])
                self.assertEqual([a["key"] for a in feature["attributes"]], ["note", "pseudo", "codon_start", "note", "unrecognized"])
        location = parse_location("complement(join(10..20,40..50))", "insdc:TEST0001.1")
        self.assertEqual([(p["start"], p["strand"]) for p in location["parts"]], [(40, "-"), (10, "-")])
        partial = imported(constructed("<10..20"))["dataset"]["features"][0]
        with self.assertRaisesRegex(ValueError, "uncertain"):
            distance(partial, partial, {"contig_id": partial["seqid"], "length_bp": 100})
        continued = imported(constructed("1..10", '                     /note="before\n                     //\n                     after"\n'))
        self.assertEqual(continued["dataset"]["features"][0]["attributes"], [{"key": "note", "value": "before // after"}])
        self.assertEqual(imported(export_source(continued, mode="reconstruct"))["dataset"], continued["dataset"])

    def test_unsupported_locations_and_incomplete_source_are_refused(self):
        for location in ("1^2", "?", "OTHER.1:1..5", "one-of(1,2)..5", "join(1..10,5..20)",
                         "join(90..100,1..5)", "1..101", "join(complement(1..5),10..20)", "join(order(1..5,10..20),30..40)"):
            with self.subTest(location=location), self.assertRaises(ConversionError):
                imported(constructed(location))
        original = constructed("1..10")
        with self.assertRaises(ConversionError):
            imported(constructed("1..10", '                     /note="' + 'x' * 100 + '"\n'))
        for changed in (original.replace(b"100 bp", b"101 bp"), original.replace(b"VERSION", b"version"),
                        original.replace(b"//\n", b""), original.replace(b"     misc_feature", b"     @unsupported")):
            with self.assertRaises(ConversionError):
                imported(changed)

    def test_model_location_invariants_and_edited_export(self):
        for mutate, diagnostic in (
            (lambda d: d["contigs"][0].pop("length_bp"), "length_bp"),
            (lambda d: d["contigs"][0].update(topology="linear"), "circular"),
            (lambda d: d["features"][1].update(start=2), "envelope"),
            (lambda d: d["features"][1]["location"].update(crosses_origin=False), "origin"),
            (lambda d: d["features"][1]["location"]["parts"][0].update(seqid="insdc:other.1"), "reference"),
            (lambda d: d["features"][1]["location"]["parts"][0].update(start_status="unknown"), "unknown"),
        ):
            data = deepcopy(self.phix["dataset"]); mutate(data)
            self.assertTrue(any(diagnostic in e for e in validation_errors(data, dataset_validator())), diagnostic)
        changed = deepcopy(self.phix); changed["dataset"]["features"][1]["location"]["parts"].reverse()
        for mode in ("exact", "reconstruct"):
            with self.assertRaises(ConversionError):
                export_source(changed, mode=mode)

    def test_circular_parts_cannot_traverse_the_reference_more_than_once(self):
        for wrapper in ("{}", "complement({})"):
            valid = wrapper.format("join(40..45,70..75,10..15)")
            invalid = wrapper.format("join(40..45,10..15,70..75)")
            with self.subTest(location=valid):
                bundle = imported(constructed(valid, topology="circular"))
                self.assertEqual(validation_errors(bundle["dataset"], dataset_validator()), [])
                self.assertEqual(imported(export_source(bundle, mode="reconstruct"))["dataset"], bundle["dataset"])
            with self.subTest(location=invalid), self.assertRaisesRegex(ConversionError, "one reference circuit"):
                imported(constructed(invalid, topology="circular"))

    def test_location_cli_launcher_and_read_only_failures(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as work:
            path = Path(work) / "dataset with spaces.json"
            path.write_text(json.dumps(self.plant["dataset"]))
            before = path.read_bytes()
            command = ["just", "location-overlap", str(path), "insdc:AJ237582.1", "60", "70", "reported"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))  # the separately annotated intron still overlaps
            command[-1] = "exact"
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
