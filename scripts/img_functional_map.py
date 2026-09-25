"""Map IMG functional annotation GFF to the feature model with linkml-map, and back.

    python3 scripts/img_functional_map.py forward GFF DATASET_JSON
    python3 scripts/img_functional_map.py reverse DATASET_JSON GFF
    python3 scripts/img_functional_map.py roundtrip GFF

The core columns go through model/transforms/img-functional-gff.transform.yaml
forward, and through `linkml-map invert` of that same file in reverse. This module
adds only what the transform file comments say linkml-map 0.5.4 can't do here:
column 9 as one Attribute per value in file order, the constant coordinate
system, and one Contig per seqid. It also restores mirror_source on the inverted
strand mapping, which `invert` drops.

`roundtrip` parses, validates the dialect, maps forward, validates the Dataset
with scripts/validate_closed.py, maps back, and requires the rows to come back
equal. The written text may differ from the source only in number spelling.
"""
import argparse
import json
from pathlib import Path
import sys

import img_functional_gff as dialect
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model/schema/ber_feature_model.yaml"
TRANSFORM = ROOT / "model/transforms/img-functional-gff.transform.yaml"
ROW = dialect.ROW_CLASS
LEXICAL = {"line", "attribute_order"}


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
    # `invert` drops mirror_source from enum derivations (linkml-map 0.5.4), which
    # maps every strand to None on the way back. Copy it from the forward spec.
    for derivation in forward.specification.enum_derivations.values():
        if derivation.mirror_source:
            inverted.enum_derivations[derivation.populated_from].mirror_source = True
    reverse = ObjectTransformer(specification=inverted)
    reverse.source_schemaview, reverse.target_schemaview = target, source
    return forward, reverse


def present(record):
    return {k: v for k, v in record.items() if v is not None and v != []}


def attributes(row):
    """Every column 9 value, one Attribute each, in file order, as text."""
    return [{"key": key, "value": dialect.value_text(value)}
            for key, values in dialect.occurrences(row) for value in values]


def forward(document, transformers=None):
    to_model, _ = transformers or _transformers()
    features = []
    for row in document["rows"]:
        feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                              source_type=ROW))
        feature["coordinate_system"] = "contig"
        feature["attributes"] = attributes(row)
        features.append(feature)
    seqids = dict.fromkeys(row["seqid"] for row in document["rows"])
    return {"contigs": [{"contig_id": seqid} for seqid in seqids], "features": features}


def rows_from_attributes(feature_attributes, slots):
    """Rebuild typed column 9 slots and key order from the Attribute list.

    Consecutive values of a comma-list key are one occurrence; a key in
    ONE_VALUE_PER_OCCURRENCE is one occurrence per value.
    """
    row, order = {}, []
    for attribute in feature_attributes:
        key = attribute["key"]
        name = dialect.slot_name(key)
        slot = slots.get(name)
        if slot is None or name in dialect.CORE or key in dialect.SLOT_ONLY_NAMES:
            raise ValueError(f"attribute key {key!r} is not a column 9 key of this dialect")
        value = dialect.convert(attribute["value"], slot)
        if slot.multivalued:
            continuing = order and order[-1] == key and name not in dialect.ONE_VALUE_PER_OCCURRENCE
            if not continuing:
                if key in order and name not in dialect.ONE_VALUE_PER_OCCURRENCE:
                    raise ValueError(f"{key} values are not contiguous; the dialect writes one comma list")
                order.append(key)
            row.setdefault(name, []).append(value)
        else:
            order.append(key)
            row[name] = value
    row["attribute_order"] = order
    return row


def reverse(dataset, source_file, transformers=None):
    _, to_dialect = transformers or _transformers()
    slots = dialect.row_slots()
    rows = []
    for number, feature in enumerate(dataset["features"], start=1):
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system")}
        # linkml-map reduces a one-item parent list to the dialect's single Parent,
        # and raises TransformationError for two or more.
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        try:
            row = rows_from_attributes(feature.get("attributes", []), slots)
        except ValueError as error:
            raise ValueError(f"{feature['feature_id']}: {error}") from None
        for name, value in mapped.items():
            if name in dialect.CORE:
                continue
            # A column 9 key promoted to a Feature slot must also be an attribute,
            # which is where its position in the row comes from.
            if name not in row:
                raise ValueError(f"{feature['feature_id']}: {name} has no attribute copy")
            if row[name] != value:
                raise ValueError(f"{feature['feature_id']}: {name} is {value!r} in the Feature "
                                 f"but {row[name]!r} in its attributes")
        row.update(mapped)
        row["line"] = number
        rows.append(row)
    return {"source_file": source_file, "rows": rows}


def roundtrip(path):
    """Return (problems, report) for one file; no problems means the round trip held."""
    report = {"file": str(path)}
    try:
        document = dialect.parse(path)
    except dialect.DialectError as error:
        return [f"dialect: {error}"], report
    problems = [f"dialect: {message}" for message in dialect.problems(document)]
    if problems:
        # Mapping assumes a valid dialect document, so stop and report.
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
    original = Path(path).read_text(encoding="utf-8").splitlines()
    written = dialect.write(back).splitlines()
    spelling = 0
    slots = dialect.row_slots()
    for number, (a, b) in enumerate(zip(original, written), start=1):
        if a == b:
            continue
        # A differing line must parse to the same typed row, so only spelling differs.
        if dialect.parse_row(number, a, slots) != dialect.parse_row(number, b, slots):
            problems.append(f"line {number}: written text differs in value, not only in spelling")
        else:
            spelling += 1
    report |= {"rows": len(document["rows"]), "features": len(dataset["features"]),
              "contigs": len(dataset["contigs"]),
              "attributes": sum(len(f["attributes"]) for f in dataset["features"]),
              "lines_differing_only_in_number_spelling": spelling}
    return problems, report


def report_errors(errors):
    """Print errors and say whether there were any; output is written only when there were none."""
    for error in errors[:20]:
        print(f"  {error}", file=sys.stderr)
    if len(errors) > 20:
        print(f"  ... {len(errors) - 20} more", file=sys.stderr)
    return bool(errors)


def main(argv=None):
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
        except (dialect.DialectError, OSError, UnicodeDecodeError) as error:
            report_errors([f"input: {error}"])
            return 1
        errors = [f"dialect: {m}" for m in dialect.problems(document)]
        if not errors:
            dataset = forward(document)
            errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if report_errors(errors):
            return 1
        args.output.write_text(json.dumps(dataset, indent=1) + "\n")
        return 0
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
        args.output.write_text(dialect.write(document))
        return 0
    problems, report = roundtrip(args.gff)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.gff}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
