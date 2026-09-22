#!/usr/bin/env python3
"""Small, parameterized queries over the draft model's DuckDB mapping."""
import argparse
import json

import duckdb


def multiple_pfams(con, accessions=()):
    """CDS parents with at least two distinct Pfams, optionally all named accessions.

    Match exact source accessions. Repeated hits to one Pfam and CRISPR repeat
    children do not satisfy this query. A child shared by several parents counts
    once for each parent; repeated child rows do not inflate the distinct count.
    """
    accessions = sorted(set(accessions))
    if accessions and len(accessions) < 2:
        raise ValueError("Supply at least two distinct Pfam accessions, or none")
    return con.execute("""
        SELECT p.feature_id, p.product, count(DISTINCT c.type) AS n_pfams,
               list_sort(list(DISTINCT c.type)) AS pfams
        FROM feature p JOIN feature c ON list_contains(c.parent, p.feature_id)
        WHERE p.type = 'CDS' AND p.coordinate_system = 'contig'
          AND c.coordinate_system = 'protein'
          AND regexp_full_match(c.type, 'PF[0-9]{5}(\\.[0-9]+)?')
          AND (? = 0 OR list_contains(?::VARCHAR[], c.type))
        GROUP BY p.feature_id, p.product
        HAVING count(DISTINCT c.type) >= ?
        ORDER BY p.feature_id
    """, [len(accessions), accessions, max(2, len(accessions))]).fetchall()


def interval_overlap(con, sequence_id, start, end, coordinate_system="contig"):
    """Inclusive overlap: sequence_id is a contig ID or a parent CDS ID, respectively."""
    if type(start) is not int or type(end) is not int:
        raise ValueError("Interval endpoints must be integers (not booleans or floats)")
    if start < 1 or end < start:
        raise ValueError("Interval must be 1-based inclusive with start <= end")
    if coordinate_system not in ("contig", "protein"):
        raise ValueError("coordinate_system must be contig or protein")
    if coordinate_system == "contig" and con.execute('''
        SELECT count(*) FROM feature f, json_each(f.location, '$.parts') p
        WHERE f.seqid = ? AND
          ((p.value->>'start_status') != 'exact' OR (p.value->>'end_status') != 'exact')
    ''', [sequence_id]).fetchone()[0]:
        raise ValueError("reference has uncertain endpoints; use the explicit location query's reported-bounds mode")
    return con.execute("""
        SELECT feature_id, type, start, "end", coordinate_system
        FROM feature
        WHERE coordinate_system = ?
          AND ((location IS NULL AND start <= ? AND "end" >= ?)
            OR EXISTS (SELECT 1 FROM json_each(location, '$.parts') p
                       WHERE CAST(p.value->>'start' AS BIGINT) <= ? AND CAST(p.value->>'end' AS BIGINT) >= ?))
          AND ((coordinate_system = 'contig' AND seqid = ?)
            OR (coordinate_system = 'protein' AND list_contains(parent, ?)))
        ORDER BY feature_id
    """, [coordinate_system, end, start, end, start, sequence_id, sequence_id]).fetchall()


def by_attribute(con, key, value):
    return con.execute("""
        SELECT DISTINCT f.feature_id
        FROM feature f, unnest(f.attributes) AS a(item)
        WHERE a.item.key = ? AND a.item.value = ?
        ORDER BY f.feature_id
    """, [key, value]).fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    commands = parser.add_subparsers(dest="command", required=True)
    pfams = commands.add_parser("pfams")
    pfams.add_argument("accessions", nargs="*")
    overlap = commands.add_parser("overlap")
    overlap.add_argument("coordinate_system", choices=("contig", "protein"))
    overlap.add_argument("sequence_id", help="Contig ID for contig coordinates; parent CDS ID for protein coordinates")
    overlap.add_argument("start", type=int)
    overlap.add_argument("end", type=int)
    attribute = commands.add_parser("attribute")
    attribute.add_argument("key")
    attribute.add_argument("value")
    args = parser.parse_args()
    con = duckdb.connect(args.database, read_only=True)
    try:
        if args.command == "pfams":
            rows = multiple_pfams(con, args.accessions)
        elif args.command == "overlap":
            rows = interval_overlap(con, args.sequence_id, args.start, args.end, args.coordinate_system)
        else:
            rows = by_attribute(con, args.key, args.value)
        print(json.dumps(rows, indent=2))
    except ValueError as error:
        parser.error(str(error))
    finally:
        con.close()


if __name__ == "__main__":
    main()
