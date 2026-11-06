#!/usr/bin/env python3
"""Split one GFF3 file into DuckDB tables, check every row against the schema, and rebuild the file.

Usage: python scripts/split_gff_prototype.py GFF3 DATABASE [--metadata-profile generic|ncbi|prodigal]
           [--reference-context CURIE]

A prototype of what https://github.com/turbomam/feature-table-corpus/issues/185 asks for, not the
fast splitter itself: it reuses scripts/source_document.py, which is stdlib Python and holds the
whole file in memory. It writes these tables:

- source_artifact: the file's URI, SHA-256 and size, one SourceArtifact row.
- header_record: every directive, comment, NCBI #! line, ### sync mark, ##FASTA line and blank
  line, one SourceRecord row each (model/schema/source_document.yaml).
- feature_record: every feature row as a SourceRecord row, so files the gff3-contig profile
  refuses still land.
- biosequence: one row per embedded FASTA sequence, after the BioSQL biosequence table and Chado's
  feature.residues: the residues in one string, plus the header line and line layout needed to
  write the FASTA back exactly.
- contig, contig_collection and sequence_feature: the feature model's tables, written only when
  gff3-contig/4.0.0 accepts the file; otherwise the refusal code is reported.

It then rebuilds the file from DuckDB alone and compares the bytes, and prints one JSON summary.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_duckdb import _populate_database  # noqa: E402
from convert_features import ConversionError, import_source  # noqa: E402
from source_document import parse_bytes  # noqa: E402
from validate_closed import make_validator, validation_errors  # noqa: E402

SOURCE_SCHEMA = ROOT / "model/schema/source_document.yaml"
SEQUENCE_KINDS = {"fasta_header", "fasta_sequence"}


def sequences(records):
    """Group FASTA records into one row per sequence, keeping what an exact rewrite needs."""
    rows, current = [], None
    for record in records:
        if record["kind"] == "fasta_header":
            current = {"header_line_number": record["line_number"], "header_text": record["raw_text"],
                       "lines": []}
            rows.append(current)
        elif record["kind"] == "fasta_sequence":
            current["lines"].append(record["raw_text"])
    out = []
    for row in rows:
        bodies = [line.rstrip("\r\n") for line in row["lines"]]
        endings = {line[len(body):] for line, body in zip(row["lines"], bodies)}
        width = len(bodies[0]) if bodies else 0
        regular = all(len(b) == width for b in bodies[:-1]) and (not bodies or 0 < len(bodies[-1]) <= width)
        out.append({
            "sequence_id": row["header_text"][1:].split()[0] if row["header_text"][1:].split() else "",
            "header_line_number": row["header_line_number"],
            "header_text": row["header_text"],
            "residues": "".join(bodies),
            "length": sum(map(len, bodies)),
            "line_width": width if regular else None,
            "line_lengths": None if regular else [len(b) for b in bodies],
            "line_ending": endings.pop() if len(endings) == 1 else None,
            "last_line_ending": row["lines"][-1][len(bodies[-1]):] if bodies else "",
        })
    return out


def sequence_lines(row):
    residues, ending = row["residues"], row["line_ending"]
    lengths = row["line_lengths"]
    if lengths is None:
        width = row["line_width"]
        lengths = [width] * (len(residues) // width) + ([len(residues) % width] if len(residues) % width else [])
    lines, start = [], 0
    for index, size in enumerate(lengths):
        last = index == len(lengths) - 1
        lines.append(residues[start:start + size] + (row["last_line_ending"] if last else ending))
        start += size
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("gff3", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("--metadata-profile", default="generic", choices=("generic", "ncbi", "prodigal"))
    parser.add_argument("--reference-context", default=None)
    args = parser.parse_args()
    content = args.gff3.read_bytes()
    times = {}

    start = time.perf_counter()
    document = parse_bytes(content, source_uri=args.gff3.resolve().as_uri(), format="gff3", profile=args.metadata_profile)
    times["parse_s"] = time.perf_counter() - start

    start = time.perf_counter()
    record_validator = make_validator(SOURCE_SCHEMA, "SourceRecord")
    invalid = [r["record_id"] for r in document["records"]
               if r["kind"] not in SEQUENCE_KINDS and validation_errors(r, record_validator, "SourceRecord")]
    artifact_errors = validation_errors(document["artifact"], make_validator(SOURCE_SCHEMA, "SourceArtifact"),
                                        "SourceArtifact")
    times["validate_rows_s"] = time.perf_counter() - start

    dataset, refusal = None, None
    start = time.perf_counter()
    try:
        bundle = import_source(content, profile="gff3-contig/4.0.0", reference_context=args.reference_context
                               or f"file:{args.gff3.name}", source_uri=args.gff3.resolve().as_uri(),
                               metadata_profile=args.metadata_profile)
        dataset = bundle["dataset"]
    except ConversionError as error:
        refusal = f"{error.code}: {error}"
    times["model_import_s"] = time.perf_counter() - start

    start = time.perf_counter()
    args.database.unlink(missing_ok=True)
    if dataset is not None:
        _populate_database(dataset, args.database)
    con = duckdb.connect(str(args.database))
    con.execute("CREATE TABLE source_artifact (uri VARCHAR, sha256 VARCHAR, byte_size BIGINT)")
    con.execute("INSERT INTO source_artifact VALUES (?, ?, ?)", list(document["artifact"].values()))
    for table in ("header_record", "feature_record"):
        con.execute(f"""CREATE TABLE {table} (record_id VARCHAR PRIMARY KEY, line_number BIGINT, raw_text VARCHAR,
                        kind VARCHAR, scope VARCHAR, sequence_id VARCHAR, metadata_type VARCHAR,
                        metadata JSON, feature_columns VARCHAR[])""")
    rows = {"header_record": [], "feature_record": []}
    for record in document["records"]:
        if record["kind"] in SEQUENCE_KINDS:
            continue
        rows["feature_record" if record["kind"] == "feature" else "header_record"].append([
            record["record_id"], record["line_number"], record["raw_text"], record["kind"], record["scope"],
            record.get("sequence_id"), record.get("metadata_type"),
            json.dumps(record["metadata"]) if "metadata" in record else None, record.get("feature_columns")])
    for table, values in rows.items():
        if values:
            con.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", values)
    con.execute("""CREATE TABLE biosequence (sequence_id VARCHAR, header_line_number BIGINT, header_text VARCHAR,
                   residues VARCHAR, length BIGINT, line_width INTEGER, line_lengths INTEGER[],
                   line_ending VARCHAR, last_line_ending VARCHAR)""")
    for row in sequences(document["records"]):
        con.execute("INSERT INTO biosequence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row.values()))
    con.close()
    times["write_duckdb_s"] = time.perf_counter() - start

    start = time.perf_counter()
    con = duckdb.connect(str(args.database), read_only=True)
    lines = con.execute("""SELECT line_number, raw_text FROM header_record
                           UNION ALL SELECT line_number, raw_text FROM feature_record""").fetchall()
    columns = [d[0] for d in con.execute("SELECT * FROM biosequence").description]
    for values in con.execute("SELECT * FROM biosequence ORDER BY header_line_number").fetchall():
        row = dict(zip(columns, values))
        lines.append((row["header_line_number"], row["header_text"]))
        for offset, line in enumerate(sequence_lines(row), start=1):
            lines.append((row["header_line_number"] + offset, line))
    tables = {name: con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
              for (name,) in con.execute("SHOW TABLES").fetchall()}
    header_kinds = dict(con.execute("SELECT kind, count(*) FROM header_record GROUP BY kind ORDER BY kind").fetchall())
    directives = dict(con.execute("""SELECT coalesce(metadata_type, kind), count(*) FROM header_record
                                     WHERE kind IN ('directive', 'comment') GROUP BY 1 ORDER BY 1""").fetchall())
    con.close()
    rebuilt = "".join(text for _, text in sorted(lines)).encode("utf-8")
    times["rebuild_s"] = time.perf_counter() - start

    print(json.dumps({
        "file": args.gff3.as_posix(), "bytes": len(content), "lines": len(document["records"]),
        "tables": tables, "header_kinds": header_kinds, "directives_and_comments": directives,
        "source_rows_invalid": invalid, "artifact_errors": artifact_errors,
        "model_tables_written": dataset is not None, "gff3_contig_refusal": refusal,
        "rebuilt_identical": rebuilt == content, "seconds": {k: round(v, 3) for k, v in times.items()},
    }, indent=1))


if __name__ == "__main__":
    main()
