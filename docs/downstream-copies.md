# Copies of the model in other repositories

The BER feature model is maintained here. Two other repositories carry a copy or a
re-implementation of it, and each can drift from this one. This page says which version each
follows, how it differs, and how to bring it back in line. Checked 2026-10-02.

## bridge-central-schema

| | |
|---|---|
| Where | https://github.com/ber-data/bridge-central-schema/pull/5, Add the BER feature model as an imported module (draft), files `src/ber_central_schema/schema/ber_feature_model.yaml` and `attributes.yaml` |
| Follows | This repository's [v0.1.0 release](https://github.com/turbomam/feature-table-corpus/releases/tag/v0.1.0) (commit 4aaca94), as stated in the copy's own `notes`. PR 5 head checked: 5e2a4b2. |
| Who updates it | Whoever opens the pull request that changes the model here also opens or updates the matching bridge-central-schema pull request, and each links the other (see the pull request template). |

Differences between the PR 5 copy at 5e2a4b2 and v0.1.0, from `diff` on 2026-10-02:

| difference | why | follow-up |
|---|---|---|
| Slot `name` is renamed `display_name`, with `alias: name` | The central root schema has its own `name` slot, and LinkML refuses two imported slots with one name. Data keys stay `name`. | A modeling decision for the maintainers of both schemas; see [overlaps and conflicts](overlaps-and-conflicts.md#inside-bridge-central-schema). |
| Prefix `EDAM.DATA` becomes `EDAM`, and enum meanings become `EDAM:data_NNNN` | The LinkML Python generator can't handle the dotted prefix (https://github.com/linkml/linkml/issues/3458). The IRIs are the same. | https://github.com/turbomam/feature-table-corpus/pull/163 (draft) renames the prefix here to `EDAM_DATA` instead, because this repository's linter flags `EDAM` as non-canonical, and adds a test that imports the model under a stub root schema. If both merge as they stand, the two copies spell the prefix differently for the same IRIs. |
| `tree_root: true` removed from `Dataset` | The central root schema chooses its own tree root. | None needed. |
| Evidence and decision-history `notes` removed or shortened, and the descriptions of `Feature` and `feature_id` shortened | The central copy keeps definitions only; the evidence stays here. | None needed, but a resync must keep these edits. |

### Bringing the copy back in line

1. Tag a release here.
2. In a bridge-central-schema branch, copy `model/schema/ber_feature_model.yaml` and
   `model/schema/attributes.yaml` from the tag.
3. Reapply the edits in the table above, and update the copy's `notes` to the new tag.
4. Run that repository's tests, then `diff` against the tag and check that only the listed
   differences remain.
5. Link the two pull requests to each other.

## nmdc-lakehouse

| | |
|---|---|
| Where | https://github.com/microbiomedata/nmdc-lakehouse, `src/nmdc_lakehouse/feature_convert.py`, documented in its `docs/nmdc_feature_tables.md` |
| Follows | No pinned version. It re-implements the model's rules without importing this repository. https://github.com/microbiomedata/nmdc-lakehouse/issues/382 asks for the README to say which version it follows. |
| Who updates it | A model change here that affects NMDC files needs a matching pull request there, as https://github.com/microbiomedata/nmdc-lakehouse/pull/374 and https://github.com/microbiomedata/nmdc-lakehouse/pull/377 were. |

Its column differences are listed under [nmdc-lakehouse](overlaps-and-conflicts.md#nmdc-lakehouse)
in the overlaps page. https://github.com/microbiomedata/nmdc-lakehouse/issues/381 asks for a CI
test there that validates its output with the installable validator, pinned to v0.1.0, so drift
fails there instead of in BERDL.
