"""Offline accounting, completeness, and provenance checks for the NMDC-only profile."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("nmdc_profile", ROOT / "scripts/profile_nmdc_data_objects.py")
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)

SCHEMA = b"""id: https://example.org/profile-test
name: profile-test
prefixes:
  linkml: https://w3id.org/linkml/
imports: [linkml:types]
default_range: string
slots:
  type:
    range: uriorcurie
  data_category:
    range: Category
  description:
  compression_type:
classes:
  NamedThing:
    slots: [type]
  DataObject:
    is_a: NamedThing
    slots: [data_category, compression_type, description]
enums:
  Category:
    permissible_values:
      observed:
      unobserved:
"""


def categories():
    return {"slots": [
        {"name": "category", "range": "Category", "multivalued": False,
         "permitted_values": ["A", "B"]},
        {"name": "tags", "range": "string", "multivalued": True, "permitted_values": None},
        {"name": "flag", "range": "boolean", "multivalued": False, "permitted_values": None},
    ]}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        # Keep even ephemeral test files under local/, never /private/tmp.
        (ROOT / "local").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "local")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def test_catalogue_includes_inherited_categories_and_excludes_free_text(self):
        schema = self.work / "schema.yaml"
        schema.write_bytes(SCHEMA)
        result = profile.catalogue(schema)
        self.assertEqual([s["name"] for s in result["slots"]],
                         ["compression_type", "data_category", "type"])
        self.assertEqual(result["slots"][1]["permitted_values"], ["observed", "unobserved"])
        self.assertIsNone(result["slots"][0]["permitted_values"])

    def test_counts_distinguish_absence_invalid_values_and_unknown_enums(self):
        rows = [
            {"id": "1", "category": "A", "tags": ["x", "x", "y"], "flag": False,
             "url": "https://EXAMPLE.org:443/a"},
            {"id": "2", "category": "outside", "tags": [], "flag": 0,
             "url": "https://example.org/b"},
            {"id": "3", "category": None, "tags": ["", "x"], "url": "relative/path"},
            {"id": "4", "category": "", "tags": "x", "url": None},
            {"id": "5", "category": ["A"], "tags": [1], "url": ""},
            {"id": "6", "url": 42},
            {"id": "7"},
        ]
        result = profile.profile_records(categories(), rows)
        cat = result["slots"]["category"]
        self.assertEqual(cat["values"], {"A": 1, "outside": 1})
        self.assertEqual(cat["observed_outside_enum"], ["outside"])
        self.assertEqual(cat["states"], {"present": 2, "missing": 2, "null": 1,
                                          "empty_string": 1, "invalid_type": 1})
        self.assertEqual(result["slots"]["tags"]["values"], {"x": 1, "y": 1})
        self.assertEqual(result["slots"]["flag"]["values"], {"false": 1})
        self.assertEqual(result["slots"]["flag"]["states"]["invalid_type"], 1)
        self.assertEqual(result["url"]["hosts"], {"example.org": 2})
        self.assertEqual(result["url"]["states"], {
            "present": 2, "missing": 1, "null": 1, "empty_string": 1,
            "invalid_type": 1, "invalid_or_hostless": 1})
        for slot in result["slots"].values():
            self.assertEqual(sum(slot["states"].values()), 7)

    def test_host_parsing_handles_authority_and_rejects_bad_urls(self):
        for value, expected in [
            ("https://user:password@HOST.example:8443/a?q=1", "host.example"),
            ("ftp://HOST.example/file", "host.example"),
            ("https://[2001:db8::1]:443/file", "2001:db8::1"),
            ("host.example/file", None), ("//host.example/file", None),
            ("https://host.example:bad/file", None), ("https://host.example:70000/", None),
            ("https://[broken/file", None), ("https://bad host/file", None),
            ("file:///path/to/file", None), (None, None),
        ]:
            with self.subTest(value=value):
                self.assertEqual(profile.url_host(value), expected)

    def test_duplicate_or_missing_ids_are_rejected(self):
        for rows in ([{"id": "1"}, {"id": "1"}], [{}], [{"id": 1}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                profile.profile_records(categories(), rows)

    def collect_fixture(self):
        responses = [profile.SCHEMA_RELEASE,
                     {"resources": [{"id": "1", "data_category": "observed"}], "next_page_token": "next"},
                     {"resources": [{"id": "2", "data_category": "observed"}]},
                     profile.SCHEMA_RELEASE]
        with patch.object(profile, "get_bytes", return_value=SCHEMA), \
             patch.object(profile, "get_json", side_effect=responses), \
             patch.object(profile, "collection_count", return_value=2):
            profile.collect(self.work)

    def test_complete_collection_and_offline_render_include_zero_counts(self):
        self.collect_fixture()
        provenance = json.loads((self.work / "provenance.json").read_text())
        self.assertEqual((provenance["records"], provenance["pages"]), (2, 2))
        self.assertEqual(provenance["projection_sha256"],
                         hashlib.sha256((self.work / "data-objects.jsonl").read_bytes()).hexdigest())
        output = self.work / "report"
        profile.render(self.work, output)
        with (output / "categorical-values.csv").open() as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(rows, [
            {"slot": "data_category", "value": "observed", "data_objects": "2", "schema_permitted": "true"},
            {"slot": "data_category", "value": "unobserved", "data_objects": "0", "schema_permitted": "true"}])
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        profile.render(self.work, output)
        self.assertEqual(original, {path.name: path.read_bytes() for path in output.iterdir()})
        with (self.work / "data-objects.jsonl").open("a") as target:
            target.write('{}\n')
        with self.assertRaisesRegex(ValueError, "checksum"):
            profile.render(self.work, output)

    def test_collection_refuses_partial_duplicate_and_nonadvancing_pages(self):
        cases = [
            ([profile.SCHEMA_RELEASE, {"resources": [{"id": "1"}]}], 2, "incomplete"),
            ([profile.SCHEMA_RELEASE, {"resources": [{"id": "1"}, {"id": "1"}]}], 2, "Duplicate"),
            ([profile.SCHEMA_RELEASE,
              {"resources": [{"id": "1"}], "next_page_token": "same"},
              {"resources": [{"id": "2"}], "next_page_token": "same"}], 2, "Non-advancing"),
            (["different-version"], 2, "update and pin"),
            ([profile.SCHEMA_RELEASE, {"resources": [{"id": "1"}]}, "changed"], 1, "changed"),
        ]
        for responses, total, message in cases:
            with self.subTest(message=message), \
                 patch.object(profile, "get_bytes", return_value=SCHEMA), \
                 patch.object(profile, "get_json", side_effect=responses), \
                 patch.object(profile, "collection_count", return_value=total):
                with self.assertRaisesRegex(ValueError, message):
                    profile.collect(self.work)
                self.assertFalse((self.work / "provenance.json").exists())

    def test_published_aggregates_reconcile(self):
        report = ROOT / "profiles/nmdc-data-objects"
        cat = json.loads((report / "catalogue.json").read_text())
        counts = json.loads((report / "counts.json").read_text())
        self.assertEqual(cat["class"], "nmdc:DataObject")
        self.assertEqual(cat["schema"], counts["provenance"])
        total = counts["records"]
        for key in ("records", "collection_count_before", "collection_count_after"):
            self.assertEqual(counts["provenance"][key], total)
        expected_rows = []
        self.assertEqual(set(counts["slots"]), {s["name"] for s in cat["slots"]})
        for definition in cat["slots"]:
            slot = counts["slots"][definition["name"]]
            values, allowed = slot["values"], definition["permitted_values"]
            self.assertEqual(sum(slot["states"].values()), total)
            self.assertEqual(slot["distinct_observed_values"], len(values))
            self.assertTrue(all(0 < n <= total for n in values.values()))
            self.assertEqual(slot["observed_outside_enum"],
                             sorted(set(values) - set(allowed)) if allowed is not None else None)
            if not definition["multivalued"]:
                self.assertEqual(sum(values.values()), slot["states"].get("present", 0))
            for value in sorted(set(values) | set(allowed or [])):
                expected_rows.append({"slot": definition["name"], "value": value,
                                      "data_objects": str(values.get(value, 0)),
                                      "schema_permitted": "not_enumerated" if allowed is None else str(value in allowed).lower()})
        with (report / "categorical-values.csv").open() as source:
            self.assertEqual(list(csv.DictReader(source)), expected_rows)
        urls = counts["url"]
        self.assertEqual(sum(urls["states"].values()), total)
        self.assertEqual(sum(urls["hosts"].values()), urls["states"].get("present", 0))
        self.assertEqual(urls["distinct_hosts"], len(urls["hosts"]))
        with (report / "url-hosts.csv").open() as source:
            self.assertEqual(list(csv.DictReader(source)), [
                {"hostname": host, "data_objects": str(n)} for host, n in urls["hosts"].items()])


if __name__ == "__main__":
    unittest.main()
