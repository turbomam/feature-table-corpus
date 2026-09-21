"""Real BGC evidence, source selection and genomic query controls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bgc_example import (EXCERPT, FIRST, LAST, REFERENCE, REPORT, SEQID, SOURCE,
                         derive_source, make_report, query_order, source_rows)
from build_duckdb import build_database
from convert_features import ConversionError, export_source, import_source


class BGCExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "local").mkdir(exist_ok=True)

    def test_report_and_direct_source_evidence_reproduce(self):
        report = make_report()
        self.assertEqual(report, json.loads(REPORT.read_text()))
        self.assertEqual(report["query_results"]["signed_gaps_bp"], [-4, 24])
        self.assertEqual(len(report["query_results"]["cluster_gene_order"]), 22)
        full = SOURCE.read_bytes().splitlines(keepends=True)
        derived_rows = [line for _, line, _, _ in source_rows(EXCERPT.read_bytes())]
        self.assertEqual(len(derived_rows), 44)
        self.assertTrue(all(line in full for line in derived_rows))
        self.assertEqual(derive_source(SOURCE.read_bytes()), EXCERPT.read_bytes())
        with self.assertRaisesRegex(ConversionError, "checksum"):
            derive_source(SOURCE.read_bytes() + b"# edited\n")

    def test_product_lookup_inclusive_overlap_and_reference_controls(self):
        bundle = import_source(EXCERPT.read_bytes(), profile="gff3-contig/1.0.0",
                               reference_context=REFERENCE, source_uri="urn:test:bgc")
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as work:
            path, db = Path(work) / "data.json", Path(work) / "features.duckdb"
            path.write_text(json.dumps(bundle["dataset"]))
            build_database(ROOT / "model/schema/ber_feature_model.yaml", path, db)
            with duckdb.connect(str(db), read_only=True) as con:
                opts = dict(actual_reference=bundle["reference_context"], reference_context=REFERENCE,
                            sequence_id=SEQID, start=FIRST, end=LAST)
                found = query_order(con, **opts, product="acyl carrier protein")
                self.assertEqual([r["old_locus_tag"] for r in found], ["SCO5089"])
                # At this shared base, both the ACP and following cyclase overlap.
                boundary = query_order(con, **{**opts, "start": 5532706, "end": 5532706})
                self.assertEqual([r["old_locus_tag"] for r in boundary], ["SCO5089", "SCO5090"])
                for override, code in (({"start": True}, "query-interval"),
                                       ({"start": 0}, "query-interval"),
                                       ({"end": FIRST - 1}, "query-interval"),
                                       ({"coordinate_system": "protein"}, "coordinate-space"),
                                       ({"reference_context": "refseq:NC_003888.2"}, "reference-context")):
                    with self.subTest(override=override), self.assertRaises(ConversionError) as caught:
                        query_order(con, **{**opts, **override})
                    self.assertEqual(caught.exception.code, code)
                self.assertEqual(query_order(con, **opts, product="x' OR true --"), [])

    def test_edited_coordinate_or_annotation_cannot_replay_old_source(self):
        bundle = import_source(EXCERPT.read_bytes(), profile="gff3-contig/1.0.0",
                               reference_context=REFERENCE, source_uri="urn:test:bgc")
        cds = next(i for i, row in enumerate(bundle["dataset"]["features"]) if row["type"] == "CDS")
        for key, value in (("start", 1), ("product", "invented annotation"), ("seqid", "NC_003888.2")):
            edited = copy.deepcopy(bundle)
            edited["dataset"]["features"][cds][key] = value
            for mode in ("exact", "reconstruct"):
                with self.subTest(key=key, mode=mode), self.assertRaises(ConversionError):
                    export_source(edited, mode=mode)

    def test_offline_cli_check_is_read_only(self):
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in (SOURCE, EXCERPT, REPORT)]
        result = subprocess.run([sys.executable, str(ROOT / "scripts/bgc_example.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reproduce exactly", result.stdout)
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in (SOURCE, EXCERPT, REPORT)])
