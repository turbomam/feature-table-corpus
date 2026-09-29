"""Derive a flat, scalar-only profile of the feature model, and flatten a Dataset to it and back.

    python3 scripts/flat_profile.py regenerate      (rewrites model/flat/ber_feature_model_flat.yaml)
    python3 scripts/flat_profile.py check
    python3 scripts/flat_profile.py schema OUT_YAML
    python3 scripts/flat_profile.py flatten DATASET_JSON OUT_JSON
    python3 scripts/flat_profile.py unflatten TABLES_JSON OUT_JSON
    python3 scripts/flat_profile.py roundtrip DATASET_JSON...

The nested model is the canonical form (https://github.com/turbomam/feature-table-corpus/issues/45).
This profile is derived from it with SchemaView, so it follows the model as it changes, for
catalogs that take scalar columns only:

- Each class the Dataset lists (ContigCollection, Contig, Feature) is a table, keyed by its
  identifier.
- A single-valued scalar, enum or identified-class reference is a column; a reference holds the
  other row's identifier.
- A single-valued value object without identity (Feature.location, Feature.target) expands into
  its owner's row, as <slot>_<field> columns.
- A multivalued slot is a child table named <table>_<slot>, keyed by the owner's identifier and
  an ordinal that keeps the list's order: feature_attributes(feature_id, ordinal, key, value),
  feature_parent(feature_id, ordinal, parent).

`flatten` writes {table: [row, ...]} as JSON; `unflatten` rebuilds the Dataset. `roundtrip`
requires every Dataset back unchanged. scripts/flat_profile_audit.py checks that the derived
schema has no field a scalar-only profile would reject.
"""
import argparse
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model/schema/ber_feature_model.yaml"
FLAT = ROOT / "model/flat/ber_feature_model_flat.yaml"
ROOT_CLASS = "Dataset"
# Slot constraints the flat columns keep, so a flat row the model would reject is rejected too.
CONSTRAINTS = ("minimum_value", "maximum_value", "pattern")


def _view():
    from linkml_runtime import SchemaView
    view = SchemaView(str(MODEL))
    view.merge_imports()
    return view


def identifier(view, class_name):
    found = [s.name for s in view.class_induced_slots(class_name) if s.identifier]
    return found[0] if found else None


def column_name(slot, field):
    """target + target_id is target_id; location + crosses_origin is location_crosses_origin."""
    return field if field.startswith(slot + "_") else f"{slot}_{field}"


def plan(view=None):
    """The flat layout: [(table, owner_class, collection_slot, columns, children)].

    columns is [(column, path, slot)], where path is the tuple of slot names from the owner record
    to the value. children is [(child_table, path, slot, fields)], where fields is None for a list
    of scalars or references, else [(column, field_slot)] for a list of value objects.
    """
    view = view or _view()
    classes = view.all_classes()
    tables = []

    def walk(class_name, table, prefix_path, prefix_name, columns, children):
        for slot in view.class_induced_slots(class_name):
            path = prefix_path + (slot.name,)
            name = column_name(prefix_name, slot.name) if prefix_name else slot.name
            target = slot.range if slot.range in classes else None
            if slot.multivalued:
                child = f"{table}_{name}"
                if target and not identifier(view, target):
                    fields = []
                    for field in view.class_induced_slots(target):
                        if field.multivalued or (field.range in classes and not identifier(view, field.range)):
                            raise ValueError(f"{child}.{field.name}: a nested list or value object inside a list")
                        fields.append((field.name, field))
                    children.append((child, path, slot, fields))
                else:
                    children.append((child, path, slot, None))
            elif target and not identifier(view, target):
                walk(target, table, path, name, columns, children)
            else:
                columns.append((name, path, slot))

    for collection in view.class_induced_slots(ROOT_CLASS):
        owner = collection.range
        table = snake(owner)
        columns, children = [], []
        walk(owner, table, (), "", columns, children)
        tables.append((table, owner, collection.name, columns, children))
    return tables


def snake(name):
    return "".join(("_" + c.lower()) if c.isupper() and i else c.lower() for i, c in enumerate(name))


def flat_range(view, slot):
    """A flat column's range: an identified-class reference becomes the identifier's text."""
    if slot.range in view.all_classes():
        return "string"
    return slot.range or "string"


def schema(view=None):
    """The derived flat LinkML schema, as a dict."""
    view = view or _view()
    tables = plan(view)
    classes, enums = {}, set()

    def attribute(slot, required=False):
        out = {"range": flat_range(view, slot)}
        for name in CONSTRAINTS:
            if getattr(slot, name, None) is not None:
                out[name] = getattr(slot, name)
        if slot.range in view.all_enums():
            enums.add(slot.range)
        if slot.range in view.all_classes():
            out["description"] = f"The {identifier(view, slot.range)} of a {snake(slot.range)} row."
        elif slot.description:
            out["description"] = " ".join(slot.description.split())
        if required:
            out["required"] = True
        return out

    for table, owner, _, columns, children in tables:
        key = identifier(view, owner)
        attrs = {}
        for name, path, slot in columns:
            # A column from an expanded struct is required only when the struct is present, which
            # a flat row can't say, so only a top-level slot keeps required.
            attrs[name] = attribute(slot, required=len(path) == 1 and bool(slot.required or slot.name == key))
            if name == key:
                attrs[name]["identifier"] = True
        classes[camel(table)] = {"description": f"One {owner}; derived from the nested model.",
                                 "attributes": attrs}
        rules = class_rules(view, owner, {name for name, path, _ in columns if len(path) == 1})
        if rules:
            classes[camel(table)]["rules"] = rules
        for child, path, slot, fields in children:
            attrs = {key: {"range": "string", "required": True,
                           "description": f"The {key} of the {table} row this belongs to."},
                     "ordinal": {"range": "integer", "required": True, "minimum_value": 0,
                                 "description": f"Position in {owner}.{'.'.join(path)}, from 0."}}
            if fields is None:
                attrs[slot.name] = attribute(slot, required=True)
            else:
                for name, field in fields:
                    attrs[name] = attribute(field, required=bool(field.required))
            classes[camel(child)] = {"description": f"{owner}.{'.'.join(path)}, one row per item.",
                                     "attributes": attrs}
    return {
        "id": "https://w3id.org/ber-data/gff-feature-model/flat",
        "name": "ber-feature-model-flat",
        "title": "BER feature model, flat scalar-only profile",
        "description": ("Generated by scripts/flat_profile.py from model/schema/ber_feature_model.yaml; "
                        "do not edit. The nested model is canonical."),
        "prefixes": {"linkml": "https://w3id.org/linkml/",
                     "bfmflat": "https://w3id.org/ber-data/gff-feature-model/flat/"},
        "default_prefix": "bfmflat",
        "default_range": "string",
        "imports": ["linkml:types"],
        "classes": classes,
        "enums": {name: enum_dict(view, name) for name in sorted(enums)},
    }


def class_rules(view, owner, direct):
    """The owner class's rules, copied when every slot they name is one of its direct columns.

    A rule naming a slot the profile moves into a struct column or a child table can't be
    written against one flat row, so it stops the derivation rather than being dropped.
    """
    from linkml_runtime.dumpers import json_dumper
    rules = []
    for rule in view.get_class(owner).rules or []:
        data = json.loads(json_dumper.dumps(rule))
        data.pop("@type", None)
        named = {name for part in ("preconditions", "postconditions", "elseconditions")
                 for name in ((data.get(part) or {}).get("slot_conditions") or {})}
        if not named <= direct:
            raise ValueError(f"{owner} rule names {sorted(named - direct)}, which aren't columns of its flat table")
        for conditions in (data.get(part) for part in ("preconditions", "postconditions", "elseconditions")):
            for name, condition in ((conditions or {}).get("slot_conditions") or {}).items():
                condition.pop("name", None)
        rules.append(data)
    return rules


def camel(table):
    return "".join(part.capitalize() for part in table.split("_"))


def enum_dict(view, name):
    enum = view.get_enum(name)
    values = {}
    for value, definition in enum.permissible_values.items():
        text = " ".join((definition.description or "").split())
        values[value] = {"description": text} if text else {}
    out = {"description": " ".join(enum.description.split())} if enum.description else {}
    return {**out, "permissible_values": values}


def get(record, path):
    for name in path:
        if not isinstance(record, dict) or name not in record:
            return None
        record = record[name]
    return record


def put(record, path, value):
    for name in path[:-1]:
        record = record.setdefault(name, {})
    record[path[-1]] = value


def unknown_fields(record, paths, prefix=()):
    """Dotted names of fields in record, or in a struct it holds, that no planned path reaches."""
    found = []
    for name, value in record.items():
        path = prefix + (name,)
        if path in paths:
            continue
        if isinstance(value, dict) and any(p[:len(path)] == path for p in paths):
            found += unknown_fields(value, paths, path)
        else:
            found.append(".".join(path))
    return sorted(found)


def key_column(columns):
    return next(name for name, path, slot in columns if slot.identifier and len(path) == 1)


def flatten(dataset, tables=None):
    tables = tables or plan()
    unknown = sorted(set(dataset) - {collection for _, _, collection, _, _ in tables})
    if unknown:
        raise ValueError(f"{unknown} are not Dataset slots; is this a Dataset?")
    out = {}
    for table, owner, collection, columns, children in tables:
        key = key_column(columns)
        rows = out.setdefault(table, [])
        for record in dataset.get(collection) or []:
            paths = [path for _, path, _ in columns] + [path for _, path, _, _ in children]
            unknown = unknown_fields(record, paths)
            if unknown:
                raise ValueError(f"{owner} {record.get(key)!r}: {unknown} are not slots of the model")
            row = {name: value for name, path, _ in columns if (value := get(record, path)) is not None}
            rows.append(row)
            for child, path, slot, fields in children:
                items = get(record, path) or []
                child_rows = out.setdefault(child, [])
                for ordinal, item in enumerate(items):
                    base = {key: record[key], "ordinal": ordinal}
                    if fields is None:
                        child_rows.append({**base, slot.name: item})
                    else:
                        extra = sorted(set(item) - {n for n, _ in fields})
                        if extra:
                            raise ValueError(f"{child} of {record[key]!r}: {extra} are not slots of the model")
                        child_rows.append({**base, **{n: item[n] for n, _ in fields if n in item}})
    return out


def unflatten(flat, tables=None):
    tables = tables or plan()
    expected = {}
    for table, _, _, columns, children in tables:
        key = key_column(columns)
        expected[table] = {name for name, _, _ in columns}
        for child, _, slot, fields in children:
            expected[child] = {key, "ordinal"} | ({slot.name} if fields is None else {n for n, _ in fields})
    unknown = sorted(set(flat) - set(expected))
    if unknown:
        raise ValueError(f"{unknown} are not tables of the flat profile")
    for table, rows in flat.items():
        for number, row in enumerate(rows):
            extra = sorted(set(row) - expected[table])
            if extra:
                raise ValueError(f"{table} row {number}: {extra} are not its columns")
    dataset = {}
    for table, owner, collection, columns, children in tables:
        key = key_column(columns)
        records, by_key = [], {}
        for row in flat.get(table) or []:
            record = {}
            for name, path, _ in columns:
                if name in row:
                    put(record, path, row[name])
            if record.get(key) in by_key:
                raise ValueError(f"{table}: {key} {record.get(key)!r} is on more than one row")
            records.append(record)
            by_key[record[key]] = record
        for child, path, slot, fields in children:
            for row in flat.get(child) or []:
                owner_record = by_key.get(row[key])
                if owner_record is None:
                    raise ValueError(f"{child}: {key} {row[key]!r} has no {table} row")
                items = get(owner_record, path)
                if items is None:
                    items = []
                    put(owner_record, path, items)
                if row["ordinal"] != len(items):
                    raise ValueError(f"{child}: {key} {row[key]!r} ordinal {row['ordinal']} is out of order")
                items.append(row[slot.name] if fields is None
                             else {n: row[n] for n, _ in fields if n in row})
        if records:
            dataset[collection] = records
    return dataset


def roundtrip(dataset, tables=None):
    """Problems for one Dataset; none means it came back unchanged."""
    tables = tables or plan()
    try:
        back = unflatten(flatten(dataset, tables), tables)
    except ValueError as error:
        return [str(error)]
    expected = {k: v for k, v in dataset.items() if v}
    return [] if back == expected else [f"the Dataset changed: {first_difference(expected, back)}"]


def first_difference(a, b):
    for kind in sorted(set(a) | set(b)):
        for x, y in zip(a.get(kind, []), b.get(kind, [])):
            if x != y:
                return f"{kind}: {json.dumps(x)[:200]} came back as {json.dumps(y)[:200]}"
        if len(a.get(kind, [])) != len(b.get(kind, [])):
            return f"{kind}: {len(a.get(kind, []))} in, {len(b.get(kind, []))} back"
    return "unknown"


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) if str(path).endswith((".yaml", ".yml")) else json.loads(text)
    # A conversion bundle or protein context carries its Dataset under "dataset".
    return data["dataset"] if isinstance(data.get("dataset"), dict) else data


def schema_text():
    return yaml.safe_dump(schema(), sort_keys=False, width=100)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema").add_argument("output", type=Path)
    for name in ("flatten", "unflatten"):
        command = commands.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("output", type=Path)
    commands.add_parser("roundtrip").add_argument("datasets", type=Path, nargs="+")
    commands.add_parser("check", help=f"fail if {FLAT.relative_to(ROOT)} is not what `schema` writes")
    commands.add_parser("regenerate", help=f"rewrite {FLAT.relative_to(ROOT)}, the one file this may overwrite")
    args = parser.parse_args(argv)
    if args.command == "regenerate":
        FLAT.write_text(schema_text(), encoding="utf-8")
        print(f"wrote {FLAT.relative_to(ROOT)}")
        return 0
    if args.command == "check":
        if FLAT.read_text(encoding="utf-8") != schema_text():
            print(f"{FLAT.relative_to(ROOT)} is out of date; run: just flat-profile", file=sys.stderr)
            return 1
        print(f"{FLAT.relative_to(ROOT)} matches the model")
        return 0
    if args.command == "roundtrip":
        failed = 0
        for path in args.datasets:
            problems = roundtrip(load(path))
            print(f"{'HELD' if not problems else 'FAILED'}  {path}" + "".join(f"\n  {p}" for p in problems))
            failed += bool(problems)
        return 1 if failed else 0
    if args.output.exists():
        print(f"output: {args.output} already exists, not overwritten", file=sys.stderr)
        return 1
    if args.command == "schema":
        text = schema_text()
    else:
        try:
            data = (flatten(load(args.input)) if args.command == "flatten"
                    else unflatten(json.loads(args.input.read_text(encoding="utf-8"))))
        except (ValueError, OSError, json.JSONDecodeError) as error:
            print(f"{args.command}: {error}", file=sys.stderr)
            return 1
        text = json.dumps(data, indent=1) + "\n"
    with open(args.output, "x", encoding="utf-8") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
