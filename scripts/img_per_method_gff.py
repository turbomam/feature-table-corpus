"""Parse an IMG per-method hit GFF (`*_pfam.gff`, `*_cog.gff` ...) into dialect rows, and validate them.

    python3 scripts/img_per_method_gff.py parse FILE [--output JSON]
    python3 scripts/img_per_method_gff.py validate FILE [--max-errors N]

The dialect schema is model/dialects/img-per-method-gff.yaml. Column 1 is a
gene ID and columns 4 and 5 are protein positions; column 3 is an accession.
This step checks the input against its own dialect only. Number parsing, the
writer's escaping limits and the error type come from scripts/img_functional_gff.py,
the first IMG dialect, so the two report problems the same way.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from img_functional_gff import DialectError, LINE_BREAKS, checked, convert, finite, integer, value_text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/img-per-method-gff.yaml"
TARGET = "ImgPerMethodGffDocument"
ROW_CLASS = "ImgPerMethodGffRow"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}

# Source keys that are not valid slot names, mapped one by one.
KEY_TO_SLOT = {
    "e-value": "e_value",
    "independent_domain_e-value": "independent_domain_e_value",
    "full_sequence_e-value": "full_sequence_e_value",
}
SLOT_ONLY_NAMES = {slot: key for key, slot in KEY_TO_SLOT.items()}

_HMMER_DOMAIN = ("ID", "fake_percent_id", "alignment_length", "independent_domain_e-value",
                 "full_sequence_e-value", "full_sequence_bitscore", "model_start", "model_end")
# Per method: column 3 accession, column 2 source, and the exact column 9 key
# order. Each was the only form seen in its method's files, measured 2026-09-25.
# Tool versions are left open on purpose: every HMMER row measured is
# "HMMER 3.1b2 (February 2015)" and lastal is 983 or 1456, but versions change.
METHODS = {
    "pfam": (r"PF\d{5}", r"HMMER .+",
             ("ID", "Name", "fake_percent_id", "alignment_length", "e-value", "model_start", "model_end")),
    "cog": (r"COG\d{4}", r"", _HMMER_DOMAIN),
    "ko_ec": (r"KO:K\d{5}(_KO:K\d{5})*(__EC:\d+(\.(\d+|-)){1,3}(_EC:\d+(\.(\d+|-)){1,3})*)?", r"lastal \d+",
              ("ID", "subject_gene_ids", "subject_start", "subject_end", "evalue", "percent_identity",
               "alignment_length", "query_gene_length", "subject_gene_length")),
    "tigrfam": (r"TIGR\d{5}", r"",
                ("ID", "fake_percent_id", "alignment_length", "e-value", "model_start", "model_end")),
    "smart": (r"SM\d{5}", r"", _HMMER_DOMAIN),
    "supfam": (r"\d+", r"HMMER .+", _HMMER_DOMAIN),
    "cath_funfam": (r"\d+\.\d+\.\d+\.\d+", r"HMMER .+", _HMMER_DOMAIN),
}
GENE = re.compile(r"^\S+_(\d+)_(\d+)$")
# Only a known method suffix counts, so "my_sample_cog.gff" is read as cog.
FILE_METHOD = re.compile(r"_(" + "|".join(sorted(METHODS, key=len, reverse=True)) + r")\.gff$")


def row_slots(schema=SCHEMA):
    """Return {slot name: induced slot} for the row class, read from the schema itself."""
    from linkml_runtime import SchemaView
    view = SchemaView(str(schema))
    return {slot.name: slot for slot in view.class_induced_slots(ROW_CLASS)}


def slot_name(key):
    return KEY_TO_SLOT.get(key, key)


def method_of(accession):
    """The one method whose column 3 form matches, or None."""
    found = [name for name, (pattern, _, _) in METHODS.items() if re.fullmatch(pattern, accession or "")]
    return found[0] if len(found) == 1 else None


def parse_row(line_number, text, slots):
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"line {line_number}: {len(columns)} columns, expected 9")
    row = {"line": line_number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if value == "." and name == "phase":
            continue
        row[name] = value
    for name, kind in (("start", integer), ("end", integer), ("score", finite)):
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
            if slot.multivalued:
                row[name] = [convert(part, slot) for part in value.split(",")]
            else:
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
        raise DialectError(f"line 1: column 3 {rows[0]['type']!r} is not an accession of any known method")
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
        value = row[slot_name(key)]
        values = value if isinstance(value, list) else [value]
        forbidden = LINE_BREAKS + (";",) + ((",",) if isinstance(value, list) else ())
        texts = [checked(value_text(v), f"{where} {key}", forbidden) for v in values]
        parts.append(f"{checked(key, where, LINE_BREAKS + (';', '='))}=" + ",".join(texts))
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row["end"]),
               value_text(row["score"]), row["strand"], str(row["phase"]) if "phase" in row else ".",
               ";".join(parts)]
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
    reparsed = parse_lines(text.splitlines(keepends=True), document.get("source_file", ""))
    for row, again in zip(document["rows"], reparsed["rows"], strict=True):
        if {**row, "line": 0} != {**again, "line": 0}:
            changed = sorted(k for k in set(row) | set(again) if row.get(k) != again.get(k))
            raise DialectError(f"line {row.get('line', '?')}: written text parses back differently in {changed}")
    return text


def cross_checks(document):
    """Rules a schema can't express, each measured on the isolate and NMDC files.

    Every row has the document's method: its column 3 form, its column 2 source
    and its exact key order. A file named *_<method>.gff must hold that method.
    IDs are <seqid>_<start>_<end> and unique. start <= end, alignment_length is
    end - start + 1, and the hit ends within the protein, whose length is at most
    a third of the gene's contig span read from the seqid. Model and subject
    positions are in order, and a KO/EC hit ends within query_gene_length.
    """
    problems = []
    method = document.get("method")
    pattern, source, order = METHODS.get(method, (None, None, None))
    name = Path(str(document.get("source_file", ""))).name
    suffix = FILE_METHOD.search(name)
    if suffix and suffix.group(1) != method:
        problems.append(f"{name}: file name says {suffix.group(1)} but rows are {method}")
    seen = set()
    for row in document["rows"]:
        where = f"line {row['line']}"
        if pattern is not None:
            if not re.fullmatch(pattern, row.get("type", "")):
                problems.append(f"{where}: column 3 {row.get('type')!r} is not a {method} accession")
            if not re.fullmatch(source, row.get("source", "")):
                problems.append(f"{where}: source {row.get('source')!r} is not what {method} files write")
            if tuple(row.get("attribute_order", ())) != order:
                problems.append(f"{where}: keys {row.get('attribute_order')} are not the {method} order {list(order)}")
        start, end = row.get("start", 0), row.get("end", 0)
        if start > end:
            problems.append(f"{where}: start > end")
        expected = f"{row.get('seqid')}_{start}_{end}"
        if row.get("ID") != expected:
            problems.append(f"{where}: ID {row.get('ID')!r} is not {expected!r}")
        if row.get("ID") in seen:
            problems.append(f"{where}: ID {row.get('ID')!r} repeats")
        seen.add(row.get("ID"))
        if "alignment_length" in row and row["alignment_length"] != end - start + 1:
            problems.append(f"{where}: alignment_length {row['alignment_length']} is not end - start + 1")
        gene = GENE.match(row.get("seqid", ""))
        if gene:
            residues = (abs(int(gene.group(2)) - int(gene.group(1))) + 1) // 3
            if end > residues:
                problems.append(f"{where}: end {end} is past the {residues} codons of gene {row['seqid']}")
        for first, last in (("model_start", "model_end"), ("subject_start", "subject_end")):
            if first in row and last in row and row[first] > row[last]:
                problems.append(f"{where}: {first} > {last}")
        if "subject_end" in row and "subject_gene_length" in row and row["subject_end"] > row["subject_gene_length"]:
            problems.append(f"{where}: subject_end is past subject_gene_length")
        if "query_gene_length" in row and end > row["query_gene_length"]:
            problems.append(f"{where}: end is past query_gene_length")
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
    if args.output and args.output.exists():
        print(f"refusing to overwrite {args.output}", file=sys.stderr)
        return 2
    try:
        document = parse(args.file)
    except DialectError as error:
        print(f"INVALID  {args.file}: {error}")
        return 1
    text = json.dumps(document, indent=1)
    if args.output:
        try:
            with open(args.output, "x", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as error:
            # A missing directory, or a file created since the check above.
            print(f"can't write {args.output}: {error}", file=sys.stderr)
            return 2
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
