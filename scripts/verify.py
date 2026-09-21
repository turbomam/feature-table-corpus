#!/usr/bin/env python3
"""Verify the corpus: index invariants, vendored checksums, then link liveness.

Usage:
    uv run --with pyyaml python scripts/verify.py            # index + checksums
    uv run --with pyyaml python scripts/verify.py --links    # also check every URL

Exit status is non-zero if an index invariant is broken or a vendored file is
missing or changed, so this can gate a merge. Link checks never fail the run:
a dead upstream URL is a fact to record, not a defect in this repository.
"""
import argparse, hashlib, os, sys, urllib.request, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


REQUIRED_ALWAYS = ("id", "label", "tier", "source", "license", "retrieved")
REQUIRED_BY_TIER = {
    "vendored": ("path", "bytes", "md5", "origin_url"),
    "derived": ("path", "bytes", "md5", "origin_url", "derived_from", "mutation",
                "validity"),
    "linked": ("origin_url",),
    "restricted": ("origin_url",),
    "not located": (),
}


def check_index(entries):
    """Enforce the invariants the index relies on.

    This exists because a previous release claimed id uniqueness was asserted
    while nothing in the repository checked it, so two entries collided on
    "nmdc-annotation" and every check still passed. A claimed invariant that
    no check enforces is worse than no invariant, because it is trusted.
    """
    bad = 0
    seen_ids, seen_paths, seen_urls = {}, {}, {}
    for e in entries:
        eid = e.get("id", "<missing id>")

        if eid in seen_ids:
            print(f"DUPLICATE-ID    {eid}  also used by entry {seen_ids[eid]}")
            bad += 1
        seen_ids[eid] = eid

        p = e.get("path")
        if p:
            if p in seen_paths:
                print(f"DUPLICATE-PATH  {p}  claimed by {seen_paths[p]} and {eid}")
                bad += 1
            seen_paths[p] = eid

        # Duplicate origin_url means one artifact indexed under two identities,
        # which inflates the counts. Derived entries legitimately share one URL,
        # the generator that produces them, so they are exempt.
        u = e.get("origin_url")
        if u and e.get("tier") != "derived":
            if u in seen_urls:
                print(f"DUPLICATE-URL   {u}\n"
                      f"                claimed by {seen_urls[u]} and {eid}")
                bad += 1
            seen_urls[u] = eid

        tier = e.get("tier")
        if tier not in REQUIRED_BY_TIER:
            print(f"UNKNOWN-TIER    {eid}  tier={tier!r}")
            bad += 1
            continue

        missing = [f for f in REQUIRED_ALWAYS + REQUIRED_BY_TIER[tier]
                   if not e.get(f)]
        if missing:
            print(f"MISSING-FIELDS  {eid}  ({tier})  {', '.join(missing)}")
            bad += 1

    print(f"index: {len(entries)} entries, {len(seen_ids)} distinct ids, "
          f"{bad} invariant problem(s)")
    return bad


SOURCED_DIRS = ("corpus/sources/nmdc", "corpus/sources/ncbi-refseq")
PROVENANCE_TAGS = ("# derived-from: ", "# single-change: ", "# validity: ")


def check_separation(entries):
    """Keep sourced files byte-faithful and derived files self-identifying.

    The corpus makes one promise above all others: a file under a sourced
    directory is exactly what its origin served. The derived fixtures carry
    four appended provenance comments, which is acceptable only because those
    files are never mistaken for sourced ones. This pass enforces both halves
    so that stays true rather than merely being intended.
    """
    bad = 0

    # No sourced file may carry a provenance comment, because that would mean
    # something in this repository had written into it.
    for e in entries:
        p = e.get("path")
        if not p or not p.startswith(SOURCED_DIRS):
            continue
        full = os.path.join(ROOT, p)
        if not os.path.exists(full):
            continue
        text = open(full, errors="replace").read()
        hits = [t.strip() for t in PROVENANCE_TAGS if t in text]
        if hits:
            print(f"SOURCED-EDITED  {p}  carries {', '.join(hits)}")
            bad += 1
        if e.get("tier") == "derived":
            print(f"MISFILED        {p}  is tier 'derived' but sits in a sourced directory")
            bad += 1

    # Every derived file must say what it came from and what was done to it.
    for e in entries:
        if e.get("tier") != "derived":
            continue
        p = e.get("path")
        if not p:
            continue
        if p.startswith(SOURCED_DIRS):
            continue  # already reported above
        full = os.path.join(ROOT, p)
        if not os.path.exists(full):
            continue
        text = open(full, errors="replace").read()
        missing = [t.strip() for t in PROVENANCE_TAGS if t not in text]
        if missing:
            print(f"NO-PROVENANCE   {p}  missing {', '.join(missing)}")
            bad += 1

    n_src = sum(1 for e in entries if (e.get("path") or "").startswith(SOURCED_DIRS))
    n_der = sum(1 for e in entries if e.get("tier") == "derived")
    print(f"separation: {n_src} sourced files unwritten, {n_der} derived files "
          f"self-identifying, {bad} problem(s)")
    return bad


def check_readme(doc):
    """Fail when the README's advertised counts drift from the index.

    Stale counts have been a review finding twice: "eleven specifications" when
    there were twelve, and "48 entries" after a split took it to 51. The index
    is the source of truth, so the prose has to be checked against it rather
    than maintained by hand.
    """
    import re
    path = os.path.join(ROOT, "README.md")
    if not os.path.exists(path):
        print("README missing")
        return 1
    text = open(path).read()
    bad = 0

    # Counts are DERIVED from the entries, never read from the summary fields.
    # Comparing the README against entry_count and tier_counts would let a new
    # entry pass while the summaries and the README were both stale, which is
    # the exact failure this pass exists to prevent.
    entries = doc["entries"]
    derived_total = len(entries)
    derived_tiers = {}
    for e in entries:
        derived_tiers[e.get("tier")] = derived_tiers.get(e.get("tier"), 0) + 1

    if doc.get("entry_count") != derived_total:
        print(f"STALE-SUMMARY   entry_count says {doc.get('entry_count')}, "
              f"entries number {derived_total}")
        bad += 1
    if doc.get("tier_counts") != derived_tiers:
        print(f"STALE-SUMMARY   tier_counts {doc.get('tier_counts')} "
              f"disagrees with the entries {derived_tiers}")
        bad += 1

    m = re.search(r"(\d+) entries in (?:two|three|four|five|six) tiers", text)
    if not m:
        print("README does not state a total entry count in the expected form")
        bad += 1
    elif int(m.group(1)) != derived_total:
        print(f"README-COUNT    total: README says {m.group(1)}, entries number {derived_total}")
        bad += 1

    for tier, n in derived_tiers.items():
        row = re.search(rf"\|\s*{re.escape(tier)}\s*\|\s*(\d+)\s*\|", text)
        if not row:
            print(f"README-COUNT    tier {tier!r} has no row in the README table")
            bad += 1
        elif int(row.group(1)) != n:
            print(f"README-COUNT    tier {tier}: README says {row.group(1)}, index has {n}")
            bad += 1

    specs = sum(1 for e in entries if e.get("kind") == "specification")
    words = {"eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "ten": 10, "nine": 9}
    m = re.search(r"(\w+) specifications are recorded", text)
    if m and words.get(m.group(1).lower()) not in (None, specs):
        print(f"README-COUNT    specifications: README says {m.group(1)}, index has {specs}")
        bad += 1

    print(f"readme: counts checked against the index, {bad} mismatch(es)")
    return bad


def check_vendored(entries):
    bad = 0
    for e in (x for x in entries if x.get("tier") in ("vendored", "derived")):
        # Guard EVERY field this pass reads, not only path. An entry that
        # check_index already rejected can be missing any of them, and
        # indexing one here would replace a clean nonzero report with a
        # traceback that hides every later entry.
        missing = [k for k in ("id", "path", "md5", "bytes") if not e.get(k)]
        if missing:
            print(f"NO-METADATA  {e.get('id', '<missing id>')}  "
                  f"missing {', '.join(missing)}  (already reported above)")
            bad += 1
            continue
        p = os.path.join(ROOT, e["path"])
        if not os.path.exists(p):
            print(f"MISSING   {e['id']}  {e['path']}")
            bad += 1
            continue
        raw = open(p, "rb").read()
        got = hashlib.md5(raw).hexdigest()
        if got != e["md5"]:
            print(f"CHANGED   {e['id']}  recorded {e['md5']} got {got}")
            bad += 1
        elif len(raw) != e["bytes"]:
            print(f"SIZE      {e['id']}  recorded {e['bytes']} got {len(raw)}")
            bad += 1
        else:
            print(f"ok        {e['id']}  {len(raw)} bytes")
    return bad


def check_links(entries):
    # A plain urlopen is refused by some of these hosts, so send a browser-ish
    # user agent. Without it the NMDC API answers 403 and the link looks dead.
    for e in entries:
        url = e.get("origin_url")
        if not url:
            continue
        eid = e.get("id", "<missing id>")
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "curl/8.7.1"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    note = "" if method == "HEAD" else "  (GET; HEAD not allowed)"
                    print(f"{r.status}  {eid}  {url}{note}")
                break
            except urllib.error.HTTPError as exc:
                # Some endpoints answer 405 to HEAD and 200 to GET. Retrying with
                # GET keeps a live URL from being reported as dead.
                if exc.code == 405 and method == "HEAD":
                    continue
                print(f"{exc.code}  {eid}  {url}")
                break
            except Exception as exc:
                print(f"---  {eid}  {url}  ({exc})")
                break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", action="store_true", help="also HEAD every origin_url")
    args = ap.parse_args()
    doc = yaml.safe_load(open(os.path.join(ROOT, "corpus/index.yaml")))
    entries = doc["entries"]
    bad = check_index(entries)
    print()
    bad += check_separation(entries)
    print()
    bad += check_readme(doc)
    print()
    bad += check_vendored(entries)
    if args.links:
        print()
        check_links(entries)
    print(f"\n{bad} problem(s) total")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
