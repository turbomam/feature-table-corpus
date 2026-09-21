"""Source fidelity and scope controls for real files and labeled parser fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from source_document import parse_bytes, replay_bytes
from validate_closed import make_validator

PRODIGAL = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff"
REFSEQ = ROOT / "corpus/sources/ncbi-refseq/ncbi_refseq_phix174_GCF_000819615.1.gff"
FIXTURE = ROOT / "tests/fixtures/source-documents/mixed-records.gff3"
SCRIPT = ROOT / "scripts/source_document.py"


def values(record):
    return {a["key"]: a["value"] for a in record["metadata"]}


class SourceDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = make_validator(ROOT / "model/schema/source_document.yaml", "SourceDocument")

    def parse(self, content, **options):
        doc = parse_bytes(content, source_uri="https://example.org/input.gff", **options)
        self.assertEqual(list(self.validator.iter_errors(doc)), [])
        self.assertEqual(replay_bytes(json.loads(json.dumps(doc))), content)
        return doc

    def test_all_real_gff_and_gtf_sources_round_trip_and_keep_every_feature(self):
        paths = list((ROOT / "corpus/sources/nmdc").glob("*.gff"))
        paths += list((ROOT / "corpus/sources/ncbi-refseq").glob("*.gff"))
        paths += list((ROOT / "corpus/sources/ncbi-refseq").glob("*.gtf"))
        self.assertEqual(len(paths), 18)
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                profile = "prodigal" if path == PRODIGAL else "ncbi" if path.parent.name == "ncbi-refseq" else "generic"
                doc = self.parse(original, format="gtf" if path.suffix == ".gtf" else "gff3", profile=profile)
                rows = [r for r in doc["records"] if r["kind"] == "feature"]
                expected = [line.decode().split("\t") for line in original.splitlines()
                            if line and not line.startswith(b"#")]
                self.assertEqual([r["feature_columns"] for r in rows], expected)
                self.assertFalse(any(r.get("warnings") for r in doc["records"]))
                self.assertEqual(path.read_bytes(), original)

    def test_prodigal_lengths_and_prediction_settings_keep_sequence_scope(self):
        doc = self.parse(PRODIGAL.read_bytes(), format="gff3", profile="prodigal")
        sequences = [r for r in doc["records"] if r.get("metadata_type") == "prodigal-sequence"]
        models = [r for r in doc["records"] if r.get("metadata_type") == "prodigal-model"]
        self.assertEqual([values(r)["seqlen"] for r in sequences], ["359", "303", "298", "298", "295"])
        self.assertEqual([values(r)["transl_table"] for r in models], ["4", "11", "11", "11", "11"])
        self.assertEqual([r["line_number"] for r in sequences], [2, 5, 8, 12, 15])
        self.assertEqual([r["context_record"] for r in models], [r["record_id"] for r in sequences])
        for sequence, model, feature_count in zip(sequences, models, (1, 1, 2, 1, 1)):
            self.assertEqual(model["scope"], "sequence")
            self.assertEqual(model["sequence_id"], sequence["sequence_id"])
            rows = [r for r in doc["records"] if r["kind"] == "feature"
                    and r.get("context_record") == sequence["record_id"]]
            self.assertEqual(len(rows), feature_count)
            self.assertEqual({r["sequence_id"] for r in rows}, {sequence["sequence_id"]})
        self.assertNotIn("taxonomic_lineage", json.dumps(doc))

    def test_profiles_are_explicit_and_ncbi_gtf_metadata_is_supported(self):
        generic = self.parse(REFSEQ.read_bytes(), format="gff3")
        ncbi = self.parse(REFSEQ.read_bytes(), format="gff3", profile="ncbi")
        self.assertEqual(generic["records"][2]["scope"], "stream")
        self.assertNotIn("metadata", generic["records"][2])
        self.assertEqual(ncbi["records"][2]["scope"], "document")
        self.assertEqual(values(ncbi["records"][2]), {"processor": "NCBI annotwriter"})
        self.assertEqual(ncbi["records"][-1]["kind"], "boundary")
        gtf = self.parse(REFSEQ.with_suffix(".gtf").read_bytes(), format="gtf", profile="ncbi")
        self.assertEqual(values(gtf["records"][0]), {"gtf-version": "2.2"})
        self.assertIn('gene_id "phiX174p04";', gtf["records"][3]["feature_columns"][8])
        with self.assertRaisesRegex(ValueError, "requires GFF3"):
            parse_bytes(b"", source_uri="https://example.org/a", format="gtf", profile="prodigal")

    def test_derived_mixed_records_keep_repeats_unknowns_boundaries_and_fasta(self):
        doc = self.parse(FIXTURE.read_bytes(), format="gff3")
        records = doc["records"]
        unknown = [r for r in records if r.get("metadata_type") == "unknown-producer-setting"]
        self.assertEqual(len(unknown), 2)
        self.assertTrue(all(r["scope"] == "stream" and "metadata" not in r for r in unknown))
        ontologies = [r for r in records if r.get("metadata_type") == "feature-ontology"]
        self.assertEqual([values(r)["feature-ontology"] for r in ontologies],
                         ["https://example.org/ontology/first", "https://example.org/ontology/second"])
        region = next(r for r in records if r.get("metadata_type") == "sequence-region")
        self.assertEqual(values(region), {"seqid": "NC_001422.1", "start": "2", "end": "4"})
        self.assertNotIn("length", json.dumps(region))
        self.assertEqual([r["kind"] for r in records[-5:]],
                         ["boundary", "fasta_start", "fasta_header", "fasta_sequence", "fasta_sequence"])
        self.assertEqual("".join(r.get("sequence_text", "") for r in records), "ACGTNN")
        self.assertTrue(all(r["context_record"] == records[-3]["record_id"] for r in records[-2:]))

    def test_headerless_files_have_no_invented_metadata(self):
        path = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-bvg4py20.1_crt.gff"
        doc = self.parse(path.read_bytes(), format="gff3")
        self.assertTrue(all(r["kind"] == "feature" for r in doc["records"]))
        self.assertTrue(all("metadata" not in r and "context_record" not in r for r in doc["records"]))

    def test_exact_bytes_include_mixed_line_endings_bom_and_missing_final_newline(self):
        content = '\ufeff##gff-version 3\r\n# café\r\t\n# a\u2028b'.encode()
        doc = self.parse(content, format="gff3")
        self.assertEqual([r["line_number"] for r in doc["records"]], [1, 2, 3, 4])
        self.assertEqual([r["kind"] for r in doc["records"]], ["directive", "comment", "blank", "comment"])
        self.parse(b"", format="gff3")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            parse_bytes(b"# \xff\n", source_uri="https://example.org/a", format="gff3")

    def test_repeated_sequence_names_and_quoted_delimiters_keep_distinct_contexts(self):
        content = b'''# Sequence Data: seqnum=1;seqlen=4;seqhdr="same description;with=delimiters";extra=one;extra=two
# Model Data: transl_table=4
same\ttest\tCDS\t1\t4\t.\t+\t0\tID=first
# Sequence Data: seqnum=2;seqlen=6;seqhdr="same other description"
# Model Data: transl_table=11
same\ttest\tCDS\t1\t6\t.\t+\t0\tID=second
'''
        doc = self.parse(content, format="gff3", profile="prodigal")
        records = doc["records"]
        self.assertEqual(values(records[0])["seqhdr"], '"same description;with=delimiters"')
        self.assertEqual([a["value"] for a in records[0]["metadata"] if a["key"] == "extra"], ["one", "two"])
        self.assertEqual(records[2]["context_record"], "line-1")
        self.assertEqual(records[5]["context_record"], "line-4")
        self.assertEqual(records[2]["sequence_id"], records[5]["sequence_id"])

    def test_malformed_headers_mismatched_rows_and_boundaries_do_not_leak_context(self):
        header = '# Sequence Data: seqnum=1;seqlen=4;seqhdr="first"\n'
        for separator in ('###\n', '# Sequence Data: seqnum=2;seqlen=4;seqhdr="unterminated\n',
                          '# Sequence Data: seqnum=2;seqlen=bad;seqhdr="second"\n',
                          'other\ttest\tCDS\t1\t4\t.\t+\t0\tID=other\n'):
            with self.subTest(separator=separator):
                doc = self.parse((header + separator + '# Model Data: transl_table=11\n').encode(),
                                 format="gff3", profile="prodigal")
                model = doc["records"][-1]
                self.assertEqual(model["scope"], "stream")
                self.assertNotIn("context_record", model)
                self.assertTrue(model["warnings"])

    def test_fasta_is_a_one_way_transition_and_headers_have_independent_contexts(self):
        doc = self.parse(b'##FASTA \t\r\n>same first\nACGT\n>same second\nNN\n# no longer a comment\n', format="gff3")
        records = doc["records"]
        self.assertEqual(records[2]["context_record"], "line-2")
        self.assertEqual(records[4]["context_record"], "line-4")
        self.assertEqual(records[-1]["kind"], "unparsed")
        self.assertTrue(records[-1]["warnings"])
        implicit = self.parse(b'>seq\nACGT', format="gff3")
        self.assertEqual(implicit["records"][0]["kind"], "fasta_header")
        self.assertEqual(implicit["records"][1]["sequence_text"], "ACGT")
        gtf = self.parse(b'##FASTA\n>seq\nACGT', format="gtf")
        self.assertEqual([r["kind"] for r in gtf["records"]], ["directive", "unparsed", "unparsed"])
        malformed = self.parse(b'##FASTA\nACGT\n>\nNN', format="gff3")
        self.assertTrue(all(r.get("warnings") for r in malformed["records"][1:]))

    def test_bad_directive_payloads_and_unrecognized_rows_remain_visible(self):
        doc = self.parse(b'##species\n##sequence-region seq 9 2\n##sequence-region seq 0 8\nnot\ta\tfeature\n', format="gff3")
        self.assertEqual(len(doc["records"]), 4)
        self.assertTrue(all(r["warnings"] for r in doc["records"]))
        self.assertTrue(all(r["scope"] == "stream" for r in doc["records"]))

    def test_integrity_checks_reject_corrupted_source_and_interpretations(self):
        original = self.parse(PRODIGAL.read_bytes(), format="gff3", profile="prodigal")
        changes = (
            lambda d: d["artifact"].update(sha256="0" * 64),
            lambda d: d["artifact"].update(byte_size=0),
            lambda d: d["records"].reverse(),
            lambda d: d["records"][0].update(raw_text="##gff-version 4\n"),
            lambda d: d["records"][0].update(line_number=99),
            lambda d: d["records"][2].update(scope="document"),
            lambda d: d["records"][2].update(context_record="line-999"),
            lambda d: d["records"][2]["metadata"][0].update(value="changed"),
        )
        for change in changes:
            with self.subTest(change=change):
                doc = copy.deepcopy(original)
                change(doc)
                with self.assertRaises(ValueError):
                    replay_bytes(doc)
        for invalid in (None, [], {}, {"records": [None]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                replay_bytes(invalid)
        bad_shape = copy.deepcopy(original)
        bad_shape["records"][3]["feature_columns"].pop()
        self.assertTrue(list(self.validator.iter_errors(bad_shape)))

    def test_independent_original_rejects_consistent_rewrites(self):
        original = b"# original annotation\n"
        changed = b"# changed annotation\n"
        document = self.parse(original, format="gff3")
        rewritten = self.parse(changed, format="gff3")
        self.assertEqual(replay_bytes(document, original_bytes=original), original)
        # Updating raw text, digest, size, and projection together stays internally consistent.
        self.assertEqual(replay_bytes(rewritten), changed)
        for retained in (original, b""):
            with self.subTest(retained=retained), self.assertRaisesRegex(ValueError, "supplied original"):
                replay_bytes(rewritten, original_bytes=retained)
        self.assertEqual(replay_bytes(self.parse(b"", format="gff3"), original_bytes=b""), b"")

    def test_cli_round_trip_strict_diagnostics_and_refusal_to_overwrite(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            work = Path(directory)
            instance, replay = work / "document.json", work / "replay.gff"
            command = [sys.executable, str(SCRIPT)]
            def run(*args):
                return subprocess.run(command + list(map(str, args)), capture_output=True, text=True)
            result = run("parse", PRODIGAL, "--format", "gff3", "--profile", "prodigal", "--output", instance)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(run("validate", instance).returncode, 0)
            self.assertEqual(run("validate", instance, "--original", PRODIGAL).returncode, 0)
            self.assertEqual(run("validate", instance, "--original", REFSEQ).returncode, 2)
            rejected = work / "rejected.gff"
            result = run("replay", instance, "--original", REFSEQ, "--output", rejected)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("supplied original", result.stderr)
            self.assertFalse(rejected.exists())
            result = run("replay", instance, "--original", PRODIGAL, "--output", replay)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(replay.read_bytes(), PRODIGAL.read_bytes())
            self.assertEqual(run("replay", instance, "--output", replay).returncode, 2)
            self.assertEqual(replay.read_bytes(), PRODIGAL.read_bytes())
            malformed = work / "malformed.gff"
            malformed.write_bytes(b"unrecognized data\n")
            result = run("parse", malformed, "--format", "gff3", "--strict")
            self.assertEqual(result.returncode, 1)
            self.assertIn("line 1", result.stderr)
            self.assertEqual(json.loads(result.stdout)["records"][0]["raw_text"], "unrecognized data\n")
            self.assertEqual(run("parse", malformed, "--format", "gff3", "--output", malformed).returncode, 2)
            self.assertEqual(malformed.read_bytes(), b"unrecognized data\n")

    def test_checked_in_example_reproduces_from_its_vendored_source(self):
        path = ROOT / "model/examples/source-documents/prodigal.json"
        document = json.loads(path.read_text())
        expected = parse_bytes(PRODIGAL.read_bytes(), source_uri=document["artifact"]["uri"],
                               format="gff3", profile="prodigal")
        self.assertEqual(document, expected)
        self.assertEqual(list(self.validator.iter_errors(document)), [])


if __name__ == "__main__":
    unittest.main()
