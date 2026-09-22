# Joined, partial and circular feature locations

The draft model now has optional **FeatureLocation** and **LocationPart** objects.
They represent the source's location expression separately from biological parent
links and BED drawing blocks. The versioned `insdc-locations/1.0.0` profile maps
real GenBank feature tables into these objects and reconstructs them.

## Model and query contract

An explicit location contains an operator (`single`, `join`, or `order`), an
ordered list of oriented parts, and `crosses_origin`. Every part has a qualified
sequence reference, one-based inclusive start/end, strand, and endpoint statuses
`exact`, `before` or `after`. Parts are in biological traversal order; complement
reverses order and orientation. `order` does not assert that parts form a joined
sequence. The [INSDC feature-table definition, sections 3.3–3.4](https://www.insdc.org/submitting-standards/feature-table/)
defines the source operators, endpoint symbols and qualifier forms.

When `location` is present, scalar Feature `start`/`end` are **only the envelope
of the reported part coordinates**. They are retained for indexing and existing
table layouts. Occupancy queries must use the parts: a CDS spanning 104–579 with
parts 104–160, 320–390 and 504–579 does not occupy 200–210. The semantic validator
requires the envelope to agree with those parts; it is never substituted for them.

`Contig.topology: circular` requires an explicit positive `length_bp`. Parts stay
within that reference; an origin-crossing feature uses ordered high- then low-
coordinate parts on the plus strand, reversed traversal on the minus strand.
`crosses_origin` is true exactly when one origin transition occurs. Parts must
follow their strand's coordinate order within one pass around the reference:
40 → 70 → 10 is a possible forward traversal, but 40 → 10 → 70 passes the
starting position again. Linear references reject origin transitions. This bounded model requires a single qualified reference,
uniform explicit strand, and nonoverlapping parts for each structured location.

Unknown endpoints and alternative-position sets remain unsupported; they are
rejected rather than replaced with guessed numbers. A before/after endpoint is
not an exact endpoint. Exact overlap queries reject a reference containing such
features. Explicit `reported` mode queries only the nominal reported parts and
labels partial results `partial-reported`; it does not claim to cover unknown
extensions, including bases outside the presented sequence.

Exact distance is the smallest number of intervening bases between any pair of
occupied parts, with zero for overlap or adjacency. On a known-length circular
reference it includes the path across the origin. Different references, protein
coordinates and uncertain endpoints are refused. This unsigned minimum distance
differs deliberately from the BGC exercise's signed gap in chromosome order.

## Retained evidence and supported conversion

| Evidence | Measured coverage | Boundary |
|---|---|---|
| [Six plant GenBank records](../corpus/sources/biopython/cor6_6.gb) | 38 features, six joined locations, seven features with partial endpoints, repeated qualifiers | Same-reference nucleotide records; no inferred gene/CDS parent relationships |
| [phiX174 GenBank record](../corpus/sources/ncbi-refseq/NC_001422.1_2026-09-21.gb) | 32 features, six origin-crossing joins, circular length 5,386 | Complete original record retained with accession version and annotation checksum |
| [Original phiX174 GFF3](../corpus/sources/ncbi-refseq/ncbi_refseq_phix174_GCF_000819615.1.gff) | Real circular/discontinuous source evidence | The original contig-only GFF profile still refuses it; the GenBank adapter does not broaden that older contract |

The plant CDS on `insdc:X62281.1` has the three parts listed above. Its two
`db_xref` qualifiers remain two ordered generic attributes. Qualifiers are not
modeled as GFF column 9: each retains its key and logical value, and the conversion
mapping records quoted, unquoted or valueless-flag form. Unique product and
translation values also populate typed slots. INSDC `codon_start` stays generic;
it is not equated with GFF phase.

For phiX174, `insdc:NC_001422.1:feature-2` has parts 3981–5386 and 1–136. Queries
at either chromosome end find it; an interior query at 2000 does not. All six
origin-crossing locations pass the same checks. Sequence accession version
qualifies reference identity; the source SHA-256 separately pins the annotation.

Both examples pass exact byte recovery and reconstruction from modeled feature
keys, locations and qualifiers. Headers, references and sequence text are retained
by SourceDocument. Reconstruction can normalize wrapping, line endings, equivalent
complement expressions and single-base spelling. Biopython **1.85**, an independent
consumer parser, checks that original and reconstructed records have equal
sequence identities, sequence bytes, feature locations/types and qualifiers.
This is not a full INSDC format or biological validation claim.

The profile refuses remote locations, between-base sites, unknown/alternative
positions, mixed strands, nested join/order operators, missing sequence lengths,
incomplete records and unsupported qualifier wrapping. It accepts the legacy
GenBank omitted-topology convention as linear. No EMBL or five-column submission
table adapter is implied. The [profile contract](../model/profiles/insdc-locations.yaml)
and [preservation report](../analyses/conversion-roundtrips/README.md) state its bounds.

## Reproduce and migrate

```sh
mkdir -p local/location-demo
just conversion-import corpus/sources/biopython/cor6_6.gb \
  insdc-locations/1.0.0 insdc:retained-plant-records local/location-demo/bundle.json
just conversion-export local/location-demo/bundle.json local/location-demo/exact.gb exact
just conversion-export local/location-demo/bundle.json local/location-demo/reconstructed.gb reconstruct
python3 -c 'import json; from pathlib import Path; p=Path("local/location-demo"); (p/"dataset.json").write_text(json.dumps(json.loads((p/"bundle.json").read_text())["dataset"]))'
just location-overlap local/location-demo/dataset.json insdc:X62281.1 200 210 reported
just location-distance local/location-demo/dataset.json insdc:X55053.1:feature-2 insdc:X55053.1:feature-3
just conversion-check
```

The overlap result can include the separately annotated intron and encompassing
gene, but excludes the joined CDS and mRNA. The distance example is zero because
the gene and CDS overlap. `exact` is the overlap default; omitting `reported` for
the partial X62281.1 record fails explicitly. Existing just launchers forward
conversion options, and `just check` runs both real and constructed controls.

Existing Dataset instances and the three older profile contracts remain valid.
Those adapters do not emit structured locations. Consumers of the new profile
must support parts or reject `location`; using its envelope alone changes query
meaning. Rebuild existing DuckDB files with `just build-duckdb`: the physical
mapping now retains topology and a JSON location object. The ordinary DuckDB
overlap helper uses exact parts and rejects uncertain endpoints. The explicit
location CLI provides reported-bounds queries and circular distance.
