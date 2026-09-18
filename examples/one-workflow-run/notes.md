# One real workflow run, harmonized against schema/ber_feature_model.yaml

Built 2026-09-18, for the BRIDGE GFF schematization check-in the same day. Source run:
`nmdc:wfmgan-11-ghk5e506.1`, a metagenome annotation workflow execution under data generation
`nmdc:omprc-11-4e682h13`. Chosen because two of its outputs (CATH FunFam and COG Annotation GFF)
were already vendored in `corpus.yaml` as `nmdc-cath-funfam` and `nmdc-cog`, so this run's
identity was already known rather than picked fresh.

All 25 DataObjects this run produced were found via the NMDC public API (`url` matching
`wfmgan-11-ghk5e506` for `nmdc:omprc-11-4e682h13`) and fetched. They sit alongside this file.
Nothing in this directory was inferred or assumed; every claim below was read from the actual
file content.

## Why some findings appear once here despite existing in two source files

**Structural Annotation GFF vs. the individual gene-caller GFFs.** Both Prodigal and GeneMark
ran and both produced calls for the same two loci. `structural_annotation.gff` (the pipeline's
roll-up) contains only the Prodigal calls, byte-identical to `prodigal.gff`'s two rows. GeneMark's
competing calls for the same loci (different coordinates: 2-406 vs 2-478, 3-278 vs 3-332) exist
only in `genemark.gff` and nowhere else. So harmonized.yaml keeps both callers' rows, marked with
`is_selected`, rather than including `structural_annotation.gff` as a third, separate source,
which would have duplicated the two Prodigal rows a second time.

**Functional Annotation GFF vs. the per-database hit GFFs.** The roll-up attaches bare accession
tags to each CDS (`pfam=PF05598;cog=COG3666;cath_funfam=3.30.240.20` on gene 01, and
`pfam=PF14104;superfamily=53254` on gene 02). The per-database files (`pfam.gff`, `cog.gff`,
`cath_funfam.gff`, `supfam.gff`) report the identical hits with full evidence: e-value, bitscore,
alignment coordinates, HMM model coordinates. harmonized.yaml keeps the per-database rows, linked
to their gene via `parent`, and drops the roll-up's bare tags, since they carry strictly less
information about the same fact.

**Product Names vs. Functional Annotation GFF's own attributes.** `product_names.tsv` reports
exactly the same two values, `transposase / COG3666` and `hypothetical protein / Hypo-rule
applied`, as the `product=` and `product_source=` attributes already on the roll-up's CDS lines.
Read from `product_names.tsv` here only to confirm the duplication; the actual `product` and
`product_source` slots in harmonized.yaml are sourced from the roll-up.

**Not duplicated, kept as-is:** `gene_phylogeny.tsv` (per-gene lineage placement) and
`scaffold_lineage.tsv` (per-contig lineage) report at different levels and were not found
anywhere else, so both are represented, on the Feature and Contig respectively.
`contig_names_mapping.tsv` is an identifier crosswalk (assembly-stage contig name to
annotation-stage contig name), not a finding, and isn't represented as a Feature or Contig at all.
`stats.tsv` is a run-level QC summary computable from the features themselves and isn't
represented either.

## A finding that shaped the schema, not just this data

Pfam hit `nmdc:wfmgan-11-ghk5e506.1_01_2_478_61_136` reports `start=61, end=136` on a CDS whose
translated protein (`proteins.faa`) is 159 residues long. `end - start + 1 = 76`, which matches
the hit's own `alignment_length=76` attribute exactly, in amino acids. The parent CDS's own
`start=2, end=478` is a contig position. Two different coordinate systems, same `start`/`end`
slot names, no field anywhere says which is which. That is why `coordinate_system` exists on
`Feature`; without it, a wide table mixing gene-level and hit-level rows would silently invite
someone to compare a protein-relative coordinate against a contig-relative one.

## Confirmed real absences, not gaps

`ec.tsv`, `ko.tsv`, `crt.crisprs`, `crt.gff`, `rfam.gff`, `smart.gff`, `tigrfam.gff`, and
`trna.gff` are all genuinely 0 bytes for this run: this particular metagenome fragment had no
CRISPR arrays, no RFAM ncRNA hits, and no SMART, TIGRFAM, KO, or EC hits. Confirmed by fetching
and checking every one of them, not inferred from `harmonized.yaml`'s silence. A run with hits in
those categories would need more example rows than this one provides; this document is a worked
case for the de-duplication logic and the schema's shape, not a claim that it exercises every
field the schema defines.

## Status

Draft. Not reviewed by Sierra Moxon, AJ Ireland, or anyone else on the BER data modeling team.
`schema/ber_feature_model.yaml` and this example both live in `turbomam/feature-table-corpus`
because `ber-data/gff-schema` does not exist yet, per the 2026-09-11 kickoff notes
(`project-ber-gff-feature-model` in Claude memory).
