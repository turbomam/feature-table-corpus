# Protein coordinates

A domain or other hit reported in amino-acid positions has its CDS as `seqid`. Decided 2026-09-28 in [issue 40](https://github.com/turbomam/feature-table-corpus/issues/40); before that, the hit's `seqid` was the contig. The [NMDC Pfam profile](#the-nmdc-pfam-profile) below converts NMDC HMMER Pfam output under this rule.

## The rule

A `SequenceFeature` with `coordinate_system: protein` has `start` and `end` in one-based, inclusive amino-acid positions along the translation of one CDS. That CDS is the hit's `seqid`, and it is also the hit's only `parent`. The CDS itself is an ordinary contig-coordinate feature, so its own `seqid` is the contig.

```yaml
- feature_id: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091
  seqid: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1        # the contig
  type: CDS
  start: 63
  end: 1091
  coordinate_system: contig
- feature_id: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091_168_312
  seqid: nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091  # the CDS
  type: PF13358
  start: 168                                          # residue 168 of the CDS translation
  end: 312
  coordinate_system: protein
  parent: [nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091]
```

The model has no Protein class. A CDS already carries `translated_sequence`, and in the prokaryotic sources here (NMDC and IMG) one CDS row translates to one protein, so the CDS stands for its protein.

The Dataset validator (`scripts/validate_closed.py`) refuses:

- a protein-coordinate feature whose `seqid` names a contig, with a message saying the CDS is needed;
- one whose `seqid` names anything but a contig-coordinate CDS;
- one whose `parent` is not that same CDS;
- a contig-coordinate feature whose `seqid` names a feature;
- a hit that ends past its CDS's `translated_sequence`, when the translation is present;
- an ID used as both a `contig_id` and a `feature_id`.

## Why

- The GFF3 specification defines column 1 as the landmark "used to establish the coordinate system for the current feature" (https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md). A contig does not establish amino-acid positions; the protein does.
- Chado locates a feature on `srcfeature_id`, a foreign key to `feature`, so any feature, including a protein, can be the landmark ([model comparison](model-comparison.md)).
- NMDC's own hit files already put the protein in column 1. Keeping it there needs no re-interpretation of the source.
- A tool that joins on `seqid`, `start` and `end` without looking at `coordinate_system`, such as polars-bio's `overlap`, now cannot compare amino-acid offsets with contig bases in a validated Dataset: the validator refuses an ID used as both a contig and a feature, so a CDS ID never matches a contig ID. Under the old shape that join was wrong unless the caller knew to add `coordinate_system` to the key. The polars-bio behavior is read from its join signature, not run on our data.
- Hits are most of NMDC's feature data: about 62.7M of 85.8M sampled rows, measured in https://github.com/microbiomedata/nmdc-lakehouse/pull/364. That PR wrote Parquet locally and left loading into BERDL out of scope, and none had been loaded when this was decided on 2026-09-28, so changing the shape cost a regenerated export, not a migration.

## Querying

Overlap within one protein is the same query as overlap within one contig, with the CDS ID as the reference:

```sql
SELECT feature_id, type, start, "end"
FROM sequence_feature
WHERE coordinate_system = 'protein' AND seqid = ? AND start <= ? AND "end" >= ?;
```

After validation only protein-coordinate features name a CDS as `seqid`, so the `coordinate_system` condition changes nothing there; it keeps the query right on data that has not been validated. To reach a hit's contig, go through its CDS:

```sql
SELECT hit.feature_id, hit.type, cds.seqid AS contig
FROM sequence_feature hit JOIN sequence_feature cds ON hit.seqid = cds.feature_id
WHERE hit.coordinate_system = 'protein';
```

In the schema, `SequenceFeature.seqid` is `any_of` Contig or SequenceFeature, while `LocationPart.seqid` stays a Contig. One column cannot be a foreign key to two tables, so the DuckDB loader (`scripts/build_duckdb.py`) has no foreign key on `feature.seqid`; the validator checks it before loading.

## Alternatives

**Keep the contig as `seqid`.** This was the model until 2026-09-28 (`nmdc-pfam-protein/2.0.0`). It is cheapest to keep, and the contig is one column away. It contradicts GFF3, and any join on `seqid` has to remember `coordinate_system` or it silently mixes residues with bases. Rejected for that reason.

**Add an alignment-target structure.** GFF3 writes a hit's position on the thing it matched as `Target=id start end [strand]`, with an optional CIGAR-like `Gap`. NMDC writes the same idea with its own keys (`model_start`, `model_end`, `subject_start`, `subject_end`), which the model keeps as untyped attribute strings. A typed target (ID, start, end, strand, alignment) would hold either form. This answers a different question, where on the Pfam model or reference protein the hit aligns, so it does not replace the rule above. It was added as `SequenceFeature.target` in https://github.com/turbomam/feature-table-corpus/issues/94, and `nmdc-pfam-protein` fills it from `model_start` and `model_end`.

**A separate Protein class as the landmark.** The hit's `seqid` would name a Protein record that points to its CDS. That repeats what the CDS already holds, its identity and translation, for no source here that needs it. It would be worth revisiting for a source where one protein comes from several CDS parts, as in eukaryotic annotation such as Phytozome, where each CDS part has its own ID. For those sources the landmark would be the transcript or a joined CDS; this decision does not settle that case.

**Chado's ranked locations.** Chado gives one feature several ranked `featureloc` rows, so a hit can be located on the protein and on the genome at once. The model has one scalar location per feature, and adding a second location for the same feature is a larger change than any source here requires.

**KBase CDM associations.** The KBase Common Data Model records a hit as an association between a protein and a domain, with no coordinates. That loses the domain positions that BERIL queries ask for, so it was not considered further.

## What changed with this rule

- `nmdc-pfam-protein` moved to 3.0.0, because its mapping changed; a 2.0.0 bundle is refused as an unsupported profile.
- Both example Datasets, the converter, the validator, the DuckDB loader and its overlap query, the schema diagram and the flat-profile audit follow the rule.
- The NMDC lakehouse converter (`microbiomedata/nmdc-lakehouse`, `src/nmdc_lakehouse/feature_convert.py`) still writes the contig and changes separately.

## The NMDC Pfam profile

`nmdc-pfam-protein/5.0.0` supports **NMDC Pfam/HMMER output**, one producer convention. It does not detect arbitrary GFF dialects or make NMDC conventions universal requirements. Generic attributes remain independent of GFF column 9.

The unchanged full Pfam source has **416 hits on 397 proteins**. With supporting CDSs, the Dataset contains **813 features**. Source column 1 identifies a protein; columns 4–5 are one-based inclusive amino-acid offsets. Model hits have `coordinate_system: protein` and their CDS as both `seqid` and `parent` ([the rule](#the-rule)). Source protein identity is retained as an explicit semantic mapping.

### Evidence and context

Three full files from `nmdc:wfmgan-11-5xxrm214.2` are retained under `corpus/sources/nmdc/`: Pfam GFF, structural annotation GFF, and amino-acid FASTA. Their MD5s match NMDC DataObject values in [the source manifest](../model/examples/source-artifacts.yaml). The [corpus index](../corpus/index.yaml) records SHA-256, URLs, attribution, license, and selection scope. These companion files belong to the curated examples' biosample, distinct from the original smallest-file sampling.

[nmdc-pfam-context.json](../model/examples/conversions/nmdc-pfam-context.json) is generated from structural CDSs, translations, one-to-one protein/CDS bindings, and source artifact hashes. Exactly two distinct companion artifacts declare `structural_annotation` and `protein_sequence` roles; repeated roles, URIs or digests are rejected. Artifact URIs must be complete absolute URIs; HTTP(S) references also require a host and a valid port. Syntax checks do not fetch the resource or establish its authenticity. The generator joins exact source IDs; it never derives coordinates by splitting identifiers or invents contig lengths from endpoints. Missing or ambiguous bindings, missing translations, context/assembly mismatches, and hits beyond protein lengths are rejected. Context must cover exactly the source protein references. If context attributes include GFF `ID`, `Parent` or `product`, their values must agree with the corresponding typed context slots before bindings are used.

Provenance is declared and supported by retained evidence. Consistency checking does not independently authenticate translation biology or provide a tamper-proof signature over context. This profile does not convert protein offsets to genomic positions.

### Run the example

```sh
mkdir -p local/protein-demo
just conversion-import \
  corpus/sources/nmdc/nmdc_wfmgan-11-5xxrm214.2_pfam.gff \
  nmdc-pfam-protein/5.0.0 nmdc:wfmgas-11-19jh9v28.1 \
  local/protein-demo/bundle.json \
  --protein-context model/examples/conversions/nmdc-pfam-context.json
just conversion-export local/protein-demo/bundle.json local/protein-demo/exact.gff exact \
  --protein-context model/examples/conversions/nmdc-pfam-context.json
just conversion-export local/protein-demo/bundle.json local/protein-demo/reconstructed.gff reconstruct \
  --protein-context model/examples/conversions/nmdc-pfam-context.json
python3 -c 'import json; from pathlib import Path; p=Path("local/protein-demo"); (p/"dataset.json").write_text(json.dumps(json.loads((p/"bundle.json").read_text())["dataset"]))'
just build-duckdb local/protein-demo/dataset.json local/protein-demo/features.duckdb
just query-overlap protein nmdc:wfmgas-11-19jh9v28.1_scf_10_c1_63_1091 17 70 local/protein-demo/features.duckdb
just query-duckdb local/protein-demo/features.duckdb PF13358 PF13592 PF13518
```

The first query finds **PF13518 at amino acids 17–70**. The second finds that CDS with PF13358 (168–312), PF13592 (95–154), and PF13518. Its genomic interval is **63–1091 on the minus strand** of scaffold `scf_10_c1`. Tests supply the wrong kind of reference to each coordinate-space query and require no matches.

Exact export recovers original bytes. Reconstruction uses modeled fields and semantic reference/attribute-group mappings without source feature text. Both check consistency against the separately supplied original context first. Validation and export require `--protein-context`; passing the bundle's own copy would not provide independent evidence. The API rejects shared mutable containers, including a shallow copy of the embedded context. A separately copied or reloaded edited document is still not a trusted original: callers must retain and select the original context. Object separation does not authenticate its provenance. Coordinated edits to context bindings, translations or provenance and their Dataset copies are rejected against the original. Supporting CDSs are not emitted as extra Pfam rows, and the contextual relationship is not fabricated as a source Parent tag. Unknown, repeated, and empty attributes preserve their ordering and grouping; SourceDocument keeps comments and lexical details.

### Context generation and limits

`just protein-context ANNOTATION STRUCTURAL FASTA REFERENCE OUTPUT` invokes [protein_context.py](../scripts/protein_context.py). Supply `--annotation-uri`, `--structural-uri`, and `--fasta-uri` using the corresponding indexed origin URLs. The command writes a new context; the regression test reproduces the checked-in JSON from all three unchanged sources and requires exact instance equality.

The CLI refuses overwrites. The builder supports uppercase amino-acid FASTA and rejects duplicate IDs or characters outside `A`–`Z`, including stop markers. Alternate protein names require explicit bindings, with one protein per CDS. Source rows require ID, HMMER source, Pfam accession, no Parent, and strand/phase `.`. Other annotation families, lossy conversion, and edited-instance export remain unsupported. The [report](../analyses/conversion-roundtrips/README.md) measures preservation separately from strict source-format validity.
