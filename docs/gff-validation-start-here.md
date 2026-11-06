# GFF validation and splitting: start here

This page is for anyone picking up the GFF validator or the fast first-pass splitter (https://github.com/turbomam/feature-table-corpus/issues/185). It lists the file kinds in this repository and the specification each one follows, the specifications and reference implementations the work depends on, and exactly which lines of a file reach DuckDB today. Everything here was read from the code on main (139d23e) on 2026-11-06; nothing on this page was newly measured.

## The pipeline today

1. `scripts/source_document.py` reads a GFF3, GTF, BED12 or GenBank file into ordered records, one per line, and can replay the file byte for byte. Details: [source-documents.md](source-documents.md).
2. A versioned conversion profile in `model/profiles/` turns feature records into `Dataset`, `Contig` and `Feature` instances of `model/schema/ber_feature_model.yaml`, and refuses with a named reason what it can't hold. `just conversion-import` writes a JSON bundle holding both the source records and the dataset; `just conversion-export` rebuilds the original file from the bundle. Details: [conversion-profiles.md](conversion-profiles.md).
3. `scripts/validate_closed.py` checks the dataset against a closed JSON Schema generated from the LinkML schema, then runs cross-record checks: duplicate IDs, unknown parents, parent cycles, a parent on another contig, end beyond contig length.
4. `just build-duckdb` loads the dataset alone, not the bundle, into three tables: `contig`, `contig_collection` and `feature`.

In the terms from the 2026-10-23 meeting, steps 1 and 2 are the loader, the closed JSON Schema is the generic validation plugin, and the cross-record checks are the schema-specific plugin. The row-level checks (phase, escaping, cardinality) live inside the loader in `scripts/convert_features.py`, not in a plugin. Moving them out is the main refactor a real validator needs.

## File kinds and what they follow

Counts are entries in `corpus/index.yaml` on main; some entries are links to files too large or too restricted to vendor.

| file kind | where in the corpus | specification or dialect | path into the model |
|---|---|---|---|
| NCBI RefSeq GFF3 | `corpus/sources/ncbi-refseq/` | SO GFF3 1.26 plus NCBI's dialect, including `#!` header lines | `gff3-contig` profile, `--metadata-profile ncbi` |
| NCBI RefSeq viral GFF3, chosen by @simroux | `corpus/sources/ncbi-refseq/`, listed in the [corpus inventory](../corpus/README.md#the-vendored-files) | as above | `gff3-contig`; circular genomes and one CDS ID on several rows are refused (https://github.com/turbomam/feature-table-corpus/issues/181, https://github.com/turbomam/feature-table-corpus/issues/175, https://github.com/turbomam/feature-table-corpus/issues/179) |
| NCBI RefSeq GTF | `corpus/sources/ncbi-refseq/` | GTF 2.2 | read by `scripts/source_document.py` only; no conversion profile |
| NMDC GFF3 in contig coordinates (JGI IMG annotation pipeline output, such as `_structural_annotation`, `_functional_annotation` and `_prodigal`) | `corpus/sources/nmdc/` | GFF3 as written by the IMG pipeline; 33 of the 37 IMG and NMDC GFF files have no `##gff-version` line | `gff3-contig`; `--metadata-profile prodigal` for the Prodigal file |
| NMDC and IMG per-method hit files (`_pfam`, `_cog`, `_ko_ec`, `_tigrfam`, `_smart`, `_supfam`, `_cath_funfam`) | `corpus/sources/nmdc/`, `corpus/sources/jgi-img/` | the IMG per-method dialect: column 1 is a gene ID and columns 4 and 5 are amino-acid positions in that gene's protein | not `gff3-contig`, which would read the protein positions as contig positions; `just map-img-per-method` with the matching functional-annotation file, and Pfam also through `nmdc-pfam-protein` ([protein-coordinates.md](protein-coordinates.md)) |
| JGI IMG per-method, functional, assembled, TMHMM/SignalP and taxon-bundle GFF and TSV | `corpus/sources/jgi-img/` | the IMG dialects in `model/dialects/` | dialect mapping scripts (`just map-img-*`), described in [IMG dialects](img-dialects.md) |
| Phytozome `gene_exons` GFF3 and `annotation_info` TSV | restricted; derived excerpts in `corpus/derived-examples/` and a constructed fixture in `tests/fixtures/phytozome/` | the [Phytozome dialects](phytozome-dialects.md) in `model/dialects/` | `just` Phytozome mapping recipes; TAIR10 is never vendored ([restricted-sources.md](restricted-sources.md)) |
| BED12 | `corpus/sources/biopython/` | BED version 1 | `bed12-blocks` profile |
| GenBank flat file | `corpus/sources/biopython/`, `corpus/sources/ncbi-refseq/` | INSDC Feature Table Definition | `insdc-locations` profile, which handles joins and origin-crossing locations |
| Malformed and edge-case GFF3, each one documented change from a real file | `corpus/fixtures/malformed/`, `corpus/fixtures/edge-cases/` | the `validity` field in `corpus/index.yaml` says whether each is invalid GFF3 or valid but refused | negative tests |
| Conversion refusal controls, written from scratch rather than changed from a real file | `tests/fixtures/conversions/` | its README | profile refusal tests |
| JGI SMC (Secondary Metabolite Collaboratory) GFF3 | linked only | SMC's own output | not imported yet |

## Specifications and reference implementations

| resource | what it is | how this repository uses it |
|---|---|---|
| https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md | SO GFF3 specification | the rules the `gff3-contig` profile enforces |
| GTF 2.2, GFF2, BED, INSDC Feature Table, NCBI GFF3 documentation | the other format specifications | linked from the [corpus inventory](../corpus/README.md#specifications) and from [background.md](background.md#reading-across-feature-table-formats) |
| GenomeTools 1.6.6 and GFF3toolkit 2.1.0 | existing GFF3 validators | their verdicts on every retained GFF3 file are recorded in `model/validation/`, and CI fails if one changes |
| https://github.com/enasequence/gff3tools | ENA's validator and converter for the INSDC GFF3 draft specification | not run yet; a comparison point in https://github.com/turbomam/feature-table-corpus/issues/185 |
| https://github.com/daler/gffutils | loads GFF and GTF into SQLite tables that mirror the format; not a validator | its line iterator was inspected when `scripts/source_document.py` was designed ([source-documents.md](source-documents.md)); its SQLite layout is a comparison for the DuckDB layout and a candidate in https://github.com/turbomam/feature-table-corpus/issues/185 |
| https://github.com/zaeleus/noodles | Rust readers and writers for GFF, GTF, BED and FASTA | the Rust option in https://github.com/turbomam/feature-table-corpus/issues/185 |
| SMC backend scripts on JGI GitLab | GFF validation, fixing and parsing code for SMC | not readable from here; the problems the SMC team has met in GFF files are listed in the 2026-10-09 SequenceFeature Modeling notes, https://docs.google.com/document/d/17Z1o7KNNqlMFq4WArIlvVlBvNeaW9ADBwZPG8R6u52o |
| https://github.com/cmdcolin/oddgenes | curated gene annotations that break common assumptions | cases mapped to model tests in [acceptance-tests.md](acceptance-tests.md) |
| Chado, KBase CDM, https://github.com/biodatamodels/gff-schema | earlier models of a sequence feature | compared in [model-comparison.md](model-comparison.md) and [background.md](background.md#prior-art) |

## What reaches DuckDB

For files that go through `gff3-contig`, each line kind ends up in one of three places: the DuckDB tables, a check that stores nothing, or only the JSON bundle that exact export replays. Nothing below is lost from the bundle; all of it except feature rows and the one `##sequence-region` case is missing from DuckDB.

| line kind | in DuckDB | used without being stored | kept only in the bundle |
|---|---|---|---|
| feature row | yes: one row in `feature`, all nine columns, column 9 as an ordered attribute list plus typed slots | | |
| `##gff-version` | no | must say 3 if present | yes |
| `##sequence-region` | only as `contig.length_bp`, under `--metadata-profile ncbi`, when a contig has exactly one region starting at 1 | every feature must fall inside its declared region | yes |
| other `##` directives, such as `##species` or `##genome-build` | no | | yes |
| `#` comments | no | with `--metadata-profile prodigal` only, Prodigal's `# Sequence Data` lines set a length check on the features that follow; the default `generic` profile doesn't read them | yes |
| NCBI `#!` header lines | no | | yes, parsed as named metadata under `--metadata-profile ncbi` |
| `###` sync marks | no | nothing checks that no Parent crosses one | yes |
| `##FASTA` and the embedded FASTA section | no | | yes; contig lengths are not taken from it yet (https://github.com/turbomam/feature-table-corpus/issues/124) |
| blank lines | no | | yes |

GTF files never reach DuckDB, because no conversion profile reads them.

## Where help is wanted

- A splitter that sends feature rows, the embedded FASTA section and the header metadata to three stores fast enough for full-size files, with lossless round-tripping: https://github.com/turbomam/feature-table-corpus/issues/185
- LinkML validator plugins over those tables, with the row-level checks moved out of the loader. No issue exists yet.
- A home for header metadata in DuckDB, so the right-hand column of the table above can move left.
