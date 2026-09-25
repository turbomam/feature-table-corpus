#!/usr/bin/env python3
"""Compare independent validators with explicit per-profile, per-file rules."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

from install_genometools import ROOT, VERSION, default_binary
import install_gff3toolkit as toolkit

REPORT = ROOT / "analyses" / "format-validation" / "report.json"
PROFILES = ROOT / "model/profiles"
VALIDATION = ROOT / "model/validation"
AGAT_BLOCKER = ROOT / "analyses/format-validation/agat-blocker.json"
VALIDATORS = ("genometools", "gff3toolkit")
# GenomeTools has no rule codes. These deliberately narrow patterns name the
# observed error rules; an unrecognized rejection is an execution/check error.
GT_RULES = {
    "missing-version": r'does not begin with "##gff-version"',
    "illegal-phase": r"phase '.+' .* not a valid character from the set '012\.'",
    "unresolved-parent": r'Parent ".+" .* was not defined \(via "ID="\)',
    "inconsistent-id-type": r'the multi-feature with ID ".+" .* has a different type',
    "start-after-end": r"start '\d+' is larger then end '\d+'",
    "attribute-assignment": r"token .+ does not contain exactly one '='",
}


def binary_path():
    return Path(os.environ["GENOMETOOLS"]).resolve() if "GENOMETOOLS" in os.environ else default_binary()


def check_version(binary):
    result = subprocess.run([str(binary), "-version"], capture_output=True, text=True, timeout=30)
    if result.returncode or not re.search(rf"\(GenomeTools\) {re.escape(VERSION)}\n", result.stdout):
        raise ValueError(f"Expected GenomeTools {VERSION}; run just validity-install")


def verdict(binary, path, root=ROOT):
    result = subprocess.run([str(binary), "gff3validator", str(path)], cwd=root,
                            capture_output=True, text=True, timeout=60,
                            env={**os.environ, "LC_ALL": "C"})
    # Crashes, missing libraries, timeouts, and unrelated command failures are not
    # evidence of invalid GFF3. Preserve warnings, including synthesized regions.
    if result.returncode == 0 and result.stdout.strip() == "input is valid GFF3":
        status = "accepted"
    elif result.returncode == 1 and "gff3validator: error:" in result.stderr:
        status = "rejected"
    else:
        raise ValueError(f"Validator execution failed for {path}: {result.returncode}: {result.stderr}")
    rules = sorted(rule for rule, pattern in GT_RULES.items() if re.search(pattern, result.stderr))
    if status == "rejected" and len(rules) != 1:
        raise ValueError(f"Unrecognized GenomeTools error for {path}: {result.stderr}")
    return {"verdict": status, "rules": rules, "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.replace(str(binary), "gt").strip()}


def check_toolkit_version(binary):
    result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=30)
    if result.returncode or result.stdout.strip() != f"gff3_QC {toolkit.VERSION}":
        raise ValueError(f"Expected GFF3toolkit {toolkit.VERSION}; run just validity-install")


def parse_qc_report(content):
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    if reader.fieldnames != ["Line_num", "Error_code", "Error_level", "Error_tag"]:
        raise ValueError("GFF3toolkit execution failed: missing or malformed QC report header")
    rows = list(reader)
    for row in rows:
        if set(row) != set(reader.fieldnames) or not all(row.values()) or not re.fullmatch(r"E(?:ma|mr|sf)\d{4}", row["Error_code"]):
            raise ValueError(f"GFF3toolkit execution failed: malformed diagnostic {row}")
    # Count every reported code, including warnings. Sort before hashing because
    # upstream traversal order does not define diagnostic identity.
    rows.sort(key=lambda row: tuple(row[key] for key in reader.fieldnames))
    diagnostics = []
    for rule in sorted({row["Error_code"] for row in rows}):
        group = [row for row in rows if row["Error_code"] == rule]
        diagnostics.append({"rule": rule, "count": len(group), "example": group[0]})
    return {"verdict": "rejected" if rows else "accepted",
            "rules": [d["rule"] for d in diagnostics], "diagnostics": diagnostics,
            "diagnostics_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}


def toolkit_verdict(binary, path, root=ROOT):
    # Never let upstream temporary/output files land beside the original input.
    # /dev/null supplies no reference sequence, and -noncg avoids BLAST and
    # canonical eukaryotic gene-model assumptions. No biological check is claimed.
    with tempfile.TemporaryDirectory(prefix="ftc-qc-") as directory:
        result = subprocess.run(
            [str(binary), "-g", str(root / path), "-noncg", "-f", "/dev/null",
             "-o", "qc.tsv", "-s", "statistics.tsv"], cwd=directory,
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
            env={**os.environ, "LC_ALL": "C", "PYTHONHASHSEED": "0"})
        report = Path(directory) / "qc.tsv"
        if result.returncode != 0 or not report.is_file() or "Traceback (most recent call last)" in result.stderr:
            raise ValueError(f"GFF3toolkit execution failed for {path}: {result.returncode}: {result.stderr}")
        return {**parse_qc_report(report.read_text()), "exit_code": result.returncode}


def load_expectations(directory=VALIDATION, contracts=PROFILES):
    """Read model/validation/*.yaml, one file per conversion contract or dialect.

    Expectations are kept out of model/profiles/ so the contracts, whose
    checksums the conversion report pins, change only when conversion does.
    Every contract there must still have a file here naming it as `profile`.
    """
    cases = {}
    covered = set()
    for path in sorted(directory.glob("*.yaml")):
        profile = yaml.safe_load(path.read_text())
        validation = profile.get("validation")
        if not isinstance(profile.get("profile"), str) or not isinstance(validation, dict):
            raise ValueError(f"Missing validator expectations in {path}")
        covered.add(profile["profile"])
        for name in VALIDATORS:
            declared = validation[name]["expected_failures"]
            observed = set()
            for identity, expected in validation["cases"].items():
                if set(expected) != set(VALIDATORS):
                    raise ValueError(f"Missing/unknown validator for {identity} in {path}")
                rules = expected[name]
                if not isinstance(rules, list) or len(rules) != len(set(rules)) or not set(rules) <= set(declared):
                    raise ValueError(f"Undeclared/duplicate expected rule for {identity}/{name} in {path}")
                observed.update(rules)
            if observed != set(declared):
                raise ValueError(f"Unused expected rules for {name} in {path}")
        if validation["agat"]["status"] != "blocked" or validation["agat"]["expected_failures"] is not None:
            raise ValueError(f"AGAT has no measured expectations: {path}")
        for identity, expected in validation["cases"].items():
            if identity in cases:
                raise ValueError(f"Duplicate validator case: {identity}")
            cases[identity] = {"profile": profile["profile"], "expected": expected}
    if contracts is not None:
        declared = {yaml.safe_load(path.read_text())["id"] for path in sorted(contracts.glob("*.yaml"))}
        if declared - covered:
            raise ValueError(f"Conversion contracts without validator expectations: {sorted(declared - covered)}")
    return cases


def compare_rules(identity, validator, actual, expected):
    unexpected = sorted(set(actual) - set(expected))
    disappeared = sorted(set(expected) - set(actual))
    if unexpected or disappeared:
        raise ValueError(f"Rule mismatch for {identity}/{validator}: unexpected={unexpected}, disappeared={disappeared}")


def expectation(entry):
    if entry["tier"] != "derived":
        return None
    label = entry.get("validity", "").lower()
    if label.startswith("invalid:"):
        return "rejected"
    if label.startswith("valid gff3:"):
        return "accepted"
    raise ValueError(f"Unrecognized validity label: {entry['id']}: {label}")


def measure(index, binary, root=ROOT, toolkit_binary=None, expectations=None):
    check_version(binary)
    toolkit_binary = toolkit_binary or toolkit.default_binary()
    check_toolkit_version(toolkit_binary)
    expectations = load_expectations() if expectations is None else expectations
    blocker = json.loads(AGAT_BLOCKER.read_text())
    entries = index["entries"]
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate corpus IDs")
    records = []
    for entry in entries:
        if entry["tier"] not in ("vendored", "derived"):
            continue
        path = entry["path"]
        record = {"id": entry["id"], "path": path, "format": entry["format"],
                  "sha256": hashlib.sha256((root / path).read_bytes()).hexdigest()}
        if entry["format"].startswith("GFF3"):
            if entry["id"] not in expectations:
                raise ValueError(f"Missing validator expectations for {entry['id']}")
            case = expectations[entry["id"]]
            record["profile"] = case["profile"]
            results = {"genometools": verdict(binary, path, root),
                       "gff3toolkit": toolkit_verdict(toolkit_binary, path, root)}
            expected = expectation(entry)
            if expected is not None:
                results["genometools"]["expected_from_validity"] = expected
                if results["genometools"]["verdict"] != expected:
                    raise ValueError(f"Validity mismatch for {entry['id']}: expected {expected}, got {results['genometools']['verdict']}")
            for name in VALIDATORS:
                rules = sorted(case["expected"][name])
                compare_rules(entry["id"], name, results[name]["rules"], rules)
                results[name]["expected_rules"] = rules
            results["agat"] = {"verdict": "blocked", "reason": blocker["reason"]}
        else:
            results = {name: {"verdict": "not_checked", "reason": "No independent validator configured for this format"}
                       for name in (*VALIDATORS, "agat")}
        record["validators"] = results
        records.append(record)
    return {"report_version": 2, "validators": {
            "genometools": {"name": "GenomeTools", "version": VERSION,
                "arguments": ["gff3validator"], "ontology_typecheck": False,
                "biological_correctness": "not_measured", "errors": "first error only"},
            "gff3toolkit": {"name": "GFF3toolkit", "version": toolkit.VERSION,
                "python_version": ".".join(map(str, toolkit.PYTHON_VERSION)),
                "source_sha256": toolkit.SHA256,
                "arguments": ["-g", "FILE", "-noncg", "-f", "/dev/null", "-o", "qc.tsv", "-s", "statistics.tsv"],
                "ontology_typecheck": False, "biological_correctness": "not_measured",
                "diagnostics": "All QC codes, including warnings; counts, one example per code, and a hash of all sorted rows"},
            "agat": blocker},
            "summary": {name: dict(sorted(Counter(r["validators"][name]["verdict"] for r in records).items()))
                        for name in (*VALIDATORS, "agat")},
            "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with the retained report without writing")
    args = parser.parse_args()
    try:
        index = yaml.safe_load((ROOT / "corpus/index.yaml").read_text())
        expectations = load_expectations()
        retained = {e["id"] for e in index["entries"] if e["tier"] in ("vendored", "derived") and e["format"].startswith("GFF3")}
        if set(expectations) != retained:
            raise ValueError(f"Validator case coverage changed: missing={sorted(retained - set(expectations))}, stale={sorted(set(expectations) - retained)}")
        report = measure(index, binary_path(), expectations=expectations)
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if REPORT.read_text() != rendered:
                raise ValueError("Validity report changed; inspect just validity-report and its diff")
        else:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(rendered)
        for r in report["records"]:
            for name, result in r["validators"].items():
                print(f"{name:12} {result['verdict']:12} {r['id']}")
        print(json.dumps(report["summary"], sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"VALIDITY ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
