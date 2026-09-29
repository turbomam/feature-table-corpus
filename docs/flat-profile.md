# Flat scalar-only profile

The model is nested on purpose: `parent`, `attributes`, `source_files`, `taxonomic_lineage` and
`location.parts` are lists or structs. The BRIDGE catalog prototype's architecture document
(https://github.com/ber-data/bridge-catalog-mvp, `docs/architecture.md`) takes scalar columns
only. [`model/flat/ber_feature_model_flat.yaml`](../model/flat/ber_feature_model_flat.yaml) is a
flat profile for such a catalog, for https://github.com/turbomam/feature-table-corpus/issues/45.
The nested model stays the canonical form: ingest nested, then flatten.

`scripts/flat_profile.py` derives the profile from the model with SchemaView, so it can't drift
from it:

- Each class a Dataset lists is a table keyed by its identifier: `contig_collection`, `contig`,
  `feature`.
- A single-valued scalar or enum is a column. A reference to an identified class, such as
  `Feature.seqid` or `LocationPart.seqid`, holds that row's identifier.
- A single-valued struct with no identifier expands into its owner's row: `Feature.target` gives
  `target_id`, `target_start`, `target_end`, `target_strand` and `target_gap`, and
  `Feature.location` gives `location_operator` and `location_crosses_origin`.
- A list is a child table `<table>_<slot>` keyed by the owner's identifier and an `ordinal` from
  0 that keeps the list's order, for example `feature_attributes(feature_id, ordinal, key, value)`,
  `feature_parent(feature_id, ordinal, parent)` and `feature_location_parts(feature_id, ordinal,
  seqid, start, end, ...)`.

`scripts/flat_profile_audit.py` finds that the model has 20 of 61 class/slot pairs a scalar-only
catalog would reject. The derived profile has 80, and it rejects none of them (measured
2026-09-29). Lists became child tables rather than array columns because the catalog document
rejects both multivalued and nested columns.

Required slots stay required. A top-level required slot, such as `Feature.seqid`, is a required
column. A struct's required fields, such as `target_id`, `target_start` and `target_end`, are
required once any of that struct's columns is present, written as class rules. A required list
inside a struct, such as `FeatureLocation.parts`, lives in a child table that one row's rules can't
see, so `unflatten` checks it: a Feature with a location must have at least one row in
`feature_location_parts`.

## Commands

- `just flat-profile` regenerates the schema after a model change;
  `tests/test_flat_profile.py` fails until it has been run.
- `python3 scripts/flat_profile.py flatten DATASET OUT` writes `{table: [row, ...]}` as JSON, and
  `unflatten` rebuilds the Dataset. Both refuse a field the model doesn't have, a child row with no
  owner, and ordinals out of order.
- `python3 scripts/flat_profile.py roundtrip DATASET...` requires each Dataset back unchanged.

The tests round-trip both harmonized examples, the BED12 conversion bundle, the NMDC Pfam protein
context, and [a fixture](../tests/fixtures/flat-profile/every-slot.json) that sets every slot of
the model. A new model slot fails the fixture's coverage test until the fixture sets it.
