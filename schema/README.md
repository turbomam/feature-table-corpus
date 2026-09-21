# Draft feature schema

[`ber_feature_model.yaml`](ber_feature_model.yaml) defines `Dataset`, `Contig`, and
`Feature`. It imports the standalone [attribute module](attributes.yaml), which defines
generic `key`/`value` pairs for metadata and evidence as well as GFF tags. See
[the attribute contract](../docs/attributes.md). The schema remains a draft, not a
complete GFF3 interchange standard.

`strict-lint-config.yaml` is a lint configuration, not a data model. Its documented
exception is the four literal GFF3 strand symbols, which are preserved despite naming rules.

## Validation

| Command | Coverage |
|---|---|
| `just verify` | Corpus index integrity and checksums |
| `just validate-schema` | Both schema modules against the LinkML metamodel |
| `just lint-schema` | LinkML's default lint rules |
| `just lint-schema-recommended` | Recommended lint, allowing only the four documented strand-name warnings |
| `just lint-schema-strict` | Additional audit; intentionally reports the strand-name exception |
| `just validate-example` | Open generated JSON Schema for the default example |
| `just validate-example-closed` | Closed shape plus Dataset semantic checks |
| `just test` | Both real examples, invalid mutations, database preservation, and query controls |
| `just check` | Corpus, schema, recommended lint, example validation, and tests; also run by CI |
| `just diagram` | Regenerate the Mermaid diagram |
| `just flat-profile-audit` | Audit scalar-table compatibility through SchemaView |

The closed validator requires an object at the document root, rejects unknown root
fields, and checks JSON Schema formats, including `source_files` URIs. An empty object
is a valid empty Dataset because both collections are optional;
absent or null collections are treated as empty. These cases have regression coverage.

The harmonized Dataset profile requires a contig reference, coordinate system, and positive
1-based inclusive endpoints on every Feature; phase, when supplied, is 0, 1, or 2.
`scripts/validate_closed.py` additionally enforces start ≤ end, unique IDs within each entity
collection, resolved references, no parent cycles, and compatible parent coordinate spaces.
Contig intervals cannot exceed a known contig length. Protein intervals need a contig-relative
CDS parent and cannot exceed a supplied translation. Missing translations are allowed; their
upper bounds cannot be checked. Multiple parents must each be compatible with the child.

These cross-record checks run for `Dataset`, not when validating an isolated Feature.
Plain `linkml-validate` and exported JSON Schema alone do not enforce them. The profile
currently assumes linear sequences; circular wraparound GFF3 coordinates need an explicit
future representation. It does not validate biological CDS phase correctness, ontology terms,
or all GFF3 grammar.

CI also downloads the pinned, unvendored prior-art GFF schema and asserts its published
19-admissible/13-rejected audit totals. Locally, set `PINNED_GFF_SCHEMA` to that downloaded
schema's path to include this test; otherwise it is explicitly skipped. The current draft
model's separate 20-admissible/8-rejected totals are tested without network access.

Both Contig and Feature expose `generated_by` and `source_files`. These remain optional
for sources lacking workflow metadata, but every supplied example populates them.
`generated_by` replaces the earlier Feature-only `predicted_by` field. The
[source manifest](../examples/source-artifacts.yaml) records IDs and checksums for cited
artifacts. Record-level source lists may include sidecars from a different workflow than
the record's producer; they are not field-level provenance.

## DuckDB mapping and queries

BRIDGE's scalar-only prototype profile is not a requirement of this model. The loader uses
native LIST columns for parents, lineages, and source files, and LIST of STRUCT for attributes.
`Feature.seqid` becomes a foreign key to Contig. The physical mapping is explicit Python/SQL;
it is not a general LinkML database generator.

`just build-duckdb` validates its supplied schema and Dataset before opening the output.
It replaces the two model tables in one transaction, so validation or insertion failure
preserves an existing database. DuckDB BIGINT columns impose a 64-bit storage limit beyond
LinkML's integer type. New databases are staged beside their destination and published
after success; insertion failures leave no output or staging directory. Publication
refuses to overwrite a destination created concurrently, including during validation.
The tests exercise that race, rollback, and fresh-path cleanup for an out-of-range value.

`just query-duckdb` selects CDS parents with multiple distinct Pfams. The default mixed-evidence
example correctly produces no matches. Build [the real three-Pfam example](../examples/multiple-pfams/README.md)
for a positive result. [Query requirements](../docs/query-requirements.md) also cover explicit
genomic and protein intervals and generic attribute lookup, informed by the BERIL census.
The Python overlap helper, like its CLI, requires integer endpoints and rejects booleans,
floats (including NaN and infinity), and strings before executing SQL.

Source-document metadata and parsing of comments/directives are tracked separately in
[issue #13](https://github.com/turbomam/feature-table-corpus/issues/13). The real Prodigal
example includes sequence-specific `#` comments between feature rows; a future parser
must preserve their scope as well as file-level directives.

Generated databases and test scratch files live under gitignored `local/`. No database
binary is committed: the YAML examples and scripts are the reviewable, reproducible artifacts.
