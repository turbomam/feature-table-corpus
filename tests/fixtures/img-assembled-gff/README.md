# Constructed IMG 4.14 assembled GFF rows

`constructed.assembled.gff` was written here on 2026-09-28, under the repository's CC0 terms. It
is not producer output and was not copied from a JGI file. Contig IDs, coordinates and scores are
invented; column values, key orders and value forms follow what IMG pipeline 4.14 writes, as
measured on `corpus/sources/jgi-img/IMG_AP-1121004/106476.assembled.gff`.

It holds one row of each type (CDS on both strands, tRNA, rRNA, misc_RNA, misc_bind,
misc_feature) on two contigs. The second contig's ID numbers start at 2 and skip 3, as two
measured contigs do, while its locus tags still count 1, 2; one of its rRNA rows writes
`LowScore` twice. `tests/test_img_assembled_gff.py` edits single rows to check that each rule
rejects what it should.
