"""Map an IMG per-method hit GFF, with its genome's functional annotation GFF, to the feature model and back.

    python3 scripts/img_per_method_map.py forward FUNCTIONAL_GFF HIT_GFF... DATASET_JSON
    python3 scripts/img_per_method_map.py reverse DATASET_JSON OUT_PREFIX
    python3 scripts/img_per_method_map.py roundtrip FUNCTIONAL_GFF HIT_GFF...

One Dataset can hold every method's hit file for a genome. A hit's source ID is
<gene>_<start>_<end>, unique within its file but shared by hits of different methods
on the same span, so a hit's feature_id is <ID>|<method>|<type> and the source ID
stays as its ID attribute (https://github.com/turbomam/feature-table-corpus/issues/98,
the rule nmdc-lakehouse uses for NMDC hits). The rule applies to a single file too,
so a hit's feature_id doesn't depend on which other files share its Dataset.

A hit is on protein coordinates: its seqid is the CDS whose translation its
positions count along, and that CDS is its only parent (docs/protein-coordinates.md).
The hit files hold no CDS rows, so the functional annotation GFF of the same
genome supplies the contigs and CDS features, through scripts/img_functional_map.py.
Hits go through model/transforms/img-per-method-gff.transform.yaml forward and
through `linkml-map invert` of it in reverse.

The reverse direction writes OUT_PREFIX_functional_annotation.gff and
OUT_PREFIX_<method>.gff. It rebuilds each hit row's text and
parses it with the per-method dialect's own row parser, then maps everything
forward again and refuses a Dataset it can't reproduce. As for the functional
annotation, written text may differ from the source only in number spelling.
"""
import argparse
import json
from pathlib import Path
import sys

import img_functional_gff as functional_dialect
import img_functional_map as functional
import img_per_method_gff as dialect
from img_functional_map import (canonical, difference, present, quiet_linkml_map, report_errors,
                                without_rederived_tables, write_output)
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = functional.MODEL
TRANSFORM = ROOT / "model/transforms/img-per-method-gff.transform.yaml"
ROW = dialect.ROW_CLASS
LEXICAL = {"line", "attribute_order"}
# Columns the reverse direction takes from the Feature, in GFF order.
COLUMN_SLOTS = ("seqid", "source", "type", "start", "end", "score", "strand")


def _hit_transformers():
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


def _transformers():
    return functional._transformers(), _hit_transformers()


def hit_attributes(row):
    """Every column 9 value, one Attribute each, in file order, as text; a list gives one per value."""
    out = []
    for key in row["attribute_order"]:
        value = row[dialect.slot_name(key)]
        for item in value if isinstance(value, list) else [value]:
            out.append({"key": key, "value": dialect.value_text(item)})
    return out


def hit_feature_id(source_id, method, accession):
    """The feature_id of a hit: source ID, method and accession, joined by |."""
    return f"{source_id}|{method}|{accession}"


def forward(functional_document, hit_documents, transformers=None):
    """Map the functional annotation and one or more hit documents (one per method) to one Dataset."""
    functional_transformers, (to_model, _) = transformers or _transformers()
    dataset = functional.forward(functional_document, functional_transformers)
    if isinstance(hit_documents, dict):
        hit_documents = [hit_documents]
    for document in hit_documents:
        for row in document["rows"]:
            feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                                  source_type=ROW))
            feature["feature_id"] = hit_feature_id(row["ID"], document["method"], feature["type"])
            feature["coordinate_system"] = "protein"
            # The CDS a hit's positions count along is both its seqid and its parent.
            feature["parent"] = [row["seqid"]]
            feature["attributes"] = hit_attributes(row)
            dataset["features"].append(feature)
    return dataset


def column9(attributes, where):
    """Column 9 text from Attributes; consecutive values of one key form its comma list."""
    parts = []
    for attribute in attributes:
        key = attribute["key"]
        value = attribute["value"]
        for character in dialect.LINE_BREAKS + (";", "="):
            if character in key or (character != "=" and character in value):
                raise ValueError(f"{where}: {key}={value!r} contains {character!r}, which this dialect doesn't write")
        if "," in value:
            raise ValueError(f"{where}: {key}={value!r} contains ',', which would split into two values")
        if parts and parts[-1][0] == key:
            parts[-1][1].append(value)
        else:
            parts.append((key, [value]))
    return ";".join(f"{key}={','.join(values)}" for key, values in parts)


def reverse(dataset, source_prefix, transformers=None):
    """Return (functional_document, hit_documents) that forward maps back to dataset.

    hit_documents has one document per method, in the order the methods first appear."""
    transformers = transformers or _transformers()
    functional_transformers, (_, to_dialect) = transformers
    slots = dialect.row_slots()
    contig_features, hits = [], []
    for feature in dataset["features"]:
        (hits if feature.get("coordinate_system") == "protein" else contig_features).append(feature)
    functional_document = functional.reverse({**dataset, "features": contig_features},
                                             f"{source_prefix}_functional_annotation.gff",
                                             functional_transformers) if contig_features else None
    if functional_document is None:
        raise ValueError("no contig-coordinate features: the hits' CDS features are missing")
    documents = {}
    for feature in hits:
        name = feature.get("feature_id")
        if feature.get("parent") != [feature.get("seqid")]:
            raise ValueError(f"{name}: parent {feature.get('parent')!r} is not its seqid; "
                             "a hit's only parent is the CDS it is on")
        source_ids = [a["value"] for a in feature.get("attributes", []) if a["key"] == "ID"]
        if len(source_ids) != 1:
            raise ValueError(f"{name}: a hit needs exactly one ID attribute, its source ID")
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system", "parent")}
        core["feature_id"] = source_ids[0]
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        method = dialect.method_of(mapped.get("type"))
        if method is None:
            raise ValueError(f"{name}: type {mapped.get('type')!r} is not an accession of any IMG method")
        expected = hit_feature_id(source_ids[0], method, feature.get("type"))
        if name != expected:
            raise ValueError(f"{name}: feature_id should be {expected!r}, the ID attribute, method and type")
        document = documents.setdefault(method, {"source_file": f"{source_prefix}_{method}.gff",
                                                 "method": method, "rows": []})
        number = len(document["rows"]) + 1
        if "score" not in mapped:
            raise ValueError(f"{name}: a hit needs a score (column 6); every per-method row has one")
        columns = [dialect.value_text(mapped[slot]) if slot == "score" else str(mapped.get(slot, ""))
                   for slot in COLUMN_SLOTS] + ["."]
        try:
            text = "\t".join(columns + [column9(feature.get("attributes", []), f"{name}")])
            row = dialect.parse_row(number, text, slots)
        except (ValueError, KeyError) as error:
            raise ValueError(f"{name}: {error}") from None
        if row.get("ID") != mapped.get("ID"):
            raise ValueError(f"{name}: ID is {mapped.get('ID')!r} in the Feature but "
                             f"{row.get('ID')!r} in its attributes")
        document["rows"].append(row)
    # Map everything forward again and require the input back, so a slot the
    # dialects can't hold is refused rather than dropped.
    if not documents:
        raise ValueError("no protein-coordinate features: a per-method Dataset needs hits")
    hit_documents = list(documents.values())
    again = without_rederived_tables(forward(functional_document, hit_documents, transformers), dataset)
    if canonical(again) != canonical(dataset):
        raise ValueError(f"the dialects can't hold this Dataset without loss: {difference(dataset, again)}")
    return functional_document, hit_documents


def parse_inputs(functional_path, hit_paths):
    """Parse and validate every input; return (functional_document, hit_documents, problems)."""
    problems = []
    try:
        functional_document = functional_dialect.parse(functional_path)
    except (functional_dialect.DialectError, OSError, UnicodeDecodeError) as error:
        return None, [], [f"{functional_path}: {error}"]
    problems += [f"{functional_path}: {m}" for m in functional_dialect.problems(functional_document)]
    hit_documents = []
    for path in hit_paths:
        try:
            document = dialect.parse(path)
        except dialect.DialectError as error:
            problems.append(f"{path}: {error}")
            continue
        problems += [f"{path}: {m}" for m in dialect.problems(document)]
        hit_documents.append(document)
    methods = [d["method"] for d in hit_documents]
    if len(set(methods)) != len(methods):
        problems.append(f"more than one file for a method: {methods}")
    return functional_document, hit_documents, problems


def compare(before, after, module, path):
    """Problems and the count of lines that differ only in number spelling, for one file."""
    problems, spelling = [], 0
    if len(after["rows"]) != len(before["rows"]):
        return [f"{path}: {len(before['rows'])} rows in, {len(after['rows'])} back"], 0
    for a, b in zip(before["rows"], after["rows"]):
        if a != b:
            changed = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            problems.append(f"{path} line {a['line']}: row differs after the round trip in {changed}")
    with open(path, encoding="utf-8", newline="") as handle:
        original = handle.read().split("\n")[:-1]
    try:
        written = module.write(after).split("\n")[:-1]
    except module.DialectError as error:
        return problems + [f"{path}: write: {error}"], 0
    slots = module.row_slots()
    for number, (a, b) in enumerate(zip(original, written), start=1):
        if a != b:
            if module.parse_row(number, a, slots) != module.parse_row(number, b, slots):
                problems.append(f"{path} line {number}: written text differs in value, not only in spelling")
            else:
                spelling += 1
    return problems, spelling


def roundtrip(functional_path, hit_paths):
    """Return (problems, report): every hit file, with the functional annotation, in one Dataset."""
    report = {"functional": str(functional_path), "files": []}
    functional_document, hit_documents, problems = parse_inputs(functional_path, hit_paths)
    if problems:
        return problems, report
    transformers = _transformers()
    try:
        dataset = forward(functional_document, hit_documents, transformers)
    except ValueError as error:  # for example CDS translation tables that disagree
        return [f"{functional_path}: model: {error}"], report
    problems = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back_functional, back_hits = reverse(dataset, "roundtrip", transformers)
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    back_by_method = {d["method"]: d for d in back_hits}
    found_functional, functional_spelling = compare(functional_document, back_functional,
                                                    functional_dialect, functional_path)
    problems += found_functional
    report["features"] = len(dataset["features"])
    report["functional_lines_differing_only_in_number_spelling"] = functional_spelling
    for hit_document, path in zip(hit_documents, hit_paths):
        back = back_by_method.get(hit_document["method"], {"rows": []})
        found, spelling = compare(hit_document, back, dialect, path)
        problems += found
        report["files"].append({"file": str(path), "method": hit_document["method"],
                                "hits": len(hit_document["rows"]),
                                "hit_lines_differing_only_in_number_spelling": spelling})
    return problems, report


def main(argv=None):
    quiet_linkml_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fwd = commands.add_parser("forward")
    fwd.add_argument("functional", type=Path)
    fwd.add_argument("hits", type=Path, nargs="+", help="one hit GFF per method")
    fwd.add_argument("output", type=Path)
    rev = commands.add_parser("reverse")
    rev.add_argument("dataset", type=Path)
    rev.add_argument("prefix", help="written as PREFIX_functional_annotation.gff and PREFIX_<method>.gff")
    trip = commands.add_parser("roundtrip")
    trip.add_argument("functional", type=Path)
    trip.add_argument("hits", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "forward":
        functional_document, hit_documents, errors = parse_inputs(args.functional, args.hits)
        dataset = None
        if not errors:
            try:
                dataset = forward(functional_document, hit_documents)
            except ValueError as error:  # for example CDS translation tables that disagree
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
        outputs = {}
        if not errors:
            try:
                functional_document, hit_documents = reverse(dataset, args.prefix)
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
            else:
                pieces = [(functional_dialect, functional_document)] + [(dialect, d) for d in hit_documents]
                for module, document in pieces:
                    errors += [f"{document['source_file']}: {m}" for m in module.problems(document)]
                    if not errors:
                        try:
                            outputs[Path(document["source_file"])] = module.write(document)
                        except module.DialectError as error:
                            errors.append(f"{document['source_file']}: write: {error}")
        existing = [str(p) for p in outputs if p.exists()]
        if existing:
            errors.append(f"output: already exists, not overwritten: {existing}")
        if report_errors(errors):
            return 1
        for path, text in outputs.items():
            if write_output(path, text):
                return 1
        return 0
    problems, report = roundtrip(args.functional, args.hits)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.functional} + {len(args.hits)} hit file(s): "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
