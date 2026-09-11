# Prior art: what exists, what it is not, and why this corpus exists

Written 2026-09-11, before the corpus was built, and kept in the repository so the search does not
have to be repeated or silently skipped. Claims are marked *measured* with a date, *quoted* from a
source, or *unverified*.

## Four models of a genome feature already exist

Three of the four have not been touched in months or years, **measured 2026-09-11** against the
GitHub API. That is the most useful single fact here, because it means a new effort displaces no
active incumbent.

| Model | State |
|---|---|
| https://github.com/biodatamodels/gff-schema | Self-described DRAFT. Last commit 2021-06-03. Ten commits, all from `cmungall`. One open issue, number 1, from 2021-02-11 |
| https://github.com/NAL-i5K/AgBioData_GFF3_recommendation | Active. Published as https://arxiv.org/abs/2202.07782 . Recommendations rather than a model |
| https://kbase.github.io/cdm-schema/Feature/ | Last push 2026-05-01. Sole human contributor is the handle `ialarmedalien`, 73 commits |
| https://laceysanderson.github.io/chado-docs/sequence/tables/feature.html | The relational ancestor the others descend from |

Two are vendored here, under `specs/`, because their licenses allow it. See the README.

**Chado repays close reading.** It keeps the feature separate from its location, in `featureloc`,
and expresses parent and child through `feature_relationship`. Nothing is nested. That is the same
normalization a flat-table publishing profile requires, reached independently about twenty years
earlier.

**The KBase Feature class holds two things the others do not.** It constrains feature type to
Sequence Ontology accessions under `sequence_feature` (SO:0000110), and it carries provenance slots
for source database and protocol. Worth keeping in anything unified. Note the tension with real
data: as documented in [columns-and-discretion.md](columns-and-discretion.md), seven of the fourteen
NMDC file types put a database accession in column 3 rather than an SO term, so NMDC data would fail
that constraint today.

## Seven normalization efforts exist, and none of them is a data model

They are parsers and rewriters. Every one takes files in and puts files out. That is the gap a
schema would fill, and it is why building rather than adopting was the right call.

| Effort | What it is |
|---|---|
| AgBioData GFF3 working group | Community recommendations, the closest thing to a standard |
| AGAT, NBIS Sweden | The broadest toolkit. Its documentation claims more than thirty distinct format cases |
| GFF3toolkit, USDA i5K | Quality control and merge pipeline for arthropod projects |
| GenomeTools | Toolkit with a validator and a tidy mode |
| gffread | GFF3 to GTF conversion |
| GFF3sort | Sorting for tabix indexing, because feature order is underspecified |
| AEGIS | Newest, 2025-12. Claims it parses files that defeat the others |

All seven are recorded in `corpus.yaml` with their URLs and licenses.

*Quoted, the AgBioData recommendations*, which is the diagnosis worth carrying into any discussion:
curators report that most of their data wrangling time goes to reformatting GFF3 files that model
the same data in different ways, and the CDS phase field "is commonly misinterpreted by both dataset
generators and consumers, which can lead to vastly different ... amino acid sequences."

**Inside DOE, no cross-agency normalization effort was found.** GitHub across the `ber-data` and
`microbiomedata` organizations, both Slack workspaces available at the time, and the literature were
searched on 2026-09-11. What exists instead is three models that no program coordinates: the draft
GFF3 schema, the KBase Feature class, and NMDC's own.

Do not read that as three unrelated models, which an earlier version of this file implied. See
[model-comparison.md](model-comparison.md): the feature-class description in the draft GFF3 schema
and in NMDC's schema is identical character for character, and that string appears nowhere in the
GFF3 specification. They are uncoordinated, not unconnected.

Treat the absence of a cross-agency effort as *looked and did not find one*, not as proof that none
exists.

## Eleven named format flavors, and where each came from

*Read from* the AGAT documentation, https://agat.readthedocs.io/en/latest/gxf.html

GFF, GFF1, GFF2, GFF2.5, GFF3, GTF, GTF2, GTF2.1, GTF2.2, GTF2.5, GTF3

- **GFF1 and GFF2** come from the Sanger Institute lineage. GFF2 is what Chado and older tools
  consume, and it is deprecated.
- **GTF** originated at Ensembl, then was adapted into **GTF2** for the Mouse and Human Annotation
  Collaboration.
- **The GTF versions differ by which feature types they admit**, from five in GTF1 to nine in GTF3,
  rather than by column count.
- **GFF3** is specified by the Sequence Ontology group.
- There is also an explicit **`relax` mode** that accepts any feature type at all. Worth naming out
  loud, because that is what most real files are.

Only GFF3 and GTF 2.2 are vendored here as real files. The archaic flavors appear to survive only
inside test suites, chiefly the GPL-3.0 AGAT one, which is why they are linked rather than copied.

## Approaches considered and rejected

- **Vendoring the AGAT suite.** Would have supplied all eleven flavors in one move. It is GPL-3.0,
  and a copyleft obligation on a reference corpus is the wrong trade.
- **Generating synthetic examples per flavor.** Fast, and worthless. The requirement was real and
  traceable, and a synthetic file cannot show what a real producer emits.
- **Linking the NMDC files rather than copying them.** The smallest are 158 bytes. Copying costs
  nothing and makes the corpus usable offline and stable against URL drift.

## What building added that adopting could not

The fourteen NMDC files: one per distinct GFF `data_object_type` in production, each the smallest
real instance of its kind, each checksum matched against the NMDC record. Under 20 KB in total, and
it did not exist anywhere.

They also produced two findings no literature review would have: column 3 carrying database
accessions instead of Sequence Ontology terms across seven file types, and an empty column 2 where
the specification calls for a dot. Both are in
[columns-and-discretion.md](columns-and-discretion.md).
