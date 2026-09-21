# Reading across feature-table formats

Search and verification date: **2026-09-21**. This is an annotated selection, not
a systematic review or a claim that the newest paper covers every format.
Dates below are publication dates or explicit specification versions, not search
engine crawl dates. A recent package release does not date every paragraph of its manual.

The previous [prior-art inventory](prior-art.md) concentrates on GFF-family
models and normalization tools. For a broader view, read across the perspectives
below. A format specification establishes its contract; it does not independently
demonstrate interoperability, adoption, or superiority. Likewise, a tool author's
evaluation is useful evidence but needs that attribution.

## Papers and community assessments

| Source and date | Why read it | Perspective and limits |
|---|---|---|
| Dimonaco, Clare & Vickers, [Genome assemblies and annotations are not static and need support for tracking their evolution](https://pubmed.ncbi.nlm.nih.gov/42398073/), *Briefings in Bioinformatics*, **2026-07-03**, [DOI](https://doi.org/10.1093/bib/bbag357) | Recent review of assembly/annotation formats, provenance, changes between releases, and requirements for machine-readable history. Particularly relevant to source-document identity. | A critical review advocating better version-aware infrastructure. It is not a neutral experimental comparison or a complete catalogue of feature-table syntaxes. Its proposed direction remains an argument to evaluate. |
| Schäfer & Yang, [A comprehensive benchmark of tools for efficient genomic interval querying](https://academic.oup.com/bib/article/26/4/bbaf379/8216879), *Briefings in Bioinformatics*, **2025-07-29** | Empirical comparison of interval-query tools; Table 1 distinguishes supported formats, sorting, indexing, and compression. Useful for turning coordinate-query requirements into measurements. | Compares multiple tools using the authors' segmeter framework. Measures query behavior/performance, not faithful conversion of attributes, hierarchies, comments, or whole documents. It cannot identify the best semantic feature model. |
| Xue, Khoroshevskyi, Gomez & Sheffield, [Opportunities and challenges in sharing and reusing genomic interval data](https://www.frontiersin.org/journals/genetics/articles/10.3389/fgene.2023.1155809/full), *Frontiers in Genetics*, **2023-03-20** | A BED/interval-data perspective: reuse depends on reference-genome identification, metadata, standardization, and data quality. Broadens a discussion otherwise dominated by GFF and gene models. | Explicitly an **Opinion** article, from researchers working on genomic data infrastructure. Useful problem analysis, not an independent format benchmark. |
| Earth BioGenome Project annotation subcommittee, [Report on Annotation Standards](https://www.earthbiogenome.org/report-on-annotation-standards), **version 1.0, June 2023** | Cross-institution expectations for feature coverage, evidence, annotation-set identifiers, assembly association, provenance, and quality. It explicitly recognizes variation among GFF3 producers. | Community guidance with a eukaryotic gene-annotation focus and an explicit preference for GFF3; broader participation does not make it format-neutral. |
| Saha and colleagues, AgBioData, [Recommendations for extending the GFF3 specification for improved interoperability of genomic data](https://arxiv.org/abs/2202.07782), **2022-02-15, v1 preprint** | Concrete curatorial disagreements and proposed conventions for GFF3 fields, functional annotations, and gene models. Good material for interoperability fixtures. | A GFF3 working group's recommendations, including people involved in its ecosystem. This is community criticism from within that ecosystem, not an external comparison. No later journal version was verified in this search. |
| Ejigu & Jung, [Review on the Computational Genome Annotation of Sequences Obtained by Next-Generation Sequencing](https://pmc.ncbi.nlm.nih.gov/articles/PMC7565776/), *Biology* 9:295, **2020-09-18**, [DOI](https://doi.org/10.3390/biology9090295) | Section 5.1 places GFF/GTF alongside GenBank, EMBL, DDBJ, and sequence formats in a broader annotation workflow. Useful orientation outside one format project. | A broad review with a short formats section. Older background, not evidence of current parser compatibility or format prevalence. |

The newest directly relevant critical review found here is the **July 2026**
Dimonaco paper. The **July 2025** interval benchmark is the strongest recent
comparative measurement in this selection, but answers a different question.
Neither is an exhaustive, independent GFF/GTF/BED/INSDC conversion benchmark.

Read the Dimonaco paper with its
[supplementary Table S1](https://pmc-oa-opendata.s3.amazonaws.com/PMC13331350.1/supplementary_file_1_bbag357.pdf).
It compares sequence, annotation, interval, graph, variant, and other representations
from a version-control perspective. The table also includes a toolkit, GFFx, explicitly
labeled as such. Its judgments about future adoption are the authors' qualitative
assessments, not measured market trends or experimental rankings.

## Current operational documentation

These sources complement the papers. Producer and maintainer documentation is
unavoidable when establishing exact syntax, but should be distinguished from
independent evidence about how well that syntax works across implementations.

- **[INSDC DDBJ/ENA/GenBank Feature Table Definition](https://www.insdc.org/submitting-standards/feature-table/),
  version 11.4, April 2026.** A current archive specification covering feature keys,
  qualifiers, and location expressions. Its location model is an important comparison
  for a simple start/end table. It is maintained by the participating archives,
  not an external evaluation.
- **[Bioconductor rtracklayer](https://bioconductor.org/packages/release/bioc/html/rtracklayer.html),
  released version 1.72.0 in Bioconductor 3.23 when checked; PDF header dated
  September 18, 2026.** Its reference manual
  describes import/export across multiple track formats. This is a consumer/tool
  perspective rather than one feature format's specification; supported import/export
  does not itself establish lossless interchange. Check behavior against the installed
  version, not just the mutable release URL.
- **[Galaxy datatypes documentation](https://galaxyproject.org/learn/datatypes/),
  checked 2026-09-21; no publication date asserted.** Useful integration evidence:
  it documents differences among BED, interval, GFF, GTF, and GFF3, and advises removing
  some comments/section content for particular workflows. That advice identifies
  information-loss risks worth testing. The page contains historical material and
  should not be treated as a verified capability matrix for every current Galaxy tool.

## Recent tool papers: useful, with attribution

[AEGIS: an annotation extraction and genomic integration resource](https://academic.oup.com/bioinformatics/article/42/6/btag363/8704544),
Navarro-Payá and colleagues, *Bioinformatics*, **2026-06-09**, describes another
GFF/GTF standardization toolkit. It is a recent source of use cases and the authors'
own evaluation, not an independent verdict on competing parsers. The publisher's
**2025-12-04** date is receipt of the manuscript, not its publication date.

AGAT's format history and tests remain useful implementation resources. They should
not be our sole basis for deciding which named dialects matter or whether a new model
is justified. Counts of format names, tool adoption, semantic expressiveness, and
parser robustness are separate claims requiring different evidence.

## Implications to test in this repository

The following are our proposed evaluation dimensions, informed by this reading;
they are not results established by these papers for our model:

1. **Scope:** distinguish a physical artifact, an annotation release, a sequence,
   a biological feature, an evidence record, and their respective attributes.
2. **Coordinates and identity:** compare coordinate conventions, compound/partial
   locations, assembly identity, sequence identifiers, and discontinuous features.
3. **Semantic preservation:** test repeated attributes, controlled terms versus
   free text, parent relationships, provenance, unknown fields, and scoped comments.
4. **Operations:** measure interval and attribute queries separately from import,
   validation, indexing, and lossless source replay.
5. **Evolution:** record source checksums and versions; do not confuse byte identity
   with biological equivalence or a complete history of annotation changes.

Candidate corpus expansion should include INSDC feature tables, BED-family interval
files, and other actual producer outputs with provenance. These are suggestions,
not claims that those fixtures or their parsers are already present. NMDC DataObjects
remain one source of modeling requirements, not the boundary of the unified model.
