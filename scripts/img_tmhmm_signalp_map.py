"""Map IMG TMHMM (_tmh) and SignalP (_cleavage_sites) GFF, with the genome's functional annotation GFF, to the feature model and back.

    python3 scripts/img_tmhmm_signalp_map.py forward FUNCTIONAL_GFF TOPOLOGY_GFF... DATASET_JSON [--spelling FILE]
    python3 scripts/img_tmhmm_signalp_map.py reverse DATASET_JSON OUT_PREFIX [--spelling FILE]
    python3 scripts/img_tmhmm_signalp_map.py roundtrip FUNCTIONAL_GFF TOPOLOGY_GFF...

A TMHMM segment or SignalP cleavage site is on protein coordinates: its seqid is the
CDS whose translation its positions count along, and that CDS is its only parent
(docs/protein-coordinates.md). The files hold no CDS rows, so the functional
annotation GFF of the same genome supplies the contigs and CDS features, through
scripts/img_functional_map.py. Rows go through
model/transforms/img-tmhmm-signalp-gff.transform.yaml forward and through
`linkml-map invert` of it in reverse.

feature_id is <seqid>_<start>_<end>|<method>|<type>, the form of
https://github.com/turbomam/feature-table-corpus/issues/98; SignalP rows have no ID,
so the source ID is built from the row. A TMHMM row's ID stays its ID Attribute.

The reverse direction writes OUT_PREFIX_functional_annotation.gff and
OUT_PREFIX_<method>.gff. It rebuilds each row's text and parses it with the
dialect's own row parser, then maps everything forward again and refuses a Dataset
it can't reproduce. Forward keeps the source's number spelling as the functional
mapping does (Attribute texts, and the --spelling file for scores), so every file
comes back byte for byte.
"""
import argparse
import json
from pathlib import Path
import sys

import img_functional_gff as functional_dialect
import img_functional_map as functional
import img_tmhmm_signalp_gff as dialect
from img_functional_map import (canonical, difference, present, quiet_linkml_map, report_errors,
                                without_rederived_tables, write_output)
from img_per_method_map import compare
from phytozome_annotation_map import write_new
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
MODEL = functional.MODEL
TRANSFORM = ROOT / "model/transforms/img-tmhmm-signalp-gff.transform.yaml"
ROW = dialect.ROW_CLASS
LEXICAL = {"line", "attribute_order"}
# Columns the reverse direction takes from the Feature, in GFF order; column 8 is always ".".
COLUMN_SLOTS = ("seqid", "source", "type", "start", "end", "score", "strand")


def _topology_transformers():
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
    return functional._transformers(), _topology_transformers()


def feature_id(seqid, start, end, method, feature_type):
    return f"{seqid}_{start}_{end}|{method}|{feature_type}"


def row_attributes(row, spelling=None):
    """Every column 9 value, one Attribute each, in file order, as text, keeping the source's spelling."""
    texts = iter((spelling or {}).get("values") or [])
    return [{"key": key, "value": functional_dialect.spelled(row[dialect.slot_name(key)], next(texts, None))}
            for key in row["attribute_order"]]


def line_spelling(text):
    """{"score": text, "values": [text, ...]} as one source line spells them; each key has one value."""
    columns = text.split("\t")
    return {"score": columns[5], "values": [pair.partition("=")[2] for pair in columns[8].split(";")]}


def source_spellings(functional_document, documents):
    """One spelling per Feature forward makes, in its order: functional rows, then each file's rows."""
    spellings = functional.source_spellings(functional_document["source_file"], functional_document)
    for document in documents:
        with open(document["source_file"], encoding="utf-8", newline="") as handle:
            lines = handle.read().split("\n")
        spellings += [line_spelling(lines[row["line"] - 1]) for row in document["rows"]]
    return spellings


def forward(functional_document, documents, transformers=None, spellings=None):
    """Map the functional annotation and one or more TMHMM or SignalP documents to one Dataset."""
    functional_transformers, (to_model, _) = transformers or _transformers()
    count = len(functional_document["rows"])
    spellings = spellings or [None] * (count + sum(len(d["rows"]) for d in documents))
    dataset = functional.forward(functional_document, functional_transformers, spellings[:count])
    rest = iter(spellings[count:])
    for document in documents:
        for row in document["rows"]:
            feature = present(to_model.map_object({k: v for k, v in row.items() if k not in LEXICAL},
                                                  source_type=ROW))
            feature["feature_id"] = feature_id(row["seqid"], row["start"], row["end"], document["method"],
                                               feature["type"])
            feature["coordinate_system"] = "protein"
            feature["parent"] = [row["seqid"]]
            feature["attributes"] = row_attributes(row, next(rest))
            dataset["features"].append(feature)
    return dataset


def reverse(dataset, source_prefix, transformers=None, scores=None):
    """Return (functional_document, documents) that forward maps back to dataset.

    documents has one document per method, in the order the methods first appear."""
    transformers = transformers or _transformers()
    functional_transformers, (_, to_dialect) = transformers
    slots = dialect.row_slots()
    contig_features, topology = [], []
    for feature in dataset["features"]:
        (topology if feature.get("coordinate_system") == "protein" else contig_features).append(feature)
    if not contig_features:
        raise ValueError("no contig-coordinate features: the CDS features are missing")
    if not topology:
        raise ValueError("no protein-coordinate features: a TMHMM or SignalP Dataset needs some")
    functional_document = functional.reverse({**dataset, "features": contig_features},
                                             f"{source_prefix}_functional_annotation.gff",
                                             functional_transformers, scores)
    documents, by_method = {}, {}
    for feature in topology:
        name = feature.get("feature_id")
        if feature.get("parent") != [feature.get("seqid")]:
            raise ValueError(f"{name}: parent {feature.get('parent')!r} is not its seqid; "
                             "its only parent is the CDS it is on")
        if feature.get("stable_identifiers") or feature.get("score_type"):
            raise ValueError(f"{name}: these files hold no stable_identifiers or score_type")
        core = {k: v for k, v in feature.items() if k not in ("attributes", "coordinate_system", "parent")}
        mapped = present(to_dialect.map_object(core, source_type="Feature"))
        method = dialect.method_of(mapped.get("type"))
        if method is None:
            raise ValueError(f"{name}: type {mapped.get('type')!r} is not a TMHMM segment or SignalP site")
        expected = feature_id(mapped.get("seqid"), mapped.get("start"), mapped.get("end"), method, mapped.get("type"))
        if name != expected:
            raise ValueError(f"{name}: feature_id should be {expected!r}")
        document = documents.setdefault(method, {"source_file": f"{source_prefix}_{method}.gff",
                                                 "method": method, "rows": []})
        by_method.setdefault(method, []).append(feature)
        columns = [str(mapped.get(slot, ".")) for slot in COLUMN_SLOTS] + ["."]
        if "score" in mapped:
            columns[COLUMN_SLOTS.index("score")] = functional_dialect.spelled(mapped["score"], (scores or {}).get(name))
        keys = tuple(a["key"] for a in feature.get("attributes", []))
        if keys != dialect.METHODS[method][2]:
            raise ValueError(f"{name}: attribute keys {list(keys)} are not the {method} keys "
                             f"{list(dialect.METHODS[method][2])}, in that order")
        parts = []
        for attribute in feature.get("attributes", []):
            key, value = attribute["key"], attribute["value"]
            for character in dialect.LINE_BREAKS + (";", "="):
                if character in key or (character != "=" and character in value):
                    raise ValueError(f"{name}: {key}={value!r} contains {character!r}, which this dialect doesn't write")
            parts.append(f"{key}={value}")
        try:
            row = dialect.parse_row(len(document["rows"]) + 1, "\t".join(columns + [";".join(parts)]), slots)
        except (ValueError, KeyError) as error:
            raise ValueError(f"{name}: {error}") from None
        document["rows"].append(row)
    documents = list(documents.values())
    # One file per method can't record how methods interleave, only each method's own order, so
    # compare in the order forward writes: contig features, then each method's rows.
    grouped = {**dataset, "features": contig_features + [f for group in by_method.values() for f in group]}
    again = without_rederived_tables(forward(functional_document, documents, transformers,
                                             functional.dataset_spellings(grouped["features"], scores)), dataset)
    if canonical(again) != canonical(grouped):
        raise ValueError(f"the dialects can't hold this Dataset without loss: {difference(grouped, again)}")
    return functional_document, documents


def write_spellings(dataset, documents, scores=None):
    """Per document from reverse, the spellings its write needs, in the order reverse groups features."""
    contig = [f for f in dataset["features"] if f.get("coordinate_system") != "protein"]
    rows = {}
    for feature in dataset["features"]:
        if feature.get("coordinate_system") == "protein":
            rows.setdefault(feature["feature_id"].split("|")[1], []).append(feature)
    return [functional.dataset_spellings(contig if i == 0 else rows.get(d.get("method"), []), scores)
            for i, d in enumerate(documents)]


def parse_inputs(functional_path, paths):
    """Parse and validate every input; return (functional_document, documents, problems)."""
    problems = []
    try:
        functional_document = functional_dialect.parse(functional_path)
    except (functional_dialect.DialectError, OSError, UnicodeDecodeError) as error:
        return None, [], [f"{functional_path}: {error}"]
    problems += [f"{functional_path}: {m}" for m in functional_dialect.problems(functional_document)]
    documents = []
    for path in paths:
        try:
            document = dialect.parse(path)
        except dialect.DialectError as error:
            problems.append(f"{path}: {error}")
            continue
        problems += [f"{path}: {m}" for m in dialect.problems(document)]
        documents.append(document)
    methods = [d["method"] for d in documents]
    if len(set(methods)) != len(methods):
        problems.append(f"more than one file for a method: {methods}")
    return functional_document, documents, problems


def roundtrip(functional_path, paths):
    """Return (problems, report): every file, with the functional annotation, in one Dataset."""
    report = {"functional": str(functional_path), "files": []}
    functional_document, documents, problems = parse_inputs(functional_path, paths)
    if problems:
        return problems, report
    transformers = _transformers()
    try:
        spellings = source_spellings(functional_document, documents)
        dataset = forward(functional_document, documents, transformers, spellings)
    except ValueError as error:  # for example CDS translation tables that disagree
        return [f"{functional_path}: model: {error}"], report
    scores = functional.score_spellings(dataset, spellings)
    problems = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
    if problems:
        return problems, report
    try:
        back_functional, back = reverse(dataset, "roundtrip", transformers, scores)
    except Exception as error:  # linkml-map raises its own TransformationError
        return [f"reverse: {error}"], report
    written = write_spellings(dataset, [back_functional] + back, scores)
    back_by_method = {d["method"]: (d, s) for d, s in zip(back, written[1:])}
    found, _ = compare(functional_document, back_functional, functional_dialect, functional_path, written[0])
    problems += found
    report["features"] = len(dataset["features"])
    for document, path in zip(documents, paths):
        again, spelling = back_by_method.get(document["method"], ({"rows": []}, None))
        found, _ = compare(document, again, dialect, path, spelling)
        problems += found
        report["files"].append({"file": str(path), "method": document["method"], "rows": len(document["rows"])})
    return problems, report


def main(argv=None):
    quiet_linkml_map()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    fwd = commands.add_parser("forward")
    fwd.add_argument("functional", type=Path)
    fwd.add_argument("files", type=Path, nargs="+", help="a _tmh.gff and/or a _cleavage_sites.gff")
    fwd.add_argument("output", type=Path)
    fwd.add_argument("--spelling", type=Path, help="also write the source's score spellings here, for reverse")
    rev = commands.add_parser("reverse")
    rev.add_argument("dataset", type=Path)
    rev.add_argument("prefix", help="written as PREFIX_functional_annotation.gff and PREFIX_<method>.gff")
    rev.add_argument("--spelling", type=Path, help="score spellings from forward --spelling")
    trip = commands.add_parser("roundtrip")
    trip.add_argument("functional", type=Path)
    trip.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "forward":
        functional_document, documents, errors = parse_inputs(args.functional, args.files)
        dataset = None
        if not errors:
            try:
                spellings = source_spellings(functional_document, documents)
                dataset = forward(functional_document, documents, spellings=spellings)
            except ValueError as error:
                errors = [f"model: {error}"]
            else:
                errors = [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        if report_errors(errors):
            return 1
        if write_output(args.output, json.dumps(dataset, indent=1) + "\n"):
            return 1
        scores = functional.score_spellings(dataset, spellings)
        if args.spelling and write_output(args.spelling, json.dumps(scores, indent=1) + "\n"):
            args.output.unlink()
            return 1
        return 0
    if args.command == "reverse":
        try:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            report_errors([f"input: {error}"])
            return 1
        scores, errors = functional.read_scores(args.spelling)
        errors += [f"model: {m}" for m in validation_errors(dataset, make_validator(str(MODEL)))]
        outputs = {}
        if not errors:
            try:
                functional_document, documents = reverse(dataset, args.prefix, scores=scores)
            except Exception as error:  # linkml-map raises its own TransformationError
                errors = [f"reverse: {error}"]
            else:
                pieces = [(functional_dialect, functional_document)] + [(dialect, d) for d in documents]
                spellings = write_spellings(dataset, [d for _, d in pieces], scores)
                for (module, document), spelling in zip(pieces, spellings):
                    errors += [f"{document['source_file']}: {m}" for m in module.problems(document)]
                    if not errors:
                        try:
                            outputs[Path(document["source_file"])] = module.write(document, spelling)
                        except module.DialectError as error:
                            errors.append(f"{document['source_file']}: write: {error}")
        existing = [str(p) for p in outputs if p.exists()]
        if existing:
            errors.append(f"output: already exists, not overwritten: {existing}")
        if report_errors(errors):
            return 1
        written = []
        for path, text in outputs.items():
            ok, created = write_new(path, text)
            if created:
                written.append(path)
            if not ok:
                # Remove only files this call created, including a partly written one.
                for done in written:
                    done.unlink()
                return 1
        return 0
    problems, report = roundtrip(args.functional, args.files)
    for problem in problems[:20]:
        print(f"  {problem}")
    print(json.dumps(report))
    print(f"{'HELD' if not problems else 'FAILED'}  {args.functional} + {len(args.files)} file(s): "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
