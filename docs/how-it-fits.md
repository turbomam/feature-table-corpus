# How the pieces fit

The BER feature model, the code that converts real annotation files into it, the NMDC pipeline
that uses it, and where its output goes. Read this first if you want to use, check or extend any
of them. Stated as of 2026-09-30.

## The pieces

| piece | where | what it does |
|---|---|---|
| Feature model | [`model/schema/ber_feature_model.yaml`](../model/schema/ber_feature_model.yaml), version 0.1.0, with [`attributes.yaml`](../model/schema/attributes.yaml) | The LinkML schema: `Dataset`, `Contig`, `ContigCollection`, `Feature`, `AlignmentTarget`, `FeatureLocation`, `LocationPart` and `Attribute`. Licensed CC0 1.0. |
| Dataset validator | [`scripts/validate_closed.py`](../scripts/validate_closed.py) | Checks a Dataset against the schema, then the rules JSON Schema can't express, such as parent links, protein coordinates and translation tables. The conversion profiles and dialect mappings in this repository run it. Other repositories can install it with the schema as the package `ber-feature-model`; see below. |
| Conversion profiles | [`scripts/convert_features.py`](../scripts/convert_features.py) and [`model/profiles/`](../model/profiles/) | Versioned, reversible converters for GFF3 (`gff3-contig/4.0.0`), NMDC Pfam hits (`nmdc-pfam-protein/5.0.0`), BED12 (`bed12-blocks/1.0.0`) and GenBank (`insdc-locations/1.0.0`). See [conversion profiles](conversion-profiles.md). |
| Source dialects | [`model/dialects/`](../model/dialects/), mapped to the model by [`model/transforms/`](../model/transforms/) and `scripts/*_map.py` | LinkML schemas for producers' own formats: IMG functional, per-method, assembled, taxon bundle, TMHMM and SignalP files, and Phytozome gene_exons GFF3 and annotation_info. |
| Corpus | [`corpus/`](../corpus/) | The real files the converters are tested against, with provenance and licenses in [`corpus/index.yaml`](../corpus/index.yaml). |
| Flat profile | [`model/flat/`](../model/flat/) | A scalar-only version of the model, generated from it, for catalogs that take only flat tables. |
| NMDC feature tables | [microbiomedata/nmdc-lakehouse](https://github.com/microbiomedata/nmdc-lakehouse), `src/nmdc_lakehouse/feature_convert.py`, documented in its [`docs/nmdc_feature_tables.md`](https://github.com/microbiomedata/nmdc-lakehouse/blob/main/docs/nmdc_feature_tables.md) | Picks which of an NMDC run's annotation files to use, drops observations repeated across files, and writes `features.parquet` and `contigs.parquet` in the model's shape. Run as `just feature-plan`, `feature-sample`, `feature-download`, `feature-check` and `feature-convert`. |
| BERDL | the KBase lakehouse | Where the NMDC Parquet is meant to be loaded. None has been loaded as of 2026-09-30. |
| Central schema | [ber-data/bridge-central-schema](https://github.com/ber-data/bridge-central-schema) | Where the model's elements are to be copied, keeping the code here ([issue 9](https://github.com/turbomam/feature-table-corpus/issues/9)). Not done yet; open questions are listed in [issue 131](https://github.com/turbomam/feature-table-corpus/issues/131#issuecomment-5913488027). |

## How they depend on each other

- The profiles, dialect mappings and the flat profile are generated from, or checked against, the
  model in this repository, in the same commit. `just check` runs all of them, and CI runs
  `just check` on every pull request.
- nmdc-lakehouse has its own converter for NMDC at scale. It follows the model's rules but does not
  import this repository, so the two can drift. A model change that affects NMDC files needs a
  matching change there, as https://github.com/microbiomedata/nmdc-lakehouse/pull/374 and
  https://github.com/microbiomedata/nmdc-lakehouse/pull/377 were.
  https://github.com/microbiomedata/nmdc-lakehouse/issues/381 asks for a CI test there that
  validates its output with this repository's validator, pinned to a model release.
- The central-schema copy is to be pinned to a release of this repository, not to main
  ([issue 131](https://github.com/turbomam/feature-table-corpus/issues/131)).

## What isn't in place yet

- No release is tagged, so nothing can pin a version yet
  ([issue 131](https://github.com/turbomam/feature-table-corpus/issues/131)).
- The converters are scripts, not part of the installable package
  ([issue 142](https://github.com/turbomam/feature-table-corpus/issues/142)).
- nmdc-lakehouse doesn't yet say which model version its tables follow
  (https://github.com/microbiomedata/nmdc-lakehouse/issues/382).

## Using the validator from another repository

The validator and the schema install together as the Python package `ber-feature-model`, whose
version is the model's version. Until a release is tagged, install from main:

```bash
uv add "ber-feature-model @ git+https://github.com/turbomam/feature-table-corpus"
uv run ber-feature-validate features.yaml # YAML or JSON; exit status 1 when invalid
```

```python
from ber_feature_model import validate
errors = validate(dataset)                # a dict shaped like Dataset; [] means valid
```

The package holds [`scripts/validate_closed.py`](../scripts/validate_closed.py),
[`scripts/feature_locations.py`](../scripts/feature_locations.py) and the two schema files,
copied unchanged at build time, so it runs the same checks as `just validate-example-closed`. The converters aren't
in it yet.

## Where to start

- To read the model: the [schema guide](../model/schema/README.md) and the class pages on this site.
- To convert a file: [conversion profiles](conversion-profiles.md) and the `just` tasks in the
  [repository map](repository-map.md).
- To see how far the converters can be trusted: the [round-trip evidence](../analyses/conversion-roundtrips/README.md)
  and [independent validation](../analyses/format-validation/README.md), both checked in CI.
