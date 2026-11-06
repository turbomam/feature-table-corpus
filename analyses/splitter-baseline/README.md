# GFF split baseline: stdlib reader and split prototype, 2026-11-06

This is the speed and memory of the current stdlib Python path on the largest GFF3 files in the corpus: `parse_bytes` in `scripts/source_document.py`, and the full split prototype in `scripts/split_gff_prototype.py` (described in `analyses/splitter-prototype/README.md`). A fast splitter chosen in https://github.com/turbomam/feature-table-corpus/issues/185 can be compared against these numbers on the same files.

Measured 2026-11-06 on an Apple M5 Max (18 cores), macOS 27.0.1 arm64, Python 3.11.15, with `scripts/benchmark_gff_split.py`.

## How it was measured

- Every measurement runs in a new Python process, so peak memory from one file never carries into the next.
- "parse s" times `parse_bytes` alone, on bytes already read into memory.
- "split s" times the prototype's `main()`: parse, validate every row against `SourceRecord`, try the `gff3-contig/4.0.0` feature model import, write DuckDB, and rebuild the file from DuckDB.
- Both times exclude interpreter startup and imports.
- "peak MB" is `ru_maxrss` of the split process, so it includes the interpreter and libraries. After imports and before any work, that process already peaked at 97 MB on every file.
- Each measurement ran 3 times; the table gives the median.
- The metadata profile is `ncbi` for NCBI RefSeq files (they carry `#!` lines), `prodigal` for the Prodigal file, and `generic` for the rest.

## Results

| file | bytes | lines | parse s | split s | peak MB | notes |
|---|---|---|---|---|---|---|
| `corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3` (*Streptomyces coelicolor* A3(2)) | 4691954 | 15852 | 0.037 | 8.916 | 269 | ncbi profile; parse peak 55 MB; rebuilt byte for byte; feature model refused (dataset-invalid: duplicate `feature_id` on multi-row CDS) |
| `corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_functional_annotation.gff` | 1386145 | 4439 | 0.010 | 1.919 | 166 | generic profile; parse peak 31 MB; rebuilt byte for byte; feature model refused (product-cardinality) |
| `corpus/sources/ncbi-refseq/NC_014649.1_2026-10-30.gff3` (mimivirus) | 1301423 | 6964 | 0.011 | 3.759 | 174 | ncbi profile; parse peak 33 MB; rebuilt byte for byte; feature model refused (dataset-invalid: duplicate `feature_id` on spliced CDS) |
| `corpus/sources/prokka/Mycoplasma_genitalium_G37_NC_000908.2_prokka-1.15.6.gff` | 707621 | 10234 | 0.010 | 0.919 | 166 | generic profile; parse peak 29 MB; rebuilt byte for byte |
| `corpus/sources/bakta/Mycoplasma_genitalium_G37_NC_000908.2_bakta-1.12.2.gff3` | 687506 | 10244 | 0.010 | 0.620 | 153 | generic profile; parse peak 29 MB; rebuilt byte for byte; feature model refused (circular-location) |
| `corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_prodigal.gff` | 452840 | 4167 | 0.006 | 3.841 | 175 | prodigal profile; parse peak 27 MB; rebuilt byte for byte |
| `corpus/sources/ensembl/Saccharomyces_cerevisiae.R64-1-1.63.chromosome.Mito.gff3` | 44006 | 320 | 0.001 | 0.219 | 139 | generic profile; parse peak 22 MB; rebuilt byte for byte; feature model refused (circular-location) |
| `corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3` (phage MS2) | 2961 | 17 | 0.000 | 0.146 | 143 | ncbi profile; parse peak 22 MB; rebuilt byte for byte |

Where the split time goes, as the prototype reports its own stages (seconds, median of 3):

| file | parse | validate rows | feature model import | write DuckDB | rebuild |
|---|---|---|---|---|---|
| `NC_003888.3_2026-09-21.gff3` | 0.033 | 0.664 | 3.139 | 5.027 | 0.019 |
| `Ga0423362_functional_annotation.gff` | 0.009 | 0.239 | 0.183 | 1.474 | 0.014 |
| `NC_014649.1_2026-10-30.gff3` | 0.011 | 0.332 | 1.130 | 2.261 | 0.014 |
| `Mycoplasma_genitalium_G37_NC_000908.2_prokka-1.15.6.gff` | 0.010 | 0.096 | 0.359 | 0.440 | 0.015 |
| `Mycoplasma_genitalium_G37_NC_000908.2_bakta-1.12.2.gff3` | 0.010 | 0.097 | 0.284 | 0.213 | 0.015 |
| `Ga0423362_prodigal.gff` | 0.005 | 0.238 | 0.448 | 3.127 | 0.014 |
| `Saccharomyces_cerevisiae.R64-1-1.63.chromosome.Mito.gff3` | 0.001 | 0.073 | 0.018 | 0.113 | 0.013 |
| `NC_001417.2_2026-10-30.gff3` | 0.000 | 0.063 | 0.035 | 0.035 | 0.012 |

Parsing is under 1% of the split time on every file. Writing DuckDB and the feature model import take most of it.

For comparison, the existing linkml-map round trip, `scripts/img_functional_map.py roundtrip`, on `Ga0423362_functional_annotation.gff` took 3.063 s (median of 3) with a peak of 187 MB, and the file came back byte for byte. The split prototype took 1.919 s on the same file.

## Not measured here

The Phytozome TAIR10 `gene_exons` GFF3 (532,682 rows) needs a JGI login, and TAIR's terms keep it out of this repo, so it is not in this table. The body of https://github.com/turbomam/feature-table-corpus/issues/185 records its earlier timings on the same kind of machine: 23.5 s to check format (2026-09-25) and 211 s for a full mapping round trip (2026-09-28).

## Reproduce

```bash
just benchmark-gff-split --roundtrip-img-functional --json local/splitter-baseline/baseline-2026-11-06.json
```

That recipe runs `uv run --python 3.11 --with-requirements requirements-conversion.txt --with-requirements requirements-mapping.txt --with duckdb python3 scripts/benchmark_gff_split.py`, prints the machine and the first table, and writes every run, with the per-stage seconds, to the JSON file. Pass `--case PATH PROFILE` (repeatable) to time other files and `--repeats N` to change the count.

To split one file and see the prototype's summary:

```bash
just split-gff corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3 ncbi
```

The database is written to `local/split-gff/NC_001417.2_2026-10-30.gff3.duckdb`. A third argument sets `--reference-context`.
