# One source-document instance

[`prodigal.json`](prodigal.json) is the parsed representation of the unchanged
[`nmdc-prodigal` corpus file](../../data/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff).
Its origin is NMDC DataObject `nmdc:dobj-11-2jq65c25`, licensed CC BY 4.0 by NMDC;
the source URL is recorded in the JSON and in [`corpus.yaml`](../../corpus.yaml).
The original is 2,033 bytes with MD5 `92d78177f3c3d0c410d0b57c94ebf22c`;
the JSON also records its SHA-256 digest.

Reproduce it from the repository root into a **new** scratch path:

```shell
python3 scripts/source_document.py parse \
  data/nmdc/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff \
  --format gff3 --profile prodigal \
  --source-uri 'https://data.microbiomedata.org/data/nmdc:omprc-11-cfaemn69/nmdc:wfmgan-11-9ya9xh30.1/nmdc_wfmgan-11-9ya9xh30.1_prodigal.gff' \
  --output local/source-documents/prodigal-reproduced.json
cmp examples/source-documents/prodigal.json local/source-documents/prodigal-reproduced.json
just validate-source-example
```

There are five Sequence Data / Model Data blocks around six feature rows. The
sequence lengths are 359, 303, 298, 298, and 295 bases. The first block uses translation
table 4; the others use table 11. These are sequence-scoped settings, not one file-wide
value. `seqhdr` quotes and ordered/repeated metadata survive; training model names
are not interpreted as sample taxonomy.

This is a source-preservation example, separate from the harmonized Dataset examples.
See [the document model and parser contract](../../docs/source-documents.md) for
scope, generic versus producer profiles, exact replay, and validation limits.
