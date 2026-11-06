"""The GFF3 loader and cross-record plugin, run through LinkML's own Validator and linkml-validate.

The negative controls in corpus/fixtures/malformed/ derive from phiX174, whose region row
carries Is_circular=true, so the gff3-contig profile refuses them before any plugin runs. The
cross-record checks are therefore exercised on single-change copies of the linear MS2 file,
made in a temporary directory the same way scripts/make_malformed.py makes its fixtures.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin
from linkml.validator.report import Severity
from linkml_cross_record_plugin import CrossRecordPlugin
from linkml_gff3_loader import Gff3ConversionRefused, Gff3Loader

SCHEMA = ROOT / "model/schema/ber_feature_model.yaml"
MS2 = ROOT / "corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3"
MALFORMED = ROOT / "corpus/fixtures/malformed"


class LinkmlGffValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = Validator(str(SCHEMA), validation_plugins=[
            JsonschemaValidationPlugin(closed=True), CrossRecordPlugin()])
        cls.lines = MS2.read_text().splitlines(keepends=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def derived(self, name, old, new, *, extra=""):
        """MS2 with exactly one data row changed (old to new), or one row appended."""
        lines = list(self.lines)
        if old:
            matches = [i for i, line in enumerate(lines) if old in line and not line.startswith("#")]
            self.assertEqual(len(matches), 1, old)
            lines[matches[0]] = lines[matches[0]].replace(old, new)
        path = Path(self.temp.name) / f"{name}.gff3"
        path.write_text("".join(lines) + extra)
        return path

    def messages(self, path, metadata_profile="ncbi"):
        report = self.validator.validate_source(
            Gff3Loader(str(path), reference_context="NC_001417.2", metadata_profile=metadata_profile), "Dataset")
        return [(r.severity, r.message) for r in report.results]

    def test_valid_file_has_no_results(self):
        self.assertEqual(self.messages(MS2), [])

    def test_loader_yields_one_dataset_with_contig_length(self):
        dataset, = Gff3Loader(str(MS2), reference_context="NC_001417.2", metadata_profile="ncbi").iter_instances()
        self.assertEqual(dataset["contigs"], [{"contig_id": "NC_001417.2", "length_bp": 3569}])
        self.assertGreater(len(dataset["features"]), 1)

    def test_unreadable_or_non_utf8_input_gives_a_clean_error(self):
        import click
        not_utf8 = Path(self.temp.name, "latin1.gff3")
        not_utf8.write_bytes(b"##gff-version 3\nc1\tsrc\tgene\t1\t9\t.\t+\t.\tID=g\xe91\n")
        for path in (not_utf8, Path(self.temp.name, "missing.gff3")):
            with self.subTest(path.name), self.assertRaises(click.ClickException) as caught:
                list(Gff3Loader(str(path), reference_context="example:c1").iter_instances())
            self.assertNotIsInstance(caught.exception, Gff3ConversionRefused)
            self.assertIn(path.name, caught.exception.format_message())

    def test_circular_malformed_fixtures_are_refused_by_conversion(self):
        for name in ("dangling_parent.gff3", "duplicate_id.gff3"):
            with self.subTest(name), self.assertRaises(Gff3ConversionRefused) as caught:
                self.messages(MALFORMED / name)
            self.assertEqual(caught.exception.code, "circular-location")
            self.assertIn(name, caught.exception.format_message())

    def test_cross_record_errors(self):
        cases = {
            "unknown parent": (self.derived("dangling", "Parent=gene-MS2g1;", "Parent=gene-DOES-NOT-EXIST;"),
                               "feature 'cds-YP_009640124.1': unknown parent 'gene-DOES-NOT-EXIST'"),
            "duplicate ID": (self.derived("duplicate", "ID=cds-YP_009640126.1;", "ID=gene-MS2g1;"),
                             "features: duplicate feature_id 'gene-MS2g1'"),
            "parent cycle": (self.derived("cycle", "ID=gene-MS2g1;", "ID=gene-MS2g1;Parent=cds-YP_009640124.1;"),
                             "features: parent cycle involving 'gene-MS2g1'"),
            "other contig": (self.derived("other_contig", None, None, extra="OTHER.1\tRefSeq\tgene\t1\t10\t.\t+\t.\t"
                                          "ID=gene-other;Parent=gene-MS2g1\n"),
                             "feature 'gene-other': parent 'gene-MS2g1' is on a different contig"),
        }
        for label, (path, expected) in cases.items():
            with self.subTest(label):
                results = self.messages(path)
                self.assertIn((Severity.ERROR, expected), results)
                self.assertTrue(all(severity == Severity.ERROR for severity, _ in results), results)

    def test_end_beyond_length_is_refused_in_gff_and_reported_for_a_dataset(self):
        # Under the ncbi profile length_bp comes from ##sequence-region, and conversion refuses a
        # row outside a declared region, so through GFF3 this check is never reached.
        path = self.derived("past_end", "gene\t1678\t1905\t", "gene\t1678\t4000\t")
        with self.assertRaises(Gff3ConversionRefused) as caught:
            self.messages(path)
        self.assertEqual(caught.exception.code, "declared-region")
        dataset, = Gff3Loader(str(MS2), reference_context="NC_001417.2", metadata_profile="ncbi").iter_instances()
        dataset["features"][-1]["end"] = 4000
        results = [(r.severity, r.message) for r in self.validator.validate(dataset, "Dataset").results]
        self.assertIn(Severity.ERROR, {severity for severity, _ in results})
        self.assertTrue(any(message.endswith("end exceeds contig length_bp") for _, message in results), results)

    def test_wrong_shape_skips_cross_record_checks(self):
        results = self.validator.validate({"features": [{"feature_id": "x"}]}, "Dataset").results
        by_type = {r.type: r for r in results}
        self.assertEqual(by_type["ber_feature_model cross-record"].severity, Severity.INFO)
        self.assertIn("jsonschema validation", by_type)

    def run_cli(self, path, *positional):
        config = Path(self.temp.name) / "config.yaml"
        config.write_text(yaml.safe_dump({
            "schema": str(SCHEMA), "target_class": "Dataset",
            "data_sources": [{"linkml_gff3_loader.Gff3Loader": {
                "source": str(path), "reference_context": "NC_001417.2", "metadata_profile": "ncbi"}}],
            "plugins": {"JsonschemaValidationPlugin": {"closed": True},
                        "linkml_cross_record_plugin.CrossRecordPlugin": None}}))
        return subprocess.run([sys.executable, "-m", "linkml.validator.cli", "--config", str(config), *positional],
                              cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "scripts")},
                              capture_output=True, text=True)

    def test_linkml_validate_command_line(self):
        path = self.derived("dangling", "Parent=gene-MS2g1;", "Parent=gene-DOES-NOT-EXIST;")
        result = self.run_cli(path, str(path))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("[ERROR] [", result.stdout)
        self.assertIn("unknown parent 'gene-DOES-NOT-EXIST'", result.stdout)
        valid = self.run_cli(MS2, str(MS2))
        self.assertEqual((valid.returncode, valid.stdout.strip()), (0, "No issues found"), valid.stderr)
        refused = self.run_cli(MALFORMED / "dangling_parent.gff3", str(MALFORMED / "dangling_parent.gff3"))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("[circular-location]", refused.stderr)

    def test_linkml_validate_without_a_positional_source_validates_nothing(self):
        # linkml 1.11.1 validator/cli.py: Config.data_sources (line 22) is an Iterable, which
        # pydantic 2 stores as a one-pass iterator, and line 252 consumes it with list() when no
        # positional source is given. This test fails once LinkML fixes that; the justfile recipe
        # validate-gff3-linkml can then drop its positional argument.
        path = self.derived("dangling", "Parent=gene-MS2g1;", "Parent=gene-DOES-NOT-EXIST;")
        result = self.run_cli(path)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "No issues found"), result.stderr)


if __name__ == "__main__":
    unittest.main()
