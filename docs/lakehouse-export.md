# Parquet export with linkml-store

`just lakehouse-export DATASET DIR` validates a `Dataset` with
[`validate_closed.py`](../scripts/validate_closed.py), loads it into
[linkml-store](https://github.com/linkml/linkml-store)'s DuckDB backend, and writes one
Parquet file per collection to `DIR`. It was written for
https://github.com/turbomam/feature-table-corpus/issues/57. The code is
[`scripts/lakehouse_export.py`](../scripts/lakehouse_export.py) and the pinned toolchain is
[`requirements-lakehouse.txt`](../requirements-lakehouse.txt) (linkml 1.11.1, linkml-store
0.3.2, DuckDB 1.5.5, pyarrow 25.0.1).

```sh
just map-img-functional local/jgi/IMG_AP-1268149/Ga0423362_functional_annotation.gff local/ga0423362.json
just lakehouse-export local/ga0423362.json local/lakehouse/ga0423362
```

`DIR` must not exist yet and must be under `local/`, so Parquet files never sit beside
tracked files. Nothing appears at `DIR` unless the three checks below pass, and directories the export
created are removed again when it fails.

## Layout

The collections are the inlined list slots of the schema's tree root, read from
[`ber_feature_model.yaml`](../model/schema/ber_feature_model.yaml), so today the export
writes `contigs.parquet` and `features.parquet`. A collection the schema adds later, such
as `contig_collections` from
https://github.com/turbomam/feature-table-corpus/pull/62, gets its own file
without a change to the export. The row-count check below also needs `build_duckdb.py` to
have a table for it, which that pull request adds. Each file has one column per slot of its class, in schema order. A
collection with no rows still gets a file with every column, so the files for different
Datasets have the same columns.

## Types

linkml-store creates each table from the schema, but two of its default mappings lose
information, so the export widens them before loading. It then casts every column to the
type the schema gives when writing, which turns inlined objects into nested Parquet types
and linkml-store's text booleans into `bool`. If linkml-store's own mapping for `float` or
`integer` is no longer the one replaced here, the export stops rather than patch a table it
has not been tested against.

| Slot range | linkml-store 0.3.2 default | Written to Parquet |
|---|---|---|
| `float` (`score`, `lineage_confidence`) | 4-byte `FLOAT` | `double` |
| `integer` (`start`, `end`, `length_bp`, `phase`) | 4-byte `INTEGER` | `int64` |
| `boolean` (`is_selected`) | `VARCHAR` holding `"true"`, not changed | `bool`, by the cast |
| inlined class (`attributes`, `location`) | `JSON` or `JSON[]` text | `struct` or `list<struct>` |
| reference to a class (`seqid`, `parent`), string, enum | `VARCHAR` | `string` |

With the defaults, a score of 239.1 in the committed
[one-biosample example](../model/examples/one-biosample-sequencing/harmonized.yaml) reads
back as 239.10000610351562. Measured on 2026-09-25, the default types changed the score of
4,222 of 4,439 features in `Ga0423362` and 1,916 of 2,005 in `Ga0416744`. A test keeps this
as a negative control. The 4-byte integer holds positions up to 2,147,483,647, which no
current input exceeds, but linkml-store refuses a larger one with "out of range"; a test
exports a feature at 2^33 and checks that the default mapping refuses it.

linkml-store's own Parquet routes were tried first, on 2026-09-25:

- `Database.export_database(path, Format.PARQUET)` raises "Unsupported output format:
  Format.PARQUET" and leaves an empty file.
- The filesystem backend with `file_format: parquet` writes through pandas, so types come
  from the data rather than the schema. `phase` became `double` because some rows have no
  phase, and slots that no row uses (`topology`, `location` in the example) got no column.

So the export keeps linkml-store's DuckDB tables and writes them with DuckDB's
`COPY ... (FORMAT PARQUET)` on the same connection.

## Nested attributes

`attributes` comes out as `list<struct<key: string, value: string>>`, one entry per value
in file order. It is not flattened into a separate table. One `UNNEST` gives a key/value
row per attribute:

```sql
SELECT feature_id,
       generate_subscripts(attributes, 1) AS ordinal,
       unnest(attributes).key AS key,
       unnest(attributes).value AS value
FROM 'local/lakehouse/ga0423362/features.parquet';
```

On 2026-09-25 this returned 53,609 rows for `Ga0423362` and 24,507 for `Ga0416744`, the
attribute counts the [linkml-map round trip](conversion-profiles.md#mapping-a-dialect-with-linkml-map)
reports for those files. `location` is a struct with a `parts` list of structs.

That works for engines that read nested Parquet. A catalog limited to scalar columns, as
the BRIDGE catalog prototype is described in
https://github.com/turbomam/feature-table-corpus/issues/45, still needs the derived
child tables proposed there; this export does not produce them.

## Checks

All three run before `DIR` is published, and a failure leaves no output:

- **Column types.** Each file's column names and types, as DuckDB reads them, must equal
  those the schema gives. The value check can't see this: an `is_selected` rewritten as
  `int64` compares equal, because `True == 1` in Python.
- **Row counts.** Each collection's row count must equal the matching table that
  [`build_duckdb.py`](../scripts/build_duckdb.py) builds from the same Dataset (the table
  name is the range class in snake case, such as `feature`). A table with no matching
  collection is also an error. https://github.com/turbomam/feature-table-corpus/issues/57
  asked for this check. The value check already compares row counts against the input, and
  both paths read the file with the same `load_validated`, so this adds no second reading.
  It is kept because it is the only check that ties the export to the existing DuckDB
  mapping: a collection one has and the other lacks is reported. It is also most of the run time: 5.37 s of the checks on `Ga0423362`, measured
  2026-09-25, against 0.01 s for types and 0.09 s for values.
- **Values.** Each file is read back with pyarrow, and every row must equal the validated
  input, with null and empty lists treated as absent.

[`tests/test_lakehouse_export.py`](../tests/test_lakehouse_export.py) reads the files back
for the committed example, the constructed IMG fixture and the vendored phiX174 RefSeq
record (joined and origin-crossing locations). Its negative controls change one attribute
value, drop one row (with the value check off, so only the row count can catch it),
rewrite `is_selected` as `int64`, export with linkml-store's default types, and change
linkml-store's type table before export; each must be reported.

## Measurements

One run each on 2026-09-25, after the column-type check was added. "Checks" is mostly
`build_duckdb.py` validating the Dataset again and inserting row by row.

| Dataset | Features | Dataset JSON | `features.parquet` | Validate | Load and write | Checks | Wall clock |
|---|---|---|---|---|---|---|---|
| One-biosample example | 15 | YAML | 9,737 B | 0.06 s | 0.03 s | 0.05 s | not timed |
| Constructed IMG fixture | 10 | 7,908 B | 5,895 B | 0.06 s | 0.03 s | 0.05 s | 0.79 s |
| `Ga0416744` (IMG_AP-1257706) | 2,005 | 2,426,519 B | 274,639 B | 2.03 s | 0.15 s | 2.45 s | 5.30 s |
| `Ga0423362` (IMG_AP-1268149) | 4,439 | 5,371,707 B | 595,593 B | 4.46 s | 0.30 s | 5.35 s | 10.78 s |

For comparison, `just build-duckdb` on the `Ga0423362` Dataset took 9.03 s and wrote a
2,109,440-byte database. The contig files were under 1 KB for the IMG Datasets and 2,161 B
for the example.
