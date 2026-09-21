"""Independent expected values, generated round-trip laws, and refusal controls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from convert_features import (ConversionError, PROFILES, export_source, import_source,
                              reconstruct_record, validate_bundle)
from source_document import parse_bytes
from validate_closed import make_validator, validation_errors
from build_duckdb import build_database
from query_duckdb import by_attribute, interval_overlap
import conversion_report

GFF = "gff3-contig/1.0.0"
BED = "bed12-blocks/1.0.0"
PRODIGAL = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff"
BED_SOURCE = ROOT / "corpus/sources/biopython/blat_34_hg19.bed"


def bundle(content, profile=GFF, **kwargs):
    return import_source(content, profile=profile, reference_context="test:reference",
                         source_uri="https://example.org/source", **kwargs)


class ConversionTests(unittest.TestCase):
    def assert_roundtrip(self, content, profile=GFF, **kwargs):
        original = bundle(content, profile, **kwargs)
        self.assertEqual(export_source(original, mode="exact", original_bytes=content), content)
        reconstructed = export_source(original, mode="reconstruct")
        again = bundle(reconstructed, profile, **kwargs)
        self.assertEqual(again["dataset"], original["dataset"])
        self.assertEqual(again["mappings"], original["mappings"])
        # Interpreted metadata scopes/contexts must survive, too. Raw lexical
        # feature columns and content hashes are intentionally not this claim.
        nonfeatures = lambda b: [r for r in b["source"]["records"] if r["kind"] != "feature"]
        self.assertEqual(nonfeatures(again), nonfeatures(original))
        return original

    def assert_rejects(self, content, code, profile=GFF):
        with self.assertRaises(ConversionError) as result:
            bundle(content, profile)
        self.assertEqual(result.exception.code, code)

    def test_real_prodigal_metadata_and_native_ids(self):
        b = self.assert_roundtrip(PRODIGAL.read_bytes(), metadata_profile="prodigal")
        rows = b["dataset"]["features"]
        self.assertEqual(len(rows), 6)
        self.assertEqual((rows[0]["start"], rows[0]["end"], rows[0]["strand"], rows[0]["phase"]),
                         (3, 359, "-", 0))
        self.assertEqual(rows[0]["score"], 3.1)
        self.assertEqual(rows[0]["attributes"][-2:], [{"key": "partial", "value": "5'"},
                                                      {"key": "partial", "value": "3'"}])
        contexts = [r for r in b["source"]["records"] if r.get("metadata_type") == "prodigal-model"]
        self.assertEqual(len(contexts), 5)
        self.assertEqual([next(a["value"] for a in r["metadata"] if a["key"] == "transl_table")
                          for r in contexts], ["4", "11", "11", "11", "11"])
        self.assertTrue(all(r["scope"] == "sequence" and r["context_record"] for r in contexts))

    def test_real_bed_blocks_keep_coordinates_order_and_display_fields(self):
        b = self.assert_roundtrip(BED_SOURCE.read_bytes(), BED)
        self.assertEqual(len(b["mappings"]), 19)
        self.assertEqual(len(b["dataset"]["features"]), 42)
        mapping = b["mappings"][4]
        by_id = {f["feature_id"]: f for f in b["dataset"]["features"]}
        parent, first, second = [by_id[i] for i in mapping["feature_ids"]]
        self.assertEqual((parent["start"], parent["end"]), (35483341, 35483510))
        self.assertEqual((first["start"], first["end"]), (35483341, 35483365))
        self.assertEqual((second["start"], second["end"]), (35483500, 35483510))
        self.assertEqual(second["parent"], [parent["feature_id"]])
        self.assertEqual(parent["score"], 890)
        self.assertIn({"key": "bed:name", "value": "hg19_dna"}, parent["attributes"])
        validator = make_validator(ROOT / "model/schema/source_document.yaml", "SourceDocument")
        self.assertEqual(validation_errors(b["source"], validator, "SourceDocument"), [])
        for chrom in (b"track", b"browser"):
            # A reference named like a header keyword is still a twelve-column row.
            self.assert_roundtrip(chrom + b"\t0\t1\tx\t0\t+\t0\t1\t0\t1\t1\t0\n", BED)

    def test_checked_in_bundle_reproduces_from_retained_bed(self):
        path = ROOT / "model/examples/conversions/blat-bed12.json"
        document = json.loads(path.read_text())
        expected = import_source(BED_SOURCE.read_bytes(), profile=document["profile"],
                                 reference_context=document["reference_context"],
                                 source_uri=document["source"]["artifact"]["uri"])
        self.assertEqual(document, expected)
        self.assertEqual(export_source(document, mode="exact", original_bytes=BED_SOURCE.read_bytes()),
                         BED_SOURCE.read_bytes())

    def test_reconstruction_uses_mapped_fields_without_original_feature_text(self):
        content = b"ctg%201\t%2E\tgene\t0001\t0010\t1e1\t?\t.\tID=g%201;Note=a%3bb,,c;Note=;product=hello%20world;\r\n"
        b = self.assert_roundtrip(content)
        feature = b["dataset"]["features"][0]
        self.assertEqual(feature["seqid"], "ctg 1")
        self.assertEqual(feature["feature_id"], "g 1")
        self.assertEqual(feature["product"], "hello world")
        self.assertEqual([a["value"] for a in feature["attributes"] if a["key"] == "Note"],
                         ["a;b", "", "c", ""])
        # This API cannot access an opaque retained source: only Dataset fields
        # and nonlexical grouping/identity metadata are passed to it.
        columns = reconstruct_record(GFF, {feature["feature_id"]: feature}, b["mappings"][0])
        self.assertEqual(columns[:6], ["ctg%201", "%2E", "gene", "1", "10", "10.0"])
        self.assertIn("product=hello%20world", columns[8])
        self.assertNotEqual(export_source(b, mode="reconstruct"), content)
        feature["product"] = "conflicting edit"
        with self.assertRaisesRegex(ConversionError, "generic product"):
            reconstruct_record(GFF, {feature["feature_id"]: feature}, b["mappings"][0])

    def test_forward_multiple_parents_missing_ids_and_empty_source_values(self):
        content = (b"c\t\texon\t1\t2\t.\t+\t.\tParent=a,b;Note=\n"
                   b"c\t.\tgene\t1\t3\t.\t+\t.\tID=a\n"
                   b"c\t.\tgene\t1\t4\t.\t+\t.\tID=b\n")
        b = self.assert_roundtrip(content)
        row = b["dataset"]["features"][0]
        self.assertEqual(row["parent"], ["a", "b"])
        self.assertEqual(row["feature_id"], "urn:ftc:line-1")
        self.assertEqual(row["source"], "")
        self.assertNotIn("source", b["dataset"]["features"][1])
        self.assertNotIn(b"ID=urn", export_source(b, mode="reconstruct"))

    def test_generated_gff_domain_with_metadata_escaping_endings_and_boundaries(self):
        rng = random.Random(16)
        for i in range(60):
            with self.subTest(case=i):
                start = rng.choice([1, 2, 1000000])
                end = start + rng.randrange(0, 20)
                ending = rng.choice(["\n", "\r", "\r\n"])
                attr = rng.choice([".", "", "Note=;Note=a%2Cb,,x;unknown_key=v%3Bz;", "ID=f;product=p%25q"])
                row = f"c\t.\tgene\t{start:08}\t{end}\t{rng.choice(['.', '1e1', '-0.0', '0.125'])}\t{rng.choice(['+', '-', '.', '?'])}\t.\t{attr}"
                content = ("\ufeff##gff-version 3" + ending + "##mystery repeated" + ending
                           + "##mystery repeated" + ending + row + (ending if i % 2 else ""))
                self.assert_roundtrip(content.encode())
        self.assert_roundtrip(b"##gff-version 3\n##sequence-region c 1 3\nc\t.\tgene\t1\t3\t.\t+\t.\tID=g\n###\n##FASTA\n>c\nACT\n")

    def test_generated_bed_domain_and_literal_optional_fields(self):
        rng = random.Random(17)
        for i in range(60):
            with self.subTest(case=i):
                start = rng.choice([0, 1, 1000000])
                sizes = [rng.randrange(1, 12) for _ in range(rng.randrange(1, 5))]
                starts, pos = [], 0
                for size in sizes:
                    starts.append(pos)
                    pos += size + rng.randrange(0, 10)
                end = start + starts[-1] + sizes[-1]
                suffix = "," if i % 2 else ""
                row = f"chr1\t{start:06}\t{end}\tname with spaces\t{rng.randrange(1001)}\t{rng.choice(['+', '-', '.'])}\t{start}\t{start}\t255,0,10\t{len(sizes)}\t"
                row += ",".join(map(str, sizes)) + suffix + "\t" + ",".join(map(str, starts)) + suffix
                ending = rng.choice(["\n", "\r\n", "\r"])
                content = ("track name=demo" + ending + "browser position chr1:1-100" + ending
                           + "# unknown metadata" + ending + row + (ending if i % 3 else "")).encode()
                b = self.assert_roundtrip(content, BED)
                self.assertEqual(b["dataset"]["features"][0]["start"], start + 1)

    def test_out_of_profile_gff_constructs_have_specific_failures(self):
        row = b"c\t.\tgene\t1\t5\t.\t+\t.\tID=x\n"
        for content, code in [
            (row + row, "dataset-invalid"),
            (row.replace(b"ID=x", b"ID=x;Is_circular=true"), "circular-location"),
            (row.replace(b"ID=x", b"ID=x;Parent=missing"), "dataset-invalid"),
            (row.replace(b"ID=x", b"ID=x;Parent=x"), "dataset-invalid"),
            (row.replace(b"ID=x", b"ID=x,y"), "identifier-cardinality"),
            (row.replace(b"ID=x", b"product=a,b"), "product-cardinality"),
            (row.replace(b"ID=x", b"Note=%xx"), "invalid-escape"),
            (row.replace(b"ID=x", b"bare_attribute"), "attribute-syntax"),
            (row.replace(b"\tgene\t", b"\tCDS\t"), "phase-domain"),
            (row.replace(b"\t5\t.\t", b"\t5\t0.12345678901234567890\t"), "score-precision"),
            (row.replace(b"\t5\t.\t", b"\t5\t1e309\t"), "score-precision"),
            (row.replace(b"\t5\t.\t", b"\t5\tNaN\t"), "score-domain"),
            (row.replace(b"\t1\t5\t", b"\t0\t5\t"), "coordinate-domain"),
            (b"##sequence-region c 1 4\n" + row, "declared-region"),
            (b"##gff-version 2\n" + row, "format-version"),
            (b"not nine columns\n", "source-syntax"),
        ]:
            with self.subTest(code=code, content=content):
                self.assert_rejects(content, code)
        inconsistent = PRODIGAL.read_bytes().replace(b"seqlen=359", b"seqlen=10")
        with self.assertRaises(ConversionError) as result:
            bundle(inconsistent, metadata_profile="prodigal")
        self.assertEqual(result.exception.code, "sequence-length")

    def test_out_of_profile_bed_constructs_have_specific_failures(self):
        for content, code in [
            (b"c\t0\t0\tx\t0\t+\t0\t0\t0\t1\t0\t0\n", "empty-interval"),
            (b"c\t0\t5\tx\t0\t+\t0\t5\t0\t2\t4,3\t0,2\n", "block-order"),
            (b"c\t0\t5\tx\t0\t+\t0\t5\t0\t2\t5\t0\n", "block-count"),
            (b"c\t0\t5\tx\t0\t+\t0\t6\t0\t1\t5\t0\n", "thick-bounds"),
            (b"c\t0\t5\tx\t1001\t+\t0\t5\t0\t1\t5\t0\n", "bed-domain"),
            (b"c\t0\t5\tx\t0\t+\t0\t5\t300,0,0\t1\t5\t0\n", "rgb-domain"),
            (b"c\t0\t5\tx\t0\t+\n", "source-syntax"),
        ]:
            with self.subTest(code=code):
                self.assert_rejects(content, code, BED)

    def test_all_edits_are_refused_in_both_export_modes(self):
        original = bundle(PRODIGAL.read_bytes(), metadata_profile="prodigal")
        mutations = [
            lambda b: b["dataset"]["features"][0].update(start=4),
            lambda b: b["dataset"]["features"][0]["attributes"].append({"key": "new", "value": "v"}),
            lambda b: b["dataset"]["contigs"][0].update(length_bp=100000),
            lambda b: b["mappings"][0].update(source_has_id=False),
            lambda b: b["source"]["records"][1].update(scope="stream"),
            lambda b: b.update(unknown_extension="cannot silently drop this"),
            lambda b: b.update(conversion_version=2),
        ]
        for mutate in mutations:
            for mode in ("exact", "reconstruct"):
                b = deepcopy(original)
                mutate(b)
                with self.subTest(mutation=mutate, mode=mode), self.assertRaises(ValueError):
                    export_source(b, mode=mode)
        for profile in PROFILES:
            with self.assertRaises(ConversionError):
                import_source(b"", profile=profile, reference_context="", source_uri="urn:source")
        self.assert_rejects(b"", "unsupported-profile", "gtf/1.0.0")
        with self.assertRaises(ConversionError) as result:
            import_source(PRODIGAL.read_bytes(), profile=GFF, reference_context="test",
                          source_uri="not a URI")
        self.assertEqual(result.exception.code, "source-invalid")

    def test_common_interval_and_attribute_queries_work_for_both_profiles(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            for source, profile, key, value in [(PRODIGAL, GFF, "translation_table", "4"),
                                                (BED_SOURCE, BED, "bed:role", "block")]:
                converted = bundle(source.read_bytes(), profile)
                dataset = Path(temp) / (source.stem + ".json")
                dataset.write_text(json.dumps(converted["dataset"]))
                database = dataset.with_suffix(".duckdb")
                build_database(ROOT / "model/schema/ber_feature_model.yaml", dataset, database)
                with duckdb.connect(str(database), read_only=True) as connection:
                    self.assertTrue(by_attribute(connection, key, value))
                    first = converted["dataset"]["features"][0]
                    found = interval_overlap(connection, first["seqid"], first["start"], first["start"])
                    self.assertIn(first["feature_id"], [r[0] for r in found])
                    if profile == BED:
                        # The gap between two BED blocks overlaps the enclosing
                        # record, but does not become a covered block.
                        gap = interval_overlap(connection, "chr19", 35483366, 35483499)
                        self.assertEqual([r[0] for r in gap], ["bed:line-5"])

    def test_report_fails_on_unexpected_adapter_failure_and_inspects_insdc(self):
        with patch.object(conversion_report, "import_source", side_effect=ConversionError("broken", "negative control")):
            with self.assertRaises(ConversionError) as result:
                conversion_report.make_report()
        self.assertEqual(result.exception.code, "unexpected-outcome")
        observations = conversion_report.insdc_observations((ROOT / "corpus/sources/biopython/cor6_6.gb").read_bytes())
        self.assertEqual(len(observations["accession_versions"]), 6)
        self.assertEqual(observations["join_location_lines"], 6)
        self.assertEqual(observations["partial_location_lines"], 7)
        self.assertEqual(observations["repeated_qualifier_keys_within_features"], 2)

    def test_cli_roundtrip_no_overwrite_and_failed_validation_writes_nothing(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            output, restored = Path(temp) / "bundle.json", Path(temp) / "restored.gff"
            def run(*args, status=0):
                result = subprocess.run([sys.executable, str(ROOT / "scripts/convert_features.py"), *map(str, args)],
                                        capture_output=True, text=True, env={**os.environ, "UV_OFFLINE": "1"})
                self.assertEqual(result.returncode, status, result.stderr)
                return result
            command = ("import", PRODIGAL, "--profile", GFF, "--reference-context", "NMDC test",
                       "--metadata-profile", "prodigal", "--output", output)
            run(*command)
            run(*command, status=2)
            run("export", output, "--mode", "exact", "--original", PRODIGAL, "--output", restored)
            self.assertEqual(restored.read_bytes(), PRODIGAL.read_bytes())
            run("export", output, "--mode", "exact", "--output", restored, status=2)
            changed = json.loads(output.read_text())
            changed["dataset"]["features"][0]["end"] -= 1
            output.write_text(json.dumps(changed))
            target = Path(temp) / "rejected.gff"
            result = run("export", output, "--mode", "reconstruct", "--output", target, status=2)
            self.assertEqual(json.loads(result.stderr)["code"], "edited-bundle")
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
