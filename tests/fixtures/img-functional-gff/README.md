# Constructed IMG functional annotation rows

`constructed.gff` was written here on 2026-09-25, under the repository's CC0 terms. It is not
producer output and was not copied from a JGI or NMDC file. Contig names, coordinates and
scores are invented; accessions and value forms follow what the IMG pipeline writes, as
measured on the files listed in `model/examples/jgi-inputs.yaml`.

It holds one row of each shape the dialect schema must accept: a CDS whose product contains a
comma, a CDS with a repeated `shortened` key and an `Edge` start, slash-joined
`product_source`, a pseudo tRNA, an rRNA and a riboswitch from Rfam, and a CRISPR with two
repeat units whose IDs extend the CRISPR's ID. `tests/test_img_functional_gff.py` edits
single rows of it to check that each rule rejects what it should.
