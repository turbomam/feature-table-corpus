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

DEFAULT = ("https://raw.githubusercontent.com/biodatamodels/gff-schema/"
           "main/src/schema/gff.yaml")


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


def has_identifier(cls, slots):
    names = list(cls.get("slots") or []) + list(cls.get("attributes") or {})
    usage = cls.get("slot_usage") or {}
    for n in names:
        for d in ((cls.get("attributes") or {}).get(n), usage.get(n), slots.get(n)):
            if d and d.get("identifier"):
                return True
    return False


def audit(doc):
    C = doc.get("classes") or {}
    S = doc.get("slots") or {}
    E = set(doc.get("enums") or {})
    T = set(doc.get("types") or {})
    rows = []
    for cn, c in C.items():
        names = list(c.get("slots") or [])
        names += [n for n in (c.get("attributes") or {}) if n not in names]
        for sn in names:
            defn = dict(S.get(sn) or {})
            defn.update((c.get("attributes") or {}).get(sn) or {})
            defn.update((c.get("slot_usage") or {}).get(sn) or {})
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
            elif has_identifier(C[rng], S):
                group, becomes = "identified class reference", "scalar id column plus a foreign key"
            else:
                group, becomes = "value object, no identity", "slots expand into the parent row"
            rows.append((cn, sn, kind, mv, rng, group, becomes))
    return rows


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    rows = audit(load(src))
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
