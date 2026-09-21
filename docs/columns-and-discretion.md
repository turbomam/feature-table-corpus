# Columns, discretion, and what writers get wrong

Three questions this answers: how many fields each format has and which are not a single table;
which columns leave the writer discretion and which do not; and which columns get populated
incorrectly in practice.

Claims are marked *quoted* from a specification, *measured* against the files in this corpus with
the date, or *unverified*. Nothing here is inferred.

## 1. Field counts, and which formats are not one table

| Format | Fixed columns | Column 9 | Total | One table? |
|---|---|---|---|---|
| GFF2 | 8 | `group`: a class and an ID | 9 | Yes |
| GFF3 | 8 | `attributes`: `tag=value;` pairs | 9 | **No** |
| GTF 2.2 | 8 | `attributes` | 9 | Yes |
| BED | 3 required | 9 further optional fields | 3 to 12 | Yes |
| Chado | relational | seven feature tables | many | **No** |
| KBase Common Data Model | LinkML classes | Feature plus related classes | many | **No** |

*Quoted, GFF3:* all nine columns must be present on every feature line, and an undefined field uses
`.` as a placeholder.

**GFF3 is not one table.** The `##FASTA` directive marks the end of the annotation section, and
"the remainder of the file contains one or more sequences (nucleotide or protein) in FASTA format."
So a single GFF3 file can carry features and sequence together. Any model that treats a GFF3 file
as one table silently drops that section.

**GFF2 is deprecated** and its ninth column is a `group` holding the class and ID of the logical
parent, which is how hierarchy was expressed before GFF3 had `Parent`.

**GTF 2.2** has nine tab-separated fields: seqname, source, feature, start, end, score, strand,
frame, attributes. The specification also allows a trailing `#` comment on a line, but a comment is
not a tenth field and a parser should not expect one. Two attributes are mandatory: `gene_id` and
`transcript_id`.

*Unverified:* the column counts for GFF1, GFF2.5, GTF1, GTF2.1, GTF2.5 and GTF3. The AGAT
documentation distinguishes those flavors by which feature types they admit, from five in GTF1 to
nine in GTF3, not by column count. It also documents an explicit `relax` mode that accepts any
feature type at all, which is what most real files amount to.

Lineage, for reading old files: GFF1 and GFF2 come from the Sanger Institute, GTF originated at
Ensembl and was adapted into GTF2 for the Mouse and Human Annotation Collaboration, and GFF3 is
specified by the Sequence Ontology group. Fuller version in [prior-art.md](prior-art.md).

## 2. Discretion, column by column

GFF3, with the specification's own words.

| Col | Field | Discretion | Basis |
|---|---|---|---|
| 1 | seqid | Low | Must establish the coordinate system; no controlled vocabulary |
| 2 | source | **Highest** | *Quoted:* "a free text qualifier intended to describe the algorithm or operating procedure that generated this feature" |
| 3 | type | **Lowest** | *Quoted:* "constrained to be either a term from the Sequence Ontology or an SO accession number ... must be sequence_feature (SO:0000110) or an is_a child of it" |
| 4, 5 | start, end | Lowest | 1-based, and start no greater than end on every feature |
| 6 | score | **Highest** | *Quoted:* "the semantics of the score are ill-defined." E-values and P-values are only recommended |
| 7 | strand | Lowest | A small fixed set of values |
| 8 | phase | Values fixed, meaning contested | Section 3 below |
| 9 | attributes | Mixed | Reserved capitalised tags are defined; everything else is free |

**Measured 2026-09-11** across the 18 GFF3 and GTF files in this corpus, 817 feature rows:

| Column | What the data shows |
|---|---|
| 2 source | 9 distinct values, most carrying a version string: `HMMER 3.1b2 (February 2015)`, `Prodigal v2.6.3_patched`, `tRNAscan-SE v.2.0.12 (Nov 2022)`, `GeneMark.hmm-2 v1.25_lic`, `lastal 1456`, `CRT 1.8.4`, `INFERNAL 1.1.3 (Nov 2019)`, `RefSeq`, and one empty |
| 3 type | 46 distinct values, the commonest being gene, CDS, start_codon, stop_codon |
| 6 score | 757 of 817 rows are `.`, so the column is unused 93% of the time |
| 7 strand | 31 rows are `.` |
| 8 phase | 366 zeros and 2 ones among CDS and codon rows |
| 9 attributes | 63 distinct keys across the two formats |

**Narrowed to just the 14 real NMDC files, 2026-09-18** (a sibling session's measurement,
independently reconfirmed here): 35 distinct keys, only 3 of GFF3's 11 reserved tags in use (ID,
Name, Parent). Both `e-value` and `evalue` occur, in one pipeline's own output. Source-code
confirmation of why: the actual script that writes these files,
`assign_product_names_and_create_fa_gff.py`, builds column 9 by string concatenation, appending
`;product=`, `;product_source=`, `;ko=`, `;ec_number=`, and a dynamic `;<fa_type>=` (`pfam`, `cog`,
`tigrfam`, `smart`, `supfam`, or `cath_funfam`), with no vocabulary check anywhere in that code
path. A public copy is at
[kellyrowland/img-omics-wdl](https://github.com/kellyrowland/img-omics-wdl), but that is a 2021
snapshot; `microbiomedata/mg_annotation`'s own Dockerfile pins `IMG_annotation_pipeline_ver=5.3.0`,
several versions ahead of it, and the canonical, current source is
[code.jgi.doe.gov/img/img-pipelines/img-annotation-pipeline](https://code.jgi.doe.gov/img/img-pipelines/img-annotation-pipeline)
(JGI GitLab, LBNL, GPL-3.0), not read directly for this finding.

**How NMDC's column 9 compares to two other annotation tools' column 9, 2026-09-18.** NMDC's 35
keys are what one production pipeline's run actually emitted; the two counts below are what each
tool's source *can* emit, a ceiling rather than a floor, and are not the same kind of measurement.

Prokka v1.15.6, 15 keys, reproduced directly from its own source:

```bash
curl -sL https://raw.githubusercontent.com/tseemann/prokka/v1.15.6/bin/prokka -o /tmp/_prokka.pl
{ grep -oE "add_tag_value\('[A-Za-z_]+'" /tmp/_prokka.pl | sed "s/.*('//;s/'//"
  awk '/-tag *=> *\{/,/\}/' /tmp/_prokka.pl | grep -oE "^[[:space:]]*'?[A-Za-z_]+'?[[:space:]]*=>" | tr -d " \t'=>"
} | sort -u
```
Result: `ID Name Note note Parent product inference gene locus_tag EC_number db_xref protein_id accession rpt_family rpt_type`.

**Bakta v1.12.1, 25 keys, resolved and confirmed 2026-09-18.** Two regex-based attempts at this
(one from a sibling session, one from this one) disagreed with each other; regex patterns missed
key assignments in different styles (dict-literal, subscript, tuple-unpacking) and, on the
constants side, over-matched on prefix collisions like `INSDC_FEATURE_PSEUDOGENE` against its own
`_TYPE_UNITARY` sibling. An AST-based extractor,
[`scripts/extract_bakta_keys.py`](../scripts/extract_bakta_keys.py), resolves this structurally:
every `bc.CONSTANT` key expression is an exact dict lookup against `bakta/constants.py`'s 124
string constants, not a pattern match, so a prefix collision can't happen. Run independently in
this repository and confirmed against the sibling session's own run: same 124 constants parsed,
same 25 keys, zero unresolved. Two keys that look like mistakes were read by hand and are real:
`sequence` (a PILER-CR CRISPR spacer feature's nucleotide sequence, written into column 9) and
`score` (a legacy `# <1.10.0 compatibility` code path that writes the same value into both column
6 and column 9 in one row).

**The three-way comparison, computed from all three verified lists.** NMDC 35 keys, Prokka 15,
Bakta 25; union 60; shared by all three, exactly: `ID`, `Name`, `Parent`, `product`. Folding case
(`EC_number`/`ec_number`, `Note`/`note`) shrinks the union to 58 but doesn't change which four
keys are common to all three.

Two of those rows deserve attention. Column 2 is the most variable column in the corpus and its
values are unparseable by design, so a model cannot use it to identify the producing tool without a
lookup table it has to maintain itself. And the phase distribution is so skewed toward zero that a
handler which mishandles 1 and 2 would pass on almost all of this data, which is the worst shape of
bug: rare enough to survive testing, consequential enough to change a protein.

## 2b. Three columns are intentionally open, and they are open in different ways

Naming them properly matters, because "ambiguous" hides the distinction. *Quoted* column names, in
order: seqid, source, type, start, end, score, strand, phase, **attributes**.

Three of the nine are open by design, and no two are open in the same sense.

| Column | What is open | What is closed |
|---|---|---|
| 9 attributes | The vocabulary | The syntax, completely |
| 2 source | Everything | Nothing |
| 6 score | The meaning | The syntax |

**Column 9, attributes: open vocabulary, closed syntax.** The grammar is fully specified as
semicolon-separated `tag=value` pairs with percent-encoding for the separators. Eleven tags are
reserved: ID, Name, Alias, Parent, Target, Gap, Derives_from, Note, Dbxref, Ontology_term and
Is_circular. The namespace is then partitioned by capitalisation. *Quoted:* "All attributes that
begin with an uppercase letter are reserved for later use. Attributes that begin with a lowercase
letter can be used freely by applications." And *quoted:* "attribute names are case sensitive.
'Parent' is not the same as 'parent'."

So whether a tag is legitimate is mechanically decidable. A parser can reject an unknown
uppercase-initial tag and accept any lowercase one. That is a bounded extension point, not an
ambiguity.

**Column 2, source: open in every respect.** *Quoted:* "a free text qualifier intended to describe
the algorithm or operating procedure that generated this feature." No grammar, no vocabulary, no
rule. Measured here, 18 files produced 9 distinct values, most carrying a version string, and one
empty. Nothing can be decided about this column mechanically, which makes it the widest of the
three in practice.

**Column 6, score: open where it counts.** The syntax is closed, a floating point number, so it
always parses. The meaning is not. *Quoted:* "the semantics of the score are ill-defined", with
E-values and P-values only recommended for two kinds of feature. This is the strongest admission of
intentional ambiguity in the document, and it is why none of the four models on file keeps the
column as the specification defines it. See [model-comparison.md](model-comparison.md).

**The one to actually worry about is none of these.** Column 8 phase has a closed value set and a
contested meaning across the two specifications that use it, which is worse than an open column,
because an open column announces itself. See the next section.

For contrast, the closed end: column 3 type must be a Sequence Ontology term that is an is_a child
of sequence_feature, and columns 4, 5 and 7 admit a small fixed set of values. Column 1 seqid has no
controlled vocabulary, but it is locally defined by the file's own `##sequence-region` directives
rather than left open.

## 3. Phase, which is the question worth asking

The same column is defined differently by the two specifications that use it.

*Quoted, GFF3 column 8:* the phase "indicates where the next codon begins relative to the 5' end
... of the current CDS feature", and it "is one of the integers 0, 1, or 2, indicating the number of
bases forward from the start of the current CDS feature the next codon begins." It is **required on
every CDS feature**.

*Quoted, GTF 2.2 column 8*, which calls the same column `frame`: "0 indicates that the feature
begins with a whole codon at the 5' most base", and start and stop codon features "must have a
0,1,2 in the frame field indicating which part of the codon is represented by this feature." GTF
also gives an arithmetic rule for the next feature: `(3 - ((length - frame) mod 3)) mod 3`.

So one specification frames it as how many bases to skip inside this feature, and the other as which
part of a codon this feature begins with. They agree at 0 and are easy to transpose at 1 and 2.

**Measured 2026-09-11, and this settles it.** NCBI publishes the same annotation in both formats,
and both files are vendored here, so the question can be answered with data rather than argued from
wording. Joining CDS records on `protein_id` across phiX174 and phage lambda gives 84 proteins
present in both formats:

| Result | Count |
|---|---|
| Identical phase list in GFF3 and GTF | 81 |
| Different | 3 |

So phase and frame encode the same quantity and the values map directly. They are not complements.
An earlier version of this document called the mapping unverified; that was resolved by measurement,
not by reading.

**The three exceptions are not about phase at all**, and they are the more interesting result. All
three are phiX174 genes that cross the origin of a circular genome, and the two formats represent
that differently:

| Protein | GFF3 span | GTF span | GFF3 phase | GTF phase |
|---|---|---|---|---|
| NP_040703.1 | 3981 to 5522 | 1 to 5386 | `0` | `1`, `0` |
| NP_040704.1 | 4497 to 5522 | 1 to 5386 | `0` | `1`, `0` |
| NP_040705.1 | 5075 to 5437 | 1 to 5386 | `0` | `0`, `0` |

The landmark is 5386 bases. GFF3 uses the extend-end convention, putting end past the landmark
length, and keeps one feature with one phase. GTF splits the gene into two segments, and the second
segment then needs a nonzero phase. Same biology, same phase semantics, different segmentation. That
is also why phiX174 has 11 CDS rows in GFF3 and 13 in GTF.

**One more boundary difference, same measurement.** For NP_040706.1 the GFF3 span is 51 to 221 and
the GTF span is 51 to 218. GTF excludes the stop codon from the CDS where GFF3 includes it. Any
converter that preserves coordinates without adjusting for this shifts every terminal CDS by three
bases.

*Quoted, AgBioData GFF3 recommendations:* the CDS phase field "is commonly misinterpreted by both
dataset generators and consumers, which can lead to vastly different ... amino acid sequences."
Their recommendation is to validate phase against translation tables rather than trust it.

Two fixtures in this corpus isolate the problem:

- `corpus/fixtures/malformed/cds_phase_illegal.gff3` sets phase to 3, outside the permitted set. A
  validator catches it.
- `corpus/fixtures/edge-cases/cds_phase_biologically_wrong.gff3` changes phase to another permitted
  value. **No syntax-only validator can catch it**, because the value is legal. Biological
  validation can: translating the CDS against the reference protein detects the change, which is
  what the AgBioData recommendation to validate phase against translation tables amounts to.

That pair is the most useful thing in the derived set, because it shows the phase problem is not a
syntax problem.

## 4. What writers get wrong, measured in this corpus

**Column 3 carries database accessions instead of Sequence Ontology terms.** Measured 2026-09-11.
Every per-database NMDC annotation file in this corpus puts the matched accession in column 3:
`PF00011` and seventeen other Pfam accessions, `COG3666`, `TIGR02937`, `SM01408`, and the CATH and
SUPERFAMILY equivalents. The specification requires column 3 to be an SO term or accession that is
an is_a child of sequence_feature. Seven of the fourteen NMDC file types do this, and it is
systematic rather than occasional.

This matters more than a validator warning. A unified model cannot assume column 3 is an SO term,
because the BER data it would have to load does not put one there.

**Column 2 is sometimes empty rather than a dot.** Measured 2026-09-11. Three files carry a row
whose source field is the empty string, where the specification calls for `.` when a field is
undefined: the SMART, TIGRFAM and COG files.

Both findings come from real production files, vendored here with their origin URLs and checksums.
They are the real malformed content the README previously listed as a gap.

**Other failures, from the specifications and from adjacent work:**

- **Score is routed around rather than used.** Correction, 2026-09-11: an earlier version of this
  document said both the NMDC schema and the KBase Common Data Model replaced the column with
  e_value and p_value slots. Only KBase does that, and its own documentation calls them ill-defined
  score fields. NMDC's `GenomeFeature` omits score entirely, and the `biodatamodels` `gff-schema`
  defines the slot and does not attach it to the feature class, though nothing records whether that
  was deliberate. So the four models
  handle the column four different ways and none keeps it as specified. Not independent replication,
  since three of them share text, but distinct handling in every case. See [model-comparison.md](model-comparison.md).
- **ID conflated with a persistent identifier.** The AgBioData recommendations ask that the `ID`
  attribute, which exists to express hierarchy within one file, be kept separate from persistent
  identifiers, which belong in `Dbxref` or `gene_id`.
- **Attribute values not escaped.** A raw `;` inside a value splits one attribute into two and
  parses cleanly. See `corpus/fixtures/malformed/unescaped_semicolon.gff3`.
- **Term-ranged fields taking free text.** A note in the NMDC schema dated 2021-06-23 records that
  `has_function`, declared to range over `FunctionalAnnotationTerm`, takes strings in practice, and
  that those are frequently full text rather than compact identifiers. The declared range and the
  stored values disagree, and nothing rejected the values.
- **A repeated ID read as an error.** GFF3 permits a discontinuous feature to span several lines
  under one ID, so a repeated ID is only a violation when the lines cannot describe one feature. See
  `corpus/fixtures/malformed/duplicate_id.gff3`, which collides an ID across two different types.
- **Multiple parents refused.** Legal, and many tools reject it. See
  `corpus/fixtures/edge-cases/multiple_parents.gff3`.

## 5. Feature sources beyond GFF, added 2026-09-17

Everything above is about the nine-column GFF/GTF family. NMDC's own `FileTypeEnum` (106 permissible
values, in `microbiomedata/nmdc-schema` `src/schema/basic_slots.yaml`) names at least three more
`data_object_type` values that are one-row-per-feature tables in their own, non-GFF formats. None of
these were in this corpus before 2026-09-17; the fourteen-GFF-file counts elsewhere in this document
are unaffected and still describe only the GFF/GTF family.

| `data_object_type` | Format here | Fields | Header | Corpus entry |
|---|---|---|---|---|
| Annotation Enzyme Commission | TSV | 11 | None | `nmdc-ec` |
| Annotation KEGG Orthology | TSV | 11 | None | `nmdc-ko` |
| Crispr Terms | CRT's own format | 6 | None | `nmdc-crispr-terms` |

**Column meanings for all three are unverified.** No header row exists in any sampled file, and no
IMG/JGI pipeline documentation for these exact outputs has been read yet. The two TSVs' fields 4 and 9
are shaped like a percent and a small exponential number respectively, consistent with a BLAST- or
HMMER-style hit record, but that is a shape observation from one sample each, not a confirmed schema.
Do not assert column names for these three without reading the producing tool's own source or docs
first.

**Why they matter more than their sample size suggests.** `nmdc-ec` and `nmdc-ko` correspond to
`annotation_enzyme_commission` and `annotation_kegg_orthology` in BERDL's `nmdc.results` namespace,
1.23 billion and 1.83 billion rows respectively at production scale, the two largest tables in the
lakehouse. A unified feature model that only covers the GFF family would miss both of them.

## Sources

- GFF3 specification, https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md
- GTF 2.2 specification, http://mblab.wustl.edu/GTF22.html
- GFF2 description, http://gmod.org/wiki/GFF2
- BED and genePred, https://genome.ucsc.edu/FAQ/FAQformat.html
- AgBioData GFF3 recommendations, https://github.com/NAL-i5K/AgBioData_GFF3_recommendation
- AGAT format documentation, https://agat.readthedocs.io/en/latest/gxf.html
- Chado feature tables, vendored at `corpus/specifications/chado_1.4_feature_tables.sql`
- KBase Common Data Model, vendored at `corpus/specifications/kbase_cdm_bioentity.yaml`
