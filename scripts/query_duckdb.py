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
    """Inclusive overlap on one reference: a contig ID, or for protein coordinates a CDS ID.

    Both are seqid, so the join is the same in either space; coordinate_system still has to
    match, since a CDS is also a contig-coordinate feature."""
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
          AND seqid = ?
        ORDER BY feature_id
    """, [coordinate_system, end, start, end, start, sequence_id]).fetchall()


def neighbors(con, sequence_id, position, count=2, feature_type="gene"):
    """Features of one type around a 1-based contig position: those containing it, and the
    nearest count on each side, in chromosome order.

    side is left, contains or right in chromosome coordinates; strand is returned so the caller
    can read upstream and downstream for whichever feature they mean. intervening_bases counts
    the bases strictly between the position and the feature, as in the BGC gene-order exercise.
    Uses each feature's start and end, so a spliced feature's introns count as occupied.
    Refused rather than answered wrongly: a circular contig (its nearest features may lie across
    the origin), a position past the contig's recorded length, a CDS that protein-coordinate hits
    use as their reference, and features of the requested type with uncertain endpoints."""
    if type(position) is not int or position < 1:
        raise ValueError("position must be a 1-based integer")
    if type(count) is not int or count < 0:
        raise ValueError("count must be a non-negative integer")
    if con.execute("SELECT count(*) FROM contig WHERE contig_id = ? AND topology = 'circular'",
                   [sequence_id]).fetchone()[0]:
        raise ValueError("circular contig: neighbors across the origin are not handled")
    length = con.execute("SELECT max(length_bp) FROM contig WHERE contig_id = ?", [sequence_id]).fetchone()[0]
    if length is not None and position > length:
        raise ValueError(f"position {position} is beyond the contig's {length} bases")
    if con.execute("SELECT count(*) FROM feature WHERE seqid = ? AND coordinate_system = 'protein'",
                   [sequence_id]).fetchone()[0]:
        raise ValueError("reference is a protein-coordinate sequence; neighbors needs a contig")
    if con.execute('''
        SELECT count(*) FROM feature f, json_each(f.location, '$.parts') p
        WHERE f.seqid = ? AND f.type = ? AND f.coordinate_system = 'contig' AND
          ((p.value->>'start_status') != 'exact' OR (p.value->>'end_status') != 'exact')
    ''', [sequence_id, feature_type]).fetchone()[0]:
        raise ValueError("features of this type have uncertain endpoints, so their side and distance are unknown")
    rows = con.execute("""
        WITH placed AS (
            SELECT feature_id, start, "end", strand,
                   CASE WHEN "end" < ? THEN 'left' WHEN start > ? THEN 'right' ELSE 'contains' END AS side,
                   CASE WHEN "end" < ? THEN ? - "end" - 1 WHEN start > ? THEN start - ? - 1 ELSE 0 END AS gap
            FROM feature
            WHERE seqid = ? AND type = ? AND coordinate_system = 'contig'),
        ranked AS (
            SELECT *, row_number() OVER (PARTITION BY side ORDER BY gap, start, feature_id) AS nearness
            FROM placed)
        SELECT feature_id, start, "end", strand, side, gap
        FROM ranked WHERE side = 'contains' OR nearness <= ?
        ORDER BY start, "end", feature_id
    """, [position, position, position, position, position, position,
          sequence_id, feature_type, count]).fetchall()
    names = ("feature_id", "start", "end", "strand", "side", "intervening_bases")
    return [dict(zip(names, row)) for row in rows]


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
    near = commands.add_parser("neighbors")
    near.add_argument("sequence_id", help="Contig ID")
    near.add_argument("position", type=int, help="1-based contig position")
    near.add_argument("--count", type=int, default=2, help="features to list on each side (default 2)")
    near.add_argument("--type", dest="feature_type", default="gene", help="feature type (default gene)")
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
        elif args.command == "neighbors":
            rows = neighbors(con, args.sequence_id, args.position, args.count, args.feature_type)
        else:
            rows = by_attribute(con, args.key, args.value)
        print(json.dumps(rows, indent=2))
    except ValueError as error:
        parser.error(str(error))
    finally:
        con.close()


if __name__ == "__main__":
    main()
