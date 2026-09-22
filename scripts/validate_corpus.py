#!/usr/bin/env python3
"""Measure retained GFF3 validity with GenomeTools, independently of our adapters."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import yaml

from install_genometools import ROOT, VERSION, default_binary

REPORT = ROOT / "analyses" / "format-validation" / "report.json"


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
    return {"verdict": status, "exit_code": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.replace(str(binary), "gt").strip()}


def expectation(entry):
    if entry["tier"] != "derived":
        return None
    label = entry.get("validity", "").lower()
    if label.startswith("invalid:"):
        return "rejected"
    if label.startswith("valid gff3:"):
        return "accepted"
    raise ValueError(f"Unrecognized validity label: {entry['id']}: {label}")


def measure(index, binary, root=ROOT):
    check_version(binary)
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
            record.update(verdict(binary, path, root))
            expected = expectation(entry)
            if expected is not None:
                record["expected_from_validity"] = expected
                if record["verdict"] != expected:
                    raise ValueError(f"Validity mismatch for {entry['id']}: expected {expected}, got {record['verdict']}")
        else:
            record.update(verdict="not_checked", reason="No independent validator configured for this format")
        records.append(record)
    return {"report_version": 1, "validator": {"name": "GenomeTools", "version": VERSION,
            "arguments": ["gff3validator"], "ontology_typecheck": False,
            "biological_correctness": "not_measured"},
            "summary": dict(sorted(Counter(r["verdict"] for r in records).items())),
            "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare with the retained report without writing")
    args = parser.parse_args()
    try:
        report = measure(yaml.safe_load((ROOT / "corpus/index.yaml").read_text()), binary_path())
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if REPORT.read_text() != rendered:
                raise ValueError("Validity report changed; inspect just validity-report and its diff")
        else:
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(rendered)
        for r in report["records"]:
            print(f"{r['verdict']:12} {r['id']}")
        print(json.dumps(report["summary"], sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"VALIDITY ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
