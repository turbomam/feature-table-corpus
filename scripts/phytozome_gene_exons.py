"""Parse a Phytozome `*.gene_exons.gff3` into dialect rows, and validate them.

    python3 scripts/phytozome_gene_exons.py parse FILE [--output JSON]
    python3 scripts/phytozome_gene_exons.py validate FILE [--max-errors N]

FILE may be gzip-compressed. `validate` reads the file as a stream and
validates rows in chunks, so a whole genome is never held as one document.
The dialect schema is model/dialects/phytozome-gene-exons-gff3.yaml. This step
checks the input against its own dialect only; mapping to the feature model is
a separate step.
"""
import argparse
import gzip
import io
import json
from pathlib import Path
import re
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/phytozome-gene-exons-gff3.yaml"
TARGET = "PhytozomeGeneExonsDocument"
ROW_CLASS = "PhytozomeGeneExonsRow"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}
PARTS = ("exon", "CDS", "five_prime_UTR", "three_prime_UTR")
# Column 9 keys in the order every row of the measured file writes them.
KEY_ORDER = {
    "gene": ["ID", "Name"],
    "mRNA": ["ID", "Name", "pacid", "longest", "Parent"],
    **{part: ["ID", "Parent", "pacid"] for part in PARTS},
}
CHUNK = 5000


class DialectError(ValueError):
    pass


def row_slots(schema=SCHEMA):
    """Return {slot name: induced slot} for the row class, read from the schema itself."""
    from linkml_runtime import SchemaView
    view = SchemaView(str(schema))
    return {slot.name: slot for slot in view.class_induced_slots(ROW_CLASS)}


def open_text(path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, encoding="utf-8", newline="")


# What a malformed or unreadable input raises while it is read. zlib.error, from a
# corrupted gzip body, is not an OSError.
READ_ERRORS = (OSError, EOFError, UnicodeDecodeError, zlib.error)


def strip(number, raw):
    """A line's text, refused unless it ends in LF alone, as every measured line does."""
    # Checked first: the reader also ends a line at a bare CR, so that line lacks LF too.
    if "\r" in raw:
        raise DialectError(f"line {number}: carriage return; this dialect writes LF line endings")
    if not raw.endswith("\n"):
        raise DialectError(f"line {number}: no final newline")
    return raw[:-1]


# The only integer spelling in the measured file. int() also accepts a sign,
# leading zeros, surrounding spaces, underscores and non-ASCII digits, and would
# turn them into a value the writer spells differently.
CANONICAL_INTEGER = re.compile(r"(0|[1-9][0-9]*)")


def integer(text):
    if not CANONICAL_INTEGER.fullmatch(text):
        raise ValueError(text)
    return int(text)


def read_header(lines):
    """Read the two directive lines that open every file, from an iterator."""
    found = {}
    for number, (key, directive) in enumerate((("gff_version", "##gff-version"),
                                               ("annot_version", "##annot-version")), start=1):
        raw = next(lines, None)
        if raw is None:
            raise DialectError(f"line {number}: expected '{directive} <value>', found end of file")
        text = strip(number, raw)
        name, _, value = text.partition(" ")
        if name != directive or not value:
            raise DialectError(f"line {number}: expected '{directive} <value>', found {text!r}")
        found[key] = value
    return found


def parse_row(line_number, text, slots):
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"line {line_number}: {len(columns)} columns, expected 9")
    row = {"line": line_number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if name == "score":
            if value != ".":
                raise DialectError(f"line {line_number}: score {value!r}; this dialect writes none")
            continue
        if value == "." and name == "phase":
            continue
        row[name] = value
    for name in ("start", "end", "phase"):
        if name in row:
            try:
                row[name] = integer(row[name])
            except ValueError:
                raise DialectError(f"line {line_number}: {name} {row[name]!r} is not a number") from None
    for pair in columns[8].split(";"):
        if not pair:
            raise DialectError(f"line {line_number}: empty attribute")
        key, sep, value = pair.partition("=")
        if not sep:
            raise DialectError(f"line {line_number}: attribute {key!r} has no value")
        # The same set write() refuses, so whatever parses can be written back.
        for character in VALUE_FORBIDDEN:
            if character in key or character in value:
                meaning = RESERVED_MEANING.get(character, f"a raw {character!r}")
                raise DialectError(f"line {line_number}: {key} {value!r} has {meaning}; this dialect writes none")
        row["attribute_order"].append(key)
        if key in CORE:
            raise DialectError(f"line {line_number}: attribute {key!r} names a column, not a column 9 key")
        if key in row:
            raise DialectError(f"line {line_number}: {key} repeats")
        slot = slots.get(key)
        if slot is None or slot.range != "integer":
            # An unknown key is kept so validation reports it as not part of the dialect.
            row[key] = value
            continue
        try:
            row[key] = integer(value)
        except ValueError:
            raise DialectError(f"line {line_number}: {key} {value!r} is not an integer") from None
    return row


def iter_rows(lines, slots, first_line=3):
    for number, raw in enumerate(lines, start=first_line):
        text = strip(number, raw)
        if not text:
            raise DialectError(f"line {number}: blank line")
        if text.startswith("#"):
            raise DialectError(f"line {number}: comment or directive after the two opening directives")
        yield parse_row(number, text, slots)


def parse_lines(lines, source_file, slots=None):
    lines = iter(lines)
    header = read_header(lines)
    rows = list(iter_rows(lines, slots or row_slots()))
    return {"source_file": str(source_file), **header, "rows": rows}


def parse(path, slots=None):
    with open_text(path) as handle:
        return parse_lines(handle, path, slots)


LINE_BREAKS = ("\t", "\n", "\r")
VALUE_FORBIDDEN = LINE_BREAKS + (";", "=", ",", "%", "&")
RESERVED_MEANING = {"%": "a percent escape", ",": "a second value"}


def checked(text, where, forbidden):
    for character in forbidden:
        if character in text:
            raise DialectError(f"{where}: {text!r} contains {character!r}, which this dialect doesn't write")
    return text


def write_row(row):
    where = f"line {row.get('line', '?')}"
    parts = [f"{checked(key, where, VALUE_FORBIDDEN)}={checked(str(row[key]), f'{where} {key}', VALUE_FORBIDDEN)}"
             for key in row["attribute_order"]]
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row["end"]), ".",
               row["strand"], str(row["phase"]) if "phase" in row else ".", ";".join(parts)]
    for column in columns[:8]:
        checked(column, where, LINE_BREAKS)
    return "\t".join(columns)


def write(document):
    """GFF3 text for a document, refused unless it parses back to the same rows."""
    head = (f"##gff-version {document['gff_version']}\n"
            f"##annot-version {document['annot_version']}\n")
    for directive in head.splitlines():
        checked(directive, "directive", LINE_BREAKS)
    text = head + "".join(write_row(row) + "\n" for row in document["rows"])
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise DialectError(f"output can't be encoded as UTF-8: {error}") from None
    reparsed = parse_lines(io.StringIO(text, newline=""), document.get("source_file", ""))
    for key in ("gff_version", "annot_version"):
        if reparsed[key] != document[key]:
            raise DialectError(f"{key} parses back differently")
    for row, again in zip(document["rows"], reparsed["rows"], strict=True):
        if {**row, "line": 0} != {**again, "line": 0}:
            changed = sorted(k for k in set(row) | set(again) if row.get(k) != again.get(k))
            raise DialectError(f"line {row.get('line', '?')}: written text parses back differently in {changed}")
    return text


def span_of(row):
    return row.get("seqid"), row.get("strand"), row.get("start", 0), row.get("end", 0)


def within(child, parent):
    seqid, strand, start, end = span_of(child)
    p_seqid, p_strand, p_start, p_end = span_of(parent)
    return (seqid, strand) == (p_seqid, p_strand) and p_start <= start and end <= p_end


class CrossChecks:
    """Rules a schema can't express, each holding on every row of the measured file.

    Fed one row at a time in file order, so a genome is checked as a stream.
    Genes come in blocks: a gene row, then each of its mRNA rows followed by
    that mRNA's parts. Parts of one type are numbered from 1 in transcription
    order, which is descending coordinates on the minus strand.
    """

    def __init__(self, annot_version):
        self.suffix = f".{annot_version}"
        self.problems = []
        self.ids = set()
        self.pacids = set()
        self.gene = None
        self.mrna = None

    def add(self, row, message):
        self.problems.append(f"line {row.get('line', '?')}: {message}")

    def feed(self, row):
        kind = row.get("type")
        order = row.get("attribute_order", [])
        expected = KEY_ORDER.get(kind)
        if expected is not None and order != expected:
            self.add(row, f"{kind} keys are {order}, expected {expected}")
        identifier = row.get("ID")
        if identifier in self.ids:
            self.add(row, f"ID {identifier!r} repeats")
        self.ids.add(identifier)
        if row.get("start", 0) > row.get("end", 0):
            self.add(row, "start > end")
        if ("phase" in row) != (kind == "CDS"):
            self.add(row, f"phase present on {kind} or missing on CDS")
        if kind == "gene":
            self.start_gene(row)
        elif kind == "mRNA":
            self.start_mrna(row)
        else:
            self.part(row)

    def start_gene(self, row):
        self.close_gene()
        self.gene = {"row": row, "mrnas": []}
        if row.get("ID") != f"{row.get('Name')}{self.suffix}":
            self.add(row, f"gene ID {row.get('ID')!r} is not Name plus {self.suffix!r}")

    def start_mrna(self, row):
        self.close_mrna()
        gene = self.gene["row"] if self.gene else {}
        if self.gene is None or row.get("Parent") != gene.get("ID"):
            self.add(row, f"Parent {row.get('Parent')!r} is not the gene row before this block")
        elif not within(row, gene):
            self.add(row, "mRNA is not inside its gene on the same seqid and strand")
        if row.get("ID") != f"{row.get('Name')}{self.suffix}":
            self.add(row, f"mRNA ID {row.get('ID')!r} is not Name plus {self.suffix!r}")
        if not re.fullmatch(re.escape(f"{gene.get('Name')}.") + r"\d+", str(row.get("Name"))):
            self.add(row, f"mRNA Name {row.get('Name')!r} is not its gene's Name plus a number")
        if row.get("pacid") in self.pacids:
            self.add(row, f"pacid {row.get('pacid')!r} repeats")
        self.pacids.add(row.get("pacid"))
        self.mrna = {"row": row, "parts": {part: [] for part in PARTS}}
        if self.gene is not None:
            self.gene["mrnas"].append(row)

    def part(self, row):
        kind = row.get("type")
        mrna = self.mrna["row"] if self.mrna else {}
        if self.mrna is None or row.get("Parent") != mrna.get("ID"):
            self.add(row, f"Parent {row.get('Parent')!r} is not the mRNA row before this block")
            return
        if row.get("pacid") != mrna.get("pacid"):
            self.add(row, f"pacid {row.get('pacid')!r} differs from its mRNA's {mrna.get('pacid')!r}")
        if not within(row, mrna):
            self.add(row, f"{kind} is not inside its mRNA on the same seqid and strand")
        same = self.mrna["parts"].setdefault(kind, [])
        expected = f"{mrna.get('ID')}.{kind}.{len(same) + 1}"
        if row.get("ID") != expected:
            self.add(row, f"ID {row.get('ID')!r} is not {expected!r}")
        if same:
            previous = same[-1]
            after = (row.get("start", 0) > previous.get("end", 0) if row.get("strand") == "+"
                     else row.get("end", 0) < previous.get("start", 0))
            if not after:
                self.add(row, f"{kind} does not follow the previous {kind} in transcription order")
        same.append(row)

    def close_mrna(self):
        if self.mrna is None:
            return
        row, parts = self.mrna["row"], self.mrna["parts"]
        self.mrna = None
        exons = parts["exon"]
        if not exons or not parts["CDS"]:
            self.add(row, "mRNA has no exon or no CDS")
            return
        if (min(e["start"] for e in exons), max(e["end"] for e in exons)) != (row.get("start"), row.get("end")):
            self.add(row, "mRNA span is not the span of its exons")
        for kind in ("CDS", "five_prime_UTR", "three_prime_UTR"):
            for part in parts[kind]:
                if not any(exon["start"] <= part["start"] and part["end"] <= exon["end"] for exon in exons):
                    self.add(part, f"{kind} is not inside one of its mRNA's exons")

    def close_gene(self):
        self.close_mrna()
        if self.gene is None:
            return
        row, mrnas = self.gene["row"], self.gene["mrnas"]
        self.gene = None
        if not mrnas:
            self.add(row, "gene has no mRNA")
            return
        flagged = sum(1 for mrna in mrnas if mrna.get("longest") == 1)
        if flagged != 1:
            self.add(row, f"gene has {flagged} mRNAs with longest=1, expected 1")
        if (min(m.get("start", 0) for m in mrnas), max(m.get("end", 0) for m in mrnas)) != (row.get("start"), row.get("end")):
            self.add(row, "gene span is not the span of its mRNAs")

    def finish(self):
        self.close_gene()
        return self.problems


def cross_checks(document):
    checks = CrossChecks(document.get("annot_version"))
    for row in document["rows"]:
        checks.feed(row)
    return checks.finish()


def schema_validator():
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    # LinkML's generated JSON Schema already sets additionalProperties false, so an
    # undeclared key is rejected with closed=False too (checked 2026-09-25); closed=True
    # only states the intent. tests/test_phytozome.py checks the rejection itself.
    return Validator(str(SCHEMA), validation_plugins=[JsonschemaValidationPlugin(closed=True)])


ROW_PATH = re.compile(r"/rows/(\d+)")


def schema_problems(validator, header, chunk):
    """Validate one chunk of rows as a document; name rows by source line."""
    report = validator.validate({**header, "rows": chunk}, TARGET)
    return [ROW_PATH.sub(lambda m: f"/line {chunk[int(m.group(1))]['line']}", result.message)
            for result in report.results]


def check_stream(header, rows, validator=None):
    """Schema and cross-row problems for a header and an iterable of rows."""
    validator = validator or schema_validator()
    checks = CrossChecks(header.get("annot_version"))
    found, chunk, count = [], [], 0
    for row in rows:
        count += 1
        checks.feed(row)
        chunk.append(row)
        if len(chunk) == CHUNK:
            found += schema_problems(validator, header, chunk)
            chunk = []
    if chunk or not count:
        found += schema_problems(validator, header, chunk)
    return found + checks.finish(), count


def problems(document):
    """Schema and cross-row problems for a parsed document; empty means valid."""
    header = {key: value for key, value in document.items() if key != "rows"}
    return check_stream(header, document["rows"])[0]


def validate(path, max_errors=20):
    try:
        with open_text(path) as handle:
            lines = iter(handle)
            header = {"source_file": str(path), **read_header(lines)}
            found, count = check_stream(header, iter_rows(lines, row_slots()))
    except (DialectError, *READ_ERRORS) as error:
        print(f"INVALID  {path}: {error}")
        return 1
    for message in found[:max_errors]:
        print(f"  {message}")
    if len(found) > max_errors:
        print(f"  ... {len(found) - max_errors} more")
    status = "VALID" if not found else "INVALID"
    print(f"{status:8} {path}: {count} rows, {len(found)} problem(s)")
    return 0 if not found else 1


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
    except (DialectError, *READ_ERRORS) as error:
        print(f"INVALID  {args.file}: {error}", file=sys.stderr)
        return 1
    text = json.dumps(document, indent=1)
    if args.output:
        return write_output(args.output, text + "\n")
    print(text)
    return 0


def write_output(path, text):
    """Write to a new file only; like the conversion commands, never overwrite."""
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except (OSError, UnicodeEncodeError) as error:
        print(f"output: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
