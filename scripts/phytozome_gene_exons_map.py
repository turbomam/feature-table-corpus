"""Map a Phytozome gene_exons GFF3 to the feature model with linkml-map, and back.

    python3 scripts/phytozome_gene_exons_map.py forward GFF3 DATASET_JSON
    python3 scripts/phytozome_gene_exons_map.py reverse DATASET_JSON GFF3
    python3 scripts/phytozome_gene_exons_map.py roundtrip GFF3

The core columns go through model/transforms/phytozome-gene-exons-gff3.transform.yaml
forward, and through `linkml-map invert` of that same file in reverse. As in
scripts/img_functional_map.py, this module adds only what linkml-map 0.5.4 can't
do here (see the transform file's comments). longest also sets
Feature.is_representative (1 true, 0 false); Name, pacid and longest travel as
attributes, as every column 9 key does.

The reverse direction rebuilds each row's text and parses it with the dialect's
own row parser, so a Dataset the dialect can't hold is refused, not reinterpreted.
The file's two directives are not model data: gff-version is always 3, and the
annot-version is recovered from the gene IDs, which are Name plus "." plus it.
`roundtrip` requires the written file to equal the source byte for byte.
"""
import argparse
import json
from pathlib import Path
import sys

import phytozome_gene_exons as dialect
from img_functional_map import canonical, difference, present, quiet_linkml_map, report_errors, write_output
from img_functional_map import hidden_warnings as functional_map_warnings
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model/schema/ber_feature_model.yaml"
TRANSFORM = ROOT / "model/transforms/phytozome-gene-exons-gff3.transform.yaml"
ROW = dialect.ROW_CLASS
LEXICAL = {"line", "attribute_order"}
# Columns the reverse direction takes from the Feature, in GFF order; score is always ".".
COLUMN_SLOTS = ("seqid", "source", "type", "start", "end", "strand", "phase")


def _transformers():
    from linkml_runtime import SchemaView
    from linkml_map.inference.inverter import TransformationSpecificationInverter
    from linkml_map.transformer.object_transformer import ObjectTransformer

    source, target = SchemaView(str(dialect.SCHEMA)), SchemaView(str(MODEL))
    forward = ObjectTransformer()
    forward.source_schemaview, forward.target_schemaview = source, target
    forward.load_transformer_specification(TRANSFORM)
    inverter = TransformationSpecificationInverter(source_schemaview=source, target_schemaview=target)
    inverted = inverter.invert(forward.specification)
    # `invert` drops mirror_source from enum derivations (linkml-map 0.5.4).
    for derivation in forward.specification.enum_derivations.values():
        if derivation.mirror_source:
            inverted.enum_derivations[derivation.populated_from].mirror_source = True
    reverse = ObjectTransformer(specification=inverted)
    reverse.source_schemaview, reverse.target_schemaview = target, source
    return forward, reverse


def forward(document, transformers=None):
    to_model, _ = transformers or _transformers()
    features = []
    for row in document["rows"]:
        feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                              source_type=ROW))
        feature["coordinate_system"] = "contig"
        feature["attributes"] = [{"key": key, "value": str(row[key])} for key in row["attribute_order"]]
        # longest=1 marks the gene's representative isoform and longest=0 the others;
        # a row without the key says nothing, so the slot stays unset.
        if "longest" in row:
            feature["is_representative"] = row["longest"] == 1
        features.append(feature)
    contigs = [{"contig_id": seqid} for seqid in dict.fromkeys(row["seqid"] for row in document["rows"])]
    return {"contigs": contigs, "features": features}


def annot_version(rows):
    """The annot-version every gene ID carries after its Name, or a ValueError."""
    found = {row["ID"][len(row["Name"]) + 1:] for row in rows
             if row.get("type") == "gene" and "Name" in row and str(row.get("ID", "")).startswith(f"{row['Name']}.")}
    if len(found) != 1:
        raise ValueError(f"can't recover annot-version from the gene IDs: found {sorted(found) or 'none'}")
    return found.pop()


def reverse(dataset, source_file, transformers=None):
    transformers = transformers or _transformers()
    _, to_dialect = transformers
    slots = dialect.row_slots()
    rows = []
    for number, feature in enumerate(dataset["features"], start=3):
        name = feature.get("feature_id")
        # The dialect has only contig coordinates; dropping another system would
        # silently reinterpret protein positions as nucleotide positions.
        if feature.get("coordinate_system") != "contig":
            raise ValueError(f"{name}: coordinate_system is {feature.get('coordinate_system')!r}; "
                             "this dialect has only contig")
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system")}
        # linkml-map reduces a one-item parent list to the dialect's single Parent,
        # and raises TransformationError for two or more.
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        columns = [str(mapped.get(slot, ".")) for slot in COLUMN_SLOTS]
        columns.insert(5, ".")  # score
        try:
            # Checked before joining, so a ";" or "=" in a value can't become another key.
            column9 = ";".join(f"{dialect.checked(a['key'], f'line {number}', dialect.VALUE_FORBIDDEN)}="
                               f"{dialect.checked(a['value'], f'line {number} ' + a['key'], dialect.VALUE_FORBIDDEN)}"
                               for a in feature.get("attributes", []))
            row = dialect.parse_row(number, "\t".join(columns + [column9]), slots)
        except dialect.DialectError as error:
            raise ValueError(f"{name}: {error}") from None
        # ID and Parent are both Feature slots and attributes; the copies must agree.
        for key in ("ID", "Parent"):
            if mapped.get(key) != row.get(key):
                raise ValueError(f"{name}: {key} is {mapped.get(key)!r} in the Feature but "
                                 f"{row.get(key)!r} in its attributes")
        # So must is_representative and the longest attribute it comes from.
        expected = row["longest"] == 1 if "longest" in row else None
        if feature.get("is_representative") != expected:
            raise ValueError(f"{name}: is_representative is {feature.get('is_representative')!r} but its "
                             f"longest attribute gives {expected!r}")
        rows.append(row)
    try:
        version = annot_version(rows)
    except ValueError as error:
        raise ValueError(f"header: {error}") from None
    document = {"source_file": source_file, "gff_version": "3", "annot_version": version, "rows": rows}
    # The dialect can't carry every model slot (score, product, is_selected, contig
    # lengths ...). Map the result forward again and require the input back, so
    # nothing is dropped silently.
    again = forward(document, transformers)
    if canonical(again) != canonical(dataset):
        raise ValueError(f"the dialect can't hold this Dataset without loss: {difference(dataset, again)}")
    return document


def roundtrip(path):
    """Return (problems, report) for one file; no problems means the round trip held byte for byte."""
    report = {"file": str(path)}
    try:
        document = dialect.parse(path)
        with dialect.open_text(path) as handle:
            original = handle.read()
    except dialect.DialectError as error:
        return [f"dialect: {error}"], report
    except dialect.READ_ERRORS as error:
        return [f"input: {error}"], report
    problems = [f"dialect: {message}" for message in dialect.problems(document)]
    if problems:
        return problems, report
    transformers = _transformers()
    dataset = forward(document, transformers)
    problems += [f"model: {message}" for message in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back = reverse(dataset, str(path), transformers)
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    for before, after in zip(document["rows"], back["rows"]):
        if before != after:
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            problems.append(f"line {before['line']}: row differs after the round trip in {changed}")
    if len(back["rows"]) != len(document["rows"]):
        problems.append(f"{len(document['rows'])} rows in, {len(back['rows'])} out")
    for key in ("gff_version", "annot_version"):
        if back[key] != document[key]:
            problems.append(f"header: {key} {document[key]!r} comes back as {back[key]!r}")
    try:
        written = dialect.write(back)
    except dialect.DialectError as error:
        return problems + [f"write: {error}"], report
    if written != original:
        differing = next(i for i, (a, b) in enumerate(zip(original.split("\n"), written.split("\n")), 1) if a != b)
        problems.append(f"written text differs from the source, first at line {differing}")
    report |= {"rows": len(document["rows"]), "features": len(dataset["features"]),
               "contigs": len(dataset["contigs"]),
               "attributes": sum(len(f["attributes"]) for f in dataset["features"]),
               "byte_identical": written == original}
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
    rev.add_argument("output", type=Path)
    trip = commands.add_parser("roundtrip")
    trip.add_argument("gff", type=Path)
    args = parser.parse_args(argv)
    if args.command == "forward":
        try:
            document = dialect.parse(args.gff)
        except dialect.DialectError as error:
            report_errors([f"dialect: {error}"])
            return 1
        except dialect.READ_ERRORS as error:
            report_errors([f"input: {error}"])
            return 1
        errors = [f"dialect: {m}" for m in dialect.problems(document)]
        if not errors:
            dataset = forward(document)
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
        if not errors:
            try:
                document = reverse(dataset, str(args.output))
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
            else:
                errors = [f"dialect: {m}" for m in dialect.problems(document)]
        if report_errors(errors):
            return 1
        try:
            text = dialect.write(document)
        except dialect.DialectError as error:
            report_errors([f"write: {error}"])
            return 1
        return write_output(args.output, text)
    problems, report = roundtrip(args.gff)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report | functional_map_warnings()))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.gff}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
