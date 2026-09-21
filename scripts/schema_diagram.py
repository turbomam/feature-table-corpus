#!/usr/bin/env python3
"""Render this model's diagram with explicit inverse reference cardinalities."""
from pathlib import Path

from linkml.generators.erdiagramgen import ERDiagramGenerator


def main():
    schema = Path(__file__).resolve().parents[1] / 'schema/ber_feature_model.yaml'
    generator = ERDiagramGenerator(str(schema), format='mermaid', metadata=False)
    seqid = generator.schemaview.induced_slot('seqid', 'Feature')
    parent = generator.schemaview.induced_slot('parent', 'Feature')
    if not (seqid.required and not seqid.multivalued and seqid.range == 'Contig'
            and parent.multivalued and not parent.required and parent.range == 'Feature'):
        raise ValueError('Feature relationships changed; review the diagram cardinality overrides')
    diagram = generator.serialize()
    # LinkML's current renderer does not infer how many records can reference
    # the same target. Correct those two edges and orient right-hand crow's feet.
    overrides = {
        'Feature ||--|| Contig : "seqid"': 'Contig ||--o{ Feature : "seqid"',
        'Feature ||--}o Feature : "parent"': 'Feature }o--o{ Feature : "parent"',
    }
    for original, corrected in overrides.items():
        if diagram.count(original) != 1:
            raise ValueError(f'Generator output changed; review cardinality override: {original}')
        diagram = diagram.replace(original, corrected)
    diagram = diagram.replace('||--}o', '||--o{')
    print('\n'.join(line.rstrip() for line in diagram.splitlines()).rstrip())


if __name__ == '__main__':
    main()
