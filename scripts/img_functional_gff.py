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


def slot_name(key):
    return key.replace("-", "_")


def convert(value, slot):
    if slot.range == "integer":
        return int(value)
    if slot.range == "float":
        return float(value)
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
    for name in ("start", "end", "phase"):
        if name in row:
            row[name] = int(row[name])
    if "score" in row:
        row["score"] = float(row["score"])
    for pair in columns[8].split(";"):
        if not pair:
            raise DialectError(f"line {line_number}: empty attribute")
        key, sep, value = pair.partition("=")
        if not sep:
            raise DialectError(f"line {line_number}: attribute {key!r} has no value")
        row["attribute_order"].append(key)
        name = slot_name(key)
        slot = slots.get(name)
        if slot is None or name in CORE:
            # Kept under its own name so validation reports it as not part of the dialect.
            row.setdefault(name, value)
            continue
        if slot.multivalued:
            parts = value.split(",") if name != "shortened" else [value]
            row.setdefault(name, []).extend(convert(part, slot) for part in parts)
        elif name in row:
            raise DialectError(f"line {line_number}: {key} repeats but is single-valued")
        else:
            row[name] = convert(value, slot)
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


def validate(path, max_errors=20):
    from linkml.validator import validate as linkml_validate
    try:
        document = parse(path)
    except DialectError as error:
        print(f"INVALID  {path}: {error}")
        return 1
    report = linkml_validate(document, str(SCHEMA), TARGET)
    problems = [result.message for result in report.results] + cross_checks(document)
    for message in problems[:max_errors]:
        print(f"  {message}")
    if len(problems) > max_errors:
        print(f"  ... {len(problems) - max_errors} more")
    status = "VALID" if not problems else "INVALID"
    print(f"{status:8} {path}: {len(document['rows'])} rows, {len(problems)} problem(s)")
    return 0 if not problems else 1


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
