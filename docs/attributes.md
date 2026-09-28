# Reusable attributes

[`model/schema/attributes.yaml`](../model/schema/attributes.yaml) is a standalone LinkML module for
named values attached to a record. It has its own draft namespace and no import of GFF,
the feature model, contigs, or coordinate systems. Consumers choose where attributes
are attached and whether the collection is multivalued.

```yaml
key: instrument_model
value: NovaSeq
```

The initial contract is deliberately small: both `key` and `value` are required strings.
They are class-local attributes with explicit ranges, so importing this module does not
reserve these common names as schema-wide slots or depend on the consumer's default range.
A key preserves the source spelling and is not a globally unique identifier. Repeated
keys can be represented as separate entries in an ordered list. Empty strings are
allowed; absent values are not silently converted to empty strings.

GFF column 9 is a minimal use case. The same module can carry annotation evidence,
tabular metadata, or other source-reported properties. For example, a GFF parser can map
a tag to `key`; an evidence importer can map `evalue` to `key` and preserve `1e-42` in
`value`. A value is the source's text for one item, not typed or normalized; if the source
format escapes characters, the value holds the decoded text and the escaped spelling stays with
the source serialization. These mappings do not define GFF escaping or a round trip back to the
source serialization. They do follow one rule for values that hold more than one item, below.

## Multivalued values

Every converter in this repository follows one rule
(https://github.com/turbomam/feature-table-corpus/issues/39):

- Each value of a multivalued attribute is its own `Attribute` entry, with the same key, in
  source order. `Parent=a,b` becomes two entries, `Parent` `a` and `Parent` `b`, never one
  entry `a,b`.
- Splitting happens before percent-decoding. An encoded comma, `%2C`, stays inside one value:
  `Note=x%2Cy` is one entry, `x,y`.
- Which keys are multivalued is a property of the source profile, not of the key.
  A GFF3-conformant profile, such as `gff3-contig/2.0.0`, treats every key as a comma list,
  because GFF3 says commas separate values and a literal comma must be written `%2C`.
  A dialect whose writers do not encode commas, such as IMG functional annotation from JGI and
  NMDC, must declare its multivalued keys in its dialect schema. Every other key's value is
  kept whole, literal commas included, so `product=glutamate-1-semialdehyde 2,1-aminomutase`
  is one entry. Such a dialect also does no percent-decoding, since its writer encodes nothing.
- A dialect that cannot tell a separator from text, and has never been seen to write either,
  refuses the value instead of guessing. The Phytozome GFF3 dialect refuses any comma or
  percent sign in column 9.

polars-bio 0.36.0 `read_gff` does not follow this rule. It returns `Parent=a,b` as one
unsplit value, and it decodes before any split, so `%2C` can no longer be told apart from a
separator. This was seen on a two-row test file on 2026-09-23; polars-bio is not a
dependency here. Its output must not be loaded into the model as it comes.

`tests/test_attribute_splitting.py` checks the rule against each converter, using the
fixtures in `tests/fixtures/attribute-splitting/`. The per-profile details are in
[conversion profiles](conversion-profiles.md#attributes-and-authority).

Typed values, units, namespaces for keys, nested structures, and per-attribute provenance
remain extension questions. Known biological fields can still have explicit typed slots
in the consuming model. Generic attributes should not replace those slots.

The feature model imports this module and attaches a list through `Feature.attributes`.
Its draft instances now use `key`, replacing the earlier GFF-oriented `tag` spelling.
`just test` validates the module independently with metadata and evidence examples,
checks repeated keys in a feature's attribute list, and imports it into a consumer
with incompatible global `key`/`value` slots to verify that both classes retain their contracts.
