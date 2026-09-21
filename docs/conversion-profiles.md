# Executable conversion profiles

Two versioned source profiles now convert complete, supported artifacts into the
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

The GFF profile is a declared **contig-coordinate** contract, not a format detector.
Do not apply it to NMDC protein-domain output just because that output has nine
columns. The corpus has examples of both coordinate spaces. The existing curated
protein-relative examples remain separately modeled and validated.

The [GFF3 specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md)
allows richer representations than this first adapter supports. Unknown attributes,
including partial-status qualifiers, survive as ordered generic values; this does
not add typed uncertain endpoints or interpret every producer convention.
Unknown directives retain stream scope. Explicit Prodigal or NCBI metadata profiles
reuse the existing source reader's scoped interpretation. Comments, FASTA and other
nonfeature records are preserved; they are not promoted into biological Dataset
fields or independently reserialized from typed metadata.

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
jsonschema 4.26.0 and PyYAML 6.0.3. Use new output paths:

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
Common interval and attribute queries run on both converted profiles. Query
performance remains unmeasured. [Independent GFF3 validation](../analyses/format-validation/README.md)
records separate GenomeTools verdicts; other formats have no independent validator yet.

## Evidence for the next model changes

The [INSDC feature-table definition](https://www.insdc.org/submitting-standards/feature-table/)
uses location expressions and qualifiers within GenBank/EMBL records. This is
distinct from the [NCBI five-column submission table](https://www.ncbi.nlm.nih.gov/genbank/feature_table/).
The retained six plant records have joined/partial locations and repeated qualifiers.
There is no INSDC adapter yet, so the report marks them unsupported instead of
reducing a joined location to its outer span. The existing GTF reader also supplies
byte preservation, not an executable GTF-to-Dataset conversion profile.

The next justified extensions are explicit compound-location parts and uncertain
endpoints, circular-reference behavior, and assembly-qualified reference identities.
BED's block children provide one reversible source mapping; they do not yet define
a universal location algebra. NMDC/JGI, Prokka and Phytozome remain candidate
producer profiles, not interchangeable dialect names or implemented support claims.

A new supported conversion must add a versioned contract, importer, reverse mapper,
profile validation, real and generated round-trip cases, rejection controls and an
expected report outcome. Change the profile version when its mapping/domain changes.
Constrained publication profiles (for example a scalar-only table) must separately
declare how arrays, references and metadata can be reconstructed. Passing the flat
schema audit does not establish conversion fidelity.
