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
census. The neighbors query below fixes their semantics: chromosome order on one linear
contig, strand returned rather than interpreted, and distance as intervening bases.

| Requirement | Executable coverage |
|---|---|
| Multiple distinct Pfams on the same gene | Real three-Pfam example; a requested pair must occur on one CDS; duplicate domains and CRISPR repeats are negative controls |
| Genomic interval overlap | Explicit contig coordinate space and contig ID; inclusive endpoint tests |
| Protein interval overlap | Explicit protein coordinate space and parent CDS ID; never compared directly to genomic offsets |
| Source annotation lookup | Exact `key`/`value` match through a nested attribute list |
| Identifier and product access | Scalar `feature_id` and `product` columns retained by the mapping |
| Features on either side of a position | Real actinorhodin genes from the RefSeq excerpt; inclusive endpoints, overlapping genes, a wrong sequence version; circular contigs, positions past the contig end, protein-coordinate references and uncertain endpoints refused |

`scripts/query_duckdb.py` runs parameterized queries against a read-only database. Examples
after `just build-duckdb`:

```sh
just query-overlap contig nmdc:wfmgas-11-19jh9v28.1_scf_1_c1 104 104
just query-overlap protein nmdc:wfmgas-11-19jh9v28.1_scf_1_c1_104_853 13 13
just query-attribute Name adh_short_C2
just query-neighbors NC_003888.3 5531500 local/build/actinorhodin.duckdb --count 2
```

The neighbors example needs a database built from the actinorhodin excerpt
(`corpus/derived-examples/actinorhodin.gff3`, imported with `gff3-contig/4.0.0`). It lists the
genes containing position 5,531,500 and the two nearest on each side, with `side` (`left`,
`contains` or `right` in chromosome coordinates), `strand`, and `intervening_bases`, the
bases strictly between the position and the gene. Upstream and downstream depend on whose
strand is meant, so the query returns strand and leaves that reading to the caller. A gene's
start and end are used, so introns count as occupied. It refuses, rather than answering
wrongly, a circular contig (the nearest feature can lie across the origin), a position past
the contig's recorded length, a CDS used as the reference for protein-coordinate hits, and
features with uncertain endpoints such as INSDC `<10..20`.

Both new query recipes accept an optional database path as their last argument.
The default is `local/build/ber_feature_model.duckdb`. Quote attribute values and paths
containing spaces; they are passed literally to the read-only query script.

The genomic query returns the CDS alone. The protein query returns its five overlapping
evidence hits. The attribute query returns the one Pfam hit. See
[the multiple-Pfam example](../model/examples/multiple-pfams/README.md) for positive and negative
controls of the domain-pair use case. Accession matching uses exact source strings; it does
not silently normalize database versions or resolve identifiers across namespaces.
