# Overlaps and conflicts with other work

Every known place where other people's schemas, tables or tools duplicate the BER feature model,
contradict it, or can't hold its data as it is. Collected 2026-10-02 from the sessions working on
this repository, nmdc-lakehouse and bridge-central-schema, then spot-checked against the sources
named in each row. [Prior art](prior-art.md) and the [model comparison](model-comparison.md) cover
the older, GFF-focused survey; this page is the running list, and it is meant to be kept current.

Each row says how the fact is known:

- **measured**: a command was run, with the date.
- **observed**: seen once in a run that was not set up to measure it, with the date.
- **read**: read from the source without running anything, with the date.

Colleagues call this work the "GenomeFeatures schema module" or the "unified BER model for
GenomeFeatures", and call a narrowing of the general class for one source a "GFF profile". In this
repository the same things are the BER feature model and its conversion profiles and dialect
schemas.

## Other models of a genome feature

| other work | what overlaps or conflicts | how known | tracked in |
|---|---|---|---|
| KBase CDM, https://github.com/kbase/cdm-schema, `src/linkml/cdm_bioentity.yaml` (MIT) | Defines its own `Contig`, `ContigCollection`, `Feature`, `EncodedFeature`, `Protein`, `StrandType`, `CdsPhaseType` and `ContigCollectionType`. Last push 2026-05-01. | read 2026-10-02 | https://github.com/turbomam/feature-table-corpus/issues/139 |
| https://github.com/biodatamodels/gff-schema | A second GFF schema. Last push 2021-11-09, no license, and it uses `SO:` CURIEs without declaring the `SO` prefix. | read 2026-10-02 (push date, license); 2026-09-29 (prefix) | not tracked |
| BRIDGE lakehouse registry, https://github.com/ber-data/lakehouse-registry, entry `schema-jgi-gff` | Registered as experimental and points at biodatamodels/gff-schema, not at this model. The BRIDGE Schema Sources sheet (row 34, "JGI GFF") points at the same repository, and a note on that row from @valerie-autumn-skye says JGI doesn't use it. | read 2026-09-29 | not tracked; proposal to repoint after a release belongs with https://github.com/turbomam/feature-table-corpus/issues/9 |
| https://github.com/cmungall/bridge-schemas, `src/bridge_schemas/schema/jgi/smc.linkml.yaml` | Its own JGI SMC schema with `Contig`, `Gene`, `BGC` and `BGCAnnotation`, plus schemas inferred from IMG, Phytozome and MycoCosm databases in the same directory. No license. | read 2026-10-02 (license, file list); 2026-09-29 (classes) | not tracked |
| JGI database survey sheet (BRIDGE) | Describes four more feature-table shapes: SMC gene, Phytozome Feature, IMG_Core Gene and gene_pfam_families, and MycoCosm gene_feature. Most of its mapping cells are empty. | read 2026-09-30 | not tracked |
| BRIDGE harmonization sheet, `harmonization_targets` row 42, "Genomic feature" | Lists NMDC `GenomeFeature`, the nmdc-lakehouse-schema `GenomeFeatureFlat` and CDM `Feature` as the things to harmonize (shared slots start, end, strand, type, seqid, phase), and doesn't mention this model. | read 2026-09-30 | not tracked |
| nmdc-schema `GenomeFeature` (`src/schema/annotation.yaml`) | The class exists, but it has not been compared slot by slot with this model. | read 2026-10-02 (class exists in nmdc-schema main); no comparison made | not tracked |
| linkml/valuesets, `src/valuesets/schema/bio/genomics.yaml` (`ContigCollectionType`, `StrandType`, `CdsPhaseType`) and `genome_features.yaml` (`GenomeFeatureType`) | `ContigCollectionType` has the same seven values as ours, but valuesets spells them in uppercase (`ISOLATE`, `MAG`, ...) where this model uses lowercase, so serialized data differs. `StrandType` and `CdsPhaseType` carry the same meanings spelled differently. `GenomeFeatureType` names match the type of 44,312 of the corpus's 77,959 feature rows (56.8%) ignoring case, and 35,005 (44.9%) exactly. | measured 2026-09-30, recounted 2026-10-02 (coverage); read 2026-10-02 (file locations, casing) | https://github.com/turbomam/feature-table-corpus/issues/131#issuecomment-5913488027 |

## Inside bridge-central-schema

https://github.com/ber-data/bridge-central-schema/pull/5 (draft) imports this model next to the
measurements module. These rows are about that combination; see
[downstream copies](downstream-copies.md) for how the copy differs from v0.1.0.

| other work | what overlaps or conflicts | how known | tracked in |
|---|---|---|---|
| The root schema's `name` slot | The root and this model both define a slot named `name`, and `gen-project` stops with "Conflicting URIs ... for item: name". PR 5 renames ours to `display_name` with `alias: name`. Generated JSON Schema still keys on `name`, and the actinorhodin Dataset validates against it with 0 errors. Tools that read slot names instead of aliases see `display_name`, including SchemaView, which `scripts/lakehouse_export.py` uses to name Parquet columns. | measured 2026-10-02 (conflict, validation); read 2026-10-02, not run (SchemaView effect) | PR 5 body |
| LinkML Python generator | `gen-python` writes `EDAM.DATA[...]` but declares only `EDAM_DATA`, so the dotted prefix in v0.1.0 breaks the generated Python. It also leaves out `MIXS` and `EDAM` unless the root declares them. PR 5 changes the prefix to `EDAM` with `EDAM:data_NNNN` meanings; https://github.com/turbomam/feature-table-corpus/pull/163 changes it here to `EDAM_DATA` (same IRIs either way). | measured 2026-10-02 | https://github.com/linkml/linkml/issues/3458, https://github.com/linkml/linkml/issues/2632, PR 5 body |
| measurements module (`measurements.yaml`, from https://github.com/ber-data/bridge-central-schema/pull/2 by @sierra-moxon) | `numeric_value` is defined twice: a top-level `double` in measurements and a `float` attribute of our `Attribute`. After `gen-linkml --mergeimports` the global slot lists both classes in `domain_of` with range `double`, while `Attribute` keeps its own definition. | observed 2026-10-02 in the merged output; ranges read 2026-10-02 | not tracked |
| measurements module | The source text is `raw_value` on `MeasurementValue` and `value` on our `Attribute`, and both descriptions say they follow NMDC's AttributeValue pattern. | read 2026-10-02 | not tracked |
| measurements module | This model owns the top-level slots `type`, `source`, `start`, `end` and `note` with their GFF meanings. https://github.com/ber-data/bridge-central-schema/issues/4 proposes source-tracking slots for measurements; a slot there named `source` or `type` would collide. Names such as `source_system` or `source_field` would not. No class, enum or type names collide today. | read 2026-10-02 | not tracked |
| NMDC schema | `Attribute.numeric_value` has `exact_mappings: nmdc:numeric_value`, but NMDC's slot is `has_numeric_value`. | read 2026-10-02 (nmdc-schema main) | not tracked |
| Licenses and prefixes | Four prefixes under three licenses: `bridge:` (measurements, BSD-3), `bfm:` and `battr:` (this model, CC0 since https://github.com/turbomam/feature-table-corpus/pull/128), and `bridge_central_schema:` (root, Apache-2.0). `bridge:` names only the measurements module, so it reads like the root's prefix. | read 2026-10-02 | not tracked |

## nmdc-lakehouse

nmdc-lakehouse has its own converter, `src/nmdc_lakehouse/feature_convert.py`, that writes Parquet
in this model's shape without importing this repository ([how the pieces fit](how-it-fits.md)).
Columns compared on 2026-10-02 by listing the columns of `_feature_schema()` and `_contig_schema()`
in `feature_convert.py` at nmdc-lakehouse main 0e4619d against the columns of this repository's
export of the actinorhodin example at 4aaca94.

| table | difference from this repository's export | how known | tracked in |
|---|---|---|---|
| features | `feature_convert.py` has none of `stable_identifiers`, `score_type`, `is_representative`, `name`, `note`, `dbxref`, `ontology_term`, `translated_sequence`, `location` or `target`; its `attributes` entries have only `key` and `value`, without `attribute_cv_id` and `numeric_value`; it adds `source_data_object_type`; and it writes `phase` as `int8` where the export writes `int64`. | measured 2026-10-02 | `source_data_object_type` is in nmdc-lakehouse `docs/nmdc_feature_tables.md`; the rest is not tracked |
| contigs | `feature_convert.py` adds `assembly_contig_id`; has no `member_of`, `length_bp`, `topology` or `translation_table`. | measured 2026-10-02 | not tracked |
| contig_collections | The export writes it; `feature_convert.py` writes no such table. | measured 2026-10-02 | not tracked |
| any | No check of `feature_convert.py` output against the model. Two model changes in the week of 2026-09-28 each needed a matching nmdc-lakehouse pull request. | read 2026-10-02 | https://github.com/microbiomedata/nmdc-lakehouse/issues/381 |
| `nmdc.results.pfam_annotation_gff` in BERDL | The table loaded in May has an unrelated shape (`workflow_run_id`, `gene_id`, `pfam_accession`, `start`, `end`, `score`, `e_value` and more), and nothing maps it to this model. | observed 2026-10-01 (live BERDL check recorded in the issue) | https://github.com/microbiomedata/nmdc-lakehouse/issues/388 |

## BERDL and the BRIDGE catalog

BERDL is the KBase lakehouse that BRIDGE publishes to.

| limit | effect on this model | how known | tracked in |
|---|---|---|---|
| Iceberg v2 refuses a column whose type is unknown | A column that is null in every row loses its type when written through pandas, and the load fails with "unknown is not supported until v3". It happened for `stable_identifiers`, `source_files`, `is_selected` and `is_representative` in the actinorhodin load. Passing the Parquet schema explicitly fixes it. Iceberg accepted the `list<struct>` column `attributes`. | observed 2026-10-02 | not tracked |
| BRIDGE Data Catalog profile refuses ARRAY columns | The model has several: `parent`, `attributes`, `source_files`, `stable_identifiers`, `member_of`, `taxonomic_lineage`. The [flat profile](flat-profile.md) is this repository's answer. | read 2026-09-10 (catalog specification, as recorded in the issue) | https://github.com/microbiomedata/nmdc-lakehouse/issues/342 |
| Lakehouse registry can't link one schema to another | A registry entry for this model can't say how it relates to `schema-jgi-gff`. | read 2026-09-29 | https://github.com/ber-data/lakehouse-registry/issues/22, https://github.com/ber-data/lakehouse-registry/issues/21, https://github.com/ber-data/lakehouse-registry/issues/15 |

## Inside this repository

| conflict | how known | tracked in |
|---|---|---|
| The JGI data policy that governs the Phytozome Populus excerpt is recorded as undetermined in `model/examples/jgi-inputs.yaml`, but four `license` fields in `corpus/index.yaml` imply the legacy policy. | read 2026-10-02 | https://github.com/turbomam/feature-table-corpus/issues/161 |
| `corpus/index.yaml` records each source's terms of use, but the model has no slot that carries them into converted data. | read 2026-10-02 (issue comment) | https://github.com/turbomam/feature-table-corpus/issues/151 |

## Keeping this page current

Add a row when a session or a reviewer finds a new overlap, with how it is known and where it is
tracked. When a row is resolved, delete it and say so in the pull request that resolves it.
