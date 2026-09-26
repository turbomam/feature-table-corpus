#!/usr/bin/env python3
"""Validate a harmonized Dataset and load it into DuckDB.

Usage: python scripts/build_duckdb.py SCHEMA_YAML DATA_YAML OUTPUT_DUCKDB

This is an explicit physical mapping of the draft model, not a general LinkML DDL
generator. Multivalued fields use native LIST/STRUCT columns. Validation precedes
opening the output, and table replacement is transactional. A new database is
published only after a successful build; temporary files stay beside its destination.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

import duckdb

from validate_closed import load_validated


COLLECTION_COLUMNS = (
    "collection_id", "collection_type", "name", "taxonomic_lineage", "generated_by", "source_files",
)
CONTIG_COLUMNS = (
    "contig_id", "length_bp", "lineage_confidence", "taxonomic_lineage",
    "generated_by", "source_files", "topology", "member_of", "translation_table",
)
FEATURE_COLUMNS = (
    "feature_id", "stable_identifiers", "seqid", "source", "type", "start", "end", "coordinate_system",
    "score", "score_type", "strand", "phase", "generated_by", "source_files", "is_selected",
    "product", "product_source", "translated_sequence", "parent", "attributes", "location",
)


def build_database(schema_path, data_path, db_path):
    destination = Path(db_path)
    existed_at_start = destination.exists()
    data = load_validated(schema_path, data_path)
    if str(db_path) == ':memory:' or existed_at_start:
        return _populate_database(data, db_path)
    with tempfile.TemporaryDirectory(prefix=f'.{destination.name}.', dir=destination.parent) as work:
        staged = Path(work) / 'build.duckdb'
        counts = _populate_database(data, staged)
        # Atomic publication without overwriting a destination created meanwhile.
        # The connection is closed before publication, including its WAL checkpoint.
        os.link(staged, destination)
        return counts


def _populate_database(data, db_path):
    con = duckdb.connect(str(db_path))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute("DROP TABLE IF EXISTS feature")
        con.execute("DROP TABLE IF EXISTS contig")
        con.execute("DROP TABLE IF EXISTS contig_collection")
        con.execute("""
            CREATE TABLE contig_collection (
                collection_id VARCHAR PRIMARY KEY,
                collection_type VARCHAR,
                name VARCHAR,
                taxonomic_lineage VARCHAR[],
                generated_by VARCHAR,
                source_files VARCHAR[]
            )
        """)
        con.execute("""
            CREATE TABLE contig (
                contig_id VARCHAR PRIMARY KEY,
                length_bp BIGINT CHECK (length_bp >= 1),
                lineage_confidence DOUBLE,
                taxonomic_lineage VARCHAR[],
                generated_by VARCHAR,
                source_files VARCHAR[],
                topology VARCHAR,
                member_of VARCHAR[],
                translation_table INTEGER
            )
        """)
        con.execute("""
            CREATE TABLE feature (
                feature_id VARCHAR PRIMARY KEY,
                stable_identifiers VARCHAR[],
                seqid VARCHAR NOT NULL REFERENCES contig(contig_id),
                source VARCHAR,
                type VARCHAR,
                start BIGINT NOT NULL CHECK (start >= 1),
                "end" BIGINT NOT NULL CHECK ("end" >= start),
                coordinate_system VARCHAR NOT NULL
                    CHECK (coordinate_system IN ('contig', 'protein')),
                score DOUBLE,
                score_type VARCHAR,
                strand VARCHAR,
                phase INTEGER CHECK (phase BETWEEN 0 AND 2),
                generated_by VARCHAR,
                source_files VARCHAR[],
                is_selected BOOLEAN,
                product VARCHAR,
                product_source VARCHAR,
                translated_sequence VARCHAR,
                parent VARCHAR[],
                attributes STRUCT(key VARCHAR, value VARCHAR)[],
                location JSON
            )
        """)
        for table, collection, columns in (
            ("contig_collection", "contig_collections", COLLECTION_COLUMNS),
            ("contig", "contigs", CONTIG_COLUMNS),
            ("feature", "features", FEATURE_COLUMNS),
        ):
            # DuckDB interprets a Python dict with exactly key/value keys as a MAP.
            # Cast JSON explicitly so the generic attribute stays a STRUCT.
            placeholders = ", ".join(
                "?::JSON::STRUCT(key VARCHAR, value VARCHAR)[]" if c == "attributes" else "?::JSON" if c == "location" else "?"
                for c in columns
            )
            for row in data.get(collection) or []:
                con.execute(
                    f"INSERT INTO {table} VALUES ({placeholders})",
                    [json.dumps(row[c]) if c in ("attributes", "location") and row.get(c) is not None else row.get(c) for c in columns],
                )
        counts = (
            con.execute("SELECT count(*) FROM contig").fetchone()[0],
            con.execute("SELECT count(*) FROM feature").fetchone()[0],
            con.execute("SELECT count(*) FROM contig_collection").fetchone()[0],
        )
        con.execute("COMMIT")
        return counts
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        n_contigs, n_features, n_collections = build_database(*sys.argv[1:])
    except (ValueError, duckdb.Error, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Wrote {sys.argv[3]}: {n_collections} contig collections, {n_contigs} contigs, {n_features} features")
    return 0


if __name__ == "__main__":
    sys.exit(main())
