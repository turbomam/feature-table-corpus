# Acceptance tests by discipline

Who is likely to judge a new feature table format, the first test each would apply, and the number
that would show whether it passes. Written 2026-10-02 to plan evidence before it is asked for.
The tests are predictions, not requirements anyone has stated. The status column says what this
repository has today, read from its own documents and code on 2026-10-02; nothing in this page was
newly measured unless it says so.

## Producers of feature data

| discipline | likely question | acceptance test | metric | status here |
|---|---|---|---|---|
| Annotation pipeline developers (NCBI PGAP, JGI IMG, Prokka, Bakta) | Can my output go in and come back out unchanged? | Round trip of each pipeline's real files | Share of rows and attribute keys preserved, per producer | Round trips for several producers in [conversion round trips](../analyses/conversion-roundtrips/README.md) |
| Eukaryotic genome groups (Phytozome, MycoCosm) | Does it hold exons, UTRs, isoforms and a representative transcript? | Gene, several mRNAs and multi-part CDS load, validate and reconstruct | Share of genes whose structure reconstructs exactly | `is_representative` exists; the eukaryotic profile is https://github.com/turbomam/feature-table-corpus/issues/48; MycoCosm is https://github.com/turbomam/feature-table-corpus/issues/92 |
| Archive submission curators (INSDC, GenBank) | Can it produce a valid submission? | Export to GenBank feature-table form that NCBI's validator accepts | Validator errors per 1,000 features | `insdc-locations/1.0.0` reads GenBank; export to a submission is untested |
| Natural-product and biosynthetic gene cluster researchers (SMC, antiSMASH, MIBiG) | Can I store a cluster and ask what is next to what? | Gene order and neighbor queries on a known cluster give the known answer | Query results against a curated answer | `just bgc-check` does this for the RefSeq actinorhodin cluster ([BGC exercise](../analyses/bgc-query/README.md)); SMC is https://github.com/turbomam/feature-table-corpus/issues/166 |
| Protein-domain annotators (Pfam, InterPro, KEGG) | Are hits kept in protein coordinates, with e-value and bit score apart? | A CDS with several domain hits keeps each hit's protein interval, target interval and score type | Share of hits that convert back to the source rows | NMDC Pfam through `nmdc-pfam-protein/5.0.0` ([protein-relative profile](protein-relative-profile.md)) |

## Consumers of the data

| discipline | likely question | acceptance test | metric | status here |
|---|---|---|---|---|
| Microbial ecologists and metagenome users (NMDC) | Does it scale to every sample and keep MAG membership? | Load one full NMDC annotation run into BERDL; contig-collection queries work | Load time and table size per million features; result counts and latency of the contig-collection queries | Not measured: https://github.com/turbomam/feature-table-corpus/issues/167, which waits on loading (https://github.com/microbiomedata/nmdc-lakehouse/issues/388) |
| Comparative genomics researchers | Can I join the same gene across annotation versions and sources? | Join features from two sources on stable identifiers | Share of features with a usable cross-source identifier | `stable_identifiers` exists on `Feature`; join coverage is not measured |
| Genome browser developers (JBrowse, IGV) | Can I get GFF3 or BED back out, by region, fast enough to draw? | Region query returns nested features; exported GFF3 loads in a browser | Region-query latency on a large table | Overlap and neighbor queries exist in DuckDB ([query examples](query-requirements.md)); latency is not measured (https://github.com/turbomam/feature-table-corpus/issues/167) |
| Agent and LLM users (BERIL) | Can an agent answer questions from the tables without being told the schema? | A fixed question set gets correct SQL and correct answers | Share of questions answered correctly | Not started |
| Statisticians and machine-learning users | Do nulls, types and counts mean the same thing across sources? | Each column has one type and one meaning in every source's tables | Columns whose types disagree across sources | The [Parquet export](lakehouse-export.md) checks types for one export; nmdc-lakehouse writes `phase` as `int8` where the export writes `int64` |

## Infrastructure and governance

| discipline | likely question | acceptance test | metric | status here |
|---|---|---|---|---|
| Data engineers and lakehouse architects (BERDL, Iceberg, Trino) | Does it load without hand fixes, and fit a flat-only catalog? | Load into Iceberg with no manual schema edits; the flat profile passes the BRIDGE catalog rules | Load failures per table; query cost of flat against nested | Columns null in every row needed an explicit schema to load (observed 2026-10-02); ARRAY columns are refused by the catalog profile (https://github.com/microbiomedata/nmdc-lakehouse/issues/342); see [flat profile](flat-profile.md) |
| Relational database designers (IMG, SMC) | Does it map to our existing tables? | A crosswalk from each database's columns to model slots, gaps listed | Share of source columns mapped | [IMG core crosswalk](img-core-crosswalk.md); SMC waits on its DDL |
| Data modelers and standards groups (LinkML, BRIDGE, KBase CDM, NMDC) | Does it import cleanly beside our modules and reuse what exists? | Builds under the BRIDGE central schema with no name or prefix clash; mappings to CDM and NMDC resolve | Name clashes; share of classes with mappings | `name` and `numeric_value` clash with the central schema (https://github.com/ber-data/bridge-central-schema/pull/5); CDM mapping is https://github.com/turbomam/feature-table-corpus/issues/139 |
| Ontologists (Sequence Ontology, EDAM) | Are feature types and score types real terms? | Every `type` resolves to a Sequence Ontology term or is marked as a database accession | Share of `type` values mapped | linkml/valuesets `GenomeFeatureType` matches 44.9% of corpus feature rows exactly and 56.8% ignoring case (https://github.com/turbomam/feature-table-corpus/issues/131); see https://github.com/turbomam/feature-table-corpus/issues/8 |
| Bioinformatics tool developers | Do existing validators and parsers agree with it? | Independent GFF3 validators' verdicts on the corpus are recorded and explained | Agreement between validators and expected labels | GenomeTools and GFF3toolkit in `just validity-check` ([independent validation](../analyses/format-validation/README.md)); AGAT is blocked on macOS arm64 |
| Data stewards and licensing (JGI data policy) | Do license and citation travel with the data? | Converted outputs carry the source's terms and citation | Share of outputs carrying terms and citation | Provenance is carried. Neither terms of use nor citations reach the Dataset or the Parquet export; the Populus excerpt files carry their citation as a `# cite:` line, which the Phytozome converters keep in their header JSON (https://github.com/turbomam/feature-table-corpus/issues/151) |
| Program managers and funders (DOE BER) | Will facilities adopt it, and who maintains it? | Data from two or more facilities load in production | Facilities using it; effort to add a source format | Not measured |

## Unusual gene structures

https://github.com/cmdcolin/oddgenes (text CC0, checked 2026-10-02) is a curated list of gene
annotations that break common bioinformatics assumptions, with literature links. Its cases are a
ready source of tests for the representation, as distinct from the format. The rows below are
the cases that touch this model; the status comes from reading
[feature locations](feature-locations.md), [columns and discretion](columns-and-discretion.md) and
the schema, and none was tested for this page.

| oddgenes case | what the model must hold | status here |
|---|---|---|
| Circular chromosomes | A feature crossing the origin | Supported: `FeatureLocation.crosses_origin`, tested on six origin-crossing joins in phiX174 through `insdc-locations`; `gff3-contig` refuses the phiX174 GFF3 |
| Translational (ribosomal) frameshift | One CDS whose parts overlap by one or more bases | Refused: a structured location requires nonoverlapping parts |
| Trans-splicing of exons on different strands | One feature with parts on both strands | Refused: mixed strands are refused |
| Exon shared across different genes | A feature with more than one parent | Supported: `Feature.parent` is multivalued, and `tests/test_conversion_profiles.py` round-trips a GFF3 exon with two parents through `gff3-contig`; the corpus fixture `corpus/fixtures/edge-cases/multiple_parents.gff3` is not run through it |
| 0 bp exon | A zero-length site between two bases | Refused: between-base sites are refused |
| 1 bp exon | A part whose start equals its end | Not checked |
| Stop codon reassignment, alternative codon tables | A genetic code per sequence, and exceptions within a gene | Per contig only, through `Contig.translation_table`; no slot for an exception within one gene |
| Overlapping genes, nested genes, antisense transcription | Independent intervals that overlap, on either strand | Plain intervals; overlap queries exist; no corpus case labelled as such |
| Polycistronic transcripts and operons | One transcript parent to several CDS | Expressible through `parent`; not checked |
| Polyproteins and inteins | Protein products cut from one CDS | No class for protein products; not checked |
| Very large introns, many exons, many isoforms | Large part counts and isoform counts per gene | Not measured |
| 0-based versus 1-based coordinates | One coordinate convention | The model is one-based inclusive; the BED12 profile converts ([conversion profiles](conversion-profiles.md)) |

## Keeping this page useful

When a test here gets run, replace the status with the result, the date and the command. When a
discipline states its own test, quote it and say where it was stated.
