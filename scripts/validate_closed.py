#!/usr/bin/env python3
"""Validate closed LinkML shapes and, for Dataset, cross-record invariants.

Usage: python scripts/validate_closed.py SCHEMA DATA_FILE TOP_CLASS

JSON Schema covers types, required fields, enums and numeric bounds. Dataset checks
also cover interval ordering, unique IDs, references, parent cycles and coordinate
spaces. These checks are explicit: JSON Schema cannot compare two fields or resolve
an identifier to another record's translated sequence.
"""
import sys
from pathlib import Path

import jsonschema
import yaml
from linkml.generators.jsonschemagen import JsonSchemaGenerator


def make_validator(schema_path, class_name="Dataset"):
    schema = JsonSchemaGenerator(str(schema_path), not_closed=False).generate()
    selected = {"$defs": schema["$defs"], "$ref": f"#/$defs/{class_name}"}
    return jsonschema.Draft202012Validator(selected, format_checker=jsonschema.FormatChecker())


def dataset_errors(data):
    """Check a structurally valid, self-contained harmonized Dataset.

    This profile uses linear, 1-based inclusive intervals. It is not a validator
    for every legal GFF3 representation (e.g. circular wraparound coordinates).
    Protein positions refer to a direct, contig-relative CDS parent. Translation
    may be absent; then its upper bound cannot be checked and is not guessed.
    """
    errors = []
    indexes = {}
    for collection, key in (("contigs", "contig_id"), ("features", "feature_id")):
        index = {}
        for row in data.get(collection) or []:
            identifier = row[key]
            if identifier in index:
                errors.append(f"{collection}: duplicate {key} {identifier!r}")
            index[identifier] = row
        indexes[collection] = index
    contigs, features = indexes["contigs"], indexes["features"]
    for fid, feature in features.items():
        def error(message):
            errors.append(f"feature {fid!r}: {message}")

        if feature["start"] > feature["end"]:
            error("start must be <= end")
        contig = contigs.get(feature["seqid"])
        if contig is None:
            error(f"unknown seqid {feature['seqid']!r}")
        space = feature["coordinate_system"]
        if space == "contig" and contig and contig.get("length_bp") is not None:
            if feature["end"] > contig["length_bp"]:
                error("end exceeds contig length_bp")
        parents = feature.get("parent") or []
        if space == "protein" and not parents:
            error("protein coordinates require a parent CDS")
        if len(parents) != len(set(parents)):
            error("duplicate parent reference")
        for pid in parents:
            parent = features.get(pid)
            if parent is None:
                error(f"unknown parent {pid!r}")
                continue
            if parent["seqid"] != feature["seqid"]:
                error(f"parent {pid!r} is on a different contig")
            if space == "protein":
                if parent.get("type") != "CDS" or parent["coordinate_system"] != "contig":
                    error(f"protein parent {pid!r} must be a contig-relative CDS")
                translation = parent.get("translated_sequence")
                if translation is not None and feature["end"] > len(translation):
                    error(f"end exceeds translated_sequence length of parent {pid!r}")
            elif parent["coordinate_system"] != "contig":
                error(f"contig-relative feature has protein-relative parent {pid!r}")

    # Iterative traversal avoids recursion limits on long parent chains.
    visited, active = set(), set()
    for fid in features:
        pending = [(fid, False)]
        while pending:
            node, leaving = pending.pop()
            if leaving:
                active.remove(node)
                visited.add(node)
            elif node in active:
                errors.append(f"features: parent cycle involving {node!r}")
            elif node not in visited and node in features:
                active.add(node)
                pending.append((node, True))
                pending.extend((p, False) for p in features[node].get("parent") or [])
    return errors


def validation_errors(data, validator, class_name="Dataset"):
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(data)]
    # Only traverse data whose shape and primitive types have already been checked.
    if not errors and class_name == "Dataset":
        errors.extend(dataset_errors(data))
    return errors


def load_validated(schema_path, data_path):
    data = yaml.safe_load(Path(data_path).read_text())
    errors = validation_errors(data, make_validator(schema_path))
    if errors:
        raise ValueError("Invalid Dataset:\n" + "\n".join(errors))
    return data


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    schema_path, data_path, top_class = sys.argv[1:4]
    data = yaml.safe_load(Path(data_path).read_text())
    errors = validation_errors(data, make_validator(schema_path, top_class), top_class)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{data_path}: {len(errors)} error(s) under the closed {top_class} checks")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
