# Query requirements and evidence

The existing internal BERIL trace census, summarized on 2026-09-21, supports testing
several access patterns. Its human-message partition reported 429 protein/domain-coordinate
pattern hits, 269 genomic-coordinate hits, 190 name hits, and 179 identifier hits, among
2,366 human pattern hits overall. These are pattern matches, not distinct questions or
estimates of user preference. Categories can overlap, and protein-domain vocabulary alone
does not prove a request for a numeric interval. Assistant text, tool output, and subagent
prompts were counted separately from human messages.

This PR uses that existing aggregate summary to choose regression cases; it does not rerun
the trace census. The underlying audit stays internal. No account identifiers, raw traces,
or transcript quotations are included here. Proximity queries are also indicated by the
census but remain a separate extension: strand, distance, and neighboring-feature semantics
need to be specified before claiming support.

| Requirement | Executable coverage |
|---|---|
| Multiple distinct Pfams on the same gene | Real three-Pfam example; a requested pair must occur on one CDS; duplicate domains and CRISPR repeats are negative controls |
| Genomic interval overlap | Explicit contig coordinate space and contig ID; inclusive endpoint tests |
| Protein interval overlap | Explicit protein coordinate space and parent CDS ID; never compared directly to genomic offsets |
| Source annotation lookup | Exact `key`/`value` match through a nested attribute list |
| Identifier and product access | Scalar `feature_id` and `product` columns retained by the mapping |

`scripts/query_duckdb.py` runs parameterized queries against a read-only database. Examples
after `just build-duckdb`:

```sh
just query-overlap contig nmdc:wfmgas-11-19jh9v28.1_scf_1_c1 104 104
just query-overlap protein nmdc:wfmgas-11-19jh9v28.1_scf_1_c1_104_853 13 13
just query-attribute Name adh_short_C2
```

Both new query recipes accept an optional database path as their last argument.
The default is `local/build/ber_feature_model.duckdb`. Quote attribute values and paths
containing spaces; they are passed literally to the read-only query script.

The genomic query returns the CDS alone. The protein query returns its five overlapping
evidence hits. The attribute query returns the one Pfam hit. See
[the multiple-Pfam example](../model/examples/multiple-pfams/README.md) for positive and negative
controls of the domain-pair use case. Accession matching uses exact source strings; it does
not silently normalize database versions or resolve identifiers across namespaces.
