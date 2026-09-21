# Source-document parser fixtures

`mixed-records.gff3` is a **derived test fixture**, not an observed production file.
It borrows the sequence name and region-row shape from the public-domain RefSeq
phiX174 GFF in `data/ncbi-refseq/`, reduces the region and feature to positions 2–4,
and adds explicitly synthetic comment/directive and FASTA content. The six-base
FASTA sequence is invented for this parser test, not phiX174 sequence evidence.

The fixture exercises repeated unknown directives, repeated ontology directives,
a comment between records, a `###` boundary, and an embedded FASTA transition.
Its sequence-region covers a subinterval, deliberately distinct from sequence length.
Tests create additional malformed and mixed-line-ending variants in memory.

These are parser unit fixtures, outside the indexed corpus and its one-mutation
derived-file convention. They never replace or modify the vendored source files.
