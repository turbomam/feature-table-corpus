"""Parse an IMG 4.14 `*.assembled.gff` into dialect rows, and validate them.

    python3 scripts/img_assembled_gff.py parse FILE [--output JSON]
    python3 scripts/img_assembled_gff.py validate FILE [--taxon TAXON_GFF] [--max-errors N]

The dialect schema is model/dialects/img-assembled-gff.yaml. Only one file of
this vintage is known, so every cross-row rule here was measured on that file.
With --taxon, the taxon GFF from the same IMG bundle is read too, and every one
of its locus tags must be here at the same coordinates and strand. Number
parsing, the writer's escaping limits and the error type come from
scripts/img_functional_gff.py, so the IMG dialects report problems the same way.
"""
import argparse
import collections
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from img_functional_gff import DialectError, LINE_BREAKS, checked, convert, value_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/img-assembled-gff.yaml"
TARGET = "ImgAssembledGffDocument"
ROW_CLASS = "ImgAssembledGffRow"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}

# Per type: the column 2 tool and the key orders written, measured 2026-09-28.
_RFAM = ("INFERNAL", {("ID", "Model", "RNA_Class_ID", "locus_tag", "product")})
TYPES = {
    "CDS": ("Prodigal", {("ID", "conf", "gc_cont", "locus_tag")}),
    "tRNA": ("INFERNAL", {("ID", "codon", "locus_tag", "product")}),
    "rRNA": ("HMMER", {("ID", "Name", "Type", "locus_tag", "product"),
                       ("ID", "LowScore", "LowScore", "Name", "Type", "locus_tag", "product")}),
    "misc_RNA": _RFAM,
    "misc_bind": _RFAM,
    "misc_feature": _RFAM,
}
COMPLEMENT = str.maketrans("ACGT", "TGCA")
# Canonical spellings only, so every accepted value is written back the same way:
# no sign, no leading zero, ASCII digits (int() also takes "0300", "-0" and "²").
CANONICAL = re.compile(r"0|[1-9][0-9]{0,17}")  # at most 18 digits: fits int64, far below int()'s limit
# ID numbers: canonical, positive and at most 18 digits, so (length, text) orders them numerically.
ID_NUMBER = re.compile(r"[1-9][0-9]{0,17}")
# Taxon GFF column 3 for each assembled type the taxon GFF keeps, measured 2026-09-28.
TAXON_TYPE = {"CDS": "CDS", "tRNA": "tRNA", "rRNA": "rRNA", "misc_RNA": "RNA"}
# Keys written with a fixed number of decimals in every measured row. The parser
# requires that spelling and the writer reproduces it, so these round-trip byte for byte.
DECIMALS = {"conf": 2, "gc_cont": 3}


def row_slots(schema=SCHEMA):
    """Return {slot name: induced slot} for the row class, read from the schema itself."""
    from linkml_runtime import SchemaView
    view = SchemaView(str(schema))
    return {slot.name: slot for slot in view.class_induced_slots(ROW_CLASS)}


def parse_row(line_number, text, slots):
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"line {line_number}: {len(columns)} columns, expected 9")
    row = {"line": line_number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if value == "." and name == "phase":
            continue
        if name == "score":
            if value != ".":
                raise DialectError(f"line {line_number}: score {value!r}; this dialect writes '.'")
            continue
        row[name] = value
    for name in ("start", "end", "phase"):
        if name in row:
            if not CANONICAL.fullmatch(row[name]):
                raise DialectError(f"line {line_number}: {name} {row[name][:40]!r} is not a number of at most 18 digits")
            row[name] = int(row[name])
    if not columns[8].endswith(";"):
        raise DialectError(f"line {line_number}: column 9 does not end with ';'")
    for pair in columns[8][:-1].split(";"):
        if not pair:
            raise DialectError(f"line {line_number}: empty attribute")
        key, sep, value = pair.partition("=")
        if not sep:
            raise DialectError(f"line {line_number}: attribute {key!r} has no value")
        if key in CORE:
            raise DialectError(f"line {line_number}: attribute {key!r} names a column, not a column 9 key")
        slot = slots.get(key)
        if key in row and not (slot is not None and slot.multivalued):
            raise DialectError(f"line {line_number}: {key} repeats")
        row["attribute_order"].append(key)
        if slot is None:
            # Kept under its own name so validation reports it as not part of the dialect.
            row[key] = value
            continue
        places = DECIMALS.get(key)
        if places is not None and not re.fullmatch(rf"(0|[1-9][0-9]*)\.[0-9]{{{places}}}", value):
            raise DialectError(f"line {line_number}: {key} {value!r} is not written with {places} decimals")
        try:
            typed = convert(value, slot)
        except ValueError:
            raise DialectError(f"line {line_number}: {key} {value!r} is not a {slot.range}") from None
        # Other floats must be spelled as the writer spells them, so they write back unchanged.
        if slot.range == "float" and places is None and value_text(typed) != value:
            raise DialectError(f"line {line_number}: {key} {value!r} is not written as {value_text(typed)!r}")
        if slot.multivalued:
            row.setdefault(key, []).append(typed)
        else:
            row[key] = typed
    return row


def parse_lines(lines, source_file, slots=None):
    slots = slots or row_slots()
    rows = []
    for number, raw in enumerate(lines, start=1):
        # Checked first: with newline="" a lone \r also ends a line, and it should
        # be reported as a carriage return, not as a missing newline.
        if "\r" in raw:
            raise DialectError(f"line {number}: carriage return; this dialect writes LF line ends only")
        if not raw.endswith("\n"):
            raise DialectError(f"line {number}: no final newline; this dialect ends every line with one")
        text = raw[:-1]
        if not text:
            raise DialectError(f"line {number}: blank line")
        if text.startswith("#"):
            raise DialectError(f"line {number}: comment or directive; this dialect has none")
        rows.append(parse_row(number, text, slots))
    if not rows:
        raise DialectError("no rows")
    return {"source_file": str(source_file), "rows": rows}


def parse(path, slots=None):
    """Parse a file; unreadable or non-UTF-8 input is a DialectError, not a traceback."""
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return parse_lines(handle, path, slots)
    except UnicodeDecodeError as error:
        raise DialectError(f"not UTF-8: {error}") from None
    except OSError as error:
        raise DialectError(f"can't read: {error}") from None


def write_row(row):
    where = f"line {row.get('line', '?')}"
    parts = []
    taken = collections.Counter()
    for key in row["attribute_order"]:
        value = row[key]
        if isinstance(value, list):
            value = value[taken[key]]
            taken[key] += 1
        spelled = f"{value:.{DECIMALS[key]}f}" if key in DECIMALS else value_text(value)
        text = checked(spelled, f"{where} {key}", LINE_BREAKS + (";",))
        parts.append(f"{checked(key, where, LINE_BREAKS + (';', '='))}={text}")
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row["end"]), ".",
               row["strand"], str(row["phase"]) if "phase" in row else ".", ";".join(parts) + ";"]
    for column in columns[:8]:
        checked(column, where, LINE_BREAKS)
    return "\t".join(columns)


def write(document):
    """GFF text for a document, refused unless it parses back to the same rows."""
    text = "".join(write_row(row) + "\n" for row in document["rows"])
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise DialectError(f"output can't be encoded as UTF-8: {error}") from None
    # newline="" splits only where a file read would; splitlines() would also split
    # at characters such as a form feed inside a value.
    reparsed = parse_lines(io.StringIO(text, newline=""), document.get("source_file", ""))
    for row, again in zip(document["rows"], reparsed["rows"], strict=True):
        if {**row, "line": 0} != {**again, "line": 0}:
            changed = sorted(k for k in set(row) | set(again) if row.get(k) != again.get(k))
            raise DialectError(f"line {row.get('line', '?')}: written text parses back differently in {changed}")
    return text


def row_checks(row):
    """Problems in one row: its type's tool and key order, and its own values."""
    where = f"line {row['line']}"
    problems = []
    kind = row.get("type")
    tool, orders = TYPES.get(kind, (None, set()))
    if tool and not str(row.get("source", "")).startswith(tool + " "):
        problems.append(f"{where}: source {row.get('source')!r} is not what writes {kind} rows")
    if tool and tuple(row.get("attribute_order", ())) not in orders:
        problems.append(f"{where}: keys {row.get('attribute_order')} are not a {kind} key order")
    if row.get("start", 0) > row.get("end", 0):
        problems.append(f"{where}: start > end")
    if ("phase" in row) != (kind == "CDS"):
        problems.append(f"{where}: phase present on {kind} or missing on CDS")
    if kind == "CDS" and (row.get("end", 0) - row.get("start", 0) + 1) % 3:
        problems.append(f"{where}: CDS length is not a multiple of 3")
    if not str(row.get("ID", "")).startswith(f"{row.get('seqid')}."):
        problems.append(f"{where}: ID {row.get('ID')!r} does not start with its contig {row.get('seqid')!r}")
    if kind == "tRNA":
        anticodon = str(row.get("product", "")).rsplit("_", 1)[-1]
        if row.get("codon") != anticodon.translate(COMPLEMENT)[::-1]:
            problems.append(f"{where}: codon {row.get('codon')!r} is not the reverse complement of {anticodon!r}")
    if kind == "rRNA" and not row.get("Name") == row.get("Type") == row.get("product"):
        problems.append(f"{where}: rRNA Name, Type and product differ")
    scores = row.get("LowScore") or []
    if len(set(scores)) > 1:
        problems.append(f"{where}: LowScore values differ")
    return problems


def cross_checks(document):
    """Rules a schema can't express, each holding on every row of the one measured file.

    Rows come in one block per contig, ordered by start. Within a contig, the ID
    number increases and the locus tag counter runs 1, 2, 3 in file order. Each
    Rfam Model has one accession. See row_checks for the rules within a row.
    """
    problems = []
    blocks = []
    models = {}
    seen, tags = set(), set()
    for row in document["rows"]:
        problems.extend(row_checks(row))
        where = f"line {row['line']}"
        if row.get("ID") in seen:
            problems.append(f"{where}: ID {row.get('ID')!r} repeats")
        seen.add(row.get("ID"))
        if not ID_NUMBER.fullmatch(str(row.get("ID", "")).rsplit(".", 1)[-1]):
            problems.append(f"{where}: ID {str(row.get('ID'))[:60]!r} does not end in a number from 1, without leading zeros")
        if row.get("locus_tag") in tags:
            problems.append(f"{where}: locus_tag {row.get('locus_tag')!r} repeats")
        tags.add(row.get("locus_tag"))
        if "Model" in row:
            if models.setdefault(row["Model"], row.get("RNA_Class_ID")) != row.get("RNA_Class_ID"):
                problems.append(f"{where}: Model {row['Model']!r} has two accessions")
        if blocks and blocks[-1][0] == row.get("seqid"):
            blocks[-1][1].append(row)
        else:
            blocks.append((row.get("seqid"), [row]))
    contigs = set()
    for seqid, rows in blocks:
        if seqid in contigs:
            problems.append(f"line {rows[0]['line']}: contig {seqid} rows are not in one block")
        contigs.add(seqid)
        previous = None
        for count, row in enumerate(rows, start=1):
            where = f"line {row['line']}"
            if row.get("locus_tag") != f"{seqid}{count}":
                problems.append(f"{where}: locus_tag {row.get('locus_tag')!r} is not {seqid}{count}")
            number = str(row.get("ID", "")).rsplit(".", 1)[-1]
            if previous is not None:
                # Digit strings order by (length, text), with no int() to overflow.
                if (not ID_NUMBER.fullmatch(number) or not ID_NUMBER.fullmatch(previous[0])
                        or (len(number), number) <= (len(previous[0]), previous[0])):
                    problems.append(f"{where}: ID number does not increase within {seqid}")
                if row.get("start", 0) < previous[1]:
                    problems.append(f"{where}: start is before the previous row's on {seqid}")
            previous = (number, row.get("start", 0))
    return problems


def taxon_checks(document, taxon_path):
    """The taxon GFF from the same bundle holds the same features, less misc_bind and misc_feature.

    The taxon GFF is read with its own dialect's parser (scripts/img_taxon_bundle.py),
    which refuses malformed rows and repeated keys. Every taxon row has a locus tag
    found here, on the same contig at the same coordinates and strand, with the
    corresponding type (the taxon GFF writes misc_RNA as RNA), and every row here
    except misc_bind and misc_feature is in the taxon GFF.
    """
    import img_taxon_bundle as taxon_dialect
    try:
        rows = taxon_dialect.parse_gff_lines(taxon_dialect.text_lines(taxon_path))
    except taxon_dialect.DialectError as error:
        return [f"--taxon: {error}"]
    strands = {"1": "+", "-1": "-"}
    here = {row.get("locus_tag"): row for row in document["rows"]}
    problems = []
    taken = set()
    for taxon in rows:
        where = f"{Path(taxon_path).name} line {taxon['line']}"
        tag = taxon.get("locus_tag")
        if tag is None:
            problems.append(f"{where}: no locus_tag")
            continue
        if tag in taken:
            problems.append(f"{where}: locus_tag {tag} repeats in the taxon GFF")
            continue
        taken.add(tag)
        row = here.get(tag)
        if row is None:
            problems.append(f"{where}: locus_tag {tag} is not in this file")
        elif (row.get("seqid"), row.get("start"), row.get("end"), strands.get(row.get("strand"))) != (
                taxon.get("seqid"), taxon.get("start"), taxon.get("end"), taxon.get("strand")):
            problems.append(f"{where}: locus_tag {tag} has another contig, coordinates or strand here")
        elif TAXON_TYPE.get(row.get("type")) != taxon.get("type"):
            problems.append(f"{where}: locus_tag {tag} is {taxon.get('type')} there but {row.get('type')} here")
    for row in document["rows"]:
        if row.get("type") in TAXON_TYPE and row.get("locus_tag") not in taken:
            problems.append(f"line {row['line']}: {row.get('type')} {row.get('locus_tag')} is not in the taxon GFF")
    return problems


def problems(document, taxon=None):
    """Schema and cross-row problems for a parsed document; empty means valid."""
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    validator = Validator(str(SCHEMA), validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    report = validator.validate(document, TARGET)
    found = [result.message for result in report.results] + cross_checks(document)
    return found + (taxon_checks(document, taxon) if taxon else [])


def validate(path, max_errors=20, taxon=None):
    try:
        document = parse(path)
    except DialectError as error:
        print(f"INVALID  {path}: {error}")
        return 1
    problems_found = problems(document, taxon)
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
    validate_cmd.add_argument("--taxon", type=Path)
    validate_cmd.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.file, args.max_errors, args.taxon)
    try:
        document = parse(args.file)
    except DialectError as error:
        print(f"INVALID  {args.file}: {error}")
        return 1
    text = json.dumps(document, indent=1)
    if not args.output:
        print(text)
        return 0
    try:
        # Mode "x" never overwrites, including a file created since the command started.
        with open(args.output, "x", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except OSError as error:
        print(f"can't write {args.output}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
