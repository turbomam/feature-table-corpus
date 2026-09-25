# Constructed IMG taxon bundle

The nine files here were written on 2026-09-25, under the repository's CC0 terms. They are not
producer output and were not copied from a JGI file. The taxon number 9900000001, contig names,
gene numbers, locus tags, coordinates and scores are invented. Column order, value spellings and
cross-file rules follow what IMG wrote in the two bundles the dialect schema was measured on,
[`model/dialects/img-taxon-bundle.yaml`](../../../model/dialects/img-taxon-bundle.yaml).

`9900000001.gff` holds one row of each shape the schema must accept: an rRNA with a product, a
CDS whose product has a comma and ends with a space, a tRNA and an RNA gene with no product, and
two CRISPR rows with no end and column 9 ".". The tables cover a KO whose name lists two EC
numbers (two rows, one shortened to `EC:3.1.-`), a KO with no EC, a gene with two hits to the same
Pfam, an InterPro member hit with no InterPro entry, GO terms joined with "|", a TMHMM topology
with one helix, and both xref databases.

`tests/test_img_taxon_bundle.py` edits one row of one file at a time to check that each rule
rejects what it should.
