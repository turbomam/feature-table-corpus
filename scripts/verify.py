#!/usr/bin/env python3
"""Verify the corpus: vendored checksums, then link liveness.

Usage:
    uv run --with pyyaml python scripts/verify.py            # checksums only
    uv run --with pyyaml python scripts/verify.py --links    # also HEAD every URL

Exit status is non-zero if any vendored file is missing or its checksum moved,
so this can gate a merge. Link checks never fail the run: a dead upstream URL
is a fact to record, not a defect in this repository.
"""
import argparse, hashlib, os, sys, urllib.request, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_vendored(entries):
    bad = 0
    for e in (x for x in entries if x["tier"] == "vendored"):
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
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "curl/8.7.1"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"{r.status}  {e['id']}  {url}")
        except Exception as exc:
            print(f"---  {e['id']}  {url}  ({exc})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", action="store_true", help="also HEAD every origin_url")
    args = ap.parse_args()
    entries = yaml.safe_load(open(os.path.join(ROOT, "corpus.yaml")))["entries"]
    bad = check_vendored(entries)
    if args.links:
        print()
        check_links(entries)
    print(f"\n{bad} problem(s) in vendored files")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
