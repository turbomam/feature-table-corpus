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
| [`nmdc-pfam-protein/4.0.0`](../model/profiles/nmdc-pfam-protein.yaml) | NMDC HMMER Pfam hits with explicit protein-to-CDS bindings, retained translations and amino-acid coordinates. | Reconstruct protein references and attributes without fabricating source Parent tags or exporting contextual CDS rows. Validation/export require the independent original context. |
| [`gff3-contig/3.0.0`](../model/profiles/gff3-contig.yaml) | Linear contig coordinates, decoded sequence/feature identities, source/type/score/strand/phase; `ID`, `Parent`, `product`, `Name`, `Note`, `Dbxref`, and `Ontology_term` also populate typed slots. Every attribute occurrence remains a generic pair. | Reconstruct nine columns from the Dataset and grouping indices. Repeated IDs/discontinuous features, circular references, protein-relative coordinates, unresolved parents, and ambiguous typed cardinalities are refused. |
| [`bed12-blocks/1.0.0`](../model/profiles/bed12-blocks.yaml) | One parent interval plus ordered block children. Source `[start,end)` becomes model `[start+1,end]`; chromosome names remain literal. Score and strand use core slots; name, RGB and thick drawing bounds use generic `bed:*` attributes. | Reconstruct twelve columns using the parent and children. Require positive, ordered, nonoverlapping blocks covering the enclosing boundaries. Zero-length intervals, fewer/extra columns and whitespace-delimited variants are refused. |

These restrictions belong to these adapters, not to the full input formats.
[UCSC's BED description](https://genome.ucsc.edu/FAQ/FAQformat.html#format1)
defines the coordinate and block conventions. In particular, a thick drawing span
is not necessarily a CDS. BED blocks become generic `sequence_feature` children;
the adapter does not invent transcript/exon identities or query-side alignment
coordinates. Overlap queries can return both the enclosing record and its blocks;
filter `bed:role=block` when asking about covered blocks. A gap overlaps the parent
span without becoming an annotated block.

The [NMDC Pfam profile](protein-relative-profile.md), `nmdc-pfam-protein/4.0.0`,
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
against two JGI isolate annotations (Clostridium acetobutylicum DJ311 `Ga0423362`, 4,439 rows;
Methanococcus maripaludis S1 `Ga0416744`, 2,005 rows), which need a JGI login to download
([#52](https://github.com/turbomam/feature-table-corpus/issues/52)), and the vendored NMDC file.
The Clostridium file is now vendored too, as `corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_functional_annotation.gff`.

- `gff3-contig/3.0.0` rejects both isolate files at their first product name containing a
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
- `partial` is `5'`, `3'` or `5',3'`. The last, a feature incomplete at both ends, is one value
  and not a list; NMDC metagenome files write it on 627 GFF lines, and the isolates never do.
- Lines end with LF and the file ends with a newline, since that is all the writer emits; a
  carriage return or a missing final newline is rejected. `parse --output` refuses a path that
  already exists.

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

It also derives each `Contig.translation_table` from the CDS rows, by the rule under
[Derived slots](#derived-slots). The reverse step writes only the attributes back and re-derives
the table, so a Dataset that leaves the slot unset still maps back, and a table with no CDS
attribute behind it is refused as a loss.

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

### IMG per-method hit files

The second dialect, [`img-per-method-gff.yaml`](../model/dialects/img-per-method-gff.yaml),
covers the seven files the IMG pipeline writes per search: `_pfam`, `_cog`, `_ko_ec`,
`_tigrfam`, `_smart`, `_supfam` and `_cath_funfam`. Column 1 is a gene ID, columns 4 and 5 are
amino acid positions in that gene's protein, and column 3 is the hit's accession rather than a
feature type. It was measured on 2026-09-25 against the same two isolates (22,872 and 10,991
rows) and the eight vendored NMDC files of these types (443 rows); every file validates.

- Each method writes one fixed key order, and the validator requires it exactly. The six
  HMMER-style files write `e-value` or `independent_domain_e-value`; the lastal KO/EC file
  writes `evalue`.
- COG, TIGRFAM and SMART files leave column 2 empty. The other four name their tool.
- A KO/EC accession packs every KO joined by `_`, then `__` and every EC number joined by `_`,
  for example `KO:K01990_KO:K01992__EC:7.6.2.-_EC:3.6.3.-`. 1,467 of 2,884 rows carry ECs.
- IDs are `<gene ID>_<start>_<end>`. Every hit ends within its protein, whose length is at most
  a third of the gene span that the gene ID itself records, and `alignment_length` always
  equals the hit's length.
- Every Pfam row in both isolates has `e-value=13`, while the NMDC Pfam files have values such
  as `6e-18`. The dialect records this and accepts it.

`write()` turns parsed rows back into GFF text and refuses unless that text parses to the same
rows, so the round trip is checked by parsed rows, not bytes. Numbers are respelled on the way:
`91.40` comes back as `91.4` and `1.22e+03` as `1220.0`, on 8,638 of the 34,306 real lines.
Numbers must be plain ASCII (`1_2`, `+395` and full-width digits are rejected), and lines must
end with LF.

The parser infers the method from the first row's accession and requires every row, and a file
name ending `_<method>.gff`, to agree. `just dialect-validate-img-per-method FILE` runs it. The
tests edit single rows of [constructed fixtures](../tests/fixtures/img-per-method-gff/README.md),
one per method.

[`img-per-method-gff.transform.yaml`](../model/transforms/img-per-method-gff.transform.yaml)
maps hit rows to `Feature` with linkml-map, and `scripts/img_per_method_map.py` adds what
linkml-map can't do, as for the functional annotation. A hit is on [protein
coordinates](protein-coordinates.md): its `seqid` is the CDS whose translation its positions count
along, and that CDS is its only `parent`. The hit files hold no CDS rows, so the mapping takes the
same genome's `_functional_annotation.gff` too, which supplies the contigs and CDS features; every
hit gene in both isolates is a CDS there. `type` is the accession, as `nmdc-pfam-protein` does, and
`score_type` stays unset because nothing retained says what kind of score column 6 is.

One Dataset can hold every method of a genome. A hit's source ID is `<gene>_<start>_<end>`, unique
within its file but shared by hits of different methods on the same span: in Ga0423362's seven
files, 1,138 hit IDs appear in more than one file (counted 2026-09-28). So a hit's `feature_id` is
`<ID>|<method>|<type>`, for example `Ga0423362_01_1001207_1001923_10_228|pfam|PF03306`, and the source ID stays
as its `ID` attribute ([issue 98](https://github.com/turbomam/feature-table-corpus/issues/98)). The
rule holds for a single file too, so a hit's `feature_id` doesn't depend on which other files share
its Dataset, and it is the form nmdc-lakehouse uses for NMDC hits. The reverse step refuses a hit
whose `feature_id` doesn't match its `ID` attribute, method and type.

`just map-img-per-method-roundtrip FUNCTIONAL HIT...` maps the hit files forward into one Dataset
with the functional annotation, validates it, maps back, and requires every row of every file to
come back equal, with written text differing only in number spelling. On 2026-09-28 it held for all
seven methods of Ga0423362 in one Dataset (22,872 hits). `just map-img-per-method FUNCTIONAL
HIT... OUT` and `just map-img-per-method-back DATASET PREFIX` run each direction, and never
overwrite a file.

The other per-genome files were measured on the same date to place them:

- `_crt`, `_trna`, `_rfam`, `_rfam_rrna`, `_rfam_ncrna_tmrna`,
  `_rfam_misc_bind_misc_feature_regulatory` and `_structural_annotation` hold contig rows of
  the functional annotation's own kinds, and all 14 isolate files validate against the first
  dialect. Every structural annotation ID is also in `_functional_annotation.gff`, and so is
  every CRT, tRNA and Rfam row, verbatim, except one: a Ga0423362 tmRNA row
  (`Ga0423362_02_1250883_1251241`) in the two Rfam files that the functional annotation lacks.
- `_prodigal` and `_genemark` also hold first-dialect rows: with their comment lines removed
  (and GeneMark's blank lines), all four isolate files validate against it. The comments are
  the tools' own: a `##gff-version 3` line and per-contig `# Sequence Data` and `# Model Data`
  lines from Prodigal. GeneMark writes a `##gff-version 2` line, then a 7-line `#` block
  (program version, input and parameter files, translation table, run date), then a blank line
  and a `##sequence-region` line before each contig's rows. The first dialect rejects comment lines, so accepting these files means extending
  it, not a new dialect.
- Three vendored NMDC files (Rfam, one structural annotation, GeneMark) failed the first
  dialect only because metagenome rows can be partial at both ends (`partial=5',3'`). It accepts
  that value since https://github.com/turbomam/feature-table-corpus/issues/65, and all three
  validate (checked 2026-09-28). The NMDC GeneMark file has no header lines.
- `_tmh` (TMHMM topology, column 3 `Inside`, `Outside` or `TMhelix`, score `.`) and
  `_cleavage_sites` (SignalP, column 3 `cleavage_site`, no `ID`) are on protein positions like
  the hit files, but their column 3 is not an accession and their keys differ. They have their
  own dialect, below.

### IMG TMHMM and SignalP files

[`img-tmhmm-signalp-gff.yaml`](../model/dialects/img-tmhmm-signalp-gff.yaml) covers `_tmh.gff`
(TMHMM topology, written by `decodeanhmm 1.1g`) and `_cleavage_sites.gff` (SignalP 4.1),
https://github.com/turbomam/feature-table-corpus/issues/76. It was measured on 2026-09-28 against
both isolates: 9,710 and 4,078 TMHMM rows on 1,066 and 436 genes, and 146 and 79 SignalP rows.
All four files validate, and the Clostridium pair is vendored.

- A TMHMM file lists only genes with at least one helix. Each gene's segments are one block
  that starts at residue 1, runs without gaps, alternates between `TMhelix` and `Inside` or
  `Outside`, begins and ends outside a helix, and switches side across every helix. Rows carry
  only an `ID` of `<gene ID>_<start>_<end>` and no score.
- The last segment ends at the protein's length, a third of the gene span less the stop codon,
  except in two Methanococcus genes where it ends one residue later. The check requires one
  of those two, so a file cut short inside a gene is rejected.
- A SignalP row spans the two residues around the cleavage, so its end is start + 1, and a gene
  has at most one. Keys are `D-score`, `network` and `organism_type` in that order. Column 6 is a
  score between 0 and 1 that differs from the D-score in every row.
- `organism_type` is `gram-` in every row, including the Gram-positive Clostridium's and the
  archaeal Methanococcus's. It is kept as written, not interpreted.

The parser infers the method from the first row's column 3 and requires every row, and a file
name ending `_tmh.gff` or `_cleavage_sites.gff`, to agree. `just dialect-validate-img-tmhmm-signalp
FILE` runs it. The writer reproduces both TMHMM files byte for byte; in the SignalP files it
respells a trailing zero (`0.670` as `0.67`) on 49 of 225 lines, so their round trip is checked
by parsed rows, as in the other IMG dialects. The tests edit single rows of
[constructed fixtures](../tests/fixtures/img-tmhmm-signalp-gff/README.md).

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

### IMG 4.14 assembled GFF

[`img-assembled-gff.yaml`](../model/dialects/img-assembled-gff.yaml) covers `106476.assembled.gff`
in the Bacillus bundle, IMG pipeline 4.14.0 output,
https://github.com/turbomam/feature-table-corpus/issues/77. It is the only file of this vintage
known here, so every rule was measured on that one file (2026-09-28, 4,693 rows on 63 contigs)
and a second file may break some of them.

- There is no header. Column 2 names the calling tool (Prodigal for CDS, INFERNAL for tRNA and
  the Rfam classes, HMMER for rRNA), column 6 is always `.`, strand is `1` or `-1`, phase is `0`
  on every CDS and `.` elsewhere, and every column 9 ends with `;`.
- Each type writes one key order; two rRNA rows add `LowScore` twice with the same value. CDS
  rows carry Prodigal's `conf` with two decimals and `gc_cont` with three.
- IDs are `<seqid>.<n>`, with n increasing within a contig; on two contigs it skips a number.
  The locus tag is the contig ID followed by a counter that runs 1, 2, 3 within the contig.
- A tRNA's `codon` is the reverse complement of the anticodon in its product, an rRNA's `Name`,
  `Type` and `product` are the same text, and each Rfam `Model` has one accession.
- Its rows include all 4,628 taxon GFF rows by locus tag, at the same coordinates and strand,
  plus 39 `misc_bind` and 26 `misc_feature` rows that the taxon GFF drops; its 39 `misc_RNA`
  rows are the taxon GFF's `RNA`.

`just dialect-validate-img-assembled FILE [TAXON_GFF]` runs it. With the taxon GFF, read with the
taxon bundle dialect's own parser, it also checks both directions: every taxon row is here at the same coordinates, strand and type (`RNA` there is
`misc_RNA` here), and every row here but misc_bind and misc_feature is in the taxon GFF. The parser
accepts only canonical numbers (no leading zeros) and the measured two- and three-decimal
spellings, so the writer reproduces any valid file byte for byte. The tests edit
single rows of a [constructed fixture](../tests/fixtures/img-assembled-gff/README.md).

[`img-assembled-gff.transform.yaml`](../model/transforms/img-assembled-gff.transform.yaml) maps the
rows to `Feature` with linkml-map, and `scripts/img_assembled_gff_map.py` adds the same pieces as
the other IMG mappings. The strand derivation maps `1` and `-1` to `+` and `-`; `linkml-map
invert` keeps those value derivations, so unlike `mirror_source` they need no repair. Each
attribute value is the text the dialect's writer produces, so `conf=100.00` stays `100.00`.
`just map-img-assembled-roundtrip FILE` requires the written file to equal the source byte for
byte; on 2026-09-28 it held for `106476.assembled.gff` (4,693 rows, 18,899 attributes).
`just map-img-assembled FILE OUT` and `just map-img-assembled-back DATASET OUT` run each direction
and never overwrite a file.

### Phytozome gene_exons GFF3 and annotation_info

Two more dialects describe a Phytozome genome's
[`gene_exons.gff3`](../model/dialects/phytozome-gene-exons-gff3.yaml) and its per-transcript
[`annotation_info.txt`](../model/dialects/phytozome-annotation-info.yaml), items 4 and 5 of
https://github.com/turbomam/feature-table-corpus/issues/54. Both were measured on 2026-09-25
against one genome only, Arabidopsis thaliana TAIR10 (`Phytozome-167` in
[the JGI input list](jgi-inputs.md)): 532,682 GFF3 rows and 35,386 table rows. TAIR restricts
redistributing substantial subsets of TAIR10, so no row of either file is in this repository;
the tests use a [constructed fixture](../tests/fixtures/phytozome/README.md).

- The GFF3 opens with `##gff-version 3` and `##annot-version TAIR10`, then gene blocks: a
  gene row, then each mRNA row followed by its exon, CDS and UTR rows. There is no score, no
  percent escape, and no comma in column 9, and each row type writes the same keys in the same
  order.
- Each part has its own ID, the mRNA's ID plus its type and a number, as in
  `X.1.TAIR10.CDS.2`. Numbers run in transcription order, so on the minus strand coordinates
  descend. A gene or mRNA ID is its Name plus `.TAIR10`.
- Every mRNA row has `longest=0` or `longest=1`, and each gene has exactly one `longest=1`
  (27,416 genes, 7,970 other isoforms). The flag is Phytozome's choice: in 16 of the 5,804
  genes with more than one isoform, the flagged one does not have the longest CDS. The
  feature model carries it as `Feature.is_representative`
  (https://github.com/turbomam/feature-table-corpus/issues/48).
- Each mRNA's `pacid` appears once in the table, as `PAC:<pacid>`, with the mRNA's Name as
  `transcriptName` and its gene's Name as `locusName`. All 35,386 match in both directions.
- In the table, one space separates values in `Pfam`, `Panther`, `ec`, `KOG`, `KO` and `GO`.
  `ec` holds four-part EC numbers, plus the non-EC token `EC:PROLINE-MULTI` in six rows,
  kept as written. Partial EC numbers such as `EC:1.1.1.-` are rejected, since none was read.
- Both files use LF line endings and end with a newline; a carriage return, a missing final
  newline, or a file with no data rows is rejected.

`just dialect-validate-phytozome-gff3 FILE` reads plain or gzip-compressed GFF3 as a stream
and validates rows in chunks of 5,000, so the whole genome is never one document. On the
TAIR10 file it took 23.5 seconds of wall time on an Apple M5 Max on 2026-09-25.
`just dialect-validate-phytozome-annotation FILE` validates the table, and
`just dialect-join-phytozome GFF3 FILE` checks that the two files name the same transcripts.
Beyond the schemas, the GFF3 checks cover ID construction, block order, part numbering, one
`longest=1` per gene, and spans: an mRNA spans its exons, each CDS and UTR sits inside an exon,
and a gene spans its mRNAs. Each writer, run on the TAIR10 files on 2026-09-25, reproduced them
byte for byte. There is no conversion profile for these dialects yet.

[`phytozome-gene-exons-gff3.transform.yaml`](../model/transforms/phytozome-gene-exons-gff3.transform.yaml)
maps the GFF3 rows to `Feature` with linkml-map, the same way as the IMG functional annotation
above, and `scripts/phytozome_gene_exons_map.py` adds the same four things linkml-map can't do.
Gene, mRNA and part rows each become a `Feature`, joined by `parent`. `longest` sets
`Feature.is_representative` (`1` true, `0` false) and, like `ID` and `Parent`, keeps its attribute
copy, which the reverse step requires to agree; `Name` and `pacid` have no `Feature` slot and travel
only as attributes. The two directives are not model
data: the reverse step writes `##gff-version 3` and recovers the annot-version from the gene IDs,
each of which is the gene's Name, a dot, and the annot-version (`.TAIR10` in the Arabidopsis file,
`.EXv1` in the fixture); all genes must agree. It rebuilds each row's text and parses it with the
dialect's own row parser, then maps the result forward again and requires the Dataset back.

`just map-phytozome-gff3-roundtrip FILE` requires the written file to equal the source byte for
byte. On the TAIR10 file on 2026-09-28 it held for all 532,682 rows (1,641,402 attributes) in 211
seconds on an Apple M5 Max, with a peak of 3.2 GB of memory. `just map-phytozome-gff3 FILE OUT`
and `just map-phytozome-gff3-back DATASET OUT` run each direction and never overwrite a file.

## Attributes and authority

The shared Attribute class still means a string key/value pair, independent of
GFF column 9. BED display/name values and parsed comment metadata use it too.

Every profile and dialect here that reads GFF column 9 or GenBank qualifiers follows one rule for multivalued values, stated in
[reusable attributes](attributes.md#multivalued-values): each value is its own Attribute
entry in source order, split before percent-decoding, and the source profile decides
which keys are multivalued.

| Source | Keys split on commas | Decoding | Example |
|---|---|---|---|
| `gff3-contig/3.0.0` | every key | after splitting | `Note=x%2Cy` is one entry `x,y`; `Parent=a,b` is two |
| `nmdc-pfam-protein/4.0.0` | every key, through the same GFF3 reader | after splitting | as for `gff3-contig` |
| IMG functional dialect and its mapping | only keys the dialect types multivalued (`pfam`, `cog`, `ko`, `ec_number`, `tigrfam`, `smart`, `superfamily`, `cath_funfam`, `transmembrane_helix_parts`); `shortened` repeats as a key instead | none; IMG writes no escapes | `product=glutamate-1-semialdehyde 2,1-aminomutase` is one entry |
| IMG per-method dialect | only `subject_gene_ids` | none | not yet mapped to `Feature` |
| IMG TMHMM and SignalP GFF | none; it declares no list keys | none | not yet mapped to `Feature` |
| IMG taxon bundle GFF | none; `ID`, `locus_tag` and `product` are single values | none | not yet mapped to `Feature` |
| Phytozome gene_exons GFF3 and its mapping | none; refuses any comma or `%` in column 9 | none | each key is one entry, for example `pacid=90000001` in the fixture |
| `insdc-locations/1.0.0` | none; a GenBank qualifier repeats instead | not applicable | two `/db_xref` lines are two entries |

`bed12-blocks/1.0.0` writes only fixed `bed:*` attributes and Prodigal comment metadata is one value per key, so neither splits anything. Tables that are not GFF, such as the Phytozome annotation_info file (lists separated by spaces) and the IMG taxon bundle TSVs, follow their own dialect schemas and are outside this table.

A literal comma in a `gff3-contig` value is a separator, so `product=a,b` is two products
and is refused (`product-cardinality`). polars-bio `read_gff` splits nothing and decodes
first, so its output does not follow the rule. `tests/test_attribute_splitting.py` checks
the first, second, third and fifth rows against the fixtures in
`tests/fixtures/attribute-splitting/`; `tests/test_locations.py` checks repeated INSDC
`db_xref` qualifiers. The taxon bundle row is read from its parser, not tested here.

GFF occurrences and comma-separated values become ordered pairs; mappings retain
the grouping indices, so `Note=a,b;Note=c` remains distinguishable from three
assignments. Empty values remain strings, distinct from absent assignments.
Original lexical cells retain escaping, delimiters and numeric spelling.

Typed GFF `feature_id`, `parent`, `product`, `name`, `note`, `dbxref` and `ontology_term` must
agree with their retained generic `ID`, `Parent`, `product`, `Name`, `Note`, `Dbxref` and
`Ontology_term` values. The last four are GFF3 reserved tags given typed slots in 3.0.0
([issue 43](https://github.com/turbomam/feature-table-corpus/issues/43)); `Name` takes at most one
value, and the other three keep every value in order. `Alias` and `Derives_from` appear in no
corpus file and stay generic. Reconstructed output uses the typed
slots for those assignments and rejects conflicting generic copies. Missing source
IDs receive document-local synthetic IDs but remain missing in exported GFF. The
model's attribute list now explicitly records that order is retained.

### Derived slots

Two model slots are filled from retained source values rather than read from a column
([#72](https://github.com/turbomam/feature-table-corpus/issues/72)):

- `Contig.translation_table`, in `gff3-contig` and the IMG functional mapping, when every CDS
  on the contig carries a `translation_table` attribute and all of them name the same assigned
  NCBI genetic code (`011` counts as 11). CDS values that disagree, within one row or across
  rows, are refused with `translation-table-conflict`. A contig is left unset when any CDS on
  it lacks the attribute, or when all its CDS name the same unassigned or non-integer value.
  The Dataset validator rejects the same disagreements, whether or not the contig has a table.
- `Feature.score_type` is `bit_score` on `nmdc-pfam-protein` rows that have a score, because
  nmdc-lakehouse documents NMDC's HMMER column 6 as a bit score
  (https://github.com/microbiomedata/nmdc-lakehouse/blob/main/docs/pfam_annotation_gff.md).
  No other profile sets it: nothing retained says what Prodigal, GeneMark, lastal, INFERNAL or
  BED scores are.

Adding these slots changed both profiles, so both moved to 2.0.0: each adds output, and each
now refuses input 1.0.0 accepted (conflicting CDS tables, in the imported file for `gff3-contig`
and in the protein context for `nmdc-pfam-protein`). A bundle made under 1.0.0 is refused as an
unsupported profile rather than validated against the new rules.

`nmdc-pfam-protein` moved again, to 3.0.0, when a protein hit's `seqid` changed from the contig to
its CDS ([protein coordinates](protein-coordinates.md)). A 2.0.0 bundle is refused the same way.

Typed slots for the GFF3 reserved tags `Name`, `Note`, `Dbxref` and `Ontology_term`
([issue 43](https://github.com/turbomam/feature-table-corpus/issues/43)) add output to both GFF3
profiles, so `gff3-contig` moved to 3.0.0 and `nmdc-pfam-protein`, whose hits carry `Name`, to
4.0.0. Bundles made under the earlier versions are refused as unsupported profiles.

The Dataset validator rejects conflicting CDS tables, as the converters do, but it accepts a
contig table that no CDS attribute backs, for example one a source states in a pragma or a
Prodigal sequence comment. The IMG functional mapping cannot write such a table back, so its
reverse step refuses it as a loss; that refusal is about what the dialect can hold, not a
validity rule.

Neither slot is read by export, so exact and reconstructed bytes do not change. Re-import
derives them again, so removing or editing one is an edit like any other and is refused.
`nmdc-pfam-protein` does not derive `translation_table` for its context contigs: the context
Dataset is used as supplied. `insdc-locations` does not derive it either; GenBank CDS carry
`/transl_table`, with table 1 implied when absent, which needs its own rule.

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
  gff3-contig/3.0.0 nmdc:wfmgan-11-9ya9xh30.1 \
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
not silently reinterpreted as the new location class. Additional NMDC/JGI and Prokka
conventions remain candidates, not interchangeable dialect names, and the Phytozome
dialects above are validated but not yet converted.

A new supported conversion must add a versioned contract, importer, reverse mapper,
profile validation, real and generated round-trip cases, rejection controls and an
expected report outcome. Change the profile version when its mapping/domain changes.
Constrained publication profiles (for example a scalar-only table) must separately
declare how arrays, references and metadata can be reconstructed. Passing the flat
schema audit does not establish conversion fidelity.
