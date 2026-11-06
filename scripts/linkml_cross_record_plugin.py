"""A LinkML validation plugin for the Dataset checks JSON Schema cannot express.

It follows linkml.validator.plugins.ValidationPlugin (linkml 1.11.1,
linkml/validator/plugins/validation_plugin.py) and reports the cross-record checks in
validate_closed.dataset_errors as ValidationResults: unknown parent, parent on another contig,
duplicate IDs, end beyond the contig's length_bp, parent cycles, and the rest of that function.
Run it beside JsonschemaValidationPlugin, which checks shape, types and enums.

dataset_errors expects data that already matches the closed Dataset JSON Schema, and a
plugin can't see another plugin's results, so this plugin checks the shape itself with the
JSON Schema validator ValidationContext caches, and skips the cross-record checks with one INFO
result when the shape is wrong. See docs/linkml-gff-validation.md.
"""
from linkml.validator.plugins import ValidationPlugin
from linkml.validator.report import Severity, ValidationResult

from validate_closed import dataset_errors

RESULT_TYPE = "ber_feature_model cross-record"


class CrossRecordPlugin(ValidationPlugin):
    """Yield one ERROR per cross-record problem in a Dataset instance.

    :param include_range_class_descendants: passed to the shape check; the default matches
        JsonschemaValidationPlugin's, so both plugins share one cached JSON Schema validator
    """

    def __init__(self, *, include_range_class_descendants=True) -> None:
        self.include_range_class_descendants = include_range_class_descendants

    def process(self, instance, context):
        if context.target_class != "Dataset":
            return
        shape = context.json_schema_validator(
            closed=True, include_range_class_descendants=self.include_range_class_descendants)
        if next(shape.iter_errors(instance), None) is not None:
            yield ValidationResult(
                type=RESULT_TYPE, severity=Severity.INFO, instance=instance, instantiates=context.target_class,
                message="cross-record checks skipped: the instance does not match the closed Dataset schema")
            return
        for message in dataset_errors(instance):
            yield ValidationResult(type=RESULT_TYPE, severity=Severity.ERROR, instance=instance,
                                   instantiates=context.target_class, message=message)
