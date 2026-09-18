# Schema diagram

Generated 2026-09-18 from `schema/ber_feature_model.yaml` with LinkML's `erdiagramgen`
(`uv run --with linkml python3 -m linkml.generators.erdiagramgen schema/ber_feature_model.yaml -f mermaid --no-metadata`).
Regenerate after any schema change; this file is not auto-updated.

```mermaid
erDiagram
Attribute {
    string tag
    string value
}
Contig {
    string contig_id
    integer length_bp
    float lineage_confidence
    stringList taxonomic_lineage
}
Feature {
    CoordinateSystemEnum coordinate_system
    integer end
    string feature_id
    boolean is_selected
    integer phase
    string predicted_by
    string product
    string product_source
    float score
    string source
    integer start
    StrandEnum strand
    string translated_sequence
    string type
}

Feature ||--|o Contig : "seqid"
Feature ||--}o Attribute : "attributes"
Feature ||--}o Feature : "parent"
```

`erdiagramgen` lists every scalar and enum slot inside each entity box and draws an arrow only
for slots whose range is another class (`Contig`, `Feature`, `Attribute`). `schema/ber_feature_model.yaml`
itself is the source of truth if this diagram and that file ever disagree.
