# NMDC source-file selection

[`selection.json`](selection.json) is the saved selection report for the original
14 NMDC GFF examples described in the [acquisition history](../../corpus/PROVENANCE.md).
It records the smallest file found for each sampled type, with its URL, checksum,
workflow, and number of records sampled. It is not a complete DataObject census;
the separate [DataObject analysis](../nmdc-data-objects/README.md) has that scope.

Run `just nmdc-sample` from the repository root for a new live sampling.
It writes `local/nmdc-selection/selection.json` and reports missing types or request
errors to stderr. Review the result before replacing this dated report or changing
the corpus index. A later sample may select different files and does not recreate
the original acquisition. Upstream source bytes remain under `corpus/sources/`.

NMDC's data-use terms apply to the source metadata; the indexed source files carry
their individual provenance and license records in [the corpus index](../../corpus/index.yaml).
