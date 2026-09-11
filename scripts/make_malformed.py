#!/usr/bin/env python3
"""Build malformed GFF3 cases from one real public-domain file.

Each output differs from the source by exactly one documented change, so the
file is traceable to a real origin and the defect is unambiguous. These are
DERIVED, not found in the wild: the corpus labels them that way, and they are
not evidence about what any real producer emits.

Every case is a failure mode named either in the Sequence Ontology GFF3
specification or in the AgBioData GFF3 recommendations.

Usage:
    python3 scripts/make_malformed.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data/ncbi-refseq/ncbi_refseq_phix174_GCF_000819615.1.gff")
OUT = os.path.join(ROOT, "data/derived-malformed")

HEADER = ("##gff3-corpus-note derived from {src}\n"
          "##gff3-corpus-note single change: {change}\n"
          "##gff3-corpus-note this file is DELIBERATELY INVALID; see corpus.yaml\n")


def rows(text):
    return [l for l in text.splitlines() if l and not l.startswith("#")]


def first_of_type(lines, t):
    for i, l in enumerate(lines):
        if l.split("\t")[2] == t:
            return i, l.split("\t")
    raise SystemExit(f"no {t} row in source")


def build():
    raw = open(SRC).read()
    lines = raw.splitlines()
    body = rows(raw)
    cases = {}

    # 1. CDS phase altered. The AgBioData headline failure: a misread phase
    #    yields a different amino acid sequence from identical coordinates.
    i, f = first_of_type(body, "CDS")
    f = list(f); f[7] = "1" if f[7] != "1" else "2"
    b = list(body); b[i] = "\t".join(f)
    cases["cds_phase_altered.gff3"] = ("CDS phase in column 8 changed to a value "
        "inconsistent with the coordinates", b)

    # 2. Parent pointing at an ID that is not defined anywhere in the file.
    i, f = first_of_type(body, "CDS")
    f = list(f)
    f[8] = f[8] + ";Parent=gene-DOES-NOT-EXIST" if "Parent=" not in f[8] else \
        ";".join(p if not p.startswith("Parent=") else "Parent=gene-DOES-NOT-EXIST"
                 for p in f[8].split(";"))
    b = list(body); b[i] = "\t".join(f)
    cases["dangling_parent.gff3"] = ("Parent attribute names an ID defined nowhere "
        "in the file", b)

    # 3. Raw semicolon inside an attribute value. Must be percent-encoded;
    #    unencoded it silently splits one attribute into two.
    i, f = first_of_type(body, "CDS")
    f = list(f); f[8] = f[8] + ";product=coat protein; putative"
    b = list(body); b[i] = "\t".join(f)
    cases["unescaped_semicolon.gff3"] = ("an attribute value contains a raw "
        "semicolon instead of %3B", b)

    # 4. Coordinate inversion. start must be <= end, except for the circular
    #    convention, and phiX174 is circular so this is the ambiguous case.
    i, f = first_of_type(body, "gene")
    f = list(f); f[3], f[4] = f[4], f[3]
    b = list(body); b[i] = "\t".join(f)
    cases["start_after_end.gff3"] = ("columns 4 and 5 swapped so start is greater "
        "than end", b)

    # 5. Two parents on one feature. LEGAL GFF3, and the AgBioData group asks
    #    that parsers keep supporting it, yet many tools reject it. Included
    #    because "malformed" and "rejected in practice" are different sets.
    i, f = first_of_type(body, "CDS")
    f = list(f)
    f[8] = ";".join(p if not p.startswith("Parent=") else p + ",gene-phiX174-second"
                    for p in f[8].split(";")) if "Parent=" in f[8] else \
        f[8] + ";Parent=gene-a,gene-b"
    b = list(body); b[i] = "\t".join(f)
    cases["multiple_parents.gff3"] = ("one feature declares two parents, which the "
        "specification allows and many tools refuse", b)

    # 6. Missing version pragma. Without it a parser cannot tell GFF3 from GFF2,
    #    and the column-9 grammar differs between them.
    cases["no_version_pragma.gff3"] = ("the ##gff-version 3 pragma is absent", body)

    # 7. One ID used by two different features.
    i, f = first_of_type(body, "gene")
    dup = list(f); dup[3] = str(int(f[4]) + 1); dup[4] = str(int(f[4]) + 50)
    b = list(body); b.insert(i + 1, "\t".join(dup))
    cases["duplicate_id.gff3"] = ("two distinct features share one ID attribute", b)

    os.makedirs(OUT, exist_ok=True)
    for name, (change, b) in cases.items():
        head = "" if name == "no_version_pragma.gff3" else "##gff-version 3\n"
        note = HEADER.format(src=os.path.relpath(SRC, ROOT), change=change)
        open(os.path.join(OUT, name), "w").write(head + note + "\n".join(b) + "\n")
        print(f"{os.path.getsize(os.path.join(OUT,name)):>6}  {name}  ({change})")
    return cases


if __name__ == "__main__":
    build()
