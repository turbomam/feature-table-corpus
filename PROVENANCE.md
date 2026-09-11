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

See `~/Desktop/markdown/prior-art-feature-table-corpus-2026-09-11.md` on the machine where this was
assembled, and the `why_not_vendored` field on each linked entry.
