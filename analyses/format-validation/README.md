# Independent format validation

GenomeTools **1.6.6** measures all retained entries indexed as GFF3, including
the nine altered fixtures and selected BGC excerpt. [report.json](report.json) records source SHA-256,
exit status, full diagnostics, and the derived fixture's expected verdict read
from `corpus/index.yaml`. Its current results are **8 accepted, 21 rejected,
and 10 not checked** (other formats). Linked/restricted/unlocated files are not
fetched or validated. This report is distinct from
[conversion preservation](../conversion-roundtrips/README.md).

## Reproduce

```sh
just validity-install  # explicit network download into gitignored local/tools/
just validity-check   # read-only; also part of just check
just validity-report  # explicitly regenerate the tracked report; review its diff
```

The installer supports Apple Silicon macOS and x86-64 Linux. It verifies the
upstream release archive's pinned SHA-256 before extraction. Python 3.11.8+
is needed for safe tar extraction. On other platforms, install GenomeTools
1.6.6 separately and set `GENOMETOOLS` to its executable path. The report checks
the version and normalizes only the executable path in diagnostics; source
paths, warning/error text, and verdicts are preserved. A timeout, crash,
unexpected output, or tool startup failure fails the check rather than counting
as rejection. CI runs the same real validator and compares the retained report.
`just test` reports an explicit skip for the three real-tool regression methods
if GenomeTools is not installed; the mock execution-failure test still runs.
`just validity-check` and therefore `just check` always require the real binary.
Extraction filters are available in Python 3.11 through the
[3.11.4 backport](https://docs.python.org/3.11/library/tarfile.html#extraction-filters);
direct invocation with a Python lacking that feature fails before downloading.

## What the result means

All **six malformed fixtures are rejected**, and all **three valid edge cases
are accepted**. Tests deliberately flip a label, repair an invalid file without
changing its label, and replace the saved report to prove disagreement fails.
GenomeTools accepts the phase-changed biological example and the silently split
Note example: legal syntax does not establish biological or authorial intent.

Of the 19 retained producer GFF3 files, Prodigal and all three RefSeq files are
accepted. Fifteen NMDC files fail at the required first-line version directive,
including the two companion GFFs for the protein profile.
The validator stops at its first error, so this does not establish whether they
have additional problems. Prodigal emits warnings about absent sequence-region
directives. Those warnings are retained; any internally inferred region is not
written back to the source or promoted to measured biological metadata.

The command is `gt gff3validator FILE`, with no ontology `-typecheck`, no
cross-reference vocabulary check, and no reference sequence/protein comparison.
Acceptance means acceptance by this pinned validator/configuration. It does not
establish valid SO typing, biological correctness, conversion support, or
conformance of BED/GTF/INSDC/other formats. Conversely, a restrictive converter
may reject a valid circular or discontinuous feature.

## Tool choice and sources

[GenomeTools documentation](https://genometools.org/tools/gt_gff3validator.html)
describes the strict validator and optional vocabulary checks. The
[1.6.6 release](https://github.com/genometools/genometools/releases/tag/v1.6.6)
provides the pinned binaries; archive hashes are recorded in
[the installer](../../scripts/install_genometools.py).

We also evaluated PyPI `gff3==1.0.1`'s `Gff3(path).lines[*].line_errors` API:
it reported five of the six malformed fixtures, but parsing alone left the
dangling-parent case without line errors. Its
[API documentation](https://gff3-py.readthedocs.io/en/latest/usage.html) separates
parsing and further checks. That experiment is not a claim that no configuration
of that package can detect missing parents. GenomeTools provides the required
end-to-end verdict here without an additional custom interpretation layer.

Upgrading the validator requires rerunning the control cases, inspecting all
diagnostic changes, and reviewing any changes to the corpus's validity labels.
Do not regenerate this report merely to hide an unexpected verdict.
