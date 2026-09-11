#!/usr/bin/env python3
"""Print the validation block for a pull request description.

This exists because the description drifted from the diff four times on one
pull request: entry counts, tier counts, generated-file counts and a claim
about which single change moved the total. Every one was a case of updating
the change and not the claim about the change.

So the claim is now generated. Run this, paste the output, push. It reads the
index rather than anything I remember.

Usage:
    uv run --with pyyaml python scripts/pr_validation_block.py [base-ref]

`base-ref` defaults to origin/main and is used only to report how many entries
the branch adds.
"""
import os, subprocess, sys, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(ref=None):
    if ref is None:
        return yaml.safe_load(open(os.path.join(ROOT, "corpus.yaml")))
    out = subprocess.run(["git", "-C", ROOT, "show", f"{ref}:corpus.yaml"],
                         capture_output=True, text=True)
    return yaml.safe_load(out.stdout) if out.returncode == 0 else None


def counts(doc):
    entries = doc["entries"]
    tiers = {}
    for e in entries:
        tiers[e.get("tier")] = tiers.get(e.get("tier"), 0) + 1
    return len(entries), tiers, {e["id"] for e in entries}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    now = load()
    n, tiers, ids = counts(now)
    before = load(base)

    # Run everything this block claims to have run. Listing a command without
    # executing it is how a generated artifact starts lying, which is the
    # failure this whole script was added to prevent.
    def run(rel):
        r = subprocess.run(["uv", "run", "--quiet", "--with", "pyyaml", "python",
                            os.path.join(ROOT, rel)],
                           capture_output=True, text=True, cwd=ROOT)
        last = [l for l in r.stdout.splitlines() if l.strip()][-1:]
        return r.returncode, (last[0].strip() if last else "no output")

    verify_rc, verify_tail = run("scripts/verify.py")
    audit_rc, audit_tail = run("scripts/flat_profile_audit.py")

    print("## Validation\n")
    print("```")
    print("uv run --with pyyaml python scripts/verify.py")
    print("uv run --with pyyaml python scripts/flat_profile_audit.py")
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
        print(f"\nCould not read corpus.yaml at `{base}`, so no comparison.")


if __name__ == "__main__":
    main()
