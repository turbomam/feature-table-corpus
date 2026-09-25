"""List, locate, and checksum JGI files that need a JGI login to download.

JGI Data Portal search is anonymous, but every file download needs a login, so
this repository cannot fetch these files itself. The manifest records exactly
which files the profiles use, and this script turns it into download URLs and
checks what a person has placed under local/jgi/.

    python3 scripts/jgi_inputs.py urls                  # print download URLs
    python3 scripts/jgi_inputs.py verify [--dir DIR]    # md5-check local copies
    python3 scripts/jgi_inputs.py collect               # refresh from the API

`collect` is the only command that uses the network. From the Data Portal
search API it rewrites three fields of each record: `name`,
`data_utilization_status` and `files`. Every other field is written by hand
and kept, including the `file_name_pattern` that selects the files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "model/examples/jgi-inputs.yaml"
LOCAL = ROOT / "local/jgi"
SEARCH = "https://files.jgi.doe.gov/search/"
DOWNLOAD = "https://files.jgi.doe.gov/filedownload"
PAGE_SIZE = 50  # the search API rejects larger pages with HTTP 400


def load(path=MANIFEST):
    with open(path) as handle:
        return yaml.safe_load(handle)


def download_url(record_file):
    name = urllib.parse.quote(record_file["name"])
    return f"{DOWNLOAD}/{record_file['file_id']}/{name}"


def local_path(record, record_file, base=LOCAL):
    return Path(base) / record["record_id"] / record_file["name"]


def md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def urls(manifest):
    for record in manifest["records"]:
        for record_file in record["files"]:
            print(f"{record['record_id']}\t{record_file['name']}\t{download_url(record_file)}")
    return 0


def verify(manifest, base=LOCAL):
    """Report each listed file as OK, MISSING, SIZE or MD5; fail on SIZE or MD5.

    Missing files are reported but do not fail, because nobody is expected to
    download every record. A present file with the wrong content always fails.
    """
    counts = {"OK": 0, "MISSING": 0, "SIZE": 0, "MD5": 0}
    for record in manifest["records"]:
        for record_file in record["files"]:
            path = local_path(record, record_file, base)
            if not path.exists():
                status = "MISSING"
            elif path.stat().st_size != record_file["bytes"]:
                status = "SIZE"
            elif md5(path) != record_file["md5"]:
                status = "MD5"
            else:
                status = "OK"
            counts[status] += 1
            print(f"{status:8}{record['record_id']}/{record_file['name']}")
    print("jgi-verify: " + ", ".join(f"{count} {status}" for status, count in counts.items()))
    return 1 if counts["SIZE"] or counts["MD5"] else 0


def search(query, page):
    params = urllib.parse.urlencode({"q": query, "x": PAGE_SIZE, "p": page})
    request = urllib.request.Request(f"{SEARCH}?{params}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


MAX_PAGES = 40


def find_record(record):
    page = 1
    for _ in range(MAX_PAGES):
        result = search(record["query"], page)
        for organism in result.get("organisms", []):
            if organism.get("id") == record["record_id"]:
                return organism
        following = result.get("next_page")
        if not following:
            raise LookupError(f"{record['record_id']} not found for query {record['query']!r}")
        if not isinstance(following, int) or following <= page:
            raise LookupError(f"search returned next_page {following!r} after page {page}")
        page = following
    raise LookupError(f"{record['record_id']} not found in {MAX_PAGES} pages of {record['query']!r}")


def merge_duplicates(record_id, matches):
    """Keep one entry per file name; the portal can list one file under several ids.

    Phytozome-167 lists its annotation table and GFF3 twice each, with the same
    name, size and md5 but different ids (seen 2026-09-25). Local copies are
    keyed by name, so identical duplicates collapse to the lowest id, with the
    others kept. Same name with different content is an error, not a choice.
    """
    by_name = {}
    for f in sorted(matches, key=lambda f: (f["file_name"], f["_id"])):
        entry = {"name": f["file_name"], "file_id": f["_id"], "bytes": f["file_size"],
                 "md5": f["md5sum"], "status_when_collected": f["file_status"]}
        kept = by_name.get(entry["name"])
        if kept is None:
            by_name[entry["name"]] = entry
        elif (kept["md5"], kept["bytes"]) == (entry["md5"], entry["bytes"]):
            kept.setdefault("duplicate_file_ids", []).append(entry["file_id"])
        else:
            raise ValueError(f"{record_id}: {entry['name']} is listed with different content "
                             f"under {kept['file_id']} and {entry['file_id']}")
    return list(by_name.values())


def collect(manifest, path=MANIFEST):
    for record in manifest["records"]:
        organism = find_record(record)
        pattern = re.compile(record["file_name_pattern"])
        matches = [f for f in organism.get("files", []) if pattern.fullmatch(f["file_name"])]
        files = merge_duplicates(record["record_id"], matches)
        if not files:
            raise LookupError(f"{record['record_id']}: no file matches {record['file_name_pattern']!r}")
        record["name"] = organism["name"]
        record["data_utilization_status"] = organism.get("data_utilization_status")
        record["files"] = files
        print(f"{record['record_id']}: {len(files)} files", file=sys.stderr)
    with open(path, "w") as handle:
        yaml.safe_dump(manifest, handle, sort_keys=False, allow_unicode=True, width=100)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("urls", help="print download URLs")
    verifier = commands.add_parser("verify", help="md5-check files under local/jgi/")
    verifier.add_argument("--dir", type=Path, default=LOCAL)
    commands.add_parser("collect", help="refresh file lists from the search API")
    args = parser.parse_args(argv)
    manifest = load(args.manifest)
    if args.command == "urls":
        return urls(manifest)
    if args.command == "verify":
        return verify(manifest, args.dir)
    return collect(manifest, args.manifest)


if __name__ == "__main__":
    sys.exit(main())
