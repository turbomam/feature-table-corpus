# Constructed conversion controls

These files were authored here on 2026-09-21, under the repository's CC0 terms.
They are not producer observations and were not copied from a vendored artifact.

- `discontinuous.gff3` describes two segments with the same feature ID. GFF3 can
  express this; the `gff3-contig/1.0.0` adapter rejects it because the core model
  currently uses one interval per identity.
- `empty.bed` tests an insertion interval of zero length. BED permits such
  intervals; `bed12-blocks/1.0.0` requires nonempty intervals and positive blocks.

These are profile rejection controls, not claims that a full-format validator
would reject the files. The tests also generate 60 positive cases per profile
with fixed seeds, along with malformed and out-of-profile cases. See
[the conversion report](../../../analyses/conversion-roundtrips/README.md).
