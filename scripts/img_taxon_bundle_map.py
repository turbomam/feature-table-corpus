"""Map an IMG taxon bundle (`<taxon_oid>.gff` and its `.tab.txt` tables) to the feature model, and back.

    python3 scripts/img_taxon_bundle_map.py forward GFF DATASET_JSON
    python3 scripts/img_taxon_bundle_map.py reverse DATASET_JSON OUT_GFF
    python3 scripts/img_taxon_bundle_map.py roundtrip GFF

The GFF rows and every table with positions go through
model/transforms/img-taxon-bundle.transform.yaml forward, and through
`linkml-map invert` of it in reverse. A table row is a hit on protein coordinates:
its seqid is the CDS named by gene_oid, which is also its only parent. Its
feature_id follows issue 98: <gene_oid>_<start>_<end>|<table>|<type>. The table's
other columns become Attributes in column order, as the dialect writes them.

Two tables need more. A KO hit that lists several EC numbers is written as one
row per number; it becomes one Feature with one EC Attribute per row, and the
rows must be adjacent and agree in every other column. The xref table has no
positions: each row becomes a stable_identifier on its CDS, as a CURIE
(ncbigi: for GI, genbank: for GenBank/EMBL).

GFF CRISPR rows are skipped and counted, never mapped: in the only bundle that has
them (Zymomonas 645058785), all 48 use two start positions repeated on every contig,
and 29 start past their contig's end, so they state nothing about real arrays
(decided in https://github.com/turbomam/feature-table-corpus/issues/101). The source
file is left as it is; the round trip compares the written GFF with the source
less those rows.

reverse writes OUT_GFF and each table beside it, named from OUT_GFF's taxon_oid.
`roundtrip` requires every file back byte for byte.
"""
import argparse
import glob
import json
from pathlib import Path
import sys

import img_taxon_bundle as dialect
from img_functional_map import canonical, difference, present, quiet_linkml_map, report_errors, write_output
from img_functional_map import reports_hidden_warnings
from phytozome_annotation_map import write_new
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model/schema/ber_feature_model.yaml"
TRANSFORM = ROOT / "model/transforms/img-taxon-bundle.transform.yaml"
GFF_CLASS = dialect.GFF_CLASS
# Per table with positions: the accession, start, end and score columns the transform maps.
HITS = {
    "cog": ("cog_id", "query_start", "query_end", "bit_score"),
    "pfam": ("pfam_id", "query_start", "query_end", "bit_score"),
    "tigrfam": ("tigrfam_id", "query_start", "query_end", "bit_score"),
    "ko": ("ko_id", "query_start", "query_end", "bit_score"),
    "ipr": ("domainid", "query_start", "query_end", None),
    "signalp": ("feature_type", "start_coord", "end_coord", None),
    "tmhmm": ("feature_type", "start_coord", "end_coord", None),
}
XREF_PREFIX = {"GI": "ncbigi", "GenBank/EMBL": "genbank"}
PREFIX_XREF = {v: k for k, v in XREF_PREFIX.items()}


def _transformers():
    from linkml_runtime import SchemaView
    from linkml_map.datamodel.transformer_model import TransformationSpecification
    from linkml_map.inference.inverter import TransformationSpecificationInverter
    from linkml_map.transformer.object_transformer import ObjectTransformer

    source, target = SchemaView(str(dialect.SCHEMA)), SchemaView(str(MODEL))
    forward = ObjectTransformer()
    forward.source_schemaview, forward.target_schemaview = source, target
    forward.load_transformer_specification(TRANSFORM)
    inverted = TransformationSpecificationInverter(source_schemaview=source,
                                                   target_schemaview=target).invert(forward.specification)
    for derivation in forward.specification.enum_derivations.values():
        if derivation.mirror_source:
            inverted.enum_derivations[derivation.populated_from].mirror_source = True
    derivations = inverted.class_derivations
    derivations = list(derivations.values()) if isinstance(derivations, dict) else list(derivations)
    # One reverse transformer per dialect class, since every derivation starts from Feature.
    reverse = {}
    for derivation in derivations:
        spec = TransformationSpecification(**{**inverted.model_dump(), "class_derivations": [derivation]})
        transformer = ObjectTransformer(specification=spec)
        transformer.source_schemaview, transformer.target_schemaview = target, source
        reverse[derivation.name] = transformer
    return forward, reverse


def cells(kind, row):
    """A table row's cells, spelled as the dialect writes them."""
    return dialect.write_table([row], kind).split("\n")[1].split("\t")


def columns(kind):
    return [name for name, _ in dialect.class_columns(dialect.TABLES[kind])]


def hit_id(gene_oid, start, end, kind, accession):
    return f"{gene_oid}_{start}_{end}|{kind}|{accession}"


def ko_groups(rows):
    """KO rows grouped by (gene, span, KO); refuse split or disagreeing groups."""
    groups, seen = [], set()
    for row in rows:
        key = tuple(row.get(n) for n in ("gene_oid", "query_start", "query_end", "ko_id"))
        if groups and groups[-1][0] == key:
            rest = {k: v for k, v in row.items() if k not in ("line", "EC")}
            first = {k: v for k, v in groups[-1][1][0].items() if k not in ("line", "EC")}
            if rest != first:
                raise ValueError(f"ko line {row['line']}: repeats a KO hit but differs in "
                                 f"{sorted(k for k in set(rest) | set(first) if rest.get(k) != first.get(k))}")
            groups[-1][1].append(row)
            continue
        if key in seen:
            raise ValueError(f"ko line {row['line']}: repeats a KO hit whose other rows are not adjacent")
        seen.add(key)
        groups.append((key, [row]))
    return [rows for _, rows in groups]


def skipped(document):
    """The GFF rows forward leaves out: every CRISPR row (issue 101)."""
    return [row for row in document["rows"] if row.get("type") == "CRISPR"]


def forward(document, transformers=None):
    to_model, _ = transformers or _transformers()
    features, cds = [], {}
    for row in document["rows"]:
        if row.get("type") == "CRISPR":
            continue
        feature = present(to_model.map_object({k: v for k, v in row.items() if k not in ("line", "attribute_order")},
                                              source_type=GFF_CLASS))
        feature["coordinate_system"] = "contig"
        column9 = dialect.write_gff_row(row).split("\t")[8]
        feature["attributes"] = [] if column9 == "." else [
            {"key": k, "value": v} for k, _, v in (pair.partition("=") for pair in column9.split(";"))]
        features.append(feature)
        if row.get("type") == "CDS":
            cds[row["ID"]] = feature
    for row in document.get("xref", []):
        feature = cds.get(str(row["gene_oid"]))
        if feature is None:
            raise ValueError(f"xref line {row['line']}: gene_oid {row['gene_oid']} is not a CDS in the GFF")
        feature.setdefault("stable_identifiers", []).append(f"{XREF_PREFIX[row['db_name']]}:{row['id']}")
    for kind, (accession, start, end, score) in HITS.items():
        rows = document.get(kind, [])
        groups = ko_groups(rows) if kind == "ko" else [[row] for row in rows]
        names = columns(kind)
        if kind != "ko":
            ids = {}
            for row in rows:
                key = hit_id(row["gene_oid"], row[start], row[end], kind, row[accession])
                if key in ids:
                    raise ValueError(f"{kind} line {row['line']}: gene, span and {accession} repeat line "
                                     f"{ids[key]}, so both would have feature_id {key!r}; none was measured")
                ids[key] = row["line"]
        for group in groups:
            row = group[0]
            core = {k: v for k, v in row.items() if k != "line"}
            feature = present(to_model.map_object(core, source_type=dialect.TABLES[kind]))
            feature["seqid"] = str(feature["seqid"])
            feature["feature_id"] = hit_id(row["gene_oid"], row[start], row[end], kind, row[accession])
            feature["coordinate_system"] = "protein"
            feature["parent"] = [feature["seqid"]]
            if score:
                feature["score_type"] = "bit_score"
            mapped = {"gene_oid", accession, start, end} | ({score} if score else set())
            attributes = []
            for name, cell in zip(names, cells(kind, row)):
                if name in mapped:
                    continue
                if kind == "ko" and name == "EC":
                    for member in group:
                        member_cells = dict(zip(names, cells(kind, member)))
                        if member_cells["EC"] != "" or len(group) > 1:
                            attributes.append({"key": "EC", "value": member_cells["EC"]})
                    continue
                if cell == "":
                    continue
                # A list cell (InterPro go_info) is one Attribute per member, in cell order.
                parts = row[name] if isinstance(row.get(name), list) else [None]
                attributes.extend({"key": name, "value": cell if part is None else dialect.value_text(part)}
                                  for part in parts)
            feature["attributes"] = attributes
            features.append(feature)
    contigs = [{"contig_id": s} for s in dict.fromkeys(r["seqid"] for r in document["rows"] if r.get("type") != "CRISPR")]
    return {"contigs": contigs, "features": features}


def table_row(kind, values, where):
    """Parse one table row from {column: text} with the dialect's own parser."""
    names = columns(kind)
    for name, value in values.items():
        for character in ("\t", "\n", "\r"):
            if character in value:
                raise ValueError(f"{where}: {name} value {value!r} contains {character!r}")
    text = "\t".join(names) + "\n" + "\t".join(values.get(name, "") for name in names) + "\n"
    return dialect.parse_table_lines(text.split("\n"), kind)[0]


def reverse(dataset, gff_path, transformers=None):
    transformers = transformers or _transformers()
    _, to_dialect = transformers
    gff_path = Path(gff_path)
    document = {"source_file": str(gff_path), "taxon_oid": gff_path.name[:-len(".gff")], "rows": []}
    xref = []
    tables = {kind: [] for kind in HITS}
    for feature in dataset["features"]:
        name = feature.get("feature_id")
        if feature.get("coordinate_system") == "contig":
            core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system", "stable_identifiers")}
            mapped = present(to_dialect[GFF_CLASS].map_object(core, source_type="Feature"))
            column9 = ";".join(f"{a['key']}={a['value']}" for a in feature.get("attributes", [])) or "."
            line = "\t".join([str(mapped.get("seqid", "")), str(mapped.get("source", "")), str(mapped.get("type", "")),
                              str(mapped.get("start", "")), str(mapped.get("end", "")), ".",
                              str(mapped.get("strand", "")), str(mapped["phase"]) if "phase" in mapped else ".", column9])
            try:
                row = dialect.parse_gff_lines([dialect.HEADER, line, ""])[0]
            except dialect.DialectError as error:
                raise ValueError(f"{name}: {error}") from None
            if mapped.get("ID") != row.get("ID") or mapped.get("product") != row.get("product"):
                raise ValueError(f"{name}: feature_id or product disagrees with its attributes")
            document["rows"].append(row)
            for identifier in feature.get("stable_identifiers", []):
                prefix, _, local = identifier.partition(":")
                if prefix not in PREFIX_XREF or feature.get("type") != "CDS":
                    raise ValueError(f"{name}: stable identifier {identifier!r} is not an ncbigi: or genbank: "
                                     "CURIE on a CDS")
                xref.append({"gene_oid": row["ID"], "db_name": PREFIX_XREF[prefix], "id": local})
            continue
        kind = name.split("|")[1] if name and name.count("|") == 2 else None
        if feature.get("coordinate_system") != "protein" or kind not in HITS:
            raise ValueError(f"{name}: not a GFF row or a hit of a known table")
        if feature.get("parent") != [feature.get("seqid")] or feature.get("stable_identifiers"):
            raise ValueError(f"{name}: a hit's only parent is its CDS, and it has no stable identifiers")
        accession, start, end, score = HITS[kind]
        core = {k: v for k, v in feature.items()
                if k not in ("attributes", "coordinate_system", "parent", "feature_id", "score_type")}
        mapped = present(to_dialect[dialect.TABLES[kind]].map_object(core, source_type="Feature"))
        if feature.get("score_type") != ("bit_score" if score else None):
            raise ValueError(f"{name}: score_type should be {'bit_score' if score else 'unset'}")
        values = {n: dialect.value_text(v) for n, v in mapped.items()}
        ec, kept = [], {}
        for attribute in feature.get("attributes", []):
            if kind == "ko" and attribute["key"] == "EC":
                ec.append(attribute["value"])
            elif attribute["key"] in values or attribute["key"] not in columns(kind):
                raise ValueError(f"{name}: attribute {attribute['key']!r} is not a {kind} column the Feature leaves out")
            else:
                kept.setdefault(attribute["key"], []).append(attribute["value"])
        # Repeats of one column rejoin into its list cell; the forward check below refuses
        # repeats of a column that holds one value.
        values.update({key: dialect.LIST_SEPARATOR.join(parts) for key, parts in kept.items()})
        for value in (ec or [None]):
            row_values = dict(values, **({"EC": value} if value is not None else {}))
            try:
                row = table_row(kind, row_values, name)
            except dialect.DialectError as error:
                raise ValueError(f"{name}: {error}") from None
            tables[kind].append(row)
        expected = hit_id(tables[kind][-1]["gene_oid"], tables[kind][-1][start], tables[kind][-1][end],
                          kind, tables[kind][-1][accession])
        if name != expected:
            raise ValueError(f"{name}: feature_id should be {expected!r}")
    for number, row in enumerate(document["rows"], start=2):
        row["line"] = number
    # The dialect sorts every table by gene_oid, which GFF order need not follow; a
    # stable sort keeps each gene's identifiers in their order.
    xref.sort(key=lambda row: (len(str(row["gene_oid"])), str(row["gene_oid"])))
    for kind, rows in [("xref", xref)] + list(tables.items()):
        if rows:
            for number, row in enumerate(rows, start=2):
                row["line"] = number
            document[kind] = rows
    again = forward(document, transformers)
    grouped = file_order(dataset)
    if canonical(again) != canonical(grouped):
        raise ValueError(f"the dialect can't hold this Dataset without loss: {difference(grouped, again)}")
    return document


def file_order(dataset):
    """The Dataset with its features in the files' grouping: GFF rows, then each table's hits.

    Separate files can't record how features of different files interleave, so only the
    order within each file is compared.
    """
    def group(feature):
        name = feature.get("feature_id") or ""
        kind = name.split("|")[1] if feature.get("coordinate_system") == "protein" and name.count("|") == 2 else None
        return 0 if kind is None else 1 + list(HITS).index(kind) if kind in HITS else len(HITS) + 1
    return {**dataset, "features": sorted(dataset["features"], key=group)}


@reports_hidden_warnings
def roundtrip(path):
    """Return (problems, report); no problems means every file came back byte for byte."""
    report = {"file": str(path)}
    try:
        document = dialect.parse(path)
    except dialect.DialectError as error:
        return [f"input: {error}"], report
    problems = [f"dialect: {m}" for m in dialect.problems(document)]
    if problems:
        return problems, report
    transformers = _transformers()
    try:
        dataset = forward(document, transformers)
    except ValueError as error:
        return [f"model: {error}"], report
    problems += [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back = reverse(dataset, Path(path), transformers)
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    try:
        written = dialect.write(back)
    except dialect.DialectError as error:
        return [f"write: {error}"], report
    path = Path(path)
    originals = {path.name: path, **{p.name: p for p in dialect.table_paths(path).values()}}
    if sorted(written) != sorted(originals):
        problems.append(f"files differ: wrote {sorted(written)}, read {sorted(originals)}")
    left_out = {row["line"] for row in skipped(document)}
    for name, text in written.items():
        if name not in originals:
            continue
        original = originals[name].read_text(encoding="utf-8")
        if name == path.name and left_out:
            # The written GFF must be the source less exactly the skipped rows.
            original = "".join(line for number, line in enumerate(original.splitlines(keepends=True), start=1)
                               if number not in left_out)
        if original != text:
            problems.append(f"{name}: written text differs from the source")
    hits = [f for f in dataset["features"] if f["coordinate_system"] == "protein"]
    report |= {"features": len(dataset["features"]), "hits": len(hits), "skipped_crispr_rows": len(left_out),
               "stable_identifiers": sum(len(f.get("stable_identifiers", [])) for f in dataset["features"]),
               "files": sorted(written)}
    return problems, report


def main(argv=None):
    quiet_linkml_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fwd = commands.add_parser("forward")
    fwd.add_argument("gff", type=Path)
    fwd.add_argument("output", type=Path)
    rev = commands.add_parser("reverse")
    rev.add_argument("dataset", type=Path)
    rev.add_argument("output", type=Path, help="<taxon_oid>.gff; the tables are written beside it")
    trip = commands.add_parser("roundtrip")
    trip.add_argument("gff", type=Path)
    args = parser.parse_args(argv)
    if args.command == "forward":
        try:
            document = dialect.parse(args.gff)
        except dialect.DialectError as error:
            report_errors([f"input: {error}"])
            return 1
        errors = [f"dialect: {m}" for m in dialect.problems(document)]
        if not errors:
            try:
                dataset = forward(document)
            except ValueError as error:
                errors = [f"model: {error}"]
            else:
                errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if report_errors(errors):
            return 1
        if skipped(document):
            print(f"skipped {len(skipped(document))} CRISPR rows (issue 101)", file=sys.stderr)
        return write_output(args.output, json.dumps(dataset, indent=1) + "\n")
    if args.command == "reverse":
        if not args.output.name.endswith(".gff"):
            report_errors(["output: expected <taxon_oid>.gff"])
            return 1
        try:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            report_errors([f"input: {error}"])
            return 1
        errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        files = {}
        if not errors:
            try:
                document = reverse(dataset, args.output)
                errors = [f"dialect: {m}" for m in dialect.problems(document)]
                if not errors:
                    files = dialect.write(document)
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
        paths = {args.output.parent / name: text for name, text in files.items()}
        taxon = args.output.name[:-len(".gff")]
        existing = sorted(str(p) for p in args.output.parent.glob(glob.escape(taxon) + ".*")
                          if p.name[len(taxon) + 1:] not in dialect.SEQUENCE_FILES)
        if existing:
            errors.append(f"output: {taxon} files already in {args.output.parent}, which would join or be "
                          f"overwritten by the bundle: {existing}")
        if report_errors(errors):
            return 1
        written = []
        for path, text in paths.items():
            ok, created = write_new(path, text)
            if created:
                written.append(path)
            if not ok:
                # Remove only files this call created, including a partly written one.
                for done in written:
                    done.unlink()
                return 1
        return 0
    problems, report = roundtrip(args.gff)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.gff}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
