# A converted BED12 document

[`blat-bed12.json`](blat-bed12.json) is a generated conversion bundle for the
[pinned BLAT BED12 source](../../../corpus/sources/biopython/README.md), using
`bed12-blocks/1.0.0`. Its 19 source rows become 19 parent intervals and 23 block
children in the shared Dataset. Names and display fields use generic attributes;
the source document and mapping records retain serialization and block order.
Reference context is explicitly source-scoped because the BED bytes do not
declare an assembly. No CDS/exon/transcript biology is inferred.

Reproduce the bundle into a new path, then compare:

```sh
just conversion-import corpus/sources/biopython/blat_34_hg19.bed \
  bed12-blocks/1.0.0 \
  'biopython-1.85:Tests/Blat/psl_34_004 (hg19_dna query; assembly not encoded in BED)' \
  local/conversions/blat-reproduced.json \
  --source-uri https://raw.githubusercontent.com/biopython/biopython/668de08f73fca7f8336049dfd78716d7dd095f21/Tests/Blat/psl_34_004.bed
cmp model/examples/conversions/blat-bed12.json local/conversions/blat-reproduced.json
just conversion-validate model/examples/conversions/blat-bed12.json \
  --original corpus/sources/biopython/blat_34_hg19.bed
just conversion-export model/examples/conversions/blat-bed12.json local/conversions/blat-exact.bed exact
just conversion-export model/examples/conversions/blat-bed12.json local/conversions/blat-fields.bed reconstruct
```

Tests require this instance to reproduce from the retained source and exercise
both byte recovery and reconstruction. See [the full profile guide](../../../docs/conversion-profiles.md).
The source content retains the [Biopython license](../../../corpus/sources/biopython/LICENSE.rst).
The extracted Dataset can be queried with the existing loader; keep the whole
bundle for reverse conversion:

```sh
mkdir -p local/conversions
jq '.dataset' model/examples/conversions/blat-bed12.json > local/conversions/blat-dataset.json
just build-duckdb local/conversions/blat-dataset.json local/conversions/blat.duckdb
just query-attribute bed:role block local/conversions/blat.duckdb
just query-overlap contig chr19 35483366 35483499 local/conversions/blat.duckdb
```

The final interval lies between two blocks; it overlaps only the parent span.
