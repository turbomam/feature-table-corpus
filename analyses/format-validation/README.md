# Independent format validation

Ran on macOS arm64 on **2026-09-25**: GenomeTools **1.6.6** and GFF3toolkit
**2.1.0** checked all 50 retained GFF3 inputs. The existing
[report.json](report.json) now records each input's checksum and separate results
for each validator. Linked/restricted/unlocated files are not fetched.

| Validator | Accepted | Rejected | Other formats, not checked | Installation blocked |
|---|---:|---:|---:|---:|
| GenomeTools | 10 | 40 | 18 | 0 |
| GFF3toolkit | 6 | 44 | 18 | 0 |
| AGAT | 0 | 0 | 18 | 50 |

A rejected result means the configured tool reported at least one rule, including
QC warnings. An expected rejection passes the regression check only when its
exact rule set matches the profile. AGAT was not run; its blocked results are
neither successes nor expected format failures.

## Reproduce

```sh
just validity-install  # explicit network downloads into gitignored local/tools/
just validity-check   # read-only; also part of just check
just validity-report  # regenerate only after rule expectations match
```

Individual install targets are `validity-install-genometools` and
`validity-install-gff3toolkit`. Both verify a pinned SHA-256 before extraction.
No package is installed globally. GenomeTools uses upstream macOS arm64 or Linux
x86-64 binaries. GFF3toolkit uses the unmodified upstream source archive and
Python **3.11.15**, selected by `uv`; the local launcher calls the upstream
`gff3_QC` entry point. Its configured QC path needs only Python's standard library.
The installer does not run upstream `setup.py`, whose build hook downloads an
unverified BLAST 2.2.31 archive. The `-noncg` mode does not invoke BLAST.

The CI job installs the same two tools before `just check`. The macOS run is
measured here; the Linux execution remains a CI check. Missing tools, wrong
versions, crashes, timeouts, unknown GenomeTools errors, malformed QC output,
and even QC exit zero without its output file all fail. `just test` explicitly
skips the real-tool tests when either tool is missing; `validity-check` requires
both. GenomeTools retains its existing `GENOMETOOLS` executable override, with
version enforcement.

## Expected rules sit beside each profile

Each file under [model/validation/](../../model/validation/) names one conversion
contract or dialect as its `profile`, and its `validation` block lists the expected
failures by rule with explanations. The files sit outside
[model/profiles/](../../model/profiles/) so the contracts, whose checksums the
conversion report pins, change only when conversion does; every contract there must
still have a file here. Its `cases` map gives the
exact rule set for each named corpus input and validator. Empty lists mean no
reported rules are expected. BED12 and INSDC explicitly say these GFF3 commands
are not applicable; their empty rule catalogues do not claim a validation pass.
AGAT lists `expected_failures: null` because no measurement exists.

The Pfam examples belong to the protein-relative profile, the retained IMG
functional annotation belongs to the IMG profile, and the remaining GFF3 corpus
and negative controls belong to the general GFF3 validation cases. These case
assignments describe validation evidence, not conversion support. In particular,
a malformed control or circular RefSeq file need not satisfy the converter's
contract. The [IMG expectations](../../model/validation/img-functional-gff.yaml)
name the [dialect schema](../../model/dialects/img-functional-gff.yaml) they
describe, which is not a conversion contract. The JGI isolate functional roll-up
(`jgi-img-clostridium-functional-annotation`) is assigned there too; the other 20 JGI isolate GFF
files are general GFF3 cases. JGI files that stay under `local/jgi/` are outside the retained corpus.

Both report generation and checking reject unexpected rules and disappearing
expected rules. A file that still fails can therefore fail the regression check
for a new reason. Missing cases, stale cases, duplicate assignments, undeclared
rules, and unused rule declarations also fail. Report regeneration cannot accept
rule drift automatically. Review the source and diagnostics before deliberately
changing an expectation. The original derived-fixture `validity` labels still
constrain GenomeTools independently.

GenomeTools has no error IDs, so the adapter assigns narrow names to its observed
diagnostics, such as `missing-version` and `unresolved-parent`. Unrecognized
errors fail rather than becoming a generic expected rejection. GFF3toolkit
supplies its own codes, such as `Esf0014` for the missing version directive.
The report retains full GenomeTools output. QC diagnostics retain each code's
count and one example, plus a SHA-256 of **all** sorted diagnostic rows, so changes
to unshown occurrences still fail `validity-check`. Sorting removes traversal
order differences. Upstream writes temporary outputs in a fresh temporary
directory; the input file is never rewritten.

## What the measurements establish

GenomeTools rejects all six malformed controls and accepts all three valid edge
cases. GFF3toolkit rejects five malformed controls but accepts the dangling-parent
control in this configuration. Both accept the biologically wrong phase and
silently split Note controls. Tests repair the missing header of a real dialect
sample, introduce a new QC phase failure while GenomeTools still rejects its
header, and remove QC's strand complaint while the file still fails other rules.
All three changes fail for the intended added or disappearing rule.

Commands are `gt gff3validator FILE` and
`gff3_QC -g FILE -noncg -f /dev/null -o qc.tsv -s statistics.tsv`.
GenomeTools stops at its first error and does not run `-typecheck`. QC's
noncanonical mode omits canonical gene-model, phase-consistency, and BLAST
checks. `/dev/null` supplies no reference FASTA; this invocation does not measure
sequence bounds or biological correctness. Neither invocation validates Sequence
Ontology types. Consequently the known NMDC accession-valued type columns have
no measured ontology failure to expect here. Neither tool's acceptance establishes
conversion support or biological correctness.

QC also reports strand `.` as missing (`Esf0003`), empty source columns
(`Esf0022`), and commas in attributes (`Esf0036`). These are observed tool opinions,
not new restrictions on the dialects. Missing headers are preserved as observed
in the IMG and NMDC inputs.

The 21 JGI isolate GFF files, added on 2026-09-25 for
https://github.com/turbomam/feature-table-corpus/issues/53, brought five more observed rules.
GenomeTools rejects the Clostridium GeneMark file with `unsupported-version`, because it
declares `##gff-version 2`, and stops there, so it measures no later defect in that file.
QC reports the same header as `Esf0019`. The IMG pipeline 4.14.0 Bacillus file writes strand
as `1` in 2,062 rows and `-1` in 2,631; QC reports all 4,693 as `Esf0025` and as `Esf0003`.
That file also uses capitalized keys that GFF3 does not reserve (`Esf0041`). A key repeated
within one row is `Esf0032`. The Clostridium Prodigal file and, for GenomeTools only, the
`img_core_v400` Bacillus file are accepted.

## AGAT installation blocker

On **2026-09-25**, downloaded and SHA-256 checked the AGAT **1.7.0** source
archive and micromamba **2.9.0-0** macOS arm64 executable under `local/tools/`.
[agat-blocker.json](agat-blocker.json) records their URLs, hashes, exact probe
command, exit status and solver diagnostic. The native solve used only
`conda-forge` and `bioconda`, with user configuration disabled, and exited **1**:

```text
nothing provides perl-socket needed by perl-test-requiresinternet-0.05-pl5321hdfd78af_1
```

Read the package metadata and solver output: AGAT requires
`perl-lwp-protocol-https`, which requires `perl-test-requiresinternet`, which
requires the unavailable `perl-socket`. This blocks the tested native Bioconda
route. Read AGAT's `Makefile.PL`: its manual route declares unpinned Perl module
requirements; it does not supply a reproducible dependency lock to substitute.
Stopped this tool under the requested macOS arm64 exception in
https://github.com/turbomam/feature-table-corpus/issues/56. No AGAT install target,
runner, or measured rule expectations are claimed. No GPL code is tracked or
vendored. The blocker is explicit on every relevant report row on all platforms;
installing an arbitrary local AGAT cannot silently change this report.

## Upstream sources read

- [GenomeTools validator documentation](https://genometools.org/tools/gt_gff3validator.html)
  and [1.6.6 release](https://github.com/genometools/genometools/releases/tag/v1.6.6).
- GFF3toolkit 2.1.0's [QC command](https://github.com/NAL-i5K/GFF3toolkit/blob/v2.1.0/gff3tool/bin/gff3_QC.py),
  [rule definitions](https://github.com/NAL-i5K/GFF3toolkit/blob/v2.1.0/gff3tool/lib/ERROR/ERROR.py),
  and [build hook](https://github.com/NAL-i5K/GFF3toolkit/blob/v2.1.0/setup.py).
- [AGAT 1.7.0 prerequisites](https://github.com/NBISweden/AGAT/blob/v1.7.0/Makefile.PL)
  and [Bioconda package metadata](https://api.anaconda.org/package/bioconda/agat).

This report is separate from [conversion preservation](../conversion-roundtrips/README.md).
