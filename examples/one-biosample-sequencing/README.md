# examples/one-biosample-sequencing/

- **`harmonized.yaml`** is the actual worked example: a representative slice of one real
  biosample's sequencing, harmonized against `schema/ber_feature_model.yaml`.
- **`notes.md`** is the full explanation: which real workflow runs this came from, why each
  finding here is represented exactly once (not duplicated across a roll-up file and the
  per-database file it duplicates or subsumes), and what was deliberately left out.

**This directory has no relationship to `corpus.yaml` or `data/nmdc/`.** Those index and hold a
separate set of standalone example files, from ten different biosamples, none of them the one
this case study uses (`nmdc:omprc-11-2t8ft192`). If you're looking for where this example's own
raw source files are, see `notes.md`'s "Reproducing" section; they are not vendored into this
repository (would be several MB across 76 files for one example) and are not the same files as
anything under `data/nmdc/`.

See `schema/README.md` for how to validate this file and what else it feeds into (a diagram, a
flat-profile audit, a DuckDB build).
