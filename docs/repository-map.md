# Repository map: evidence, models, and examples

Use this page to choose the right artifact and find its authority, provenance, and
reproduction path. The directories serve different purposes: a source file, a model,
an example instance, and a report about source metadata are different kinds of evidence.
`corpus.yaml` is the source of truth for the **corpus inventory**, not for every
model, example, or measurement in the repository.

This map describes `main` after [PR #14](https://github.com/turbomam/feature-table-corpus/pull/14)
on September 21, 2026. The draft model and source-document work are separately
identified below as proposals in [#6][model-pr] and [#15][document-pr]. Links to those
artifacts use fixed commits so this page is usable before they merge.

## Choose a reading path

| Your question | Start with |
|---|---|
| Which real files can I reuse, and where did they come from? | [Corpus index](../corpus.yaml), [acquisition history](../PROVENANCE.md), then the indexed `data/` paths |
| How do prior models differ? | [Model comparison](model-comparison.md), [columns and producer discretion](columns-and-discretion.md), and their cited specifications |
| What is this repository proposing? | The [draft model and validation guide][model-guide] in #6, then the worked examples below |
| What do comments and directives mean at file or sequence scope? | The [source-document guide][document-guide] in #15 |
| What do the NMDC category and URL counts measure? | The [NMDC DataObject profile](../profiles/nmdc-data-objects/README.md), which covers NMDC metadata records only |
| What should I read beyond one format's advocates? | The [annotated cross-format reading guide][reading-guide] in #15, with dates and source perspectives |
| Where should a new artifact go? | The role table below and the [layout decision](decisions/001-artifact-layout.md) |

The analysis documents contain dated observations and interpretations. They are not
format specifications or proof that a proposed model handles every representation.

## Artifacts already on main

| Area | Role, authority, and intended reader | Provenance and license | Reproduce or check |
|---|---|---|---|
| [`corpus.yaml`](../corpus.yaml) | Maintained inventory of sourced, linked, derived, restricted, and unlocated artifacts; for corpus users and contributors | Each entry records its own origin, retrieval, license, and tier-specific fields; repository-authored metadata is covered by [LICENSE](../LICENSE) | `uv run --with pyyaml python scripts/verify.py` checks invariants, current README counts, files, and checksums |
| [`data/nmdc/`](../data/nmdc/) and [`data/ncbi-refseq/`](../data/ncbi-refseq/) | Preserved source text used as producer evidence and parser input | Read each index entry. NMDC sources carry attribution requirements; RefSeq entries record public-domain status. RefSeq gzip downloads are stored decompressed, and the indexed checksum covers that text | Verify with the command above. Acquisition is recorded in [PROVENANCE.md](../PROVENANCE.md); there is no blanket command that safely replaces these snapshots with today's upstream content |
| [`data/derived-malformed/`](../data/derived-malformed/) and [`data/derived-edge-cases/`](../data/derived-edge-cases/) | Generated, deliberately altered parser fixtures; for validator authors, not observations of producer behavior | Each entry names its source and mutation; files also carry appended provenance comments. The source is the public-domain phiX174 GFF | `python3 scripts/make_malformed.py`, then run the verifier and review the diff. CI checks exact reproduction; independent measurement of validity labels is still [#2](https://github.com/turbomam/feature-table-corpus/issues/2) |
| [`specs/`](../specs/) | Prior-art schema material for comparison, not this project's proposed model | Chado SQL contains extracted feature-table blocks under Artistic-2.0; the KBase YAML is a complete upstream module under MIT. Their index entries and acquisition history specify the scope | Indexed bytes are checked by the verifier. Chado extraction is documented in PROVENANCE.md; no standalone extraction generator is supplied |
| [`profiles/nmdc-data-objects/`](../profiles/nmdc-data-objects/) | Generated source-specific catalogue, counts, CSVs, and report; for readers assessing one source's metadata | The report and JSON provenance identify the pinned NMDC schema, collection timestamps, hashes, and data-use policy | Use the profile commands below. Refreshes can change the counts; an API traversal is not a transactional snapshot |
| [`docs/`](.) | Human-maintained comparisons, interpretations, decisions, and navigation; for reviewers and contributors | Cite the supporting source or measurement and retain its date. Repository prose does not relicense referenced sources | Follow each document's measurement commands; there is no universal report generator. The [layout decision](decisions/001-artifact-layout.md) defines the publication boundary |
| [`scripts/`](../scripts/) | Acquisition, fixture generation, analysis, verification, and reporting implementations; for contributors | Code follows the repository license. `nmdc_selection.json` is a generated selection report, not the corpus index or a full DataObject census | Run the named script for the artifact being changed. `python3 scripts/harvest_nmdc.py` refreshes the selection report using a live query; it does not reproduce the dated full-collection profile |
| [`tests/`](../tests/) and [`.github/workflows/`](../.github/workflows/) | Executable checks and CI orchestration; for maintainers | Test fixtures and assertions describe their scope. Passing a check establishes only the property it tests | `uv run --with linkml-runtime python -m unittest discover -s tests -v`; CI also verifies the corpus and regenerates derived fixtures |
| `local/` (gitignored) | Local inputs, snapshots, caches, downloaded sources, and generated outputs needed by a particular analysis | Keep source URLs and checksums with retained inputs; never assume these are redistributable or safe to publish | Recreate from the responsible script or documented source. This directory is not a checked-in source of truth and must be excluded from a future site |

`PROVENANCE.md` is a dated acquisition and correction history. Its older intermediate
counts describe that history; use the current index and generated profile outputs for
current counts. A live download or collection is a new observation, not automatically a
reproduction of an earlier snapshot.

## Proposed model and example areas

These paths are introduced by the open PRs, rather than present in the `main` snapshot
described above. Their status is deliberately separate from the existing corpus.

| Area | Role and authority | Reproduction and provenance |
|---|---|---|
| [`schema/` in #6][model-schema] | Proposed reusable LinkML contracts: `attributes.yaml` is generic; `ber_feature_model.yaml` defines the harmonized Dataset, Contig, and Feature profile | On that branch, `just check` validates the schemas and examples. [Attribute semantics][attribute-guide] and [model limitations][model-guide] are part of the draft contract; prior-art files under `specs/` do not override it |
| [`examples/` in #6][model-examples] | Worked instances of the proposed model, plus an artifact manifest; a separate case-study collection from the sampled files indexed in `corpus.yaml` | The worked examples are curated transformations with documented selections, not outputs of a complete automatic harmonizer. Follow their guides and source checksums; do not substitute similarly named corpus files |
| [`schema/source_document.yaml` in #15][document-schema] | Independent source-document contract for one physical source and its ordered records; imports generic attributes | The [parser guide][document-guide] defines explicit format/producer profiles, scopes, byte replay, and limits. It does not make a physical file equivalent to a harmonized Dataset |
| [`examples/source-documents/` in #15][document-example] | Generated parsed instance from a real, unchanged corpus file | The example guide supplies the exact parse command and comparison with its vendored source; `just validate-source-example` checks shape and replay integrity on that branch |
| `tests/fixtures/source-documents/` in #15 | Small derived inputs for parser edge cases, separate from observed producer output | Fixture documentation labels constructed cases; `just test` checks behavior. These are not additional real files in the corpus inventory |
| Generated diagrams and databases in #6 | The committed diagram is a reviewed presentation of the schema; a DuckDB file is a generated physical mapping for query experiments | `just diagram` regenerates the diagram and CI checks its freshness. `just build-duckdb` writes under gitignored `local/build/` by default. No database binary is an authoritative model or published corpus source |

All commands in that table belong to the indicated PR branch; `main` does not yet have
their `justfile`. After those PRs merge, update this dated status and use ordinary
relative links for the now-current artifacts. Keep commit links when citing a historical
comparison or reproduction.

## Example-to-schema and source map

| Example | Exact schema snapshot | Source authority and reproduction guide |
|---|---|---|
| [One biosample's sequencing][biosample-example] | [Harmonized model][model-schema-file], including its [attribute module][attribute-schema] | [Selection and transformation notes][biosample-notes] and [source-artifact manifest][source-manifest]. This case uses a different biosample from the standalone NMDC corpus files |
| [One CDS with three Pfams][pfam-example] | [Harmonized model][model-schema-file], including its [attribute module][attribute-schema] | [Example guide][pfam-guide] and the same [manifest][source-manifest]; source rows and FASTA records are identified explicitly, with NMDC attribution and checksums |
| [Parsed Prodigal source document][document-example-json] | [Source-document model][document-schema], including [its attribute module][document-attribute-schema] | [Example guide][document-example] maps directly to the unchanged `nmdc-prodigal` corpus entry and supplies the exact regeneration command |

The first two are harmonized biological records; the third is a preservation-oriented
representation of source text. Similar use of YAML/JSON or shared attributes does not
make their purposes or validation guarantees interchangeable.

## Record granularity

- An **NMDC DataObject** is a metadata record describing an artifact. One such artifact
  can contain many feature rows or no genomic features at all. Its category and URL-host
  frequencies are counts of NMDC metadata records, not counts of features or formats in use
  across genomics.
- A **source artifact** identifies the bytes and their provenance; a **source document**
  represents the ordered contents of one physical text artifact, including comments and
  control records.
- A **harmonized Dataset** can combine records from several artifacts and workflow
  executions. Contig and Feature instances are biological/model records, not files.
- An **Attribute** is an attached key/value entry. Its scope comes from the object or
  record to which it is attached; GFF column 9 is one use case.

These distinctions are responsibilities of the proposed model, not claims that NMDC's
DataObject class should define a universal feature-table format.

## Reproduce the NMDC profile

From the repository root, with Python 3.11 or later:

```sh
uv run --with linkml-runtime python scripts/profile_nmdc_data_objects.py collect
uv run --offline --with linkml-runtime python scripts/profile_nmdc_data_objects.py render
```

`collect` performs a new public-API traversal and writes the local projection plus
published aggregates. `render` requires the checksum-verified inputs under
`local/nmdc-profile/` and cached dependencies; a fresh clone alone cannot reproduce the
dated counts offline. See the [profile report](../profiles/nmdc-data-objects/README.md)
for interpretation and refresh safeguards. Its generated README and CSV/JSON files
should be regenerated together rather than edited independently.

[model-pr]: https://github.com/turbomam/feature-table-corpus/pull/6
[document-pr]: https://github.com/turbomam/feature-table-corpus/pull/15
[model-schema]: https://github.com/turbomam/feature-table-corpus/tree/bfec42c4448a79cc945406f5b84beefd439ab8cc/schema
[model-guide]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/schema/README.md
[attribute-guide]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/docs/attributes.md
[model-examples]: https://github.com/turbomam/feature-table-corpus/tree/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples
[model-schema-file]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/schema/ber_feature_model.yaml
[attribute-schema]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/schema/attributes.yaml
[biosample-example]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples/one-biosample-sequencing/harmonized.yaml
[biosample-notes]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples/one-biosample-sequencing/notes.md
[source-manifest]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples/source-artifacts.yaml
[pfam-example]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples/multiple-pfams/harmonized.yaml
[pfam-guide]: https://github.com/turbomam/feature-table-corpus/blob/bfec42c4448a79cc945406f5b84beefd439ab8cc/examples/multiple-pfams/README.md
[document-schema]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/schema/source_document.yaml
[document-attribute-schema]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/schema/attributes.yaml
[document-guide]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/docs/source-documents.md
[document-example]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/examples/source-documents/README.md
[document-example-json]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/examples/source-documents/prodigal.json
[reading-guide]: https://github.com/turbomam/feature-table-corpus/blob/bb6b68cb17993e0afed184160dfa122deece046b/docs/feature-format-reading.md
