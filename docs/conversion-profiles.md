# Executable conversion profiles

Four versioned source profiles now convert complete, supported artifacts into the
shared `Dataset` model and back. They implement the first cross-format milestone
in [#16](https://github.com/turbomam/feature-table-corpus/issues/16).
The [measured report](../analyses/conversion-roundtrips/README.md) separates exact
byte recovery, reconstruction of mapped fields, and unsupported cases.
The [converted BED12 example](../model/examples/conversions/README.md) shows a
complete generated bundle and how to query its Dataset projection.

## What the converted instance contains

The JSON conversion bundle is one document with these required fields:

| Field | Contract |
|---|---|
| `conversion_version` | Envelope version, currently integer `1`. |
| `profile` | Explicit source contract ID including version; no filename or dialect guessing. |
| `reference_context` | Caller-supplied assembly or source-scoped reference identity. Required; never inferred from `chr1` or an annotation name. |
| `source` | A [SourceDocument](source-documents.md) retaining record order, lexical details, scoped metadata, content hash and provenance URI. |
| `dataset` | An instance of the existing [Dataset/Contig/Feature model](../model/schema/README.md), validated with its closed shape and cross-record checks. |
| `mappings` | Source-record-to-feature identities, ordered block identities, and attribute grouping/cardinality metadata needed by the reverse mapping. |

The protein profile additionally requires `protein_context` in the bundle. Supply
the independent original context again to validation/export with
`--protein-context`; it is compared before reimporting the source projection.

`scripts/convert_features.py` checks both component shapes, then validates the complete
executable bundle contract by re-importing its internally checked source and comparing the whole projection.
Unknown fields and inconsistent copies fail. The two component classes remain
LinkML-defined; this version's enclosing JSON/mapping contract is enforced in code.
Retain the whole bundle for conversion. Extracting just `dataset` is a useful
query projection and does **not** preserve the full round-trip contract.

The reference context and URI are declarations, not authenticated provenance.
Validation without an independently supplied original establishes internal
consistency. `--original PATH` additionally requires agreement with that retained
artifact. A coordinated rewrite of source, hash and mapped values describes a new
internally consistent artifact; it cannot pass comparison with the old original.

## Source contracts

| Profile | Forward mapping | Reverse mapping and bounds |
|---|---|---|
| [`insdc-locations/1.0.0`](../model/profiles/insdc-locations.yaml) | GenBank nucleotide records with qualified references, ordered parts, partial endpoints, circular topology and generic qualifiers. | Reconstruct feature-table blocks from modeled locations and qualifiers; preserve header/sequence text in SourceDocument. Remote, between-base, unknown and mixed-strand locations are refused. |
| [`nmdc-pfam-protein/1.0.0`](../model/profiles/nmdc-pfam-protein.yaml) | NMDC HMMER Pfam hits with explicit protein-to-CDS bindings, retained translations and amino-acid coordinates. | Reconstruct protein references and attributes without fabricating source Parent tags or exporting contextual CDS rows. Validation/export require the independent original context. |
| [`gff3-contig/1.0.0`](../model/profiles/gff3-contig.yaml) | Linear contig coordinates, decoded sequence/feature identities, source/type/score/strand/phase; `ID`, `Parent`, and `product` also populate typed slots. Every attribute occurrence remains a generic pair. | Reconstruct nine columns from the Dataset and grouping indices. Repeated IDs/discontinuous features, circular references, protein-relative coordinates, unresolved parents, and ambiguous typed cardinalities are refused. |
| [`bed12-blocks/1.0.0`](../model/profiles/bed12-blocks.yaml) | One parent interval plus ordered block children. Source `[start,end)` becomes model `[start+1,end]`; chromosome names remain literal. Score and strand use core slots; name, RGB and thick drawing bounds use generic `bed:*` attributes. | Reconstruct twelve columns using the parent and children. Require positive, ordered, nonoverlapping blocks covering the enclosing boundaries. Zero-length intervals, fewer/extra columns and whitespace-delimited variants are refused. |

These restrictions belong to these adapters, not to the full input formats.
[UCSC's BED description](https://genome.ucsc.edu/FAQ/FAQformat.html#format1)
defines the coordinate and block conventions. In particular, a thick drawing span
is not necessarily a CDS. BED blocks become generic `sequence_feature` children;
the adapter does not invent transcript/exon identities or query-side alignment
coordinates. Overlap queries can return both the enclosing record and its blocks;
filter `bed:role=block` when asking about covered blocks. A gap overlaps the parent
span without becoming an annotated block.

The [NMDC Pfam profile](protein-relative-profile.md), `nmdc-pfam-protein/1.0.0`,
adds explicit protein-to-CDS context and amino-acid bounds, while keeping the two
original contracts unchanged. Supporting CDSs are not exported as additional
Pfam rows. Source rows require HMMER/Pfam, ID, strand/phase `.`, and no Parent.

The original GFF profile is a declared **contig-coordinate** contract, not a format detector.
Do not apply it to NMDC protein-domain output just because that output has nine
columns. The corpus has examples of both coordinate spaces. Use the Pfam profile
and its explicit companion context for the supported protein-relative convention;
the existing curated protein-relative examples remain separately validated.

The [GFF3 specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md)
allows richer representations than this first adapter supports. Unknown attributes,
including partial-status qualifiers, survive as ordered generic values; this does
not add typed uncertain endpoints or interpret every producer convention.
Unknown directives retain stream scope. Explicit Prodigal or NCBI metadata profiles
reuse the existing source reader's scoped interpretation. Comments, FASTA and other
nonfeature records are preserved; they are not promoted into biological Dataset
fields or independently reserialized from typed metadata.

## Dialect schemas

A profile above converts a source into the model. A dialect schema is an earlier,
separate check: it describes a source's own rows in LinkML, so a file can be validated
against its dialect before anything is mapped. When a file fails, that says it differs
from what its producer is known to write, not that a mapping is wrong
([#54](https://github.com/turbomam/feature-table-corpus/issues/54)).

The first is [`img-functional-gff.yaml`](../model/dialects/img-functional-gff.yaml),
for the JGI IMG pipeline's `*_functional_annotation.gff`. It was measured on 2026-09-25
against two JGI isolate annotations (Clostridium acetobutylicum `Ga0423362`, 4,439 rows;
Methanococcus maripaludis S1 `Ga0416744`, 2,005 rows), which need a JGI login to download
([#52](https://github.com/turbomam/feature-table-corpus/issues/52)), and the vendored NMDC file.

- `gff3-contig/1.0.0` rejects both isolate files at their first product name containing a
  comma (`product-cardinality`), for example "glutamate-1-semialdehyde 2,1-aminomutase".
  96 product names in the two files have one. The dialect splits commas only for the keys it
  types as lists (`pfam`, `cog`, `ko`, `ec_number`, `tigrfam`, `smart`, `superfamily`,
  `cath_funfam`, `transmembrane_helix_parts`).
- Rows come from five tools (GeneMark, Prodigal, INFERNAL, tRNAscan-SE, CRT) in eight
  column 3 types. There are no header or comment lines.
- IDs are `<seqid>_<start>_<end>`, except CRISPR repeat units, which take their CRISPR's ID
  plus `_DR1`, `_DR2` in order. Only repeat units carry `Parent`, and only CRISPR rows and
  repeat units are unstranded.
- A key can repeat: one Prodigal CDS has `shortened` twice. Key order is kept in
  `attribute_order` so rows can be written back.

`just dialect-validate-img-functional FILE` parses a file, validates it with the LinkML
validator, and adds the cross-row checks a schema can't express. The tests edit single rows
of a [constructed fixture](../tests/fixtures/img-functional-gff/README.md) to show each rule
rejects what it should.

### Mapping a dialect with linkml-map

[`img-functional-gff.transform.yaml`](../model/transforms/img-functional-gff.transform.yaml)
maps dialect rows to `Feature` with [linkml-map](https://github.com/linkml/linkml-map) 0.5.4,
pinned in [`requirements-mapping.txt`](../requirements-mapping.txt). The reverse mapping is not written by hand: it is generated
from the same file with linkml-map's inverter each time
([#55](https://github.com/turbomam/feature-table-corpus/issues/55)).

linkml-map handles the nine columns, the typed keys with a `Feature` slot (`ID`, `Parent`,
`product`, `product_source`) and the strand enum. `scripts/img_functional_map.py` does four
things it couldn't, found while building this on 2026-09-25:

- MELT turns wide slots into key/value rows, but keeps a list as one value, keeps non-string
  types, and follows the spec's slot order. Column 9 needs one `Attribute` per value, as text,
  in file order, so the script builds `attributes` itself. Every key is kept, including those
  that also fill a `Feature` slot, as `gff3-contig` does; the reverse step rejects a Feature
  whose slot and attribute copies disagree.
- A constant slot (`coordinate_system: contig`) makes inversion fail, so the script sets it.
- linkml-map won't build records inside an expression, so the script makes one `Contig` per
  distinct seqid, in file order.
- Inversion drops `mirror_source` from the strand enum mapping, which turns every strand into
  nothing on the way back, so the script copies it from the forward specification.

`just map-img-functional-roundtrip FILE` validates the dialect, maps forward, validates the
Dataset with `scripts/validate_closed.py`, maps back, and requires every row to come back
equal. It then writes GFF text and checks that each line that differs from the source parses
to the same row. Run on 2026-09-25, all rows came back equal for Clostridium acetobutylicum
`Ga0423362` (4,439 features, 53,609 attributes) and Methanococcus maripaludis S1 `Ga0416744`
(2,005 features, 24,507 attributes). The written text differs from the source only in number
spelling, on 430 and 196 lines: scores such as `84.50` come back as `84.5`, and CRISPR lengths
such as `26` as `26.0`. Exact bytes are out of scope here; `gff3-contig` keeps them through a
[SourceDocument](source-documents.md).

`just map-img-functional FILE OUT` and `just map-img-functional-back DATASET OUT` run each
direction on its own, and never overwrite an existing file. The reverse direction maps its
result forward again and refuses unless that reproduces the input Dataset, so a slot the
dialect can't hold, such as `translated_sequence` or a contig length, is an error rather than
a silent loss.

### IMG taxon bundle

[`img-taxon-bundle.yaml`](../model/dialects/img-taxon-bundle.yaml) is the third dialect in
https://github.com/turbomam/feature-table-corpus/issues/54: the older IMG taxon download, a
`<taxon_oid>.gff` written from the `img_core_v400` database plus `<taxon_oid>.<kind>.tab.txt`
tables whose columns the bundle's `README.txt` documents. It was measured on 2026-09-25 against
two bundles, Bacillus sp. V-88 (`IMG_AP-1121004`, taxon 2708743150, 4,628 GFF rows,
7 tables) and Zymomonas mobilis ATCC 10988 (`IMG_AP-1377582`, taxon 645058785, 1,942 GFF rows,
8 tables), both downloaded to `local/jgi/`.

The tables name genes only by `gene_oid`, which is the GFF row's `ID`, so a bundle is validated
as one document with one class per table. What the two bundles share:

- The GFF starts with `##gff-version 3`. Score is always `.`, and phase is `0` on every gene row,
  RNA genes included. Column 9 is `ID`, `locus_tag`, then `product` on CDS and rRNA rows only.
  There is no gene hierarchy. Types are CDS, tRNA, rRNA, RNA and CRISPR.
- The 48 CRISPR rows, all in Zymomonas, have no end, no ID and column 9 `.`. They repeat two start
  positions on each of the 24 contigs, 17 of which are shorter than the larger one, so they
  carry no usable location. The dialect accepts them as written.
- Every `gene_oid` in every table is a CDS, and a gene's `gene_length` is the same in every
  table. Rows are sorted by `gene_oid`. TMHMM segments tile each protein from 1 to its length.
- A KO whose name lists several EC numbers gets one row per number, and the EC column shortens
  trailing unknown parts to one, so `[EC:3.1.-.-]` in the name is `EC:3.1.-` in the column.
- Only `.ipr.tab.txt` has GO terms, joined with `|`. Pfam accessions are written `pfam00578`.

`.kog.tab.txt`, `.crispr.txt` and a non-empty `img_ko_flag` are documented but were not in
either bundle, so they fail until measured. Any other `<taxon_oid>.*` file beside the GFF fails
too, except the documented sequence files (`.fna`, `.genes.fna`, `.genes.faa`,
`.intergenic.fna`) and the downloaded `.tar.gz` they come in, so no table goes unchecked. Numbers must use ASCII digits with no leading
zeros and no trailing fractional zeros, as IMG writes them, which keeps write-back exact. `just dialect-validate-img-taxon GFF` checks the
GFF and every table beside it. Both bundles pass, and the writer reproduces all 17 files byte
for byte. The tests edit single rows of a
[constructed bundle](../tests/fixtures/img-taxon-bundle/README.md) to show each rule rejects.

`106476.assembled.gff`, in the Bacillus bundle, is a separate dialect and is not written yet. It
is IMG pipeline 4.14.0 output with no `##gff-version` line: sources are the calling tools
(Prodigal V2.6.3, INFERNAL, HMMER), strand is `1` or `-1`, IDs are `<seqid>.<n>`, CDS rows carry
Prodigal's `conf` and `gc_cont`, and every column 9 ends with `;`. Its 4,693 rows include all
4,628 taxon GFF rows by locus tag, at the same coordinates, plus 39 `misc_bind` and 26
`misc_feature` rows that the taxon GFF drops; its 39 `misc_RNA` rows are the taxon GFF's `RNA`.

## Attributes and authority

The shared Attribute class still means a string key/value pair, independent of
GFF column 9. BED display/name values and parsed comment metadata use it too.
GFF occurrences and comma-separated values become ordered pairs; mappings retain
the grouping indices, so `Note=a,b;Note=c` remains distinguishable from three
assignments. Empty values remain strings, distinct from absent assignments.
Original lexical cells retain escaping, delimiters and numeric spelling.

Typed GFF `feature_id`, `parent`, and `product` must agree with their retained
generic `ID`, `Parent`, and `product` values. Reconstructed output uses the typed
slots for those assignments and rejects conflicting generic copies. Missing source
IDs receive document-local synthetic IDs but remain missing in exported GFF. The
model's attribute list now explicitly records that order is retained.

These versions support **unmodified imported instances**. Changes to modeled fields,
attributes, block relationships, preservation records or mappings are rejected in
both export modes. There is no precedence rule that silently overwrites an edit,
and no implemented lossy or edited-instance export mode. Conversion/data errors
return status 2 with a JSON diagnostic; command-usage errors use standard argparse
help. Existing source/output files are never overwritten.

## Reproduce the two guarantees

Use Python 3.11+, uv and just 1.27+. The conversion commands and regression suite
use [pinned dependencies](../requirements-conversion.txt): LinkML 1.11.1,
jsonschema 4.26.0, PyYAML 6.0.3, rfc3987 1.3.8 and Biopython 1.85. Use new output paths:

```sh
just conversion-import \
  corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff \
  gff3-contig/1.0.0 nmdc:wfmgan-11-9ya9xh30.1 \
  local/conversions/prodigal.json --metadata-profile prodigal
just conversion-validate local/conversions/prodigal.json \
  --original corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff
just conversion-export local/conversions/prodigal.json local/conversions/prodigal-exact.gff exact
just conversion-export local/conversions/prodigal.json local/conversions/prodigal-reconstructed.gff reconstruct
cmp corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff local/conversions/prodigal-exact.gff

just conversion-import corpus/sources/biopython/blat_34_hg19.bed \
  bed12-blocks/1.0.0 biopython-1.85:Tests/Blat/psl_34_004 local/conversions/blat.json
just conversion-export local/conversions/blat.json local/conversions/blat-exact.bed exact
just conversion-export local/conversions/blat.json local/conversions/blat-reconstructed.bed reconstruct
just conversion-check
just test
```

`exact` first verifies the imported projection and reconstructs feature semantics,
then restores lexical cells and original line endings. `reconstruct` generates
feature columns using a function that receives **no source feature text or columns**;
only the Dataset and nonlexical identity/grouping map. Re-importing that output must
recover the same Dataset, relationships, grouping and nonfeature metadata records.
Percent-escape spelling, numeric spelling, trailing delimiters and empty column 9
may normalize in this mode. It promises preserved interpreted fields, not biological
equivalence beyond the declared mappings.

`just conversion-report` deliberately regenerates the tracked JSON report;
`just conversion-check`, included in `just check` and CI, compares it without writing.
Unexpected rejection **or** unexpected acceptance fails. Unit tests also cover
120 deterministically generated positive cases, wrong/conflicting representations,
malformed values, boundaries, metadata scopes, literal arguments and refused edits.
Common interval and attribute queries cover the converted profiles, with explicit
[part-aware and partial-bound semantics](feature-locations.md) for INSDC. Query
performance remains unmeasured. [Independent GFF3 validation](../analyses/format-validation/README.md)
records separate GenomeTools verdicts; other formats have no independent validator yet.

## Additional format coverage and remaining limits

The [INSDC feature-table definition](https://www.insdc.org/submitting-standards/feature-table/)
uses location expressions and qualifiers within GenBank/EMBL records. This is
distinct from the [NCBI five-column submission table](https://www.ncbi.nlm.nih.gov/genbank/feature_table/).
The retained six plant records have joined/partial locations and repeated qualifiers.
The [bounded INSDC adapter](feature-locations.md) now covers these retained examples. Earlier reports marked them unsupported instead of
reducing a joined location to its outer span. The existing GTF reader also supplies
byte preservation, not an executable GTF-to-Dataset conversion profile.

Explicit ordered parts, partial endpoints and circular references now have a bounded
GenBank profile. Remote locations, between-base sites and ambiguous bounds remain
unsupported. BED's block children retain their original profile meaning; they are
not silently reinterpreted as the new location class. Additional NMDC/JGI, Prokka
and Phytozome conventions remain candidates, not interchangeable dialect names.

A new supported conversion must add a versioned contract, importer, reverse mapper,
profile validation, real and generated round-trip cases, rejection controls and an
expected report outcome. Change the profile version when its mapping/domain changes.
Constrained publication profiles (for example a scalar-only table) must separately
declare how arrays, references and metadata can be reconstructed. Passing the flat
schema audit does not establish conversion fidelity.
