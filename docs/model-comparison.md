# The four models, compared decision by decision

Read before designing a unified model. The headline is that the four are not four independent
efforts, and the one written off as a dead draft addresses more of the hard cases than either
active model.

All claims below are *read* from the sources on 2026-09-11: Chris Mungall's schema at
https://github.com/biodatamodels/gff-schema (`src/schema/gff.yaml`), the KBase Common Data Model
vendored here at `specs/kbase_cdm_bioentity.yaml`, the NMDC schema at
`src/schema/annotation.yaml` in `microbiomedata/nmdc-schema`, and the Chado tables vendored here at
`specs/chado_1.4_feature_tables.sql`.

## Three of the four share a lineage, and one shared string does not count

Scoped deliberately to the three LinkML models. Chado is relational and has no feature-class
description to compare, so it is outside this section.

The class descriptions are not merely similar.

| Model | Description of the feature class |
|---|---|
| `biodatamodels/gff-schema` | "A feature localized to an interval along a genome" |
| NMDC `GenomeFeature` | "A feature localized to an interval along a genome" |
| KBase Common Data Model `Feature` | "A feature localized to an interval along a contig." |

The first two are identical character for character. The third differs by one word. So a unified
model is a reconciliation of one family, not a greenfield design, and "three unconnected models" is
the wrong framing to walk into a room with.

Which came first is not established here. The identical string is evidence of shared ancestry, not
of a direction.

**One test worth running before trusting any shared string.** All three models also carry the
circular-genome convention in near-identical words, and that is *not* evidence of anything: the
sentence "For features that cross the origin of a circular feature (e.g. most bacterial genomes,
plasmids, and some viral genomes), the requirement for start to be less than or equal to end is
satisfied by making end = the position of the end + the length of the landmark feature" is verbatim
GFF3 specification text. Three models quoting the specification means three people read it.

The class description is different. "localized to an interval" appears nowhere in the GFF3
specification, checked 2026-09-11. That string had to come from one of these models into another,
which is why it carries weight and the circular comment does not.

## Decision by decision

| Design decision | gff-schema | KBase Feature | NMDC GenomeFeature | Chado |
|---|---|---|---|---|
| Models the whole file or one table | **`gff document` class holding both `sequences` and `features`** | feature only | feature only | relational, seven tables |
| seqid | **range `seq`, an object** | via a link to `Contig` | `string`, carrying a TODO to change it | `srcfeature_id`, a foreign key to `feature` |
| type constrained to Sequence Ontology | **pattern `^SO:\d+`** | `LocalCurie` matching `SO:xxxxxx`, constrained to children of `sequence_feature` | `type` plus a `feature_type` string whose description is "TODO: Yuri to write" | `type_id`, a foreign key to `cvterm` |
| phase | **`phase_enum`: 0, 1, 2** | `CdsPhaseType` | integer, minimum 0, maximum 2 | `phase int` on `featureloc`, unconstrained |
| strand | **`strand_enum`: `+`, `-`, `.`, `?`** | `StrandType` | no range, carrying a TODO to add an enum | `strand`, a smallint |
| score | slot defined and **deliberately not attached to the feature class** | **replaced by `e_value` and `p_value`** | absent | not applicable |
| Parent and hierarchy | **`Parent`, range `genome feature`, multivalued** | via `EncodedFeature` and related classes | not modeled on the feature class | `feature_relationship`, with subject, object, type and rank |
| Column 9 modeled explicitly | **`genome feature attribute set` class: ID, Name, Parent, Ontology term** | flat attributes on the class | not modeled | `featureprop` table |
| Header directives and pragmas modeled | **yes: gff version, feature, attribute and source ontology URIs, species, sequence region, genome build** | no | no | no |
| Provenance of the assertion | no | `source_database`, `protocol_id`, `hash` | no | via `analysisfeature` and `dbxref` |
| Circular genomes | the convention quoted, plus an `Is circular` slot | the convention quoted | the convention quoted | not applicable |
| Partial coordinates | not addressed | not addressed | not addressed | **`is_fmin_partial`, `is_fmax_partial`** |
| Several locations per feature | no. `target location` is the range of the GFF3 `Target` attribute, an alignment target, not a second location for the feature | no | no | **`locgroup` and `rank` on `featureloc`** |

## What that table says

**Nobody kept the score column.** Three independent models refused it in three different ways: the
slot defined and left off the class, replaced by two typed slots, or omitted entirely. The
specification says the semantics are ill-defined, and every modeler who read that sentence acted on
it. A unified model should not reintroduce it.

**The dormant draft is the only one that models a file rather than a feature table.**
`gff-schema` has a `gff document` class holding `features` and `sequences` side by side, so the
`##FASTA` section exists in the model where the other three have no place to put it. Note the limit:
its `seq` class carries an ID and a `has sequence string` slot whose range is an `NA` or `AA` enum,
so it models sequence *entries* and their type, not residues. Nothing in these four models stores
the sequence itself.

It is also the only one that models the header directives and pragmas as data, and the only one with
an explicit `seqid` slot ranged over a model class. That last point needs the qualifier: KBase
reaches the landmark through a link to `Contig` and Chado through the `srcfeature_id` foreign key, so
three of the four treat the landmark as an entity. Only `gff-schema` does it as a named `seqid` slot,
which is the change NMDC's own schema carries a TODO asking for.

**It also already supports the case that breaks tools.** `Parent` is multivalued with a range of
`genome feature`, so multiple parents are first class. That is the legal-but-widely-refused
construct in `data/derived-edge-cases/multiple_parents.gff3`.

**Each model carries something the others do not, and the counts are smaller than "only" suggests.**
Provenance of the assertion is modeled in KBase and in Chado, and absent from the other two. Partial
coordinates and several locations per feature are in Chado alone. File structure and the header
directives are in `gff-schema` alone. The circular convention is in three of the four, because all
three quote the specification for it.

None of these is a large piece of work. The risk in picking a base is losing what the others hold,
which is a shorter list than it first appears.

## The obstacle the table does not show

Measured 2026-09-11, documented in [columns-and-discretion.md](columns-and-discretion.md): seven of
the fourteen NMDC annotation file types put a database accession in column 3 rather than a Sequence
Ontology term. `PF00011`, `COG3666`, `TIGR02937`, `SM01408`.

Both gff-schema and the KBase Feature class constrain type to SO accessions. So real NMDC data fails
both constraints today, and the constraint is right while the data is what exists. That is a
decision for people, not for a schema: coerce at load, carry the accession in a different slot, or
relax the constraint.

## What this implies about scope

A unified model looks like reconciliation, not construction. The pieces exist and no two models hold
the same subset. The unresolved items are the ones no model addresses:

- How multivalued column 9 attributes are represented, which the BRIDGE Data Catalog's flat profile
  forces a decision on. Tracked at
  https://github.com/microbiomedata/nmdc-lakehouse/issues/342
- What happens to the database accessions currently sitting in column 3.
- Whether the model describes a file, a feature, or one evidence stream. NMDC production says these
  are different things, because the same feature appears across several per-database files.

## Is `gff-schema` compatible with a flat, scalar-only publishing profile?

Yes, and the flattening is mechanical for all but one slot.

The question matters because the BRIDGE Data Catalog's stated input profile is "Flat; scalar-valued
columns only," rejecting multivalued slots, class-valued slots, nested structures and inlined object
graphs. Tracked at https://github.com/microbiomedata/nmdc-lakehouse/issues/342 . On its face that
looks fatal for `gff-schema`, which is an object graph by design.

Measured 2026-09-11 across all 32 class and slot pairs in that schema:

| Under a scalar-only profile | Count |
|---|---|
| Admissible as written | 22 |
| Rejected | 10 |

But the ten rejections are not ten problems. Nine of them are a foreign key or a child table in a
normalized relational rendering, and the catalog supports declared foreign keys between multiple
tables per dataset version. Grouped by what they become:

| What was rejected | Count | What it flattens to |
|---|---|---|
| Single class-valued reference | 5 | Scalar id column plus a declared foreign key |
| Value object with no identity | 1 | Its slots expand into the parent row |
| Multivalued class reference | 3 | Child or junction table |
| Multivalued scalar | 1 | The only genuine array-or-junction choice |

Slot by slot:

| Slot | Why rejected | Flattened form |
|---|---|---|
| `gff document.sequence region` | class-valued | scalar id column plus a declared foreign key |
| `gff document.genome build` | class-valued | same |
| `genome feature.seqid` | class-valued | same |
| `sequence region value.seqid` | class-valued | same |
| `target location.seqid` | class-valued | same |
| `genome feature.has attributes` | class-valued | a value object with no identity, so its slots expand into the parent row |
| `gff document.sequences` | class-valued, multivalued | child table keyed on the document |
| `gff document.features` | class-valued, multivalued | child table keyed on the document |
| `genome feature attribute set.Parent` | class-valued, multivalued | junction table of feature and parent |
| `genome feature attribute set.Ontology term` | multivalued, scalar range | **the only genuine choice: array column or junction table** |

So nine of the ten resolve to shapes the catalog already accepts. Exactly one, a multivalued scalar,
lands on the open question in that issue.

**Chado is the proof rather than the analogy.** It is the same model already normalized this way and
in production for twenty years: `feature` separate from `featureloc`, hierarchy in
`feature_relationship` with subject, object, type and rank, column 9 in `featureprop`, and not one
nested structure anywhere. A flat scalar-only profile is close to a description of Chado. The
question is not whether this family of models can be flattened. One member of it has only ever
existed flat.

**What that means for scope.** A semantic model and a publishing profile are not competitors at the
same layer, and treating them as alternatives is the mistake to avoid. `gff-schema` says what a
feature is; the catalog profile says what bytes it may be published as. The mapping between them is
the flattener, which already exists in `microbiomedata/nmdc-lakehouse` and already implements all
three mechanisms above: scalar id columns for single references, child tables for inlined
multivalued slots, and junction tables for referenced multivalued slots.

One decision therefore unblocks both: whether a multivalued scalar becomes an array column or a
junction table. Answering it settles `Ontology term` here, the multivalued `Parent` attribute of
GFF3, and the 150 multivalued attributes in the flattened NMDC schema, all at once.
