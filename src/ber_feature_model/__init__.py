"""Validate Datasets against the BER feature model, with the schema bundled.

    from ber_feature_model import validate
    errors = validate(dataset)          # a dict; [] means valid

    ber-feature-validate DATASET.yaml   # or .json; exit 0 when valid

The validator and schema are the ones in https://github.com/turbomam/feature-table-corpus
(scripts/validate_closed.py and model/schema/), packaged at the model version below so another
repository can pin it. See https://github.com/turbomam/feature-table-corpus/issues/142.
"""
import argparse
from importlib.resources import files
import sys

import yaml

from .validate_closed import load_data, make_validator, validation_errors

__version__ = "0.1.0"
__all__ = ["__version__", "schema_path", "validate", "main"]


def schema_path():
    """Path of the bundled ber_feature_model.yaml; attributes.yaml sits beside it."""
    return str(files(__package__) / "schema" / "ber_feature_model.yaml")


def validate(data, class_name="Dataset"):
    """Every schema and closed-model error for data, as strings; empty when valid."""
    return validation_errors(data, make_validator(schema_path(), class_name), class_name)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ber-feature-validate", description=__doc__.splitlines()[0])
    parser.add_argument("dataset", help="YAML or JSON file")
    parser.add_argument("--class", dest="class_name", default="Dataset", help="top class (default Dataset)")
    parser.add_argument("--version", action="version", version=f"ber-feature-model {__version__}")
    args = parser.parse_args(argv)
    try:
        data = load_data(args.dataset)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"{args.dataset}: {error}", file=sys.stderr)
        return 1
    errors = validate(data, args.class_name)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{args.dataset}: {len(errors)} error(s) against ber-feature-model {__version__}")
    return 1 if errors else 0
