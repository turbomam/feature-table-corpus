"""Derive Contig.translation_table from the translation_table attribute on CDS rows.

NMDC and IMG GFF write translation_table=N on every CDS row. The table is a property of
the contig, so it is set there only when the evidence is complete and consistent:

- every contig-coordinate CDS on the contig carries the attribute,
- all of those values are the same unsigned integer, and
- that integer is an assigned NCBI genetic code.

Values that disagree on one contig are a conflict for the caller to report; this module
never picks one. A contig is left unset when any CDS on it lacks the attribute, or when
all its CDS name the same non-integer or unassigned value. The attribute itself stays in Feature.attributes, so a
round trip that writes attributes back never needs the derived slot.
"""
from validate_closed import NCBI_GENETIC_CODES, table_value

KEY = "translation_table"


def contig_translation_tables(features):
    """Return ({contig_id: table}, [conflict message, ...]) for contig-coordinate CDS rows."""
    seen, incomplete = {}, set()
    for feature in features:
        if feature.get("type") != "CDS" or feature.get("coordinate_system") != "contig":
            continue
        found = [a["value"] for a in feature.get("attributes") or [] if a["key"] == KEY]
        if not found:
            incomplete.add(feature["seqid"])
        values = seen.setdefault(feature["seqid"], {})
        for value in found:
            # 11 and 011 name the same table; anything else is compared by its text.
            values.setdefault(table_value(value), feature["feature_id"])
    tables, conflicts = {}, []
    for contig, values in seen.items():
        if len(values) > 1:
            listed = ", ".join(f"{value!r} on {fid!r}" for value, fid in values.items())
            conflicts.append(f"contig {contig!r}: CDS {KEY} attributes disagree ({listed})")
        elif values and contig not in incomplete:
            (value,) = values
            if isinstance(value, int) and value in NCBI_GENETIC_CODES:
                tables[contig] = value
    return tables, conflicts


def with_translation_tables(contigs, features):
    """Copy contigs, adding each derived table; return (contigs, conflicts)."""
    tables, conflicts = contig_translation_tables(features)
    updated = []
    for contig in contigs:
        contig = dict(contig)
        if contig["contig_id"] in tables:
            contig["translation_table"] = tables[contig["contig_id"]]
        updated.append(contig)
    return updated, conflicts
