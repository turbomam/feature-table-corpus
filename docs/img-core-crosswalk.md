# Crosswalk to IMG's core database

[`model/crosswalks/img-core-v400.sssom.tsv`](../model/crosswalks/img-core-v400.sssom.tsv) maps
slots of the feature model to columns of IMG's `img_core_v400` database, for
https://github.com/turbomam/feature-table-corpus/issues/47. It's an
[SSSOM](https://mapping-commons.github.io/sssom/) table: one row per slot and column, with
`skos:closeMatch` where the two hold the same thing in a different form, and `skos:relatedMatch`
where they only overlap. No row is `skos:exactMatch`, because the source doesn't state coordinate
bases or value spellings.

Each subject is a slot, typed `rdf property`, with its SSSOM `subject_label` naming the class it
is used on, such as `Feature.start` or `LocationPart.start`; the same slot can map to different
columns on different classes. A list of structs, such as `Feature.attributes` or
`FeatureLocation.parts`, maps through its items' slots (`Attribute.key`, `LocationPart.start`),
not as one column. A hit table's `gene_oid` maps to both `seqid` and `parent`, because the model
requires both on a protein-coordinate Feature.

## Source

IMG's code isn't public, but its database schema is readable as a LinkML view in
https://github.com/cmungall/bridge-schemas, file `src/bridge_schemas/schema/jgi/img_core_v400.linkml.yaml`,
read at commit ba25724947002e40a0393dba624a6c200d9ef603 on 2026-09-29. That view has 117 tables,
and every column named in the crosswalk exists in it (checked the same day). The view isn't
vendored here, since the repository has no license. The IMG files this repository vendors come
from the same database: `2708743150.gff` and its tables are a `img_core_v400` taxon export, and
`scripts/img_taxon_bundle_map.py` maps them. So the hit-table rows follow what that mapping does.

## How the model lines up

- `gene` is a Feature on contig coordinates: `start_coord`, `end_coord`, `strand`, `locus_type`,
  `product_name`, and `scaffold` and `taxon` as integer keys to contig and genome tables.
- `gene_frag_coords` is `FeatureLocation.parts`, one row per part ordered by `frag_order`.
- `gene_feature_tags` is `Attribute`: an open tag/value table.
- The per-method hit tables (`gene_pfam_families`, `gene_cog_groups`, `gene_ko_terms` and others)
  are protein-coordinate Features on the gene: `query_start` and `query_end` are `start` and `end`,
  `bit_score` is `score` with `score_type: bit_score`, and `subj_start` and `subj_end` are the
  alignment target's positions.
- `gene_sig_peptides` holds the SignalP sites the TMHMM/SignalP mapping reads from GFF.

## What doesn't line up

- The view has no scaffold or taxon table, so `Contig.length_bp`, `topology` and
  `ContigCollection` have no column here. `docs/genes.md` in bridge-schemas joins `gene` to a
  `taxon` table, so the database has one; the view leaves it out.
- `evalue`, `percent_identity` and `align_length` on the hit tables have no typed slot; they are
  Attributes today. Typed attribute values are
  https://github.com/turbomam/feature-table-corpus/issues/42.
- `gene.is_pseudogene` is a flag on a gene row, where GFF, and so the model, writes type
  `pseudogene`. `gc_percent`, `dna_seq_length` and `aa_seq_length` can be derived and have no
  slot.
- `gene_tigrfams` keeps its positions as text lists (`sfstarts`, `sfsends`), so one row can hold
  several spans.

What the IMG website queries, and so which of these columns matter most, is application code.
That still needs someone at JGI.
