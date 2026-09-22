#!/usr/bin/env python3
"""Versioned, conservative source <-> Dataset conversions. See docs/conversion-profiles.md.

Exact export and reconstructed export are separate operations. Both reject edits
to an imported bundle; neither silently replays an obsolete original after edits.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import quote, unquote, urlsplit

import rfc3987

from source_document import parse_bytes, replay_bytes, write_new
from validate_closed import make_validator, validation_errors

ROOT = Path(__file__).resolve().parents[1]
PROTEIN = "nmdc-pfam-protein/1.0.0"
PROFILES = {"gff3-contig/1.0.0": "gff3", "bed12-blocks/1.0.0": "bed12", PROTEIN: "gff3"}


class ConversionError(ValueError):
    """Stable machine-readable failure code plus a human-readable explanation."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise ConversionError(code, message)


def integer(text, minimum=0):
    require(bool(re.fullmatch(r"[0-9]+", text)), "invalid-integer", f"not an unsigned integer: {text!r}")
    value = int(text)
    require(value >= minimum, "coordinate-domain", f"{value} is below {minimum}")
    return value


def decoded(text):
    require(not re.search(r"%(?![0-9A-Fa-f]{2})", text), "invalid-escape", f"invalid percent escape: {text!r}")
    try:
        return unquote(text, encoding="utf-8", errors="strict")
    except UnicodeError as error:
        raise ConversionError("invalid-escape", "percent escapes must decode as UTF-8") from error


def encoded(text):
    return quote(text, safe=".:^*$@!+_?-|")


def encoded_field(text):
    # A literal dot is distinct from the GFF missing-value sentinel.
    return "%2E" if text == "." else encoded(text)


def attributes(text):
    """Retain ordered occurrences and comma grouping separately from generic pairs."""
    pairs, groups = [], []
    if text in ("", "."):
        return pairs, groups
    tokens = text.split(";")
    if tokens[-1] == "":
        tokens.pop()  # One trailing delimiter is a lexical detail.
    for token in tokens:
        key, separator, value = token.partition("=")
        key = decoded(key)
        require(separator and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", key),
                "attribute-syntax", f"expected a GFF key=value assignment: {token!r}")
        indices = []
        for item in value.split(","):
            indices.append(len(pairs))
            pairs.append({"key": key, "value": decoded(item)})
        groups.append({"key": key, "indices": indices})
    return pairs, groups


def values(pairs, key):
    return [a["value"] for a in pairs if a["key"] == key]


def gff_feature(columns, record_id):
    seqid, source, kind, start, end, score, strand, phase, attr = columns
    require(seqid not in ("", ".") and not re.search(r"\s", seqid),
            "reference-identity", "GFF seqid must be a nonempty identifier, with whitespace escaped")
    require(kind not in ("", "."), "feature-type", "a feature type is required by this profile")
    pairs, groups = attributes(attr)
    ids, parents, products = values(pairs, "ID"), values(pairs, "Parent"), values(pairs, "product")
    require(len(ids) <= 1 and all(ids), "identifier-cardinality", "ID must have one nonempty value")
    require(all(parents), "parent-cardinality", "Parent values cannot be empty")
    require(len(products) <= 1, "product-cardinality", "typed product requires at most one value")
    require("true" not in values(pairs, "Is_circular"), "circular-location",
            "circular reference semantics require a different location profile")
    feature = {"feature_id": ids[0] if ids else f"urn:ftc:{record_id}",
               "seqid": decoded(seqid), "type": decoded(kind), "start": integer(start, 1),
               "end": integer(end, 1), "coordinate_system": "contig", "strand": strand,
               "attributes": pairs}
    if source != ".":
        feature["source"] = decoded(source)
    if score != ".":
        require(bool(re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", score)),
                "score-domain", f"not a finite decimal score: {score!r}")
        number = float(score)
        require(math.isfinite(number) and Decimal(str(number)) == Decimal(score),
                "score-precision", "score cannot be represented by the model float without decimal precision loss")
        feature["score"] = number
    if phase != ".":
        feature["phase"] = integer(phase)
    require((feature["type"] == "CDS" and phase in ("0", "1", "2"))
            or (feature["type"] != "CDS" and phase == "."),
            "phase-domain", "this profile requires CDS phase 0/1/2 and '.' on non-CDS rows")
    if parents:
        feature["parent"] = parents
    if products:
        feature["product"] = products[0]
    return [feature], {"record_id": record_id, "feature_ids": [feature["feature_id"]],
                       "attribute_groups": groups, "source_has_id": bool(ids)}


def bed_features(columns, record_id):
    chrom, start, end, name, score, strand, thick_start, thick_end, rgb, count, sizes, starts = columns
    require(chrom and not re.search(r"\s", chrom), "reference-identity", "BED chrom must be a nonempty identifier")
    start, end = integer(start), integer(end)
    require(start < end, "empty-interval", "zero-length or reversed BED intervals are outside this profile")
    score, thick_start, thick_end, count = integer(score), integer(thick_start), integer(thick_end), integer(count, 1)
    require(score <= 1000 and strand in ("+", "-", "."), "bed-domain", "BED score or strand outside its domain")
    require(start <= thick_start <= thick_end <= end, "thick-bounds", "thick interval must lie within the BED span")
    require(rgb == "0" or (re.fullmatch(r"[0-9]+,[0-9]+,[0-9]+", rgb)
                           and all(int(c) <= 255 for c in rgb.split(","))),
            "rgb-domain", "itemRgb must be 0 or three integers from 0 to 255")
    sizes = [integer(v, 1) for v in sizes.removesuffix(",").split(",")]
    starts = [integer(v) for v in starts.removesuffix(",").split(",")]
    require(len(sizes) == len(starts) == count, "block-count", "block count and list lengths disagree")
    require(starts[0] == 0 and starts[-1] + sizes[-1] == end - start,
            "block-bounds", "first and last blocks must reach the enclosing span boundaries")
    require(all(starts[i] + sizes[i] <= starts[i + 1] for i in range(count - 1)),
            "block-order", "blocks must be ordered and nonoverlapping")
    fid = f"bed:{record_id}"
    feature = {"feature_id": fid, "seqid": chrom, "type": "sequence_feature", "start": start + 1,
               "end": end, "coordinate_system": "contig", "score": score, "strand": strand,
               "attributes": [{"key": k, "value": v} for k, v in (
                   ("bed:role", "record"), ("bed:name", name), ("bed:thickStart", str(thick_start)),
                   ("bed:thickEnd", str(thick_end)), ("bed:itemRgb", rgb))]}
    rows = [feature]
    for i, (offset, size) in enumerate(zip(starts, sizes), 1):
        rows.append({"feature_id": f"{fid}:block-{i}", "seqid": chrom, "type": "sequence_feature",
                     "start": start + offset + 1, "end": start + offset + size,
                     "coordinate_system": "contig", "strand": strand, "parent": [fid],
                     "attributes": [{"key": "bed:role", "value": "block"}]})
    return rows, {"record_id": record_id, "feature_ids": [r["feature_id"] for r in rows]}


@lru_cache(maxsize=1)
def dataset_validator():
    return make_validator(ROOT / "model/schema/ber_feature_model.yaml")


@lru_cache(maxsize=1)
def source_validator():
    return make_validator(ROOT / "model/schema/source_document.yaml", "SourceDocument")


def absolute_artifact_uri(value):
    """Check the whole URI; HTTP(S) references also need a host and valid port."""
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f]", value):
        return False
    try:
        parsed = rfc3987.parse(value, rule="URI")
        if parsed["scheme"].lower() in ("http", "https"):
            url = urlsplit(value)
            if not url.hostname:
                return False
            _ = url.port  # Access validates the port, including its numeric range.
        return True
    except ValueError:
        return False


def protein_bindings(context, reference_context):
    """Validate an explicit protein -> CDS map; never parse identity from offsets."""
    require(isinstance(context, dict) and set(context) == {
        "context_version", "reference_context", "dataset", "bindings", "artifacts"},
        "protein-context", "supply a complete protein context document")
    require(type(context["context_version"]) is int and context["context_version"] == 1
            and context["reference_context"] == reference_context,
            "protein-context", "protein context version/reference does not match")
    errors = validation_errors(context["dataset"], dataset_validator())
    require(not errors, "protein-context", "; ".join(errors))
    parents = {f["feature_id"]: f for f in context["dataset"].get("features", [])}
    require(bool(parents), "protein-context", "protein context requires CDS features")
    for parent in parents.values():
        require(parent.get("type") == "CDS" and parent["coordinate_system"] == "contig"
                and re.fullmatch(r"[A-Z]+", parent.get("translated_sequence", "")) is not None,
                "protein-context", "each context feature must be a contig CDS with an explicit protein sequence")
        pairs = parent.get("attributes") or []
        for key, typed in (("ID", [parent["feature_id"]]), ("Parent", parent.get("parent") or []),
                           ("product", [parent["product"]] if "product" in parent else [])):
            generic = values(pairs, key)
            require(not generic or generic == typed, "protein-context",
                    f"context {key} attribute disagrees with its typed slot")
    require(isinstance(context["bindings"], list), "protein-context", "bindings must be a list")
    bindings, used = {}, set()
    for binding in context["bindings"]:
        require(isinstance(binding, dict) and set(binding) == {"protein_id", "cds_id"}
                and isinstance(binding["protein_id"], str) and binding["protein_id"]
                and isinstance(binding["cds_id"], str) and binding["cds_id"],
                "protein-context", "protein bindings require nonempty protein and CDS identifiers")
        protein, cds = binding["protein_id"], binding["cds_id"]
        require(protein not in bindings and cds not in used and cds in parents,
                "protein-context", "protein bindings must uniquely identify existing CDSs")
        bindings[protein] = parents[cds]
        used.add(cds)
    require(used == set(parents), "protein-context", "every context CDS must have one protein binding")
    require(isinstance(context["artifacts"], list) and len(context["artifacts"]) == 2,
            "protein-context", "record structural annotation and protein FASTA provenance")
    for artifact in context["artifacts"]:
        require(isinstance(artifact, dict) and set(artifact) == {"role", "uri", "sha256"}
                and artifact["role"] in ("structural_annotation", "protein_sequence")
                and absolute_artifact_uri(artifact["uri"])
                and isinstance(artifact["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]),
                "protein-context", "artifacts require absolute URIs and SHA-256 digests")
    require({a["role"] for a in context["artifacts"]} == {"structural_annotation", "protein_sequence"}
            and len({a["uri"] for a in context["artifacts"]}) == 2
            and len({a["sha256"] for a in context["artifacts"]}) == 2,
            "protein-context", "declare distinct structural annotation and protein sequence artifacts")
    return bindings


def protein_feature(columns, record_id, bindings):
    rows, mapping = gff_feature(columns, record_id)
    feature = rows[0]
    protein = feature["seqid"]
    require(protein in bindings, "protein-reference", f"no explicit CDS binding for {protein!r}")
    require(mapping["source_has_id"] and not feature.get("parent")
            and feature["strand"] == "." and "phase" not in feature
            and feature.get("source", "").startswith("HMMER ")
            and re.fullmatch(r"PF[0-9]{5}(?:\.[0-9]+)?", feature["type"]),
            "protein-profile", "NMDC Pfam profile requires ID, HMMER source, Pfam accession, no Parent, strand/phase '.'")
    parent = bindings[protein]
    require(feature["end"] <= len(parent["translated_sequence"]),
            "protein-bound", f"{record_id}: hit exceeds the retained protein length")
    feature.update(seqid=parent["seqid"], coordinate_system="protein", parent=[parent["feature_id"]])
    mapping["protein_id"] = protein
    return rows, mapping


def import_source(content, *, profile, reference_context, source_uri, metadata_profile="generic", protein_context=None):
    require(profile in PROFILES, "unsupported-profile", f"no executable conversion profile {profile!r}")
    require(isinstance(reference_context, str) and reference_context.strip(),
            "reference-context", "supply an assembly or source-scoped reference context explicitly")
    if profile == PROTEIN:
        bindings = protein_bindings(protein_context, reference_context)
        require(metadata_profile == "generic", "protein-profile", "protein profile uses generic source metadata")
    else:
        require(protein_context is None, "protein-context", "protein context is only valid with the protein profile")
    source = parse_bytes(content, source_uri=source_uri, format=PROFILES[profile], profile=metadata_profile)
    errors = validation_errors(source, source_validator(), "SourceDocument")
    require(not errors, "source-invalid", "; ".join(errors))
    warnings = [(r["record_id"], r.get("warnings")) for r in source["records"] if r.get("warnings")]
    require(not warnings, "source-syntax", f"source parser reported unsupported or malformed content: {warnings}")
    rows, mappings, contigs = [], [], {}
    regions = {}
    source_records = {r["record_id"]: r for r in source["records"]}
    for record in source["records"]:
        if record.get("metadata_type") == "gff-version":
            require(record["metadata"][0]["value"].strip() == "3", "format-version", "only GFF version 3 is supported")
        if record.get("metadata_type") == "sequence-region":
            region = {a["key"]: a["value"] for a in record["metadata"]}
            regions.setdefault(decoded(region["seqid"]), []).append((int(region["start"]), int(region["end"])))
        if record["kind"] != "feature":
            continue
        try:
            if profile == PROTEIN:
                features, mapping = protein_feature(record["feature_columns"], record["record_id"], bindings)
            else:
                adapter = gff_feature if PROFILES[profile] == "gff3" else bed_features
                features, mapping = adapter(record["feature_columns"], record["record_id"])
        except ConversionError as error:
            raise ConversionError(error.code, f"{record['record_id']}: {error}") from error
        context = source_records.get(record.get("context_record"), {})
        if context.get("metadata_type") == "prodigal-sequence":
            length = int(values(context["metadata"], "seqlen")[0])
            require(all(f["end"] <= length for f in features), "sequence-length",
                    f"{record['record_id']}: feature exceeds its Prodigal sequence-context length")
        rows.extend(features)
        mappings.append(mapping)
        for feature in features:
            contigs.setdefault(feature["seqid"], {"contig_id": feature["seqid"]})
    require(bool(rows), "no-features", "this profile requires at least one feature record")
    protein_ids = {m["feature_ids"][0]: m.get("protein_id") for m in mappings}
    for feature in rows:
        region_id = protein_ids[feature["feature_id"]] if profile == PROTEIN else feature["seqid"]
        for start, end in regions.get(region_id, []):
            require(start <= feature["start"] <= feature["end"] <= end,
                    "declared-region", f"{feature['feature_id']} is outside a declared sequence region")
    dataset = {"contigs": list(contigs.values()), "features": rows}
    if profile == PROTEIN:
        require(set(protein_ids.values()) == set(bindings), "protein-context",
                "protein context must cover exactly the source protein references")
        dataset = deepcopy(protein_context["dataset"])
        dataset["features"].extend(rows)
    errors = validation_errors(dataset, dataset_validator())
    require(not errors, "dataset-invalid", "; ".join(errors))
    bundle = {"conversion_version": 1, "profile": profile, "reference_context": reference_context,
              "source": source, "dataset": dataset, "mappings": mappings}
    if profile == PROTEIN:
        bundle["protein_context"] = deepcopy(protein_context)
    return bundle


def reconstruct_record(profile, by_id, mapping):
    """Rebuild columns from mapped fields, with NO source text/columns argument.

    Ordered attribute indices retain grouping/cardinality; BED child IDs retain
    block order. Promoted attributes are emitted from typed slots after checking
    their generic mirrors. No lexical source cell is used here.
    """
    feature = by_id[mapping["feature_ids"][0]]
    if profile == PROTEIN:
        require(feature["coordinate_system"] == "protein" and len(feature.get("parent", [])) == 1,
                "protein-profile", "protein features require one explicit CDS parent")
        # Protein identity is a semantic reference mapping, not a retained source
        # cell. The contextual CDS relationship is not a source Parent tag.
        projected = {**feature, "seqid": mapping["protein_id"]}
        projected.pop("parent")
        return reconstruct_record("gff3-contig/1.0.0", {feature["feature_id"]: projected}, mapping)
    if PROFILES[profile] == "gff3":
        pairs = feature["attributes"]
        typed = {"ID": [feature["feature_id"]] if mapping["source_has_id"] else [],
                 "Parent": feature.get("parent", []),
                 "product": [feature["product"]] if "product" in feature else []}
        for key, expected in typed.items():
            require(values(pairs, key) == expected, "attribute-conflict", f"generic {key} disagrees with its typed slot")
        offsets = {key: 0 for key in typed}
        assignments = []
        for group in mapping["attribute_groups"]:
            key, indices = group["key"], group["indices"]
            if key in typed:
                offset = offsets[key]
                items = typed[key][offset:offset + len(indices)]
                offsets[key] += len(indices)
            else:
                items = [pairs[i]["value"] for i in indices]
            assignments.append(encoded(key) + "=" + ",".join(encoded(item) for item in items))
        return [encoded_field(feature["seqid"]), encoded_field(feature["source"]) if "source" in feature else ".",
                encoded_field(feature["type"]), str(feature["start"]), str(feature["end"]),
                str(feature["score"]) if "score" in feature else ".", feature["strand"],
                str(feature["phase"]) if "phase" in feature else ".", ";".join(assignments) or "."]
    pairs = feature["attributes"]
    def bed_value(key):
        found = values(pairs, "bed:" + key)
        require(len(found) == 1, "attribute-conflict", f"BED {key} must occur exactly once")
        return found[0]
    blocks = [by_id[fid] for fid in mapping["feature_ids"][1:]]
    return [feature["seqid"], str(feature["start"] - 1), str(feature["end"]), bed_value("name"),
            str(int(feature["score"])), feature["strand"], bed_value("thickStart"), bed_value("thickEnd"),
            bed_value("itemRgb"), str(len(blocks)),
            ",".join(str(b["end"] - b["start"] + 1) for b in blocks) + ",",
            ",".join(str(b["start"] - feature["start"]) for b in blocks) + ","]


def mutable_object_ids(value):
    """Identify shared JSON containers, including shallow copies of a context."""
    pending, seen = [value], set()
    while pending:
        item = pending.pop()
        if not isinstance(item, (dict, list)) or id(item) in seen:
            continue
        seen.add(id(item))
        pending.extend(item.values() if isinstance(item, dict) else item)
    return seen


def validate_bundle(bundle, original_bytes=None, *, protein_context=None):
    try:
        if bundle["profile"] == PROTEIN:
            require(protein_context is not None, "protein-context-original",
                    "supply the independent original protein context for validation/export")
            require(not mutable_object_ids(protein_context) & mutable_object_ids(bundle.get("protein_context")),
                    "protein-context-original", "original context must not share mutable objects with the embedded context")
            require(protein_context == bundle.get("protein_context"), "protein-context-edited",
                    "bundle protein context differs from the supplied original context")
        else:
            require(protein_context is None, "protein-context", "this profile does not use protein context")
        source = bundle["source"]
        content = replay_bytes(source, original_bytes=original_bytes)
        expected = import_source(content, profile=bundle["profile"], reference_context=bundle["reference_context"],
                                 source_uri=source["artifact"]["uri"], metadata_profile=source["profile"],
                                 protein_context=protein_context)
        require(json.dumps(bundle, sort_keys=True) == json.dumps(expected, sort_keys=True),
                "edited-bundle", "bundle differs from its imported projection; edited-instance export is not supported")
        return content
    except (KeyError, TypeError) as error:
        raise ConversionError("bundle-shape", "invalid conversion bundle structure") from error


def export_source(bundle, *, mode, original_bytes=None, protein_context=None):
    require(mode in ("exact", "reconstruct"), "export-mode", "choose exact or reconstruct explicitly")
    content = validate_bundle(bundle, original_bytes, protein_context=protein_context)
    by_id = {f["feature_id"]: f for f in bundle["dataset"]["features"]}
    mappings = {m["record_id"]: m for m in bundle["mappings"]}
    bindings = protein_bindings(bundle["protein_context"], bundle["reference_context"]) if bundle["profile"] == PROTEIN else None
    output = []
    for record in bundle["source"]["records"]:
        if record["kind"] != "feature":
            output.append(record["raw_text"])
            continue
        columns = reconstruct_record(bundle["profile"], by_id, mappings[record["record_id"]])
        # Validate semantic reconstruction even when returning original spellings.
        if bundle["profile"] == PROTEIN:
            rebuilt, mapping = protein_feature(columns, record["record_id"], bindings)
        else:
            adapter = gff_feature if PROFILES[bundle["profile"]] == "gff3" else bed_features
            rebuilt, mapping = adapter(columns, record["record_id"])
        require(rebuilt == [by_id[fid] for fid in mapping["feature_ids"]]
                and mapping == mappings[record["record_id"]],
                "reconstruction-mismatch", f"modeled fields do not reconstruct {record['record_id']}")
        if mode == "exact":
            columns = record["feature_columns"]
        raw = record["raw_text"]
        ending = raw[len(raw.rstrip("\r\n")):]
        prefix = "\ufeff" if raw.startswith("\ufeff") else ""
        output.append(prefix + "\t".join(columns) + ending)
    result = "".join(output).encode("utf-8")
    if mode == "exact":
        require(result == content, "byte-mismatch", "exact reconstruction changed source bytes")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("import")
    load.add_argument("input", type=Path)
    load.add_argument("--profile", required=True)
    load.add_argument("--reference-context", required=True)
    load.add_argument("--metadata-profile", default="generic", choices=("generic", "prodigal", "ncbi"))
    load.add_argument("--source-uri")
    load.add_argument("--protein-context", type=Path, help="Explicit JSON protein-to-CDS context for the NMDC Pfam profile")
    load.add_argument("--output", type=Path, required=True)
    dump = commands.add_parser("export")
    dump.add_argument("input", type=Path)
    dump.add_argument("--mode", choices=("exact", "reconstruct"), required=True)
    dump.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("input", type=Path)
    for command in (dump, validate):
        command.add_argument("--original", type=Path)
        command.add_argument("--protein-context", type=Path, help="Independent original context; required for the protein profile")
    args = parser.parse_args()
    try:
        if args.command == "import":
            bundle = import_source(args.input.read_bytes(), profile=args.profile,
                                   reference_context=args.reference_context, metadata_profile=args.metadata_profile,
                                   source_uri=args.source_uri or args.input.resolve().as_uri(),
                                   protein_context=json.loads(args.protein_context.read_text()) if args.protein_context else None)
            write_new(args.output, (json.dumps(bundle, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        else:
            bundle = json.loads(args.input.read_text(encoding="utf-8"))
            original = args.original.read_bytes() if args.original else None
            context = json.loads(args.protein_context.read_text()) if args.protein_context else None
            if args.command == "export":
                write_new(args.output, export_source(bundle, mode=args.mode, original_bytes=original, protein_context=context))
            else:
                validate_bundle(bundle, original, protein_context=context)
                print(json.dumps({"profile": bundle["profile"], "valid": True, "edited_export": "unsupported"}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "rejected", "code": getattr(error, "code", "input-error"),
                          "message": str(error), "losses": []}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
