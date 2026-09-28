"""Parse an IMG TMHMM (`*_tmh.gff`) or SignalP (`*_cleavage_sites.gff`) file into dialect rows, and validate them.

    python3 scripts/img_tmhmm_signalp_gff.py parse FILE [--output JSON]
    python3 scripts/img_tmhmm_signalp_gff.py validate FILE [--max-errors N]

The dialect schema is model/dialects/img-tmhmm-signalp-gff.yaml. Column 1 is a
gene ID and columns 4 and 5 are protein positions; column 3 is a TMHMM segment
or a SignalP cleavage site. Number parsing, the writer's escaping limits and the
error type come from scripts/img_functional_gff.py, the first IMG dialect, so the
IMG dialects report problems the same way.
"""
import argparse
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from img_functional_gff import DialectError, LINE_BREAKS, checked, convert, finite, integer, value_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/img-tmhmm-signalp-gff.yaml"
TARGET = "ImgTmhmmSignalpGffDocument"
ROW_CLASS = "ImgTmhmmSignalpGffRow"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}

KEY_TO_SLOT = {"D-score": "D_score"}
SLOT_ONLY_NAMES = {slot: key for key, slot in KEY_TO_SLOT.items()}

# Per method: column 3 values, column 2 tool, and the exact column 9 key order.
# Each was the only form seen in its method's files, measured 2026-09-28.
METHODS = {
    "tmh": ({"Inside", "Outside", "TMhelix"}, "decodeanhmm", ("ID",)),
    "cleavage_sites": ({"cleavage_site"}, "signalp", ("D-score", "network", "organism_type")),
}
GENE = re.compile(r"^\S+_(\d+)_(\d+)$")
FILE_METHOD = re.compile(r"_(tmh|cleavage_sites)\.gff$")


def row_slots(schema=SCHEMA):
    """Return {slot name: induced slot} for the row class, read from the schema itself."""
    from linkml_runtime import SchemaView
    view = SchemaView(str(schema))
    return {slot.name: slot for slot in view.class_induced_slots(ROW_CLASS)}


def slot_name(key):
    return KEY_TO_SLOT.get(key, key)


def method_of(feature_type):
    found = [name for name, (types, _, _) in METHODS.items() if feature_type in types]
    return found[0] if found else None


def parse_row(line_number, text, slots):
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"line {line_number}: {len(columns)} columns, expected 9")
    row = {"line": line_number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if value == "." and name in ("score", "phase"):
            continue
        row[name] = value
    for name, kind in (("start", integer), ("end", integer), ("score", finite)):
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
        if key in SLOT_ONLY_NAMES:
            raise DialectError(f"line {line_number}: key {key!r} is spelled {SLOT_ONLY_NAMES[key]!r} in this dialect")
        name = slot_name(key)
        if name in CORE:
            raise DialectError(f"line {line_number}: attribute {key!r} names a column, not a column 9 key")
        if name in row:
            raise DialectError(f"line {line_number}: {key} repeats")
        row["attribute_order"].append(key)
        slot = slots.get(name)
        if slot is None:
            # Kept under its own name so validation reports it as not part of the dialect.
            row[name] = value
            continue
        try:
            row[name] = convert(value, slot)
        except ValueError:
            raise DialectError(f"line {line_number}: {key} {value!r} is not a {slot.range}") from None
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
        raise DialectError("no rows; an empty file has no method to check")
    method = method_of(rows[0]["type"])
    if method is None:
        raise DialectError(f"line 1: column 3 {rows[0]['type']!r} is not a TMHMM segment or SignalP site")
    return {"source_file": str(source_file), "method": method, "rows": rows}


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
    for key in row["attribute_order"]:
        text = checked(value_text(row[slot_name(key)]), f"{where} {key}", LINE_BREAKS + (";",))
        parts.append(f"{checked(key, where, LINE_BREAKS + (';', '='))}={text}")
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row["end"]),
               value_text(row["score"]) if "score" in row else ".", row["strand"],
               str(row["phase"]) if "phase" in row else ".", ";".join(parts)]
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


def residues(seqid):
    """Codons in the gene span that the gene ID records, or None if it records none."""
    gene = GENE.match(seqid or "")
    return (abs(int(gene.group(2)) - int(gene.group(1))) + 1) // 3 if gene else None


def row_checks(row, method, seen):
    """Problems in one row: its method's form, its ID, and its positions."""
    where = f"line {row['line']}"
    types, tool, order = METHODS[method]
    problems = []
    if row.get("type") not in types:
        problems.append(f"{where}: column 3 {row.get('type')!r} is not a {method} row")
    if not str(row.get("source", "")).startswith(tool + " "):
        problems.append(f"{where}: source {row.get('source')!r} is not what {method} files write")
    if tuple(row.get("attribute_order", ())) != order:
        problems.append(f"{where}: keys {row.get('attribute_order')} are not the {method} order {list(order)}")
    if ("score" in row) != (method == "cleavage_sites"):
        problems.append(f"{where}: {'SignalP rows need a score' if method == 'cleavage_sites' else 'TMHMM rows have no score'}")
    start, end = row.get("start", 0), row.get("end", 0)
    if start > end:
        problems.append(f"{where}: start > end")
    length = residues(row.get("seqid"))
    if length is not None and end > length:
        problems.append(f"{where}: end {end} is past the {length} codons of gene {row['seqid']}")
    if method == "tmh":
        expected = f"{row.get('seqid')}_{start}_{end}"
        if row.get("ID") != expected:
            problems.append(f"{where}: ID {row.get('ID')!r} is not {expected!r}")
        if row.get("ID") in seen:
            problems.append(f"{where}: ID {row.get('ID')!r} repeats")
        seen.add(row.get("ID"))
    elif end != start + 1:
        problems.append(f"{where}: a cleavage site spans two residues, so end is start + 1")
    return problems


def gene_checks(seqid, rows):
    """Problems in one gene's TMHMM segments, which tile its protein from residue 1."""
    where = f"line {rows[0]['line']}: gene {seqid}"
    problems = []
    if rows[0].get("start") != 1:
        problems.append(f"{where}: first segment starts at {rows[0].get('start')}, not 1")
    for before, after in zip(rows, rows[1:]):
        if after.get("start") != before.get("end", 0) + 1:
            problems.append(f"line {after['line']}: segment does not start right after the one before")
        if (before.get("type") == "TMhelix") == (after.get("type") == "TMhelix"):
            problems.append(f"line {after['line']}: two helix or two non-helix segments in a row")
    if not any(row.get("type") == "TMhelix" for row in rows):
        problems.append(f"{where}: no TMhelix; genes without one are not listed")
    if "TMhelix" in (rows[0].get("type"), rows[-1].get("type")):
        problems.append(f"{where}: begins or ends with a helix")
    length = residues(seqid)
    # The last segment reaches the protein's end: the residues before the stop codon
    # in every measured gene but two, which end one residue later.
    if length is not None and rows[-1].get("end") not in (length - 1, length):
        problems.append(f"line {rows[-1]['line']}: gene {seqid} ends at residue {rows[-1].get('end')}, "
                        f"not at its protein's end ({length - 1} or {length})")
    sides = [row for row in rows if row.get("type") != "TMhelix"]
    for before, after in zip(sides, sides[1:]):
        if before.get("type") == after.get("type"):
            problems.append(f"line {after['line']}: {after.get('type')} on both sides of a helix")
    return problems


def cross_checks(document):
    """Rules a schema can't express, each holding on every row of the measured files.

    Every row has the document's method: its column 3 values, its column 2 tool
    and its exact key order, and a file named *_tmh.gff or *_cleavage_sites.gff
    must hold that method. Positions end within the protein, whose length is at
    most a third of the gene span that the gene ID records. TMHMM IDs are
    <seqid>_<start>_<end> and unique, and each gene's segments form one block;
    SignalP rows are two residues wide and one per gene.
    """
    method = document.get("method")
    if method not in METHODS:
        return []
    problems = []
    name = Path(str(document.get("source_file", ""))).name
    suffix = FILE_METHOD.search(name)
    if suffix and suffix.group(1) != method:
        problems.append(f"{name}: file name says {suffix.group(1)} but rows are {method}")
    seen = set()
    blocks = []
    for row in document["rows"]:
        problems.extend(row_checks(row, method, seen))
        if blocks and blocks[-1][0] == row.get("seqid"):
            blocks[-1][1].append(row)
        else:
            blocks.append((row.get("seqid"), [row]))
    genes = set()
    for seqid, rows in blocks:
        if seqid in genes:
            kind = "segments are not in one block" if method == "tmh" else "has more than one cleavage site"
            problems.append(f"line {rows[0]['line']}: gene {seqid} {kind}")
        genes.add(seqid)
        if method == "tmh":
            problems.extend(gene_checks(seqid, rows))
        elif len(rows) > 1:
            problems.append(f"line {rows[1]['line']}: gene {seqid} has more than one cleavage site")
    return problems


def problems(document):
    """Schema and cross-row problems for a parsed document; empty means valid."""
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    # closed=True rejects keys the dialect doesn't declare, including a phase.
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
    print(f"{status:8} {path}: {document['method']}, {len(document['rows'])} rows, {len(problems_found)} problem(s)")
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
