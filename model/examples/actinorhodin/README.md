# The actinorhodin example as a Dataset and as Parquet

The files here are the actinorhodin RefSeq excerpt,
[`corpus/derived-examples/actinorhodin.gff3`](../../../corpus/derived-examples/actinorhodin.gff3),
converted to the BER feature model and exported to Parquet. They are the same bytes as the
Parquet files used for the GenomeFeatures review on 2026-10-02, two of which were loaded into
BERDL (the KBase lakehouse) as `mamillerpa.feature_model_demo.features` and `.contigs`.

| file | what it is | rows |
|---|---|---|
| [`dataset.json`](dataset.json) | The `Dataset`, validated against the model | 1 contig, 44 features |
| [`parquet/features.parquet`](parquet/features.parquet) | One row per feature: 22 genes and their 22 CDS | 44 |
| [`parquet/contigs.parquet`](parquet/contigs.parquet) | The chromosome NC_003888.3 | 1 |
| [`parquet/contig_collections.parquet`](parquet/contig_collections.parquet) | Empty; the excerpt names no assembly or genome | 0 |

The source is NCBI RefSeq data, freely available under
https://www.ncbi.nlm.nih.gov/home/about/policies/ (see its entry in
[`corpus/index.yaml`](../../../corpus/index.yaml)). It is NCBI's annotation of genes
SCO5071 to SCO5092 of *Streptomyces coelicolor* A3(2), not an analysis made here.

## Reproducing and checking

The [actinorhodin walkthrough](../../../docs/actinorhodin-walkthrough.md) explains each step,
from the source GFF3 to the BERDL tables.

```sh
just actinorhodin-parquet   # regenerate these files
just actinorhodin-check     # fail unless every file here reproduces
```

Both run [`scripts/actinorhodin_parquet.py`](../../../scripts/actinorhodin_parquet.py), which
imports the excerpt with `just conversion-import` (profile `gff3-contig/4.0.0`, reference
`refseq:NC_003888.3`, metadata profile `ncbi`) and exports with `just lakehouse-export`, so the
pinned toolchains in `requirements-conversion.txt` and `requirements-lakehouse.txt` apply.
The check requires `dataset.json` to match byte for byte and each Parquet file to have the same
schema, metadata included, and the same rows in the same order. It does not compare Parquet bytes:
on 2026-10-02, with the same DuckDB build and the same rows, `features.parquet` came out 11,305
bytes on macOS, 11,294 bytes in a Linux container, and different again in GitHub Actions, because a few column chunks compressed to slightly
different sizes. The committed files are the macOS bytes, the ones loaded into BERDL.
`just check` includes `actinorhodin-check`, so a change to the model, a converter or the export
that changes these files fails CI until they are regenerated and committed.

Read the Parquet with DuckDB:

```sql
SELECT seqid, type, count(*) AS n
FROM 'model/examples/actinorhodin/parquet/features.parquet'
GROUP BY seqid, type ORDER BY n DESC, type;
```
