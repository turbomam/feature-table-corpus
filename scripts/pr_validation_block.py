#!/usr/bin/env python3
"""Print the validation block for a pull request description.

This exists because the description drifted from the diff four times on one
pull request: entry counts, tier counts, generated-file counts and a claim
about which single change moved the total. Every one was a case of updating
the change and not the claim about the change.

So the claim is now generated. Run this, paste the output, push. It reads the
index rather than anything I remember.

Usage:
    uv run --with pyyaml python scripts/pr_validation_block.py [base-ref] [--audit-source path-or-url]

`base-ref` defaults to origin/main and is used only to report how many entries
the branch adds.
"""
import argparse
import os
import shlex
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(ref=None):
    if ref is None:
        return yaml.safe_load(open(os.path.join(ROOT, "corpus/index.yaml")))
    # Comparisons may cross the artifact-layout migration.
    for path in ('corpus/index.yaml', 'corpus.yaml'):
        out = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:{path}"],
                             capture_output=True, text=True)
        if out.returncode == 0:
            return yaml.safe_load(out.stdout)
    return None


def counts(doc):
    entries = doc["entries"]
    tiers = {}
    for e in entries:
        tiers[e.get("tier")] = tiers.get(e.get("tier"), 0) + 1
    return len(entries), tiers, {e["id"] for e in entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_ref', nargs='?', default='origin/main')
    parser.add_argument('--audit-source', help='Local schema or URL; default is the pinned upstream GFF schema')
    args = parser.parse_args()
    base = args.base_ref
    now = load()
    n, tiers, ids = counts(now)
    before = load(base)

    # Run everything this block claims to have run. Listing a command without
    # executing it is how a generated artifact starts lying, which is the
    # failure this whole script was added to prevent.
    def run(command):
        r = subprocess.run(command,
                           capture_output=True, text=True, cwd=ROOT)
        output = r.stderr if r.returncode and r.stderr.strip() else r.stdout
        last = [l for l in output.splitlines() if l.strip()][-1:]
        return r.returncode, (last[0].strip() if last else "no output")

    verify_command = ["uv", "run", "--with", "pyyaml", "python", "scripts/verify.py"]
    audit_command = ["uv", "run", "--with", "linkml-runtime", "python", "scripts/flat_profile_audit.py"]
    if args.audit_source:
        audit_command.append(args.audit_source)
    verify_rc, verify_tail = run(verify_command)
    audit_rc, audit_tail = run(audit_command)

    print("## Validation\n")
    print("```")
    print(shlex.join(verify_command))
    print(shlex.join(audit_command))
    print("```\n")
    print(f"| command | exit | last line |")
    print(f"|---|---|---|")
    print(f"| `verify.py` | {verify_rc} | {verify_tail} |")
    print(f"| `flat_profile_audit.py` | {audit_rc} | {audit_tail} |")
    print()
    if verify_rc or audit_rc:
        print("**One of these failed. Do not paste this block until it passes.**\n")
    print(f"{n} entries, {len(ids)} distinct ids.\n")
    print("| tier | count |")
    print("|---|---|")
    for t, c in sorted(tiers.items(), key=lambda x: -x[1]):
        print(f"| {t} | {c} |")

    if before:
        bn, btiers, bids = counts(before)
        added = sorted(ids - bids)
        removed = sorted(bids - ids)
        print(f"\nAgainst `{base}`: {bn} entries before, {n} after.")
        if added:
            print(f"\nAdds {len(added)}: " + ", ".join(f"`{a}`" for a in added))
        if removed:
            print(f"\nRemoves {len(removed)}: " + ", ".join(f"`{r}`" for r in removed))
        if not added and not removed:
            print("\nNo index entries added or removed.")
    else:
        print(f"\nCould not read corpus/index.yaml at `{base}`, so no comparison.")
    return 1 if verify_rc or audit_rc else 0


if __name__ == "__main__":
    sys.exit(main())
