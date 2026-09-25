# Repository map

The repository groups artifacts by their role. Paths below describe this branch's
actual layout; the model remains a draft, regardless of its directory name.

```text
corpus/                         Evidence collected from producers and prior art
  index.yaml                    Inventory, provenance, licenses, and checksums
  PROVENANCE.md                 Dated acquisition and correction history
  sources/{nmdc,ncbi-refseq,biopython}/  Preserved upstream source text
  specifications/               Prior-art schemas and specification extracts
  fixtures/{malformed,edge-cases}/  Deliberately altered, indexed test cases
  derived-examples/              Explicit selections of unchanged real source rows
model/                          This project's proposed contracts and instances
  schema/                       LinkML schemas and validation guide
  profiles/                     Versioned, executable source conversion contracts
  dialects/                     LinkML schemas for a source's own rows, validated before mapping
  examples/                     Worked examples and their source-artifact manifest
analyses/                       Source-specific measurements and selection reports
  nmdc-data-objects/             NMDC categorical-slot and URL-host counts
  nmdc-selection/                Saved sampling report for the original GFF files
  conversion-roundtrips/         Case manifest and reproducible preservation outcomes
  bgc-query/                     Source-grounded actinorhodin order/proximity exercise
  format-validation/             Independent GFF3 verdicts and retained diagnostics
docs/                           Comparisons, interpretation, and design decisions
scripts/                        Acquisition, generation, and validation code
tests/                          Executable checks and small test-only fixtures
local/                          Gitignored inputs, caches, and generated outputs
```

The [layout decision](decisions/001-artifact-layout.md) records the old-to-new path
mapping. Each artifact has one maintained location; there are no compatibility copies
at the old paths. Commands below run from the repository root.

## Running tasks

Use Python 3.11 or later, `uv`, and `just` 1.27 or later. The justfile uses
[groups and explicit help descriptions](https://just.systems/man/en/attributes.html)
to keep the command list readable. Run `just` or `just --list` from the repository
root; `just --show RECIPE` displays a task's implementation. Named defaults such as
`feature_example` keep long paths out of the list; `just --evaluate` displays them.

| Group | Main tasks | Effect |
|---|---|---|
| Validation | `check`, `test`, schema lint and example validation | Check retained artifacts; test scratch goes under `local/` |
| Conversions | `conversion-import`, `conversion-export`, `conversion-validate`, `conversion-check`, `conversion-report` | Create new conversion outputs, check preserved fields/bytes, or explicitly regenerate the tracked report |
| Corpus | `verify`, `verify-links`, `fixtures-generate`, `pr-validation` | Link checks and the default PR audit use the network; fixture generation rewrites tracked derived files |
| Model | `diagram`, `flat-profile-audit [schema]` | Print results; a schema URL may require network access |
| Queries | `build-duckdb`, `query-duckdb`, `query-attribute`, `query-overlap` | Build/update a database, then query it read-only |
| Queries | `bgc-check`, `bgc-report` | Check the real BGC exercise offline, or explicitly regenerate its selected excerpt and query report |
| Source documents | `source-parse`, `source-validate`, `source-replay`, `validate-source-example` | Parse/replay into new files; validate consistency or compare with a retained original |
| NMDC | `nmdc-collect`, `nmdc-render`, `nmdc-sample` | Explicit live collection/sampling or offline regeneration of source-specific reports |
| Documentation | `docs-build`, `docs-check`, `docs-serve [port]` | Stage tracked public files, render and check the site, or preview on loopback |

`just check` keeps its validation scope: it does not collect live NMDC records, sample
files, regenerate corpus fixtures, or publish reports. `uv` can still need the network
to obtain dependencies; `UV_OFFLINE=1` uses cached dependencies when available.
Run `just validity-install` once to install the checksum-pinned GenomeTools binary
under `local/tools/`. `validity-check` compares independent GFF3 verdicts and
diagnostics with the retained report; `validity-report` explicitly regenerates it.
The optional pinned-upstream audit regression requires a retained schema supplied
through `PINNED_GFF_SCHEMA`; otherwise that test reports a skip.
Conversion commands and regression tests use `requirements-conversion.txt` to pin
the measured toolchain. `conversion-check` is read-only; `conversion-report` is the
explicit report-writing task.

The [source-document guide](source-documents.md), [query examples](query-requirements.md),
and nearby NMDC reports document task arguments. Recipe arguments are forwarded as
quoted shell positional parameters: quote values with spaces at the command line.
Source-document recipes accept trailing CLI options such as `--profile prodigal`,
`--source-uri URI`, `--strict`, and `--original PATH` where the underlying operation
supports them. Their errors and exit statuses are preserved.

Recurring user and contributor operations get recipes. A recipe's existence does not
make it a dependency of `check`. The specialized
[Bakta key extractor](../scripts/extract_bakta_keys.py) intentionally remains a direct
command taking the two chosen Bakta source files; its module documentation gives the
pinned retrieval and invocation commands. Individual test modules are reached through
`just test` rather than separate recipes. There is no blanket one-recipe-per-script
requirement. Add concise help and a task group when introducing a new public recipe.

## Choose an artifact

| Question | Start here | Authority and reproduction |
|---|---|---|
| Which real files can I reuse? | [Corpus index](../corpus/index.yaml), [acquisition history](../corpus/PROVENANCE.md), then [source files](../corpus/sources/) | The index governs the corpus inventory. Each entry records provenance and license; paths are repository-root-relative. `just verify` checks inventory invariants and stored checksums. RefSeq gzip downloads are stored decompressed. |
| Which cases were constructed here? | [Malformed](../corpus/fixtures/malformed/) and [edge-case](../corpus/fixtures/edge-cases/) fixtures | Nine indexed mutations of the public-domain phiX174 source, each with a mutation description and appended provenance. `just fixtures-generate` regenerates them; CI checks exact reproduction. [Independent validation](../analyses/format-validation/README.md) measures the validity labels separately from conversion support. |
| How do prior models differ? | [Comparison](model-comparison.md), [columns and producer discretion](columns-and-discretion.md), and [specification evidence](../corpus/specifications/) | Chado SQL is an extracted subset under Artistic-2.0; the KBase YAML is an upstream module under MIT. Their indexed bytes and acquisition scope are recorded. The reserved-attribute YAML is a repository-authored transcription, with its source and date in the file header. These files are evidence for comparison. |
| What model are we proposing? | [Schema guide](../model/schema/README.md), [attribute semantics](attributes.md), and [source-document guide](source-documents.md) | Reusable draft LinkML contracts live in `model/schema/`. Generic attributes are shared by biological records and source records. `just check` runs schema, semantic, corpus, and regression checks. |
| Which instances demonstrate those contracts? | [Example crosswalk](#examples-and-their-contracts) below | Harmonized examples are curated transformations; the parsed source-document example is generated. Their guides identify exact sources and validation commands. |
| Which conversions can round-trip? | [Profile contracts](conversion-profiles.md), [protein-relative example](protein-relative-profile.md) and [measured outcomes](../analyses/conversion-roundtrips/README.md) | GFF3/BED12, NMDC Pfam and bounded INSDC adapters require explicit profiles and reference context; exact byte recovery and mapped-field reconstruction are tested separately. [Joined, partial and circular locations](feature-locations.md) have explicit semantics; unsupported GTF and richer location constructs remain visible. |
| What do the NMDC counts measure? | [DataObject analysis](../analyses/nmdc-data-objects/README.md) | A generated catalogue and counts of NMDC metadata records only. The report identifies pinned schema inputs, collection timestamps, hashes, and data-use terms. Refresh all report/JSON/CSV outputs together using the commands below. |
| How were the original NMDC GFF files selected? | [Selection report guide](../analyses/nmdc-selection/README.md) and [saved selection](../analyses/nmdc-selection/selection.json) | This sampled selection is distinct from the full DataObject analysis. `just nmdc-sample` writes a new live sample to `local/nmdc-selection/selection.json`; inspect errors and changed selections before replacing the saved report. |
| What should I read beyond one format's advocates? | [Cross-format reading guide](feature-format-reading.md) | Sources are dated and their perspectives identified. Literature and tool documentation motivate tests; they do not establish conversion fidelity. |

`corpus/PROVENANCE.md` is a historical account, so its intermediate counts can differ
from the current index. Likewise, a fresh upstream download or API traversal is a new
observation, not automatically a reproduction of an earlier snapshot.

## Examples and their contracts

| Example | Contract | Source and reproduction |
|---|---|---|
| [One biosample's sequencing](../model/examples/one-biosample-sequencing/harmonized.yaml) | [Harmonized feature model](../model/schema/ber_feature_model.yaml), importing [generic attributes](../model/schema/attributes.yaml) | [Guide](../model/examples/one-biosample-sequencing/README.md), [transformation notes](../model/examples/one-biosample-sequencing/notes.md), and [source manifest](../model/examples/source-artifacts.yaml). The curated selection uses a different biosample from the standalone NMDC corpus files. `just validate-example-closed` validates the instance. |
| [One CDS with three Pfams](../model/examples/multiple-pfams/harmonized.yaml) | The same harmonized feature and attribute schemas | [Guide](../model/examples/multiple-pfams/README.md) and the same source manifest identify rows, FASTA records, attribution, and checksums. `just validate-example-closed model/examples/multiple-pfams/harmonized.yaml` validates the instance. |
| [Converted BED12 document](../model/examples/conversions/blat-bed12.json) | Versioned BED12 conversion bundle combining Dataset, SourceDocument and mapping records | [Guide](../model/examples/conversions/README.md) reproduces and validates the generated instance from the pinned BED source; tests require byte agreement and reconstruction of ordered blocks. |
| [Parsed Prodigal document](../model/examples/source-documents/prodigal.json) | [Source-document model](../model/schema/source_document.yaml), importing generic attributes | [Guide](../model/examples/source-documents/README.md) supplies the exact parse command for the unchanged `nmdc-prodigal` corpus entry. `just validate-source-example` checks shape, internal consistency, and byte agreement with the retained corpus source. |

The first two represent biological records. The third preserves ordered source text,
including comments, directives, and feature rows. Source replay alone is not evidence
of a reversible conversion through the harmonized model; executable conversion-profile
guarantees are tracked in [#16](https://github.com/turbomam/feature-table-corpus/issues/16).

[Parser test fixtures](../tests/fixtures/source-documents/README.md) stay under `tests/`
because they are small constructed inputs for unit tests, not additional observed
producer outputs. Corpus fixtures are separately indexed evidence for validator
comparisons and remain under `corpus/fixtures/`.

## Record granularity

- An **NMDC DataObject** describes an artifact. Its category and URL-host frequencies
  count NMDC metadata records, not genomic features or format use across genomics.
- A **source artifact** identifies bytes and provenance. A **source document** represents
  the ordered contents of one physical text artifact.
- A **harmonized Dataset** can combine several artifacts and workflow executions.
  Contig and Feature instances are biological/model records.
- An **Attribute** is an attached key/value entry. The containing object supplies its
  scope; GFF column 9 is one use case.

## Generated outputs and local work

The [schema diagram](schema-diagram.md) is regenerated by `just diagram`, with freshness
checked by CI. `just build-duckdb` writes an experimental physical mapping under
gitignored `local/build/`. Database binaries do not define the model.

To refresh the NMDC DataObject analysis with Python 3.11 or later:

```sh
just nmdc-collect
just nmdc-render
```

`nmdc-collect` traverses the public API and writes local inputs plus published aggregates.
`nmdc-render` requires checksum-verified inputs under `local/nmdc-profile/` and cached
dependencies; a fresh clone cannot reproduce the dated counts offline. An API traversal
is not a transactional snapshot. See the report's refresh safeguards.

Keep task inputs, retained downloads, and scratch output under `local/<task>/`, with
source URLs and checksums where needed. These gitignored files are excluded from the
[GitHub Pages build](documentation-site.md).
