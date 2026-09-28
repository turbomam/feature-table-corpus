# Constructed IMG TMHMM and SignalP rows

`constructed_tmh.gff` and `constructed_cleavage_sites.gff` were written here on 2026-09-28,
under the repository's CC0 terms. They are not producer output and were not copied from a JGI
or NMDC file. Gene IDs, positions and scores are invented; column values, key orders and value
forms follow what the IMG pipeline writes, as measured on the `_tmh.gff` and
`_cleavage_sites.gff` files of the two isolates listed in `model/examples/jgi-inputs.yaml`.

The TMHMM file has two genes. The first has two helices, so its segments switch from Outside to
Inside and back. The second has one helix, and its last segment ends at residue 200 of a
600-base gene span, one past the 199 residues before the stop codon, as two measured
Methanococcus genes do. The SignalP file has one cleavage site on each of those genes, one with
each network variant, and one D-score and one score with a trailing zero, which the writer
respells. `tests/test_img_tmhmm_signalp_gff.py` edits single rows of them to check that each
rule rejects what it should.
