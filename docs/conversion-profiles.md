# Executable conversion profiles

Four versioned source profiles now convert complete, supported artifacts into the shared `Dataset` model and back. They implement the first cross-format milestone in https://github.com/turbomam/feature-table-corpus/issues/16. The [measured report](../analyses/conversion-roundtrips/README.md) separates exact byte recovery, reconstruction of mapped fields, and unsupported cases. The [converted BED12 example](../model/examples/conversions/README.md) shows a complete generated bundle and how to query its Dataset projection.

## What the converted instance contains

The JSON conversion bundle is one document with these required fields:

| Field | Contract |
|---|---|
| `conversion_version` | Envelope version, currently integer `1`. |
| `profile` | Explicit source contract ID including version; no filename or dialect guessing. |
| `reference_context` | Caller-supplied assembly or source-scoped reference identity. Required; never inferred from `chr1` or an annotation name. |
| `source` | A [SourceDocument](source-documents.md) retaining record order, lexical details, scoped metadata, content hash and provenance URI. |
| `dataset` | An instance of the existing [Dataset/Contig/SequenceFeature model](../model/schema/README.md), validated with its closed shape and cross-record checks. |
| `mappings` | Source-record-to-feature identities, ordered block identities, and attribute grouping/cardinality metadata needed by the reverse mapping. |

The protein profile additionally requires `protein_context` in the bundle. Supply the independent original context again to validation/export with `--protein-context`; it is compared before reimporting the source projection.

`scripts/convert_features.py` checks both component shapes, then validates the complete executable bundle contract by re-importing its internally checked source and comparing the whole projection. Unknown fields and inconsistent copies fail. The two component classes remain LinkML-defined; this version's enclosing JSON/mapping contract is enforced in code. Retain the whole bundle for conversion. Extracting just `dataset` is a useful query projection and does **not** preserve the full round-trip contract.

The reference context and URI are declarations, not authenticated provenance. Validation without an independently supplied original establishes internal consistency. `--original PATH` additionally requires agreement with that retained artifact. A coordinated rewrite of source, hash and mapped values describes a new internally consistent artifact; it cannot pass comparison with the old original.

## Source contracts

| Profile | Forward mapping | Reverse mapping and bounds |
|---|---|---|
| [`insdc-locations/1.0.0`](../model/profiles/insdc-locations.yaml) | GenBank nucleotide records with qualified references, ordered parts, partial endpoints, circular topology and generic qualifiers. | Reconstruct feature-table blocks from modeled locations and qualifiers; preserve header/sequence text in SourceDocument. Remote, between-base, unknown and mixed-strand locations are refused. |
| [`nmdc-pfam-protein/5.0.0`](../model/profiles/nmdc-pfam-protein.yaml) | NMDC HMMER Pfam hits with explicit protein-to-CDS bindings, retained translations and amino-acid coordinates. | Reconstruct protein references and attributes without fabricating source Parent tags or exporting contextual CDS rows. Validation/export require the independent original context. |
| [`gff3-contig/4.0.0`](../model/profiles/gff3-contig.yaml) | Linear contig coordinates, decoded sequence/feature identities, source/type/score/strand/phase; `ID`, `Parent`, `product`, `Name`, `Note`, `Dbxref`, and `Ontology_term` also populate typed slots. Every attribute occurrence remains a generic pair. | Reconstruct nine columns from the Dataset and grouping indices. Repeated IDs/discontinuous features, circular references, protein-relative coordinates, unresolved parents, and ambiguous typed cardinalities are refused. |
| [`bed12-blocks/1.0.0`](../model/profiles/bed12-blocks.yaml) | One parent interval plus ordered block children. Source `[start,end)` becomes model `[start+1,end]`; chromosome names remain literal. Score and strand use core slots; name, RGB and thick drawing bounds use generic `bed:*` attributes. | Reconstruct twelve columns using the parent and children. Require positive, ordered, nonoverlapping blocks covering the enclosing boundaries. Zero-length intervals, fewer/extra columns and whitespace-delimited variants are refused. |

These restrictions belong to these adapters, not to the full input formats. [UCSC's BED description](https://genome.ucsc.edu/FAQ/FAQformat.html#format1) defines the coordinate and block conventions. In particular, a thick drawing span is not necessarily a CDS. BED blocks become generic `sequence_feature` children; the adapter does not invent transcript/exon identities or query-side alignment coordinates. Overlap queries can return both the enclosing record and its blocks; filter `bed:role=block` when asking about covered blocks. A gap overlaps the parent span without becoming an annotated block.

The [NMDC Pfam profile](protein-coordinates.md#the-nmdc-pfam-profile), `nmdc-pfam-protein/5.0.0`, adds explicit protein-to-CDS context and amino-acid bounds, while keeping the two original contracts unchanged. Supporting CDSs are not exported as additional Pfam rows. Source rows require HMMER/Pfam, ID, strand/phase `.`, and no Parent.

The original GFF profile is a declared **contig-coordinate** contract, not a format detector. Do not apply it to NMDC protein-domain output just because that output has nine columns. The corpus has examples of both coordinate spaces. Use the Pfam profile and its explicit companion context for the supported protein-relative convention; the existing curated protein-relative examples remain separately validated.

The [GFF3 specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md) allows richer representations than this first adapter supports. Unknown attributes, including partial-status qualifiers, survive as ordered generic values; this does not add typed uncertain endpoints or interpret every producer convention. Unknown directives retain stream scope. Explicit Prodigal or NCBI metadata profiles reuse the existing source reader's scoped interpretation. Comments, FASTA and other nonfeature records are preserved; they are not promoted into biological Dataset fields or independently reserialized from typed metadata.

## Dialect schemas

A profile above converts a source into the model. A dialect schema is an earlier, separate check: it describes a source's own rows in LinkML, so a file can be validated against its dialect before anything is mapped. When a file fails, that says it differs from what its producer is known to write, not that a mapping is wrong (https://github.com/turbomam/feature-table-corpus/issues/54).

The dialects are described on their own pages:

- [IMG dialects](img-dialects.md): the IMG functional annotation GFF and its linkml-map mapping, the per-method hit files, the TMHMM and SignalP files, the taxon bundle, and the IMG 4.14 assembled GFF.
- [Phytozome dialects](phytozome-dialects.md): Phytozome gene_exons GFF3 and annotation_info.

## Attributes and authority

The shared Attribute class still means a string key/value pair, independent of GFF column 9. BED display/name values and parsed comment metadata use it too.

Every profile and dialect here that reads GFF column 9 or GenBank qualifiers follows one rule for multivalued values, stated in [reusable attributes](attributes.md#multivalued-values): each value is its own Attribute entry in source order, split before percent-decoding, and the source profile decides which keys are multivalued.

| Source | Keys split on commas | Decoding | Example |
|---|---|---|---|
| `gff3-contig/4.0.0` | every key | after splitting | `Note=x%2Cy` is one entry `x,y`; `Parent=a,b` is two |
| `nmdc-pfam-protein/5.0.0` | every key, through the same GFF3 reader | after splitting | as for `gff3-contig` |
| IMG functional dialect and its mapping | only keys the dialect types multivalued (`pfam`, `cog`, `ko`, `ec_number`, `tigrfam`, `smart`, `superfamily`, `cath_funfam`, `transmembrane_helix_parts`); `shortened` repeats as a key instead | none; IMG writes no escapes | `product=glutamate-1-semialdehyde 2,1-aminomutase` is one entry |
| IMG per-method dialect | only `subject_gene_ids` | none | not yet mapped to `SequenceFeature` |
| IMG TMHMM and SignalP GFF and their mapping | none; it declares no list keys | none | `D-score=0.670` is one entry, kept as written |
| IMG taxon bundle and its mapping | only the InterPro table's `go_info`, split on `\|`; GFF `ID`, `locus_tag` and `product` are single values | none | `GO:0006807\|GO:0016810` in the fixture is two entries |
| Phytozome gene_exons GFF3 and its mapping | none; refuses any comma or `%` in column 9 | none | each key is one entry, for example `pacid=90000001` in the fixture |
| `insdc-locations/1.0.0` | none; a GenBank qualifier repeats instead | not applicable | two `/db_xref` lines are two entries |

`bed12-blocks/1.0.0` writes only fixed `bed:*` attributes and Prodigal comment metadata is one value per key, so neither splits anything. Tables that are not GFF, such as the Phytozome annotation_info file (lists separated by spaces) and the IMG taxon bundle TSVs, follow their own dialect schemas and are outside this table.

A literal comma in a `gff3-contig` value is a separator, so `product=a,b` is two products and is refused (`product-cardinality`). polars-bio `read_gff` splits nothing and decodes first, so its output does not follow the rule. `tests/test_attribute_splitting.py` checks the first, second, third and fifth rows against the fixtures in `tests/fixtures/attribute-splitting/`; `tests/test_locations.py` checks repeated INSDC `db_xref` qualifiers. The taxon bundle row is read from its parser, not tested here.

GFF occurrences and comma-separated values become ordered pairs; mappings retain the grouping indices, so `Note=a,b;Note=c` remains distinguishable from three assignments. Empty values remain strings, distinct from absent assignments. Original lexical cells retain escaping, delimiters and numeric spelling.

Typed GFF `feature_id`, `parent`, `product`, `name`, `note`, `dbxref` and `ontology_term` must agree with their retained generic `ID`, `Parent`, `product`, `Name`, `Note`, `Dbxref` and `Ontology_term` values. The last four are GFF3 reserved tags given typed slots in 3.0.0 ([issue 43](https://github.com/turbomam/feature-table-corpus/issues/43)); `Name` takes at most one value, and the other three keep every value in order. `Alias` and `Derives_from` appear in no corpus file and stay generic. Reconstructed output uses the typed slots for those assignments and rejects conflicting generic copies. Missing source IDs receive document-local synthetic IDs but remain missing in exported GFF. The model's attribute list now explicitly records that order is retained.

### Derived slots

Two model slots are filled from retained source values rather than read from a column (https://github.com/turbomam/feature-table-corpus/issues/72):

- `Contig.translation_table`, in `gff3-contig` and the IMG functional mapping, when every CDS on the contig carries a `translation_table` attribute and all of them name the same assigned NCBI genetic code (`011` counts as 11). CDS values that disagree, within one row or across rows, are refused with `translation-table-conflict`. A contig is left unset when any CDS on it lacks the attribute, or when all its CDS name the same unassigned or non-integer value. The Dataset validator rejects the same disagreements, whether or not the contig has a table.
- `SequenceFeature.score_type` is `bit_score` on `nmdc-pfam-protein` rows that have a score, because nmdc-lakehouse documents NMDC's HMMER column 6 as a bit score (https://github.com/microbiomedata/nmdc-lakehouse/blob/main/docs/pfam_annotation_gff.md). No other profile sets it: nothing retained says what Prodigal, GeneMark, lastal, INFERNAL or BED scores are.

Adding these slots changed both profiles, so both moved to 2.0.0: each adds output, and each now refuses input 1.0.0 accepted (conflicting CDS tables, in the imported file for `gff3-contig` and in the protein context for `nmdc-pfam-protein`). A bundle made under 1.0.0 is refused as an unsupported profile rather than validated against the new rules.

`nmdc-pfam-protein` moved again, to 3.0.0, when a protein hit's `seqid` changed from the contig to its CDS ([protein coordinates](protein-coordinates.md)). A 2.0.0 bundle is refused the same way.

Typed slots for the GFF3 reserved tags `Name`, `Note`, `Dbxref` and `Ontology_term` ([issue 43](https://github.com/turbomam/feature-table-corpus/issues/43)) add output to both GFF3 profiles, so `gff3-contig` moved to 3.0.0 and `nmdc-pfam-protein`, whose hits carry `Name`, to 4.0.0. Bundles made under the earlier versions are refused as unsupported profiles.

`gff3-contig` moved to 4.0.0 when it began filling `Contig.length_bp` from `##sequence-region` ([issue 46](https://github.com/turbomam/feature-table-corpus/issues/46)), under the `ncbi` metadata profile only. NCBI writes one region per record, from 1 to the record's length: the RefSeq phiX174 GFF3 declares `NC_001422.1 1 5386`, and the vendored GenBank record for the same accession says 5386 bp. A contig with no region, more than one, or one that doesn't start at 1 keeps `length_bp` unset, as does every file read under another metadata profile, because GFF3 lets a region cover part of a sequence.

`nmdc-pfam-protein` moved to 5.0.0 when its hits gained a typed alignment target ([issue 94](https://github.com/turbomam/feature-table-corpus/issues/94)): `target_id` is the Pfam accession and `target_start` and `target_end` come from HMMER's `model_start` and `model_end`, positions on the Pfam model. The attributes stay, and export refuses a target that disagrees with them.

The Dataset validator rejects conflicting CDS tables, as the converters do, but it accepts a contig table that no CDS attribute backs, for example one a source states in a pragma or a Prodigal sequence comment. The IMG functional mapping cannot write such a table back, so its reverse step refuses it as a loss; that refusal is about what the dialect can hold, not a validity rule.

Neither slot is read by export, so exact and reconstructed bytes do not change. Re-import derives them again, so removing or editing one is an edit like any other and is refused. `nmdc-pfam-protein` does not derive `translation_table` for its context contigs: the context Dataset is used as supplied. `insdc-locations` does not derive it either; GenBank CDS carry `/transl_table`, with table 1 implied when absent, which needs its own rule.

These versions support **unmodified imported instances**. Changes to modeled fields, attributes, block relationships, preservation records or mappings are rejected in both export modes. There is no precedence rule that silently overwrites an edit, and no implemented lossy or edited-instance export mode. Conversion/data errors return status 2 with a JSON diagnostic; command-usage errors use standard argparse help. Existing source/output files are never overwritten.

## Reproduce the two guarantees

Use Python 3.11+, uv and just 1.27+. The conversion commands and regression suite use [pinned dependencies](../requirements-conversion.txt): LinkML 1.11.1, jsonschema 4.26.0, PyYAML 6.0.3, rfc3987 1.3.8 and Biopython 1.85. Use new output paths:

```sh
just conversion-import \
  corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff \
  gff3-contig/4.0.0 nmdc:wfmgan-11-9ya9xh30.1 \
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

`exact` first verifies the imported projection and reconstructs feature semantics, then restores lexical cells and original line endings. `reconstruct` generates feature columns using a function that receives **no source feature text or columns**; only the Dataset and nonlexical identity/grouping map. Re-importing that output must recover the same Dataset, relationships, grouping and nonfeature metadata records. Percent-escape spelling, numeric spelling, trailing delimiters and empty column 9 may normalize in this mode. It promises preserved interpreted fields, not biological equivalence beyond the declared mappings.

`just conversion-report` deliberately regenerates the tracked JSON report; `just conversion-check`, included in `just check` and CI, compares it without writing. Unexpected rejection **or** unexpected acceptance fails. Unit tests also cover 120 deterministically generated positive cases, wrong/conflicting representations, malformed values, boundaries, metadata scopes, literal arguments and refused edits. Common interval and attribute queries cover the converted profiles, with explicit [part-aware and partial-bound semantics](feature-locations.md) for INSDC. Query performance remains unmeasured. [Independent GFF3 validation](../analyses/format-validation/README.md) records separate GenomeTools verdicts; other formats have no independent validator yet.

## Additional format coverage and remaining limits

The [INSDC feature-table definition](https://www.insdc.org/submitting-standards/feature-table/) uses location expressions and qualifiers within GenBank/EMBL records. This is distinct from the [NCBI five-column submission table](https://www.ncbi.nlm.nih.gov/genbank/feature_table/). The retained six plant records have joined/partial locations and repeated qualifiers. The [bounded INSDC adapter](feature-locations.md) now covers these retained examples. Earlier reports marked them unsupported instead of reducing a joined location to its outer span. The existing GTF reader also supplies byte preservation, not an executable GTF-to-Dataset conversion profile.

Explicit ordered parts, partial endpoints and circular references now have a bounded GenBank profile. Remote locations, between-base sites and ambiguous bounds remain unsupported. BED's block children retain their original profile meaning; they are not silently reinterpreted as the new location class. Additional NMDC/JGI and Prokka conventions remain candidates, not interchangeable dialect names, and the [Phytozome dialects](phytozome-dialects.md) are validated but not yet converted.

A new supported conversion must add a versioned contract, importer, reverse mapper, profile validation, real and generated round-trip cases, rejection controls and an expected report outcome. Change the profile version when its mapping/domain changes. Constrained publication profiles (for example a scalar-only table) must separately declare how arrays, references and metadata can be reconstructed. Passing the flat schema audit does not establish conversion fidelity.
