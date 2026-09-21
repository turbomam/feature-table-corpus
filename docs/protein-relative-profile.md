# Protein-relative annotation profile

`nmdc-pfam-protein/1.0.0` supports **NMDC Pfam/HMMER output**, one producer
convention. It does not detect arbitrary GFF dialects or make NMDC conventions
universal requirements. Generic attributes remain independent of GFF column 9.

The unchanged full Pfam source has **416 hits on 397 proteins**. With supporting
CDSs, the Dataset contains **813 features**. Source column 1 identifies a protein;
columns 4–5 are one-based inclusive amino-acid offsets. Model hits have
`coordinate_system: protein`, a direct CDS `parent`, and that CDS's contig as
`seqid`. Source protein identity is retained as an explicit semantic mapping.

## Evidence and context

Three full files from `nmdc:wfmgan-11-5xxrm214.2` are retained under
`corpus/sources/nmdc/`: Pfam GFF, structural annotation GFF, and amino-acid FASTA.
Their MD5s match NMDC DataObject values in
[the source manifest](../model/examples/source-artifacts.yaml). The
[corpus index](../corpus/index.yaml) records SHA-256, URLs, attribution, license,
and selection scope. These companion files belong to the curated examples'
biosample, distinct from the original smallest-file sampling.

[nmdc-pfam-context.json](../model/examples/conversions/nmdc-pfam-context.json)
is generated from structural CDSs, translations, one-to-one protein/CDS bindings,
and source artifact hashes. The generator joins exact source IDs; it never derives
coordinates by splitting identifiers or invents contig lengths from endpoints.
Missing or ambiguous bindings, missing translations, context/assembly mismatches,
and hits beyond protein lengths are rejected. Context must cover exactly the
source protein references.

Provenance is declared and supported by retained evidence. Consistency checking
does not independently authenticate translation biology or provide a tamper-proof
signature over context. This profile does not convert protein offsets to genomic
positions.

## Run the example

```sh
mkdir -p local/protein-demo
just conversion-import \
  corpus/sources/nmdc/nmdc_wfmgan-11-5xxrm214.2_pfam.gff \
  nmdc-pfam-protein/1.0.0 nmdc:wfmgas-11-19jh9v28.1 \
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

The first query finds **PF13518 at amino acids 17–70**. The second finds that
CDS with PF13358 (168–312), PF13592 (95–154), and PF13518. Its genomic interval
is **63–1091 on the minus strand** of scaffold `scf_10_c1`. Tests supply the wrong
kind of reference to each coordinate-space query and require no matches.

Exact export recovers original bytes. Reconstruction uses modeled fields and
semantic reference/attribute-group mappings without source feature text. Both
check consistency against the separately supplied original context first.
Validation and export require `--protein-context`; passing the bundle's own copy
would not provide independent evidence. Coordinated edits to context bindings,
translations or provenance and their Dataset copies are rejected against the
original. Supporting CDSs are not emitted as extra Pfam rows, and
the contextual relationship is not fabricated as a source Parent tag. Unknown,
repeated, and empty attributes preserve their ordering and grouping; SourceDocument
keeps comments and lexical details.

## Context generation and limits

`just protein-context ANNOTATION STRUCTURAL FASTA REFERENCE OUTPUT` invokes
[protein_context.py](../scripts/protein_context.py). Supply `--annotation-uri`,
`--structural-uri`, and `--fasta-uri` using the corresponding indexed origin URLs.
The command writes a new context; the regression test reproduces the checked-in
JSON from all three unchanged sources and requires exact instance equality.

The CLI refuses overwrites. The builder supports uppercase amino-acid FASTA and
rejects duplicate IDs or characters outside `A`–`Z`, including stop markers.
Alternate protein names require explicit bindings, with one protein per CDS.
Source rows require ID, HMMER source, Pfam accession, no Parent, and strand/phase
`.`. Other annotation families, lossy conversion, and edited-instance export
remain unsupported. The [report](../analyses/conversion-roundtrips/README.md)
measures preservation separately from strict source-format validity.
