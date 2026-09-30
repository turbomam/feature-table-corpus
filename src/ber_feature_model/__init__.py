"""Validate Datasets against the BER feature model, with the schema bundled.

    from ber_feature_model import validate
    errors = validate(dataset)          # a dict; [] means valid

    ber-feature-validate DATASET.yaml   # or .json; exit 0 when valid

The validator and schema are the ones in https://github.com/turbomam/feature-table-corpus
(scripts/validate_closed.py and model/schema/), packaged at the model version below so another
repository can pin it. See https://github.com/turbomam/feature-table-corpus/issues/142.
"""
import argparse
import json
from pathlib import Path
import sys

import yaml

from .validate_closed import _check_values, load_data, make_validator, validation_errors

__version__ = "0.1.0"
__all__ = ["__version__", "schema_path", "validate", "main"]


def schema_path():
    """Path of the bundled ber_feature_model.yaml; attributes.yaml sits beside it.

    LinkML reads the schema and its import by file path, so the package must be installed
    unpacked, as pip and uv install it, not imported from a zip archive.
    """
    return str(Path(__file__).with_name("schema") / "ber_feature_model.yaml")


def validate(data, class_name="Dataset"):
    """Every schema and closed-model error for data, as strings; empty when valid.

    data is judged as it would be written to JSON, the form the command reads, so a value
    JSON can't hold (NaN, a complex number, a Decimal, a numpy scalar) is an error.
    """
    try:
        _check_values(data)  # NaN, infinity and cycles, reported with their path
    except ValueError as error:
        return [str(error)]
    # jsonschema counts any number as a JSON number, so types JSON lacks would otherwise pass.
    try:
        data = json.loads(json.dumps(data, allow_nan=False))
    except (TypeError, ValueError) as error:
        return [f"not JSON data: {error}"]
    except RecursionError:
        return ["nested too deeply to validate"]
    return validation_errors(data, make_validator(schema_path(), class_name), class_name)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ber-feature-validate", description=__doc__.splitlines()[0])
    parser.add_argument("dataset", help="YAML or JSON file")
    parser.add_argument("--class", dest="class_name", default="Dataset", help="top class (default Dataset)")
    parser.add_argument("--version", action="version", version=f"ber-feature-model {__version__}")
    args = parser.parse_args(argv)
    # Same order and exit statuses as scripts/validate_closed.py's main: an unknown class is a
    # usage error (2), reported before the data is read; unreadable data is 1.
    try:
        validator = make_validator(schema_path(), args.class_name)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    try:
        data = load_data(args.dataset)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"{args.dataset}: {error}", file=sys.stderr)
        return 1
    errors = validation_errors(data, validator, args.class_name)
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{args.dataset}: {len(errors)} error(s) against ber-feature-model {__version__}")
    return 1 if errors else 0
