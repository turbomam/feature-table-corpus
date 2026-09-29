"""Map IMG functional annotation GFF to the feature model with linkml-map, and back.

    python3 scripts/img_functional_map.py forward GFF DATASET_JSON
    python3 scripts/img_functional_map.py reverse DATASET_JSON GFF
    python3 scripts/img_functional_map.py roundtrip GFF

The core columns go through model/transforms/img-functional-gff.transform.yaml
forward, and through `linkml-map invert` of that same file in reverse. This module
adds only what the transform file comments say linkml-map 0.5.4 can't do here:
column 9 as one Attribute per value in file order, the constant coordinate
system, and one Contig per seqid. It also restores mirror_source on the inverted
strand mapping, which `invert` drops, and derives each Contig's translation_table
from its CDS rows' translation_table attributes (scripts/translation_tables.py).

`roundtrip` parses, validates the dialect, maps forward, validates the Dataset
with scripts/validate_closed.py, maps back, and requires the rows to come back
equal. Forward keeps the source's spelling of numbers: column 9 values in the
Attribute texts, and scores (a number in the model) in a separate spelling map, the
--spelling file. With both, the written text is the source byte for byte.
"""
import argparse
import json
import logging
from pathlib import Path
import sys

import img_functional_gff as dialect
from translation_tables import with_translation_tables
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


def attributes(row, spelling=None):
    """Every column 9 value, one Attribute each, in file order, as text: the source's
    own spelling where spelling gives one (24, not 24.0), else the dialect's."""
    texts = iter((spelling or {}).get("values") or [])
    return [{"key": key, "value": dialect.spelled(value, next(texts, None))}
            for key, values in dialect.occurrences(row) for value in values]


def line_spelling(text, row):
    """{"score": text, "values": [text, ...]} as one source line spells them, for
    dialect.write_row; values in the order dialect.occurrences(row) yields them."""
    columns = text.split("\t")
    values = []
    pairs = columns[8].split(";")
    for (key, parsed), pair in zip(dialect.occurrences(row), pairs, strict=True):
        raw = pair.partition("=")[2]
        name = dialect.slot_name(key)
        comma_list = isinstance(row[name], list) and name not in dialect.ONE_VALUE_PER_OCCURRENCE
        parts = raw.split(",") if comma_list else [raw]
        if len(parts) != len(parsed):
            raise ValueError(f"line {row['line']}: {key} has {len(parts)} values in the text, {len(parsed)} parsed")
        values += parts
    return {"score": columns[5], "values": values}


def source_spellings(path, document):
    """One line_spelling per row of a document parsed from path."""
    with open(path, encoding="utf-8", newline="") as handle:
        lines = handle.read().split("\n")
    return [line_spelling(lines[row["line"] - 1], row) for row in document["rows"]]


def score_spellings(dataset, spellings):
    """{feature_id: score text} for each score the source spells differently from the
    dialect's default (84.50 for 84.5). The model's score is a number, so this is the
    one spelling a Dataset can't carry itself; pass it back to reverse."""
    out = {}
    for feature, spelling in zip(dataset["features"], spellings):
        text = (spelling or {}).get("score")
        if "score" in feature and text and dialect.spelled(feature["score"], text) != dialect.value_text(feature["score"]):
            out[feature["feature_id"]] = text
    return out


def dataset_spellings(features, scores=None):
    """Per feature, the spelling a write needs: its Attribute texts, and its score text from scores."""
    scores = scores or {}
    return [{"score": scores.get(f.get("feature_id")), "values": [a["value"] for a in f.get("attributes", [])]}
            for f in features]


def forward(document, transformers=None, spellings=None):
    """Map a document to a Dataset. spellings (source_spellings) keeps the source's
    spelling of numbers in the Attribute texts."""
    to_model, _ = transformers or _transformers()
    spellings = spellings or [None] * len(document["rows"])
    features = []
    for row, spelling in zip(document["rows"], spellings, strict=True):
        feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                              source_type=ROW))
        feature["coordinate_system"] = "contig"
        feature["attributes"] = attributes(row, spelling)
        features.append(feature)
    seqids = dict.fromkeys(row["seqid"] for row in document["rows"])
    # Contig.translation_table is derived from the CDS attributes, which the reverse
    # direction writes back; mapping forward again re-derives it, so it round trips.
    contigs, conflicts = with_translation_tables([{"contig_id": seqid} for seqid in seqids], features)
    if conflicts:
        raise ValueError("; ".join(conflicts))
    return {"contigs": contigs, "features": features}


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


def reverse(dataset, source_file, transformers=None, scores=None):
    """The dialect document for a Dataset. scores (score_spellings) is only used to
    check the round trip here; a write passes it again through dataset_spellings."""
    transformers = transformers or _transformers()
    _, to_dialect = transformers
    slots = dialect.row_slots()
    # Column 9 keys that the specification also maps to a Feature slot.
    derivations = to_dialect.specification.class_derivations
    derivations = derivations.values() if isinstance(derivations, dict) else derivations
    promoted = {name for cd in derivations for name in cd.slot_derivations} - dialect.CORE
    rows = []
    for number, feature in enumerate(dataset["features"], start=1):
        # The dialect has only contig coordinates; dropping any other system would
        # silently reinterpret protein positions as nucleotide positions.
        if feature.get("coordinate_system") != "contig":
            raise ValueError(f"{feature['feature_id']}: coordinate_system is "
                             f"{feature.get('coordinate_system')!r}; this dialect has only contig")
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system")}
        # linkml-map reduces a one-item parent list to the dialect's single Parent,
        # and raises TransformationError for two or more.
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        try:
            row = rows_from_attributes(feature.get("attributes", []), slots)
        except ValueError as error:
            raise ValueError(f"{feature['feature_id']}: {error}") from None
        for name in promoted & row.keys() - mapped.keys():
            raise ValueError(f"{feature['feature_id']}: {name} is an attribute but not set on the Feature")
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
    document = {"source_file": source_file, "rows": rows}
    # The dialect can't carry every model slot (translated_sequence, is_selected,
    # location, contig lengths ...). Map the result forward again and require the
    # input back, so nothing is dropped silently.
    again = without_rederived_tables(forward(document, transformers, dataset_spellings(dataset["features"], scores)),
                                     dataset)
    if canonical(again) != canonical(dataset):
        raise ValueError(f"the dialect can't hold this Dataset without loss: {difference(dataset, again)}")
    return document


def without_rederived_tables(again, dataset):
    """Drop translation tables that forward re-derived for contigs the input Dataset left unset.

    translation_table is derived, not written: the CDS attributes carry it. A Dataset
    that leaves it unset loses nothing, so the re-derived value is not a difference.
    """
    unset = {c["contig_id"] for c in dataset.get("contigs", []) if c.get("translation_table") is None}
    for contig in again["contigs"]:
        if contig["contig_id"] in unset:
            contig.pop("translation_table", None)
    return again


def canonical(dataset):
    # contig_collections too: the dialect has no place for them, so a Dataset that has any
    # must fail the round trip rather than lose them.
    return {"contig_collections": [present(c) for c in dataset.get("contig_collections") or []],
            "contigs": [present(c) for c in dataset.get("contigs", [])],
            "features": [present(f) for f in dataset.get("features", [])]}


def difference(dataset, again):
    """Name the first record and fields that don't survive the round trip."""
    before, again = canonical(dataset), canonical(again)
    for kind in ("contig_collections", "contigs", "features"):
        if len(before[kind]) != len(again[kind]):
            return f"{len(before[kind])} {kind} in, {len(again[kind])} back"
        for a, b in zip(before[kind], again[kind]):
            if a != b:
                fields = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                name = a.get("feature_id") or a.get("contig_id") or a.get("collection_id")
                return f"{kind[:-1]} {name!r} loses or changes {fields}"
    return "unknown"


def roundtrip(path):
    """Return (problems, report) for one file; no problems means it came back byte for byte."""
    report = {"file": str(path)}
    try:
        document = dialect.parse(path)
    except dialect.DialectError as error:
        return [f"dialect: {error}"], report
    except (OSError, UnicodeDecodeError) as error:
        return [f"input: {error}"], report
    problems = [f"dialect: {message}" for message in dialect.problems(document)]
    if problems:
        # Mapping assumes a valid dialect document, so stop and report.
        return problems, report
    transformers = _transformers()
    try:
        spellings = source_spellings(path, document)
        dataset = forward(document, transformers, spellings)
    except ValueError as error:
        return [f"model: {error}"], report
    scores = score_spellings(dataset, spellings)
    problems += [f"model: {message}" for message in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back = reverse(dataset, str(path), transformers, scores)
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    for before, after in zip(document["rows"], back["rows"]):
        if before != after:
            changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
            problems.append(f"line {before['line']}: row differs after the round trip in {changed}")
    if len(back["rows"]) != len(document["rows"]):
        problems.append(f"{len(document['rows'])} rows in, {len(back['rows'])} out")
    # Split at LF only, as the parser does: both texts have passed its LF-only rule, and
    # splitlines() would also split at a form feed or other break inside a value.
    with open(path, encoding="utf-8", newline="") as handle:
        original = handle.read().split("\n")[:-1]
    try:
        written = dialect.write(back, dataset_spellings(dataset["features"], scores)).split("\n")[:-1]
    except dialect.DialectError as error:
        return problems + [f"write: {error}"], report
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
    if spelling:
        problems.append(f"{spelling} lines differ from the source in number spelling")
    report |= {"rows": len(document["rows"]), "features": len(dataset["features"]),
              "contigs": len(dataset["contigs"]),
              "attributes": sum(len(f["attributes"]) for f in dataset["features"]),
              "lines_differing_only_in_number_spelling": spelling}
    return problems, report


def read_scores(path):
    """(scores, errors) from a --spelling file; no file means no kept spellings."""
    if path is None:
        return {}, []
    try:
        scores = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {}, [f"spelling: {error}"]
    if not isinstance(scores, dict) or not all(isinstance(v, str) for v in scores.values()):
        return {}, ["spelling: expected a JSON object of feature_id to score text"]
    return scores, []


def report_errors(errors):
    """Print errors and say whether there were any; output is written only when there were none."""
    for error in errors[:20]:
        print(f"  {error}", file=sys.stderr)
    if len(errors) > 20:
        print(f"  ... {len(errors) - 20} more", file=sys.stderr)
    return bool(errors)


def write_output(path, text):
    """Write to a new file only; like the conversion commands, never overwrite."""
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except (OSError, UnicodeEncodeError) as error:
        report_errors([f"output: {error}"])
        return 1
    return 0


def quiet_linkml_map():
    """Keep linkml-map's per-record warnings off stderr, so a run prints only its own result.

    linkml-map 0.5.4 logs "Unexpected: <id> for type ..." and "Unknown target range ..."
    for every record it maps; errors still show.
    """
    logging.getLogger("linkml_map").setLevel(logging.ERROR)


def main(argv=None):
    quiet_linkml_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fwd = commands.add_parser("forward")
    fwd.add_argument("gff", type=Path)
    fwd.add_argument("output", type=Path)
    fwd.add_argument("--spelling", type=Path, help="also write the source's score spellings here, for reverse")
    rev = commands.add_parser("reverse")
    rev.add_argument("dataset", type=Path)
    rev.add_argument("output", type=Path)
    rev.add_argument("--spelling", type=Path, help="score spellings from forward --spelling")
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
            try:
                spellings = source_spellings(args.gff, document)
                dataset = forward(document, spellings=spellings)
            except ValueError as error:
                errors = [f"model: {error}"]
            else:
                errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if report_errors(errors):
            return 1
        if write_output(args.output, json.dumps(dataset, indent=1) + "\n"):
            return 1
        if args.spelling and write_output(args.spelling, json.dumps(score_spellings(dataset, spellings), indent=1) + "\n"):
            args.output.unlink()
            return 1
        return 0
    if args.command == "reverse":
        try:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            report_errors([f"input: {error}"])
            return 1
        scores, errors = read_scores(args.spelling)
        errors += [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if not errors:
            try:
                document = reverse(dataset, str(args.output), scores=scores)
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
            else:
                errors = [f"dialect: {m}" for m in dialect.problems(document)]
        if report_errors(errors):
            return 1
        try:
            text = dialect.write(document, dataset_spellings(dataset["features"], scores))
        except dialect.DialectError as error:
            report_errors([f"write: {error}"])
            return 1
        return write_output(args.output, text)
    problems, report = roundtrip(args.gff)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.gff}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
