# Which workflows produce feature-table content

Established 2026-09-18 by fetching every DataObject for one real biosample's full sequencing
(data generation `nmdc:omprc-11-2t8ft192`) and reading what each workflow execution actually
produced, rather than assuming from workflow names. See
`examples/one-biosample-sequencing/notes.md` for the full inventory this is based on.

## Five workflow types across seven executions

This sequencing has seven workflow executions across five distinct types (two versions each
of annotation and MAG binning). Of these types,
exactly one produces feature-table content in the sense this repository cares about, one row per
sequence feature.

| Workflow type | Example id | Produces | Feature-table content? |
|---|---|---|---|
| Read QC / filtering | `wfrqc-*` | Filtered reads, QC statistics | No. No positional structure below the whole-read level. |
| Metagenome assembly | `wfmgas-*` | Contigs, scaffolds, an AGP file, per-contig coverage stats | No, but adjacent. Produces the `Contig` a feature table's features sit on. |
| **Metagenome annotation** | **`wfmgan-*`** | **The 17 vendored feature-bearing types: 14 GFF and 3 non-GFF** | **Yes. This is the only source in the sampled workflow chain.** |
| Read-based taxonomic classification | `wfrbt-*` | Kraken2, Centrifuge, GOTTCHA2 classification and reports | No. One row per read or per taxon, bypasses assembly and annotation entirely. |
| MAG binning | `wfmag-*` | CheckM quality stats, GTDB-Tk taxonomy, bin compression files | No. One row per genome bin, a different granularity from a feature table. |

**Practical consequence for this repository:** fetch tooling, corpus entries, and the schema in
`schema/ber_feature_model.yaml` should target `wfmgan` DataObjects for `Feature` instances and
`wfmgas` DataObjects (specifically `Assembly Contigs`) for `Contig` instances. The other three
workflow types are a different data category, not an incomplete version of this one, and adding
them to this corpus would not extend its scope so much as change what it is about.

## A workflow execution id does not name both a Contig and its Features

This is easy to get wrong from the naming convention alone. Every `seqid` in a `wfmgan` GFF file
references the assembly workflow's id, not the annotation workflow's own id: for example, features
in `nmdc:wfmgan-11-5xxrm214.2_prodigal.gff` are all `seqid`-tagged
`nmdc:wfmgas-11-19jh9v28.1_scf_N_cM`, an entirely different workflow execution. A `Contig` and the
`Feature` rows on it come from two different pipeline stages, connected only by the fact that one
ran against the other's output. `schema/ber_feature_model.yaml`'s `generated_by` slot records
the producer separately on each Contig and Feature; `source_files` also lists contributing
artifacts, including sidecars from other workflows. Anything that parses a `Feature.seqid` to find the
producing annotation workflow there will be wrong.

## AGP: a related, uncovered format

The assembly workflow also produces an `Assembly AGP` file, a tabular, positional format (per the
NCBI AGP specification) describing how contigs are ordered, oriented, and gapped within a
scaffold. It is structurally GFF-adjacent, tabular and positional, but describes assembly
structure rather than a biological feature, and nothing in this repository's schema or corpus
covers it as of 2026-09-18. Noted here so it isn't silently forgotten if the model's scope ever
grows to include assembly-level structure.

Related: [non-GFF annotation tables](columns-and-discretion.md#5-feature-sources-beyond-gff-added-2026-09-17)
and the [worked biosample's workflow inventory](../examples/one-biosample-sequencing/notes.md).
