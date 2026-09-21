# feature-table-corpus: run `just` to list tasks. Requires just >= 1.27.
# Pass recipe arguments as shell positional parameters, never as shell source.
set positional-arguments

# Named defaults keep long paths out of `just --list`; inspect with `just --evaluate`.
feature_schema := "model/schema/ber_feature_model.yaml"
feature_example := "model/examples/one-biosample-sequencing/harmonized.yaml"
source_example := "model/examples/source-documents/prodigal.json"
source_original := "corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff"
duckdb_path := "local/build/ber_feature_model.duckdb"
nmdc_work := "local/nmdc-profile"
nmdc_report := "analyses/nmdc-data-objects"

[private]
default:
    @just --list

# ---- Validation -------------------------------------------------------------

[doc("Run corpus, schema, example, and regression checks.")]
[group("Validation")]
check: verify validate-schema lint-schema-recommended validate-example validate-example-closed validate-source-example test
    @echo "all checks passed"

[doc("Check all three LinkML schemas against the metamodel.")]
[group("Validation")]
validate-schema:
    uv run --with linkml linkml-validate model/schema/ber_feature_model.yaml
    uv run --with linkml linkml-validate model/schema/attributes.yaml
    uv run --with linkml linkml-validate model/schema/source_document.yaml

[doc("Run LinkML's default lint rules on the feature model.")]
[group("Validation")]
lint-schema:
    uv run --with linkml linkml-lint model/schema/ber_feature_model.yaml

# Check exact diagnostic identity, not just the number of four strand warnings.
[doc("Run recommended lint with the four declared strand exceptions.")]
[group("Validation")]
lint-schema-recommended:
    uv run --with linkml python3 scripts/lint_schema.py model/schema/ber_feature_model.yaml model/schema/attributes.yaml model/schema/source_document.yaml

# Intentionally outside check: this reports the standard-naming exception by design.
[doc("Run the strict audit; its strand-name finding is expected.")]
[group("Validation")]
lint-schema-strict:
    uv run --with linkml linkml-lint --config model/schema/strict-lint-config.yaml model/schema/ber_feature_model.yaml

[doc("Validate a Dataset using the open generated schema.")]
[group("Validation")]
validate-example example=feature_example:
    uv run --with linkml linkml-validate --schema model/schema/ber_feature_model.yaml -C Dataset "$1"

[doc("Check closed Dataset shape, coordinates, and references.")]
[group("Validation")]
validate-example-closed example=feature_example:
    uv run --with linkml --with jsonschema python3 scripts/validate_closed.py model/schema/ber_feature_model.yaml "$1" Dataset

[doc("Run regression tests on real examples and negative controls.")]
[group("Validation")]
test:
    uv run --with linkml --with jsonschema --with duckdb python3 -m unittest discover -s tests -v

# ---- Corpus maintenance -----------------------------------------------------

[doc("Check the corpus inventory, counts, and stored checksums.")]
[group("Corpus")]
verify:
    uv run --with pyyaml python3 scripts/verify.py

# Network checks report dead URLs without treating them as corpus defects.
[doc("Also check upstream URLs (network; dead links are reported).")]
[group("Corpus")]
verify-links:
    uv run --with pyyaml python3 scripts/verify.py --links

# Explicitly regenerates tracked files. CI separately checks exact reproduction.
[doc("Regenerate the nine tracked derived corpus fixtures.")]
[group("Corpus")]
fixtures-generate:
    python3 scripts/make_malformed.py

# Empty audit_source preserves the script's pinned upstream default.
# Pass a local schema for an offline audit, or a URL for another comparison.
[doc("Run checks and print a PR report; default audit uses upstream.")]
[group("Corpus")]
pr-validation base="origin/main" audit_source="":
    if [ -n "$2" ]; then \
        uv run --with pyyaml python3 scripts/pr_validation_block.py "$1" --audit-source "$2"; \
    else \
        uv run --with pyyaml python3 scripts/pr_validation_block.py "$1"; \
    fi

# ---- Model analysis and databases -------------------------------------------

# This recipe prints Mermaid; the checked-in diagram also contains maintained prose.
[doc("Print the feature model's Mermaid ER diagram.")]
[group("Model")]
diagram:
    uv run --with linkml python3 scripts/schema_diagram.py

[doc("Audit scalar-table compatibility of a schema path or URL.")]
[group("Model")]
flat-profile-audit schema=feature_schema:
    uv run --with linkml-runtime python3 scripts/flat_profile_audit.py "$1"

[doc("Validate a Dataset and build or update its DuckDB mapping.")]
[group("Queries")]
build-duckdb example=feature_example out=duckdb_path:
    mkdir -p "$(dirname "$2")"
    uv run --with linkml --with jsonschema --with duckdb python3 scripts/build_duckdb.py model/schema/ber_feature_model.yaml "$1" "$2"

# Keep the original recipe name/default; optional accessions filter the Pfam query.
[doc("Find CDSs with multiple Pfams, optionally selecting accessions.")]
[group("Queries")]
query-duckdb db=duckdb_path *accessions:
    query_database="$1"; shift; \
        uv run --with duckdb python3 scripts/query_duckdb.py "$query_database" pfams "$@"

[doc("Find features with an exact attribute key/value match.")]
[group("Queries")]
query-attribute key value db=duckdb_path:
    uv run --with duckdb python3 scripts/query_duckdb.py "$3" attribute "$1" "$2"

[doc("Query a 1-based inclusive contig or protein interval.")]
[group("Queries")]
query-overlap space seqid start end db=duckdb_path:
    uv run --with duckdb python3 scripts/query_duckdb.py "$5" overlap "$1" "$2" "$3" "$4"

# ---- Source documents -------------------------------------------------------

# Additional options go to the existing parser: --profile, --source-uri, --strict.
[doc("Parse a GFF3/GTF file into a new source-document JSON file.")]
[group("Source documents")]
source-parse input format output *options:
    source_input="$1"; source_format="$2"; source_output="$3"; shift 3; \
        python3 scripts/source_document.py parse "$source_input" --format "$source_format" --output "$source_output" "$@"

[doc("Check consistency; add --original PATH for source comparison.")]
[group("Source documents")]
source-validate input *options:
    python3 scripts/source_document.py validate "$@"

[doc("Replay to a new file; optionally compare with --original PATH.")]
[group("Source documents")]
source-replay input output *options:
    source_input="$1"; source_output="$2"; shift 2; \
        python3 scripts/source_document.py replay "$source_input" --output "$source_output" "$@"

# For another example, supply its matching original as the second argument.
[doc("Check SourceDocument shape and agreement with its original.")]
[group("Source documents")]
validate-source-example example=source_example original=source_original:
    uv run --with linkml --with jsonschema python3 scripts/validate_closed.py model/schema/source_document.yaml "$1" SourceDocument
    python3 scripts/source_document.py validate "$1" --original "$2"

# ---- NMDC analysis (explicit tasks; never dependencies of check) -------------

[doc("Collect live DataObject metadata and regenerate its reports.")]
[group("NMDC")]
nmdc-collect work=nmdc_work output=nmdc_report:
    uv run --with linkml-runtime python3 scripts/profile_nmdc_data_objects.py collect --work-dir "$1" --output "$2"

# Requires retained, checksum-verified inputs and dependencies already in uv's cache.
[doc("Render reports offline from retained inputs and cached tools.")]
[group("NMDC")]
nmdc-render work=nmdc_work output=nmdc_report:
    uv run --offline --with linkml-runtime python3 scripts/profile_nmdc_data_objects.py render --work-dir "$1" --output "$2"

[doc("Sample live GFF candidates into local/ for inspection.")]
[group("NMDC")]
nmdc-sample:
    python3 scripts/harvest_nmdc.py
