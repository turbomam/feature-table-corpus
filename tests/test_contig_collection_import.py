"""`convert_features.py import` can write one ContigCollection and put every contig in it.

https://github.com/turbomam/feature-table-corpus/issues/204. The collection's values are supplied by
the caller, not read from the source. These tests use the GOLD record for the genome in the test file,
read on 2026-11-13 from GOLD's public export, https://gold.jgi.doe.gov/download?mode=site_excel : analysis project Ga0423362, organism Go0389779
"Clostridium acetobutylicum DJ311", superkingdom Bacteria, kingdom Bacillati, phylum BACILLOTA,
genus Clostridium, species Clostridium acetobutylicum, strain DJ311.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lakehouse_export as lakehouse  # noqa: E402
from convert_features import ConversionError, export_source, import_source, validate_bundle  # noqa: E402

SCHEMA = ROOT / "model/schema/ber_feature_model.yaml"
DJ311 = ROOT / "corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_structural_annotation.gff"
PROFILE = "gff3-contig/4.0.0"
REFERENCE = "img:IMG_AP-1268149"
COLLECTION = {
    "collection_id": "Ga0423362",
    "collection_type": "isolate",
    "name": "Clostridium acetobutylicum DJ311",
    "taxonomic_lineage": ["Bacteria", "Bacillati", "BACILLOTA", "Clostridium", "Clostridium acetobutylicum", "DJ311"],
}


def imported(collection=None):
    return import_source(DJ311.read_bytes(), profile=PROFILE, reference_context=REFERENCE,
                         source_uri="urn:ftc:contig-collection-test", collection=collection)


class ContigCollectionImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = DJ311.read_bytes()
        cls.plain = imported()
        cls.grouped = imported(COLLECTION)

    def test_without_options_the_bundle_has_no_collection(self):
        self.assertNotIn("collection", self.plain)
        self.assertNotIn("contig_collections", self.plain["dataset"])
        self.assertFalse(any("member_of" in contig for contig in self.plain["dataset"]["contigs"]))

    def test_every_contig_of_a_multi_sequence_genome_joins_the_collection(self):
        contigs = self.grouped["dataset"]["contigs"]
        self.assertEqual(len(contigs), 5)
        self.assertEqual({tuple(c["member_of"]) for c in contigs}, {("Ga0423362",)})
        self.assertEqual(self.grouped["dataset"]["contig_collections"], [COLLECTION])
        # Only the collection and member_of differ from the plain import.
        stripped = json.loads(json.dumps(self.grouped))
        del stripped["collection"], stripped["dataset"]["contig_collections"]
        for contig in stripped["dataset"]["contigs"]:
            del contig["member_of"]
        self.assertEqual(stripped, self.plain)

    def test_validation_and_exact_export_repeat_the_collection(self):
        validate_bundle(self.grouped, self.content)
        self.assertEqual(export_source(self.grouped, mode="exact", original_bytes=self.content), self.content)
        edited = json.loads(json.dumps(self.grouped))
        edited["dataset"]["contig_collections"][0]["name"] = "changed"
        with self.assertRaises(ConversionError) as caught:
            validate_bundle(edited, self.content)
        self.assertEqual(caught.exception.code, "edited-bundle")

    def test_genbank_exports_with_a_collection(self):
        source = ROOT / "corpus/sources/ncbi-refseq/NC_001422.1_2026-09-21.gb"
        content = source.read_bytes()
        bundles = [import_source(content, profile="insdc-locations/1.0.0", reference_context="refseq:NC_001422.1",
                                 source_uri="urn:ftc:contig-collection-test", collection=collection)
                   for collection in (None, {"collection_id": "NC_001422.1", "collection_type": "isolate"})]
        self.assertEqual(export_source(bundles[1], mode="exact", original_bytes=content), content)
        self.assertEqual(export_source(bundles[1], mode="reconstruct", original_bytes=content),
                         export_source(bundles[0], mode="reconstruct", original_bytes=content))

    def test_refusals(self):
        for collection, code in (({"name": "no id"}, "collection"),
                                 ({"collection_id": "x", "organism": "y"}, "collection"),
                                 ({"collection_id": "x", "collection_type": "genome"}, "dataset-invalid")):
            with self.subTest(collection=collection), self.assertRaises(ConversionError) as caught:
                imported(collection)
            self.assertEqual(caught.exception.code, code)

    def test_lakehouse_export_writes_the_collection(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="collection ", dir=scratch) as temp:
            data = Path(temp) / "dataset.json"
            data.write_text(json.dumps(self.grouped["dataset"]))
            lakehouse.export(SCHEMA, data, Path(temp) / "out")
            collections = pq.read_table(Path(temp) / "out/contig_collections.parquet").to_pylist()
            contigs = pq.read_table(Path(temp) / "out/contigs.parquet").to_pylist()
        self.assertEqual(len(collections), 1)
        self.assertEqual({key: collections[0][key] for key in COLLECTION}, COLLECTION)
        self.assertEqual([c["member_of"] for c in contigs], [["Ga0423362"]] * 5)

    def test_command_line_options(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "bundle.json"
            lineage = [arg for rank in COLLECTION["taxonomic_lineage"] for arg in ("--taxonomic-lineage", rank)]
            run = subprocess.run(
                [sys.executable, str(ROOT / "scripts/convert_features.py"), "import", str(DJ311), "--profile", PROFILE,
                 "--reference-context", REFERENCE, "--source-uri", "urn:ftc:contig-collection-test",
                 "--output", str(out), "--collection-id", COLLECTION["collection_id"],
                 "--collection-type", COLLECTION["collection_type"], "--collection-name", COLLECTION["name"], *lineage],
                capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(out.read_text())["collection"], COLLECTION)
            refused = subprocess.run(
                [sys.executable, str(ROOT / "scripts/convert_features.py"), "import", str(DJ311), "--profile", PROFILE,
                 "--reference-context", REFERENCE, "--output", str(Path(temp) / "refused.json"),
                 "--collection-type", "isolate"],
                capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(json.loads(refused.stderr)["code"], "collection")


if __name__ == "__main__":
    unittest.main()
