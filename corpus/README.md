# Corpus

Real, traceable examples of GFF and other genome feature table content, built to support work on a unified LinkML model for genome features across DOE Biological and Environmental Research data sources. The point is breadth of real producers, not volume: every entry names the tool or project that wrote it, the URL it came from, and the date it was fetched.

| Path | Contents |
|---|---|
| [`index.yaml`](index.yaml) | Inventory, provenance, licenses, and checksums |
| [`PROVENANCE.md`](PROVENANCE.md) | Dated acquisition and correction history |
| [`sources/`](sources/) | Preserved upstream source text |
| [`specifications/`](specifications/) | Prior-art schemas and specification extracts |
| [`fixtures/`](fixtures/) | Deliberately altered, indexed test cases |
| [`derived-examples/`](derived-examples/) | Explicit selections of unchanged real source rows |

## What is here

108 entries in five tiers. The index is [corpus/index.yaml](index.yaml), which is the source of truth for the corpus inventory; this page describes it.

| Tier | Count | Meaning |
|---|---|---|
| vendored | 66 | The file is in this repository, with its origin URL and an MD5 checksum |
| linked | 24 | Too large or not redistributable, so a stable public URL is recorded instead |
| derived | 12 | Nine deliberately altered fixtures and three explicitly selected real excerpts (a BGC, and 200 Populus genes in GFF3 and table form), each traceable to its source |
| restricted | 5 | Behind a login. Recorded for completeness, not fetchable here |
| not located | 1 | Known to exist, no public URL found. Recorded so the gap stays visible |

**The one promise this corpus makes.** A file under `corpus/sources/` is byte-for-byte what its origin served. Nothing in this repository writes into those files, and the verifier enforces it two ways: every checksum is compared on each run, and any provenance comment appearing in a sourced file is reported as `SOURCED-EDITED`. The nine files under `corpus/fixtures/malformed/` and `corpus/fixtures/edge-cases/` are the only altered content, they live only in those directories, and each one carries four appended comment lines naming its source and the single change made to it. The verifier fails if a derived file lacks them, and CI proves both halves of that check can fail by injecting each violation on purpose.

So the derived files are not byte-exact copies plus one change; they are that plus four comment lines. The trade is deliberate: a fixture found loose on disk still says where it came from, which `corpus/index.yaml` cannot do once a file is copied out.

The checked-in source files are plain text, so their contents are reviewable in a diff.

## The vendored files

The NMDC collection contains 20 retained files in the following three groups.

**Original NMDC GFF sample: 14 files, 158 bytes to 4.6 KB.** One per distinct `data_object_type` that carries GFF in NMDC production. Each is the smallest real file of its kind out of roughly 600 sampled through the public API, and each checksum matches the MD5 recorded in the NMDC record itself. These 14 are the useful part of this corpus, because they show that one annotation is not one file. It is a set of evidence streams that all describe the same features:

- gene callers: Prodigal, GeneMark
- feature finders: tRNAscan, CRISPR Recognition Tool, Rfam
- database searches, each written to its own file: Pfam, TIGRFAM, SMART, SUPERFAMILY, CATH functional families, Clusters of Orthologous Groups, KEGG Orthology with Enzyme Commission numbers
- roll-ups: structural, functional

All are outputs of the JGI IMG annotation pipeline, reachable openly through NMDC. Licensed CC BY 4.0 under the [NMDC data use policy](https://microbiomedata.org/nmdc-data-use-policy/).

**NMDC, 3 additional non-GFF files.** Enzyme Commission TSV, KEGG Orthology TSV, and CRT `.crisprs` text extend the corpus to other feature-bearing formats. The EC and KO files carry hits; the selected `.crisprs` file contains three populated, six-field records. Together these first two groups contain 17 files; the 14-file GFF measurements above remain specifically about the original sample.

**NMDC, 3 companion files for protein conversion.** A full Pfam GFF, structural GFF and protein FASTA from `nmdc:wfmgan-11-5xxrm214.2` bring the NMDC total to 20. They support the [protein-relative conversion example](../docs/protein-coordinates.md#the-nmdc-pfam-profile): 416 hits on 397 proteins, with explicit CDS bindings and retained translations. These were selected as related evidence, independently of the smallest-file sample.

**JGI IMG isolate annotation sets, 28 files, 13.4 MB.** Every NMDC file above comes from a metagenome workflow, so these add annotation of single organisms, from two pipeline generations, under `corpus/sources/jgi-img/` (https://github.com/turbomam/feature-table-corpus/issues/53). Clostridium acetobutylicum DJ311 `IMG_AP-1268149` (`Ga0423362`) has all 19 per-method GFF files of the newer IMG pipeline, the same evidence streams as the NMDC sample above plus SignalP, TMHMM and three Rfam subsets. Bacillus sp. V-88 `IMG_AP-1121004` has one assembly annotated twice: `106476.assembled.gff` from IMG pipeline 4.14.0 and `2708743150.gff` from `img_core_v400`, with that taxon's seven tab-separated side tables (COG, InterPro with GO, KO with EC, Pfam, SignalP, TIGRFAM, TMHMM). Its 8.6 MB GenBank file is left out. Each md5 matches the JGI Data Portal search API. Downloading needs a JGI login ([docs/jgi-inputs.md](../docs/jgi-inputs.md)). Both records are `data_utilization_status: Unrestricted` and were accepted before FY22, so the [JGI Legacy Data Policy](https://jgi.doe.gov/sites/default/files/2025-01/Data%26Support_LegacyDataPolicy.pdf) governs them. It names no license; for proposals of this age it says publications "should" include JGI's acknowledgment. **This repository asks for attribution**: cite the dataset DOI (Clostridium https://doi.org/10.25585/1488021, Bacillus https://doi.org/10.25585/1488085) and include JGI's acknowledgment, "These sequence data were produced by the US Department of Energy Joint Genome Institute http://www.jgi.doe.gov/ in collaboration with the user community." Each index entry repeats both.

**NCBI RefSeq, 2 files.** Complete tiny reference annotations from the canonical GFF3 producer, for phiX174 at 6.5 KB and phage lambda at 58 KB. Public domain. Both are decompressed from the gzip the FTP site serves, because this repository carries no binary files. These give a clean baseline: a well formed GFF3 with a spec-version pragma, sequence regions, and proper parent and child structure.

**NCBI RefSeq viral GFF3, 8 files.** Whole-record GFF3 exports of eight virus genomes, chosen by @simroux to show unusual viral genome features: origin-crossing features on circular genomes, a metagenome-assembled phage, ribosomal slippage, stop-codon readthrough, spliced giant-virus genes, a partial CDS, a modified base and RNA genomes. Each is byte-identical to NCBI's nucleotide-record GFF3 export on 2026-10-30. Which of them `gff3-contig/4.0.0` imports is recorded in [analyses/conversion-roundtrips/cases.yaml](../analyses/conversion-roundtrips/cases.yaml) (https://github.com/turbomam/feature-table-corpus/issues/179).

**NCBI RefSeq GTF, 2 files.** The same two annotations in GTF rather than GFF3, so a model can be tested for round-tripping between the two column 9 grammars. Both declare `#gtf-version 2.2` in their own header.

## Columns, discretion, and what writers get wrong

[docs/columns-and-discretion.md](../docs/columns-and-discretion.md) answers three questions with quotes from the specifications and measurements against the files here: how many fields each format has and which formats are not one table, which columns leave the writer discretion, and which columns get populated incorrectly in practice.

Two findings from it are worth surfacing, both measured against real production files in this corpus rather than read from a document.

**Column 3 carries database accessions instead of Sequence Ontology terms.** Every per-database NMDC annotation file here puts the matched accession in the type column: Pfam accessions such as `PF00011`, plus `COG3666`, `TIGR02937` and `SM01408`. The specification requires an SO term that is an is_a child of `sequence_feature`. Seven of the fourteen NMDC file types do this, systematically. A unified model cannot assume column 3 holds an SO term, because the data it would load does not.

**Phase is the column to worry about.** GFF3 defines it as how many bases to skip inside the current feature; GTF defines the same column as which part of a codon the feature begins with. They agree at 0 and are easy to transpose at 1 and 2. In this corpus 366 of 368 phase values are 0, so a handler that mishandles 1 and 2 passes on almost all real data. The AgBioData group says the field is commonly misread by producers and consumers alike, yielding different amino acid sequences.

## Where this came from, and the analysis built on it

This corpus was assembled on 2026-09-11 as input to a discussion about a unified LinkML model for genome features across DOE Biological and Environmental Research data sources.

The companion analysis, which surveys the four existing models, the eleven named format flavors, the prior normalization efforts, and what the measurements here imply for a unified model, is a Claude artifact:

https://claude.ai/code/artifact/d8ee05e5-c7b1-49f7-a700-3ae4e9adad1c

That page is private to its owner, so it will ask you to sign in. Everything in it that this repository can support is reproduced here, in [docs/prior-art.md](../docs/prior-art.md) and [docs/columns-and-discretion.md](../docs/columns-and-discretion.md), so nothing load-bearing depends on access to it.

## Specifications

Thirteen specifications are recorded, two of them vendored and eleven linked.

The vendored two are the ones whose licenses allow it. `corpus/specifications/chado_1.4_feature_tables.sql` holds the seven Chado feature tables extracted from a 2.2 MB schema, under Artistic-2.0. Chado is worth reading closely for this work: it keeps the feature separate from its location and expresses parent and child through a relationship table, so nothing is nested. That is the same normalization a flat-table profile requires, reached independently twenty years earlier. `corpus/specifications/kbase_cdm_bioentity.yaml` is the KBase Common Data Model module holding the Feature class, under MIT. It constrains feature type to Sequence Ontology accessions under `sequence_feature` and carries provenance slots for source database and protocol, which the other models do not.

The other eleven are linked: the JGI IMG pipeline documentation, which specifies the GFF output of the pipeline that produced every NMDC file here; the INSDC Feature Table Definition and the DDBJ rendering of it, which are the ancestor of all of this and still govern what a feature means in a sequence database; the Sequence Ontology GFF3 and GVF specifications; GTF 2.2; the GMOD descriptions of GFF2 and GFF3; the BED version 1 specification; the UCSC format reference, which is the broadest single list of real feature-table formats; and NCBI's own statement of what it emits.

## Derived files, in two directories

Nine files are built here from the vendored phiX174 GFF3. Each is that source preserved line for line with **one change to one data row**, plus provenance comments, single-hash lines appended after the source's own `###` terminator, so the header region stays byte-identical. Rebuild them with `just fixtures-generate`.

`no_version_pragma` is the documented exception to both halves of that sentence. Its one change removes a header directive, so its change is not to a data row and its header is deliberately not byte-identical. Every other header line is preserved, and its index entry says so rather than repeating the generic claim.

They are **derived, not found**. They are not evidence about what any real producer emits, and the index labels them that way. They exist because the failures the AgBioData group describes are easier to test against than to read about.

The split into two directories is deliberate, and one pair of files is the reason why.

**`corpus/fixtures/malformed/`**, six files that violate the specification.

| Case | The one change |
|---|---|
| `cds_phase_illegal` | Phase set to 3, outside the permitted 0, 1 and 2 |
| `dangling_parent` | Parent names an ID defined nowhere. Breaks the graph without breaking the syntax |
| `unescaped_semicolon` | A raw `;` inside a `Note` value instead of `%3B`. The tail has no `tag=value` form, so a conforming parser must reject the record |
| `start_after_end` | Columns 4 and 5 swapped. GFF3 requires start no greater than end on every feature, circular ones included, where wraparound is expressed by extending end past the landmark length |
| `no_version_pragma` | The `##gff-version 3` line removed and every other header line kept |
| `duplicate_id` | One ID on a `gene` and a `sequence_alteration`. Repeating an ID is legal when every line describes one discontinuous feature, so duplicating a row would not be a violation; colliding across two types is |

**`corpus/fixtures/edge-cases/`**, three files that are valid GFF3 and still wrong in practice.

`cds_phase_biologically_wrong` changes a CDS phase to another permitted value. This is the failure the AgBioData group leads with, and **no syntax-only validator can catch it**: 0, 1 and 2 are all legal, so identical coordinates with a different phase translate to a different protein while the file stays valid. Read it beside `cds_phase_illegal`, which a validator does catch. The pair is the clearest thing in this corpus: a syntax check is not a correctness check.

`multiple_parents` gives one CDS two parents, both defined in the file. That is permitted, the AgBioData recommendations ask that parsers keep supporting it, and many tools refuse it anyway.

`unescaped_semicolon_silent` is the dangerous half of the escaping problem, and it is worth reading beside `unescaped_semicolon` in the invalid set. There the tail of the unescaped value is a bare segment and a parser must reject it. Here the tail is itself a valid lowercase `tag=value` pair, so the file stays valid, the intended `Note` is silently truncated, and a `note` attribute nobody wrote now exists. Nothing reports anything.

Every derived entry carries a `validity` field for exactly these cases.

[Independent validation](../analyses/format-validation/README.md) runs pinned GenomeTools 1.6.6 and GFF3toolkit 2.1.0. A file in `model/validation/` for each conversion contract and dialect lists the expected rule failures for its retained inputs; new failures and disappearing failures both fail the check. The tools disagree on the dangling-parent control, which only GenomeTools rejects. AGAT 1.7.0 is recorded as blocked after its macOS arm64 dependency solve failed on 2026-09-25. Run `just validity-install` once, then `just validity-check`; CI checks that the report reproduces. Biological correctness and conversion support remain separate.

## Why some things are only linked

The best single source for the eleven named format flavors, GFF through GTF3, is the AGAT test suite, and it is GPL-3.0. Linking keeps a copyleft obligation off this corpus. GenomeTools and GFF3toolkit carry no determinable license in their repository metadata, so those are linked too rather than guessed at. GENCODE is linked because it is tens of megabytes.

Where a license could not be determined, `corpus/index.yaml` says so in that entry rather than leaving it blank.

## Verifying it

`just verify` checks index invariants and checksums, and `just verify-links` also checks upstream URLs over the network. `just pr-validation` writes the PR report.

The PR report exists because a pull request description drifted from its own diff four times: entry counts, tier counts, generated-file counts, and a claim about which change moved the total. Every one was updating the change and not the claim about it, so the claim is generated now.

Two things are checked. **Index invariants**: ids and paths are unique, tiers are known, and every entry carries the fields its tier requires, which for a `derived` entry includes `derived_from` and `mutation`. **Vendored checksums**: every file is present, its size matches, and its MD5 matches.

Either failure exits non-zero. Dead upstream links do not, because a moved URL is something to record rather than a defect here.

The invariant check exists because of a real failure in this repository. An earlier commit claimed id uniqueness was asserted while nothing in the repository checked it, two entries collided on the id `nmdc-annotation`, and every check still passed. A claimed invariant that no check enforces is worse than no invariant, because it gets trusted. So CI does not only run the check, it also injects a duplicate id and fails the build if the check passes anyway.

## Reproducing the NMDC selection

The separate [NMDC DataObject profile](../analyses/nmdc-data-objects/README.md) catalogues categorical slots, allowed and observed values, record frequencies, and URL hosts across the public NMDC DataObject collection. It includes metadata for all file types, not just the GFF files selected below. This is an NMDC-specific source profile, one inspiration for the broader model; its vocabularies and frequencies are not general modeling requirements.

```shell
just nmdc-sample
```

This re-runs the sampling query and writes `local/nmdc-selection/selection.json`. Review request errors and changed selections before replacing the [saved acquisition report](../analyses/nmdc-selection/README.md); a live sample may choose different files. One thing to know if you adapt it: a plain `urllib` request to the NMDC API returns 403, and the same URL through `curl` returns 200. The script sends a `curl` user agent for that reason. Without it the API looks down when it is not.

## Known gaps

These are wanted and still not here.

- **EMSL BASALT.** Reported as EMSL's LinkML model for MONet and parts of the analysis database, with a flattened version coming from James Carr. GitHub across the `ber-data` and `microbiomedata` organizations and the open web were searched on 2026-09-11 and nothing public turned up. Every code hit for "basalt" in those organizations is the rock, in environmental value sets. Recorded as `not located` rather than dropped, because the next step is to ask EMSL rather than to search again.
- **EMSL MONet feature tables.** MONet itself is recorded and its data is published without embargo on EMSL Science Central, but it is soil chemistry and microstructure rather than feature tables. Its sequence-derived products route through JGI portals, which need an account.
- **KBase sample feature tables.** The Common Data Model Feature class is vendored here, and no example data was found in that repository. The model is present, the data is not.
- **Archaic GTF and GFF flavors as vendored files.** GFF1, GFF2, GFF2.5, GTF1, GTF2.1 and GTF2.5 appear to survive only inside test suites, chiefly the GPL-3.0 AGAT one, which is linked. If a real file in one of those flavors turns up with a redistributable license, it belongs here.
- **More real malformed files.** This gap is partly closed. Two real violations were found in the vendored NMDC files and are documented in [docs/columns-and-discretion.md](../docs/columns-and-discretion.md): database accessions in column 3 instead of Sequence Ontology terms, across seven of the fourteen file types, and an empty column 2 where the specification calls for `.`. More would still help, especially from producers other than the JGI IMG pipeline.

Pull requests adding entries should fill in every field the existing entries carry, especially `origin_url`, `retrieved` and `license`. For a `derived` entry, also `derived_from` and `mutation`.
