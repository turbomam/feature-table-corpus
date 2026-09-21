# Group artifacts into corpus, model, and analyses

Implemented in this branch on September 21, 2026, for
[issue #11](https://github.com/turbomam/feature-table-corpus/issues/11).

## Decision

Group collected evidence under `corpus/`, the proposed contracts and their instances
under `model/`, and source-specific measurements under `analyses/`. This replaces the
initial proposal to retain all paths and document their roles. The directories now
express those roles directly, with the [repository map](../repository-map.md) providing
navigation and reproduction guidance.

| Previous path | Maintained location | Role |
|---|---|---|
| `corpus.yaml` | `corpus/index.yaml` | Corpus inventory, provenance, licenses, and checksums |
| `PROVENANCE.md` | `corpus/PROVENANCE.md` | Dated acquisition and correction history |
| `data/nmdc/`, `data/ncbi-refseq/` | `corpus/sources/nmdc/`, `corpus/sources/ncbi-refseq/` | Preserved upstream source text |
| `data/derived-malformed/` | `corpus/fixtures/malformed/` | Deliberate specification violations |
| `data/derived-edge-cases/` | `corpus/fixtures/edge-cases/` | Deliberate semantic and consumer edge cases |
| `specs/` | `corpus/specifications/` | Prior-art schemas and specification extracts |
| `schema/` | `model/schema/` | This project's draft LinkML contracts and validation configuration |
| `examples/` | `model/examples/` | Worked instances, transformation guides, and source manifest |
| `profiles/nmdc-data-objects/` | `analyses/nmdc-data-objects/` | NMDC-specific catalogue and counts |
| `scripts/nmdc_selection.json` | `analyses/nmdc-selection/selection.json` | Saved source-selection report |

`docs/`, `scripts/`, `tests/`, `.github/`, and gitignored `local/` retain their roles.
The NMDC reports use `analyses/` so they are not confused with the model and conversion
profiles being defined in [#16](https://github.com/turbomam/feature-table-corpus/issues/16).
NMDC's vocabulary and observed frequencies remain one source of modeling evidence.

## Migration and compatibility

The move updates the index, generators, validation commands, tests, CI, and current
documentation links together. There are no duplicate authoritative copies or symlinks
at the old paths. Downstream scripts using old filesystem paths must update them.
Historical fixed-commit citations still point to the artifacts they originally cited.

Index paths, including `derived_from`, remain relative to the repository root even
though the index itself is now inside `corpus/`. The PR validation-report script reads
either index location when comparing against a historical Git revision.

The 21 upstream source files and three specification files retain their bytes. The
nine derived fixtures are regenerated with new provenance paths, and their indexed
sizes and checksums change accordingly. Their biological mutations are unchanged.
No corpus entry is added or removed by this migration.

The NMDC harvester now writes a fresh sampling to `local/nmdc-selection/selection.json`.
Review its errors and changed selections before promoting a new report to `analyses/`;
running it does not silently replace the dated report used for acquisition history.

## Placement rules

1. Add real producer files through the corpus index, with provenance and a known
   redistribution basis. Preserve source bytes. Index deliberate corpus mutations
   under `corpus/fixtures/`, with their source and transformation recorded.
2. Put prior-art model material in `corpus/specifications/`, with source scope and
   license. Put proposed contracts in `model/schema/` and their worked instances in
   `model/examples/`. Each example guide names its schema, sources, transformation,
   and validation command, including whether the transformation is curated.
3. Put source-specific measurements in `analyses/<analysis>/`, keeping provenance and
   regeneration instructions beside the outputs. Regenerate related prose, CSV, and
   JSON together rather than making independently edited copies in `docs/`.
4. Keep small inputs used only by unit tests under `tests/fixtures/`. They do not add
   observed producers to the corpus inventory.
5. Keep local inputs, caches, and generated experimental output in `local/<task>/`.
   Record retained inputs' URLs and checksums rather than relying on temporary paths.

## Documentation-site handoff

[Issue #12](https://github.com/turbomam/feature-table-corpus/issues/12) can publish the
maintained Markdown through a navigation layer covering corpus evidence, the draft
model and examples, source-specific analyses, and contributor guidance. Reuse these
files as the documentation source; select pages explicitly and exclude `local/`,
private research, raw trace exports, and database binaries.

This migration does not enable Pages. The eventual organizational home of the general
model remains [issue #9](https://github.com/turbomam/feature-table-corpus/issues/9).
