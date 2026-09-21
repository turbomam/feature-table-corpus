# Chado's status, and what a feature table should be expected to cover

Two questions a reviewer will ask about reusing Chado's design, and an answer to the scope question
underneath them. Claims are *measured* with a date, *read* from a source, or marked as a *judgement*.

## Chado is not maintained, and that is separable from whether it is right

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

The combined count GitHub reports on the repository page is 59, which includes the two open pull
requests. The issue-only figure is 57.

So there is a schema to read and learn from, and no project to depend on. Those are different
things, and the distinction matters for this work: Chado's decomposition of GFF3 column 9 into one
table per reserved tag, documented in [model-comparison.md](model-comparison.md), is the best
available answer to how a multivalued attribute survives a flat publishing profile. Borrowing that
answer costs nothing and takes on no dependency.

## The blocker is not age. It is one constraint

*Read from* `corpus/specifications/chado_1.4_feature_tables.sql`, vendored here:

```sql
organism_id bigint not null,
constraint feature_c1 unique (organism_id, uniquename, type_id)
```

Every feature must belong to exactly one organism, and feature identity is **scoped by** organism.

That is incompatible with the data BER holds. A metagenome contig comes from a mixed community. An
unbinned contig has no organism assignment at all. A metagenome-assembled genome carries a
provisional taxonomy, and revising it changes the feature's uniqueness key.

**Measured 2026-09-11:** NMDC's `GenomeFeature` declares nine slots and zero mentions of organism or
taxon. Note what that does and does not establish: the absence is measured, and whether it was
deliberate is not recorded anywhere. Chado requires precisely what NMDC does not carry, and the fourteen NMDC annotation files vendored in this corpus are all metagenome
annotation.

## What Chado predates, for completeness

Read from the schema and its repository. None of these is a reason to reject the column 9 design;
they are reasons not to adopt the implementation.

- A row-store PostgreSQL schema from 2002. No columnar or Parquet form, so nothing in it reaches a
  lakehouse without a translation layer.
- Data definition language only. No generated Python, JSON Schema, RDF or validators, which is the
  whole value of a LinkML model over a set of `CREATE TABLE` statements.
- Identity is integer surrogate keys, not resolvable identifiers, so nothing in it is findable or
  reusable in the FAIR sense without an external mapping.
- Ontology terms live as a local copy in `cvterm` rather than as resolvable ontology identifiers,
  so they go stale silently.
- No API. That is why Tripal exists.
- No GitHub Releases. That is narrower than it sounds: the repository carries a `1.31-release` tag,
  and any commit can be pinned directly, so a dependency is possible. What is missing is a published
  release with notes, which is what would tell a consumer whether an upgrade is safe.
- Row timestamps, `timeaccessioned` and `timelastmodified`, but no versioning of assertions and no
  agent model beyond publication and analysis references.

## Should a BER feature table be expected to support metagenomics?

**Yes, and the requirement is negative rather than positive.** *Judgement.*

The ask is not "add metagenomics support." It is "do not require what metagenomics cannot supply."
Chado's `organism_id not null` is exactly that kind of assumption, and it is cheap to avoid: leave
the organism reference optional, and do not put it in any uniqueness constraint.

This is not a hypothetical accommodation. Metagenome annotation is the data. Every one of the
fourteen NMDC GFF types in this corpus is a metagenome annotation product, and the JGI IMG pipeline
that produced them is a metagenome pipeline. A model that requires an organism per feature cannot
load the corpus it is meant to describe.

The same reasoning covers taxonomy on a bin: if a metagenome-assembled genome's taxonomy is an
attribute that can be revised, it must not participate in identity. Chado makes that mistake and it
is worth naming so a new model does not repeat it.

## Should it support the other science?

**Mostly no, and saying so early is cheaper than discovering it late.** *Judgement.*

- **Proteomics and metabolomics features: no.** A feature table is an interval on a sequence with
  attributes. A mass spectrometry peak is not an interval on a sequence. EMSL MONet's data is soil
  chemistry and microstructure, and forcing it into a feature model would make the model worse at
  the thing it exists for without making it good at that.
- **Quantitative cross-sample matrices: no.** Expression and abundance belong in a table keyed by
  feature and sample, referencing the feature model rather than living inside it.
- **Genome graphs and pangenomes: not now, but do not foreclose it.** GFF3 assumes a linear
  landmark, and graph coordinates break that assumption. Nothing at BER publishes graph genomes
  today, so designing for it would be speculative. One cheap hedge keeps the door open: make the
  landmark reference an **entity** rather than a string, which is what `gff-schema` already does
  with its `seqid` slot ranged over `seq` and what NMDC's schema carries a TODO asking for. A future
  non-linear landmark type is then an addition rather than a migration.

## The test to apply instead

The useful question is not what a model can support. It is **what assumptions it hardcodes**, since
those are what break later and cannot be fixed without a migration.

Three worth checking against any candidate:

1. Does a feature require an organism? It must not.
2. Does anything revisable participate in identity? Taxonomy and functional assignment both get
   revised.
3. Is the landmark an entity or a string? An entity costs nothing now and is the only cheap hedge
   against non-linear coordinates.

## What the kickoff added, 2026-09-11

Recorded here because the meeting notes live in a Google document that only attendees can open,
and these are design positions rather than minutes.

**The goal is mappable and subclassable, not replacement.** The stated aim is a model that groups
with existing feature or GFF classes "should be able to map to our representation and/or subclass
our implementation." That rules out a design that only works if everyone migrates, and it raises the
value of the comparison in [model-comparison.md](model-comparison.md), since each of the four models
has to be reachable from the result.

**There is a live argument against designing for the flat profile at all.** One position put in the
meeting: flattening nested data at import is not the hard part, and the real decision is whether to
design a schema that is already flat. Ingest nested, then flatten, as the KBase lakehouse does.

That is a different answer from the one this corpus works toward, and it is a reasonable one. It
sharpens rather than settles the question, because the two positions disagree about *where* the
flattening belongs rather than whether it is possible. Both agree a semantic model and a publishing
profile are separate layers. Worth keeping the disagreement visible instead of resolving it by
assertion.

**The scalar-only profile question is now on the record and still unanswered.** The notes ask
whether the catalog's all-scalar requirement applies to JGI, to BRIDGE, or to both, and "Do we need
to stick to that?" Nobody has asked its author. Tracked at
https://github.com/microbiomedata/nmdc-lakehouse/issues/342

**The metagenome question was framed better than in this document.** Not only "must features belong
to an organism" but: metagenome-assembled structures are *predicted*, so does the model need to
distinguish a predicted feature from one observed in a sequenced physical sample from a single
organism? That is a provenance distinction rather than a taxonomy one, and it may be recoverable
from the file: the tool that called a feature is sometimes in column 2. Which is another reason
column 2's openness, measured in
[columns-and-discretion.md](columns-and-discretion.md), matters more than it looks.

**The CURIE question is the column 3 finding, arrived at independently.** The notes ask whether
feature classifications must always be compact identifiers, or whether names and unprefixed codes
are acceptable, noting that NMDC has been using those. That is exactly the measurement in
[columns-and-discretion.md](columns-and-discretion.md): seven of the fourteen NMDC file types put a
bare database accession in column 3. So the question has an answer about current practice even
though the policy is undecided.

**Two sources added to the reading list**, both now in `corpus/index.yaml`: the IMG pipeline
documentation, which specifies the GFF output of the pipeline that produced every NMDC file vendored
here, and the Blue Collar Bioinformatics parser, as an example of what consumers actually run.
