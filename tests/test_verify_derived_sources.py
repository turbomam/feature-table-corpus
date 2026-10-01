"""A derived entry's source is an index entry: vendored, or restricted with an md5 recorded."""
import contextlib
import importlib.util
import io
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)

BASE = {"label": "x", "source": "x", "license": "x", "retrieved": "2026-09-30"}
BASIS = {"terms": ["https://example.org/terms"], "read": "2026-09-30", "allows": "public with citation"}


def entry(eid, tier, **fields):
    extra = {"vendored": {"path": f"{eid}.gff", "bytes": 1, "md5": "a", "origin_url": f"https://e/{eid}"},
             "restricted": {"origin_url": f"https://e/{eid}"},
             "linked": {"origin_url": f"https://e/{eid}"},
             "derived": {"path": f"{eid}.gff", "bytes": 1, "md5": "b", "origin_url": "https://e/gen",
                         "mutation": "m", "validity": "v"}}[tier]
    return {"id": eid, "tier": tier, **BASE, **extra, **fields}


class DerivedSourceTests(unittest.TestCase):
    def check(self, entries):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bad = verify.check_index(entries)
        return bad, out.getvalue()

    def test_the_real_index_passes(self):
        entries = yaml.safe_load((ROOT / "corpus/index.yaml").read_text())["entries"]
        self.assertEqual(self.check(entries)[0], 0)

    def test_each_rule_is_enforced(self):
        cases = {
            "vendored source": ([entry("s", "vendored"), entry("d", "derived", derived_from="s")], None),
            "vendored source by path": ([entry("s", "vendored"), entry("d", "derived", derived_from="s.gff")], None),
            "restricted with md5 and basis": ([entry("s", "restricted", md5="a"),
                                              entry("d", "derived", derived_from="s", redistribution_basis=BASIS)], None),
            "restricted without basis": ([entry("s", "restricted", md5="a"), entry("d", "derived", derived_from="s")],
                                         "needs redistribution_basis"),
            "basis without https terms": ([entry("s", "restricted", md5="a"),
                                          entry("d", "derived", derived_from="s",
                                                redistribution_basis={**BASIS, "terms": ["ftp://x"]})],
                                         "terms is a non-empty list of https URLs"),
            "basis with a bare https terms URL": ([entry("s", "restricted", md5="a"),
                                                  entry("d", "derived", derived_from="s",
                                                        redistribution_basis={**BASIS, "terms": ["https://"]})],
                                                 "terms is a non-empty list of https URLs"),
            "basis without a read date": ([entry("s", "restricted", md5="a"),
                                          entry("d", "derived", derived_from="s",
                                                redistribution_basis={**BASIS, "read": "last week"})],
                                         "read is the YYYY-MM-DD"),
            "basis with an impossible read date": ([entry("s", "restricted", md5="a"),
                                                   entry("d", "derived", derived_from="s",
                                                         redistribution_basis={**BASIS, "read": "2026-99-99"})],
                                                  "read is the YYYY-MM-DD"),
            "basis without allows": ([entry("s", "restricted", md5="a"),
                                     entry("d", "derived", derived_from="s",
                                           redistribution_basis={**BASIS, "allows": " "})],
                                    "allows says what the terms permit"),
            "restricted without md5": ([entry("s", "restricted"),
                                        entry("d", "derived", derived_from="s", redistribution_basis=BASIS)],
                                       "restricted source 's' has no md5"),
            "linked source": ([entry("s", "linked"), entry("d", "derived", derived_from="s")], "is 'linked'"),
            "missing source": ([entry("d", "derived", derived_from="nope")], "'nope' is not an entry id or path"),
        }
        for name, (entries, expected) in cases.items():
            with self.subTest(name):
                bad, out = self.check(entries)
                if expected is None:
                    self.assertEqual(bad, 0, out)
                else:
                    self.assertGreater(bad, 0)
                    self.assertIn(expected, out)


if __name__ == "__main__":
    unittest.main()
