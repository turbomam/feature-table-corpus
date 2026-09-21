"""Exercise real CLI boundaries: literal arguments, source fidelity, and failures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

import test_nmdc_profile as nmdc_fixture

ROOT = Path(__file__).resolve().parents[1]
PRODIGAL = ROOT / "corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff"


@unittest.skipUnless(shutil.which("just"), "install just to exercise task launchers")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="just tasks ", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def run_recipe(self, *args, status=0):
        result = subprocess.run(["just", *map(str, args)], cwd=ROOT,
                                env={**os.environ, "UV_OFFLINE": "1"},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return result.stdout

    def test_source_round_trip_literal_paths_options_and_failure_statuses(self):
        original = self.work / "source 'quoted' $(echo literal).gff"
        original.write_bytes(PRODIGAL.read_bytes())
        document = self.work / "parsed 'document'.json"
        replay = self.work / "replayed source.gff"
        uri = "https://example.org/source?first=1&second=2"
        self.run_recipe("source-parse", original, "gff3", document,
                        "--profile", "prodigal", "--source-uri", uri)
        parsed = json.loads(document.read_text())
        self.assertEqual(parsed["artifact"]["uri"], uri)
        self.assertEqual(parsed["profile"], "prodigal")
        self.run_recipe("source-validate", document, "--original", original)
        self.run_recipe("source-replay", document, replay, "--original", original)
        self.assertEqual(replay.read_bytes(), original.read_bytes())
        self.run_recipe("source-replay", document, replay, status=2)
        self.assertEqual(replay.read_bytes(), original.read_bytes())

        wrong = self.work / "different original.gff"
        wrong.write_bytes(b"# different source\n")
        self.run_recipe("source-validate", document, "--original", wrong, status=2)
        rejected = self.work / "rejected output.gff"
        self.run_recipe("source-replay", document, rejected, "--original", wrong, status=2)
        self.assertFalse(rejected.exists())
        malformed = self.work / "malformed.gff"
        malformed.write_bytes(b"unrecognized data\n")
        strict_output = self.work / "strict output.json"
        self.run_recipe("source-parse", malformed, "gff3", strict_output, "--strict", status=1)
        self.assertTrue(json.loads(strict_output.read_text())["records"][0]["warnings"])

    def test_queries_preserve_literal_values_coordinate_spaces_and_errors(self):
        example = yaml.safe_load((ROOT / "model/examples/multiple-pfams/harmonized.yaml").read_text())
        key, value = "note 'with quotes'", "literal $(echo wrong); two words"
        example["features"][0].setdefault("attributes", []).append({"key": key, "value": value})
        source = self.work / "example 'copy'.yaml"
        source.write_text(yaml.safe_dump(example))
        database = self.work / "database 'copy'.duckdb"
        self.run_recipe("build-duckdb", source, database)
        rows = json.loads(self.run_recipe("query-attribute", key, value, database))
        self.assertEqual(rows, [[example["features"][0]["feature_id"]]])

        all_pfams = json.loads(self.run_recipe("query-duckdb", database))
        self.assertEqual(len(all_pfams), 1)
        self.assertEqual(all_pfams[0][2], 3)
        selected = json.loads(self.run_recipe("query-duckdb", database, "PF13358", "PF13592"))
        self.assertEqual(selected[0][3], ["PF13358", "PF13592"])
        self.run_recipe("query-duckdb", database, "PF13358", status=2)

        cds = all_pfams[0][0]
        contig = example["contigs"][0]["contig_id"]
        genomic = json.loads(self.run_recipe("query-overlap", "contig", contig, 63, 63, database))
        protein = json.loads(self.run_recipe("query-overlap", "protein", cds, 168, 168, database))
        self.assertEqual(genomic[0][0], cds)
        self.assertEqual(protein[0][1], "PF13358")
        self.run_recipe("query-overlap", "contig", contig, 10, 1, database, status=2)

    def test_nmdc_render_uses_retained_inputs_offline_and_preserves_counts(self):
        profile = nmdc_fixture.profile
        work, output = self.work / "retained inputs", self.work / "rendered reports"
        responses = [profile.SCHEMA_RELEASE,
                     {"resources": [{"id": "1", "data_category": "observed"}]},
                     profile.SCHEMA_RELEASE]
        with patch.object(profile, "get_bytes", return_value=nmdc_fixture.SCHEMA), \
             patch.object(profile, "get_json", side_effect=responses), \
             patch.object(profile, "collection_count", return_value=1):
            profile.collect(work)
        self.run_recipe("nmdc-render", work, output)
        counts = json.loads((output / "counts.json").read_text())
        self.assertEqual(counts["records"], 1)
        self.assertEqual(counts["slots"]["data_category"]["values"], {"observed": 1})
        with (work / "data-objects.jsonl").open("a") as handle:
            handle.write('{}\n')
        rejected = self.work / "bad report"
        self.run_recipe("nmdc-render", work, rejected, status=1)
        self.assertFalse((rejected / "counts.json").exists())


if __name__ == "__main__":
    unittest.main()
