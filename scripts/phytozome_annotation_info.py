"""Parse a Phytozome `*.annotation_info.txt` into dialect rows, validate them, and join them to the GFF3.

    python3 scripts/phytozome_annotation_info.py parse FILE [--output JSON]
    python3 scripts/phytozome_annotation_info.py validate FILE [--max-errors N]
    python3 scripts/phytozome_annotation_info.py join GFF3 FILE [--max-errors N]

The dialect schema is model/dialects/phytozome-annotation-info.yaml. `join`
checks that the table and the same genome's gene_exons GFF3 describe the same
transcripts: one table row per mRNA row, matched on pacid, with the same
transcript and gene names. Each file should pass its own `validate` first.
"""
import argparse
import io
import json
from pathlib import Path
import sys

import phytozome_gene_exons as gff3

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/phytozome-annotation-info.yaml"
TARGET = "PhytozomeAnnotationInfoDocument"
ROW_CLASS = "PhytozomeAnnotationInfoRow"
HEADER = ("#pacId", "locusName", "transcriptName", "peptideName", "Pfam", "Panther", "ec", "KOG",
          "KO", "GO", "Best-hit-clamy-name", "Best-hit-clamy-defline", "Best-hit-rice-name",
          "Best-hit-rice-defline")
# "#pacId" becomes pacId, and each Best-hit column the same name in lower
# case with underscores. Every other column keeps its source spelling.
COLUMN_TO_SLOT = {name: (name.lower().replace("-", "_") if name.startswith("Best-hit-") else name.lstrip("#"))
                  for name in HEADER}
LIST_SLOTS = ("Pfam", "Panther", "ec", "KOG", "KO", "GO")
PAC = "PAC:"


# One error type for both dialects, since this parser reuses the GFF3 line reader.
DialectError = gff3.DialectError


def parse_row(line_number, text):
    cells = text.split("\t")
    if len(cells) != len(HEADER):
        raise DialectError(f"line {line_number}: {len(cells)} columns, expected {len(HEADER)}")
    row = {"line": line_number}
    for column, cell in zip(HEADER, cells):
        if cell == "":
            continue
        slot = COLUMN_TO_SLOT[column]
        if slot in LIST_SLOTS:
            values = cell.split(" ")
            if "" in values:
                raise DialectError(f"line {line_number}: {column} {cell!r} has an empty value")
            row[slot] = values
        else:
            row[slot] = cell
    return row


def parse_lines(lines, source_file):
    rows, number = [], 0
    for number, raw in enumerate(lines, start=1):
        text = gff3.strip(number, raw)
        if number == 1:
            if tuple(text.split("\t")) != HEADER:
                raise DialectError(f"line 1: header is not the {len(HEADER)} Phytozome columns")
            continue
        if not text:
            raise DialectError(f"line {number}: blank line")
        if text.startswith("#"):
            raise DialectError(f"line {number}: comment after the header")
        rows.append(parse_row(number, text))
    if number == 0:
        raise DialectError("line 1: empty file, expected a header")
    return {"source_file": str(source_file), "rows": rows}


def parse(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return parse_lines(handle, path)


LINE_BREAKS = ("\t", "\n", "\r")


def write_row(row):
    cells = []
    for column in HEADER:
        slot = COLUMN_TO_SLOT[column]
        value = row.get(slot)
        where = f"line {row.get('line', '?')} {column}"
        if value is None:
            cells.append("")
            continue
        if slot in LIST_SLOTS:
            for item in value:
                gff3.checked(str(item), where, LINE_BREAKS + (" ",))
            value = " ".join(value)
        cells.append(gff3.checked(str(value), where, LINE_BREAKS))
    return "\t".join(cells)


def write(document):
    """Table text for a document, refused unless it parses back to the same rows."""
    text = "\t".join(HEADER) + "\n" + "".join(write_row(row) + "\n" for row in document["rows"])
    reparsed = parse_lines(io.StringIO(text, newline=""), document.get("source_file", ""))
    for row, again in zip(document["rows"], reparsed["rows"], strict=True):
        if {**row, "line": 0} != {**again, "line": 0}:
            changed = sorted(k for k in set(row) | set(again) if row.get(k) != again.get(k))
            raise DialectError(f"line {row.get('line', '?')}: written text parses back differently in {changed}")
    return text


def cross_checks(document):
    """Rules a schema can't express, each holding on every row of the measured file."""
    problems = []
    seen = {"pacId": set(), "transcriptName": set()}
    for row in document["rows"]:
        where = f"line {row['line']}"
        for slot, values in seen.items():
            if row.get(slot) in values:
                problems.append(f"{where}: {slot} {row.get(slot)!r} repeats")
            values.add(row.get(slot))
        if not gff3.is_transcript_name(row.get("transcriptName"), row.get("locusName")):
            problems.append(f"{where}: transcriptName is not locusName plus '.' and a number")
        if row.get("peptideName") != row.get("transcriptName"):
            problems.append(f"{where}: peptideName differs from transcriptName")
        for slot in LIST_SLOTS:
            values = row.get(slot, [])
            if len(values) != len(set(values)):
                problems.append(f"{where}: {slot} repeats a value")
        for species in ("clamy", "rice"):
            if f"best_hit_{species}_defline" in row and f"best_hit_{species}_name" not in row:
                problems.append(f"{where}: Best-hit-{species}-defline without its name")
    return problems


def problems(document):
    """Schema and cross-row problems for a parsed document; empty means valid."""
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    # See phytozome_gene_exons.schema_validator: the generated schema is closed either way.
    validator = Validator(str(SCHEMA), validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    report = validator.validate(document, TARGET)
    rows = document["rows"]
    messages = [gff3.ROW_PATH.sub(lambda m: f"/line {rows[int(m.group(1))]['line']}", result.message)
                for result in report.results]
    return messages + cross_checks(document)


def gff3_transcripts(path):
    """{pacid: (mRNA Name, gene Name, line)} from a gene_exons GFF3, read as a stream."""
    transcripts, gene_names, problems = {}, {}, []
    with gff3.open_text(path) as handle:
        lines = iter(handle)
        gff3.read_header(lines)
        for row in gff3.iter_rows(lines, gff3.row_slots()):
            if row.get("type") == "gene":
                gene_names[row.get("ID")] = row.get("Name")
            elif row.get("type") == "mRNA":
                pacid = str(row.get("pacid"))
                if pacid in transcripts:
                    problems.append(f"GFF3 line {row['line']}: pacid {pacid} repeats line {transcripts[pacid][2]}")
                    continue
                transcripts[pacid] = (row.get("Name"), gene_names.get(row.get("Parent")), row["line"])
    return transcripts, problems


def join_problems(transcripts, document):
    """Differences between GFF3 mRNA rows and table rows, matched on pacid."""
    problems = []
    unmatched = dict(transcripts)
    for row in document["rows"]:
        where = f"line {row['line']}"
        pac = str(row.get("pacId", ""))
        pacid = pac[len(PAC):] if pac.startswith(PAC) else None
        found = unmatched.pop(pacid, None)
        if found is None:
            known = pacid in transcripts
            problems.append(f"{where}: {pac!r} " + ("repeats an earlier table row" if known
                                                      else "is not the pacid of any GFF3 mRNA row"))
            continue
        name, gene_name, line = found
        if row.get("transcriptName") != name:
            problems.append(f"{where}: transcriptName {row.get('transcriptName')!r} is not GFF3 line {line} Name {name!r}")
        if row.get("locusName") != gene_name:
            problems.append(f"{where}: locusName {row.get('locusName')!r} is not the gene Name {gene_name!r}")
    for pacid, (name, _, line) in unmatched.items():
        problems.append(f"GFF3 line {line}: mRNA {name!r} pacid {pacid} has no table row")
    return problems


def report(path, found, count, max_errors):
    for message in found[:max_errors]:
        print(f"  {message}")
    if len(found) > max_errors:
        print(f"  ... {len(found) - max_errors} more")
    status = "VALID" if not found else "INVALID"
    print(f"{status:8} {path}: {count} rows, {len(found)} problem(s)")
    return 0 if not found else 1


def validate(path, max_errors=20):
    try:
        document = parse(path)
    except (DialectError, *gff3.READ_ERRORS) as error:
        print(f"INVALID  {path}: {error}")
        return 1
    return report(path, problems(document), len(document["rows"]), max_errors)


def join(gff3_path, path, max_errors=20):
    try:
        transcripts, found = gff3_transcripts(gff3_path)
        document = parse(path)
    except (DialectError, gff3.DialectError, *gff3.READ_ERRORS) as error:
        print(f"INVALID  {error}")
        return 1
    found += join_problems(transcripts, document)
    print(f"GFF3 {gff3_path}: {len(transcripts)} mRNA rows")
    return report(path, found, len(document["rows"]), max_errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    parse_cmd = commands.add_parser("parse")
    parse_cmd.add_argument("file", type=Path)
    parse_cmd.add_argument("--output", type=Path)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("file", type=Path)
    validate_cmd.add_argument("--max-errors", type=int, default=20)
    join_cmd = commands.add_parser("join")
    join_cmd.add_argument("gff3", type=Path)
    join_cmd.add_argument("file", type=Path)
    join_cmd.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.file, args.max_errors)
    if args.command == "join":
        return join(args.gff3, args.file, args.max_errors)
    try:
        document = parse(args.file)
    except (DialectError, *gff3.READ_ERRORS) as error:
        print(f"INVALID  {args.file}: {error}", file=sys.stderr)
        return 1
    text = json.dumps(document, indent=1)
    if args.output:
        return gff3.write_output(args.output, text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
