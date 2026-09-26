#!/usr/bin/env python3
"""Render this model's diagram with explicit inverse reference cardinalities."""
from pathlib import Path

from linkml.generators.erdiagramgen import ERDiagramGenerator

ROOT = Path(__file__).resolve().parents[1]

# LinkML's current renderer does not infer how many records can reference
# the same target. Correct those edges and orient right-hand crow's feet.
FEATURE_OVERRIDES = {
    'LocationPart ||--|| Contig : "seqid"': 'Contig ||--o{ LocationPart : "seqid"',
    'Feature ||--|| Contig : "seqid"': 'Contig ||--o{ Feature : "seqid"',
    'Feature ||--}o Feature : "parent"': 'Feature }o--o{ Feature : "parent"',
    # Many contigs share one assembly or bin, and one contig can be in an assembly and a bin.
    'Contig ||--}o ContigCollection : "member_of"': 'Contig }o--o{ ContigCollection : "member_of"',
}
# One Prodigal Sequence Data or FASTA header record sets the context for many records.
SOURCE_DOCUMENT_OVERRIDES = {
    'SourceRecord ||--|o SourceRecord : "context_record"': 'SourceRecord }o--o| SourceRecord : "context_record"',
}


def check_feature_slots(view):
    seqid = view.induced_slot('seqid', 'Feature')
    parent = view.induced_slot('parent', 'Feature')
    if not (seqid.required and not seqid.multivalued and seqid.range == 'Contig'
            and parent.multivalued and not parent.required and parent.range == 'Feature'):
        raise ValueError('Feature relationships changed; review the diagram cardinality overrides')
    member_of = view.induced_slot('member_of', 'Contig')
    if not (member_of.multivalued and not member_of.required and member_of.range == 'ContigCollection'
            and not member_of.inlined):
        raise ValueError('Contig.member_of changed; review the diagram cardinality override')


def check_source_document_slots(view):
    context = view.induced_slot('context_record', 'SourceRecord')
    if context.multivalued or context.required or context.range != 'SourceRecord':
        raise ValueError('SourceRecord.context_record changed; review the diagram cardinality override')


def render(schema, overrides, checks):
    generator = ERDiagramGenerator(str(schema), format='mermaid', metadata=False)
    for check in checks:
        check(generator.schemaview)
    diagram = generator.serialize()
    for original, corrected in overrides.items():
        if diagram.count(original) != 1:
            raise ValueError(f'Generator output changed; review cardinality override: {original}')
        diagram = diagram.replace(original, corrected)
    diagram = diagram.replace('||--}o', '||--o{').replace('||--}|', '||--|{').replace('||--|o', '||--o|')
    return '\n'.join(line.rstrip() for line in diagram.splitlines()).rstrip()


def render_combined():
    """Both schemas, for the documentation site's home page."""
    return render(ROOT / 'model/schema/feature_schemas.yaml',
                  {**FEATURE_OVERRIDES, **SOURCE_DOCUMENT_OVERRIDES},
                  [check_feature_slots, check_source_document_slots])


def main():
    print(render(ROOT / 'model/schema/ber_feature_model.yaml', FEATURE_OVERRIDES, [check_feature_slots]))


if __name__ == '__main__':
    main()
