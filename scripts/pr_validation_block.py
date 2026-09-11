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

    print("## Validation\n")
    print("```")
    print("uv run --with pyyaml python scripts/verify.py")
    print("uv run --with pyyaml python scripts/flat_profile_audit.py")
    print("```\n")

    verify = subprocess.run(
        ["uv", "run", "--quiet", "--with", "pyyaml", "python",
         os.path.join(ROOT, "scripts/verify.py")],
        capture_output=True, text=True, cwd=ROOT)
    last = [l for l in verify.stdout.splitlines() if l.strip()][-1:]
    tail = last[0] if last else "no output"

    print(f"{n} entries, {len(ids)} distinct ids, {tail.strip()}. "
          f"Exit status {verify.returncode}.\n")
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
