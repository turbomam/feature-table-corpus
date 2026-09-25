#!/usr/bin/env python3
"""Export a validated Dataset to Parquet through linkml-store, one file per collection.

Usage: python scripts/lakehouse_export.py SCHEMA_YAML DATASET OUTPUT_DIR

The Dataset is validated with scripts/validate_closed.py, stored in linkml-store's
DuckDB backend, and each collection slot of the schema's tree root (contigs,
features, and any collection a later schema adds) is written to
OUTPUT_DIR/<collection>.parquet. Columns follow the schema's induced slots, so a
collection with no rows still gets a file with the full column set.

Two things here are not linkml-store defaults, both driven by the schema:

- linkml-store 0.3.2 maps `float` to a 4-byte FLOAT and `integer` to a 4-byte
  INTEGER. A score of 239.1 comes back as 239.10000610351562, and a coordinate
  above 2,147,483,647 is refused. TYPE_FIXES widens both before loading, and
  refuses to run if linkml-store's own mapping is no longer the one it replaces.
- Every Parquet column is cast to the type column_type() derives from the schema.
  That turns linkml-store's JSON text for inlined objects into nested STRUCT
  types, so `attributes` is list<struct<key, value>>, and its VARCHAR booleans
  into BOOLEAN.

Before the output directory is published, three checks run and any failure
leaves no output: each file's column types must equal column_type(), row counts
must equal those of scripts/build_duckdb.py for the same Dataset (asked for in
https://github.com/turbomam/feature-table-corpus/issues/57; it ties the export to
that existing mapping, so a collection one has and the other lacks is reported),
and every value read back with pyarrow must equal the validated input. The
output directory must not exist, and the command line requires it under local/
so Parquet files are never staged beside tracked files. Directories the export
created are removed again if it fails.
"""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

import duckdb
import pyarrow.parquet as pq
import sqlalchemy as sqla
import yaml
from linkml_runtime import SchemaView
from linkml_store import Client
from linkml_store.api.stores.duckdb import mappings as store_mappings

from build_duckdb import build_database
from validate_closed import load_validated

ROOT = Path(__file__).resolve().parents[1]
TYPE_FIXES = {"integer": sqla.BigInteger, "float": sqla.Double}
# linkml-store 0.3.2's own entries that TYPE_FIXES replaces. If a later version
# changes them, the fix may no longer be needed or right, so stop and recheck.
REPLACED_TYPES = {"integer": sqla.Integer, "float": sqla.Float}
SCALAR_TYPES = {"integer": "BIGINT", "float": "DOUBLE", "double": "DOUBLE", "boolean": "BOOLEAN"}


def widen_store_types(fixes=TYPE_FIXES):
    """Replace linkml-store's lossy scalar mappings; return the previous ones."""
    previous = {k: store_mappings.TMAP.get(k) for k in fixes}
    unexpected = {k: v for k, v in previous.items() if v is not REPLACED_TYPES.get(k)}
    if unexpected:
        raise ValueError(f"linkml-store's type table changed ({unexpected}); "
                         "recheck TYPE_FIXES against the installed version")
    store_mappings.TMAP.update(fixes)
    return previous


def restore_store_types(previous):
    for key, value in previous.items():
        if value is None:
            store_mappings.TMAP.pop(key, None)
        else:
            store_mappings.TMAP[key] = value


def collections(view):
    """(slot name, range class) for each inlined list slot of the tree root."""
    roots = [c.name for c in view.all_classes().values() if c.tree_root]
    if len(roots) != 1:
        raise ValueError(f"expected one tree_root class, found {roots}")
    return [(s.name, s.range) for s in view.class_induced_slots(roots[0])
            if s.multivalued and s.range in view.all_classes() and view.is_inlined(s)]


def column_type(view, slot):
    """DuckDB type for a slot: nested STRUCT for inlined classes, text for references."""
    if slot.range in view.all_classes():
        if view.is_inlined(slot):
            fields = ", ".join(f'"{s.name}" {column_type(view, s)}'
                               for s in view.class_induced_slots(slot.range))
            base = f"STRUCT({fields})"
        else:
            base = "VARCHAR"
    elif slot.range in view.all_types():
        ancestors = view.type_ancestors(slot.range)
        base = next((SCALAR_TYPES[t] for t in ancestors if t in SCALAR_TYPES), "VARCHAR")
    else:
        base = "VARCHAR"  # enums and strings
    return base + "[]" if slot.multivalued else base


def _quote(path):
    return "'" + str(path).replace("'", "''") + "'"


def _select(view, conn, name, cls):
    columns = [(s.name, column_type(view, s)) for s in view.class_induced_slots(cls)]
    exists = conn.execute(sqla.text(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = :t"), {"t": name}).scalar()
    if exists:
        body = ", ".join(f'CAST("{c}" AS {t}) AS "{c}"' for c, t in columns)
        return f'SELECT {body} FROM "{name}"'
    body = ", ".join(f'CAST(NULL AS {t}) AS "{c}"' for c, t in columns)
    return f"SELECT {body} WHERE false"


def write_parquet(view, data, out_dir):
    """Store data in linkml-store's DuckDB backend and write one Parquet per collection."""
    client = Client()
    db = client.attach_database("duckdb", alias="lakehouse")
    db.set_schema_view(view)
    db.store(data)
    written = {}
    with db.engine.connect() as conn:
        for name, cls in collections(view):
            path = Path(out_dir) / f"{name}.parquet"
            conn.execute(sqla.text(f"COPY ({_select(view, conn, name, cls)}) TO {_quote(path)} (FORMAT PARQUET)"))
            written[name] = path
    db.close()
    return written


def type_mismatches(view, written):
    """Each file's column names and types must equal those column_type() derives."""
    problems = []
    con = duckdb.connect()
    try:
        for name, cls in collections(view):
            expected = con.execute("DESCRIBE SELECT " + ", ".join(
                f'CAST(NULL AS {column_type(view, s)}) AS "{s.name}"'
                for s in view.class_induced_slots(cls))).fetchall()
            actual = con.execute(f"DESCRIBE SELECT * FROM read_parquet({_quote(written[name])})").fetchall()
            want, got = [r[:2] for r in expected], [r[:2] for r in actual]
            if want != got:
                diff = [f"{w} != {g}" for w, g in zip(want, got) if w != g] or [f"{len(got)} columns, {len(want)} expected"]
                problems.append(f"{name}: column types differ: " + "; ".join(diff))
    finally:
        con.close()
    return problems


def present(value):
    """Drop absent values (None and empty lists) at every depth."""
    if isinstance(value, dict):
        cleaned = {k: present(v) for k, v in value.items()}
        return {k: v for k, v in cleaned.items() if v is not None and v != []}
    if isinstance(value, list):
        return [present(v) for v in value]
    return value


def value_mismatches(view, data, written):
    """Compare every value read back with pyarrow against the validated input."""
    problems = []
    for name, cls in collections(view):
        expected = [present(row) for row in data.get(name) or []]
        actual = [present(row) for row in pq.read_table(written[name]).to_pylist()]
        if len(expected) != len(actual):
            problems.append(f"{name}: {len(actual)} rows read back, {len(expected)} expected")
            continue
        for index, (want, got) in enumerate(zip(expected, actual)):
            if want != got:
                keys = sorted(k for k in set(want) | set(got) if want.get(k) != got.get(k))
                problems.append(f"{name}[{index}]: differs in {keys}")
    return problems


def _table_name(cls):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", cls).lower()


def count_mismatches(view, schema_path, data_path, written, work):
    """Row counts per collection must equal build_duckdb.py's tables for the same Dataset."""
    db_path = Path(work) / "reference.duckdb"
    build_database(schema_path, data_path, db_path)
    with duckdb.connect(str(db_path), read_only=True) as con:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        reference = {t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    problems = []
    matched = set()
    for name, cls in collections(view):
        table = _table_name(cls)
        rows = pq.read_metadata(written[name]).num_rows
        if table not in reference:
            problems.append(f"{name}: build_duckdb.py has no {table} table")
            continue
        matched.add(table)
        if rows != reference[table]:
            problems.append(f"{name}: {rows} Parquet rows, build_duckdb.py {table} has {reference[table]}")
    for table in sorted(tables - matched):
        problems.append(f"build_duckdb.py table {table} has no exported collection")
    return problems


def export(schema_path, data_path, out_dir):
    """Validate, export, check, then publish out_dir. Returns a summary dict."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise ValueError(f"{out_dir} already exists; choose a new output directory")
    timings = {}
    started = time.perf_counter()
    data = load_validated(schema_path, data_path)
    timings["validate_seconds"] = time.perf_counter() - started
    view = SchemaView(str(schema_path))
    created = [p for p in [out_dir.parent, *out_dir.parent.parents] if not p.exists()]
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    previous = {}
    try:
        previous = widen_store_types()
        with tempfile.TemporaryDirectory(prefix=f".{out_dir.name}.", dir=out_dir.parent) as work:
            staged = Path(work) / "export"
            staged.mkdir()
            started = time.perf_counter()
            written = write_parquet(view, data, staged)
            timings["store_and_write_seconds"] = time.perf_counter() - started
            started = time.perf_counter()
            problems = type_mismatches(view, written)
            problems += count_mismatches(view, schema_path, data_path, written, work)
            problems += value_mismatches(view, data, written)
            timings["check_seconds"] = time.perf_counter() - started
            if problems:
                raise ValueError("Parquet export failed its checks: " + "; ".join(problems[:20]))
            summary = {name: {"rows": pq.read_metadata(path).num_rows, "bytes": path.stat().st_size}
                       for name, path in written.items()}
            os.rename(staged, out_dir)
    except BaseException:
        for directory in created:  # innermost first; only directories this call made
            try:
                directory.rmdir()
            except OSError:
                break
        raise
    finally:
        restore_store_types(previous)
    return {"output": str(out_dir), "collections": summary,
            **{k: round(v, 2) for k, v in timings.items()}}


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    schema_path, data_path, out_dir = sys.argv[1:]
    local = (ROOT / "local").resolve()
    target = Path(out_dir).resolve()
    if local not in target.parents:
        print(f"{out_dir}: output must be under {local}", file=sys.stderr)
        return 2
    try:
        summary = export(schema_path, data_path, out_dir)
    except (ValueError, yaml.YAMLError, duckdb.Error, sqla.exc.SQLAlchemyError, OSError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
