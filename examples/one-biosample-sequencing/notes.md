# One biosample's full sequencing, harmonized against schema/ber_feature_model.yaml

Built 2026-09-18. Replaces an earlier worked example (`examples/one-workflow-run/`, removed) that
turned out to be a poor choice: it was built on a run selected only because two of its files
happened to already be vendored in `corpus.yaml`, and those had been picked by that file's own
stated method, "the smallest real file of its kind out of roughly 600 sampled." A 2-contig,
813-bp assembly is not representative of a real metagenome, and using it made every design
decision look more trivial than it is. Mark caught this by asking whether it was small because the
underlying biosample was poor quality; it wasn't, the biosample and study are entirely legitimate,
the file was just a deliberately minimal example picked for a different purpose.

## Source

Data generation `nmdc:omprc-11-2t8ft192`, "Montane desert soil microbial communities from Mustang
Region, Nepal - Schmidt56.soil.Nepal.3", PI Janet Jansson (PNNL), GOLD sequencing project
`Gp0452617`, NCBI BioProject `PRJEB42019`. Picked this time by filtering the NMDC public API
directly for a moderate file-size band (`file_size_bytes` between 3,000 and 15,000 for Annotation
Enzyme Commission files) rather than sampling blindly, after an earlier attempt at a 75th-percentile
pick landed on a 27MB file. This run was the only size-appropriate candidate found with an actual,
non-empty CRISPR array, which mattered enough to Mark to be worth the extra searching.

## One sequencing, seven workflow executions

Querying the NMDC public API for every DataObject whose URL contains this data generation's id
(not scoped to one workflow) surfaced the complete chain: read QC (`wfrqc-11-y4x3c425.1`), assembly
(`wfmgas-11-19jh9v28.1`), annotation (`wfmgan-11-5xxrm214.1` and `.2`, two processing versions),
read-based taxonomic classification (`wfrbt-11-k9jkd382.1`), and MAG binning
(`wfmag-11-n2d0ma07.2` and `.3`). 80 DataObjects total; 76 fetched (about 4.7MB), 4 skipped by
size and recorded by metadata only: a 1.18GB assembly coverage BAM, a 1.03GB Centrifuge
classification, an 804MB Kraken2 classification, and a 1.13GB filtered-reads FASTQ. None of the
four skipped files are feature tables.

**Of the seven workflow types, exactly one produces feature-table content**: metagenome annotation
(`wfmgan`). Assembly (`wfmgas`) is upstream and adjacent, it produces the `Contig` this schema's
features sit on, plus the AGP format (a tabular, positional description of how contigs join into
scaffolds, worth noting as GFF-adjacent but not covered here). Read QC, read-based taxonomy, and
MAG binning produce read-level, taxon-level, and bin-level data respectively, none of it shaped
like a feature table. This matters for anyone extending fetch tooling in this repo: point it at
`wfmgan` DataObjects, not at the other five workflow types.

**A workflow execution id does not name both a Contig and its Features.** `seqid` values in every
GFF file from the annotation workflow reference the ASSEMBLY workflow's id
(`nmdc:wfmgas-11-19jh9v28.1_scf_N_cM`), not the annotation workflow's own id
(`wfmgan-11-5xxrm214.2`). A Contig and the Features on it come from two different workflow
executions. `schema/ber_feature_model.yaml`'s `predicted_by` slot now says this explicitly.

**This run has two annotation versions, `.1` and `.2`, and they are not identical.** Their Product
Names outputs differ by a few bytes (104,223 vs 104,195). This example uses only `.2`, so as not to
mix two provenance records under one label.

## What is represented here, and why nothing is duplicated

Three contigs, fifteen features. Not the full ~1,121 genes this run actually has; a representative
slice chosen to exercise every part of the schema with real content, which a full harmonization
would not make any clearer.

- **`scf_1_c1_104_853`**: a gene where Prodigal and GeneMark called the identical 104-853 boundary
  independently. Recorded once, from Prodigal (the roll-up's choice), with GeneMark's agreement
  noted as an attribute rather than a second, redundant Feature row, since the coordinates are
  identical, not a competing claim. Carries six real functional-evidence hits: COG, CATH-FunFam,
  Pfam, SUPERFAMILY, and a combined KO/EC hit.
- **The KO/EC hit is one row, not three.** `ec.tsv`, `ko.tsv`, and `KO_EC Annotation GFF` all
  report the same 252 underlying `lastal` alignments for this run; `ec.tsv` (88 rows) is a filtered
  subset of the same 252 hits `ko.tsv` and `ko_ec.gff` both carry in full. `ko_ec.gff` is the
  richest of the three (both labels combined, e.g. `KO:K00059__EC:1.1.1.100`, plus full evidence),
  so it's the only one used here. Confirmed by checking three EC/KO row pairs by hand: identical
  coordinates, e-value, and every numeric field in each pair.
- **`scf_2_c1_3_866` vs. `scf_2_c1_3_740`**: a genuine Prodigal/GeneMark disagreement. Same start,
  different end (866 vs. 740), so these are two different boundary claims for one locus, not a
  duplicate. Both are kept, `is_selected` distinguishes them.
- **`scf_1_c1_3_65`**: the case that complicated `is_selected` further. This Prodigal call has no
  competing GeneMark call at all, and is still absent from Structural Annotation GFF and from
  Annotation Amino Acid FASTA. `is_selected=false` here cannot mean "lost to a competitor"; it
  means something filtered this call out regardless. Flagged as an open question in the schema.
- **`scf_2_c1_887_1104`**: an RFAM/INFERNAL ncRNA hit (a Group II catalytic intron), included
  directly in Structural Annotation GFF the same way Prodigal's CDS calls are, confirming the
  roll-up duplicates non-CDS structural calls too, not just gene calls. Kept once, sourced from
  `rfam.gff`. Notable for `type`: this one uses the generic term `misc_feature` rather than a bare
  accession, the opposite problem from the Pfam/COG/CATH pattern documented elsewhere in this
  repository, here the specific identity is in `attributes` (`model`, `accession`) and the
  positional column holds a placeholder.
- **The CRISPR array, `scf_344_c1_76_183`**, plus its three `repeat_unit` children linked by
  `parent`. This is the run's only real, populated example of the `Crispr Terms` /
  `CRT Annotation GFF` pair added to `corpus.yaml` on 2026-09-17; the corpus's own vendored
  examples of these two types are empty (no hits) in every file sampled for them so far.

**None of these three contigs are MAG scaffolds.** Confirmed 2026-09-18 by unzipping both MAG
binning outputs for this biosample (`nmdc:wfmag-11-n2d0ma07.2` and `.3`): every one of the four
bin archives (`hqmq_bin.zip` and `lq_bin.zip`, both versions) contains only an empty marker file,
`no_hqmq_mags.txt` or `no_lq_mags.txt`. This assembly produced zero MAGs, of either quality
category, in either binning run. `scf_1_c1`, `scf_2_c1`, and `scf_344_c1` are plain metagenome
assembly contigs, never binned into anything. Recorded here because an early description of this
case study (in meeting notes, not in this repository) called them "MAG scaffolds," which this
directly contradicts.

**Not represented, and why:** Product Names duplicates `product`/`product_source` exactly (checked
for both genes here); Gene Phylogeny and Scaffold Lineage are used but folded into the Feature and
Contig they describe rather than kept as separate rows; the tiny gene's absence from Annotation
Amino Acid FASTA is recorded as an absence of `translated_sequence`, not invented.

## Reproducing

```python
# Every DataObject for the whole data generation, any workflow execution:
filter = {"url": {"$regex": "omprc-11-2t8ft192"}}
# https://api.microbiomedata.org/nmdcschema/data_object_set?filter=<url-encoded filter>&max_page_size=200
```

Raw files are not committed here (76 files, ~4.7MB, disproportionate for one worked example); they
were downloaded into this worktree's gitignored `local/` directory, one subdirectory per workflow
execution id, and are reproducible from the query above plus the DataObject urls cited inline in
`harmonized.yaml`.

## Status

Draft. Not reviewed by Sierra Moxon, AJ Ireland, or anyone else on the BER data modeling team.
