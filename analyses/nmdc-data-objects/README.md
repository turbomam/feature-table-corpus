# NMDC DataObject profile

This catalogue describes **NMDC DataObjects only**. NMDC is one source of evidence
for the broader feature/attribute modeling work. These fields, vocabularies, hosts,
and frequencies are not requirements of the proposed general model.

Collected 2026-09-21T15:34:56+00:00 from the [public NMDC API](https://api.microbiomedata.org).
Coverage: **303,977 DataObjects**, all 304 pages of
`data_object_set`, without a feature-file or workflow filter. Unique IDs and the
collection counts before/after agree. This traversal is not a transactional snapshot;
unchanged totals cannot prove that no individual record changed during collection.

Schema release: **11.23.0**, [commit 84651fe32b2e](https://github.com/microbiomedata/nmdc-schema/tree/84651fe32b2e2f783f5d38ef5b8757d90c5ab768).
The release's merged YAML embeds version `0.0.0`; the release, commit, URL, and
SHA-256 in the JSON provenance identify the actual source used.

## Categorical slots

Schema enums and booleans are discovered from DataObject's induced slots, including
inheritance. `compression_type` and the `type` class discriminator are explicitly
included as categorical strings; neither is falsely labeled an enum. Free-text names,
descriptions, identifiers, references, sizes, and checksums are not categorical slots.

| Slot | Range | Required | Allowed enum values | Observed distinct values | Present | Missing | Null | Empty string | Invalid type |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| compression_type | string | false | not enumerated | 0 | 0 | 303977 | 0 | 0 | 0 |
| data_category | DataCategoryEnum | true | 3 | 3 | 303977 | 0 | 0 | 0 | 0 |
| data_object_type | FileTypeEnum | true | 106 | 82 | 303977 | 0 | 0 | 0 | 0 |
| type | uriorcurie | true | not enumerated | 1 | 303977 | 0 | 0 | 0 | 0 |

[categorical-values.csv](categorical-values.csv) lists each value and its DataObject
count, including permitted-but-unobserved enum values with zero counts. Unknown enum
values remain visible. Missing, null, empty, and invalid types are separate states in
[counts.json](counts.json); these are not counted as distinct categorical values.

Counts measure records carrying a value; duplicate values in a multivalued slot would
count once per record. A multivalued slot's frequencies need not sum to the record total.
Empty lists and lists containing empty strings are recorded as `empty_list` and
`empty_item`; neither contributes categorical counts. All slots in this release are scalar.

## URL hosts

Hosts are parsed from the URL authority after the scheme and before the path, then
lowercased. Ports and user information are excluded; IPv6 hosts are supported.
Missing, null, empty, malformed, and hostless values remain separate. Bare paths or
bare domains are not silently treated as HTTP URLs. Counts describe metadata records,
not files fetched, host availability, or distinct URLs.

| Hostname | DataObjects |
|---|---:|
| `data.microbiomedata.org` | 256,359 |
| `nmdcdemo.emsl.pnnl.gov` | 26,423 |
| `storage.neonscience.org` | 5,646 |
| `massive.ucsd.edu` | 2,733 |
| `portal.nersc.gov` | 231 |

Distinct hosts: **5**.

URL states: missing: 12,585, present: 291,392.

[url-hosts.csv](url-hosts.csv) provides the same host counts as CSV.

## Reproduction and interpretation

Run from the repository root:

```sh
uv run --with linkml-runtime python scripts/profile_nmdc_data_objects.py collect
uv run --offline --with linkml-runtime python scripts/profile_nmdc_data_objects.py render
```

`collect` refreshes the public metadata projection and verifies completeness before
publishing aggregates. `render` recreates them offline from the checksum-verified
files under gitignored `local/nmdc-profile/`. No data files referenced by the URLs
are downloaded. The script is pinned to the API schema release above and refuses
a different release until its schema source is updated. A later collection may have
different counts; each report carries its own timestamps and content hashes.

Python 3.11 or later is required. Run `collect` online once to obtain the projection
and schema and populate uv's dependency cache. The documented `render` command uses
uv's `--offline` mode as well as making no API calls; it needs those cached dependencies.

The catalogue is derived from the [NMDC schema source](https://raw.githubusercontent.com/microbiomedata/nmdc-schema/84651fe32b2e2f783f5d38ef5b8757d90c5ab768/nmdc_schema/nmdc_materialized_patterns.yaml),
licensed CC0. [NMDC's data use policy](https://microbiomedata.org/nmdc-data-use-policy/)
applies to the source metadata. This is descriptive source profiling, not validation
of every NMDC schema constraint or a universal feature-table vocabulary.
