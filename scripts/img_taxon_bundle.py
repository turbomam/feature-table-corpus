"""Parse an older IMG taxon bundle, `<taxon_oid>.gff` and its `.tab.txt` tables, and validate it.

    python3 scripts/img_taxon_bundle.py parse GFF [--output JSON]
    python3 scripts/img_taxon_bundle.py validate GFF [--max-errors N]

GFF is `<taxon_oid>.gff`; every `<taxon_oid>.<kind>.tab.txt` beside it is read
too, because the tables name genes by the GFF row's ID. The dialect schema is
model/dialects/img-taxon-bundle.yaml, which also records where each rule was
measured. This checks the bundle against its own dialect only.
"""
import argparse
from collections import defaultdict
import glob
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "model/dialects/img-taxon-bundle.yaml"
TARGET = "ImgTaxonBundle"
GFF_CLASS = "ImgTaxonGffRow"
HEADER = "##gff-version 3"
COLUMNS = ("seqid", "source", "type", "start", "end", "score", "strand", "phase")
CORE = {"line", "attribute_order", *COLUMNS}
TABLES = {
    "cog": "CogHit",
    "pfam": "PfamHit",
    "tigrfam": "TigrfamHit",
    "ko": "KoHit",
    "ipr": "IprHit",
    "signalp": "SignalpFeature",
    "tmhmm": "TmhmmFeature",
    "xref": "XrefRow",
}
# Documented in the bundle README.txt but absent from both measured bundles.
UNMEASURED = {"kog.tab.txt", "crispr.txt"}
# Other bundle members the README documents; they hold sequence, not annotation rows.
SEQUENCE_FILES = {"fna", "genes.fna", "genes.faa", "intergenic.fna"}
# Values of a multivalued table cell are separated by "|".
LIST_SEPARATOR = "|"

# Column 9 keys in the order IMG writes them, by feature type.
KEYS_BY_TYPE = {
    "CDS": ["ID", "locus_tag", "product"],
    "rRNA": ["ID", "locus_tag", "product"],
    "tRNA": ["ID", "locus_tag"],
    "RNA": ["ID", "locus_tag"],
    "CRISPR": [],
}
DOMAIN_ID = {
    "SUPERFAMILY": r"SSF[0-9]{5,6}",
    "ProSiteProfiles": r"PS[0-9]{5}",
    "ProSitePatterns": r"PS[0-9]{5}",
    "SMART": r"SM[0-9]{5}",
}
XREF_ID = {"GI": r"[1-9][0-9]*", "GenBank/EMBL": r"[A-Z]{2}_[0-9]+"}
NAMED_ACCESSIONS = {"cog": "cog", "pfam": "pfam", "tigrfam": "tigrfam", "ko": "ko"}
# ASCII digits only (\d also matches Arabic-Indic and full-width digits), no leading
# zeros, and no trailing zeros in a fraction: IMG writes 118, never 0118 or 118.0.
INTEGER = re.compile(r"0|[1-9][0-9]*")
DECIMAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")


class DialectError(ValueError):
    pass


_VIEW = None


def view():
    global _VIEW
    if _VIEW is None:
        from linkml_runtime import SchemaView
        _VIEW = SchemaView(str(SCHEMA))
    return _VIEW


def class_columns(class_name):
    """[(slot name, induced slot)] in the class's declared order, which is the file's column order."""
    schema = view()
    return [(name, schema.induced_slot(name, class_name))
            for name in schema.get_class(class_name).slots if name != "line"]


def convert(text, slot, where):
    """Numbers are unsigned decimals in every measured file; int() and float() accept more."""
    if slot.range == "integer":
        if not INTEGER.fullmatch(text):
            raise DialectError(f"{where}: {text!r} is not an integer")
        return int(text)
    if slot.range == "float":
        if not DECIMAL.fullmatch(text):
            raise DialectError(f"{where}: {text!r} is not a decimal number")
        return float(text)
    return text


def text_lines(path):
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read().split("\n")
    except UnicodeDecodeError as error:
        raise DialectError(f"{path}: not UTF-8 ({error.reason} at byte {error.start})") from None
    except OSError as error:
        raise DialectError(f"{path}: {error.strerror or error}") from None


def body(lines, name):
    """Lines without the final newline's empty tail. Rejects CR, which IMG never writes,
    and a missing final newline, which IMG always writes."""
    if lines == [""]:
        raise DialectError(f"{name}: empty file")
    if lines[-1] != "":
        raise DialectError(f"{name} line {len(lines)}: no final newline")
    lines = lines[:-1]
    for number, text in enumerate(lines, start=1):
        if "\r" in text:
            raise DialectError(f"{name} line {number}: carriage return; this dialect writes LF only")
        if not text:
            raise DialectError(f"{name} line {number}: blank line")
    return lines


def parse_gff_row(number, text):
    where = f"gff line {number}"
    columns = text.split("\t")
    if len(columns) != 9:
        raise DialectError(f"{where}: {len(columns)} columns, expected 9")
    row = {"line": number, "attribute_order": []}
    for name, value in zip(COLUMNS, columns[:8]):
        if value == "." and name in ("score", "phase"):
            continue
        if value == "" and name == "end":
            continue
        row[name] = value
    for name in ("start", "end", "phase"):
        if name in row:
            if not INTEGER.fullmatch(row[name]):
                raise DialectError(f"{where}: {name} {row[name]!r} is not a number")
            row[name] = int(row[name])
    if columns[8] == ".":
        return row
    for pair in columns[8].split(";"):
        if not pair:
            raise DialectError(f"{where}: empty attribute")
        key, sep, value = pair.partition("=")
        if not sep:
            raise DialectError(f"{where}: attribute {key!r} has no value")
        if key in CORE:
            raise DialectError(f"{where}: attribute {key!r} names a column, not a column 9 key")
        if key in row:
            raise DialectError(f"{where}: {key} repeats")
        row["attribute_order"].append(key)
        # Unknown keys are kept, so validation reports them as not part of the dialect.
        row[key] = value
    return row


def parse_gff_lines(lines):
    lines = body(lines, "gff")
    if lines[0] != HEADER:
        raise DialectError(f"gff line 1: {lines[0][:40]!r} is not {HEADER!r}")
    if len(lines) == 1:
        raise DialectError("gff: header only, no feature rows")
    rows = []
    for number, text in enumerate(lines[1:], start=2):
        if text.startswith("#"):
            raise DialectError(f"gff line {number}: comment or directive after the header")
        rows.append(parse_gff_row(number, text))
    return rows


def parse_table_lines(lines, kind):
    columns = class_columns(TABLES[kind])
    names = [name for name, _ in columns]
    lines = body(lines, kind)
    if lines[0].split("\t") != names:
        raise DialectError(f"{kind} line 1: header is not {chr(9).join(names)!r}")
    if len(lines) == 1:
        raise DialectError(f"{kind}: header only; IMG leaves an empty table out of the bundle")
    rows = []
    for number, text in enumerate(lines[1:], start=2):
        where = f"{kind} line {number}"
        cells = text.split("\t")
        if len(cells) != len(names):
            raise DialectError(f"{where}: {len(cells)} columns, expected {len(names)}")
        row = {"line": number}
        for (name, slot), cell in zip(columns, cells):
            if cell == "":
                continue
            if slot.multivalued:
                row[name] = [convert(part, slot, f"{where} {name}") for part in cell.split(LIST_SEPARATOR)]
            else:
                row[name] = convert(cell, slot, f"{where} {name}")
        rows.append(row)
    return rows


def table_paths(gff_path):
    """{kind: path} for every `<taxon_oid>.<kind>.tab.txt` beside the GFF.

    Every other `<taxon_oid>.*` file fails unless it is a sequence file, so a table
    this dialect doesn't read, such as `.crispr.txt` or a renamed `.tab.txt.bak`,
    can't pass unchecked.
    """
    taxon = gff_path.name[:-len(".gff")]
    found = {}
    for path in sorted(gff_path.parent.glob(glob.escape(taxon) + ".*")):
        suffix = path.name[len(taxon) + 1:]
        if suffix == "gff" or suffix in SEQUENCE_FILES:
            continue
        if suffix in UNMEASURED:
            raise DialectError(f"{path.name}: documented in the bundle README but not yet measured")
        kind = suffix[:-len(".tab.txt")] if suffix.endswith(".tab.txt") else None
        if kind not in TABLES:
            raise DialectError(f"{path.name}: not a file this dialect reads")
        found[kind] = path
    return found


def parse(gff_path):
    gff_path = Path(gff_path)
    if not gff_path.name.endswith(".gff"):
        raise DialectError(f"{gff_path}: expected <taxon_oid>.gff")
    document = {"source_file": str(gff_path), "taxon_oid": gff_path.name[:-len(".gff")],
                "rows": parse_gff_lines(text_lines(gff_path))}
    for kind, path in table_paths(gff_path).items():
        document[kind] = parse_table_lines(text_lines(path), kind)
    return document


def value_text(value):
    """IMG writes a whole-number float without a fraction (100, not 100.0) and never pads
    one with trailing zeros, so this spelling reproduces all 26,492 measured values."""
    if isinstance(value, list):
        return LIST_SEPARATOR.join(value_text(part) for part in value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def write_gff_row(row):
    attributes = ";".join(f"{key}={row[key]}" for key in row["attribute_order"]) or "."
    columns = [row["seqid"], row["source"], row["type"], str(row["start"]), str(row.get("end", "")),
               value_text(row["score"]) if "score" in row else ".", row["strand"],
               str(row["phase"]) if "phase" in row else ".", attributes]
    return "\t".join(columns)


def write_table(rows, kind):
    names = [name for name, _ in class_columns(TABLES[kind])]
    lines = ["\t".join(names)]
    lines += ["\t".join(value_text(row[name]) if name in row else "" for name in names) for row in rows]
    return "".join(line + "\n" for line in lines)


def write(document):
    """{file name: text} for a bundle, refused unless every file parses back to the same rows.

    The reparse catches every value the dialect can't hold (a tab, a newline, a
    ";" in a GFF value, a "|" in a GO term) without naming each one.
    """
    taxon = document["taxon_oid"]
    files = {f"{taxon}.gff": HEADER + "\n" + "".join(write_gff_row(row) + "\n" for row in document["rows"])}
    for kind in TABLES:
        if kind in document:
            files[f"{taxon}.{kind}.tab.txt"] = write_table(document[kind], kind)
    for name, text in files.items():
        kind = "gff" if name.endswith(".gff") else name[len(taxon) + 1:-len(".tab.txt")]
        lines = text.split("\n")
        reparsed = parse_gff_lines(lines) if kind == "gff" else parse_table_lines(lines, kind)
        original = document["rows"] if kind == "gff" else document[kind]
        # A newline inside a value also shortens that value, so the comparison
        # reports it before the row counts could differ; strict=True turns any
        # other count difference into an error instead of a silent truncation.
        for row, again in zip(original, reparsed, strict=True):
            if {**row, "line": 0} != {**again, "line": 0}:
                changed = sorted(k for k in set(row) | set(again) if row.get(k) != again.get(k))
                raise DialectError(f"{name} line {row.get('line', '?')}: written text parses back differently in {changed}")
    return files


def gff_checks(rows):
    problems = []
    seen = {"ID": set(), "locus_tag": set()}
    for row in rows:
        where = f"gff line {row['line']}"
        kind = row.get("type")
        crispr = kind == "CRISPR"
        if ("end" in row) == crispr:
            problems.append(f"{where}: end {'present on' if crispr else 'missing on'} {kind}")
        elif not crispr and row.get("start", 0) > row["end"]:
            problems.append(f"{where}: start > end")
        if ("phase" in row) == crispr:
            problems.append(f"{where}: phase {'present on' if crispr else 'missing on'} {kind}")
        expected = KEYS_BY_TYPE.get(kind)
        if expected is not None and row.get("attribute_order") != expected:
            problems.append(f"{where}: {kind} keys {row.get('attribute_order')} are not {expected}")
        for key, values in seen.items():
            if key in row:
                if row[key] in values:
                    problems.append(f"{where}: {key} {row[key]!r} repeats")
                values.add(row[key])
    return problems


def table_checks(document):
    problems = []
    cds = {row.get("ID") for row in document["rows"] if row.get("type") == "CDS"}
    lengths = {}
    for kind in TABLES:
        rows = document.get(kind, [])
        previous = None
        names = {}
        for row in rows:
            where = f"{kind} line {row['line']}"
            gene = row.get("gene_oid")
            if gene not in cds:
                problems.append(f"{where}: gene_oid {gene!r} is not a CDS ID in the GFF")
            if str(previous).isdigit() and str(gene).isdigit() and int(gene) < int(previous):
                problems.append(f"{where}: gene_oid {gene} comes after {previous}; rows are sorted by gene_oid")
            previous = gene if gene is not None else previous
            if "gene_length" in row:
                first = lengths.setdefault(gene, (row["gene_length"], where))
                if first[0] != row["gene_length"]:
                    problems.append(f"{where}: gene_length {row['gene_length']} differs from {first[0]} at {first[1]}")
            for low, high, limit in (("query_start", "query_end", "gene_length"),
                                     ("start_coord", "end_coord", "gene_length"),
                                     ("subj_start", "subj_end", f"{kind}_length")):
                if low in row and high in row:
                    if row[low] > row[high]:
                        problems.append(f"{where}: {low} > {high}")
                    if limit in row and row[high] > row[limit]:
                        problems.append(f"{where}: {high} > {limit}")
            prefix = NAMED_ACCESSIONS.get(kind)
            if prefix and f"{prefix}_id" in row:
                accession = row[f"{prefix}_id"]
                name = names.setdefault(accession, row.get(f"{prefix}_name"))
                if name != row.get(f"{prefix}_name"):
                    problems.append(f"{where}: {accession} is named {row.get(f'{prefix}_name')!r} here and {name!r} earlier")
        checker = {"signalp": signalp_checks, "tmhmm": tmhmm_checks, "ko": ko_checks,
                   "ipr": ipr_checks, "xref": xref_checks}.get(kind)
        if checker:
            problems += checker(rows)
    return problems


def by_gene(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row.get("gene_oid")].append(row)
    return groups


def signalp_checks(rows):
    problems = []
    for gene, group in by_gene(rows).items():
        if len(group) > 1:
            problems.append(f"signalp line {group[1]['line']}: second cleavage site for {gene}")
    for row in rows:
        if "start_coord" in row and row.get("end_coord") != row["start_coord"] + 1:
            problems.append(f"signalp line {row['line']}: a cleavage site spans two adjacent residues")
    return problems


def tmhmm_checks(rows):
    """A gene's segments tile its protein, and exactly one of each adjacent pair is a helix."""
    problems = []
    for gene, group in by_gene(rows).items():
        position = 1
        for index, row in enumerate(group):
            where = f"tmhmm line {row['line']}"
            if row.get("start_coord") != position:
                problems.append(f"{where}: {gene} segment starts at {row.get('start_coord')}, not {position}")
            position = row.get("end_coord", position) + 1
            if index and (row.get("feature_type") == "TMhelix") == (group[index - 1].get("feature_type") == "TMhelix"):
                problems.append(f"{where}: {row.get('feature_type')} follows {group[index - 1].get('feature_type')}")
        last = group[-1]
        if last.get("end_coord") != last.get("gene_length"):
            problems.append(f"tmhmm line {last['line']}: {gene} segments end at {last.get('end_coord')}, "
                            f"not gene_length {last.get('gene_length')}")
    return problems


def short_ec(number):
    """The EC column shortens a name's trailing unknown parts to one: 3.1.-.- is EC:3.1.-."""
    return "EC:" + re.sub(r"(\.-)+$", ".-", number)


def ko_checks(rows):
    """One row per EC number listed at the end of the KO name; one row with no EC when there is none."""
    problems = []
    groups = defaultdict(list)
    for row in rows:
        groups[(row.get("gene_oid"), row.get("ko_id"))].append(row)
    for (gene, ko), group in groups.items():
        listed = re.search(r" \[EC:([^\]]+)\]$", group[0].get("ko_name", ""))
        expected = sorted(short_ec(number) for number in listed.group(1).split(" ")) if listed else [None]
        found = sorted((row.get("EC") for row in group), key=str)
        if found != expected:
            problems.append(f"ko line {group[0]['line']}: {gene} {ko} has EC rows {found}, "
                            f"but its name lists {expected}")
    return problems


def ipr_checks(rows):
    problems = []
    entries = {}
    for row in rows:
        where = f"ipr line {row['line']}"
        pattern = DOMAIN_ID.get(row.get("domaindb"))
        if pattern and not re.fullmatch(pattern, row.get("domainid", "")):
            problems.append(f"{where}: {row.get('domaindb')} accession {row.get('domainid')!r} is not {pattern}")
        if ("iprid" in row) != ("iprdesc" in row):
            problems.append(f"{where}: iprid and iprdesc must both be present or both empty")
        if "go_info" in row and "iprid" not in row:
            problems.append(f"{where}: GO terms without an InterPro entry")
        if "iprid" in row:
            described = (row.get("iprdesc"), row.get("go_info"))
            first = entries.setdefault(row["iprid"], described)
            if first != described:
                problems.append(f"{where}: {row['iprid']} has a different description or GO terms than earlier")
    return problems


def xref_checks(rows):
    problems = []
    for row in rows:
        pattern = XREF_ID.get(row.get("db_name"))
        if pattern and not re.fullmatch(pattern, row.get("id", "")):
            problems.append(f"xref line {row['line']}: {row.get('db_name')} id {row.get('id')!r} is not {pattern}")
    return problems


def cross_checks(document):
    """Rules a schema can't express, each measured on both bundles."""
    return gff_checks(document["rows"]) + table_checks(document)


def problems(document):
    """Schema and cross-row problems for a parsed bundle; empty means valid."""
    from linkml.validator import Validator
    from linkml.validator.plugins import JsonschemaValidationPlugin
    # closed=True rejects keys the dialect doesn't declare, such as a numeric score.
    validator = Validator(str(SCHEMA), validation_plugins=[JsonschemaValidationPlugin(closed=True)])
    report = validator.validate(document, TARGET)
    return [result.message for result in report.results] + cross_checks(document)


def validate(gff_path, max_errors=20):
    try:
        document = parse(gff_path)
    except DialectError as error:
        print(f"INVALID  {gff_path}: {error}")
        return 1
    found = problems(document)
    for message in found[:max_errors]:
        print(f"  {message}")
    if len(found) > max_errors:
        print(f"  ... {len(found) - max_errors} more")
    tables = ", ".join(f"{kind} {len(document[kind])}" for kind in TABLES if kind in document) or "no tables"
    status = "VALID" if not found else "INVALID"
    print(f"{status:8} {gff_path}: {len(document['rows'])} GFF rows; {tables}; {len(found)} problem(s)")
    return 0 if not found else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    parse_cmd = commands.add_parser("parse")
    parse_cmd.add_argument("gff", type=Path)
    parse_cmd.add_argument("--output", type=Path)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("gff", type=Path)
    validate_cmd.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "validate":
        return validate(args.gff, args.max_errors)
    try:
        document = parse(args.gff)
    except DialectError as error:
        print(f"INVALID  {args.gff}: {error}", file=sys.stderr)
        return 1
    text = json.dumps(document, indent=1)
    if args.output:
        try:
            # "x" refuses an existing file or directory instead of replacing it.
            with open(args.output, "x", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as error:
            print(f"{args.output}: not written: {error.strerror or error}", file=sys.stderr)
            return 1
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
