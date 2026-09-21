# A real gene with multiple Pfams

This example uses annotation `nmdc:wfmgan-11-5xxrm214.2`, the same execution as
[the larger worked example](../one-biosample-sequencing/notes.md). It contains one
contig, the CDS `nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091`, and its three Pfam hits:

| Pfam | Source name | Protein interval (1-based, inclusive) |
|---|---|---|
| PF13358 | DDE_3 | 168–312 |
| PF13592 | HTH_33 | 95–154 |
| PF13518 | HTH_28 | 17–70 |

These are source records, not synthetic hits. The CDS boundary, score, strand, and phase
come from `prodigal.gff`; its product comes from `functional_annotation.gff`; its translation
comes from `proteins.faa`. Contig length was computed from its `contigs.fna` FASTA record.
Pfam source IDs, intervals, scores, and attributes come from `pfam.gff`, with its gene-valued
column 1 represented as `parent` and the CDS's contig as `seqid`. Each record cites the full
source URLs; [the manifest](../source-artifacts.yaml) supplies DataObject IDs and checksums.
Sources are NMDC public data under [CC BY 4.0](https://microbiomedata.org/nmdc-data-use-policy/).

Reproduce the selection by fetching those URLs, checking their MD5s, and selecting the
FASTA contig and CDS IDs above, then every `pfam.gff` row whose first column is that CDS ID.
All source attributes except ID (promoted to `feature_id`) are retained on the three hits.

```sh
just build-duckdb examples/multiple-pfams/harmonized.yaml local/build/multiple-pfams.duckdb
just query-duckdb local/build/multiple-pfams.duckdb
uv run --with duckdb python scripts/query_duckdb.py local/build/multiple-pfams.duckdb pfams PF13358 PF13592
```

The first query returns this gene with three distinct Pfams. The second returns it with
the two requested accessions. The earlier scientific pair PF04183/PF06276 has no match
in this slice; the test asserts an empty result rather than inventing supporting data.

The larger worked example is a negative control: five different evidence databases on one
CDS, or three repeats on a CRISPR array, must not count as multiple Pfams on one gene.
