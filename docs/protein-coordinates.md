# Protein coordinates

A domain or other hit reported in amino-acid positions has its CDS as `seqid`. Decided
2026-09-28 in [issue 40](https://github.com/turbomam/feature-table-corpus/issues/40); before
that, the hit's `seqid` was the contig.

## The rule

A `Feature` with `coordinate_system: protein` has `start` and `end` in one-based, inclusive
amino-acid positions along the translation of one CDS. That CDS is the hit's `seqid`, and it is
also the hit's only `parent`. The CDS itself is an ordinary contig-coordinate feature, so its own
`seqid` is the contig.

```yaml
- feature_id: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091
  seqid: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1        # the contig
  type: CDS
  start: 63
  end: 1091
  coordinate_system: contig
- feature_id: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091_168_312
  seqid: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091  # the CDS
  type: PF13358
  start: 168                                          # residue 168 of the CDS translation
  end: 312
  coordinate_system: protein
  parent: [nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091]
```

The model has no Protein class. A CDS already carries `translated_sequence`, and in the
prokaryotic sources here (NMDC and IMG) one CDS row translates to one protein, so the CDS stands
for its protein.

The Dataset validator (`scripts/validate_closed.py`) refuses:

- a protein-coordinate feature whose `seqid` names a contig, with a message saying the CDS is
  needed;
- one whose `seqid` names anything but a contig-coordinate CDS;
- one whose `parent` is not that same CDS;
- a contig-coordinate feature whose `seqid` names a feature;
- a hit that ends past its CDS's `translated_sequence`, when the translation is present;
- an ID used as both a `contig_id` and a `feature_id`.

## Why

- The GFF3 specification defines column 1 as the landmark "used to establish the coordinate
  system for the current feature"
  (https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md). A contig does
  not establish amino-acid positions; the protein does.
- Chado locates a feature on `srcfeature_id`, a foreign key to `feature`, so any feature,
  including a protein, can be the landmark (docs/model-comparison.md).
- NMDC's own hit files already put the protein in column 1. Keeping it there needs no
  re-interpretation of the source.
- A tool that joins on `seqid`, `start` and `end` without looking at `coordinate_system`, such as
  polars-bio's `overlap`, now cannot compare amino-acid offsets with contig bases in a validated
  Dataset: the validator refuses an ID used as both a contig and a feature, so a CDS ID never
  matches a contig ID. Under the old shape that join was wrong unless the caller knew to add
  `coordinate_system` to the key. The polars-bio behavior is read from its join signature, not
  run on our data.
- Hits are most of NMDC's feature data: about 62.7M of 85.8M sampled rows, measured in
  https://github.com/microbiomedata/nmdc-lakehouse/pull/364. That PR wrote Parquet locally and
  left loading into BERDL out of scope, and none had been loaded when this was decided on
  2026-09-28, so changing the shape cost a regenerated export, not a migration.

## Querying

Overlap within one protein is the same query as overlap within one contig, with the CDS ID as
the reference:

```sql
SELECT feature_id, type, start, "end"
FROM feature
WHERE coordinate_system = 'protein' AND seqid = ? AND start <= ? AND "end" >= ?;
```

After validation only protein-coordinate features name a CDS as `seqid`, so the
`coordinate_system` condition changes nothing there; it keeps the query right on data that has not
been validated. To reach a hit's contig, go through its CDS:

```sql
SELECT hit.feature_id, hit.type, cds.seqid AS contig
FROM feature hit JOIN feature cds ON hit.seqid = cds.feature_id
WHERE hit.coordinate_system = 'protein';
```

In the schema, `Feature.seqid` is `any_of` Contig or Feature, while `LocationPart.seqid` stays a
Contig. One column cannot be a foreign key to two tables, so the DuckDB loader
(`scripts/build_duckdb.py`) has no foreign key on `feature.seqid`; the validator checks it before
loading.

## Alternatives

**Keep the contig as `seqid`.** This was the model until 2026-09-28 (`nmdc-pfam-protein/2.0.0`).
It is cheapest to keep, and the contig is one column away. It contradicts GFF3, and any join on
`seqid` has to remember `coordinate_system` or it silently mixes residues with bases. Rejected
for that reason.

**Add an alignment-target structure.** GFF3 writes a hit's position on the thing it matched as
`Target=id start end [strand]`, with an optional CIGAR-like `Gap`. NMDC writes the same idea with
its own keys (`model_start`, `model_end`, `subject_start`, `subject_end`), which the model keeps
as untyped attribute strings. A typed target (ID, start, end, strand, alignment) would hold
either form. This answers a different question, where on the Pfam model or reference protein
the hit aligns, so it does not replace the rule above. It was added as `Feature.target` in
https://github.com/turbomam/feature-table-corpus/issues/94, and `nmdc-pfam-protein` fills it from
`model_start` and `model_end`.

**A separate Protein class as the landmark.** The hit's `seqid` would name a Protein record that
points to its CDS. That repeats what the CDS already holds, its identity and translation, for no
source here that needs it. It would be worth revisiting for a source where one protein comes
from several CDS parts, as in eukaryotic annotation such as Phytozome, where each CDS part has
its own ID. For those sources the landmark would be the transcript or a joined CDS; this
decision does not settle that case.

**Chado's ranked locations.** Chado gives one feature several ranked `featureloc` rows, so a
hit can be located on the protein and on the genome at once. The model has one scalar location
per feature, and adding a second location for the same feature is a larger change than any
source here requires.

**KBase CDM associations.** The KBase Common Data Model records a hit as an association between
a protein and a domain, with no coordinates. That loses the domain positions that BERIL queries
ask for, so it was not considered further.

## What changed with this rule

- `nmdc-pfam-protein` moved to 3.0.0, because its mapping changed; a 2.0.0 bundle is refused as
  an unsupported profile.
- Both example Datasets, the converter, the validator, the DuckDB loader and its overlap query,
  the schema diagram and the flat-profile audit follow the rule.
- The NMDC lakehouse converter (`microbiomedata/nmdc-lakehouse`,
  `src/nmdc_lakehouse/feature_convert.py`) still writes the contig and changes separately.
