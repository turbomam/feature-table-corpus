"""Map a Phytozome gene_exons GFF3 and its annotation_info.txt together to the feature model, and back.

    python3 scripts/phytozome_annotation_map.py forward GFF3 TABLE DATASET_JSON [--table-url URL]
    python3 scripts/phytozome_annotation_map.py reverse DATASET_JSON GFF3_OUT TABLE_OUT
    python3 scripts/phytozome_annotation_map.py roundtrip GFF3 TABLE

The table has no positions: one row per transcript, joined to the GFF3's mRNA on
pacid. The GFF3 goes through scripts/phytozome_gene_exons_map.py; each table value
then becomes one Attribute on its mRNA Feature, keyed by the table's column name
(Pfam, Panther, ec, KOG, KO, GO, and the Best-hit columns), with a list column
giving one Attribute per value in table order, and the table's URL is added to the
mRNA's source_files. locusName, transcriptName and peptideName are not stored: they
are the gene's Name, the mRNA's Name, and (in every measured row) the mRNA's Name
again, and a row where they disagree is refused.

The reverse direction rebuilds each table row's text from those Attributes and
parses it with the table dialect's own row parser. Rows are written sorted by
locusName and then by transcript number, the order of the measured table; forward
refuses a table in any other order, since the round trip could not reproduce it.
`roundtrip` requires both written files to equal their sources byte for byte.
"""
import argparse
import json
from pathlib import Path
import sys

import phytozome_annotation_info as table_dialect
import phytozome_gene_exons as gff3_dialect
import phytozome_gene_exons_map as gff3_map
from img_functional_map import canonical, difference, quiet_linkml_map, report_errors, write_output
from img_functional_map import reports_hidden_warnings
from validate_closed import make_validator, validation_errors

MODEL = gff3_map.MODEL
# Columns the Dataset carries as Attributes, in table order; the first four are the join.
VALUE_COLUMNS = table_dialect.HEADER[4:]
VALUE_COLUMN_SET = frozenset(VALUE_COLUMNS)
SLOT = table_dialect.COLUMN_TO_SLOT
LISTS = table_dialect.LIST_SLOTS


def transcript_number(name):
    return int(name.rsplit(".", 1)[1]) if "." in name and name.rsplit(".", 1)[1].isdigit() else -1


def table_order(row):
    return row.get("locusName", ""), transcript_number(row.get("transcriptName", ""))


def forward(gff3_document, table_document, table_url, transformers=None):
    dataset = gff3_map.forward(gff3_document, transformers)
    features = {f["feature_id"]: f for f in dataset["features"]}
    mrnas = {}
    for feature in dataset["features"]:
        if feature["type"] == "mRNA":
            pacid = next(a["value"] for a in feature["attributes"] if a["key"] == "pacid")
            mrnas[pacid] = feature
    rows = table_document["rows"]
    if rows != sorted(rows, key=table_order):
        raise ValueError("table rows are not sorted by locusName and transcript number, "
                         "so the round trip could not reproduce their order")
    seen = set()
    for row in rows:
        where = f"table line {row['line']}"
        pacid = row.get("pacId", "")[len(table_dialect.PAC):]
        mrna = mrnas.get(pacid)
        if mrna is None or pacid in seen:
            raise ValueError(f"{where}: {row.get('pacId')} is not one mRNA of the GFF3")
        seen.add(pacid)
        name = next(a["value"] for a in mrna["attributes"] if a["key"] == "Name")
        gene = features[mrna["parent"][0]]
        gene_name = next(a["value"] for a in gene["attributes"] if a["key"] == "Name")
        if (row.get("locusName"), row.get("transcriptName"), row.get("peptideName")) != (gene_name, name, name):
            raise ValueError(f"{where}: locusName, transcriptName and peptideName are not the gene's Name, "
                             f"the mRNA's Name and the mRNA's Name ({gene_name}, {name})")
        clash = {a["key"] for a in mrna["attributes"]} & VALUE_COLUMN_SET
        if clash:
            raise ValueError(f"{where}: the GFF3 mRNA already has {sorted(clash)}, so a table value "
                             "would be indistinguishable from a GFF3 one")
        for column in VALUE_COLUMNS:
            value = row.get(SLOT[column])
            for item in value if isinstance(value, list) else ([] if value is None else [value]):
                mrna["attributes"].append({"key": column, "value": item})
        mrna["source_files"] = [table_url]
    missing = sorted(set(mrnas) - seen)
    if missing:
        raise ValueError(f"{len(missing)} GFF3 mRNA have no table row, for example pacid {missing[0]}")
    return dataset


def reverse(dataset, gff3_source, table_source, transformers=None, species=None, provenance=None):
    """Return (gff3_document, table_document) that forward maps back to dataset."""
    features = {f.get("feature_id"): f for f in dataset["features"]}
    stripped, rows, urls = [], [], set()
    for feature in dataset["features"]:
        values = [a for a in feature.get("attributes", []) if a["key"] in VALUE_COLUMNS]
        if feature.get("type") != "mRNA":
            if values or feature.get("source_files"):
                raise ValueError(f"{feature.get('feature_id')}: only an mRNA carries table values")
            stripped.append(feature)
            continue
        name = feature.get("feature_id")
        if len(feature.get("source_files") or []) != 1:
            raise ValueError(f"{name}: an mRNA needs exactly one source_files entry, the table's URL")
        urls.add(feature["source_files"][0])
        gff3_part = [a for a in feature.get("attributes", []) if a["key"] not in VALUE_COLUMNS]
        if feature.get("attributes", [])[:len(gff3_part)] != gff3_part:
            raise ValueError(f"{name}: table values are not all after the GFF3's own attributes")
        by_column = {}
        for attribute in values:
            by_column.setdefault(attribute["key"], []).append(attribute["value"])
        if [a["key"] for a in values] != [c for c in VALUE_COLUMNS for _ in by_column.get(c, [])]:
            raise ValueError(f"{name}: table values are not in table column order")
        attrs = {a["key"]: a["value"] for a in gff3_part}
        gene = features.get((feature.get("parent") or [None])[0]) or {}
        gene_name = next((a["value"] for a in gene.get("attributes", []) if a["key"] == "Name"), "")
        cells = [f"{table_dialect.PAC}{attrs.get('pacid', '')}", gene_name, attrs.get("Name", ""), attrs.get("Name", "")]
        for column in VALUE_COLUMNS:
            items = by_column.get(column, [])
            if column not in LISTS and len(items) > 1:
                raise ValueError(f"{name}: {column} has {len(items)} values; the table holds one")
            for item in items:
                for character in table_dialect.LINE_BREAKS + ((" ",) if column in LISTS else ()):
                    if character in item:
                        raise ValueError(f"{name}: {column} value {item!r} contains {character!r}")
            cells.append(" ".join(items))
        try:
            rows.append(table_dialect.parse_row(0, "\t".join(cells)))
        except table_dialect.DialectError as error:
            raise ValueError(f"{name}: {error}") from None
        stripped.append({**{k: v for k, v in feature.items() if k != "source_files"}, "attributes": gff3_part})
    if len(urls) > 1:
        raise ValueError(f"the mRNA source_files name {len(urls)} different table URLs; "
                         "a Dataset holds one annotation_info table")
    rows.sort(key=table_order)
    for number, row in enumerate(rows, start=2):
        row["line"] = number
    gff3_document = gff3_map.reverse({**dataset, "features": stripped}, gff3_source, transformers, species,
                                     provenance)
    table_document = {"source_file": table_source, "rows": rows}
    again = forward(gff3_document, table_document, urls.pop() if urls else "", transformers)
    if canonical(again) != canonical(dataset):
        raise ValueError(f"the dialects can't hold this Dataset without loss: {difference(dataset, again)}")
    return gff3_document, table_document


def parse_inputs(gff3_path, table_path):
    problems = []
    try:
        gff3_document = gff3_dialect.parse(gff3_path)
        table_document = table_dialect.parse(table_path)
    except gff3_dialect.DialectError as error:
        return None, None, [f"dialect: {error}"]
    except gff3_dialect.READ_ERRORS as error:
        return None, None, [f"input: {error}"]
    problems += [f"{gff3_path}: {m}" for m in gff3_dialect.problems(gff3_document)]
    problems += [f"{table_path}: {m}" for m in table_dialect.problems(table_document)]
    return gff3_document, table_document, problems


@reports_hidden_warnings
def roundtrip(gff3_path, table_path):
    """Return (problems, report); no problems means both files came back byte for byte."""
    report = {"gff3": str(gff3_path), "table": str(table_path)}
    gff3_document, table_document, problems = parse_inputs(gff3_path, table_path)
    if problems:
        return problems, report
    transformers = gff3_map._transformers()
    url = Path(table_path).resolve().as_uri()
    try:
        dataset = forward(gff3_document, table_document, url, transformers)
    except ValueError as error:
        return [f"model: {error}"], report
    problems += [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back_gff3, back_table = reverse(dataset, str(gff3_path), str(table_path), transformers,
                                        gff3_document.get("species"), gff3_document.get("provenance"))
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    with gff3_dialect.open_text(gff3_path) as handle:
        gff3_original = handle.read()
    with open(table_path, encoding="utf-8", newline="") as handle:
        table_original = handle.read()
    for label, module, document, original in (("GFF3", gff3_dialect, back_gff3, gff3_original),
                                              ("table", table_dialect, back_table, table_original)):
        try:
            written = module.write(document)
        except module.DialectError as error:
            problems.append(f"{label}: write: {error}")
            continue
        if written != original:
            problems.append(f"{label}: written text differs from the source")
    mrnas = [f for f in dataset["features"] if f["type"] == "mRNA"]
    report |= {"features": len(dataset["features"]), "mRNA": len(mrnas),
               "table_attributes": sum(1 for f in mrnas for a in f["attributes"] if a["key"] in VALUE_COLUMNS)}
    return problems, report


def write_new(path, text):
    """Write text to a new file; return (ok, created). created says whether this call made the file.

    Only a file this call created may be removed on failure: if another process made
    the path first, open(..., "x") fails without touching it.
    """
    try:
        handle = open(path, "x", encoding="utf-8")
    except (OSError, UnicodeEncodeError) as error:
        report_errors([f"output: {error}"])
        return False, False
    try:
        with handle:
            handle.write(text)
    except (OSError, UnicodeEncodeError) as error:
        report_errors([f"output: {error}"])
        return False, True
    return True, True


def main(argv=None):
    quiet_linkml_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fwd = commands.add_parser("forward")
    fwd.add_argument("gff3", type=Path)
    fwd.add_argument("table", type=Path)
    fwd.add_argument("output", type=Path)
    fwd.add_argument("--table-url", help="the table's published URL, stored in each mRNA's source_files; "
                                         "defaults to its file: URI")
    rev = commands.add_parser("reverse")
    rev.add_argument("dataset", type=Path)
    rev.add_argument("gff3_output", type=Path)
    rev.add_argument("table_output", type=Path)
    rev.add_argument("--species", help="the ##species directive to write, if the source GFF3 had one")
    trip = commands.add_parser("roundtrip")
    trip.add_argument("gff3", type=Path)
    trip.add_argument("table", type=Path)
    args = parser.parse_args(argv)
    if args.command == "forward":
        gff3_document, table_document, errors = parse_inputs(args.gff3, args.table)
        if not errors:
            try:
                dataset = forward(gff3_document, table_document, args.table_url or args.table.resolve().as_uri())
            except ValueError as error:
                errors = [f"model: {error}"]
            else:
                errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if report_errors(errors):
            return 1
        return write_output(args.output, json.dumps(dataset, indent=1) + "\n")
    if args.command == "reverse":
        try:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            report_errors([f"input: {error}"])
            return 1
        errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if args.gff3_output.resolve() == args.table_output.resolve():
            errors.append("output: the GFF3 and the table need different paths")
        texts = {}
        if not errors:
            try:
                gff3_document, table_document = reverse(dataset, str(args.gff3_output), str(args.table_output),
                                                        species=args.species)
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
            else:
                for path, module, document in ((args.gff3_output, gff3_dialect, gff3_document),
                                               (args.table_output, table_dialect, table_document)):
                    errors += [f"{path}: {m}" for m in module.problems(document)]
                    if not errors:
                        try:
                            texts[path] = module.write(document)
                        except module.DialectError as error:
                            errors.append(f"{path}: write: {error}")
        existing = [str(p) for p in texts if p.exists()]
        if existing:
            errors.append(f"output: already exists, not overwritten: {existing}")
        if report_errors(errors):
            return 1
        created = []
        for path, text in texts.items():
            ok, made = write_new(path, text)
            if made:
                created.append(path)
            if not ok:
                # Leave nothing half done, but remove only files this call created.
                for done in created:
                    done.unlink(missing_ok=True)
                return 1
        return 0
    problems, report = roundtrip(args.gff3, args.table)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.gff3} + {args.table}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
