# Reusable attributes

[`schema/attributes.yaml`](../schema/attributes.yaml) is a standalone LinkML module for
named values attached to a record. It has its own draft namespace and no import of GFF,
the feature model, contigs, or coordinate systems. Consumers choose where attributes
are attached and whether the collection is multivalued.

```yaml
key: instrument_model
value: NovaSeq
```

The initial contract is deliberately small: both `key` and `value` are required strings.
A key preserves the source spelling and is not a globally unique identifier. Repeated
keys can be represented as separate entries in an ordered list. Empty strings are
allowed; absent values are not silently converted to empty strings.

GFF column 9 is a minimal use case. The same module can carry annotation evidence,
tabular metadata, or other source-reported properties. For example, a GFF parser can map
a tag to `key`; an evidence importer can map `evalue` to `key` and preserve `1e-42` in
`value`. These mappings do not define GFF escaping, delimiter handling, or a round trip
back to the source serialization.

Typed values, units, namespaces for keys, nested structures, and per-attribute provenance
remain extension questions. Known biological fields can still have explicit typed slots
in the consuming model. Generic attributes should not replace those slots.

The feature model imports this module and attaches a list through `Feature.attributes`.
Its draft instances now use `key`, replacing the earlier GFF-oriented `tag` spelling.
`just test` validates the module independently with metadata and evidence examples,
and checks repeated keys in a feature's attribute list.
