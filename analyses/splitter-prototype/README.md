# GFF split prototype: four real files into DuckDB and back, 2026-11-06

Prototype for https://github.com/turbomam/feature-table-corpus/issues/185. Not the fast splitter: it reuses the stdlib Python reader `scripts/source_document.py` and holds each file in memory. Script: `scripts/split_gff_prototype.py`. Databases and per-file JSON summaries are written to the gitignored local/split-prototype-2026-11-06/ when the script is rerun. Run 2026-11-06 on an Apple M5 Max, Python 3.11.

## What each database holds

- `header_record`: every `##` directive, `#` comment, NCBI `#!` line, `###` sync mark, `##FASTA` line and blank line, one row each, valid against the `SourceRecord` class in `model/schema/source_document.yaml`.
- `feature_record`: every feature row, also as a `SourceRecord` row, so files the feature model refuses still land.
- `biosequence`: one row per embedded FASTA sequence, with the residues and the line layout needed to write the FASTA back exactly.
- `contig`, `contig_collection` and `sequence_feature`: the feature model's tables, only when the `gff3-contig/4.0.0` profile accepts the file.

## Results

| file | bytes | header rows | feature rows | sequences | every row valid | feature model tables | rebuilt byte for byte | total seconds |
|---|---|---|---|---|---|---|---|---|
| Ensembl yeast mitochondrion GFF3 (`Saccharomyces_cerevisiae.R64-1-1.63.chromosome.Mito.gff3`) | 44006 | 63 | 257 | 0 | yes | no: refused as circular | yes | 0.55 |
| Bakta v1.12.2 GFF3, *Mycoplasma genitalium* G37 (NC_000908.2) | 687506 | 9 | 566 | 1 | yes | no: refused as circular | yes | 0.79 |
| Prokka v1.15.6 GFF3, same genome | 707621 | 3 | 562 | 1 | yes | yes: 562 `sequence_feature` rows | yes | 0.99 |
| NCBI RefSeq GFF3, phage MS2 (NC_001417.2) | 2961 | 6 | 11 | 0 | yes | yes: 11 `sequence_feature` rows | yes | 0.27 |

Header rows by kind:

| file | directives | comments (`#` and `#!`) | `###` sync marks | `##FASTA` | blank |
|---|---|---|---|---|---|
| Ensembl yeast mitochondrion | 2 | 5 | 56 | 0 | 0 |
| Bakta | 3 | 5 | 0 | 1 | 0 |
| Prokka | 2 | 0 | 0 | 1 | 0 |
| NCBI MS2 | 3 | 2 | 0 | 0 | 1 |

Most of the time goes to writing DuckDB and to the feature model import; parsing took 0.01 s or less per file.

## What changes before this becomes the real output

From the review of established GFF tools, a review of how established GFF tools parse and store these files (to be added; summary at https://github.com/turbomam/feature-table-corpus/issues/185):

1. Typed directive classes (`SequenceRegion`, `GenomeBuild`, `Species`, `GffVersion`) in `source_document.yaml`, after noodles-gff and ENA gff3tools, instead of one untyped key/value column.
2. Directive and attribute content feeding the feature model: `Is_circular=true` into `Contig.topology` (both refusals above are this case), `#!genome-build-accession` into `ContigCollection.collection_id`, and a taxon id slot.
3. The sequence table rebuilt on samtools faidx's `.fai` columns (bases per line, bytes per line, offset) instead of columns of my own.
4. The nine GFF columns as typed columns in `feature_record`, as every Arrow reader stores them.
5. A fix to the reader: a FASTA line containing a space is accepted as sequence and the space is counted in the length (found by reading the code, not yet reproduced).
