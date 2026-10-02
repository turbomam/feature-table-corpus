# The actinorhodin example, from source file to BERDL table

One small real example taken through every form the model's data takes: the source GFF3, a
Dataset that conforms to the model, Parquet, and a table in BERDL (the KBase lakehouse). It was
used for the GenomeFeatures review on 2026-10-02. Each command below was run on 2026-10-02 from
main at 4aaca94 (the v0.1.0 tag) and reproduced the reviewed files byte for byte.

## 1. Source: NCBI RefSeq annotation

[`corpus/derived-examples/actinorhodin.gff3`](../corpus/derived-examples/actinorhodin.gff3) is an
excerpt of the RefSeq annotation of the *Streptomyces coelicolor* A3(2) chromosome NC_003888.3,
whose full file is
[`corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3`](../corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3).
It keeps the gene rows with legacy locus tags SCO5071 to SCO5092 and each gene's CDS row: 22 genes
and 22 CDS, positions 5,513,809 to 5,535,091, with the original header and coordinates. Product
names come from NCBI; three of them name actinorhodin genes (ActVA, ActII, ActVB). It is NCBI's
annotation, not an analysis made here, and the excerpt does not claim to match the
biosynthetic gene cluster's boundaries.

## 2. A Dataset that conforms to the model

Import the excerpt with the `gff3-contig` [conversion profile](conversion-profiles.md), then take
the Dataset out of the conversion bundle:

```bash
just conversion-import corpus/derived-examples/actinorhodin.gff3 gff3-contig/4.0.0 \
  refseq:NC_003888.3 local/actinorhodin/bundle.json --metadata-profile ncbi
jq '.dataset' local/actinorhodin/bundle.json > local/actinorhodin/dataset.json
```

The bundle also holds the source records and the mappings that let
`just conversion-export` rebuild the original file. The Dataset has 1 contig and 44 features. One
feature, as JSON:

```json
{
  "feature_id": "gene-SC_RS27515",
  "seqid": "NC_003888.3",
  "source": "RefSeq",
  "type": "gene",
  "start": 5513809,
  "end": 5514249,
  "strand": "-",
  "coordinate_system": "contig",
  "name": "SC_RS27515",
  "attributes": [
    {"key": "ID", "value": "gene-SC_RS27515"},
    {"key": "Name", "value": "SC_RS27515"},
    {"key": "gbkey", "value": "Gene"},
    {"key": "gene_biotype", "value": "protein_coding"},
    {"key": "locus_tag", "value": "SC_RS27515"},
    {"key": "old_locus_tag", "value": "SCO5071"}
  ]
}
```

LinkML reads JSON and YAML alike, so this is also the YAML form of the data.

## 3. Parquet

```bash
just lakehouse-export local/actinorhodin/dataset.json local/actinorhodin/parquet
```

This validates the Dataset, writes `features.parquet` (44 rows), `contigs.parquet` (1 row) and
`contig_collections.parquet` (0 rows), and checks each file's column types, row counts and values
against the validated Dataset. Those checks run in a staging directory, so a failed check writes
nothing to the output directory. A failure later, while the checked files are being linked into
the output directory, can leave that directory and the files already linked; the error names
them. The [Parquet export guide](lakehouse-export.md) describes the checks. Read the files locally with DuckDB:

```sql
SELECT seqid, type, count(*) AS n
FROM 'local/actinorhodin/parquet/features.parquet'
GROUP BY seqid, type ORDER BY n DESC;
-- NC_003888.3  CDS   22
-- NC_003888.3  gene  22
```

For order and distance queries on the same excerpt, see the [query examples](query-requirements.md)
and the [BGC exercise](../analyses/bgc-query/README.md).

## 4. BERDL tables

The two Parquet files with rows, `features.parquet` and `contigs.parquet`, were loaded; the empty
`contig_collections.parquet` was not. They were loaded on 2026-10-02 into a personal BERDL namespace,
`mamillerpa.feature_model_demo`, as `features` (44 rows) and `contigs` (1 row). The load script
ran on the BERDL JupyterHub and is not in this repository. Two things it had to handle:

- Columns that are null in every row (`stable_identifiers`, `source_files`, `is_selected`,
  `is_representative`) lose their type when written through pandas, and Iceberg refuses them.
  Pass the Parquet file's own schema when writing.
- NMDC data stays out of personal namespaces. Loading the model's tables into an `nmdc`
  namespace is https://github.com/microbiomedata/nmdc-lakehouse/issues/388.

Query the tables from a JupyterHub terminal with Harlequin or any Trino client. The editor needs a
full statement; a bare table name is a syntax error.

```sql
SELECT seqid, type, count(*) AS n
FROM mamillerpa.feature_model_demo.features
GROUP BY seqid, type
ORDER BY n DESC
LIMIT 5
```

The tables in BERDL are not validated against the model after loading; only the Dataset they were
exported from is.
