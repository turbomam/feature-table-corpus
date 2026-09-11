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
| GTF 2.2 | 8 | `attributes`, plus optional comments | 9 or more | Yes |
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

**GTF 2.2** lists its fields as seqname, source, feature, start, end, score, strand, frame, then
attributes and optional comments. Two attributes are mandatory: `gene_id` and `transcript_id`.

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
intentional ambiguity in the document, and it is the reason both the NMDC schema and the KBase
Common Data Model replaced the single column with separate e_value and p_value slots.

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

*Unverified:* the exact arithmetic mapping between GFF3 phase and GTF frame. Sources differ on
whether they are identical or complements, and this document will not assert one. That uncertainty
is itself the finding.

*Quoted, AgBioData GFF3 recommendations:* the CDS phase field "is commonly misinterpreted by both
dataset generators and consumers, which can lead to vastly different ... amino acid sequences."
Their recommendation is to validate phase against translation tables rather than trust it.

Two fixtures in this corpus isolate the problem:

- `data/derived-malformed/cds_phase_illegal.gff3` sets phase to 3, outside the permitted set. A
  validator catches it.
- `data/derived-edge-cases/cds_phase_biologically_wrong.gff3` changes phase to another permitted
  value. **No validator can catch it.** The file stays valid and the protein changes.

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

- **Score is routed around rather than used.** Both the NMDC schema and the KBase Common Data Model
  replace the single score column with separate e_value and p_value slots, and the KBase schema
  calls them ill-defined score fields in its own documentation. When two independent models make the
  same substitution, the column is the problem.
- **ID conflated with a persistent identifier.** The AgBioData recommendations ask that the `ID`
  attribute, which exists to express hierarchy within one file, be kept separate from persistent
  identifiers, which belong in `Dbxref` or `gene_id`.
- **Attribute values not escaped.** A raw `;` inside a value splits one attribute into two and
  parses cleanly. See `data/derived-malformed/unescaped_semicolon.gff3`.
- **Term-ranged fields taking free text.** A note in the NMDC schema dated 2021-06-23 records that
  `has_function`, declared to range over `FunctionalAnnotationTerm`, takes strings in practice, and
  that those are frequently full text rather than compact identifiers. The declared range and the
  stored values disagree, and nothing rejected the values.
- **A repeated ID read as an error.** GFF3 permits a discontinuous feature to span several lines
  under one ID, so a repeated ID is only a violation when the lines cannot describe one feature. See
  `data/derived-malformed/duplicate_id.gff3`, which collides an ID across two different types.
- **Multiple parents refused.** Legal, and many tools reject it. See
  `data/derived-edge-cases/multiple_parents.gff3`.

## Sources

- GFF3 specification, https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md
- GTF 2.2 specification, http://mblab.wustl.edu/GTF22.html
- GFF2 description, http://gmod.org/wiki/GFF2
- BED and genePred, https://genome.ucsc.edu/FAQ/FAQformat.html
- AgBioData GFF3 recommendations, https://github.com/NAL-i5K/AgBioData_GFF3_recommendation
- AGAT format documentation, https://agat.readthedocs.io/en/latest/gxf.html
- Chado feature tables, vendored at `specs/chado_1.4_feature_tables.sql`
- KBase Common Data Model, vendored at `specs/kbase_cdm_bioentity.yaml`
