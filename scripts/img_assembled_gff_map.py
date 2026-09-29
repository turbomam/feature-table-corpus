"""Map an IMG 4.14 `*.assembled.gff` to the feature model with linkml-map, and back.

    python3 scripts/img_assembled_gff_map.py forward GFF DATASET_JSON
    python3 scripts/img_assembled_gff_map.py reverse DATASET_JSON GFF
    python3 scripts/img_assembled_gff_map.py roundtrip GFF

The core columns go through model/transforms/img-assembled-gff.transform.yaml
forward, and through `linkml-map invert` of that same file in reverse. As in the
other mappings, this module adds column 9 as one Attribute per key occurrence in
file order, the constant coordinate system and one Contig per seqid. Attribute
values are the text the dialect's own writer produces, so Prodigal's conf and
gc_cont keep their two and three decimals.

The reverse direction rebuilds each row's text and parses it with the dialect's
own row parser, then maps the result forward again and refuses a Dataset it
can't reproduce. `roundtrip` requires the written file to equal the source byte
for byte.
"""
import argparse
import json
from pathlib import Path
import sys

import img_assembled_gff as dialect
from img_functional_map import canonical, difference, present, quiet_linkml_map, report_errors, write_output
from img_functional_map import hidden_warnings as functional_map_warnings
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model/schema/ber_feature_model.yaml"
TRANSFORM = ROOT / "model/transforms/img-assembled-gff.transform.yaml"
ROW = dialect.ROW_CLASS
LEXICAL = {"line", "attribute_order"}
# Column 9 keys the transform also maps to a Feature slot; their attribute copy must agree.
PROMOTED = {"ID": "feature_id", "product": "product"}


def _transformers():
    from linkml_runtime import SchemaView
    from linkml_map.inference.inverter import TransformationSpecificationInverter
    from linkml_map.transformer.object_transformer import ObjectTransformer

    source, target = SchemaView(str(dialect.SCHEMA)), SchemaView(str(MODEL))
    forward = ObjectTransformer()
    forward.source_schemaview, forward.target_schemaview = source, target
    forward.load_transformer_specification(TRANSFORM)
    inverter = TransformationSpecificationInverter(source_schemaview=source, target_schemaview=target)
    reverse = ObjectTransformer(specification=inverter.invert(forward.specification))
    reverse.source_schemaview, reverse.target_schemaview = target, source
    return forward, reverse


def attributes(row):
    """Column 9 as the dialect writes it, one Attribute per key occurrence, in file order."""
    column9 = dialect.write_row(row).split("\t")[8]
    pairs = [pair.partition("=") for pair in column9[:-1].split(";")]
    return [{"key": key, "value": value} for key, _, value in pairs]


def forward(document, transformers=None):
    to_model, _ = transformers or _transformers()
    features = []
    for row in document["rows"]:
        feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                              source_type=ROW))
        feature["coordinate_system"] = "contig"
        feature["attributes"] = attributes(row)
        features.append(feature)
    contigs = [{"contig_id": seqid} for seqid in dict.fromkeys(row["seqid"] for row in document["rows"])]
    return {"contigs": contigs, "features": features}


def row_text(mapped, feature_attributes, where):
    """One GFF line from mapped columns and Attributes, refused if a value would change its shape."""
    for attribute in feature_attributes:
        for character in dialect.LINE_BREAKS + (";",):
            if character in attribute["key"] or character in attribute["value"]:
                raise ValueError(f"{where}: {attribute['key']}={attribute['value']!r} contains {character!r}")
        if "=" in attribute["key"]:
            raise ValueError(f"{where}: attribute key {attribute['key']!r} contains '='")
    column9 = "".join(f"{a['key']}={a['value']};" for a in feature_attributes)
    phase = str(mapped["phase"]) if "phase" in mapped else "."
    return "\t".join([str(mapped.get("seqid", "")), str(mapped.get("source", "")), str(mapped.get("type", "")),
                      str(mapped.get("start", "")), str(mapped.get("end", "")), ".",
                      str(mapped.get("strand", "")), phase, column9])


def reverse(dataset, source_file, transformers=None):
    transformers = transformers or _transformers()
    _, to_dialect = transformers
    slots = dialect.row_slots()
    rows = []
    for number, feature in enumerate(dataset["features"], start=1):
        name = feature.get("feature_id")
        if feature.get("coordinate_system") != "contig":
            raise ValueError(f"{name}: coordinate_system is {feature.get('coordinate_system')!r}; "
                             "this dialect has only contig")
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system")}
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        try:
            row = dialect.parse_row(number, row_text(mapped, feature.get("attributes", []), name), slots)
        except (ValueError, dialect.DialectError) as error:
            raise ValueError(f"{name}: {error}") from None
        for key, slot in PROMOTED.items():
            if feature.get(slot) != row.get(key):
                raise ValueError(f"{name}: {slot} is {feature.get(slot)!r} in the Feature but "
                                 f"{key} is {row.get(key)!r} in its attributes")
        rows.append(row)
    document = {"source_file": source_file, "rows": rows}
    # The dialect can't carry every model slot (score, contig lengths ...). Map the
    # result forward again and require the input back, so nothing is dropped silently.
    again = forward(document, transformers)
    if canonical(again) != canonical(dataset):
        raise ValueError(f"the dialect can't hold this Dataset without loss: {difference(dataset, again)}")
    return document


def roundtrip(path):
    """Return (problems, report) for one file; no problems means it came back byte for byte."""
    report = {"file": str(path)}
    try:
        document = dialect.parse(path)
        with open(path, encoding="utf-8", newline="") as handle:
            original = handle.read()
    except (dialect.DialectError, OSError, UnicodeDecodeError) as error:
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
        if {**before, "line": 0} != {**after, "line": 0}:
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            problems.append(f"line {before['line']}: row differs after the round trip in {changed}")
    try:
        written = dialect.write(back)
    except dialect.DialectError as error:
        return problems + [f"write: {error}"], report
    if written != original:
        problems.append("written text differs from the source")
    report |= {"rows": len(document["rows"]), "contigs": len(dataset["contigs"]),
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
