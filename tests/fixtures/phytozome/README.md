# Constructed Phytozome gene_exons GFF3 and annotation_info rows

`constructed.gene_exons.gff3` and `constructed.annotation_info.txt` were written here on
2026-09-25, under the repository's CC0 terms. They are not producer output and contain no row,
identifier, coordinate or description from any Phytozome file.

TAIR restricts redistributing substantial subsets of TAIR10, and whether TAIR10 is under CC BY
is not yet confirmed ([JGI inputs](../../../docs/jgi-inputs.md)). So nothing from
`Athaliana_167_TAIR10`, the only Phytozome genome read so far, is kept here, not even an excerpt.
The genome name `EXv1`, the scaffold, the `Exa01g...` gene names, the pacids from 90000001,
the coordinates, and the best-hit names and descriptions are invented. Accessions (Pfam,
PANTHER, EC, KOG, KO, GO) are real identifier forms attached to invented transcripts. The
token `EC:PROLINE-MULTI` is copied as a value form because it occurs in the real table.

The GFF3 holds two genes. The first, on the plus strand, has a two-exon isoform flagged
`longest=1` and a single-exon isoform flagged `longest=0`. The second, on the minus strand,
has one isoform with three exons and two five-prime UTR parts, numbered in transcription
order, so their coordinates descend. The table has one row per mRNA, including empty cells,
multi-value cells, a best-hit name without its description, and both PANTHER spellings.

`tests/test_phytozome.py` edits single rows of these files to check that each rule of the two
dialects, and the join between them, rejects what it should.
