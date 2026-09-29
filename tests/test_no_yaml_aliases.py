"""No YAML file in the repository uses anchors or aliases, and the scripts that write YAML never emit them.

The project writes every value out in full. PyYAML's safe_dump would add &id001 and *id001 on its
own whenever one Python object appears twice, so the writers use a dumper that doesn't.
"""
from pathlib import Path
import subprocess
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import flat_profile  # noqa: E402
import jgi_inputs  # noqa: E402


class NoYamlAliasTests(unittest.TestCase):
    def test_no_tracked_yaml_file_has_an_anchor_or_alias(self):
        tracked = subprocess.run(["git", "ls-files", "*.yaml", "*.yml"], cwd=ROOT, capture_output=True,
                                 text=True, check=True).stdout.split()
        self.assertGreater(len(tracked), 20)
        found = {}
        for name in tracked:
            lines = flat_profile.yaml_references((ROOT / name).read_text(encoding="utf-8"))
            if lines:
                found[name] = lines
        self.assertEqual(found, {})

    def test_the_check_finds_an_anchor_and_an_alias(self):
        self.assertEqual(flat_profile.yaml_references("a: &x {b: 1}\nc: *x\n"), [1, 2])

    def test_the_writers_repeat_a_shared_object_in_full(self):
        shared = {"permissible_values": ["+", "-"]}
        data = {"StrandEnum": shared, "TargetStrandEnum": shared}
        self.assertIn("&id001", yaml.safe_dump(data))  # the behavior the dumpers exist to avoid
        for dumper in (flat_profile.NoAliasDumper, jgi_inputs.NoAliasDumper):
            with self.subTest(dumper.__module__):
                text = yaml.dump(data, Dumper=dumper)
                self.assertEqual(flat_profile.yaml_references(text), [])
                self.assertEqual(yaml.safe_load(text), data)


if __name__ == "__main__":
    unittest.main()
