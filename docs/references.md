# Key references

A short, ranked list of links for someone new to the GFF and sequence feature work. Read the first group before anything else. Each entry says what the resource is and why it is worth reading. How this repository uses each one is in the specifications table in [gff-validation-start-here.md](gff-validation-start-here.md#specifications-and-reference-implementations), and the longer inventory of earlier work is in [background.md](background.md).

Every link on this page returned HTTP 200 on 2026-11-20, except where a note says otherwise. Last-push dates were read from the GitHub API on the same day.

## Read first

1. <https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md>
   The GFF3 specification from the Sequence Ontology group. Everything else on this page is measured against it.
2. <https://github.com/cmdcolin/oddgenes>
   A curated list of papers on gene structures that break common assumptions, such as ribosomal frameshifts and trans-splicing across strands. Drew Doering suggested it in the BRIDGE #bridge-gff Slack channel on 2026-10-16.
3. <https://github.com/BioJulia/BioFmtSpecimens>
   Bioinformatics files collected from real use by the BioJulia maintainers, useful as test input. Drew suggested it in the same message.
4. <https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/file-formats/annotation-files/about-ncbi-gff3/>
   NCBI's GFF3 conventions, including its `#!` header lines.
5. <https://github.com/NAL-i5K/AgBioData_GFF3_recommendation>
   The AgBioData community's GFF3 recommendations, published as <https://arxiv.org/abs/2202.07782>. It explains why files from different producers model the same data in different ways, and why CDS phase is often misread.
6. <https://github.com/daler/gffutils>
   A Python library that loads GFF and GTF into SQLite tables that mirror the format. It is not a validator.
7. <https://github.com/genometools/genometools> and <https://github.com/NAL-i5K/GFF3toolkit>
   Two established GFF3 validators: `gt gff3validator` in GenomeTools and `gff3_QC` in GFF3toolkit.
8. Current schema work elsewhere:
   - <https://github.com/doe-bridge/bridge-central-schema/pull/5> adds the BER feature model to the BRIDGE central schema as an imported module (open on 2026-11-20).
   - <https://github.com/kbase/cdm-data-loaders/blob/develop/src/cdm_data_loaders/schemas/gff/gff.schema.json> is the GFF JSON Schema in KBase's data loaders. Its `required` list misspells `seqid` as `sequid` (<https://github.com/kbase/cdm-data-loaders/issues/385>).

## Useful context

- <https://agat.readthedocs.io/en/latest/gxf.html>
  AGAT's account of the eleven named GFF and GTF variants and where each came from.
- <https://www.insdc.org/submitting-standards/feature-table/>
  The INSDC Feature Table Definition, shared by GenBank, ENA and DDBJ.
- <https://github.com/enasequence/gff3tools>
  ENA's validator and converter for the draft INSDC GFF3 specification.
- <https://github.com/NBISweden/AGAT>
  The broadest GFF and GTF toolkit. It checks and repairs files as it reads them. It is licensed GPL-3.0.
- <https://github.com/dathere/qsv>
  A command-line tool for tabular files that can check columns against a JSON Schema and set bad rows aside. @ialarmedalien suggested it in the BRIDGE #bridge-gff Slack channel on 2026-10-16 for the first eight GFF columns. It cannot check links between rows, such as `Parent`. <https://github.com/turbomam/feature-table-corpus/issues/200> tracks benchmarking it here.
- <https://github.com/biodatamodels/gff-schema>, <https://kbase.github.io/cdm-schema/Feature/> and <https://laceysanderson.github.io/chado-docs/sequence/tables/feature.html>
  Earlier models of a sequence feature: a draft LinkML GFF3 schema, the KBase CDM Feature class, and Chado. [model-comparison.md](model-comparison.md) compares them.

## Older formats

- <http://gmod.org/wiki/GFF2>
  GFF2, which is deprecated. Older tools and Chado still consume it.
- <http://mblab.wustl.edu/GTF22.html>
  GTF 2.2.

## Left off this page

These were considered on 2026-11-20 and left off, so the choice is recorded:

- <https://www.ncbi.nlm.nih.gov/genbank/feature_table/> mostly repeats the INSDC page above.
- <https://github.com/tao-bioinfo/gff3sort> only sorts files for tabix indexing, and its last push was 2020-06-27.
- <https://github.com/chapmanb/bcbb> holds the Biopython GFF parser in one directory of a general-purpose repository.
- <https://bioconductor.org/packages/release/bioc/html/rtracklayer.html> is an R package that nothing in this work has used.
- <https://genometools.org/tools/gt_gff3validator.html>, the GenomeTools manual page for `gt gff3validator`, did not respond on 2026-11-20. The same page is in the GenomeTools repository above, under `www/genometools.org/htdocs/tools/`.
