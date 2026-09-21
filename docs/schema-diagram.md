# Schema diagram

Generated 2026-09-21 from `schema/ber_feature_model.yaml` with `just diagram`, using
LinkML's `erdiagramgen` and the model-specific cardinality corrections in
[`scripts/schema_diagram.py`](../scripts/schema_diagram.py).
Regenerate after any schema change; this file is not auto-updated.

```mermaid
erDiagram
Attribute {
    string key
    string value
}
Contig {
    string contig_id
    string generated_by
    integer length_bp
    float lineage_confidence
    uriList source_files
    stringList taxonomic_lineage
}
Dataset {

}
Feature {
    CoordinateSystemEnum coordinate_system
    integer end
    string feature_id
    string generated_by
    boolean is_selected
    integer phase
    string product
    string product_source
    float score
    string source
    uriList source_files
    integer start
    StrandEnum strand
    string translated_sequence
    string type
}

Dataset ||--o{ Contig : "contigs"
Dataset ||--o{ Feature : "features"
Contig ||--o{ Feature : "seqid"
Feature ||--o{ Attribute : "attributes"
Feature }o--o{ Feature : "parent"
```

`Dataset` is the tree root, added 2026-09-18 so a whole harmonized data file validates as one
instance of one class instead of a bag of loose Contig and Feature fragments. Its own box is
empty because it has no scalar slots, only the two relationships shown.

`erdiagramgen` lists every scalar and enum slot inside each entity box and draws an arrow only
for slots whose range is another class (`Contig`, `Feature`, `Attribute`). `schema/ber_feature_model.yaml`
itself is the source of truth if this diagram and that file ever disagree.

Each Feature references exactly one Contig, while a Contig may have zero or many
Features. Parent links are optional and many-to-many: a child can have multiple
parents, and a parent can have multiple children. The wrapper preserves those inverse
cardinalities when regenerating; it fails for review if the relevant schema constraints
or upstream generator output change. It does not modify the schema.
