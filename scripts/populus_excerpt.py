"""Write the Populus trichocarpa v4.1 gene_exons excerpt vendored in corpus/derived-examples/.

    python3 scripts/populus_excerpt.py SOURCE_GFF3_GZ OUTPUT

SOURCE_GFF3_GZ is Ptrichocarpa_533_v4.1.gene_exons.gff3.gz from Phytozome (Phytozome-533),
which needs a JGI login to download, so the full file isn't vendored (112.8 MB uncompressed).
This keeps its directives and the first GENES genes on Chr01 in file order, each with all of
its mRNA, exon, CDS and UTR rows, byte for byte, and adds the three provenance lines
scripts/verify.py requires of a derived file after the directives. The source's md5 is checked
first, so the excerpt can only be made from the file the index records.
"""
import argparse
import gzip
import hashlib
from pathlib import Path
import sys

SOURCE_MD5 = "3fdcfdd5af213c5f4dde0c01f2cdbfda"
GENES = 200
SOURCE_NAME = "Ptrichocarpa_533_v4.1.gene_exons.gff3.gz"


def excerpt(source, genes=GENES, digest=SOURCE_MD5):
    """The excerpt's text from the gzipped source GFF3."""
    head, rows, count = [], [], 0
    with gzip.open(source, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            if line.startswith("#"):
                if rows:
                    raise ValueError(f"{source}: a comment after the feature rows begin")
                head.append(line)
                continue
            columns = line.split("\t")
            if columns[2] == "gene":
                count += 1
                if count > genes:
                    break
            if columns[0] != "Chr01":
                raise ValueError(f"{source}: reached {columns[0]} before {genes} genes on Chr01")
            rows.append(line)
    provenance = [
        f"# derived-from: jgi-phytozome-populus-v4.1-gene-exons ({SOURCE_NAME}, md5 {digest})\n",
        f"# single-change: select the first {genes} genes on Chr01 in file order with all their rows; "
        "retain the directives, row bytes and chromosome coordinates\n",
        "# validity: valid GFF3; selected source rows, not a complete genome annotation\n",
    ]
    return "".join(head + provenance + rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        digest = hashlib.md5(args.source.read_bytes()).hexdigest()
        if digest != SOURCE_MD5:
            print(f"{args.source}: md5 {digest}, expected {SOURCE_MD5}", file=sys.stderr)
            return 1
        text = excerpt(args.source)
        with open(args.output, "x", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        # The source needs a JGI login, so a missing or unreadable file is the usual failure.
        print(f"populus_excerpt: {error}", file=sys.stderr)
        return 1
    print(f"wrote {args.output}: {text.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
