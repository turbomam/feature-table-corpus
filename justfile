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

# Lint with LinkML's own default rules (a handful of "recommended"-level checks).
lint-schema:
    uv run --with linkml linkml-lint schema/ber_feature_model.yaml

# Lint with LinkML's bundled recommended.yaml: undeclared slots/ranges, invalid
# slot usage, one-identifier-per-class, and more, all promoted to error.
# --max-warnings 4 tolerates exactly the one documented, permanent exception
# (StrandEnum's 4 literal GFF3 symbols); any other warning still fails.
lint-schema-recommended:
    #!/usr/bin/env bash
    set -euo pipefail
    cfg=$(uv run --with linkml python3 -c "import linkml.linter, os; print(os.path.dirname(linkml.linter.__file__))")/config/recommended.yaml
    uv run --with linkml linkml-lint --config "$cfg" --max-warnings 4 schema/ber_feature_model.yaml

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

# Same, but against a CLOSED schema (additionalProperties: false), which
# catches an undeclared or typo'd field the open validation above lets
# through silently. scripts/validate_closed.py is verified with a negative
# control (an injected bogus field), not just assumed to work.
validate-example-closed example="examples/one-biosample-sequencing/harmonized.yaml":
    uv run --with linkml --with jsonschema python3 scripts/validate_closed.py schema/ber_feature_model.yaml {{example}} Dataset

# Print a Mermaid ER diagram for the schema. Paste the erDiagram block into
# docs/schema-diagram.md by hand; this recipe does not write the file, since
# that file also carries prose that a straight overwrite would destroy.
diagram:
    uv run --with linkml python3 -m linkml.generators.erdiagramgen schema/ber_feature_model.yaml -f mermaid --no-metadata

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
    uv run --with duckdb --with pyyaml python3 scripts/build_duckdb.py schema/ber_feature_model.yaml {{example}} {{out}}

# Run the kickoff doc's own named use case against the DuckDB build: genes
# with more than one functional-evidence hit (the "multiple Pfams in one
# gene" pattern), plus whatever else has multiple children via `parent`.
query-duckdb db="local/build/ber_feature_model.duckdb":
    duckdb {{db}} -c "SELECT p.feature_id AS gene_id, p.product, count(*) AS n_evidence_hits, list(DISTINCT c.type) AS evidence_types FROM feature c JOIN feature p ON list_contains(c.parent, p.feature_id) GROUP BY p.feature_id, p.product HAVING count(*) > 1 ORDER BY n_evidence_hits DESC;"

# Everything expected to pass cleanly: corpus integrity, metamodel validation,
# the recommended lint profile, and example-data validation (open and closed
# schema). This is the target to run before pushing a schema change. Run
# `lint-schema-strict` separately for an occasional deeper audit.
check: verify validate-schema lint-schema-recommended validate-example validate-example-closed
    @echo "all checks passed"
