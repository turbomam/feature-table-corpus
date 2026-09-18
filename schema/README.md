# schema/

Two YAML files here, easy to confuse with each other:

- **`ber_feature_model.yaml`** is the actual draft LinkML model: `Dataset`, `Contig`, `Feature`,
  `Attribute`. This is the thing being designed. Every non-obvious field has a `notes` entry
  citing the measurement it's based on; `description` is kept to one clause per slot.
- **`strict-lint-config.yaml`** is not a schema, it's a `linkml-lint` configuration: every
  available lint rule turned to `error`, including several `linkml-lint`'s own bundled
  `recommended.yaml` leaves disabled. It exists to run one occasional, exhaustive audit; see
  `just lint-schema-strict` below. It documents one permanent, deliberate exception: `StrandEnum`'s
  permissible values are the literal GFF3 symbols (`+`, `-`, `.`, `?`), which no naming convention
  accepts, kept because a word form would round-trip less faithfully to a real GFF3 file.

## Checking this schema

Everything below is a `just` recipe (run from the repo root); see the `justfile` there for the
exact commands.

| Command | What it checks |
|---|---|
| `just validate-schema` | The schema file itself against the LinkML metamodel |
| `just lint-schema` | LinkML's own default lint rules |
| `just lint-schema-recommended` | LinkML's bundled `recommended.yaml`: undeclared slots/ranges, invalid slot usage, and more, promoted to error |
| `just lint-schema-strict` | Every available rule at error, via `strict-lint-config.yaml`. Not part of `just check`; run by hand |
| `just validate-example` | One example data file, as a whole `Dataset` instance, against the open schema |
| `just validate-example-closed` | Same, against a CLOSED schema (`additionalProperties: false`), which catches an undeclared or typo'd field the open check lets through |
| `just flat-profile-audit` | Whether this schema survives a flat, scalar-only publishing profile (see below) |
| `just diagram` | Prints a Mermaid ER diagram; see `docs/schema-diagram.md` for the current one, rendered |
| `just build-duckdb` / `just query-duckdb` | Loads an example into a real DuckDB database and runs a demo query; see below |
| `just check` | The subset expected to always pass cleanly: `verify`, `validate-schema`, `lint-schema-recommended`, `validate-example`, `validate-example-closed` |

## Does this schema require a flat, relational table?

No, and it doesn't need to. Georg Rath (`gbrath-lbl`) confirmed 2026-09-17 that the scalar-only,
flat-table profile in `ber-data/bridge-catalog-mvp`'s `docs/architecture.md` is an early-prototype
decision, not a BRIDGE-wide requirement, so `parent` and `attributes` are genuinely multivalued
slots here rather than decomposed into join tables.

`just flat-profile-audit` runs the same tool used on Chris Mungall's `gff-schema` in
`docs/model-comparison.md`, against this schema instead. Run 2026-09-18: of 25 class/slot pairs,
19 are admissible under a scalar-only profile as written; the 6 that aren't split into 5 mechanical
cases (multivalued class references needing a child or junction table, and one identified class
reference needing a scalar id plus a foreign key) and exactly 1 real decision
(`Contig.taxonomic_lineage`, a multivalued scalar: array column or junction table).

`just build-duckdb` answers that one decision concretely rather than just describing it: it loads
an example into a real DuckDB database using DuckDB's native `LIST` and `STRUCT` types for
`taxonomic_lineage`, `parent`, and `attributes`, no junction tables. `just query-duckdb` then runs
the kickoff doc's own named use case, genes with more than one functional-evidence hit, directly
against those nested columns. The built `.duckdb` file is not committed (see "Why no committed
database file" below); the script that builds it, `scripts/build_duckdb.py`, is.

## Why no committed database file

A build of the one example in `examples/one-biosample-sequencing/` is about 2 MB, almost entirely
DuckDB's own fixed file-format overhead, for 3 contigs and 15 features. This repository's own
README states its content is plain text and reviewable in a diff; a 2 MB binary for 18 rows of
data that regenerates in under a second from files already here doesn't meet that bar. Build it
locally with `just build-duckdb` instead.
