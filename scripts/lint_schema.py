#!/usr/bin/env python3
"""Run recommended LinkML lint with four exact strand-symbol exceptions."""
import argparse

from linkml.linter.linter import Linter, get_named_config


ALLOWED = {
    ("ber-feature-model", "standard_naming", "warning",
     f"Permissible value of Enum 'StrandEnum' has name '{symbol}'")
    for symbol in ("+", "-", ".", "?")
}


def allowed(problem):
    return (problem.schema_name, problem.rule_name, str(problem.level), problem.message) in ALLOWED


def lint(path):
    failures = []
    for problem in Linter(get_named_config("recommended")).lint(str(path)):
        if allowed(problem):
            continue
        failures.append(problem)
        print(f"{path}: {problem.level}: {problem.rule_name}: {problem.message}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schemas", nargs="+")
    args = parser.parse_args()
    failed = False
    for path in args.schemas:
        failed = bool(lint(path)) or failed
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
