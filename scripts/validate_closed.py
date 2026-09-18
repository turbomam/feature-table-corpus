#!/usr/bin/env python3
"""Validate a data file against a LinkML schema with additionalProperties: false.

linkml validate's default JSON Schema generation leaves additionalProperties open, so a
typo'd or undeclared field in the data passes silently. This regenerates the schema closed
and validates against it directly, which is the check that actually catches that class of
mistake. See schema/ber_feature_model.yaml and examples/one-biosample-sequencing/notes.md
for why this repository added it (2026-09-18): an earlier one-off version of this check had
a bug that made every real field look like an error, caught only by hand before trusting it.

Usage:
    uv run --with linkml --with jsonschema python scripts/validate_closed.py \
        SCHEMA DATA_FILE TOP_CLASS
"""
import sys

import yaml
import jsonschema
from linkml.generators.jsonschemagen import JsonSchemaGenerator


def subschema(schema: dict, class_name: str) -> dict:
    return {"$defs": schema["$defs"], "$ref": f"#/$defs/{class_name}"}


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    schema_path, data_path, top_class = sys.argv[1:4]

    gen = JsonSchemaGenerator(schema_path, not_closed=False)
    schema = gen.generate()

    data = yaml.safe_load(open(data_path))
    if not isinstance(data, dict):
        print("Top-level data must be a mapping (a single instance).", file=sys.stderr)
        sys.exit(2)

    # If the data is a whole top-level instance (e.g. a Dataset), validate it directly.
    # Otherwise treat top-level keys as slot names holding lists of a different class,
    # the shape this repository's example files use (contigs: [...], features: [...]).
    validator = jsonschema.Draft202012Validator(subschema(schema, top_class))
    errors = list(validator.iter_errors(data))

    for e in errors:
        print(f"ERROR at {list(e.path)}: {e.message}")
    print(f"{data_path}: {len(errors)} error(s) under the CLOSED schema for {top_class}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
