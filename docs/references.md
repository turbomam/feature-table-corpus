# Key references

A short, ranked list of links for someone new to the GFF and sequence feature work. Read the first group before anything else. The longer inventories are in [background.md](background.md) and in the specifications table in [gff-validation-start-here.md](gff-validation-start-here.md#specifications-and-reference-implementations).

Every link on this page returned HTTP 200 on 2026-11-20, except where a note says otherwise. Last-push dates were read from the GitHub API on the same day.

## Read first

1. https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md
   The GFF3 specification from the Sequence Ontology group. The `gff3-contig` conversion profile enforces its rules, and everything else on this page is measured against it.
2. https://github.com/cmdcolin/oddgenes
   A curated list of papers on gene structures that break common assumptions, such as ribosomal frameshifts and trans-splicing across strands. Drew Doering suggested it in the BRIDGE #bridge-gff Slack channel on 2026-10-16. [acceptance-tests.md](acceptance-tests.md#unusual-gene-structures) maps its cases to tests of the model.
3. https://github.com/BioJulia/BioFmtSpecimens
   Bioinformatics files collected from real use by the BioJulia maintainers. Drew suggested it in the same message. Running its GFF3 files through GenomeTools on 2026-10-16 showed that `gff3-contig` accepted files with no `##gff-version 3` line.
4. https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/file-formats/annotation-files/about-ncbi-gff3/
   NCBI's GFF3 conventions. The NCBI RefSeq files in the corpus follow them, including the `#!` header lines.
5. https://github.com/NAL-i5K/AgBioData_GFF3_recommendation
   The AgBioData community's GFF3 recommendations, published as https://arxiv.org/abs/2202.07782. It explains why files from different producers model the same data in different ways, and why CDS phase is often misread.
6. https://github.com/daler/gffutils
   A Python library that loads GFF and GTF into SQLite tables that mirror the format. It is not a validator. Its SQLite layout is a comparison point for the DuckDB layout here.
7. https://github.com/genometools/genometools and https://github.com/NAL-i5K/GFF3toolkit
   The two validators this repository runs on every retained GFF3 file: `gt gff3validator` from GenomeTools 1.6.6 and `gff3_QC` from GFF3toolkit 2.1.0. Their verdicts are recorded in `model/validation/`, and CI fails if one changes. Details are in [analyses/format-validation/README.md](../analyses/format-validation/README.md).
8. Current schema work elsewhere:
   - https://github.com/doe-bridge/bridge-central-schema/pull/5 adds the BER feature model to the BRIDGE central schema as an imported module (open on 2026-11-20).
   - https://github.com/kbase/cdm-data-loaders/blob/main/src/cdm_data_loaders/schemas/gff/gff.schema.json is the GFF JSON Schema in KBase's data loaders. Its `required` list misspells `seqid` as `sequid` (https://github.com/kbase/cdm-data-loaders/issues/385).

## Useful context

- https://agat.readthedocs.io/en/latest/gxf.html
  AGAT's account of the eleven named GFF and GTF variants and where each came from.
- https://www.insdc.org/submitting-standards/feature-table/
  The INSDC Feature Table Definition, shared by GenBank, ENA and DDBJ. The `insdc-locations` conversion profile follows it.
- https://github.com/enasequence/gff3tools
  ENA's validator and converter for the draft INSDC GFF3 specification. This repository has not run it yet. It is a comparison point in https://github.com/turbomam/feature-table-corpus/issues/185.
- https://github.com/NBISweden/AGAT
  The broadest GFF and GTF toolkit. It checks and repairs files as it reads them. It is GPL-3.0, which is why its test suite is linked from here and not copied ([background.md](background.md#approaches-considered-and-rejected)).
- https://github.com/dathere/qsv
  A command-line tool for tabular files that can check columns against a JSON Schema and set bad rows aside. AJ suggested it in #bridge-gff on 2026-10-16 for the first eight GFF columns. It cannot check links between rows, such as `Parent`.
- https://github.com/biodatamodels/gff-schema, https://kbase.github.io/cdm-schema/Feature/ and https://laceysanderson.github.io/chado-docs/sequence/tables/feature.html
  Earlier models of a sequence feature: a draft LinkML GFF3 schema, the KBase CDM Feature class, and Chado. They are compared in [model-comparison.md](model-comparison.md).

## Older formats

- http://gmod.org/wiki/GFF2
  GFF2, which is deprecated. Older tools and Chado still consume it.
- http://mblab.wustl.edu/GTF22.html
  GTF 2.2. The corpus has NCBI GTF files, but no conversion profile reads them yet.

## Left off this page

These were considered on 2026-11-20 and left off, so the choice is recorded:

- https://www.ncbi.nlm.nih.gov/genbank/feature_table/ mostly repeats the INSDC page above.
- https://github.com/tao-bioinfo/gff3sort only sorts files for tabix indexing, and its last push was 2020-06-27.
- https://github.com/chapmanb/bcbb holds the Biopython GFF parser in one directory of a general-purpose repository.
- https://bioconductor.org/packages/release/bioc/html/rtracklayer.html is an R package that nothing in this work has used.
- https://genometools.org/tools/gt_gff3validator.html, the GenomeTools web validator, did not respond on 2026-11-20. The GenomeTools repository above is the stable link.
