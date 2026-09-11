# Chado's status, and what a feature table should be expected to cover

Two questions a reviewer will ask about reusing Chado's design, and an answer to the scope question
underneath them. Claims are *measured* with a date, *read* from a source, or marked as a *judgement*.

## Chado is not maintained, and that is separable from whether it is right

**Measured 2026-09-11** against the GitHub API for `GMOD/Chado`:

| | |
|---|---|
| Last push | 2024-06-24 |
| Releases | none, ever |
| Open issues | 59 |
| Archived | no |
| Default branch | `1.4` |

Commits by year: 932 in 2011, then 26, 13, 0, 50, 2, 1, 31, 69, 7, 3, 15, and 34 in 2024. Nothing
since.

So there is a schema to read and learn from, and no project to depend on. Those are different
things, and the distinction matters for this work: Chado's decomposition of GFF3 column 9 into one
table per reserved tag, documented in [model-comparison.md](model-comparison.md), is the best
available answer to how a multivalued attribute survives a flat publishing profile. Borrowing that
answer costs nothing and takes on no dependency.

## The blocker is not age. It is one constraint

*Read from* `specs/chado_1.4_feature_tables.sql`, vendored here:

```sql
organism_id bigint not null,
constraint feature_c1 unique (organism_id, uniquename, type_id)
```

Every feature must belong to exactly one organism, and feature identity is **scoped by** organism.

That is incompatible with the data BER holds. A metagenome contig comes from a mixed community. An
unbinned contig has no organism assignment at all. A metagenome-assembled genome carries a
provisional taxonomy, and revising it changes the feature's uniqueness key.

**Measured 2026-09-11:** NMDC's `GenomeFeature` has ten slots and zero mentions of organism or
taxon. It deliberately does not tie a feature to an organism. Chado requires precisely what NMDC
cannot supply, and the fourteen NMDC annotation files vendored in this corpus are all metagenome
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
- No releases, so there is no versioned artifact to pin a dependency to.
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
