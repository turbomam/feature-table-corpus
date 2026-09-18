#!/usr/bin/env python3
"""Load a schema/ber_feature_model.yaml-shaped dataset into DuckDB.

Answers the "what would this look like in a relational lakehouse" question with a real,
queryable artifact instead of a claim. Resolves scripts/flat_profile_audit.py's findings
against this schema (run 2026-09-18, first time against ber_feature_model.yaml):

  25 class/slot pairs, 19 admissible under a scalar-only profile as written, 6 rejected:
    - 4 multivalued class references (Dataset.contigs, Dataset.features, Feature.parent,
      Feature.attributes) -> child/junction tables, or in DuckDB's case a native LIST
      column, which is the choice made here for parent and attributes (see below).
    - 1 identified class reference (Feature.seqid -> Contig) -> a scalar id column plus a
      foreign key. Mechanical; done exactly that way below.
    - 1 multivalued scalar (Contig.taxonomic_lineage) -> the one real decision the audit
      flagged, array column or a junction table. Resolved here as a native LIST(VARCHAR)
      column, not a junction table, because DuckDB (and Parquet/Iceberg, which is what
      BERDL actually runs on) supports nested list and struct columns directly. This
      exercises the 2026-09-17 finding that BRIDGE does not require a scalar-only profile,
      so there is no forcing function to normalize this into a join.

Two tables, matching the schema's two entity classes:
  contig(contig_id, length_bp, lineage_confidence, taxonomic_lineage LIST(VARCHAR))
  feature(feature_id, seqid FK->contig, source, type, start, end, coordinate_system,
          score, strand, phase, predicted_by, is_selected, product, product_source,
          translated_sequence, parent LIST(VARCHAR), attributes LIST(STRUCT(tag, value)))

`parent` and `attributes` are native LIST columns, not junction tables. Chosen deliberately,
not because a junction table would be wrong; it is the schema's own general position
(multivalued and nested slots used directly, see the schema file's own notes) carried
through to the physical layer, and DuckDB can query into both directly with unnest().

Usage:
    uv run --with duckdb --with pyyaml python scripts/build_duckdb.py \
        SCHEMA_YAML DATA_YAML OUTPUT_DUCKDB
"""
import sys

import duckdb
import yaml


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    _schema_path, data_path, db_path = sys.argv[1:4]

    data = yaml.safe_load(open(data_path))

    con = duckdb.connect(db_path)
    con.execute("DROP TABLE IF EXISTS feature")
    con.execute("DROP TABLE IF EXISTS contig")

    con.execute("""
        CREATE TABLE contig (
            contig_id VARCHAR PRIMARY KEY,
            length_bp INTEGER,
            lineage_confidence DOUBLE,
            taxonomic_lineage VARCHAR[]
        )
    """)
    con.execute("""
        CREATE TABLE feature (
            feature_id VARCHAR PRIMARY KEY,
            seqid VARCHAR REFERENCES contig(contig_id),
            source VARCHAR,
            type VARCHAR,
            start INTEGER,
            "end" INTEGER,
            coordinate_system VARCHAR,
            score DOUBLE,
            strand VARCHAR,
            phase INTEGER,
            predicted_by VARCHAR,
            is_selected BOOLEAN,
            product VARCHAR,
            product_source VARCHAR,
            translated_sequence VARCHAR,
            parent VARCHAR[],
            attributes STRUCT(tag VARCHAR, value VARCHAR)[]
        )
    """)

    for c in data.get("contigs", []):
        con.execute(
            "INSERT INTO contig VALUES (?, ?, ?, ?)",
            [c.get("contig_id"), c.get("length_bp"), c.get("lineage_confidence"),
             c.get("taxonomic_lineage")],
        )

    for f in data.get("features", []):
        attrs = [{"tag": a["tag"], "value": a["value"]} for a in f.get("attributes", [])]
        con.execute(
            """INSERT INTO feature VALUES
               (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [f.get("feature_id"), f.get("seqid"), f.get("source"), f.get("type"),
             f.get("start"), f.get("end"), f.get("coordinate_system"), f.get("score"),
             f.get("strand"), f.get("phase"), f.get("predicted_by"),
             f.get("is_selected"), f.get("product"), f.get("product_source"),
             f.get("translated_sequence"), f.get("parent"), attrs],
        )

    n_contigs = con.execute("SELECT count(*) FROM contig").fetchone()[0]
    n_features = con.execute("SELECT count(*) FROM feature").fetchone()[0]
    print(f"Wrote {db_path}: {n_contigs} contigs, {n_features} features")
    con.close()


if __name__ == "__main__":
    main()
