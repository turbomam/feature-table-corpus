# Draft feature schema

[`ber_feature_model.yaml`](ber_feature_model.yaml) defines `Dataset`, `Contig`, and
`Feature`. It imports the standalone [attribute module](attributes.yaml), which defines
generic `key`/`value` pairs for metadata and evidence as well as GFF tags. See
[the attribute contract](../../docs/attributes.md). The schema remains a draft, not a
complete GFF3 interchange standard.

Optional `FeatureLocation` and `LocationPart` objects retain ordered, uncertain or
circular locations. See the [location contract and migration guide](../../docs/feature-locations.md).
With a structured location, scalar feature bounds are its indexing envelope;
parts are authoritative for occupancy.

[`source_document.yaml`](source_document.yaml) separately defines a physical source
document and its ordered records. It imports the same generic attribute module for
scoped comment metadata, without depending on Feature or NMDC DataObject. See the
[source-document parser contract](../../docs/source-documents.md) and
[reproducible example](../examples/source-documents/README.md).

[Versioned source profiles](../../docs/conversion-profiles.md) compose these two
contracts with preservation/mapping records. GFF3 and BED12 use the same Dataset
and generic Attribute classes; the latter also uses ordinary parent/child features
for ordered blocks. The surrounding conversion bundle is validated by its executable
profile contract, not by treating Dataset alone as a complete lossless serialization.

`strict-lint-config.yaml` is a lint configuration, not a data model. Its documented
exception is the four literal GFF3 strand symbols, which are preserved despite naming rules.

## Validation

| Command | Coverage |
|---|---|
| `just verify` | Corpus index integrity and checksums |
| `just validate-schema` | All three schema modules against the LinkML metamodel |
| `just lint-schema` | LinkML's default lint rules |
| `just lint-schema-recommended` | Recommended lint, allowing only the four documented strand-name warnings |
| `just lint-schema-strict` | Additional audit; intentionally reports the strand-name exception |
| `just validate-example` | Open generated JSON Schema for the default example |
| `just validate-example-closed` | Closed shape plus Dataset semantic checks |
| `just validate-source-example` | Closed SourceDocument shape plus exact-source/projection integrity |
| `just conversion-check` | Reproducible source-byte and mapped-field preservation report, including expected refusals |
| `just test` | Both real examples, invalid mutations, database preservation, and query controls |
| `just check` | Corpus, schema, recommended lint, examples, regression tests, and conversion report; also run by CI |
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
supports explicit parts and known-length circular references; the original GFF
conversion profile still refuses circular input. It does not validate biological CDS phase correctness, ontology terms,
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
Structured locations use a JSON column, and references retain optional topology.
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
for a positive result. [Query requirements](../../docs/query-requirements.md) also cover explicit
genomic and protein intervals and generic attribute lookup, informed by the BERIL census.
The Python overlap helper, like its CLI, requires integer endpoints and rejects booleans,
floats (including NaN and infinity), and strings before executing SQL.

The source-document reader preserves comments/directives and their justified scope.
It keeps feature columns lexical; converting them into harmonized Features remains
a separate step. The real Prodigal example includes sequence-specific `#` comments
between feature rows, in addition to document-level directives.

Generated databases and test scratch files live under gitignored `local/`. No database
binary is committed: the YAML examples and scripts are the reviewable, reproducible artifacts.

## Translation tables and score types

`Contig.translation_table` records the assigned NCBI genetic code a contig's coding features were
translated with, and `Feature.score_type` says what kind of number `score` is: `bit_score`,
`e_value`, `p_value` or `score`, each mapped to an EDAM data term
([issue 46](https://github.com/turbomam/feature-table-corpus/issues/46)). Unset `score_type` means
no source states the meaning, and a schema rule rejects a `score_type` on a feature with no
`score`. In the worked example only the HMMER rows set it. nmdc-lakehouse
documents NMDC's HMMER column 6 as a bit score
(https://github.com/microbiomedata/nmdc-lakehouse/blob/main/docs/pfam_annotation_gff.md). On all
five vendored HMMER rows that also have `full_sequence_bitscore`, column 6 is lower, so it reads
as the per-domain bit score. The lastal, Prodigal, GeneMark and INFERNAL scores are left unset.

Both slots are filled only by hand in the worked example. No converter derives them yet, and the
validator does not check `translation_table` against each CDS's `translation_table` attribute.
Filling `Contig.length_bp` from `##sequence-region` is not part of this: the
`gff3-contig` profile deliberately does not infer contig lengths from declared regions.
