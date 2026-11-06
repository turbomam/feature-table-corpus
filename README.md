# feature-table-corpus

Real, traceable examples of GFF and other genome feature table content, and a draft unified LinkML model for genome features across DOE Biological and Environmental Research data sources.

[Documentation website](https://turbomam.github.io/feature-table-corpus/) · [Build or preview locally](docs/documentation-site.md)

The model and conversion profiles are drafts; source-specific observations are evidence for modeling, not universal requirements.

This repository is a staging ground for content that will move into https://github.com/doe-bridge/bridge-central-schema, the BRIDGE central LinkML schema. The feature model in `model/schema/ber_feature_model.yaml` and the Attribute module in `model/schema/attributes.yaml` are copied there through pull requests, and [downstream copies](docs/downstream-copies.md) records how those copies differ from the ones here. The corpus, converters and checks stay here to test the model against real files.

## Start here

1. [GFF validation and splitting: start here](docs/gff-validation-start-here.md) is for anyone picking up the GFF validator or the fast first-pass splitter. It lists the file kinds in this repository and the specification each one follows, and which lines of a file reach DuckDB today.
2. [How the pieces fit](docs/how-it-fits.md) shows how the feature model, its converters, the NMDC pipeline in [nmdc-lakehouse](https://github.com/microbiomedata/nmdc-lakehouse), BERDL and the BER central schema connect, and which version each depends on. [Overlaps and conflicts](docs/how-it-fits.md#overlaps-and-conflicts) lists where other people's schemas and tables duplicate or disagree with the model.
3. The [repository map](docs/repository-map.md) explains artifact roles and reproduction, and the [layout decision](docs/decisions/001-artifact-layout.md) records the directory reorganization.

Then, depending on what you need:

- The [corpus inventory](corpus/README.md) describes every group of source files, specifications and derived fixtures, with provenance and licenses. [corpus/index.yaml](corpus/index.yaml) is the index and source of truth for the corpus inventory.
- [docs/model-comparison.md](docs/model-comparison.md) compares the four existing models of a genome feature decision by decision, and answers whether they survive a flat publishing profile. This is the one to read if you only read one.
- [Chado and scope](docs/background.md#chado-and-scope) answers the two questions a reviewer asks first: is Chado maintained, and what should a feature table be expected to cover. Short answers: no, and metagenomics but not much else.
- [docs/columns-and-discretion.md](docs/columns-and-discretion.md) says how many fields each format has, which columns leave the writer discretion, and which get populated incorrectly in real data.
- The [annotated reading list](docs/background.md#reading-across-feature-table-formats), checked September 2026, covers literature beyond GFF-focused projects. It distinguishes reviews, comparative measurements, community recommendations, consumer documentation, and format/tool authors' claims.
- [model/schema/README.md](model/schema/README.md) and [model/examples/one-biosample-sequencing/README.md](model/examples/one-biosample-sequencing/README.md) cover the draft unified LinkML feature model (`model/schema/ber_feature_model.yaml`) and a worked example harmonizing one real biosample's sequencing against it. This curated case study has its own source-artifact manifest and uses a different biosample from the standalone NMDC corpus files.
- [Versioned conversion profiles](docs/conversion-profiles.md) and the [per-case preservation report](analyses/conversion-roundtrips/README.md) cover executable interchange. The GFF3, BED12, [NMDC Pfam](docs/protein-coordinates.md#the-nmdc-pfam-profile) and [INSDC location](docs/feature-locations.md) profiles separately test exact byte recovery and reconstruction from mapped fields, with unsupported cases reported explicitly.
- [Validating GFF3 with LinkML's validator](docs/linkml-gff-validation.md) runs the GFF3 profile as a LinkML loader, with a validation plugin for the cross-record checks. The [split prototype](analyses/splitter-prototype/README.md) and its [timing baseline](analyses/splitter-baseline/README.md) show what reaches DuckDB today and how long it takes.
- [Source documents](docs/source-documents.md) describes the parser and separate document model for scoped comments, directives, feature rows, and FASTA sections.
- The [actinorhodin walkthrough](docs/actinorhodin-walkthrough.md) follows one example from source file to BERDL table, and the [actinorhodin BGC exercise](analyses/bgc-query/README.md) connects retained RefSeq source evidence to genomic gene order, annotation lookup, signed distances and both conversion round trips. Run `just bgc-check` to reproduce it offline.

| Directory | Contents |
|---|---|
| [`corpus/`](corpus/README.md) | Source files, prior-art specifications, derived fixtures, and their index/provenance |
| [`model/`](model/) | Proposed schemas and worked examples of their instances |
| [`analyses/`](analyses/) | Source-specific catalogues, counts, and selection reports |
| [`docs/`](docs/) | Comparisons, design decisions, and interpretation |

## Running the checks

Use Python 3.11 or later, `uv`, and `just` 1.27 or later. Run `just` or `just --list` for grouped tasks; see [running tasks](docs/repository-map.md#running-tasks) for requirements, defaults, and the operations that change files or use the network.

```shell
just check                    # corpus, schema, example, and regression checks
just verify                   # index invariants and checksums
just verify-links             # also check upstream URLs (network)
just flat-profile-audit       # our feature model's flat-profile figures
just pr-validation            # PR report, auditing the pinned upstream GFF schema
just docs-build               # build the documentation site and check its links
```

The audit and report accept alternate schema paths or URLs. To audit the historical upstream schema explicitly, use:

```sh
just flat-profile-audit https://raw.githubusercontent.com/biodatamodels/gff-schema/cb31263471ab3855c3622c3be3d3f908db8be654/src/schema/gff.yaml
just pr-validation origin/main model/schema/ber_feature_model.yaml
```

The first command fetches the pinned upstream schema; the second produces a report using our local model instead. They measure different schemas and need not have matching totals.

## Licensing

Per entry, recorded in `corpus/index.yaml`. The NMDC files are CC BY 4.0 and require attribution to NMDC. The JGI IMG files are unrestricted data under the JGI Legacy Data Policy, which names no license; this repository asks for attribution, with the dataset DOI and acknowledgment given in each entry. The NCBI files are public domain. This repository's own contributions, meaning the index, the scripts, this README and the LinkML schemas (`model/schema/`, `model/dialects/` and the generated `model/flat/`), are CC0 1.0.

If you own content vendored here and would rather it were linked, open an issue and it will be moved to the linked tier.
