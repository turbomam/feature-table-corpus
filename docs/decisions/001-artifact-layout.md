# Keep artifact roles separate and simplify navigation

Decision proposed September 21, 2026, for [issue #11](https://github.com/turbomam/feature-table-corpus/issues/11).

## Problem

The repository contains upstream evidence, extracted prior models, proposed models,
curated examples, derived fixtures, analytical prose, and generated reports. File
extensions and names such as "schema" or "example" do not explain those distinctions.
Merging everything into one examples or schemas directory would conceal provenance
and make it harder to know which files may be edited or regenerated.

## Decision

Keep the current artifact paths. Add one [repository map](../repository-map.md), linked
from the root README, as the navigation authority. Use the existing artifact-specific
guides for detailed methods rather than copying their prose into the map.

The only new documentation locations are `docs/repository-map.md` and `docs/decisions/`.
No source files, fixtures, schema material, scripts, or reports move in this change:

| Current or proposed area | Destination | Reason |
|---|---|---|
| `corpus.yaml`, `PROVENANCE.md` | Unchanged | Inventory and acquisition history have different scopes and established links |
| `data/<producer>/` | Unchanged | Preserves the distinction between upstream bytes and repository-authored material |
| `data/derived-malformed/`, `data/derived-edge-cases/` | Unchanged | Existing generator, index, and CI encode this separation; validity measurement remains #2 |
| `specs/` | Unchanged | Prior-art schema/specification evidence stays separate from proposed contracts |
| `schema/`, `examples/` in #6/#15 | Keep their proposed paths | Reusable contracts and their worked instances remain distinct; example guides identify exact sources |
| `profiles/<source>/` | Unchanged | A source-specific catalogue does not define universal modeling requirements |
| `docs/`, `scripts/`, `tests/`, `.github/` | Unchanged | Narrative, implementation, and executable checks retain separate responsibilities |
| `local/` | Unchanged and gitignored | Downloaded inputs and generated scratch outputs must not become implicit published sources |

This identity mapping is intentional. A future move needs evidence that it improves
navigation enough to justify changing indexed paths, generators, tests, and external
links together. It must remove the old authoritative copy rather than leave two.

## Maintenance rules

1. Add real producer outputs through the corpus index with provenance and a known
   redistribution basis. Keep upstream bytes intact; place mutations in a clearly
   derived area with source and transformation recorded.
2. Add a prior model under `specs/` only with its source scope and license; add this
   project's proposed contract under `schema/`. A configuration file such as a lint
   rule set is not another biological schema.
3. Give each worked example a guide that names its exact schema, source artifacts,
   transformation or generation procedure, and validation command. State when a
   transformation is curated rather than automatically reproducible.
4. Keep a generated report's commands, pinned inputs, and data-use terms nearby. Update
   related CSV, JSON, and prose outputs as one generation result. Do not create a
   second editable copy of a profile report inside `docs/`.
5. Put persistent local work under `local/<task>/`, with retained inputs identified by
   their original URLs and checksums. Do not rely on machine-specific temporary paths
   as a source of reproducible evidence.
6. When a pending model/example PR merges, update the map's status and navigation links.
   Preserve fixed-commit citations where a document discusses a historical measurement.

## Documentation-site handoff

[Issue #12](https://github.com/turbomam/feature-table-corpus/issues/12) can publish these
same Markdown files through a navigation layer: orientation and artifact roles;
format/model evidence; proposed model and examples; source-specific profiles; and
contributor/reproduction guidance. Draft status and source scope belong on each page,
not just on the home page.

The site should select content explicitly. Include the maintained guides, relevant
source/schema download links, and reviewed generated reports. Exclude `local/`, raw
trace exports, private research files, unreviewed downloads, and database binaries.
Do not copy all repository or workspace files into a public site as a shortcut.

This decision creates no second documentation source tree and does not enable Pages.
The permanent organizational home of the general model remains [issue #9](https://github.com/turbomam/feature-table-corpus/issues/9),
independent of navigation within this repository. Cross-format expansion and fidelity
measurement are tracked in [issue #16](https://github.com/turbomam/feature-table-corpus/issues/16).
