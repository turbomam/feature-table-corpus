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
check: verify validate-schema lint-schema-recommended validate-example validate-example-closed validate-source-example test conversion-check validity-check bgc-check
    @echo "all checks passed"

[doc("Check every LinkML schema and transform specification against its metamodel.")]
[group("Validation")]
validate-schema:
    uv run --with linkml linkml-validate model/schema/ber_feature_model.yaml
    uv run --with linkml linkml-validate model/schema/attributes.yaml
    uv run --with linkml linkml-validate model/schema/source_document.yaml
    uv run --with linkml linkml-validate model/dialects/img-functional-gff.yaml
    uv run --with-requirements requirements-mapping.txt linkml-map validate-spec model/transforms/img-functional-gff.transform.yaml

[doc("Run LinkML's default lint rules on the feature model.")]
[group("Validation")]
lint-schema:
    uv run --with linkml linkml-lint model/schema/ber_feature_model.yaml

# Check exact diagnostic identity, not just the number of four strand warnings.
[doc("Run recommended lint with the declared naming exceptions.")]
[group("Validation")]
lint-schema-recommended:
    uv run --with linkml python3 scripts/lint_schema.py model/schema/ber_feature_model.yaml model/schema/attributes.yaml model/schema/source_document.yaml model/dialects/img-functional-gff.yaml

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
    uv run --with-requirements requirements-conversion.txt --with-requirements requirements-mapping.txt --with duckdb python3 -m unittest discover -s tests -v

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

[doc("Install checksum-pinned GenomeTools and GFF3toolkit in local/. AGAT is blocked; see the report.")]
[group("Corpus")]
validity-install: validity-install-genometools validity-install-gff3toolkit

[doc("Install checksum-pinned GenomeTools in local/.")]
[group("Corpus")]
validity-install-genometools:
    uv run --python '>=3.11.8' python scripts/install_genometools.py

[doc("Install checksum-pinned GFF3toolkit QC in local/ with Python 3.11.15.")]
[group("Corpus")]
validity-install-gff3toolkit:
    uv run --python 3.11.15 python scripts/install_gff3toolkit.py

[doc("Measure retained GFF3 files and regenerate the validity report.")]
[group("Corpus")]
validity-report:
    uv run --with pyyaml python3 scripts/validate_corpus.py

[doc("Check per-profile rule expectations, fixture labels, and retained validator results.")]
[group("Corpus")]
validity-check:
    uv run --with pyyaml python3 scripts/validate_corpus.py --check

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

[doc("Query explicit location parts; choose reported bounds for partials.")]
[group("Queries")]
location-overlap dataset reference start end mode="exact":
    uv run --with-requirements requirements-conversion.txt python3 scripts/query_locations.py "$1" overlap "$2" "$3" "$4" --mode "$5"

[doc("Measure shortest genomic gap between two exact feature locations.")]
[group("Queries")]
location-distance dataset left right:
    uv run --with-requirements requirements-conversion.txt python3 scripts/query_locations.py "$1" distance "$2" "$3"

[doc("Regenerate the real BGC excerpt and gene-order query report.")]
[group("Queries")]
bgc-report:
    uv run --with-requirements requirements-conversion.txt --with duckdb python3 scripts/bgc_example.py

[doc("Reproduce BGC source selection, round trips, and query results.")]
[group("Queries")]
bgc-check:
    uv run --with-requirements requirements-conversion.txt --with duckdb python3 scripts/bgc_example.py --check

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
[doc("Parse GFF3/GTF/BED12 into a new source-document JSON file.")]
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

# ---- JGI files that need a login -------------------------------------------

[doc("Print download URLs for the JGI files in model/examples/jgi-inputs.yaml.")]
[group("JGI")]
jgi-urls:
    uv run --with pyyaml python3 scripts/jgi_inputs.py urls

[doc("Check sizes and md5s of JGI files placed under local/jgi/RECORD/.")]
[group("JGI")]
jgi-verify dir="local/jgi":
    uv run --with pyyaml python3 scripts/jgi_inputs.py verify --dir "$1"

[doc("Refresh the JGI file lists from the anonymous search API (network).")]
[group("JGI")]
jgi-collect:
    uv run --with pyyaml python3 scripts/jgi_inputs.py collect

# ---- Versioned conversions -------------------------------------------------

[doc("Build NMDC protein/CDS context; supply source URI options.")]
[group("Conversions")]
protein-context annotation structural fasta reference output *options:
    context_annotation="$1"; context_structural="$2"; context_fasta="$3"; context_reference="$4"; context_output="$5"; shift 5; \
        uv run --with-requirements requirements-conversion.txt python3 scripts/protein_context.py "$context_annotation" "$context_structural" "$context_fasta" "$context_output" --reference-context "$context_reference" "$@"

[doc("Import through an explicit profile and reference context.")]
[group("Conversions")]
conversion-import input profile reference output *options:
    conversion_input="$1"; conversion_profile="$2"; conversion_reference="$3"; conversion_output="$4"; shift 4; \
        uv run --with-requirements requirements-conversion.txt python3 scripts/convert_features.py import "$conversion_input" --profile "$conversion_profile" --reference-context "$conversion_reference" --output "$conversion_output" "$@"

[doc("Validate an IMG *_functional_annotation.gff against its dialect schema.")]
[group("Conversions")]
dialect-validate-img-functional input:
    uv run --with-requirements requirements-conversion.txt python3 scripts/img_functional_gff.py validate "$1"

[doc("Map an IMG *_functional_annotation.gff to a Dataset JSON with linkml-map.")]
[group("Conversions")]
map-img-functional input output:
    uv run --with-requirements requirements-mapping.txt python3 scripts/img_functional_map.py forward "$1" "$2"

[doc("Map a Dataset JSON back to IMG functional annotation GFF text.")]
[group("Conversions")]
map-img-functional-back input output:
    uv run --with-requirements requirements-mapping.txt python3 scripts/img_functional_map.py reverse "$1" "$2"

[doc("Map an IMG functional annotation GFF forward and back; rows must match.")]
[group("Conversions")]
map-img-functional-roundtrip input:
    uv run --with-requirements requirements-mapping.txt python3 scripts/img_functional_map.py roundtrip "$1"

[doc("Export exact bytes or reconstruct fields; refuse edited bundles.")]
[group("Conversions")]
conversion-export input output mode="exact" *options:
    conversion_input="$1"; conversion_output="$2"; conversion_mode="$3"; shift 3; \
        uv run --with-requirements requirements-conversion.txt python3 scripts/convert_features.py export "$conversion_input" --output "$conversion_output" --mode "$conversion_mode" "$@"

[doc("Check a conversion bundle, optionally against --original PATH.")]
[group("Conversions")]
conversion-validate input *options:
    uv run --with-requirements requirements-conversion.txt python3 scripts/convert_features.py validate "$@"

[doc("Regenerate the tracked per-case conversion preservation report.")]
[group("Conversions")]
conversion-report:
    uv run --with-requirements requirements-conversion.txt python3 scripts/conversion_report.py

[doc("Require the retained conversion report to reproduce exactly.")]
[group("Conversions")]
conversion-check:
    uv run --with-requirements requirements-conversion.txt python3 scripts/conversion_report.py --check

# ---- Documentation ---------------------------------------------------------

[doc("Build the public documentation and check local links.")]
[group("Documentation")]
docs-build:
    uv run --python '>=3.11.8' python scripts/prepare_docs.py
    uv run --python '>=3.11.8' --with linkml==1.11.1 python scripts/schema_docs.py
    uv run --with-requirements requirements-docs.txt mkdocs build --strict
    uv run --python '>=3.11.8' python scripts/check_site.py

[doc("Check links and fragments in the already built documentation.")]
[group("Documentation")]
docs-check:
    uv run --python '>=3.11.8' python scripts/check_site.py

[doc("Stage and preview documentation on a chosen loopback port.")]
[group("Documentation")]
docs-serve port="8765":
    uv run --python '>=3.11.8' python scripts/prepare_docs.py
    uv run --python '>=3.11.8' --with linkml==1.11.1 python scripts/schema_docs.py
    uv run --with-requirements requirements-docs.txt mkdocs serve --dev-addr "127.0.0.1:$1"
