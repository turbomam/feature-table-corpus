# Validating GFF3 with LinkML's validator

This is a working skeleton of a GFF3 loader and one validation plugin for LinkML's validation framework, so a GFF3 file can be checked against [`model/schema/ber_feature_model.yaml`](../model/schema/ber_feature_model.yaml) with LinkML's `Validator` or with `linkml-validate`. It was written against linkml 1.11.1, the version pinned in `requirements-conversion.txt`.

LinkML validation has two steps. A loader reads a file and yields unvalidated instances, and validation plugins check each instance and yield `ValidationResult`s. The two pieces here follow those interfaces.

## The loader

[`scripts/linkml_gff3_loader.py`](../scripts/linkml_gff3_loader.py) defines `Gff3Loader`, a subclass of `linkml.validator.loaders.Loader`. It reads the file with the `gff3-contig/4.0.0` conversion profile, `import_source` in [`scripts/convert_features.py`](../scripts/convert_features.py), which in turn uses [`scripts/source_document.py`](../scripts/source_document.py). It passes `check_dataset=False`, so the converter skips its own closed Dataset check and leaves that to the plugins.

The loader yields one `Dataset` per file, with its contigs and features. It doesn't yield one `SequenceFeature` at a time because the checks that matter here compare records with each other, and a plugin can only return results from `process`, which sees one instance. `post_process` runs after the last instance but returns nothing, so a plugin that collected features one by one would have no way to report what it found.

`Gff3Loader` takes the file path, a `reference_context` (the converter requires one and won't guess it), and a `metadata_profile` (`generic`, `prodigal` or `ncbi`). Under `ncbi`, a `##sequence-region` that starts at 1 gives the contig's `length_bp`.

Some problems stop the conversion before there is a Dataset: `Is_circular=true` (code `circular-location`), a CDS phase outside 0, 1 and 2, bad percent escapes, more than one `ID` or `Name`, and a feature outside its declared sequence region, among others. The loader then raises `Gff3ConversionRefused` with the converter's code and message. It is a `click.ClickException`, so `linkml-validate` prints `Error: <file>: the gff3-contig/4.0.0 conversion refused this file [circular-location]: ...` and exits 1 instead of printing a traceback.

## The plugin

[`scripts/linkml_cross_record_plugin.py`](../scripts/linkml_cross_record_plugin.py) defines `CrossRecordPlugin`, a subclass of `linkml.validator.plugins.ValidationPlugin`. It calls `dataset_errors` from [`scripts/validate_closed.py`](../scripts/validate_closed.py) and yields one `ERROR` result per message. That covers:

- a parent ID that names no feature (`feature 'cds-1': unknown parent 'gene-X'`);
- a parent on a different contig;
- a duplicate feature, contig or collection ID;
- a feature whose end is beyond its contig's `length_bp`;
- parent cycles;
- and the rest of `dataset_errors`: start after end, unknown seqid, protein coordinates, translation tables, representative isoforms and attribute numbers.

`dataset_errors` expects data that already matches the closed Dataset JSON Schema, and one plugin can't see another plugin's results. So the plugin first checks the shape with the JSON Schema validator that `ValidationContext` caches, the same one `JsonschemaValidationPlugin` uses with its default settings. If the shape is wrong, it yields a single `INFO` result saying the cross-record checks were skipped, and `JsonschemaValidationPlugin` reports the shape errors. The plugin yields nothing when the target class isn't `Dataset`.

Run it after `JsonschemaValidationPlugin(closed=True)`, which checks types, required slots and enums.

## Running it

From Python, with `scripts/` on `sys.path`:

```python
from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin
from linkml_gff3_loader import Gff3Loader
from linkml_cross_record_plugin import CrossRecordPlugin

validator = Validator("model/schema/ber_feature_model.yaml",
                      validation_plugins=[JsonschemaValidationPlugin(closed=True), CrossRecordPlugin()])
loader = Gff3Loader("corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3",
                    reference_context="NC_001417.2", metadata_profile="ncbi")
report = validator.validate_source(loader, "Dataset")
```

From the command line:

```
just validate-gff3-linkml corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3 NC_001417.2 ncbi
```

The recipe writes a `linkml-validate` config file naming the loader and both plugins, and runs `PYTHONPATH=scripts linkml-validate --config <config> <file>`. `linkml-validate` finds custom loaders only in a config file's `data_sources`, by dotted class name, so `scripts/` has to be importable.

The recipe also passes the GFF3 file as a positional argument, which `linkml-validate` doesn't read when the config has `data_sources`. Without it, linkml 1.11.1 validates nothing and reports `No issues found`. The config's `data_sources` is declared as an `Iterable` ([cli.py line 22](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/cli.py#L22)), which pydantic 2 stores as a one-pass iterator, and when no positional source is given, [line 252](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/cli.py#L252) uses it up with `list()` before [line 274](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/cli.py#L274) builds the loaders. The test `test_linkml_validate_without_a_positional_source_validates_nothing` in [`tests/test_linkml_gff_validation.py`](../tests/test_linkml_gff_validation.py) will fail once LinkML changes this, and the positional argument can then go.

## What the tests show

[`tests/test_linkml_gff_validation.py`](../tests/test_linkml_gff_validation.py) runs the loader and plugin through LinkML's `Validator` and through `linkml-validate`:

- `NC_001417.2_2026-10-30.gff3` (MS2, linear) with the `ncbi` metadata profile gives no results.
- The negative controls in [`corpus/fixtures/malformed/`](../corpus/fixtures/malformed/) all derive from phiX174, whose region row carries `Is_circular=true`, so the converter refuses each of them with `circular-location` before any plugin runs. `dangling_parent.gff3` and `duplicate_id.gff3` are checked for that refusal.
- To reach the plugin, the test makes single-change copies of the MS2 file in a temporary directory: a dangling parent, one ID given to two features, a parent cycle, and a feature on a second contig whose parent is on the first. Each gives exactly the one expected `ERROR`.
- A feature end past the contig length can't reach the plugin through GFF3 under the `ncbi` profile, because `length_bp` comes from `##sequence-region` and the converter refuses a feature outside that region (`declared-region`). The test checks that refusal, then checks that the plugin reports `end exceeds contig length_bp` on an edited Dataset passed to `Validator.validate`.

## Left for Patrick

- Performance. `import_source` holds the whole file and the whole Dataset in memory, and JSON Schema then validates the Dataset as one instance. Nothing here has been timed on a large file.
- Row-level checks still live inside the conversion in `scripts/convert_features.py` (`gff_feature` and `attributes`): phase, percent escapes, `ID`, `Name` and `product` cardinality, score precision, and declared sequence regions. They stop at the first problem and arrive as an exception rather than as `ValidationResult`s. Moving them into a plugin would need a loader that yields rows without refusing them.
- Whether these belong in LinkML or in this repository. A GFF3 loader with no knowledge of this schema could be general, while `CrossRecordPlugin` depends on this schema's slot names.
- Whether `linkml-validate` should find loaders by file extension or entry point, so a `.gff3` file can be passed directly.

## LinkML source used (linkml 1.11.1)

- [validator/loaders/loader.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/loaders/loader.py), the `Loader` base class
- [validator/loaders/yaml_loader.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/loaders/yaml_loader.py), the example loader
- [validator/loaders/\_\_init\_\_.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/loaders/__init__.py), `default_loader_for_file`
- [validator/plugins/validation_plugin.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/plugins/validation_plugin.py), the `ValidationPlugin` base class
- [validator/plugins/jsonschema_validation_plugin.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/plugins/jsonschema_validation_plugin.py), the example plugin
- [validator/validation_context.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/validation_context.py), `ValidationContext`
- [validator/report.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/report.py), `ValidationResult` and `Severity`
- [validator/validator.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/validator.py), `Validator`
- [validator/cli.py](https://github.com/linkml/linkml/blob/v1.11.1/packages/linkml/src/linkml/validator/cli.py), `linkml-validate`
