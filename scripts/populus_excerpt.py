"""Write the Populus trichocarpa v4.1 gene_exons excerpt vendored in corpus/derived-examples/.

    python3 scripts/populus_excerpt.py SOURCE_GFF3_GZ OUTPUT [--table SOURCE_TABLE TABLE_OUTPUT]

SOURCE_GFF3_GZ is Ptrichocarpa_533_v4.1.gene_exons.gff3.gz from Phytozome (Phytozome-533),
which needs a JGI login to download, so the full file isn't vendored (112.8 MB uncompressed).
This keeps its directives and the first GENES genes on Chr01 in file order, each with all of
its mRNA, exon, CDS and UTR rows, byte for byte, and adds the three provenance lines
scripts/verify.py requires of a derived file after the directives. The source's md5 is checked
first, so the excerpt can only be made from the file the index records.

--table also writes the rows of Ptrichocarpa_533_v4.1.annotation_info.txt for the excerpt's
genes, in table order, after the header and its own three provenance lines, after checking that
file's md5 too.
"""
import argparse
import gzip
import hashlib
from pathlib import Path
import sys

SOURCE_MD5 = "3fdcfdd5af213c5f4dde0c01f2cdbfda"
TABLE_MD5 = "aaf04aa3515d96748d1229d36ac7dfe4"
TABLE_NAME = "Ptrichocarpa_533_v4.1.annotation_info.txt"
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


def table_excerpt(table, gff3_text, digest=TABLE_MD5):
    """The annotation_info rows of the genes in a gene_exons excerpt, in table order, after its header
    and the three provenance lines."""
    genes = {line.split("Name=")[1].split(";")[0].rstrip("\n") for line in gff3_text.splitlines()
             if not line.startswith("#") and line.split("\t")[2] == "gene"}
    with open(table, encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    rows = [line for line in lines[1:] if line.split("\t")[1] in genes]
    found = {line.split("\t")[1] for line in rows}
    if found != genes:
        raise ValueError(f"{table}: no rows for {len(genes - found)} of the excerpt's genes")
    provenance = [
        f"# derived-from: jgi-phytozome-populus-v4.1-annotation-info ({TABLE_NAME}, md5 {digest})\n",
        f"# single-change: select the rows of the {len(genes)} genes in the gene_exons excerpt, in table order; "
        "retain the header and row bytes\n",
        "# validity: selected source rows, not a complete genome annotation\n",
    ]
    return "".join([lines[0]] + provenance + rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--table", nargs=2, type=Path, metavar=("SOURCE_TABLE", "TABLE_OUTPUT"),
                        help=f"also write the excerpt's rows of {TABLE_NAME}")
    args = parser.parse_args(argv)
    try:
        digest = hashlib.md5(args.source.read_bytes()).hexdigest()
        if digest != SOURCE_MD5:
            print(f"{args.source}: md5 {digest}, expected {SOURCE_MD5}", file=sys.stderr)
            return 1
        text = excerpt(args.source)
        outputs = [(args.output, text)]
        if args.table:
            table_source, table_output = args.table
            table_digest = hashlib.md5(table_source.read_bytes()).hexdigest()
            if table_digest != TABLE_MD5:
                print(f"{table_source}: md5 {table_digest}, expected {TABLE_MD5}", file=sys.stderr)
                return 1
            outputs.append((table_output, table_excerpt(table_source, text)))
        from img_functional_map import write_new_files
        if write_new_files(outputs):
            return 1
    except (OSError, UnicodeDecodeError, ValueError) as error:
        # The source needs a JGI login, so a missing or unreadable file is the usual failure.
        print(f"populus_excerpt: {error}", file=sys.stderr)
        return 1
    for path, written in outputs:
        print(f"wrote {path}: {written.count(chr(10))} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
