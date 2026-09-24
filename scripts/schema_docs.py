#!/usr/bin/env python3
"""Generate LinkML schema reference pages into the staged site, after prepare_docs.py.

The site home becomes the feature model's generated index, as on the nmdc-schema site,
followed by one block of links to the supplementary material.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "local" / "site-src"

SCHEMAS = [
    ("model/schema/ber_feature_model.yaml", DEST),
    ("model/schema/source_document.yaml", DEST / "source-document"),
]

# One block of links, in the order a new reader needs them. Paths are relative to the site root.
SUPPLEMENTARY = [
    ("Start here", [
        ("Repository overview", "overview.md"),
        ("Repository map and tasks", "docs/repository-map.md"),
        ("Source document schema", "source-document/index.md"),
        ("Schema diagram", "docs/schema-diagram.md"),
        ("Schema guide", "model/schema/README.md"),
    ]),
    ("Evidence and formats", [
        ("Reading guide", "docs/feature-format-reading.md"),
        ("Prior art", "docs/prior-art.md"),
        ("Model comparison", "docs/model-comparison.md"),
        ("Columns and producer conventions", "docs/columns-and-discretion.md"),
        ("Chado and scope", "docs/chado-and-scope.md"),
        ("Corpus sources and downloads", "corpus/README.md"),
        ("Acquisition history", "corpus/PROVENANCE.md"),
        ("Independent validation", "analyses/format-validation/README.md"),
    ]),
    ("Model contracts", [
        ("Generic attributes", "docs/attributes.md"),
        ("Joined and circular locations", "docs/feature-locations.md"),
        ("Source documents and comments", "docs/source-documents.md"),
        ("Workflow provenance", "docs/workflow-provenance.md"),
    ]),
    ("Conversion and query examples", [
        ("Versioned profiles", "docs/conversion-profiles.md"),
        ("Protein-relative Pfam profile", "docs/protein-relative-profile.md"),
        ("Real BGC query exercise", "analyses/bgc-query/README.md"),
        ("Round-trip evidence", "analyses/conversion-roundtrips/README.md"),
        ("Converted BED12", "model/examples/conversions/README.md"),
        ("One biosample", "model/examples/one-biosample-sequencing/README.md"),
        ("Biosample transformation notes", "model/examples/one-biosample-sequencing/notes.md"),
        ("Multiple Pfams", "model/examples/multiple-pfams/README.md"),
        ("Query requirements", "docs/query-requirements.md"),
        ("Parsed source document", "model/examples/source-documents/README.md"),
    ]),
    ("NMDC-specific analyses", [
        ("DataObject catalogue and counts", "analyses/nmdc-data-objects/README.md"),
        ("Source sampling", "analyses/nmdc-selection/README.md"),
    ]),
    ("Repository decisions", [
        ("Build and publish the docs", "docs/documentation-site.md"),
        ("Artifact layout", "docs/decisions/001-artifact-layout.md"),
    ]),
]


def supplementary_block():
    lines = ["", "## Supplementary material", ""]
    for group, links in SUPPLEMENTARY:
        lines.append(f"**{group}:** " + " · ".join(f"[{title}]({path})" for title, path in links))
        lines.append("")
    return "\n".join(lines)


def generate():
    if not DEST.is_dir():
        raise SystemExit("Run scripts/prepare_docs.py first")
    # The repository README would collide with the generated index.md at the site root.
    readme = DEST / "README.md"
    if readme.exists():
        readme.rename(DEST / "overview.md")
    for schema, out in SCHEMAS:
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gen-doc", "--subfolder-type-separation", "-d", str(out), str(ROOT / schema)], check=True)
    index = DEST / "index.md"
    index.write_text(index.read_text() + supplementary_block())
    print(f"Generated schema pages for {len(SCHEMAS)} schemas in {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    generate()
