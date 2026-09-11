# How each vendored file got here

Written 2026-09-11. Every step below was run, not planned.

## The 14 NMDC files

1. Read `src/schema/basic_slots.yaml` in `microbiomedata/nmdc-schema` and found 16 distinct
   `data_object_type` values whose descriptions say GFF3.
2. Queried the NMDC public API once per type, same query shape for all 16. Fourteen returned
   records. Two returned none, `Misc Annotation GFF` and `TMRNA Annotation GFF`, so those two
   absences are real rather than a broken query.
3. For each of the 14, paged up to 600 records and selected the smallest by `file_size_bytes`.
   The selection is recorded per entry in `corpus.yaml` under `selection`, including how many
   records were sampled.
4. Downloaded each file and compared its MD5 against the `md5_checksum` field in the NMDC record.
   All 14 matched. That comparison is recorded per entry as `md5_matches_source_record: true`.

The smallest files are small because those workflow runs produced few features, not because the
files are truncated. Each is a complete file as NMDC serves it.

## The 2 NCBI files

Fetched from the RefSeq FTP tree by assembly accession. Both returned HTTP 200 and were complete
gzipped GFF3, then decompressed for storage here because this repository carries no binary files.
The recorded MD5 is therefore of the decompressed text, not of the gzip the URL serves.

A third candidate, tobacco mosaic virus at `GCF_000862205.1`, returned 404 and was
discarded rather than kept as a 990 byte error page.

NCBI publishes no per-file checksum at those URLs, so the MD5 in `corpus.yaml` is of the bytes as
fetched on 2026-09-11 and establishes only that the file has not changed since, not that it matches
an upstream record.

## What was searched and not used

See [docs/prior-art.md](docs/prior-art.md), which records the four existing models and their
staleness, the seven normalization efforts and why none of them is a data model, the eleven named
format flavors with their attributions, and the approaches that were considered and rejected. Also
the `why_not_vendored` field on each linked entry.

## The 2 NCBI GTF files

Same accessions as the GFF3 files, fetched from the `_genomic.gtf.gz` sibling on the same FTP path,
then decompressed. Both declare `#gtf-version 2.2` in their own first line, so the flavor is the
file's own claim rather than an assumption.

## The 2 vendored specifications

`specs/chado_1.4_feature_tables.sql`. Downloaded the 2.2 MB `schemas/1.4/default_schema.sql` from
branch `1.4` of GMOD/Chado, then extracted the seven `create table` blocks whose names begin
`feature`. The repository default branch is `1.4`, not `master`; a raw URL built on `master`
returns 404, which is how the first attempt failed.

`specs/kbase_cdm_bioentity.yaml`. Taken whole from `src/linkml/cdm_bioentity.yaml` on `main`. The
Feature class is in that module, not in `cdm_components.yaml`; the first attempt fetched the wrong
file and a grep for `Feature:` matched an enum value inside it, which looked like success.

## The 8 derived files

Built by `scripts/make_malformed.py` from the vendored phiX174 GFF3, six in
`data/derived-malformed/` and two in `data/derived-edge-cases/`. Each output is that source
preserved line for line with one change to one data row, plus provenance comments, which are
ordinary single-hash lines appended after the source's own `###` terminator. They are not pragmas
and they are not in the header, and earlier wording in this file called them header pragmas, which
was wrong.

`no_version_pragma` is the one exception to both halves of that: its single change removes a header
directive, so its change is not to a data row and its header is deliberately not byte-identical.

The two files in `derived-edge-cases/` are valid GFF3 rather than malformed. `multiple_parents` is
permitted by the specification and refused by many tools. `cds_phase_biologically_wrong` carries a
legal phase value that is biologically wrong, so a syntax-only validator passes it while the
translated protein changes.

All eight are labeled `derived` in the index and are not evidence about any real producer.

## EMSL, searched and not found

Searched GitHub repository and code search across `ber-data` and `microbiomedata` for BASALT, and
the open web for MONet data access. MONet is real, published without embargo on EMSL Science
Central, and recorded. BASALT is not public anywhere that could be found on 2026-09-11. Recorded as
`not located` so the gap is visible rather than forgotten.

## Corrections after the second review, 2026-09-11

The first version of the derived files was wrong in ways the review caught, and the corrections
changed the files themselves rather than only their descriptions.

**The generator discarded every source pragma.** It rebuilt each fixture from data rows alone and
wrote a fresh header, so `#!genome-build`, `##sequence-region`, `##species` and the `###`
terminator were all lost. Each file therefore differed from its source in many header semantics
while claiming one documented change. The generator now preserves the source line for line and
appends provenance comments, single-hash lines after the terminator, so the header region is
byte-identical. These are comments rather than pragmas and they sit outside the header, which
earlier wording in this file got wrong. The one exception is `no_version_pragma`, whose single
change is the removal of that one header line.

**Two fixtures carried a second, undocumented defect.** The semicolon case overwrote a `product`
attribute that already existed, adding a duplicate-attribute defect beside the intended one; it now
uses `Note`. The multiple-parent case named a second parent that was defined nowhere, making it a
dangling-parent fixture as well; it now uses `gene-phiX174p06`, which the source defines.

**The circular-genome rationale was backwards.** The earlier text said a swapped start and end was
ambiguous rather than wrong because phiX174 is circular. GFF3 requires start no greater than end on
every feature, circular included, and expresses wraparound by extending end past the landmark
length. The case is a plain coordinate-rule violation. Corrected in the generator, the index and
the README.

**One valid file was filed as invalid.** The multiple-parent case is legal GFF3 that many tools
refuse, and it sat in `derived-malformed/` labeled invalid. It now lives in `derived-edge-cases/`,
and every derived entry carries a `validity` field so the distinction cannot be lost again.

**The index was indexing one artifact twice.** The Sequence Ontology GFF3 specification appeared as
both `so-gff3-spec` and `spec-gff3-so`, which inflated the entry and specification counts. The
duplicate is removed, and the verifier now rejects a repeated `origin_url`, exempting derived
entries because they legitimately share the generator that produces them.

**Three checks could not fail.** The verifier did not require `origin_url` on a vendored entry
though the README calls it part of the contract; it raised `KeyError` instead of a clean nonzero
report when an entry it had just rejected lacked `path` or `tier`; and the CI fixture check used
`git diff`, which ignores untracked files, so a fixture deleted from a pull request would have been
silently regenerated and the step would have passed. All three are fixed, and CI now injects five
separate defects and fails the build if the verifier accepts any of them or rejects one without
naming it.

**The README counts were wrong.** Twelve specifications, not eleven, and ten linked, not nine. The
byte total still said 80 KB after four files were added.

## Corrections after the balanced review, 2026-09-11

Two fixtures were classified as specification violations without checking the specification, which
is the same mistake as the `multiple_parents` misclassification corrected earlier the same day.

**A changed CDS phase is not a violation.** GFF3 permits 0, 1 and 2, so altering 0 to 1 produces a
biologically wrong annotation that stays valid. That file moved to `derived-edge-cases/` as
`cds_phase_biologically_wrong`, and a genuine violation was added as `cds_phase_illegal`, which
sets phase to 3. The pair is now the most useful thing in the derived set: one is caught by a
validator and the other is not, and the one that is not is the failure AgBioData leads with.

**A duplicated row is not a duplicate ID.** GFF3 permits a discontinuous feature to span several
lines under a shared ID. The earlier fixture inserted a row with the same seqid, source, type,
strand and attributes, which is exactly a legal discontinuous feature. The ID now collides across a
`gene` and a `sequence_alteration`, which cannot describe one feature, so the violation is real.

**Descriptions that contradicted the files.** The README stated "one change to one data row" and a
byte-identical header as blanket claims, while `no_version_pragma` is the exception to both. That
exception is now stated in the README and in that entry's own notes rather than the entry repeating
the generic text.

**Wording.** The provenance lines were called header pragmas. They are single-hash comments
appended after the source's `###` terminator, outside the header and not pragmas at all.
