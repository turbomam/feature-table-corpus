#!/usr/bin/env python3
"""Reproduce measured conversion outcomes; unexpected success/failure is an error."""
import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import sys

import yaml

from convert_features import (ConversionError, PROFILES, export_source, import_source, require)

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "analyses/conversion-roundtrips/report.json"
CASES = ROOT / "analyses/conversion-roundtrips/cases.yaml"


def insdc_observations(content):
    """Text observations on this fixture, NOT an INSDC parser/validity verdict."""
    lines = content.decode().splitlines()
    locations = [m.group(1) for line in lines
                 if (m := re.match(r"^ {5}[A-Za-z][A-Za-z0-9_'*-]* +(.+)$", line))]
    repeated, qualifiers = 0, Counter()
    for line in [*lines, "     end             end"]:
        if re.match(r"^ {5}[A-Za-z]", line):
            repeated += sum(n > 1 for n in qualifiers.values())
            qualifiers.clear()
        match = re.match(r"^ {21}/([A-Za-z0-9_]+)", line)
        if match:
            qualifiers[match.group(1)] += 1
    return {"method": "fixed-column source-text inspection, not format validation",
            "accession_versions": re.findall(r"^VERSION\s+(\S+)", content.decode(), re.M),
            "feature_location_lines": len(locations),
            "join_location_lines": sum("join(" in loc for loc in locations),
            "partial_location_lines": sum("<" in loc or ">" in loc for loc in locations),
            "repeated_qualifier_keys_within_features": repeated}


def make_report():
    toolchain = {}
    for line in (ROOT / "requirements-conversion.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            package, pinned = line.split("==")
            require(version(package) == pinned, "toolchain-version", f"install {line} to reproduce this report")
            toolchain[package] = pinned
    contracts = {}
    for path in sorted((ROOT / "model/profiles").glob("*.yaml")):
        contract = yaml.safe_load(path.read_text())
        contracts[contract["id"]] = {"path": path.relative_to(ROOT).as_posix(),
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    require(set(contracts) == set(PROFILES), "profile-contract", "each executable profile must have exactly one contract")
    inventory = yaml.safe_load((ROOT / "corpus/index.yaml").read_text())["entries"]
    by_path = {e["path"]: e for e in inventory if e.get("path")}
    rows = []
    for case in yaml.safe_load(CASES.read_text())["cases"]:
        content = (ROOT / case["path"]).read_bytes()
        indexed = by_path.get(case["path"])
        row = {"id": case["id"], "path": case["path"], "format": case["format"],
               "profile": case.get("profile"), "source_sha256": hashlib.sha256(content).hexdigest(),
               "case_kind": case["case_kind"], "losses": [], "edited_export": "unsupported"}
        context = None
        if case.get("protein_context"):
            context_bytes = (ROOT / case["protein_context"]).read_bytes()
            context = json.loads(context_bytes)
            row["protein_context_sha256"] = hashlib.sha256(context_bytes).hexdigest()
        if case["format"] == "genbank":
            row["observations"] = insdc_observations(content)
        try:
            require(case.get("profile") in PROFILES, "unsupported-format",
                    f"no {case['format']} conversion adapter implemented; source is retained as corpus evidence")
            source_uri = indexed["origin_url"] if indexed else "urn:ftc:test:" + case["id"]
            bundle = import_source(content, profile=case["profile"], reference_context=case["reference_context"],
                                   source_uri=source_uri, metadata_profile=case.get("metadata_profile", "generic"),
                                   protein_context=context)
            exact = export_source(bundle, mode="exact", original_bytes=content, protein_context=context)
            reconstructed = export_source(bundle, mode="reconstruct", original_bytes=content, protein_context=context)
            again = import_source(reconstructed, profile=case["profile"], reference_context=case["reference_context"],
                                  source_uri=source_uri, metadata_profile=case.get("metadata_profile", "generic"),
                                  protein_context=context)
            require(exact == content, "byte-mismatch", "exact export differs")
            mappings_equal = again["mappings"] == bundle["mappings"]
            if case["format"] == "genbank":
                from insdc_profile import semantic_mappings, nonfeature_text
                mappings_equal = semantic_mappings(again) == semantic_mappings(bundle)
            require(again["dataset"] == bundle["dataset"] and mappings_equal,
                    "reconstruction-mismatch", "re-imported fields/relationships/grouping differ")
            nonfeatures = (nonfeature_text if case["format"] == "genbank" else
                           lambda b: [r for r in b["source"]["records"] if r["kind"] != "feature"])
            require(nonfeatures(again) == nonfeatures(bundle), "metadata-mismatch", "metadata records/scopes changed")
            feature_columns = lambda b: [r["feature_columns"] for r in b["source"]["records"] if "feature_columns" in r]
            lexical_changes = Counter()
            for before, after in zip(feature_columns(bundle), feature_columns(again)):
                lexical_changes.update(i for i, (a, b) in enumerate(zip(before, after), 1) if a != b)
            row.update(status="supported", source_byte_recovery="exact-bytes",
                       modeled_field_reconstruction="preserved-interpreted-meaning",
                       reconstructed_bytes_identical=reconstructed == content,
                       normalization="none observed" if reconstructed == content else "documented lexical normalization",
                       normalized_columns=[{"column": i, "changed_records": n} for i, n in sorted(lexical_changes.items())],
                       source_feature_rows=len(bundle["mappings"]), model_features=len(bundle["dataset"]["features"]),
                       nonfeature_records=len(nonfeatures(bundle)),
                       reconstructed_sha256=hashlib.sha256(reconstructed).hexdigest(),
                       validation="profile constraints and closed Dataset checks passed; not a full source-format validator")
            if case["format"] == "genbank":
                row.pop("normalized_columns")
                def blocks(b):
                    records = b["source"]["records"]
                    return ["".join(r["raw_text"] for r in records[m["source_span"][0]:m["source_span"][1]]) for m in b["mappings"]]
                row["normalized_feature_blocks"] = sum(a != b for a, b in zip(blocks(bundle), blocks(again)))
        except ConversionError as error:
            row.update(status="unsupported", source_byte_recovery="not-attempted",
                       modeled_field_reconstruction="not-attempted", diagnostic={"code": error.code, "message": str(error)})
        require(row["status"] == case["expected"], "unexpected-outcome", f"{case['id']}: {row}")
        if case.get("expected_code"):
            require(row.get("diagnostic", {}).get("code") == case["expected_code"],
                    "unexpected-diagnostic", f"{case['id']}: {row}")
        rows.append(row)
    return {"report_version": 1, "implementation": "scripts/convert_features.py",
            "toolchain": toolchain, "profiles": contracts,
            "query_performance": "not-measured", "lossy_export": "not-implemented",
            "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--check", action="store_true", help="compare against the retained report without writing")
    args = parser.parse_args()
    try:
        text = json.dumps(make_report(), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            require(args.output.read_text() == text, "stale-report", "conversion report does not reproduce; regenerate and review it")
            print("conversion report reproduces exactly")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
            print(f"wrote {args.output}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
