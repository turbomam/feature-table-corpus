"""A new warning must fail even when a previously allowed warning disappears."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from lint_schema import lint


class SchemaLintTests(unittest.TestCase):
    def test_real_schema_has_only_allowed_findings(self):
        self.assertEqual(lint(ROOT / "model/schema/ber_feature_model.yaml"), [])

    def test_replacing_allowed_warning_still_fails(self):
        schema = yaml.safe_load((ROOT / "model/schema/ber_feature_model.yaml").read_text())
        values = schema["enums"]["StrandEnum"]["permissible_values"]
        values["bad-name"] = values.pop("?")
        scratch = ROOT / "local/test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "schema.yaml"
            path.write_text(yaml.safe_dump(schema))
            (Path(directory) / "attributes.yaml").write_bytes((ROOT / "model/schema/attributes.yaml").read_bytes())
            with contextlib.redirect_stdout(io.StringIO()):
                failures = lint(path)
            self.assertEqual(len(failures), 1)
            self.assertIn("bad-name", failures[0].message)


if __name__ == "__main__":
    unittest.main()
