# The four models, compared decision by decision

Read before designing a unified model. Two things to take from it: the one written off as a dead
draft addresses more of the hard cases than either active model, and there is textual evidence that
three of the four may not be independent efforts, which this document treats as a hypothesis rather
than a conclusion.

All claims below are *read* from the sources on 2026-09-11: the schema at
https://github.com/biodatamodels/gff-schema (`src/schema/gff.yaml`), the KBase Common Data Model
vendored here at `specs/kbase_cdm_bioentity.yaml`, the NMDC schema at
`src/schema/annotation.yaml` in `microbiomedata/nmdc-schema`, and the Chado tables vendored here at
`specs/chado_1.4_feature_tables.sql`.

## Three of the four may share a lineage, and one shared string is not evidence

Stated as a hypothesis throughout. The textual evidence below is real and the conclusion it
supports is not settled; the caveat at the end of this section says what would settle it.

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
specification, checked 2026-09-11. That rules out the obvious shared source, which is why the string
carries weight where the circular comment does not.

It does not prove inheritance. Independent phrasing, or a fourth source none of these documents
cites, remain possible. **Treat shared lineage as a hypothesis supported by textual similarity**, and
note what would settle it: commit history in either repository showing the text arriving from the
other, or an author saying so. Neither has been checked.

## Decision by decision

| Design decision | gff-schema | KBase Feature | NMDC GenomeFeature | Chado |
|---|---|---|---|---|
| Models the whole file or one table | **`gff document` class holding both `sequences` and `features`** | feature only | feature only | relational, seven tables |
| seqid | **range `seq`, an object** | not declared. `Feature` has only `feature_id` and `hash` plus scalar attributes; `contig_id` belongs to `Contig` | `string`, carrying a TODO to change it | `srcfeature_id`, a foreign key to `feature` |
| type constrained to Sequence Ontology | **pattern `^SO:\d+`** | `LocalCurie` matching `SO:xxxxxx`, constrained to children of `sequence_feature` | `type` plus a `feature_type` string whose description is "TODO: Yuri to write" | `type_id`, a foreign key to `cvterm` |
| phase | **`phase_enum`: 0, 1, 2** | `CdsPhaseType` | integer, minimum 0, maximum 2 | `phase int` on `featureloc`, unconstrained |
| strand | **`strand_enum`: `+`, `-`, `.`, `?`** | `StrandType` | no range, carrying a TODO to add an enum | `strand`, a smallint |
| score | slot defined and not attached to the feature class | **replaced by `e_value` and `p_value`** | absent | `rawscore`, `normscore` and `significance` on `analysisfeature`, which is outside the seven-table excerpt vendored here |
| Parent and hierarchy | **`Parent`, range `genome feature`, multivalued** | not declared in the vendored module. `EncodedFeature` carries its own identifier and no link to `Feature` | not modeled on the feature class | `feature_relationship`, with subject, object, type and rank |
| Column 9 modeled explicitly | **`genome feature attribute set` class: ID, Name, Parent, Ontology term** | flat attributes on the class | not modeled | **decomposed across five dedicated tables plus a catch-all** |
| Header directives and pragmas modeled | **yes: gff version, feature, attribute and source ontology URIs, species, sequence region, genome build** | no | no | no |
| Provenance of the assertion | no | `source_database`, `protocol_id`, `hash` | no | via `analysisfeature` and `dbxref` |
| Circular genomes | the convention quoted, plus an `Is circular` slot | the convention quoted | the convention quoted | not applicable |
| Partial coordinates | not addressed | not addressed | not addressed | **`is_fmin_partial`, `is_fmax_partial`** |
| Several locations per feature | no. `target location` is the range of the GFF3 `Target` attribute, an alignment target, not a second location for the feature | no | no | **`locgroup` and `rank` on `featureloc`** |

## What that table says

**None of the four keeps the score column as the specification defines it**, and each does something
different with it: the slot defined and left off the feature class, replaced by two typed slots,
omitted entirely, or moved to a separate analysis table with three named scores. These are not
independent data points, since the lineage section above shows three of the models share text. But
the handling is distinct in all four cases, and the specification's own admission that the semantics
are ill-defined is the obvious common cause. A unified model should not reintroduce it as one
column.

Note what the source supports and what it does not: `gff-schema` defines a `score` slot and does not
attach it to `genome feature`. That is what the file shows. Whether the omission was deliberate is
not recorded anywhere, and an earlier version of this document asserted that it was.

**The dormant draft is the only one that models a file rather than a feature table.**
`gff-schema` has a `gff document` class holding `features` and `sequences` side by side, so the
`##FASTA` section exists in the model where the other three have no place to put it. Note the limit:
its `seq` class carries an ID and a `has sequence string` slot whose range is an `NA` or `AA` enum,
so it models sequence *entries* and their type, not residues.

Chado does store residues, in `feature.residues text`, which an earlier version of this document
denied. So the accurate statement is narrower: `gff-schema` is the only one of the four that gives
the FASTA section a place at document level, and it is not the one that stores sequence content.

It is also the only one that models the header directives and pragmas as data, and the only one with
an explicit `seqid` slot ranged over a model class. Chado also treats the landmark as an entity, via
the `srcfeature_id` foreign key. KBase does not, in the vendored module: `Feature` declares no
landmark reference at all. So two of the four reach the landmark as an entity, and only `gff-schema`
does it as a named `seqid` slot, which is the change NMDC's own schema carries a TODO asking for.

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

## Is `gff-schema` compatible with a flat, scalar-only publishing profile?

Largely yes. Nine of the thirteen rejections are mechanical, and the remaining four share a single
representation decision.

The question matters because the BRIDGE Data Catalog's stated input profile is "Flat; scalar-valued
columns only," rejecting multivalued slots, class-valued slots, nested structures and inlined object
graphs. Tracked at https://github.com/microbiomedata/nmdc-lakehouse/issues/342 . On its face that
looks fatal for `gff-schema`, which is an object graph by design.

**These numbers are computed, not counted.** Reproduce them with
`uv run --with pyyaml python scripts/flat_profile_audit.py`. Two earlier hand counts were wrong: the
first read only each class's `slots` list and missed the classes that declare `attributes` inline,
and the second did not follow `is_a` slot inheritance, so it treated three multivalued slots as
single-valued. Both produced a clean-looking table.

| Under a scalar-only profile | Count |
|---|---|
| Admissible as written | 19 |
| Rejected | 13 |

The thirteen rejections are not thirteen problems. Grouped by what each becomes:

| What was rejected | Count | What it flattens to | Mechanical? |
|---|---|---|---|
| Multivalued scalar | 4 | array column or junction table | **No. One decision, four slots** |
| Identified class reference | 4 | scalar id column plus a declared foreign key | Yes |
| Multivalued class reference | 3 | child or junction table | Yes |
| Value object with no identity | 2 | its slots expand into the parent row | Yes |

So nine resolve without a judgement call, in three different ways, and the catalog accepts all three:
it supports declared foreign keys across multiple tables per dataset version, and a value object
with no identifier simply flattens into its parent row.

The four that remain are `Ontology term` on the attribute set, and the three ontology URI directives
on `gff document`, which inherit `multivalued: true` from an abstract `ontology URI` slot. All four
are multivalued scalars, so all four are answered by the same choice.

**Chado is the proof rather than the analogy, and it already solved the column 9 problem.** It is
the same model normalized this way and in production for twenty years, with `feature` separate from
`featureloc` and not one nested structure anywhere. More to the point, it does not put column 9 in
one place. It decomposes it across five tables, giving the structural tags their own and sending the
rest to a catch-all, and every one of those tables is scalar only:

| GFF3 column 9 | Chado table | Columns |
|---|---|---|
| `Parent` | `feature_relationship` | subject, object, type, rank |
| `Ontology_term` | `feature_cvterm` | feature, cvterm, publication, rank |
| `Dbxref` | `feature_dbxref` | feature, dbxref |
| `Alias` and `Name` | `feature_synonym` | synonym, feature, publication |
| everything else | `featureprop` | feature, type, value, rank |

So the open question in this document, how a multivalued column 9 attribute is represented under a
flat profile, has a twenty-year-old answer sitting in a schema nobody in the conversation has been
treating as a candidate: a dedicated junction table for each structural tag, and one catch-all
property table for the rest. Two earlier versions of this document got this wrong in opposite directions, first saying Chado
puts column 9 in one property table, then saying it uses one table per reserved tag. Neither is
right: `Alias` and `Name` share `feature_synonym`, and everything unreserved falls to
`featureprop`.

A flat scalar-only profile is close to a description of Chado. The question is not whether this
family of models can be flattened. One member of it has only ever existed flat.

## What this implies about scope

A unified model looks like reconciliation, not construction. The pieces exist and no two models hold
the same subset. The unresolved items are the ones no model addresses:

- How multivalued column 9 attributes are represented, which the BRIDGE Data Catalog's flat profile
  forces a decision on. Tracked at
  https://github.com/microbiomedata/nmdc-lakehouse/issues/342
- What happens to the database accessions currently sitting in column 3.
- Whether the model describes a file, a feature, or one evidence stream. NMDC production says these
  are different things, because the same feature appears across several per-database files.
