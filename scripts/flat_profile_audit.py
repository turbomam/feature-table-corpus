#!/usr/bin/env python3
"""Audit a LinkML schema against a flat, scalar-only publishing profile.

Use SchemaView to resolve imported definitions, inherited slots, mixins and slot
usage before classifying a field. Range expressions remain outside this audit's
scope and are rejected rather than guessed.

Usage:
    uv run --with linkml-runtime python scripts/flat_profile_audit.py [path-or-url]
"""
import sys
from collections import Counter
from copy import deepcopy

from linkml_runtime.utils.schemaview import SchemaView

# Preserve the dated comparison in docs/model-comparison.md.
GFF_SCHEMA_COMMIT = "cb31263471ab3855c3622c3be3d3f908db8be654"
DEFAULT = ("https://raw.githubusercontent.com/biodatamodels/gff-schema/"
           f"{GFF_SCHEMA_COMMIT}/src/schema/gff.yaml")
RANGE_EXPRESSIONS = ("any_of", "exactly_one_of", "none_of", "all_of", "range_expression")


def effective_slots(view, class_name):
    attributes = {}
    for ancestor in view.class_ancestors(class_name):
        for name, attribute in view.get_class(ancestor).attributes.items():
            attributes.setdefault(name, attribute)
    for slot in view.class_induced_slots(class_name):
        attribute = attributes.get(slot.name)
        if attribute and (attribute.is_a or attribute.mixins):
            # SchemaView currently skips slot inheritance for inline attributes.
            # Promote this class's effective declaration and its inline ancestors
            # in an isolated copy, then resolve them (including class slot_usage).
            # Class-local names must never pick up an unrelated class's declaration.
            scoped = SchemaView(deepcopy(view.schema))
            visited = set()

            def promote(name):
                if name in visited:
                    return
                visited.add(name)
                definition = attributes.get(name) or view.schema.slots.get(name)
                if definition is None:
                    return  # SchemaView will report the unresolved ancestor.
                if name in attributes:
                    for cls in scoped.schema.classes.values():
                        cls.attributes.pop(name, None)
                    scoped.schema.slots[name] = deepcopy(definition)
                for parent in [definition.is_a, *definition.mixins]:
                    if parent:
                        promote(parent)

            promote(slot.name)
            scoped.set_modified()
            slot = scoped.induced_slot(slot.name, class_name)
        yield slot


def audit(view):
    # Materialize imports in memory so isolated contexts retain their definitions.
    view.merge_imports()
    classes, enums, types = view.all_classes(), view.all_enums(), view.all_types()
    slots = {cn: list(effective_slots(view, cn)) for cn in classes}
    rows = []
    for cn in classes:
        for slot in slots[cn]:
            present = [key for key in RANGE_EXPRESSIONS if getattr(slot, key, None)]
            if present:
                raise ValueError(f"{cn}.{slot.name} uses {', '.join(present)}; range expressions are not resolved")
            rng = slot.range or "string"
            mv = bool(slot.multivalued)
            if rng in classes:
                kind = "class"
            elif rng in enums:
                kind = "enum"
            elif rng in types:
                kind = "type"
            elif rng == "string" and slot.range is None:
                kind = "implicit string"
            else:
                raise ValueError(f"{cn}.{slot.name} has unresolved range {rng!r}")
            if not mv and kind != "class":
                group, becomes = "admissible", "scalar column"
            elif mv and kind == "class":
                group, becomes = "multivalued class reference", "child or junction table"
            elif mv:
                group, becomes = "multivalued scalar", "ARRAY COLUMN OR JUNCTION TABLE (a decision)"
            elif any(s.identifier for s in slots[rng]):
                group, becomes = "identified class reference", "scalar id column plus a foreign key"
            else:
                group, becomes = "value object, no identity", "slots expand into the parent row"
            rows.append((cn, slot.name, kind, mv, rng, group, becomes))
    return rows


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    try:
        rows = audit(SchemaView(src))
    except (ValueError, OSError) as error:
        print(f"REFUSING to audit {src}: {error}", file=sys.stderr)
        return 2
    print(f"source: {src}\n")
    if not rows:
        print("0 class/slot pairs. Nothing to audit.")
        return 0
    width = max(len(r[0]) for r in rows) + 2
    for cn, sn, kind, mv, rng, group, becomes in rows:
        flag = "  " if group == "admissible" else "->"
        print(f"{flag} {cn:<{width}}{sn:<26}{kind:<9}mv={str(mv):<6}{group}")
    counts = Counter(r[5] for r in rows)
    admissible = counts.pop("admissible", 0)
    print(f"\n{len(rows)} class/slot pairs")
    print(f"  {admissible} admissible under a scalar-only profile as written")
    print(f"  {sum(counts.values())} rejected:")
    for group, count in sorted(counts.items(), key=lambda x: -x[1]):
        becomes = next(r[6] for r in rows if r[5] == group)
        print(f"      {count}  {group:<28} -> {becomes}")
    mechanical = sum(n for g, n in counts.items() if g != "multivalued scalar")
    decisions = counts.get("multivalued scalar", 0)
    print(f"\n  {mechanical} of the {sum(counts.values())} rejections are mechanical")
    print(f"  {decisions} hinge on one representation decision")
    return 0


if __name__ == "__main__":
    sys.exit(main())
