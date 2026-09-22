#!/usr/bin/env python3
"""Reproduce a source-grounded actinorhodin gene-order/proximity exercise offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import unquote

import duckdb

from build_duckdb import build_database
from convert_features import export_source, import_source, require, validate_bundle

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3"
SOURCE_SHA = "e49de7213e25d075e0b79541f8a49288a055ae87bdd355931d129c0573026858"
EXCERPT = ROOT / "corpus/derived-examples/actinorhodin.gff3"
REPORT = ROOT / "analyses/bgc-query/report.json"
EXPECTED = ROOT / "analyses/bgc-query/expected.json"
REFERENCE = "refseq:NC_003888.3"
SEQID = "NC_003888.3"
PROFILE = "gff3-contig/1.0.0"
FIRST, LAST = 5513809, 5535091
FOCUS_FIRST, FOCUS_LAST = 5529801, 5532709
URI = "https://github.com/turbomam/feature-table-corpus/blob/main/corpus/derived-examples/actinorhodin.gff3"


def source_rows(content):
    """Direct source inspection, independent of the conversion/SQL implementations."""
    for line_number, line in enumerate(content.splitlines(keepends=True), 1):
        if not line.strip() or line.startswith(b"#"):
            continue
        columns = line.decode().rstrip("\r\n").split("\t")
        require(len(columns) == 9, "bgc-source", "expected nine source columns")
        attrs = {}
        for token in columns[8].split(";"):
            key, separator, value = token.partition("=")
            if separator:
                attrs.setdefault(unquote(key), []).extend(unquote(v) for v in value.split(","))
        yield line_number, line, columns, attrs


def derive_source(content):
    require(hashlib.sha256(content).hexdigest() == SOURCE_SHA, "bgc-source", "source checksum changed")
    rows = list(source_rows(content))
    wanted = {f"SCO{i}" for i in range(5071, 5093)}
    genes = {a["ID"][0]: a["old_locus_tag"][0] for _, _, c, a in rows
             if c[2] == "gene" and set(a.get("old_locus_tag", ())) & wanted}
    require(set(genes.values()) == wanted, "bgc-source", "source does not cover the declared 22 genes")
    selected = [line for _, line, c, a in rows
                if a.get("ID", [None])[0] in genes
                or (c[2] == "CDS" and set(a.get("Parent", ())) & genes.keys())]
    require(len(selected) == 44, "bgc-source", "expected 22 gene and 22 CDS rows")
    header = b"".join(line for line in content.splitlines(keepends=True) if line.startswith(b"#"))
    provenance = (
        "# derived-from: corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3\n"
        "# single-change: select SCO5071-SCO5092 gene rows and their direct CDS children; retain header and absolute coordinates\n"
        "# validity: valid GFF3; selected source rows, not a complete chromosome annotation\n"
    ).encode()
    return header + provenance + b"".join(selected)


def query_order(con, *, reference_context, sequence_id, start, end,
                coordinate_system="contig", product=None, old_locus_tags=()):
    # This bounded exercise uses one versioned RefSeq sequence. Derive its
    # qualified context from stored reference identity, never a second caller claim.
    references = con.execute("SELECT contig_id FROM contig").fetchall()
    require(len(references) == 1 and re.fullmatch(r"NC_[0-9]+\.[1-9][0-9]*", references[0][0]),
            "reference-context", "BGC query requires one stored, versioned RefSeq chromosome")
    trusted_reference = "refseq:" + references[0][0]
    require(isinstance(reference_context, str) and reference_context == trusted_reference,
            "reference-context", "query reference differs from the stored database reference")
    require(coordinate_system == "contig", "coordinate-space", "genomic gene order requires contig coordinates")
    require(type(start) is int and type(end) is int and 1 <= start <= end,
            "query-interval", "query bounds must be one-based inclusive integers")
    rows = con.execute('''
        SELECT g.feature_id, a.item.value, c.feature_id, c.start, c."end", c.strand, c.product
        FROM feature g, unnest(g.attributes) a(item), feature c
        WHERE g.type = 'gene' AND g.coordinate_system = 'contig'
          AND c.type = 'CDS' AND c.coordinate_system = 'contig'
          AND g.seqid = ? AND c.seqid = g.seqid AND list_contains(c.parent, g.feature_id)
          AND a.item.key = 'old_locus_tag' AND c.start <= ? AND c."end" >= ?
          AND (? IS NULL OR c.product = ?)
          AND (? = 0 OR list_contains(?::VARCHAR[], a.item.value))
        ORDER BY c.start, c."end", c.feature_id
    ''', [sequence_id, end, start, product, product, len(old_locus_tags), list(old_locus_tags)]).fetchall()
    names = ("gene_id", "old_locus_tag", "cds_id", "start", "end", "strand", "product")
    return [dict(zip(names, row)) for row in rows]


def make_report():
    content = SOURCE.read_bytes()
    excerpt = derive_source(content)
    require(EXCERPT.read_bytes() == excerpt, "bgc-excerpt", "derived example does not reproduce")
    expected = json.loads(EXPECTED.read_text())
    bundle = import_source(excerpt, profile=PROFILE, reference_context=REFERENCE, source_uri=URI, metadata_profile="ncbi")
    validate_bundle(bundle)
    exact = export_source(bundle, mode="exact", original_bytes=excerpt)
    reconstructed = export_source(bundle, mode="reconstruct", original_bytes=excerpt)
    again = import_source(reconstructed, profile=PROFILE, reference_context=REFERENCE, source_uri=URI, metadata_profile="ncbi")
    require(exact == excerpt and again["dataset"] == bundle["dataset"] and again["mappings"] == bundle["mappings"],
            "bgc-roundtrip", "conversion preservation failed")
    (ROOT / "local").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "local") as work:
        data, db = Path(work) / "dataset.json", Path(work) / "features.duckdb"
        data.write_text(json.dumps(bundle["dataset"]))
        build_database(ROOT / "model/schema/ber_feature_model.yaml", data, db)
        with duckdb.connect(str(db), read_only=True) as con:
            arguments = dict(reference_context=REFERENCE,
                             sequence_id=SEQID, start=FOCUS_FIRST, end=FOCUS_LAST)
            focus = query_order(con, **arguments, old_locus_tags=("SCO5087", "SCO5088", "SCO5089"))
            order = query_order(con, **{**arguments, "start": FIRST, "end": LAST})
            negatives = {
                "out_of_range": query_order(con, **{**arguments, "start": 1, "end": 100}),
                "absent_product": query_order(con, **arguments, product="deliberately absent annotation"),
                "wrong_sequence": query_order(con, **{**arguments, "sequence_id": "NC_003888.2"}),
            }
            for name, override in (("wrong_reference", {"reference_context": "refseq:NC_003888.2"}),
                                   ("protein_space", {"coordinate_system": "protein"})):
                try:
                    query_order(con, **{**arguments, **override})
                except ValueError as error:
                    negatives[name] = error.code
                else:
                    raise ValueError(f"{name} was incorrectly accepted")
    gaps = [right["start"] - left["end"] - 1 for left, right in zip(focus, focus[1:])]
    observed = {"focus": focus, "signed_gaps_bp": gaps,
                "cluster_gene_order": [row["old_locus_tag"] for row in order], "negative_controls": negatives}
    require(observed == expected, "bgc-query", "query results differ from independently recorded source expectations")
    evidence = [{"line": number, "old_locus_tag": a["old_locus_tag"][0],
                 "start": int(c[3]), "end": int(c[4]), "strand": c[6]}
                for number, _, c, a in source_rows(content)
                if c[2] == "gene" and set(a.get("old_locus_tag", ())) & {"SCO5087", "SCO5088", "SCO5089"}]
    require([(r["old_locus_tag"], r["start"], r["end"], r["strand"]) for r in evidence] ==
            [(r["old_locus_tag"], r["start"], r["end"], r["strand"]) for r in expected["focus"]],
            "bgc-evidence", "direct source inspection differs from checked-in expectations")
    return {"report_version": 1, "profile": PROFILE, "reference_context": REFERENCE, "seqid": SEQID,
            "source_sha256": SOURCE_SHA, "excerpt_sha256": hashlib.sha256(excerpt).hexdigest(),
            "source_feature_rows": 44, "exact_export": "byte-identical excerpt",
            "reconstructed_export": "same mapped fields and relationships",
            "source_evidence": evidence, "query_results": observed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if not args.check:
            EXCERPT.write_bytes(derive_source(SOURCE.read_bytes()))
        text = json.dumps(make_report(), indent=2) + "\n"
        if args.check:
            require(REPORT.read_text() == text, "stale-report", "BGC report does not reproduce")
            print("BGC source selection, round trips and queries reproduce exactly")
        else:
            REPORT.write_text(text)
            print(f"wrote {EXCERPT} and {REPORT}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
