"""The installable ber-feature-model package: build the wheel, install it, validate with it."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "model/examples/multiple-pfams/harmonized.yaml"

# Every file the wheel copies from the repository, so the package can never ship a stale copy.
BUNDLED = {
    "ber_feature_model/validate_closed.py": "scripts/validate_closed.py",
    "ber_feature_model/feature_locations.py": "scripts/feature_locations.py",
    "ber_feature_model/schema/ber_feature_model.yaml": "model/schema/ber_feature_model.yaml",
    "ber_feature_model/schema/attributes.yaml": "model/schema/attributes.yaml",
}


@unittest.skipIf(shutil.which("uv") is None, "uv builds and runs the package")
class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        # Build through the sdist, as `uv build` does, so a file missing from the sdist fails here.
        subprocess.run(["uv", "build", "--quiet", "--out-dir", str(out), str(ROOT)], check=True)
        cls.wheel = next(out.glob("*.whl"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_installed(self, *args):
        return subprocess.run(["uv", "run", "--no-project", "--isolated", "--with", str(self.wheel), *args],
                              capture_output=True, text=True, cwd=self.tmp.name)

    def test_package_version_is_the_schema_version(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        schema = yaml.safe_load((ROOT / "model/schema/ber_feature_model.yaml").read_text())
        self.assertEqual(project["version"], str(schema["version"]))
        self.assertIn(f'__version__ = "{project["version"]}"',
                      (ROOT / "src/ber_feature_model/__init__.py").read_text())

    def test_wheel_bundles_the_repository_files_unchanged(self):
        with zipfile.ZipFile(self.wheel) as wheel:
            for packaged, source in BUNDLED.items():
                self.assertEqual(wheel.read(packaged), (ROOT / source).read_bytes(), packaged)

    def test_installed_command_accepts_a_valid_dataset(self):
        result = self.run_installed("ber-feature-validate", str(EXAMPLE))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 error(s) against ber-feature-model", result.stdout)

    def test_installed_command_rejects_an_undeclared_slot(self):
        bad = Path(self.tmp.name) / "bad.yaml"
        bad.write_text("contigs:\n  - contig_id: c1\n    bogus: 1\n")
        result = self.run_installed("ber-feature-validate", str(bad))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("'bogus' was unexpected", result.stdout)

    def test_installed_command_reports_malformed_yaml_without_a_traceback(self):
        bad = Path(self.tmp.name) / "malformed.yaml"
        bad.write_text("contigs: [\n")
        result = self.run_installed("ber-feature-validate", str(bad))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("malformed.yaml:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_installed_command_reports_an_unknown_class_as_a_usage_error(self):
        result = self.run_installed("ber-feature-validate", "--class", "Datset", str(EXAMPLE))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("'Datset' is not a class", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_installed_function_runs_the_closed_model_checks(self):
        # Two contigs with one ID is a closed-model error JSON Schema alone can't report.
        data = yaml.safe_load(EXAMPLE.read_text())
        data["contigs"].append(dict(data["contigs"][0]))
        script = ("import json, sys, ber_feature_model as m; "
                  "print(json.dumps(m.validate(json.load(sys.stdin))))")
        result = subprocess.run(["uv", "run", "--no-project", "--isolated", "--with", str(self.wheel),
                                 "python", "-c", script], input=json.dumps(data),
                                capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any("duplicate" in error.lower() for error in json.loads(result.stdout)), result.stdout)

    def test_installed_function_reports_deep_nesting_without_a_traceback(self):
        # Deeper than jsonschema can follow on any supported Python; a loader would refuse it,
        # but data built in memory never passes through one.
        script = ("import ber_feature_model as m; v = []; "
                  "exec('for _ in range(10000): v = [v]'); "
                  "print(m.validate({'contigs': [{'contig_id': 'c1', 'member_of': v}]}))")
        result = subprocess.run(["uv", "run", "--no-project", "--isolated", "--with", str(self.wheel),
                                 "python", "-c", script], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nested too deeply to validate", result.stdout)

    def test_installed_function_refuses_non_finite_scores(self):
        # JSON can't carry NaN, so the Dataset is built in memory, as a dataframe conversion would.
        # Feature.score has no range limit, so only the value check stands between these and [].
        values = ["float('nan')", "float('inf')", "Decimal('NaN')", "Decimal('-Infinity')", "Decimal('sNaN')"]
        script = ("import json, yaml, ber_feature_model as m; from decimal import Decimal; "
                  f"d = yaml.safe_load(open({str(EXAMPLE)!r})); "
                  "f = next(f for f in d['features'] if 'score' in f); out = []\n"
                  f"for v in [{', '.join(values)}]:\n"
                  "    f['score'] = v; out.append(m.validate(d))\n"
                  "print(json.dumps(out))")
        result = subprocess.run(["uv", "run", "--no-project", "--isolated", "--with", str(self.wheel),
                                 "python", "-c", script], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        for value, errors in zip(values, json.loads(result.stdout)):
            self.assertTrue(any("is not a finite number" in error for error in errors), (value, errors))


if __name__ == "__main__":
    unittest.main()
