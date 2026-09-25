"""Parse an IMG `*_functional_annotation.gff` into dialect rows, and validate them.

    python3 scripts/img_functional_gff.py parse FILE [--output JSON]
    python3 scripts/img_functional_gff.py validate FILE [--max-errors N]

The dialect schema is model/dialects/img-functional-gff.yaml. This step
checks the input against its own dialect only; mapping to the feature model is
a separate step. Commas split values only for the keys the schema types as
multivalued, because product names and notes contain literal commas.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/img-functional-gff.yaml"
TARGET = "ImgFunctionalGffDocument"
ROW_CLASS = "ImgFunctionalGffRow"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}


def row_slots(schema=SCHEMA):
    """Return {slot name: induced slot} for the row class, read from the schema itself."""
    from linkml_runtime import SchemaView
    view = SchemaView(str(schema))
    return {slot.name: slot for slot in view.class_induced_slots(ROW_CLASS)}


# Multivalued keys that repeat as a key, one value per occurrence, instead of
# taking a comma list. Their values may contain commas.
ONE_VALUE_PER_OCCURRENCE = {"shortened"}

# Source keys that are not valid slot names, mapped one by one. Anything else
# keeps its source spelling, so a key the dialect doesn't write stays unknown.
KEY_TO_SLOT = {"e-value": "e_value"}
SLOT_ONLY_NAMES = {slot: key for key, slot in KEY_TO_SLOT.items()}


def slot_name(key):
    return KEY_TO_SLOT.get(key, key)


def finite(text):
    """float() accepts nan and inf; a GFF number never is either."""
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(text)
    return number


def convert(value, slot):
    if slot.range == "integer":
        return int(value)
    if slot.range == "float":
        return finite(value)
    return value


class DialectError(ValueError):
    pass


def parse_row(line_number, text, slots):
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"line {line_number}: {len(columns)} columns, expected 9")
    row = {"line": line_number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if value == "." and name in ("score", "phase"):
            continue
        row[name] = value
    for name, kind in (("start", int), ("end", int), ("phase", int), ("score", finite)):
        if name in row:
            try:
                row[name] = kind(row[name])
            except ValueError:
                raise DialectError(f"line {line_number}: {name} {row[name]!r} is not a number") from None
    for pair in columns[8].split(";"):
        if not pair:
            raise DialectError(f"line {line_number}: empty attribute")
        key, sep, value = pair.partition("=")
        if not sep:
            raise DialectError(f"line {line_number}: attribute {key!r} has no value")
        row["attribute_order"].append(key)
        if key in SLOT_ONLY_NAMES:
            raise DialectError(f"line {line_number}: key {key!r} is spelled {SLOT_ONLY_NAMES[key]!r} in this dialect")
        name = slot_name(key)
        if name in CORE:
            raise DialectError(f"line {line_number}: attribute {key!r} names a column, not a column 9 key")
        slot = slots.get(name)
        if slot is None:
            # Kept under its own name so validation reports it as not part of the dialect.
            row.setdefault(name, value)
            continue
        if slot.multivalued:
            parts = [value] if name in ONE_VALUE_PER_OCCURRENCE else value.split(",")
            try:
                row.setdefault(name, []).extend(convert(part, slot) for part in parts)
            except ValueError:
                raise DialectError(f"line {line_number}: {key} {value!r} is not a {slot.range}") from None
        elif name in row:
            raise DialectError(f"line {line_number}: {key} repeats but is single-valued")
        else:
            try:
                row[name] = convert(value, slot)
            except ValueError:
                raise DialectError(f"line {line_number}: {key} {value!r} is not a {slot.range}") from None
    return row


def parse(path, slots=None):
    slots = slots or row_slots()
    rows = []
    with open(path, encoding="utf-8", newline="") as handle:
        for number, raw in enumerate(handle, start=1):
            text = raw.rstrip("\n").rstrip("\r")
            if not text:
                raise DialectError(f"line {number}: blank line")
            if text.startswith("#"):
                raise DialectError(f"line {number}: comment or directive; this dialect has none")
            rows.append(parse_row(number, text, slots))
    return {"source_file": str(path), "rows": rows}


def value_text(value):
    """Text for a typed value. A float is written as Python's shortest repr, so a
    source spelling such as 84.50 comes back as 84.5; see the round-trip report."""
    return repr(value) if isinstance(value, float) else str(value)


def occurrences(row):
    """Yield (key, [values]) for each column 9 occurrence, in source order."""
    taken = {}
    for key in row["attribute_order"]:
        name = slot_name(key)
        value = row[name]
        if isinstance(value, list):
            if name in ONE_VALUE_PER_OCCURRENCE:
                index = taken.get(name, 0)
                taken[name] = index + 1
                yield key, [value[index]]
            else:
                yield key, value
        else:
            yield key, [value]


def write_row(row):
    column9 = ";".join(f"{key}=" + ",".join(value_text(v) for v in values)
                       for key, values in occurrences(row))
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row["end"]),
               value_text(row["score"]) if "score" in row else ".", row["strand"],
               str(row["phase"]) if "phase" in row else ".", column9]
    return "\t".join(columns)


def write(document):
    return "".join(write_row(row) + "\n" for row in document["rows"])


def cross_checks(document):
    """Rules a schema can't express, each measured on the isolate files.

    Phase only on CDS; start <= end; strand "." only on CRISPR and repeat_unit;
    IDs built as <seqid>_<start>_<end>, except that a repeat_unit takes its
    CRISPR's ID plus _DR1, _DR2 ... in file order, and its Parent must be a
    CRISPR row in the same file.
    """
    problems = []
    crisprs = {row.get("ID") for row in document["rows"] if row.get("type") == "CRISPR"}
    next_unit = {}
    for row in document["rows"]:
        where = f"line {row['line']}"
        kind = row.get("type")
        if row.get("start", 0) > row.get("end", 0):
            problems.append(f"{where}: start > end")
        if ("phase" in row) != (kind == "CDS"):
            problems.append(f"{where}: phase present on {kind} or missing on CDS")
        if row.get("strand") == "." and kind not in ("CRISPR", "repeat_unit"):
            problems.append(f"{where}: {kind} is unstranded")
        if kind == "repeat_unit":
            parent = row.get("Parent")
            if parent not in crisprs:
                problems.append(f"{where}: Parent {parent!r} is not a CRISPR row")
            next_unit[parent] = next_unit.get(parent, 0) + 1
            expected = f"{parent}_DR{next_unit[parent]}"
        else:
            if "Parent" in row:
                problems.append(f"{where}: Parent on {kind}")
            expected = f"{row.get('seqid')}_{row.get('start')}_{row.get('end')}"
        if row.get("ID") != expected:
            problems.append(f"{where}: ID {row.get('ID')!r} is not {expected!r}")
    return problems


def problems(document):
    """Schema and cross-row problems for a parsed document; empty means valid."""
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    # closed=True rejects keys the dialect doesn't declare; set here rather than
    # relying on the plugin's default.
    validator = Validator(str(SCHEMA), validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    report = validator.validate(document, TARGET)
    return [result.message for result in report.results] + cross_checks(document)


def validate(path, max_errors=20):
    try:
        document = parse(path)
    except DialectError as error:
        print(f"INVALID  {path}: {error}")
        return 1
    problems_found = problems(document)
    for message in problems_found[:max_errors]:
        print(f"  {message}")
    if len(problems_found) > max_errors:
        print(f"  ... {len(problems_found) - max_errors} more")
    status = "VALID" if not problems_found else "INVALID"
    print(f"{status:8} {path}: {len(document['rows'])} rows, {len(problems_found)} problem(s)")
    return 0 if not problems_found else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    parse_cmd = commands.add_parser("parse")
    parse_cmd.add_argument("file", type=Path)
    parse_cmd.add_argument("--output", type=Path)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("file", type=Path)
    validate_cmd.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.file, args.max_errors)
    document = parse(args.file)
    text = json.dumps(document, indent=1)
    if args.output:
        args.output.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
