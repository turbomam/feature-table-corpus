# Pinned cross-format examples

These source files are unchanged copies from **Biopython 1.85**, commit
[`668de08f73fca7f8336049dfd78716d7dd095f21`](https://github.com/biopython/biopython/tree/668de08f73fca7f8336049dfd78716d7dd095f21),
retrieved 2026-09-21. The [index](../../index.yaml) records exact paths, URLs, sizes,
MD5/SHA-256 hashes and license information. The upstream [license](LICENSE.rst) is
retained; its default Biopython License Agreement applies to files without overrides.

- `blat_34_hg19.bed` is upstream `Tests/Blat/psl_34_004.bed`: nineteen BED12
  renderings of BLAT v34 real-sequence alignments, with scores, both strands and
  multiblock cases. The upstream
  [README](https://github.com/biopython/biopython/blob/668de08f73fca7f8336049dfd78716d7dd095f21/Tests/Blat/README.txt)
  identifies BLAT v34; the records label the query `hg19_dna`. BED itself does not
  declare the target assembly, so the conversion uses an explicit source-scoped
  reference context and does not infer assembly from that query label. These are
  upstream alignment test examples, not an annotation release or a synthetic
  chromosome-position example created in this repository.
- `cor6_6.gb` is upstream `Tests/GenBank/cor6_6.gb`: six INSDC plant records with
  accession versions X55053.1, X62281.1, M81224.1, AJ237582.1, L31939.1 and
  AF297471.1. Original submitters, dates and citations are in the records. Joined
  and partial locations and repeated qualifiers supply concrete modeling evidence.
  This is GenBank flat-file feature-table syntax, not a five-column submission table.

Only the BED example currently has an executable semantic conversion profile.
See the [preservation report](../../../analyses/conversion-roundtrips/README.md).
