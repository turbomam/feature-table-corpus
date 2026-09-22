"""Real BGC evidence, source selection and genomic query controls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bgc_example import (EXCERPT, EXPECTED, FIRST, LAST, REFERENCE, REPORT, SEQID, SOURCE, URI,
                         derive_source, export_example, make_report, query_order, source_rows)
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
        self.assertEqual(len(report["source_evidence"]), 22)
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
                opts = dict(reference_context=REFERENCE,
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
                for empty in (None, "", "   "):
                    with self.subTest(empty=empty), self.assertRaises(ConversionError) as caught:
                        query_order(con, **{**opts, "reference_context": empty})
                    self.assertEqual(caught.exception.code, "reference-context")
                self.assertEqual(query_order(con, **opts, product="x' OR true --"), [])
                for start, end in ((1, 100), (LAST + 1, LAST + 100), (10_000_000, 10_000_100)):
                    with self.subTest(start=start, end=end):
                        self.assertEqual(query_order(con, **{**opts, "start": start, "end": end}), [])

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

    def test_pinned_context_and_independent_full_order_cannot_be_redefined(self):
        bundle = import_source(EXCERPT.read_bytes(), profile="gff3-contig/1.0.0",
                               reference_context=REFERENCE, source_uri=URI, metadata_profile="ncbi")
        for field in ("reference_context", "source_uri"):
            edited = copy.deepcopy(bundle)
            if field == "reference_context":
                edited[field] = "refseq:NC_003888.2"
            else:
                edited["source"]["artifact"]["uri"] = "urn:changed:source"
            for mode in ("exact", "reconstruct"):
                with self.subTest(field=field, mode=mode), self.assertRaisesRegex(ConversionError, "pinned BGC context"):
                    export_example(edited, mode=mode)
        # A coordinated wrong SQL order and expected list must still fail
        # independent inspection of all 22 genes in the retained source.
        expected = json.loads(EXPECTED.read_text())
        order = expected["cluster_gene_order"]
        order[0], order[1] = order[1], order[0]
        def wrong_order(con, **kwargs):
            rows = query_order(con, **kwargs)
            if len(rows) == 22:
                rows[0], rows[1] = rows[1], rows[0]
            return rows
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as work:
            path = Path(work) / "wrong-expectations.json"
            path.write_text(json.dumps(expected))
            with patch("bgc_example.EXPECTED", path), patch("bgc_example.query_order", wrong_order):
                with self.assertRaisesRegex(ConversionError, "full source gene order"):
                    make_report()
