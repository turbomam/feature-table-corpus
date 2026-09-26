# Constructed IMG per-method hit rows

The seven `constructed_<method>.gff` files were written here on 2026-09-25, under the
repository's CC0 terms. They are not producer output and were not copied from a JGI or NMDC
file. Gene IDs, positions, scores and reference gene IDs are invented; accessions, key orders
and value forms follow what the IMG pipeline writes, as measured on the files listed in
`model/examples/jgi-inputs.yaml` and the vendored NMDC per-method files.

Each file holds one method, because a real per-method file does. Between them they cover: a
Pfam name with a hyphen, the empty column 2 of COG, TIGRFAM and SMART, a negative SMART score
and bit score, a lastal score in exponent form, a KO/EC accession packing two KOs and two
partial EC numbers, several reference gene IDs in one comma list, and two hits on one protein.
Every hit ends within its protein, whose length is a third of the gene span in its ID.
`tests/test_img_per_method_gff.py` edits single rows of them to check that each rule rejects
what it should.
