# Actinorhodin: gene order, annotations and genomic distance

**Question:** In the known actinorhodin biosynthetic region of *Streptomyces
coelicolor* A3(2), do the annotated synthase, chain-length factor and acyl carrier
protein occur in the expected order, and how many genomic bases separate them?

The [original genome publication, Figure 3](https://www.nature.com/articles/417141a)
identifies the actinorhodin cluster as **SCO5071–SCO5092**. The retained RefSeq
annotation snapshot maps those old locus tags to current gene IDs on the linear
chromosome **NC_003888.3**. This exercises a real BGC without making an NMDC
annotation convention part of the general model.

## Independently recorded expectations

These values were read directly from the retained GFF rows before running the
converter or SQL. [expected.json](expected.json) is maintained evidence, not
generated query output. [report.json](report.json) checks the result against it
and records full-source line numbers for a separate direct inspection.

| Old locus tag | Current gene | CDS product in this snapshot | Inclusive genomic interval | Strand |
|---|---|---|---|---|
| SCO5087 | SC_RS27595 | beta-ketoacyl-[acyl-carrier-protein] synthase family protein | 5,529,801–5,531,204 | + |
| SCO5088 | SC_RS27600 | ketosynthase chain-length factor | 5,531,201–5,532,424 | + |
| SCO5089 | SC_RS27605 | acyl carrier protein | 5,532,449–5,532,709 | + |

Ordering uses increasing chromosome coordinates, irrespective of transcriptional
strand. Signed gap is `next.start - previous.end - 1`: **−4** means a four-base
overlap; **24** means 24 intervening bases. These are nucleotide distances, never
amino-acid offsets. The query selects these three old locus tags explicitly; a
general overlap query at 5,532,706 also finds the next gene, SCO5090.

The full cluster query recovers all 22 locus tags in order. Exact product lookup
finds SCO5089 for `acyl carrier protein`. Controls give no matches for an absent
product, an out-of-range interval or a different sequence accession version.
Queries declaring a different reference context or protein coordinate space fail
explicitly. SQL parameters preserve literal attribute values.
The reference guard derives `refseq:ACCESSION.VERSION` from the sole chromosome
stored in DuckDB. It cannot be bypassed by supplying two matching caller claims.
This is a bounded single-RefSeq-sequence query, not a multi-assembly join API.

## Source, selection and limits

[The full source](../../corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3)
is the unchanged 4.69 MB NCBI annotwriter response retrieved September 21, 2026.
The download endpoint returned the whole chromosome despite range parameters;
the index records that exact request, checksum and outcome. Sequence accession
version identifies the reference; the retrieval date and SHA-256 pin the annotation
snapshot, because annotations can change without changing sequence version.
Reuse follows the [NCBI data policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).

[The derived input](../../corpus/derived-examples/actinorhodin.gff3) contains the
22 selected gene rows and their 22 direct CDS children, original header, unchanged
row bytes and absolute chromosome coordinates, plus explicit selection provenance.
Selection is by the publication's locus tags, not inferred biological exclusion.
The complete source remains available to reproduce and inspect the selection.
Both files pass the pinned GenomeTools validator.

`gff3-contig/1.0.0` converts this declared excerpt with reference context
`refseq:NC_003888.3`. Exact export recovers **the excerpt** byte for byte.
Reconstruction derives its feature rows from modeled fields and semantic mappings,
then reimports with identical fields and relationships. This does not claim that
44 selected rows reconstruct the complete chromosome annotation. Edited bundles
are rejected by both exporters.

The query describes annotations and proximity. It does not infer biochemical
function from distance or establish cluster activity. MIBiG provides complementary
[curated evidence](https://mibig.secondarymetabolites.org/repository/BGC0000194.5/index.html)
on accession AL645882.2; its wider display region and that accession are not
silently substituted for this exercise's RefSeq coordinates.

## Reproduce offline

After installing the repository's pinned conversion dependencies:

```sh
just bgc-check    # read-only selection, conversion, query and report verification
just bgc-report   # explicitly regenerate the derived excerpt and measured report
mkdir -p local/bgc-demo
just conversion-import corpus/derived-examples/actinorhodin.gff3 \
  gff3-contig/1.0.0 refseq:NC_003888.3 local/bgc-demo/bundle.json --metadata-profile ncbi
just conversion-export local/bgc-demo/bundle.json local/bgc-demo/exact.gff3 exact
just conversion-export local/bgc-demo/bundle.json local/bgc-demo/reconstructed.gff3 reconstruct
```

The example builds a temporary DuckDB in ignored `local/`, validates the model,
executes genomic gene/CDS/attribute joins, and removes the temporary database.
Set `UV_OFFLINE=1` to require cached dependencies. `just check` and CI include the
read-only check and regression tests. The general
[conversion report](../conversion-roundtrips/README.md) measures this case too.
