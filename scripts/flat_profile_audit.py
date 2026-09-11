#!/usr/bin/env python3
"""Audit a LinkML schema against a flat, scalar-only publishing profile.

Written because these numbers were hand-counted three times and wrong twice.
The first pass read only each class's `slots` list and missed classes that
declare `attributes` inline. The second did not follow `is_a` slot inheritance
and so counted three multivalued slots as single-valued. Both produced a clean
looking table.

The profile modeled here is the BRIDGE Data Catalog's: flat, scalar-valued
columns only, rejecting multivalued and class-valued slots. See
https://github.com/microbiomedata/nmdc-lakehouse/issues/342

The target schema is not vendored in this repository, because
https://github.com/biodatamodels/gff-schema carries no license, so this fetches
it. Pass a local path to audit something else.

Usage:
    uv run --with pyyaml python scripts/flat_profile_audit.py [path-or-url]
"""
import sys, urllib.request, yaml

# Pinned to the commit that produced the counts published in
# docs/model-comparison.md. Following `main` would let the documented
# reproduction command audit a future revision while the dated results stand.
GFF_SCHEMA_COMMIT = "cb31263471ab3855c3622c3be3d3f908db8be654"
DEFAULT = ("https://raw.githubusercontent.com/biodatamodels/gff-schema/"
           f"{GFF_SCHEMA_COMMIT}/src/schema/gff.yaml")


def load(src):
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "curl/8.7.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return yaml.safe_load(r.read())
    return yaml.safe_load(open(src))


def resolve(defn, key, slots):
    """Effective value of `key`, following is_a up the slot hierarchy."""
    if defn.get(key) is not None:
        return defn[key]
    parent, seen = defn.get("is_a"), set()
    while parent and parent not in seen:
        seen.add(parent)
        pv = slots.get(parent) or {}
        if pv.get(key) is not None:
            return pv[key]
        parent = pv.get("is_a")
    return None


def has_identifier(cn, C, S):
    """Does this class have an identifier, including inherited ones?

    Checks every slot the class effectively has, across its own lineage, and
    resolves the `identifier` flag through slot `is_a` as well. An earlier
    version looked only at directly declared slots with a directly declared
    flag, which misclassified a subclass whose identity is inherited as a value
    object.
    """
    for n in class_slot_names(cn, C):
        defn = dict(S.get(n) or {})
        for anc in reversed(lineage(cn, C)):
            defn.update((C[anc].get("attributes") or {}).get(n) or {})
            defn.update((C[anc].get("slot_usage") or {}).get(n) or {})
        if resolve(defn, "identifier", S):
            return True
    return False


def lineage(cn, C, seen=None):
    """The class's own name followed by its ancestors, in precedence order.

    Precedence is the class itself, then its is_a chain, then its mixins, which
    is the order a definition should be looked up in.
    """
    seen = seen or set()
    if cn in seen or cn not in C:
        return []
    seen.add(cn)
    out = [cn]
    c = C[cn]
    if c.get("is_a"):
        out += lineage(c["is_a"], C, seen)
    for m in c.get("mixins") or []:
        out += lineage(m, C, seen)
    return out


def class_slot_names(cn, C, seen=None):
    """Slot names on a class, including those inherited via is_a and mixins.

    A class that shares slots through inheritance would otherwise be
    undercounted, which matters for any schema other than the pinned one.
    """
    seen = seen or set()
    if cn in seen or cn not in C:
        return []
    seen.add(cn)
    c = C[cn]
    names = []
    for parent in ([c.get("is_a")] if c.get("is_a") else []) + list(c.get("mixins") or []):
        for n in class_slot_names(parent, C, seen):
            if n not in names:
                names.append(n)
    for n in list(c.get("slots") or []) + list(c.get("attributes") or {}):
        if n not in names:
            names.append(n)
    return names


def audit(doc):
    C = doc.get("classes") or {}
    S = doc.get("slots") or {}
    E = set(doc.get("enums") or {})
    T = set(doc.get("types") or {})
    rows = []
    for cn, c in C.items():
        for sn in class_slot_names(cn, C):
            defn = dict(S.get(sn) or {})
            # Walk ONLY this class's own lineage, from the most distant
            # ancestor inwards, so a nearer definition overrides a farther one
            # and an unrelated class that happens to use the same slot name
            # cannot supply it. Scanning every class made the result depend on
            # dictionary order.
            for anc in reversed(lineage(cn, C)):
                defn.update((C[anc].get("attributes") or {}).get(sn) or {})
                defn.update((C[anc].get("slot_usage") or {}).get(sn) or {})
            rng = resolve(defn, "range", S)
            mv = bool(resolve(defn, "multivalued", S))
            if rng in C:
                kind = "class"
            elif rng in E:
                kind = "enum"
            elif rng in T:
                kind = "type"
            elif rng is None:
                kind = "unset"
            else:
                kind = "builtin"
            if not mv and kind != "class":
                group, becomes = "admissible", "scalar column"
            elif mv and kind == "class":
                group, becomes = "multivalued class reference", "child or junction table"
            elif mv:
                group, becomes = "multivalued scalar", "ARRAY COLUMN OR JUNCTION TABLE (a decision)"
            elif has_identifier(rng, C, S):
                group, becomes = "identified class reference", "scalar id column plus a foreign key"
            else:
                group, becomes = "value object, no identity", "slots expand into the parent row"
            rows.append((cn, sn, kind, mv, rng, group, becomes))
    return rows


STD_IMPORTS = ("linkml:types", "linkml:mappings", "linkml:extensions",
               "linkml:annotations", "linkml:meta")


def check_imports(doc, src):
    """Refuse a schema whose imports we do not resolve.

    Classification only indexes definitions in the top-level file, so a slot
    ranged over an imported class would fall through to "builtin" and be
    counted as an admissible scalar. A wrong number that looks right is worse
    than a refusal, so this exits instead.
    """
    unresolved = [i for i in (doc.get("imports") or []) if i not in STD_IMPORTS]
    if unresolved:
        print(f"REFUSING to audit {src}\n", file=sys.stderr)
        print("It imports schemas this tool does not resolve, so any class ranged over a",
              file=sys.stderr)
        print("definition from them would be miscounted as an admissible scalar:\n", file=sys.stderr)
        for i in unresolved:
            print(f"    {i}", file=sys.stderr)
        print("\nMerge the imports into one file first, or extend this tool to follow them.",
              file=sys.stderr)
        sys.exit(2)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    doc = load(src)
    check_imports(doc, src)
    rows = audit(doc)
    print(f"source: {src}\n")
    w = max(len(r[0]) for r in rows) + 2
    for cn, sn, kind, mv, rng, group, becomes in rows:
        flag = "  " if group == "admissible" else "->"
        print(f"{flag} {cn:<{w}}{sn:<26}{kind:<9}mv={str(mv):<6}{group}")
    print()
    from collections import Counter
    counts = Counter(r[5] for r in rows)
    adm = counts.pop("admissible", 0)
    print(f"{len(rows)} class/slot pairs")
    print(f"  {adm} admissible under a scalar-only profile as written")
    print(f"  {sum(counts.values())} rejected:")
    for g, n in sorted(counts.items(), key=lambda x: -x[1]):
        becomes = next(r[6] for r in rows if r[5] == g)
        print(f"      {n}  {g:<28} -> {becomes}")
    mech = sum(n for g, n in counts.items() if g != "multivalued scalar")
    dec = counts.get("multivalued scalar", 0)
    print(f"\n  {mech} of the {sum(counts.values())} rejections are mechanical")
    print(f"  {dec} hinge on one representation decision")


if __name__ == "__main__":
    main()
