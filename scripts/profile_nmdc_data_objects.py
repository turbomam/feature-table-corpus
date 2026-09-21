#!/usr/bin/env python3
"""Collect and report NMDC DataObject categories and URL hosts, independently of the draft model.

uv run --with linkml-runtime python scripts/profile_nmdc_data_objects.py collect
uv run --offline --with linkml-runtime python scripts/profile_nmdc_data_objects.py render

Only public NMDC metadata is read. Source projection and schema stay in local/;
the publishable outputs contain schema definitions and aggregate counts.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from linkml_runtime.utils.schemaview import SchemaView

API = "https://api.microbiomedata.org"
COLLECTION = "data_object_set"
SCHEMA_RELEASE = "11.23.0"
SCHEMA_COMMIT = "84651fe32b2e2f783f5d38ef5b8757d90c5ab768"
SCHEMA_URL = (f"https://raw.githubusercontent.com/microbiomedata/nmdc-schema/{SCHEMA_COMMIT}"
              "/nmdc_schema/nmdc_materialized_patterns.yaml")
EXTRA_CATEGORIES = {
    "compression_type": "Open string describing compression; profiled as categorical, not an enum",
    "type": "Class discriminator; profiled as categorical, not an enum",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_bytes(url, accept="*/*"):
    for attempt in range(4):
        try:
            # Match the existing NMDC harvester's compatibility convention.
            headers = {"User-Agent": "curl/8.7.1 feature-table-corpus-nmdc-profile/1", "Accept": accept}
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def get_json(url):
    return json.loads(get_bytes(url, accept="application/json"))


def dump_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def collection_count():
    stats = get_json(API + "/nmdcschema/collection_stats")
    return next(s["storageStats"]["count"] for s in stats if s["ns"] == "nmdc." + COLLECTION)


def catalogue(schema_path):
    view = SchemaView(str(schema_path))
    slots = []
    for slot in view.class_induced_slots("DataObject"):
        enum = view.all_enums().get(slot.range)
        if enum is None and slot.name not in EXTRA_CATEGORIES and slot.range != "boolean":
            continue
        slots.append({
            "name": slot.name, "range": slot.range,
            "required": bool(slot.required), "multivalued": bool(slot.multivalued),
            "description": slot.description,
            "basis": "Schema enum" if enum else EXTRA_CATEGORIES.get(slot.name, "Boolean category"),
            "permitted_values": sorted(enum.permissible_values) if enum else None,
        })
    return {"class": "nmdc:DataObject", "embedded_schema_version": view.schema.version,
            "slots": sorted(slots, key=lambda s: s["name"])}


def collect(work):
    work.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    api_version = get_json(API + "/nmdcschema/version")
    if api_version != SCHEMA_RELEASE:
        raise ValueError(f"API schema is {api_version}; update and pin the schema source before collecting")
    schema_bytes = get_bytes(SCHEMA_URL)
    schema_path = work / "nmdc-schema.yaml"
    schema_path.write_bytes(schema_bytes)
    categories = catalogue(schema_path)
    fields = [s["name"] for s in categories["slots"]] + ["url"]
    before = collection_count()
    params = {"max_page_size": 1000, "projection": ",".join(fields)}
    seen_ids, seen_tokens = set(), set()
    pages = 0
    raw_part = work / "data-objects.jsonl.part"
    with raw_part.open("w") as out:
        while True:
            page = get_json(API + "/nmdcschema/" + COLLECTION + "?" + urlencode(params))
            rows = page["resources"]
            for row in rows:
                identifier = row["id"]
                if identifier in seen_ids:
                    raise ValueError(f"Duplicate DataObject id during pagination: {identifier}")
                seen_ids.add(identifier)
                out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            pages += 1
            if pages % 20 == 0:
                print(f"Read {len(seen_ids):,} DataObjects in {pages} pages", flush=True)
            token = page.get("next_page_token")
            if not token:
                break
            if token in seen_tokens or not rows:
                raise ValueError("Non-advancing pagination; refusing to publish a partial profile")
            seen_tokens.add(token)
            params["page_token"] = token
    after = collection_count()
    if before != after or len(seen_ids) != after:
        raise ValueError(f"Coverage changed or is incomplete: before={before}, after={after}, read={len(seen_ids)}")
    final_version = get_json(API + "/nmdcschema/version")
    if final_version != api_version:
        raise ValueError("API schema version changed during collection")
    raw_path = work / "data-objects.jsonl"
    raw_part.replace(raw_path)
    with raw_path.open("rb") as source:
        projection_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    provenance = {
        "scope": "Only the public NMDC data_object_set collection; one inspiration for broader modeling",
        "api": API, "collection": COLLECTION, "filter": {}, "projection": fields,
        "started_at": started, "completed_at": utc_now(), "pages": pages,
        "records": len(seen_ids), "collection_count_before": before, "collection_count_after": after,
        "schema_release": api_version, "schema_commit": SCHEMA_COMMIT, "schema_url": SCHEMA_URL,
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "projection_sha256": projection_sha256,
        "coverage": "Pagination exhausted; unique IDs and counts agree before/after; not a transactional snapshot",
    }
    dump_json(work / "provenance.json", provenance)
    print(f"Collected all {len(seen_ids):,} NMDC DataObjects", flush=True)


def value_state(record, name):
    if name not in record:
        return "missing"
    if record[name] is None:
        return "null"
    if record[name] == "":
        return "empty_string"
    return "present"


def url_host(value):
    """Return a normalized hostname; do not infer schemes for relative/bare URLs."""
    if not isinstance(value, str):
        return None
    if any(c.isspace() for c in value):
        return None
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc or not parts.hostname:
            return None
        # Access validates numeric ports and malformed IPv6 authorities.
        parts.port
        return parts.hostname.lower()
    except ValueError:
        return None


def profile_records(categories, records):
    slots = {s["name"]: {"states": Counter(), "values": Counter()} for s in categories["slots"]}
    hosts, url_states, ids = Counter(), Counter(), set()
    total = 0
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("Each DataObject projection needs a string id")
        if row["id"] in ids:
            raise ValueError("Duplicate DataObject id")
        ids.add(row["id"])
        total += 1
        for definition in categories["slots"]:
            name = definition["name"]
            entry = slots[name]
            state = value_state(row, name)
            if state == "present":
                value = row[name]
                values = value if definition["multivalued"] else [value]
                expected_type = bool if definition["range"] == "boolean" else str
                if not isinstance(values, list) or any(type(v) is not expected_type for v in values):
                    state = "invalid_type"
                elif not values:
                    state = "empty_list"
                elif any(v == "" for v in values):
                    state = "empty_item"
                else:
                    # Counts are DataObjects carrying each value, not repeated occurrences.
                    # String labels keep boolean keys consistent across JSON and CSV.
                    entry["values"].update({str(v).lower() if type(v) is bool else v for v in values})
            entry["states"][state] += 1
        state = value_state(row, "url")
        if state == "present":
            host = url_host(row["url"])
            if host is None:
                state = "invalid_or_hostless" if isinstance(row["url"], str) else "invalid_type"
            else:
                hosts[host] += 1
        url_states[state] += 1
    result = {"records": total, "slots": {}, "url": {
        "states": dict(sorted(url_states.items())), "distinct_hosts": len(hosts),
        "hosts": dict(sorted(hosts.items(), key=lambda p: (-p[1], p[0]))),
    }}
    for definition in categories["slots"]:
        name, allowed = definition["name"], definition["permitted_values"]
        values = slots[name]["values"]
        result["slots"][name] = {
            "states": dict(sorted(slots[name]["states"].items())),
            "distinct_observed_values": len(values),
            "values": dict(sorted(values.items(), key=lambda p: (-p[1], str(p[0])))),
            "observed_outside_enum": sorted(set(values) - set(allowed)) if allowed is not None else None,
        }
    return result


def render(work, output):
    provenance = json.loads((work / "provenance.json").read_text())
    raw_path, schema_path = work / "data-objects.jsonl", work / "nmdc-schema.yaml"
    for path, key in ((raw_path, "projection_sha256"), (schema_path, "schema_sha256")):
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != provenance[key]:
                raise ValueError(f"Input checksum changed: {path}")
    categories = catalogue(schema_path)
    with raw_path.open() as source:
        counts = profile_records(categories, (json.loads(line) for line in source))
    if counts["records"] != provenance["records"]:
        raise ValueError("Projection count disagrees with collection provenance")
    output.mkdir(parents=True, exist_ok=True)
    dump_json(output / "catalogue.json", {"schema": provenance, **categories})
    dump_json(output / "counts.json", {"provenance": provenance, **counts})
    with (output / "categorical-values.csv").open("w", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["slot", "value", "data_objects", "schema_permitted"])
        for slot in categories["slots"]:
            values = counts["slots"][slot["name"]]["values"]
            allowed = slot["permitted_values"]
            for value in sorted(set(values) | set(allowed or []), key=str):
                writer.writerow([slot["name"], value, values.get(value, 0),
                                 "not_enumerated" if allowed is None else str(value in allowed).lower()])
    with (output / "url-hosts.csv").open("w", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["hostname", "data_objects"])
        writer.writerows(counts["url"]["hosts"].items())
    lines = ["# NMDC DataObject profile", "",
             "This catalogue describes **NMDC DataObjects only**. NMDC is one source of evidence",
             "for the broader feature/attribute modeling work. These fields, vocabularies, hosts,",
             "and frequencies are not requirements of the proposed general model.", "",
             f"Collected {provenance['completed_at']} from the [public NMDC API]({provenance['api']}).",
             f"Coverage: **{counts['records']:,} DataObjects**, all {provenance['pages']} pages of",
             f"`{provenance['collection']}`, without a feature-file or workflow filter. Unique IDs and the",
             "collection counts before/after agree. This traversal is not a transactional snapshot;",
             "unchanged totals cannot prove that no individual record changed during collection.", "",
             f"Schema release: **{provenance['schema_release']}**, [commit {provenance['schema_commit'][:12]}]"
             f"(https://github.com/microbiomedata/nmdc-schema/tree/{provenance['schema_commit']}).",
             f"The release's merged YAML embeds version `{categories['embedded_schema_version']}`; the release, commit, URL, and",
             "SHA-256 in the JSON provenance identify the actual source used.", "",
             "## Categorical slots", "",
             "Schema enums and booleans are discovered from DataObject's induced slots, including",
             "inheritance. `compression_type` and the `type` class discriminator are explicitly",
             "included as categorical strings; neither is falsely labeled an enum. Free-text names,",
             "descriptions, identifiers, references, sizes, and checksums are not categorical slots.", "",
             "| Slot | Range | Required | Allowed enum values | Observed distinct values | Present | Missing | Null | Empty string | Invalid type |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for slot in categories["slots"]:
        result = counts["slots"][slot["name"]]
        states = result["states"]
        allowed = "not enumerated" if slot["permitted_values"] is None else len(slot["permitted_values"])
        cells = [slot["name"], slot["range"], str(slot["required"]).lower(), allowed,
                 result["distinct_observed_values"]] + [states.get(k, 0) for k in
                    ("present", "missing", "null", "empty_string", "invalid_type")]
        lines.append("| " + " | ".join(map(str, cells)) + " |")
    lines += ["", "[categorical-values.csv](categorical-values.csv) lists each value and its DataObject",
              "count, including permitted-but-unobserved enum values with zero counts. Unknown enum",
              "values remain visible. Missing, null, empty, and invalid types are separate states in",
              "[counts.json](counts.json); these are not counted as distinct categorical values.", "",
              "Counts measure records carrying a value; duplicate values in a multivalued slot would",
              "count once per record. A multivalued slot's frequencies need not sum to the record total.",
              "Empty lists and lists containing empty strings are recorded as `empty_list` and",
              "`empty_item`; neither contributes categorical counts. All slots in this release are scalar.", "",
              "## URL hosts", "",
              "Hosts are parsed from the URL authority after the scheme and before the path, then",
              "lowercased. Ports and user information are excluded; IPv6 hosts are supported.",
              "Missing, null, empty, malformed, and hostless values remain separate. Bare paths or",
              "bare domains are not silently treated as HTTP URLs. Counts describe metadata records,",
              "not files fetched, host availability, or distinct URLs.", "",
              "| Hostname | DataObjects |", "|---|---:|"]
    lines += [f"| `{host}` | {count:,} |" for host, count in counts["url"]["hosts"].items()]
    lines += ["", f"Distinct hosts: **{counts['url']['distinct_hosts']}**.", "",
              "URL states: " + ", ".join(f"{k}: {v:,}" for k,v in counts["url"]["states"].items()) + ".", "",
              "[url-hosts.csv](url-hosts.csv) provides the same host counts as CSV.", "",
              "## Reproduction and interpretation", "",
              "Run from the repository root:", "", "```sh",
              "uv run --with linkml-runtime python scripts/profile_nmdc_data_objects.py collect",
              "uv run --offline --with linkml-runtime python scripts/profile_nmdc_data_objects.py render",
              "```", "",
              "`collect` refreshes the public metadata projection and verifies completeness before",
              "publishing aggregates. `render` recreates them offline from the checksum-verified",
              "files under gitignored `local/nmdc-profile/`. No data files referenced by the URLs",
              "are downloaded. The script is pinned to the API schema release above and refuses",
              "a different release until its schema source is updated. A later collection may have",
              "different counts; each report carries its own timestamps and content hashes.", "",
              "Python 3.11 or later is required. Run `collect` online once to obtain the projection",
              "and schema and populate uv's dependency cache. The documented `render` command uses",
              "uv's `--offline` mode as well as making no API calls; it needs those cached dependencies.", "",
              "The catalogue is derived from the [NMDC schema source](" + provenance['schema_url'] + "),",
              "licensed CC0. [NMDC's data use policy](https://microbiomedata.org/nmdc-data-use-policy/)",
              "applies to the source metadata. This is descriptive source profiling, not validation",
              "of every NMDC schema constraint or a universal feature-table vocabulary."]
    (output / "README.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote NMDC-only catalogue and counts to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect", "render"))
    parser.add_argument("--work-dir", type=Path, default=Path("local/nmdc-profile"))
    parser.add_argument("--output", type=Path, default=Path("analyses/nmdc-data-objects"))
    args = parser.parse_args()
    if args.command == "collect":
        collect(args.work_dir)
    render(args.work_dir, args.output)


if __name__ == "__main__":
    main()
