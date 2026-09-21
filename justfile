# feature-table-corpus. Run `just` with no arguments to list all recipes.

default:
    @just --list

# Corpus index integrity and vendored-file checksums (the same check CI runs).
verify:
    uv run --with pyyaml python scripts/verify.py

# --- schema/ber_feature_model.yaml -----------------------------------------

# Validate the schema file itself against the LinkML metamodel.
validate-schema:
    uv run --with linkml linkml-validate schema/ber_feature_model.yaml
    uv run --with linkml linkml-validate schema/attributes.yaml

# Lint with LinkML's own default rules (a handful of "recommended"-level checks).
lint-schema:
    uv run --with linkml linkml-lint schema/ber_feature_model.yaml

# Lint with LinkML's bundled recommended.yaml: undeclared slots/ranges, invalid
# slot usage, one-identifier-per-class, and more, all promoted to error.
# Allow only the exact standard_naming diagnostics for StrandEnum's four GFF3
# symbols, checking schema name, rule, severity, and message rather than a count.
lint-schema-recommended:
    uv run --with linkml python3 scripts/lint_schema.py schema/ber_feature_model.yaml schema/attributes.yaml

# Every available lint rule at error level, including several recommended.yaml
# leaves disabled. NOT part of `just check`: schema/strict-lint-config.yaml
# deliberately sets StrandEnum's exception to error, unconditionally, so this
# recipe always reports exactly that finding by design. Run it by hand as an
# occasional deep audit; a clean run means nothing NEW has appeared beyond the
# one documented exception.
lint-schema-strict:
    uv run --with linkml linkml-lint --config schema/strict-lint-config.yaml schema/ber_feature_model.yaml

# Validate one example data file as a single Dataset instance (the whole
# document, not just its Contig/Feature fragments one at a time).
validate-example example="examples/one-biosample-sequencing/harmonized.yaml":
    uv run --with linkml linkml-validate --schema schema/ber_feature_model.yaml -C Dataset {{example}}

# Closed shape validation plus cross-field, reference, and coordinate-space checks.
validate-example-closed example="examples/one-biosample-sequencing/harmonized.yaml":
    uv run --with linkml --with jsonschema python3 scripts/validate_closed.py schema/ber_feature_model.yaml {{example}} Dataset

# Print a Mermaid ER diagram for the schema. Paste the erDiagram block into
# docs/schema-diagram.md by hand; this recipe does not write the file, since
# that file also carries prose that a straight overwrite would destroy.
diagram:
    uv run --with linkml python3 scripts/schema_diagram.py

# --- relational / lakehouse shape --------------------------------------

# Audit the schema against a flat, scalar-only publishing profile (the same
# tool used on Chris Mungall's gff-schema in docs/model-comparison.md).
flat-profile-audit:
    uv run --with linkml-runtime python3 scripts/flat_profile_audit.py schema/ber_feature_model.yaml

# Build a real DuckDB database from one example, resolving the flat-profile
# audit's findings at the physical layer: parent and attributes become native
# LIST columns, not junction tables. Output is gitignored (local/build/); this
# recipe regenerates it, nothing here is meant to be committed as a binary.
build-duckdb example="examples/one-biosample-sequencing/harmonized.yaml" out="local/build/ber_feature_model.duckdb":
    mkdir -p $(dirname {{out}})
    uv run --with linkml --with jsonschema --with duckdb python3 scripts/build_duckdb.py schema/ber_feature_model.yaml {{example}} {{out}}

# CDS genes with multiple distinct Pfams; see examples/multiple-pfams/ for a positive example.
query-duckdb db="local/build/ber_feature_model.duckdb":
    uv run --with duckdb python3 scripts/query_duckdb.py {{db}} pfams

# Real examples plus negative controls for validation, safe loading, and queries.
test:
    uv run --with linkml --with jsonschema --with duckdb python3 -m unittest discover -s tests -v

# Everything expected to pass cleanly: corpus integrity, metamodel validation,
# the recommended lint profile, and example-data validation (open and closed
# schema). This is the target to run before pushing a schema change. Run
# `lint-schema-strict` separately for an occasional deeper audit.
check: verify validate-schema lint-schema-recommended validate-example validate-example-closed test
    @echo "all checks passed"
