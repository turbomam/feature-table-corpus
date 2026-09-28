# Constructed multivalued-attribute controls

These files were written here on 2026-09-28, under the repository's CC0 terms. They are not
producer output and were not copied from a vendored artifact. They exist to check one rule,
stated in [docs/attributes.md](../../../docs/attributes.md#multivalued-values): each value of a
multivalued attribute is its own Attribute entry, split before percent-decoding
(https://github.com/turbomam/feature-table-corpus/issues/39).

- `gff3-contig.gff3` is read by `gff3-contig/1.0.0` (`scripts/convert_features.py`). Its mRNA
  has `Parent=a,b`, `Dbxref=A:1,B:2`, an encoded comma in `Note=x%2Cy`, and a product with an
  encoded comma, `2%2C1-aminomutase`.
- `img-functional.gff` is read by the IMG functional dialect and its mapping
  (`scripts/img_functional_gff.py`, `scripts/img_functional_map.py`). Its CDS has comma lists in
  `pfam`, `ko` and `cog`, and a product with a literal comma, as IMG writes it. Its tRNA has
  `note=x%2Cy`, which this dialect keeps as written because IMG does not percent-encode.

`tests/test_attribute_splitting.py` makes the same claims about each converter.
