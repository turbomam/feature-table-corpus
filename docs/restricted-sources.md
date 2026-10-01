# Excerpts of login-only sources

A `derived` corpus entry may be built from a `restricted` source, one behind a login, such as the
two Populus trichocarpa v4.1 excerpts from JGI Phytozome. Mark accepted this on 2026-10-01
(https://github.com/turbomam/feature-table-corpus/pull/145). The next restricted source may have
weaker terms, so each one is decided on its own, with
https://github.com/turbomam/feature-table-corpus/issues/152 as the reason for this page.

Before adding an excerpt of a restricted source:

1. Read the terms that govern this exact file, not the provider in general: the data release or
   use policy for its project and date, and any per-record label. A provider can mix public,
   use-restricted and embargoed records. JGI's use-restricted data, for example, need the
   proposal PI's permission before redistribution.
2. Confirm that the terms allow redistributing a subset, and say what they require: citations,
   acknowledgments, or keeping a license notice. If they don't clearly allow it, don't vendor the
   excerpt. Keep the source as a `restricted` entry only.
3. Record the source as a `restricted` entry with its provider file ID, file name, bytes and md5,
   so the excerpt can only be rebuilt from that exact file.
4. Give the `derived` entry a `redistribution_basis`: `terms`, the https URLs read; `read`, the
   date they were read; and `allows`, what they permit and who accepted it. `scripts/verify.py`
   refuses a derived entry from a restricted source without one.
5. Put the required citations in `corpus/derived-examples/README.md` and the entry's `license`.
6. Write the excerpt with a script that checks the source's md5 first, as
   `scripts/populus_excerpt.py` does, and add a dated note to `corpus/PROVENANCE.md`.

Known limits of this rule are tracked separately:
- the excerpt can't be rebuilt in CI (https://github.com/turbomam/feature-table-corpus/issues/148);
- terms or file IDs may change later (https://github.com/turbomam/feature-table-corpus/issues/149);
- citations don't yet travel with outputs made from an excerpt
  (https://github.com/turbomam/feature-table-corpus/issues/151).
