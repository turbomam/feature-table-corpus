#!/usr/bin/env python3
"""Build explicit CDS/protein context from retained NMDC structural GFF and FASTA."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

from convert_features import (PROTEIN, decoded, import_source, protein_bindings, require)
from source_document import parse_bytes, write_new


def build_context(annotation, structural, fasta, *, reference_context, annotation_uri, structural_uri, fasta_uri):
    structural_bundle = import_source(structural, profile="gff3-contig/1.0.0",
                                      reference_context=reference_context, source_uri=structural_uri)
    document = parse_bytes(annotation, source_uri=annotation_uri, format="gff3", profile="generic")
    needed = {decoded(r["feature_columns"][0]) for r in document["records"] if r["kind"] == "feature"}
    proteins, current = {}, None
    for line in fasta.decode("utf-8").splitlines():
        if line.startswith(">"):
            fields = line[1:].split()
            require(bool(fields) and fields[0] not in proteins, "protein-fasta", "FASTA IDs must be nonempty and unique")
            current = fields[0]
            proteins[current] = ""
        elif line:
            require(current is not None and re.fullmatch(r"[A-Z]+", line), "protein-fasta", "expected uppercase amino-acid sequence")
            proteins[current] += line
    by_id = {f["feature_id"]: f for f in structural_bundle["dataset"]["features"]}
    require(needed <= proteins.keys() and needed <= by_id.keys(), "protein-reference",
            "every Pfam protein ID must match both a structural CDS ID and a FASTA record")
    parents = []
    for identifier in sorted(needed):
        parent = deepcopy(by_id[identifier])
        require(parent["type"] == "CDS", "protein-reference", f"{identifier} is not a CDS")
        parent["translated_sequence"] = proteins[identifier]
        parent["source_files"] = [structural_uri, fasta_uri]
        parents.append(parent)
    contigs = sorted({p["seqid"] for p in parents})
    context = {"context_version": 1, "reference_context": reference_context,
               "dataset": {"contigs": [{"contig_id": c} for c in contigs], "features": parents},
               "bindings": [{"protein_id": p["feature_id"], "cds_id": p["feature_id"]} for p in parents],
               "artifacts": [{"uri": uri, "sha256": hashlib.sha256(content).hexdigest()} for uri, content in
                             ((structural_uri, structural), (fasta_uri, fasta))]}
    protein_bindings(context, reference_context)
    # Check actual producer annotations against this context before writing it.
    import_source(annotation, profile=PROTEIN, reference_context=reference_context,
                  source_uri=annotation_uri, protein_context=context)
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("annotation", "structural", "fasta", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--reference-context", required=True)
    for name in ("annotation", "structural", "fasta"):
        parser.add_argument(f"--{name}-uri", required=True)
    args = parser.parse_args()
    try:
        context = build_context(args.annotation.read_bytes(), args.structural.read_bytes(), args.fasta.read_bytes(),
                                reference_context=args.reference_context, annotation_uri=args.annotation_uri,
                                structural_uri=args.structural_uri, fasta_uri=args.fasta_uri)
        write_new(args.output, (json.dumps(context, indent=2) + "\n").encode())
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "rejected", "code": getattr(error, "code", "input-error"), "message": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
