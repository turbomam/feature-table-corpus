#!/usr/bin/env python3
"""Extract the distinct GFF column-9 keys Bakta's source can emit, by AST parse.

Written by a sibling session (mam-98, 2026-09-18) working the same BER feature model thread,
after two regex-based attempts (one from that session, one from this one) disagreed with each
other. AST parsing resolves the disagreement structurally rather than by pattern-matching harder:
`bc.CONSTANT_NAME` key expressions are resolved by an exact dict lookup against every string
constant in constants.py, so a prefix collision like `INSDC_FEATURE_PSEUDOGENE` against its own
`_TYPE_UNITARY`/`_TYPE_UNKNOWN`/`_TYPE_UNPROCESSED` siblings cannot happen, unlike a regex over
the constant names. Verified independently in this repository before trusting it: reproduced the
same 25 keys, same 124 parsed constants, zero unresolved key expressions.

Two keys that look like mistakes are real: `sequence` (gff.py, a PILER-CR CRISPR spacer feature's
nucleotide sequence written into column 9) and `score` (gff.py's `write_signal_peptide`, a legacy
`# <1.10.0 compatibility` path that writes the same value into both column 6 and column 9 in one
row). Read by hand, not just trusted from the parse, before counting them.

This complements Prokka's count in docs/columns-and-discretion.md, which does have a clean
one-shot shell extractor; Bakta's key assignment is spread across a dict-literal, subscript, and
tuple-unpacking style that a single regex pass reliably misses part of.

Usage:
    mkdir -p local/bakta
    curl -sL https://raw.githubusercontent.com/oschwengers/bakta/v1.12.1/bakta/io/gff.py -o local/bakta/gff.py
    curl -sL https://raw.githubusercontent.com/oschwengers/bakta/v1.12.1/bakta/constants.py -o local/bakta/constants.py
    python3 scripts/extract_bakta_keys.py local/bakta/gff.py local/bakta/constants.py
"""
import ast
import sys


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    gff_path, const_path = sys.argv[1:3]

    consts = {}
    ctree = ast.parse(open(const_path).read())
    for node in ctree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = node.value.value

    def keyname(expr):
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return expr.value
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name) and expr.value.id == 'bc':
            if expr.attr not in consts:
                print(f"  UNRESOLVED CONSTANT bc.{expr.attr}", file=sys.stderr)
                return None
            return consts[expr.attr]
        return None

    TARGETS = {'annotations', 'gene_annotations'}
    keys, unresolved = set(), []
    tree = ast.parse(open(gff_path).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in TARGETS:
                    k = keyname(t.slice)
                    if k:
                        keys.add(k)
                    else:
                        unresolved.append(ast.dump(t.slice)[:60])
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                for t in targets:
                    if isinstance(t, ast.Name) and t.id in TARGETS:
                        for kexpr in node.value.keys:
                            k = keyname(kexpr)
                            if k:
                                keys.add(k)
                            else:
                                unresolved.append(ast.dump(kexpr)[:60] if kexpr is not None else "dict unpacking")
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Tuple):
                    for el in t.elts:
                        if isinstance(el, ast.Subscript) and isinstance(el.value, ast.Name) and el.value.id in TARGETS:
                            k = keyname(el.slice)
                            if k:
                                keys.add(k)
                            else:
                                unresolved.append(ast.dump(el.slice)[:60])

    print(f"constants parsed: {len(consts)}")
    print(f"distinct GFF column-9 keys: {len(keys)}")
    for k in sorted(keys, key=str.lower):
        print(" ", k)
    if unresolved:
        print("UNRESOLVED KEY EXPRESSIONS:", *unresolved, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
