# Background: prior art, reading, and scope

What existed before this corpus, what a feature table should be expected to cover, and what to read across formats. The [model comparison](model-comparison.md) compares the four existing models decision by decision. For the running list of overlaps and conflicts with other people's current work, including BRIDGE, KBase CDM and nmdc-lakehouse, see [overlaps and conflicts](how-it-fits.md#overlaps-and-conflicts).

## Prior art

This section records what exists, what it is not, and why this corpus exists. It was written 2026-09-11, before the corpus was built, and kept in the repository so the search does not have to be repeated or silently skipped. Claims are marked *measured* with a date, *quoted* from a source, or *unverified*. This inventory is GFF-focused. For a broader and more recent assessment, see the [annotated reading list, checked 2026-09-21](#reading-across-feature-table-formats) below. It includes cross-format reviews, comparative measurements, and consumer documentation, with each source's perspective and limits identified.

### Four models of a genome feature already exist

Three of the four have not been touched in months or years, **measured 2026-09-11** against the GitHub API. Repository activity alone does not establish adoption, suitability, or whether an existing model should be extended instead of creating another one.

| Model | State |
|---|---|
| https://github.com/biodatamodels/gff-schema | Self-described DRAFT. Last commit 2021-06-03. Ten commits, all from a single contributor. One open issue, number 1, from 2021-02-11 |
| https://github.com/NAL-i5K/AgBioData_GFF3_recommendation | Active. Published as https://arxiv.org/abs/2202.07782 . Recommendations rather than a model |
| https://kbase.github.io/cdm-schema/Feature/ | Last push 2026-05-01. Sole human contributor is the handle `ialarmedalien`, 73 commits |
| https://laceysanderson.github.io/chado-docs/sequence/tables/feature.html | The relational ancestor the others descend from |

Two are vendored here, under `corpus/specifications/`, because their licenses allow it. See the [corpus inventory](../corpus/README.md#specifications).

**Chado repays close reading.** It keeps the feature separate from its location, in `featureloc`, and expresses parent and child through `feature_relationship`. Nothing is nested. That is the same normalization a flat-table publishing profile requires, reached independently about twenty years earlier.

**The KBase Feature class holds two things the others do not.** It constrains feature type to Sequence Ontology accessions under `sequence_feature` (SO:0000110), and it carries provenance slots for source database and protocol. Worth keeping in anything unified. Note the tension with real data: as documented in [columns and discretion](columns-and-discretion.md), seven of the fourteen NMDC file types put a database accession in column 3 rather than an SO term, so NMDC data would fail that constraint today.

### Seven normalization efforts exist, and none of them is a data model

These entries mix community recommendations with software for parsing, validation, conversion, sorting, and integration. Their existence alone does not settle whether to adopt an existing model, extend one, or build another; that requires explicit requirements and interoperability tests.

| Effort | What it is |
|---|---|
| AgBioData GFF3 working group | Community recommendations, the closest thing to a standard |
| AGAT, NBIS Sweden | The broadest toolkit. Its documentation claims more than thirty distinct format cases |
| GFF3toolkit, USDA i5K | Quality control and merge pipeline for arthropod projects |
| GenomeTools | Toolkit with a validator and a tidy mode |
| gffread | GFF3 to GTF conversion |
| GFF3sort | Sorting for tabix indexing, because feature order is underspecified |
| AEGIS | Toolkit paper published 2026-06-09; the 2025-12 date was manuscript receipt. Its comparative claims are the tool authors' evaluation; see [recent tool papers](#recent-tool-papers-useful-with-attribution) |

All seven are recorded in `corpus/index.yaml` with their URLs and licenses.

*Quoted, the AgBioData recommendations*, which is the diagnosis worth carrying into any discussion: curators report that most of their data wrangling time goes to reformatting GFF3 files that model the same data in different ways, and the CDS phase field "is commonly misinterpreted by both dataset generators and consumers, which can lead to vastly different ... amino acid sequences."

**Inside DOE, no cross-agency normalization effort was found.** GitHub across the `ber-data` and `microbiomedata` organizations, both Slack workspaces available at the time, and the literature were searched on 2026-09-11. What exists instead is three models that no program coordinates: the draft GFF3 schema, the KBase Feature class, and NMDC's own.

Do not read that as three unrelated models, which an earlier version of this file implied. See [model comparison](model-comparison.md): the feature-class description in the draft GFF3 schema and in NMDC's schema is identical character for character, and that string appears nowhere in the GFF3 specification. They are uncoordinated, not unconnected.

Treat the absence of a cross-agency effort as *looked and did not find one*, not as proof that none exists.

### Eleven named format flavors, and where each came from

*Read from* the AGAT documentation, https://agat.readthedocs.io/en/latest/gxf.html

GFF, GFF1, GFF2, GFF2.5, GFF3, GTF, GTF2, GTF2.1, GTF2.2, GTF2.5, GTF3

- **GFF1 and GFF2** come from the Sanger Institute lineage. GFF2 is what Chado and older tools consume, and it is deprecated.
- **GTF** originated at Ensembl, then was adapted into **GTF2** for the Mouse and Human Annotation Collaboration.
- **The GTF versions differ by which feature types they admit**, from five in GTF1 to nine in GTF3, rather than by column count.
- **GFF3** is specified by the Sequence Ontology group.
- There is also an explicit **`relax` mode** that accepts any feature type at all. Worth naming out loud, because that is what most real files are.

Only GFF3 and GTF 2.2 are vendored here as real files. The archaic flavors appear to survive only inside test suites, chiefly the GPL-3.0 AGAT one, which is why they are linked rather than copied.

### Approaches considered and rejected

- **Vendoring the AGAT suite.** Would have supplied all eleven flavors in one move. It is GPL-3.0, and a copyleft obligation on a reference corpus is the wrong trade.
- **Generating synthetic examples per flavor.** Fast, and worthless. The requirement was real and traceable, and a synthetic file cannot show what a real producer emits.
- **Linking the NMDC files rather than copying them.** The smallest are 158 bytes. Copying costs nothing and makes the corpus usable offline and stable against URL drift.

### What building added that adopting could not

The fourteen NMDC files: one per distinct GFF `data_object_type` in production, each the smallest real instance of its kind, each checksum matched against the NMDC record. Under 20 KB in total, and it did not exist anywhere.

They also produced two findings no literature review would have: column 3 carrying database accessions instead of Sequence Ontology terms across seven file types, and an empty column 2 where the specification calls for a dot. Both are in [columns and discretion](columns-and-discretion.md).

## Chado and scope

Chado's status, and what a feature table should be expected to cover: two questions a reviewer will ask about reusing Chado's design, and an answer to the scope question underneath them. Claims are *measured* with a date, *read* from a source, or marked as a *judgement*.

### Chado is not maintained, and that is separable from whether it is right

**Measured 2026-09-11** against the GitHub API for `GMOD/Chado`:

| | |
|---|---|
| Last push | 2024-06-24 |
| GitHub Releases | none |
| Tags | one, `1.31-release` |
| Open issues | 57, excluding two open pull requests |
| Archived | no |
| Default branch | `1.4` |

Commits by year, with every year present so the series is not shifted:

| 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 932 | 26 | 13 | 0 | 50 | 2 | 1 | 31 | 69 | 7 | 3 | 15 | 0 | 34 | 0 | 0 |

The combined count GitHub reports on the repository page is 59, which includes the two open pull requests. The issue-only figure is 57.

So there is a schema to read and learn from, and no project to depend on. Those are different things, and the distinction matters for this work: Chado's decomposition of GFF3 column 9 into one table per reserved tag, documented in [model comparison](model-comparison.md), is the best available answer to how a multivalued attribute survives a flat publishing profile. Borrowing that answer costs nothing and takes on no dependency.

### The blocker is not age. It is one constraint

*Read from* `corpus/specifications/chado_1.4_feature_tables.sql`, vendored here:

```sql
organism_id bigint not null,
constraint feature_c1 unique (organism_id, uniquename, type_id)
```

Every feature must belong to exactly one organism, and feature identity is **scoped by** organism.

That is incompatible with the data BER holds. A metagenome contig comes from a mixed community. An unbinned contig has no organism assignment at all. A metagenome-assembled genome carries a provisional taxonomy, and revising it changes the feature's uniqueness key.

**Measured 2026-09-11:** NMDC's `GenomeFeature` declares nine slots and zero mentions of organism or taxon. Note what that does and does not establish: the absence is measured, and whether it was deliberate is not recorded anywhere. Chado requires precisely what NMDC does not carry, and the fourteen NMDC annotation files vendored in this corpus are all metagenome annotation.

### What Chado predates, for completeness

Read from the schema and its repository. None of these is a reason to reject the column 9 design; they are reasons not to adopt the implementation.

- A row-store PostgreSQL schema from 2002. No columnar or Parquet form, so nothing in it reaches a lakehouse without a translation layer.
- Data definition language only. No generated Python, JSON Schema, RDF or validators, which is the whole value of a LinkML model over a set of `CREATE TABLE` statements.
- Identity is integer surrogate keys, not resolvable identifiers, so nothing in it is findable or reusable in the FAIR sense without an external mapping.
- Ontology terms live as a local copy in `cvterm` rather than as resolvable ontology identifiers, so they go stale silently.
- No API. That is why Tripal exists.
- No GitHub Releases. That is narrower than it sounds: the repository carries a `1.31-release` tag, and any commit can be pinned directly, so a dependency is possible. What is missing is a published release with notes, which is what would tell a consumer whether an upgrade is safe.
- Row timestamps, `timeaccessioned` and `timelastmodified`, but no versioning of assertions and no agent model beyond publication and analysis references.

### Should a BER feature table be expected to support metagenomics?

**Yes, and the requirement is negative rather than positive.** *Judgement.*

The ask is not "add metagenomics support." It is "do not require what metagenomics cannot supply." Chado's `organism_id not null` is exactly that kind of assumption, and it is cheap to avoid: leave the organism reference optional, and do not put it in any uniqueness constraint.

This is not a hypothetical accommodation. Metagenome annotation is the data. Every one of the fourteen NMDC GFF types in this corpus is a metagenome annotation product, and the JGI IMG pipeline that produced them is a metagenome pipeline. A model that requires an organism per feature cannot load the corpus it is meant to describe.

The same reasoning covers taxonomy on a bin: if a metagenome-assembled genome's taxonomy is an attribute that can be revised, it must not participate in identity. Chado makes that mistake and it is worth naming so a new model does not repeat it.

### Should it support the other science?

**Mostly no, and saying so early is cheaper than discovering it late.** *Judgement.*

- **Proteomics and metabolomics features: no.** A feature table is an interval on a sequence with attributes. A mass spectrometry peak is not an interval on a sequence. EMSL MONet's data is soil chemistry and microstructure, and forcing it into a feature model would make the model worse at the thing it exists for without making it good at that.
- **Quantitative cross-sample matrices: no.** Expression and abundance belong in a table keyed by feature and sample, referencing the feature model rather than living inside it.
- **Genome graphs and pangenomes: not now, but do not foreclose it.** GFF3 assumes a linear landmark, and graph coordinates break that assumption. Nothing at BER publishes graph genomes today, so designing for it would be speculative. One cheap hedge keeps the door open: make the landmark reference an **entity** rather than a string, which is what `gff-schema` already does with its `seqid` slot ranged over `seq` and what NMDC's schema carries a TODO asking for. A future non-linear landmark type is then an addition rather than a migration.

### The test to apply instead

The useful question is not what a model can support. It is **what assumptions it hardcodes**, since those are what break later and cannot be fixed without a migration.

Three worth checking against any candidate:

1. Does a feature require an organism? It must not.
2. Does anything revisable participate in identity? Taxonomy and functional assignment both get revised.
3. Is the landmark an entity or a string? An entity costs nothing now and is the only cheap hedge against non-linear coordinates.

### What the kickoff added, 2026-09-11

Recorded here because the meeting notes live in a Google document that only attendees can open, and these are design positions rather than minutes.

**The goal is mappable and subclassable, not replacement.** The stated aim is a model that groups with existing feature or GFF classes "should be able to map to our representation and/or subclass our implementation." That rules out a design that only works if everyone migrates, and it raises the value of the comparison in [model comparison](model-comparison.md), since each of the four models has to be reachable from the result.

**There is a live argument against designing for the flat profile at all.** One position put in the meeting: flattening nested data at import is not the hard part, and the real decision is whether to design a schema that is already flat. Ingest nested, then flatten, as the KBase lakehouse does.

That is a different answer from the one this corpus works toward, and it is a reasonable one. It sharpens rather than settles the question, because the two positions disagree about *where* the flattening belongs rather than whether it is possible. Both agree a semantic model and a publishing profile are separate layers. Worth keeping the disagreement visible instead of resolving it by assertion.

**The scalar-only profile question is now on the record and still unanswered.** The notes ask whether the catalog's all-scalar requirement applies to JGI, to BRIDGE, or to both, and "Do we need to stick to that?" Nobody has asked its author. Tracked at https://github.com/microbiomedata/nmdc-lakehouse/issues/342

**The metagenome question was framed better than in this document.** Not only "must features belong to an organism" but: metagenome-assembled structures are *predicted*, so does the model need to distinguish a predicted feature from one observed in a sequenced physical sample from a single organism? That is a provenance distinction rather than a taxonomy one, and it may be recoverable from the file: the tool that called a feature is sometimes in column 2. Which is another reason column 2's openness, measured in [columns and discretion](columns-and-discretion.md), matters more than it looks.

**The CURIE question is the column 3 finding, arrived at independently.** The notes ask whether feature classifications must always be compact identifiers, or whether names and unprefixed codes are acceptable, noting that NMDC has been using those. That is exactly the measurement in [columns and discretion](columns-and-discretion.md): seven of the fourteen NMDC file types put a bare database accession in column 3. So the question has an answer about current practice even though the policy is undecided.

**Two sources added to the reading list**, both now in `corpus/index.yaml`: the IMG pipeline documentation, which specifies the GFF output of the pipeline that produced every NMDC file vendored here, and the Blue Collar Bioinformatics parser, as an example of what consumers actually run.

## Reading across feature-table formats

Search and verification date: **2026-09-21**. This is an annotated selection, not a systematic review or a claim that the newest paper covers every format. Dates below are publication dates or explicit specification versions, not search engine crawl dates. A recent package release does not date every paragraph of its manual.

The [prior-art inventory](#prior-art) above concentrates on GFF-family models and normalization tools. For a broader view, read across the perspectives below. A format specification establishes its contract; it does not independently demonstrate interoperability, adoption, or superiority. Likewise, a tool author's evaluation is useful evidence but needs that attribution.

### Papers and community assessments

| Source and date | Why read it | Perspective and limits |
|---|---|---|
| Dimonaco, Clare & Vickers, [Genome assemblies and annotations are not static and need support for tracking their evolution](https://pubmed.ncbi.nlm.nih.gov/42398073/), *Briefings in Bioinformatics*, **2026-07-03**, [DOI](https://doi.org/10.1093/bib/bbag357) | Recent review of assembly/annotation formats, provenance, changes between releases, and requirements for machine-readable history. Particularly relevant to source-document identity. | A critical review advocating better version-aware infrastructure. It is not a neutral experimental comparison or a complete catalogue of feature-table syntaxes. Its proposed direction remains an argument to evaluate. |
| Schäfer & Yang, [A comprehensive benchmark of tools for efficient genomic interval querying](https://academic.oup.com/bib/article/26/4/bbaf379/8216879), *Briefings in Bioinformatics*, **2025-07-29** | Empirical comparison of interval-query tools; Table 1 distinguishes supported formats, sorting, indexing, and compression. Useful for turning coordinate-query requirements into measurements. | Compares multiple tools using the authors' segmeter framework. Measures query behavior/performance, not faithful conversion of attributes, hierarchies, comments, or whole documents. It cannot identify the best semantic feature model. |
| Xue, Khoroshevskyi, Gomez & Sheffield, [Opportunities and challenges in sharing and reusing genomic interval data](https://www.frontiersin.org/journals/genetics/articles/10.3389/fgene.2023.1155809/full), *Frontiers in Genetics*, **2023-03-20** | A BED/interval-data perspective: reuse depends on reference-genome identification, metadata, standardization, and data quality. Broadens a discussion otherwise dominated by GFF and gene models. | Explicitly an **Opinion** article, from researchers working on genomic data infrastructure. Useful problem analysis, not an independent format benchmark. |
| Earth BioGenome Project annotation subcommittee, [Report on Annotation Standards](https://www.earthbiogenome.org/report-on-annotation-standards), **version 1.0, June 2023** | Cross-institution expectations for feature coverage, evidence, annotation-set identifiers, assembly association, provenance, and quality. It explicitly recognizes variation among GFF3 producers. | Community guidance with a eukaryotic gene-annotation focus and an explicit preference for GFF3; broader participation does not make it format-neutral. |
| Saha and colleagues, AgBioData, [Recommendations for extending the GFF3 specification for improved interoperability of genomic data](https://arxiv.org/abs/2202.07782), **2022-02-15, v1 preprint** | Concrete curatorial disagreements and proposed conventions for GFF3 fields, functional annotations, and gene models. Good material for interoperability fixtures. | A GFF3 working group's recommendations, including people involved in its ecosystem. This is community criticism from within that ecosystem, not an external comparison. No later journal version was verified in this search. |
| Ejigu & Jung, [Review on the Computational Genome Annotation of Sequences Obtained by Next-Generation Sequencing](https://pmc.ncbi.nlm.nih.gov/articles/PMC7565776/), *Biology* 9:295, **2020-09-18**, [DOI](https://doi.org/10.3390/biology9090295) | Section 5.1 places GFF/GTF alongside GenBank, EMBL, DDBJ, and sequence formats in a broader annotation workflow. Useful orientation outside one format project. | A broad review with a short formats section. Older background, not evidence of current parser compatibility or format prevalence. |

The newest directly relevant critical review found here is the **July 2026** Dimonaco paper. The **July 2025** interval benchmark is the strongest recent comparative measurement in this selection, but answers a different question. Neither is an exhaustive, independent GFF/GTF/BED/INSDC conversion benchmark.

Read the Dimonaco paper with its [supplementary Table S1](https://pmc-oa-opendata.s3.amazonaws.com/PMC13331350.1/supplementary_file_1_bbag357.pdf). It compares sequence, annotation, interval, graph, variant, and other representations from a version-control perspective. The table also includes a toolkit, GFFx, explicitly labeled as such. Its judgments about future adoption are the authors' qualitative assessments, not measured market trends or experimental rankings.

### Current operational documentation

These sources complement the papers. Producer and maintainer documentation is unavoidable when establishing exact syntax, but should be distinguished from independent evidence about how well that syntax works across implementations.

- **[INSDC DDBJ/ENA/GenBank Feature Table Definition](https://www.insdc.org/submitting-standards/feature-table/), version 11.4, April 2026.** A current archive specification covering feature keys, qualifiers, and location expressions. Its location model is an important comparison for a simple start/end table. It is maintained by the participating archives, not an external evaluation.
- **[Bioconductor rtracklayer](https://bioconductor.org/packages/release/bioc/html/rtracklayer.html), released version 1.72.0 in Bioconductor 3.23 when checked; PDF header dated September 18, 2026.** Its reference manual describes import/export across multiple track formats. This is a consumer/tool perspective rather than one feature format's specification; supported import/export does not itself establish lossless interchange. Check behavior against the installed version, not just the mutable release URL.
- **[Galaxy datatypes documentation](https://galaxyproject.org/learn/datatypes/), checked 2026-09-21; no publication date asserted.** Useful integration evidence: it documents differences among BED, interval, GFF, GTF, and GFF3, and advises removing some comments/section content for particular workflows. That advice identifies information-loss risks worth testing. The page contains historical material and should not be treated as a verified capability matrix for every current Galaxy tool.

### Recent tool papers: useful, with attribution

[AEGIS: an annotation extraction and genomic integration resource](https://academic.oup.com/bioinformatics/article/42/6/btag363/8704544), Navarro-Payá and colleagues, *Bioinformatics*, **2026-06-09**, describes another GFF/GTF standardization toolkit. It is a recent source of use cases and the authors' own evaluation, not an independent verdict on competing parsers. The publisher's **2025-12-04** date is receipt of the manuscript, not its publication date.

AGAT's format history and tests remain useful implementation resources. They should not be our sole basis for deciding which named dialects matter or whether a new model is justified. Counts of format names, tool adoption, semantic expressiveness, and parser robustness are separate claims requiring different evidence.

### Implications to test in this repository

The following are our proposed evaluation dimensions, informed by this reading; they are not results established by these papers for our model:

1. **Scope:** distinguish a physical artifact, an annotation release, a sequence, a biological feature, an evidence record, and their respective attributes.
2. **Coordinates and identity:** compare coordinate conventions, compound/partial locations, assembly identity, sequence identifiers, and discontinuous features.
3. **Semantic preservation:** test repeated attributes, controlled terms versus free text, parent relationships, provenance, unknown fields, and scoped comments.
4. **Operations:** measure interval and attribute queries separately from import, validation, indexing, and lossless source replay.
5. **Evolution:** record source checksums and versions; do not confuse byte identity with biological equivalence or a complete history of annotation changes.

Candidate corpus expansion should include INSDC feature tables, BED-family interval files, and other actual producer outputs with provenance. These are suggestions, not claims that those fixtures or their parsers are already present. NMDC DataObjects remain one source of modeling requirements, not the boundary of the unified model.
