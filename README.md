# feature-table-corpus

Real, traceable examples of GFF and other genome feature table content.

Built to support work on a unified LinkML model for genome features across DOE Biological and
Environmental Research data sources. The point is breadth of real producers, not volume: every
entry names the tool or project that wrote it, the URL it came from, and the date it was fetched.

## What is here

25 entries in three tiers. The index is [corpus.yaml](corpus.yaml), which is the source of truth;
this README describes it.

| Tier | Count | Meaning |
|---|---|---|
| vendored | 16 | The file is in this repository, with its origin URL and an MD5 checksum |
| linked | 6 | Too large or not redistributable, so a stable public URL is recorded instead |
| restricted | 3 | Behind a login. Recorded for completeness, not fetchable here |

Everything vendored totals about 80 KB of plain text, so a clone is cheap and every file is
reviewable in a diff. Nothing here is binary or compressed.

## The vendored files

**NMDC, 14 files, 158 bytes to 4.6 KB.** One per distinct `data_object_type` that carries GFF in
NMDC production. Each is the smallest real file of its kind out of roughly 600 sampled through the
public API, and each checksum matches the MD5 recorded in the NMDC record itself. These 14 are the
useful part of this corpus, because they show that one annotation is not one file. It is a set of
evidence streams that all describe the same features:

- gene callers: Prodigal, GeneMark
- feature finders: tRNAscan, CRISPR Recognition Tool, Rfam
- database searches, each written to its own file: Pfam, TIGRFAM, SMART, SUPERFAMILY, CATH
  functional families, Clusters of Orthologous Groups, KEGG Orthology with Enzyme Commission numbers
- roll-ups: structural, functional

All are outputs of the JGI IMG annotation pipeline, reachable openly through NMDC. Licensed CC BY
4.0 under the [NMDC data use policy](https://microbiomedata.org/nmdc-data-use-policy/).

**NCBI RefSeq, 2 files.** Complete tiny reference annotations from the canonical GFF3 producer,
for phiX174 at 6.5 KB and phage lambda at 58 KB. Public domain. Both are decompressed from the
gzip the FTP site serves, because this repository carries no binary files. These give a clean baseline: a well formed GFF3 with
a spec-version pragma, sequence regions, and proper parent and child structure.

## Why some things are only linked

The best single source for the eleven named format flavors, GFF through GTF3, is the AGAT test
suite, and it is GPL-3.0. Linking keeps a copyleft obligation off this corpus. GenomeTools and
GFF3toolkit carry no determinable license in their repository metadata, so those are linked too
rather than guessed at. GENCODE is linked because it is tens of megabytes.

Where a license could not be determined, `corpus.yaml` says so in that entry rather than leaving
it blank.

## Verifying it

```shell
uv run --with pyyaml python scripts/verify.py          # checksums
uv run --with pyyaml python scripts/verify.py --links  # also HEAD every URL
```

Checksum failures exit non-zero. Dead upstream links do not, because a moved URL is something to
record rather than a defect here.

## Reproducing the NMDC selection

```shell
python3 scripts/harvest_nmdc.py
```

This re-runs the query that picked the 14 files and writes `scripts/nmdc_selection.json`. One
thing to know if you adapt it: a plain `urllib` request to the NMDC API returns 403, and the same
URL through `curl` returns 200. The script sends a `curl` user agent for that reason. Without it
the API looks down when it is not.

## Known gaps

These are wanted and not yet here.

- **EMSL.** MONet and the BASALT schema. A flattened BASALT schema was reported as coming from
  James Carr. No stable public URL located yet.
- **KBase.** The Common Data Model defines a
  [Feature class](https://kbase.github.io/cdm-schema/Feature/), but that is a model rather than
  data. No sample feature tables located.
- **Chado.** The relational ancestor of most of this. Sample data not yet tracked down.
- **GTF flavors as vendored files.** Currently only reachable through the linked AGAT suite.
- **Malformed real files.** The corpus is all well formed so far. The failures the AgBioData group
  describes, in particular the CDS phase column being misread, are better shown than described.

Pull requests adding entries should fill in every field that the existing entries carry, especially
`origin_url`, `retrieved` and `license`.

## Licensing

Per entry, recorded in `corpus.yaml`. The NMDC files are CC BY 4.0 and require attribution to NMDC.
The NCBI files are public domain. This repository's own contributions, meaning the index, the
scripts and this README, are CC0.

If you own content vendored here and would rather it were linked, open an issue and it will be
moved to the linked tier.
