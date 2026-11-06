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
  write the FASTA back exactly. The layout uses the samtools faidx .fai column meanings (offset,
  bases per line, bytes per line) and falls back to one entry per line for layouts faidx refuses.
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
    """Group FASTA records into one row per sequence, keeping what an exact rewrite needs.

    Residues come from the reader's sequence_text, which has no whitespace. A sequence laid out the
    way samtools faidx expects (consecutive lines, each line but the last holding line_bases residues
    in line_bytes bytes, the last no longer) is stored as the faidx columns plus its line endings.
    Any other layout keeps one entry per line with its line number, residue count and ending, plus
    the raw text when the line holds more than residues and ending.
    """
    rows, current, position = [], None, 0
    for record in records:
        size = len(record["raw_text"].encode("utf-8"))
        if record["kind"] == "fasta_header":
            current = {"sequence_id": record.get("sequence_id", ""),
                       "header_line_number": record["line_number"], "header_text": record["raw_text"],
                       "offset": position + size, "lines": []}
            rows.append(current)
        elif record["kind"] == "fasta_sequence":
            if not current["lines"]:
                current["offset"] = position
            current["lines"].append(record)
        position += size
    out = []
    for row in rows:
        lines = row["lines"]
        bases = [r["sequence_text"] for r in lines]
        endings = [r["raw_text"][len(r["raw_text"].rstrip("\r\n")):] for r in lines]
        line_bases = len(bases[0]) if lines else 0
        ending = endings[0] if lines else ""
        regular = (all(r["raw_text"] == b + e for r, b, e in zip(lines, bases, endings))
                   and all(r["line_number"] == row["header_line_number"] + n for n, r in enumerate(lines, start=1))
                   and all(len(b) == line_bases and e == ending for b, e in zip(bases[:-1], endings[:-1]))
                   and (not lines or len(bases[-1]) <= line_bases))
        residues = "".join(bases)
        out.append({
            # The reader's own identifier, so a byte-order mark before ">" is not read as part of it.
            "sequence_id": row["sequence_id"],
            "header_line_number": row["header_line_number"],
            "header_text": row["header_text"],
            "residues": residues,
            "length": len(residues),
            "offset": row["offset"],
            "line_bases": line_bases if regular else None,
            "line_bytes": line_bases + len(ending.encode("utf-8")) if regular else None,
            "line_ending": ending if regular else None,
            "last_line_ending": (endings[-1] if lines else "") if regular else None,
            "lines": None if regular else [
                {"line_number": r["line_number"], "bases": len(b), "line_ending": e,
                 "raw_text": None if r["raw_text"] == b + e else r["raw_text"]}
                for r, b, e in zip(lines, bases, endings)],
        })
    return out


def sequence_lines(row):
    """Return (line_number, raw_text) for each sequence line of one biosequence row."""
    residues = row["residues"]
    if row["lines"] is not None:
        out, start = [], 0
        for line in row["lines"]:
            text = residues[start:start + line["bases"]] + line["line_ending"]
            out.append((line["line_number"], line["raw_text"] if line["raw_text"] is not None else text))
            start += line["bases"]
        return out
    width = row["line_bases"]
    count = -(-row["length"] // width) if width else 0
    return [(row["header_line_number"] + n + 1, residues[n * width:(n + 1) * width]
             + (row["last_line_ending"] if n == count - 1 else row["line_ending"])) for n in range(count)]


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
    if args.database.resolve() == args.gff3.resolve():
        parser.error("the database path is the input file; choose another path so the input is not overwritten")
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
                   residues VARCHAR, length BIGINT, "offset" BIGINT, line_bases INTEGER, line_bytes INTEGER,
                   line_ending VARCHAR, last_line_ending VARCHAR,
                   lines STRUCT(line_number BIGINT, bases INTEGER, line_ending VARCHAR, raw_text VARCHAR)[])""")
    for row in sequences(document["records"]):
        con.execute("INSERT INTO biosequence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row.values()))
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
        lines.extend(sequence_lines(row))
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
