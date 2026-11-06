# IMG dialects

Dialect schemas for files written by the JGI IMG annotation pipeline, and their mappings to the feature model. [Conversion profiles](conversion-profiles.md#dialect-schemas) says what a dialect schema is and how it differs from a conversion profile.

## IMG functional annotation GFF

The first dialect is [`img-functional-gff.yaml`](../model/dialects/img-functional-gff.yaml), for the JGI IMG pipeline's `*_functional_annotation.gff`. It was measured on 2026-09-25 against two JGI isolate annotations (Clostridium acetobutylicum DJ311 `Ga0423362`, 4,439 rows; Methanococcus maripaludis S1 `Ga0416744`, 2,005 rows), which need a JGI login to download (https://github.com/turbomam/feature-table-corpus/issues/52), and the vendored NMDC file. The Clostridium file is now vendored too, as `corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_functional_annotation.gff`.

- `gff3-contig/4.0.0` rejects both isolate files at their first product name containing a comma (`product-cardinality`), for example "glutamate-1-semialdehyde 2,1-aminomutase". 96 product names in the two files have one. The dialect splits commas only for the keys it types as lists (`pfam`, `cog`, `ko`, `ec_number`, `tigrfam`, `smart`, `superfamily`, `cath_funfam`, `transmembrane_helix_parts`).
- Rows come from five tools (GeneMark, Prodigal, INFERNAL, tRNAscan-SE, CRT) in eight column 3 types. There are no header or comment lines.
- IDs are `<seqid>_<start>_<end>`, except CRISPR repeat units, which take their CRISPR's ID plus `_DR1`, `_DR2` in order. Only repeat units carry `Parent`, and only CRISPR rows and repeat units are unstranded.
- A key can repeat: one Prodigal CDS has `shortened` twice. Key order is kept in `attribute_order` so rows can be written back.
- `partial` is `5'`, `3'` or `5',3'`. The last, a feature incomplete at both ends, is one value and not a list; NMDC metagenome files write it on 627 GFF lines, and the isolates never do.
- Lines end with LF and the file ends with a newline, since that is all the writer emits; a carriage return or a missing final newline is rejected. `parse --output` refuses a path that already exists.

`just dialect-validate-img-functional FILE` parses a file, validates it with the LinkML validator, and adds the cross-row checks a schema can't express. The tests edit single rows of a [constructed fixture](../tests/fixtures/img-functional-gff/README.md) to show each rule rejects what it should.

## Mapping a dialect with linkml-map

[`img-functional-gff.transform.yaml`](../model/transforms/img-functional-gff.transform.yaml) maps dialect rows to `SequenceFeature` with [linkml-map](https://github.com/linkml/linkml-map) 0.5.4, pinned in [`requirements-mapping.txt`](../requirements-mapping.txt). The reverse mapping is not written by hand: it is generated from the same file with linkml-map's inverter each time (https://github.com/turbomam/feature-table-corpus/issues/55).

linkml-map handles the nine columns, the typed keys with a `SequenceFeature` slot (`ID`, `Parent`, `product`, `product_source`) and the strand enum. `scripts/img_functional_map.py` does four things it couldn't, found while building this on 2026-09-25:

- MELT turns wide slots into key/value rows, but keeps a list as one value, keeps non-string types, and follows the spec's slot order. Column 9 needs one `Attribute` per value, as text, in file order, so the script builds `attributes` itself. Every key is kept, including those that also fill a `SequenceFeature` slot, as `gff3-contig` does; the reverse step rejects a SequenceFeature whose slot and attribute copies disagree.
- A constant slot (`coordinate_system: contig`) makes inversion fail, so the script sets it.
- linkml-map won't build records inside an expression, so the script makes one `Contig` per distinct seqid, in file order.
- Inversion drops `mirror_source` from the strand enum mapping, which turns every strand into nothing on the way back, so the script copies it from the forward specification.

It also derives each `Contig.translation_table` from the CDS rows, by the rule under [Derived slots](conversion-profiles.md#derived-slots). The reverse step writes only the attributes back and re-derives the table, so a Dataset that leaves the slot unset still maps back, and a table with no CDS attribute behind it is refused as a loss.

`just map-img-functional-roundtrip FILE` validates the dialect, maps forward, validates the Dataset with `scripts/validate_closed.py`, maps back, and requires every row to come back equal. It then writes GFF text and requires it to be the source byte for byte. Run on 2026-09-25, all rows came back equal for Clostridium acetobutylicum `Ga0423362` (4,439 features, 53,609 attributes) and Methanococcus maripaludis S1 `Ga0416744` (2,005 features, 24,507 attributes), with the text differing only in number spelling on 430 and 196 lines: scores such as `84.50` came back as `84.5`, and CRISPR lengths such as `26` as `26.0`.

Since 2026-09-28 forward keeps the source's spelling (https://github.com/turbomam/feature-table-corpus/issues/107). A column 9 number keeps it in its Attribute text, which is a string. A score is a number in the model, so its spelling goes in a separate map of `feature_id` to text, and only for scores the dialect would otherwise write differently. `roundtrip` holds both in memory; `forward --spelling FILE` writes the map and `reverse --spelling FILE` reads it. A kept spelling is used only while it still parses to the SequenceFeature's value, so an edited value is written as edited. `Ga0423362` now comes back byte for byte, its 430 lines included. `Ga0416744` is not in the repo and was not rerun.

`just map-img-functional FILE OUT` and `just map-img-functional-back DATASET OUT` run each direction on its own, and never overwrite an existing file. The reverse direction maps its result forward again and refuses unless that reproduces the input Dataset, so a slot the dialect can't hold, such as `translated_sequence` or a contig length, is an error rather than a silent loss.

## IMG per-method hit files

The second dialect, [`img-per-method-gff.yaml`](../model/dialects/img-per-method-gff.yaml), covers the seven files the IMG pipeline writes per search: `_pfam`, `_cog`, `_ko_ec`, `_tigrfam`, `_smart`, `_supfam` and `_cath_funfam`. Column 1 is a gene ID, columns 4 and 5 are amino acid positions in that gene's protein, and column 3 is the hit's accession rather than a feature type. It was measured on 2026-09-25 against the same two isolates (22,872 and 10,991 rows) and the eight vendored NMDC files of these types (443 rows); every file validates.

- Each method writes one fixed key order, and the validator requires it exactly. The six HMMER-style files write `e-value` or `independent_domain_e-value`; the lastal KO/EC file writes `evalue`.
- COG, TIGRFAM and SMART files leave column 2 empty. The other four name their tool.
- A KO/EC accession packs every KO joined by `_`, then `__` and every EC number joined by `_`, for example `KO:K01990_KO:K01992__EC:7.6.2.-_EC:3.6.3.-`. 1,467 of 2,884 rows carry ECs.
- IDs are `<gene ID>_<start>_<end>`. Every hit ends within its protein, whose length is at most a third of the gene span that the gene ID itself records, and `alignment_length` always equals the hit's length.
- Every Pfam row in both isolates has `e-value=13`, while the NMDC Pfam files have values such as `6e-18`. The dialect records this and accepts it.

`write()` turns parsed rows back into GFF text and refuses unless that text parses to the same rows, so the dialect's own round trip is checked by parsed rows, not bytes. Written without the source's spelling, numbers are respelled: `91.40` comes back as `91.4` and `1.22e+03` as `1220.0`, on 8,638 of the 34,306 real lines. The mapping below passes the source spelling back. Numbers must be plain ASCII (`1_2`, `+395` and full-width digits are rejected), columns 4, 5 and 8 have no leading zero (`0100` is rejected, as in the functional and TMHMM/SignalP dialects), and lines must end with LF.

The parser infers the method from the first row's accession and requires every row, and a file name ending `_<method>.gff`, to agree. `just dialect-validate-img-per-method FILE` runs it. The tests edit single rows of [constructed fixtures](../tests/fixtures/img-per-method-gff/README.md), one per method.

[`img-per-method-gff.transform.yaml`](../model/transforms/img-per-method-gff.transform.yaml) maps hit rows to `SequenceFeature` with linkml-map, and `scripts/img_per_method_map.py` adds what linkml-map can't do, as for the functional annotation. A hit is on [protein coordinates](protein-coordinates.md): its `seqid` is the CDS whose translation its positions count along, and that CDS is its only `parent`. The hit files hold no CDS rows, so the mapping takes the same genome's `_functional_annotation.gff` too, which supplies the contigs and CDS features; every hit gene in both isolates is a CDS there. `type` is the accession, as `nmdc-pfam-protein` does, and `score_type` stays unset because nothing retained says what kind of score column 6 is.

One Dataset can hold every method of a genome. A hit's source ID is `<gene>_<start>_<end>`, unique within its file but shared by hits of different methods on the same span: in Ga0423362's seven files, 1,138 hit IDs appear in more than one file (counted 2026-09-28). So a hit's `feature_id` is `<ID>|<method>|<type>`, for example `Ga0423362_01_1001207_1001923_10_228|pfam|PF03306`, and the source ID stays as its `ID` attribute ([issue 98](https://github.com/turbomam/feature-table-corpus/issues/98)). The rule holds for a single file too, so a hit's `feature_id` doesn't depend on which other files share its Dataset, and it is the form nmdc-lakehouse uses for NMDC hits. The reverse step refuses a hit whose `feature_id` doesn't match its `ID` attribute, method and type.

`just map-img-per-method-roundtrip FUNCTIONAL HIT...` maps the hit files forward into one Dataset with the functional annotation, validates it, maps back, and requires every row of every file to come back equal and every file's text to be the source byte for byte, keeping number spelling as the functional mapping does (`--spelling` on both directions). On 2026-09-28 it held for all seven methods of Ga0423362 in one Dataset (22,872 hits), with every file byte for byte. `just map-img-per-method FUNCTIONAL HIT... OUT` and `just map-img-per-method-back DATASET PREFIX` run each direction, and never overwrite a file.

The other per-genome files were measured on the same date to place them:

- `_crt`, `_trna`, `_rfam`, `_rfam_rrna`, `_rfam_ncrna_tmrna`, `_rfam_misc_bind_misc_feature_regulatory` and `_structural_annotation` hold contig rows of the functional annotation's own kinds, and all 14 isolate files validate against the first dialect. Every structural annotation ID is also in `_functional_annotation.gff`, and so is every CRT, tRNA and Rfam row, verbatim, except one: a Ga0423362 tmRNA row (`Ga0423362_02_1250883_1251241`) in the two Rfam files that the functional annotation lacks.
- `_prodigal` and `_genemark` also hold first-dialect rows: with their comment lines removed (and GeneMark's blank lines), all four isolate files validate against it. The comments are the tools' own: a `##gff-version 3` line and per-contig `# Sequence Data` and `# Model Data` lines from Prodigal. GeneMark writes a `##gff-version 2` line, then a 7-line `#` block (program version, input and parameter files, translation table, run date), then a blank line and a `##sequence-region` line before each contig's rows. The first dialect rejects comment lines, so accepting these files means extending it, not a new dialect.
- Three vendored NMDC files (Rfam, one structural annotation, GeneMark) failed the first dialect only because metagenome rows can be partial at both ends (`partial=5',3'`). It accepts that value since https://github.com/turbomam/feature-table-corpus/issues/65, and all three validate (checked 2026-09-28). The NMDC GeneMark file has no header lines.
- `_tmh` (TMHMM topology, column 3 `Inside`, `Outside` or `TMhelix`, score `.`) and `_cleavage_sites` (SignalP, column 3 `cleavage_site`, no `ID`) are on protein positions like the hit files, but their column 3 is not an accession and their keys differ. They have their own dialect, below.

## IMG TMHMM and SignalP files

[`img-tmhmm-signalp-gff.yaml`](../model/dialects/img-tmhmm-signalp-gff.yaml) covers `_tmh.gff` (TMHMM topology, written by `decodeanhmm 1.1g`) and `_cleavage_sites.gff` (SignalP 4.1), https://github.com/turbomam/feature-table-corpus/issues/76. It was measured on 2026-09-28 against both isolates: 9,710 and 4,078 TMHMM rows on 1,066 and 436 genes, and 146 and 79 SignalP rows. All four files validate, and the Clostridium pair is vendored.

- A TMHMM file lists only genes with at least one helix. Each gene's segments are one block that starts at residue 1, runs without gaps, alternates between `TMhelix` and `Inside` or `Outside`, begins and ends outside a helix, and switches side across every helix. Rows carry only an `ID` of `<gene ID>_<start>_<end>` and no score.
- The last segment ends at the protein's length, a third of the gene span less the stop codon, except in two Methanococcus genes where it ends one residue later. The check requires one of those two, so a file cut short inside a gene is rejected.
- A SignalP row spans the two residues around the cleavage, so its end is start + 1, and a gene has at most one. Keys are `D-score`, `network` and `organism_type` in that order. Column 6 is a score between 0 and 1 that differs from the D-score in every row.
- `organism_type` is `gram-` in every row, including the Gram-positive Clostridium's and the archaeal Methanococcus's. It is kept as written, not interpreted.

The parser infers the method from the first row's column 3 and requires every row, and a file name ending `_tmh.gff` or `_cleavage_sites.gff`, to agree. `just dialect-validate-img-tmhmm-signalp FILE` runs it. The writer reproduces both TMHMM files byte for byte; in the SignalP files it respells a trailing zero (`0.670` as `0.67`) on 49 of 225 lines, so their round trip is checked by parsed rows, as in the other IMG dialects. The tests edit single rows of [constructed fixtures](../tests/fixtures/img-tmhmm-signalp-gff/README.md).

[`img-tmhmm-signalp-gff.transform.yaml`](../model/transforms/img-tmhmm-signalp-gff.transform.yaml) maps the rows to `SequenceFeature` with linkml-map, and `scripts/img_tmhmm_signalp_map.py` maps them with the genome's functional annotation GFF, which supplies the CDS, as for the per-method hits:

- Each segment or site is a SequenceFeature on protein coordinates. Its seqid is its CDS, which is also its only parent.
- `feature_id` is `<seqid>_<start>_<end>|<method>|<type>`, the form of https://github.com/turbomam/feature-table-corpus/issues/98, with `tmh` or `cleavage_sites` as the method. SignalP rows have no `ID`, so the source ID is built from the row, as for the taxon bundle's tables. A TMHMM row's `ID` stays as its `ID` Attribute.
- SignalP's column 6 becomes `score` with `score_type` unset, since nothing in the files says which score it is; the D-score stays an Attribute. TMHMM rows have no score.
- Number spelling is kept as in the functional and per-method mappings (`--spelling`), so the SignalP `0.670` values come back as written.

`just map-img-tmhmm-signalp-roundtrip FUNCTIONAL FILE...` maps forward, validates the Dataset, maps back and requires every file byte for byte. On 2026-09-28 it held for the vendored Clostridium `_tmh.gff` (9,710 rows) and `_cleavage_sites.gff` (146 rows) in one Dataset with the functional annotation (14,295 features). `just map-img-tmhmm-signalp` and `just map-img-tmhmm-signalp-back` run each direction, and never overwrite a file.

## IMG taxon bundle

[`img-taxon-bundle.yaml`](../model/dialects/img-taxon-bundle.yaml) is the third dialect in https://github.com/turbomam/feature-table-corpus/issues/54: the older IMG taxon download, a `<taxon_oid>.gff` written from the `img_core_v400` database plus `<taxon_oid>.<kind>.tab.txt` tables whose columns the bundle's `README.txt` documents. It was measured on 2026-09-25 against two bundles, Bacillus sp. V-88 (`IMG_AP-1121004`, taxon 2708743150, 4,628 GFF rows, 7 tables) and Zymomonas mobilis ATCC 10988 (`IMG_AP-1377582`, taxon 645058785, 1,942 GFF rows, 8 tables), both downloaded to `local/jgi/`.

The tables name genes only by `gene_oid`, which is the GFF row's `ID`, so a bundle is validated as one document with one class per table. What the two bundles share:

- The GFF starts with `##gff-version 3`. Score is always `.`, and phase is `0` on every gene row, RNA genes included. Column 9 is `ID`, `locus_tag`, then `product` on CDS and rRNA rows only. There is no gene hierarchy. Types are CDS, tRNA, rRNA, RNA and CRISPR.
- The 48 CRISPR rows, all in Zymomonas, have no end, no ID and column 9 `.`. They repeat two start positions on each of the 24 contigs, 17 of which are shorter than the larger one, so they carry no usable location. The dialect accepts them as written.
- Every `gene_oid` in every table is a CDS, and a gene's `gene_length` is the same in every table. Rows are sorted by `gene_oid`. TMHMM segments tile each protein from 1 to its length.
- A KO whose name lists several EC numbers gets one row per number, and the EC column shortens trailing unknown parts to one, so `[EC:3.1.-.-]` in the name is `EC:3.1.-` in the column.
- Only `.ipr.tab.txt` has GO terms, joined with `|`. Pfam accessions are written `pfam00578`.

`.kog.tab.txt`, `.crispr.txt` and a non-empty `img_ko_flag` are documented but were not in either bundle, so they fail until measured. Any other `<taxon_oid>.*` file beside the GFF fails too, except the documented sequence files (`.fna`, `.genes.fna`, `.genes.faa`, `.intergenic.fna`) and the downloaded `.tar.gz` they come in, so no table goes unchecked. Numbers must use ASCII digits with no leading zeros and no trailing fractional zeros, as IMG writes them, which keeps write-back exact. `just dialect-validate-img-taxon GFF` checks the GFF and every table beside it. Both bundles pass, and the writer reproduces all 17 files byte for byte. The tests edit single rows of a [constructed bundle](../tests/fixtures/img-taxon-bundle/README.md) to show each rule rejects.

[`img-taxon-bundle.transform.yaml`](../model/transforms/img-taxon-bundle.transform.yaml) maps the GFF rows and every table with positions to `SequenceFeature`, one linkml-map derivation per source class, and `scripts/img_taxon_bundle_map.py` adds the rest:

- A table row is a hit on [protein coordinates](protein-coordinates.md), on the CDS its `gene_oid` names. Its `feature_id` follows https://github.com/turbomam/feature-table-corpus/issues/98: `<gene_oid>_<start>_<end>|<table>|<type>`, since table rows have no ID. `score` is `bit_score` where the table has one, with `score_type: bit_score`, because the README names the column so. Every other column is an Attribute in column order, as the dialect writes it. A list cell, InterPro `go_info`, is one Attribute per `|`-separated member, in cell order.
- A KO hit that lists several EC numbers is written as one row per number (126 extra rows in Bacillus, 79 in Zymomonas). It becomes one SequenceFeature with one `EC` Attribute per row; the rows must be adjacent and agree in every other column, or the bundle is refused.
- `.xref.tab.txt` has no positions, so each row becomes a `stable_identifiers` entry on its CDS (https://github.com/turbomam/feature-table-corpus/issues/102): `ncbigi:` for `GI`, `genbank:` for `GenBank/EMBL`, both registered in the Bioregistry. The `GenBank/EMBL` IDs look like RefSeq protein accessions (`ZP_`), but the label is IMG's and is kept.
- CRISPR GFF rows are skipped and counted (https://github.com/turbomam/feature-table-corpus/issues/101). All 48 are in Zymomonas, use two start positions repeated on every contig, and 29 start past their contig's end. https://github.com/turbomam/feature-table-corpus/issues/104 tracks recovering the real arrays.

`just map-img-taxon-roundtrip GFF` requires every file back byte for byte, the GFF less any skipped rows. On 2026-09-28 it held for Bacillus (all 8 files, 36,555 hits, nothing skipped) and Zymomonas (all 9 files, 14,750 hits, 3,690 identifiers, 48 CRISPR rows skipped).

## IMG 4.14 assembled GFF

[`img-assembled-gff.yaml`](../model/dialects/img-assembled-gff.yaml) covers `106476.assembled.gff` in the Bacillus bundle, IMG pipeline 4.14.0 output, https://github.com/turbomam/feature-table-corpus/issues/77. It is the only file of this vintage known here, so every rule was measured on that one file (2026-09-28, 4,693 rows on 63 contigs) and a second file may break some of them.

- There is no header. Column 2 names the calling tool (Prodigal for CDS, INFERNAL for tRNA and the Rfam classes, HMMER for rRNA), column 6 is always `.`, strand is `1` or `-1`, phase is `0` on every CDS and `.` elsewhere, and every column 9 ends with `;`.
- Each type writes one key order; two rRNA rows add `LowScore` twice with the same value. CDS rows carry Prodigal's `conf` with two decimals and `gc_cont` with three.
- IDs are `<seqid>.<n>`, with n increasing within a contig; on two contigs it skips a number. The locus tag is the contig ID followed by a counter that runs 1, 2, 3 within the contig.
- A tRNA's `codon` is the reverse complement of the anticodon in its product, an rRNA's `Name`, `Type` and `product` are the same text, and each Rfam `Model` has one accession.
- Its rows include all 4,628 taxon GFF rows by locus tag, at the same coordinates and strand, plus 39 `misc_bind` and 26 `misc_feature` rows that the taxon GFF drops; its 39 `misc_RNA` rows are the taxon GFF's `RNA`.

`just dialect-validate-img-assembled FILE [TAXON_GFF]` runs it. With the taxon GFF, read with the taxon bundle dialect's own parser, it also checks both directions: every taxon row is here at the same coordinates, strand and type (`RNA` there is `misc_RNA` here), and every row here but misc_bind and misc_feature is in the taxon GFF. The parser accepts only canonical numbers (no leading zeros) and the measured two- and three-decimal spellings, so the writer reproduces any valid file byte for byte. The tests edit single rows of a [constructed fixture](../tests/fixtures/img-assembled-gff/README.md).

[`img-assembled-gff.transform.yaml`](../model/transforms/img-assembled-gff.transform.yaml) maps the rows to `SequenceFeature` with linkml-map, and `scripts/img_assembled_gff_map.py` adds the same pieces as the other IMG mappings. The strand derivation maps `1` and `-1` to `+` and `-`; `linkml-map invert` keeps those value derivations, so unlike `mirror_source` they need no repair. Each attribute value is the text the dialect's writer produces, so `conf=100.00` stays `100.00`. `just map-img-assembled-roundtrip FILE` requires the written file to equal the source byte for byte; on 2026-09-28 it held for `106476.assembled.gff` (4,693 rows, 18,899 attributes). `just map-img-assembled FILE OUT` and `just map-img-assembled-back DATASET OUT` run each direction and never overwrite a file.
