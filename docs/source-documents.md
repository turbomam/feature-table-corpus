# Source documents, comments, and directives

[`model/schema/source_document.yaml`](../model/schema/source_document.yaml) represents one
GFF3, GTF or BED12 source file as a `SourceDocument` instance with ordered `SourceRecord`
instances. [`scripts/source_document.py`](../scripts/source_document.py) preserves
every UTF-8 source byte and adds an explicitly scoped interpretation where the
format or selected producer profile supports one. This implements the preservation
and metadata layer requested in [issue #13](https://github.com/turbomam/feature-table-corpus/issues/13).

## What each object means

| Object | Role and boundary |
|---|---|
| `SourceArtifact` | URI, SHA-256, and byte size of the physical, uncompressed input. A URI is provenance supplied by the caller; it is not fetched or authenticated. |
| `SourceDocument` | Parsed view of exactly one artifact, with the selected format and metadata profile. It is not an annotation release assembled from several files. |
| `SourceRecord` | One physical line, including its original ending, line number, lexical kind, scope, and optional interpreted fields. A feature row is not necessarily a whole biological feature: discontinuous GFF3 features can occupy several rows. |
| `Attribute` | The shared, format-independent string `key`/`value` module, reused for recognized comment and directive metadata. Repeated keys remain ordered entries. |
| Harmonized `Dataset`, `Contig`, `Feature` | Separate biological model in `ber_feature_model.yaml`. This reader does not convert source rows into those entities. |
| NMDC `DataObject` | External source catalogue used by one contributing project. This schema does not import it or require NMDC identifiers, slots, or categories. |

Feature fields remain lexical strings in `feature_columns`: nine for GFF3/GTF,
twelve for BED12. GFF/GTF column 9 is preserved without attribute parsing. Likewise, metadata extracted
from a Prodigal comment does not acquire GFF column-9 escaping rules. Control markers
(`###`, `##FASTA`) have their own record kinds rather than becoming generic attributes.

## Why a small preservation reader

Existing feature parsers were inspected before adding this layer, on 2026-09-21:

| Implementation inspected | Behavior relevant to this task | Decision |
|---|---|---|
| [gffutils `_FileIterator`](https://github.com/daler/gffutils/blob/6b84330f472dd2b4c69e36f319da7ade95bd5961/gffutils/iterators.py) at `6b84330` | Retains a separate list of double-hash directives, strips line endings, skips ordinary comments/blanks, and stops at FASTA. | Useful for feature/database interpretation; does not supply the original ordered document needed here. |
| [BCBio.GFF parser](https://github.com/chapmanb/bcbb/blob/320353c64ee0dc938113ca36f19b2e6de6b597be/gff/BCBio/GFF/GFFParser.py) at `320353c` | Processes directives and FASTA into Biopython structures, while ignoring ordinary single-hash comments and stripping line text. | Useful biological parsing, but not a byte-replayable source representation. |

This is source-code inspection, not a runtime benchmark or a claim about every
release. The new standard-library reader preserves the document around feature rows;
it does not replace those projects' biological parsers. Future harmonization can
consume these records or use an existing feature parser alongside them. The wider
[reading list](feature-format-reading.md) separates comparative evidence from
specifications and tool authors' evaluations.

## Scope and producer profiles

The caller must choose `--format gff3`, `--format gtf` or `--format bed12`. A filename or absent header
never supplies an inferred format. `--profile generic` is the default; producer
interpretation requires explicitly selecting `prodigal` or `ncbi`.
BED12 accepts only `generic`; comments and `track`/`browser` commands retain stream
scope without inferred biological metadata. The BED reader requires tab separation.

| Source construct | Interpretation |
|---|---|
| GFF3 `##gff-version`, ontology directives, `##species`, `##genome-build` | Document metadata when a nonempty payload is present. This layer does not fully validate the payload grammar. |
| GFF3 `##sequence-region seqid start end` | Sequence-scoped interval declaration; endpoints remain strings. Its end is **not** inferred to be the full sequence length. |
| Prodigal `# Sequence Data:` | Ordered key/value pairs, including quoted `seqhdr`, `seqlen`, and `seqnum`. A valid declaration starts a sequence context identified by this record's ID. |
| Prodigal `# Model Data:` | Metadata for the preceding valid sequence context, including `transl_table`. Model/training-organism text is not a taxonomic assignment for the sequence. |
| NCBI recognized `#!` comments and GTF `#gtf-version` | Document metadata under the `ncbi` profile. The recognized names are enumerated in the reader. Other comments remain raw. |
| Unknown comments/directives | Preserved with `stream` scope: only their position is established. Neither document-wide nor sequence-specific semantics are guessed. |
| GFF3 `###` | Feature-group boundary; ends the current Prodigal sequence context. |
| GFF3 `##FASTA`, or first `>` header | One-way FASTA transition. Subsequent headers and sequence lines retain their own sequence context. Annotation parsing does not resume. |

`context_record` identifies the actual declaring record, not just a sequence name.
Repeated Prodigal blocks or FASTA headers for the same name therefore remain distinct.
A malformed new Prodigal sequence declaration clears the previous context. A feature
with a mismatching sequence ID warns and clears it too. A Model Data comment without
a valid context is retained with a warning and stream scope.

The checked-in [Prodigal example](../model/examples/source-documents/README.md) demonstrates
five sequence blocks with comments interleaved among six feature rows. Its first
translation table is 4 and the other four are 11. The fourteen NMDC GFF files also
include headerless examples; those do not gain fabricated metadata.

The [GFF3 specification](https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md)
defines directives and stream markers; the
[NCBI GFF3 documentation](https://www.ncbi.nlm.nih.gov/datasets/docs/v2/reference-docs/file-formats/annotation-files/about-ncbi-gff3/)
documents producer conventions. Actual retained text is always available for checking
or reinterpreting those conventions.

## Reproduction and validation

Run from the repository root, choosing new output filenames:

```shell
just source-parse \
  corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff gff3 \
  local/source-documents/prodigal.json --profile prodigal
just source-validate local/source-documents/prodigal.json \
  --original corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff
just source-replay local/source-documents/prodigal.json \
  local/source-documents/prodigal-replayed.gff \
  --original corpus/sources/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff
just validate-source-example
just test
```

Without `--source-uri`, parsing records an absolute local file URI. Supply a public
provenance URI for portable examples. The checked-in example uses its corpus origin
URL, as documented beside it. The parse and replay recipes require a new output path
and refuse to overwrite existing files, including the input. Direct invocation of
`scripts/source_document.py parse` can also emit JSON on stdout when `--output` is omitted.
The recipes forward trailing options unchanged, including the explicit producer profile.

Ordinary parsing retains unknown syntax and reports interpretation warnings to stderr.
`--strict` still emits the document but returns status 1 when warnings occurred.
Unknown comments/directives are expected preserved content and do not warn merely
because their semantics are unknown. File, decoding, and integrity errors return 2.

LinkML/closed JSON Schema checks the document's shape. The `validate` and `replay`
commands reconstruct the bytes, verify size/digest, reparse with the recorded profile,
and compare the whole projection, including record order, scope, metadata, and context
references. This detects editing a parsed field without updating the stored source text.
Without `--original`, this checks internal consistency only: changing raw text, digest,
size, and parsed fields together can produce another internally consistent document.

Pass `--original PATH` to either command to additionally require byte-for-byte agreement
with an independently retained source file. A mismatch exits 2 before replay writes an
output. This comparison depends on the caller selecting a trusted original; neither
mode proves that the claimed provenance URI hosted those bytes or fetches that URI.
`just validate-source-example` runs shape, consistency, and original-file checks for the
checked-in Prodigal example; for another instance, pass its JSON and matching source as
the recipe's two arguments. `just check` and CI include this comparison.

All eighteen vendored GFF/GTF files are tested for exact byte replay, retained feature
rows, and warning-free parsing under their selected profiles. A separately labeled
[derived parser fixture](../tests/fixtures/source-documents/README.md) exercises
repeated and unknown directives, a mid-file comment, a subinterval sequence-region,
`###`, and embedded FASTA. Additional controls cover malformed metadata, duplicate
sequence names, mixed line endings, corrupted projections, and consistent rewrites that
fail an independent original-file comparison. Raw corpus files are
unchanged. Scratch files remain under gitignored `local/`.

## Relation to Chris's model and the word “metaobject”

The [upstream draft GFF schema](https://github.com/biodatamodels/gff-schema/blob/cb31263471ab3855c3622c3be3d3f908db8be654/src/schema/gff.yaml)
already separates a GFF document, metadata (with pragma/directive aliases), and a
genome-feature attribute set. Our `SourceDocument` has a similar document role, but
retains physical records and explicit scope rather than treating every comment as
document metadata. `Attribute` is reusable beyond a GFF feature's ninth column.

In the kickoff notes, Chris's “metaobject” question occurs in a discussion about
whether attributes are composed as a part or folded into the feature. That context
supports an attribute-container interpretation; it does not establish that he meant
the whole file. A file-level instance is useful independently of resolving that term.

## Deliberate limits

Input is uncompressed UTF-8 and held in memory. CR, LF, CRLF, a UTF-8 BOM, blank lines,
and a missing final newline are preserved. Compression, streaming very large files,
and other encodings are not implemented. The reader does not fully validate GFF/GTF
grammar, feature coordinates, phase, relationships, sequence alphabets or declared
lengths; it does not normalize, repair, or export harmonized biological features.
Byte replay is a separate claim from semantic round-trip conversion. The separate
[conversion profiles](conversion-profiles.md) now map constrained GFF3 and BED12
inputs into Dataset instances and reconstruct feature fields. INSDC and GTF semantic
conversion remain unsupported; that limitation does not prevent corpus observation
or the existing GTF source-byte preservation.
