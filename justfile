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

# Everything expected to pass cleanly: corpus integrity, metamodel validation,
# the recommended lint profile, and example-data validation (open and closed
# schema). This is the target to run before pushing a schema change. Run
# `lint-schema-strict` separately for an occasional deeper audit.
check: verify validate-schema lint-schema-recommended validate-example validate-example-closed
    @echo "all checks passed"
