#!/usr/bin/env python3
"""Validate closed LinkML shapes and, for Dataset, cross-record invariants.

Usage: python scripts/validate_closed.py SCHEMA DATA_FILE TOP_CLASS

JSON Schema covers types, required fields, enums and numeric bounds. Dataset checks
also cover interval ordering, unique IDs, references (including contig membership
in declared collections), parent cycles and coordinate spaces. These checks are explicit: JSON Schema cannot compare two fields or resolve
an identifier to another record's translated sequence.
"""
import json
import math
import re
import sys
from pathlib import Path

import jsonschema
import yaml
from linkml.generators.jsonschemagen import JsonSchemaGenerator
from feature_locations import location_errors


# Assigned NCBI genetic codes, from https://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi
# (read 2026-09-25). 7, 8 and 17 to 20 are unassigned.
NCBI_GENETIC_CODES = frozenset([*range(1, 7), *range(9, 17), *range(21, 34)])


def table_value(text):
    """A translation_table attribute as an integer when it is one, else its text.

    Leading zeros are ignored, so 011 is 11 and 01000 equals 1000. Only up to three digits are
    read as a number: codes stop at 33, and a longer digit string would otherwise reach int()'s
    digit limit, so it stays text with its leading zeros removed.
    """
    if not re.fullmatch(r"[0-9]+", text):
        return text
    digits = text.lstrip("0") or "0"
    return int(digits) if len(digits) <= 3 else digits


def make_validator(schema_path, class_name="Dataset"):
    """A closed validator for one class of the schema; ValueError if it has no such class."""
    schema = JsonSchemaGenerator(str(schema_path), not_closed=False).generate()
    classes = sorted(name for name, definition in schema["$defs"].items() if definition.get("type") == "object")
    if class_name not in classes:
        raise ValueError(f"{class_name!r} is not a class in {schema_path}; classes: {', '.join(classes)}")
    selected = {"$defs": schema["$defs"], "$ref": f"#/$defs/{class_name}"}
    return jsonschema.Draft202012Validator(selected, format_checker=jsonschema.FormatChecker())


def attribute_number_agrees(attribute):
    try:
        return float(attribute["value"]) == float(attribute["numeric_value"])
    except (TypeError, ValueError):
        return False


def dataset_errors(data):
    """Check a structurally valid, self-contained harmonized Dataset.

    Scalar intervals and structured location parts use 1-based inclusive bounds.
    Structured parts are checked for order, overlap, envelope agreement and
    endpoint status; origin crossings require a circular reference of known length.
    This validates the harmonized model, not every source-format representation.
    Protein positions refer to a contig-relative CDS, named both as seqid and as the
    only parent (issue 40). Translation
    may be absent; then its upper bound cannot be checked and is not guessed.
    """
    errors = []
    indexes = {}
    for collection, key in (
        ("contig_collections", "collection_id"), ("contigs", "contig_id"), ("features", "feature_id")
    ):
        index = {}
        for row in data.get(collection) or []:
            identifier = row[key]
            if identifier in index:
                errors.append(f"{collection}: duplicate {key} {identifier!r}")
            index[identifier] = row
        indexes[collection] = index
    contigs, features = indexes["contigs"], indexes["features"]
    # Feature.seqid names a contig or, for protein coordinates, a CDS (issue 40). One ID naming
    # both would let a join on seqid alone mix residues with bases, so the two sets are disjoint.
    for shared in sorted(contigs.keys() & features.keys()):
        errors.append(f"{shared!r} is both a contig_id and a feature_id")
    collections = indexes["contig_collections"]
    # translation_table attributes on contig-coordinate CDS rows, by contig (issue 72).
    cds_tables = {}
    for fid, feature in features.items():
        if feature.get("type") == "CDS" and feature.get("coordinate_system") == "contig":
            for attribute in feature.get("attributes") or []:
                if attribute["key"] == "translation_table":
                    cds_tables.setdefault(feature["seqid"], []).append((fid, attribute["value"]))
    # A gene has at most one representative isoform (issue 48); unset marks are allowed. A mark,
    # true or false, is about a transcript's place among its gene's isoforms, so it needs a parent
    # gene. Gene type names vary by source, so a gene is recognized by structure instead: a
    # top-level feature, one with no parent of its own. An exon or CDS under an mRNA fails this.
    representatives = {}
    for fid, feature in features.items():
        if feature.get("is_representative") is None:
            continue
        parents = feature.get("parent") or []
        if not parents:
            errors.append(f"feature {fid!r}: is_representative needs a parent gene")
        for pid in parents:
            if (features.get(pid) or {}).get("parent"):
                errors.append(f"feature {fid!r}: is_representative parent {pid!r} is not a top-level "
                              "feature, so it is not a gene")
        if feature.get("is_representative") is True:
            for pid in feature.get("parent") or []:
                representatives.setdefault(pid, []).append(fid)
    for pid, fids in representatives.items():
        if len(fids) > 1:
            errors.append(f"feature {pid!r}: more than one representative isoform ({', '.join(map(repr, fids))})")
    for cid, contig in contigs.items():
        members = contig.get("member_of") or []
        if len(members) != len(set(members)):
            errors.append(f"contig {cid!r}: duplicate member_of reference")
        for collection_id in members:
            if collection_id not in collections:
                errors.append(f"contig {cid!r}: unknown member_of collection {collection_id!r}")
        table = contig.get("translation_table")
        if table is not None and table not in NCBI_GENETIC_CODES:
            errors.append(f"contig {cid!r}: translation_table {table} is not an assigned NCBI genetic code")
        if contig.get("topology") == "circular" and not contig.get("length_bp"):
            errors.append(f"contig {cid!r}: circular topology requires length_bp")
        cds_values = cds_tables.get(cid, [])
        if len({table_value(value) for _, value in cds_values}) > 1:
            # The same conflict the converters refuse, whether or not the contig has a table.
            listed = ", ".join(f"{value!r} on {fid!r}" for fid, value in cds_values)
            errors.append(f"contig {cid!r}: CDS translation_table attributes disagree ({listed})")
        if table is not None:
            for fid, value in cds_values:
                if table_value(value) != table:
                    errors.append(f"contig {cid!r}: translation_table {table} disagrees with "
                                  f"CDS {fid!r} translation_table attribute {value!r}")
    for fid, feature in features.items():
        def error(message):
            errors.append(f"feature {fid!r}: {message}")

        if feature["start"] > feature["end"]:
            error("start must be <= end")
        for attribute in feature.get("attributes") or []:
            # numeric_value is value read as a number (issue 42), so the two must agree.
            if attribute.get("numeric_value") is not None and not attribute_number_agrees(attribute):
                error(f"attribute {attribute['key']!r}: numeric_value {attribute['numeric_value']!r} "
                      f"disagrees with value {attribute['value']!r}")
        target = feature.get("target")
        if target and target["target_start"] > target["target_end"]:
            error("target_start must be <= target_end")
        space, seqid = feature["coordinate_system"], feature["seqid"]
        if space == "protein":
            # Protein positions are measured along the translation of the CDS that seqid names,
            # so seqid is that CDS and its contig is one step further (issue 40).
            landmark = features.get(seqid)
            contig = contigs.get(landmark["seqid"]) if landmark else None
            if landmark is None:
                hint = "; protein coordinates need their CDS as seqid, not a contig" if seqid in contigs else ""
                error(f"unknown protein seqid {seqid!r}{hint}")
            elif landmark.get("type") != "CDS" or landmark["coordinate_system"] != "contig":
                error(f"protein seqid {seqid!r} must be a contig-relative CDS")
        else:
            contig = contigs.get(seqid)
            if contig is None:
                hint = "; contig coordinates need a contig as seqid" if seqid in features else ""
                error(f"unknown seqid {seqid!r}{hint}")
        for problem in location_errors(feature, contig):
            error(problem)
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
            if space == "protein" and pid != seqid:
                error(f"protein parent {pid!r} must be the CDS named by seqid {seqid!r}")
            elif space != "protein" and parent["seqid"] != seqid:
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


def _no_constant(name):
    raise ValueError(f"{name} is not a JSON number")


def _check_values(data):
    """Refuse a non-finite float, or a container that contains itself (a YAML alias can build one).

    Iterative, with one iterator per nesting level, so this walk neither recurses
    nor builds a list of every child. A problem's path is built from the frames
    only when it is reported. A container shared without a cycle, as a repeated
    YAML alias makes, is checked once.
    """
    def children(value):
        return iter(value.items()) if isinstance(value, dict) else enumerate(value)

    def path(frames, key):
        keys = [frame[2] for frame in frames[1:]] + ([key] if frames else [])
        parts = [f"[{k!r}]" for k in keys]
        if len(parts) > 20:
            parts = parts[:5] + [f"...({len(parts) - 10} more)..."] + parts[-5:]
        return "data" + "".join(parts)

    active, done = set(), set()
    frames = []  # (container, iterator over its children, key it sits under)
    pending = [(data, None)]
    while pending or frames:
        if pending:
            value, key = pending.pop()
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{path(frames, key)} is not a finite number")
            if isinstance(value, (dict, list)) and id(value) not in done:
                if id(value) in active:
                    raise ValueError(f"{path(frames, key)} contains itself")
                active.add(id(value))
                frames.append((value, children(value), key))
            continue
        container, items, _ = frames[-1]
        step = next(items, None)
        if step is None:
            frames.pop()
            active.discard(id(container))
            done.add(id(container))
        else:
            pending.append((step[1], step[0]))


def load_data(data_path):
    """A file whose suffix is .json, in any case, is read as JSON, anything else as YAML.

    PyYAML follows YAML 1.1, which reads 1e-05 (as json.dumps writes it) as a string.
    NaN and Infinity, which json.load accepts by default, are not JSON and are refused,
    and so is any non-finite float either format yields (1e400 in JSON, .inf in YAML).
    Both loaders recurse, so nesting deeper than they can follow is a ValueError too.
    """
    path = Path(data_path)
    try:
        if path.suffix.lower() == ".json":
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle, parse_constant=_no_constant)
        else:
            data = yaml.safe_load(path.read_text())
    except RecursionError:
        raise ValueError("nested too deeply to load") from None
    _check_values(data)
    return data


def load_validated(schema_path, data_path):
    data = load_data(data_path)
    errors = validation_errors(data, make_validator(schema_path))
    if errors:
        raise ValueError("Invalid Dataset:\n" + "\n".join(errors))
    return data


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    schema_path, data_path, top_class = sys.argv[1:4]
    # A missing schema or an unknown class is a usage error, reported before the data is read.
    try:
        validator = make_validator(schema_path, top_class)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    try:
        data = load_data(data_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"{data_path}: {error}", file=sys.stderr)
        return 1
    errors = validation_errors(data, validator, top_class)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{data_path}: {len(errors)} error(s) under the closed {top_class} checks")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
