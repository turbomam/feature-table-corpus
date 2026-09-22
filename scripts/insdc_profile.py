"""Bounded GenBank feature-table conversion, with explicit ordered locations."""
import re
import textwrap

from convert_features import require, dataset_validator, source_validator
from source_document import parse_bytes
from validate_closed import validation_errors

PROFILE = "insdc-locations/1.0.0"


def split_arguments(text):
    depth, start, pieces = 0, 0, []
    for i, character in enumerate(text):
        depth += (character == "(") - (character == ")")
        require(depth >= 0, "location-syntax", "unbalanced location parentheses")
        if character == "," and depth == 0:
            pieces.append(text[start:i]); start = i + 1
    require(depth == 0, "location-syntax", "unbalanced location parentheses")
    return pieces + [text[start:]]


def parse_location(text, seqid, *, depth=0):
    require(depth < 4, "unsupported-location", "location nesting exceeds this profile")
    if text.startswith("complement(") and text.endswith(")"):
        location = parse_location(text[11:-1], seqid, depth=depth + 1)
        location["parts"].reverse()
        for part in location["parts"]:
            part["strand"] = "-" if part["strand"] == "+" else "+"
        return location
    match = re.fullmatch(r"(join|order)\((.+)\)", text)
    if match:
        parts = []
        for argument in split_arguments(match[2]):
            child = parse_location(argument, seqid, depth=depth + 1)
            require(child["location_operator"] == "single", "unsupported-location", "nested join/order is outside this profile")
            parts.extend(child["parts"])
        require(len(parts) >= 2, "location-syntax", "join/order needs at least two parts")
        return {"location_operator": match[1], "parts": parts}
    match = re.fullmatch(r"([<>]?)([1-9][0-9]*)(?:\.\.([<>]?)([1-9][0-9]*))?", text)
    require(match is not None, "unsupported-location", f"unsupported location descriptor: {text!r}")
    statuses = {"": "exact", "<": "before", ">": "after"}
    start, end = int(match[2]), int(match[4] or match[2])
    return {"location_operator": "single", "parts": [{"seqid": seqid, "start": start, "end": end,
             "start_status": statuses[match[1]], "end_status": statuses[match[3] if match[4] else match[1]], "strand": "+"}]}


def quoted_value(text):
    """Return a complete INSDC quoted value, or None while it continues."""
    require(text.startswith('"'), "qualifier-syntax", "expected quoted qualifier")
    result, i = [], 1
    while i < len(text):
        if text[i] == '"':
            if i + 1 < len(text) and text[i + 1] == '"':
                result.append('"'); i += 2
                continue
            require(i == len(text) - 1, "qualifier-syntax", "text follows closing quote")
            return "".join(result)
        result.append(text[i]); i += 1
    return None


def parse_feature(lines, feature_id, seqid, topology):
    kind, location_text = lines[0][5:21].strip(), lines[0][21:].strip()
    i = 1
    while i < len(lines) and not lines[i][21:].lstrip().startswith("/"):
        location_text += lines[i][21:].strip(); i += 1
    location = parse_location(location_text, seqid)
    strands = {p["strand"] for p in location["parts"]}
    require(len(strands) == 1, "unsupported-location", "mixed-strand joins require another profile")
    strand = next(iter(strands))
    parts = location["parts"]
    location["crosses_origin"] = any((b["start"] < a["start"] if strand == "+" else b["start"] > a["start"])
                                     for a, b in zip(parts, parts[1:]))
    require(not location["crosses_origin"] or topology == "circular", "circular-location", "origin crossing on a noncircular reference")
    pairs, forms = [], []
    while i < len(lines):
        payload = lines[i][21:].strip(); i += 1
        match = re.fullmatch(r"/([A-Za-z][A-Za-z0-9_'*-]*)(?:=(.*))?", payload)
        require(match is not None, "qualifier-syntax", f"invalid qualifier: {payload!r}")
        key, value = match[1], match[2]
        if value is None:
            form, value = "flag", ""
        elif value.startswith('"'):
            form = "quoted"
            while quoted_value(value) is None:
                require(i < len(lines), "qualifier-syntax", "unterminated quoted qualifier")
                value += ("" if key == "translation" else " ") + lines[i][21:].strip(); i += 1
            value = quoted_value(value)
            if key == "translation":
                value = "".join(value.split())
        else:
            form = "unquoted"
            require(bool(value) and '"' not in value and len(payload) <= 59,
                    "qualifier-syntax", "unsupported unquoted qualifier")
        pairs.append({"key": key, "value": value}); forms.append(form)
    feature = {"feature_id": feature_id, "seqid": seqid, "type": kind,
               "coordinate_system": "contig", "start": min(p["start"] for p in parts),
               "end": max(p["end"] for p in parts), "strand": strand, "location": location,
               "attributes": pairs}
    for qualifier, slot in (("product", "product"), ("translation", "translated_sequence")):
        values = [p["value"] for p in pairs if p["key"] == qualifier]
        if len(values) == 1:
            feature[slot] = values[0]
    return feature, forms


def import_insdc(content, *, reference_context, source_uri):
    source = parse_bytes(content, source_uri=source_uri, format="genbank")
    errors = validation_errors(source, source_validator(), "SourceDocument")
    require(not errors, "source-invalid", "; ".join(errors))
    records = source["records"]
    contigs, features, mappings, i = [], [], [], 0
    while i < len(records):
        if not records[i]["raw_text"].strip():
            i += 1; continue
        first = i
        locus = re.match(r"^LOCUS\s+\S+\s+([1-9][0-9]*) bp\s+(.+)", records[i]["raw_text"])
        require(locus is not None, "genbank-record", "expected nucleotide LOCUS with length in bp")
        length = int(locus[1])
        # Old GenBank records omit the topology field for the linear default.
        topology = "circular" if re.search(r"\bcircular\b", locus[2]) else "linear"
        while i < len(records) and records[i]["raw_text"].rstrip("\r\n") != "//":
            i += 1
        require(i < len(records), "genbank-record", "record lacks // terminator")
        last = i; i += 1
        block = records[first:last + 1]
        versions = [m[1] for r in block if (m := re.match(r"^VERSION\s+([A-Z][A-Z0-9_]*\.[1-9][0-9]*)(?:\s|$)", r["raw_text"]))]
        require(len(versions) == 1, "reference-identity", "record requires one accession-version")
        seqid = "insdc:" + versions[0]
        contigs.append({"contig_id": seqid, "length_bp": length, "topology": topology})
        origins = [n for n in range(first, last) if records[n]["raw_text"].startswith("ORIGIN")]
        require(len(origins) == 1, "genbank-record", "one ORIGIN sequence is required")
        headers = [n for n in range(first, origins[0]) if records[n]["raw_text"].startswith("FEATURES ")]
        require(len(headers) == 1, "genbank-record", "one FEATURES section is required")
        require(all(r["kind"] in ("feature", "feature_continuation") or r["raw_text"].startswith("BASE COUNT")
                    for r in records[headers[0] + 1:origins[0]]),
                "genbank-record", "unsupported content within FEATURES section")
        sequence = ""
        for record in records[origins[0] + 1:last]:
            match = re.fullmatch(r"\s*[0-9]+\s+([A-Za-z\s]+)", record["raw_text"])
            require(match is not None, "genbank-sequence", "unsupported sequence line")
            sequence += "".join(match[1].split())
        require(len(sequence) == length and re.fullmatch(r"[ACGTRYSWKMBDHVNUacgtryswkmbdhvnu]+", sequence),
                "genbank-sequence", "sequence length/alphabet differs from LOCUS")
        starts = [n for n in range(first, origins[0]) if records[n]["kind"] == "feature"]
        require(bool(starts), "no-features", "record requires feature rows")
        require(starts[0] == headers[0] + 1, "genbank-record", "orphan feature continuation")
        for ordinal, start in enumerate(starts, 1):
            end = start + 1
            while end < origins[0] and records[end]["kind"] == "feature_continuation":
                end += 1
            lines = [r["raw_text"].rstrip("\r\n") for r in records[start:end]]
            feature, forms = parse_feature(lines, f"{seqid}:feature-{ordinal}", seqid, topology)
            # Successful import must already lie in the reverse mapper's domain.
            canonical = reconstruct_feature(feature, {"qualifier_forms": forms})
            rebuilt, rebuilt_forms = parse_feature(canonical.splitlines(), feature["feature_id"], seqid, topology)
            require(rebuilt == feature and rebuilt_forms == forms, "unsupported-qualifier",
                    "feature cannot be reconstructed without changing its interpreted values")
            features.append(feature)
            mappings.append({"feature_ids": [feature["feature_id"]], "source_span": [start, end], "qualifier_forms": forms})
    require(bool(contigs), "no-features", "at least one nucleotide record is required")
    dataset = {"contigs": contigs, "features": features}
    errors = validation_errors(dataset, dataset_validator())
    require(not errors, "dataset-invalid", "; ".join(errors))
    return {"conversion_version": 1, "profile": PROFILE, "reference_context": reference_context,
            "source": source, "dataset": dataset, "mappings": mappings}


def location_text(location):
    symbols = {"exact": "", "before": "<", "after": ">"}
    rendered = []
    for part in location["parts"]:
        start = symbols[part["start_status"]] + str(part["start"])
        end = symbols[part["end_status"]] + str(part["end"])
        text = start if start == end else start + ".." + end
        rendered.append("complement(" + text + ")" if part["strand"] == "-" else text)
    return rendered[0] if location["location_operator"] == "single" else location["location_operator"] + "(" + ",".join(rendered) + ")"


def reconstruct_feature(feature, mapping):
    """Build feature-table lines from semantic fields; no source feature text is read."""
    location = location_text(feature["location"])
    chunks = [location[i:i + 59] for i in range(0, len(location), 59)]
    lines = ["     " + feature["type"].ljust(16) + chunks[0]]
    lines.extend(" " * 21 + text for text in chunks[1:])
    pairs = feature.get("attributes", [])
    require(len(pairs) == len(mapping["qualifier_forms"]), "qualifier-mapping", "qualifier forms do not match attributes")
    for qualifier, slot in (("product", "product"), ("translation", "translated_sequence")):
        if slot in feature:
            require([p["value"] for p in pairs if p["key"] == qualifier] == [feature[slot]],
                    "attribute-conflict", f"generic {qualifier} differs from typed {slot}")
    for pair, form in zip(pairs, mapping["qualifier_forms"]):
        payload = "/" + pair["key"]
        if form == "flag":
            require(pair["value"] == "", "qualifier-mapping", "flag qualifier must have an empty generic value")
        elif form == "quoted":
            payload += '="' + pair["value"].replace('"', '""') + '"'
        else:
            require(form == "unquoted", "qualifier-mapping", "unknown qualifier form")
            payload += "=" + pair["value"]
        wrapped = textwrap.wrap(payload, width=59, break_long_words=pair["key"] == "translation",
                                break_on_hyphens=False, replace_whitespace=False)
        require(all(len(line) <= 59 for line in wrapped), "unsupported-qualifier", "unbreakable qualifier exceeds flat-file width")
        lines.extend(" " * 21 + line for line in wrapped)
    return "\n".join(lines) + "\n"


def semantic_mappings(bundle):
    return [{k: v for k, v in mapping.items() if k != "source_span"} for mapping in bundle["mappings"]]


def nonfeature_text(bundle):
    return [r["raw_text"] for r in bundle["source"]["records"] if r["kind"] not in ("feature", "feature_continuation")]


def reconstruct_document(bundle):
    by_id = {f["feature_id"]: f for f in bundle["dataset"]["features"]}
    starts = {m["source_span"][0]: m for m in bundle["mappings"]}
    output, i = [], 0
    while i < len(bundle["source"]["records"]):
        if i in starts:
            mapping = starts[i]
            output.append(reconstruct_feature(by_id[mapping["feature_ids"][0]], mapping))
            i = mapping["source_span"][1]
        else:
            output.append(bundle["source"]["records"][i]["raw_text"]); i += 1
    content = "".join(output).encode()
    again = import_insdc(content, reference_context=bundle["reference_context"], source_uri=bundle["source"]["artifact"]["uri"])
    require(again["dataset"] == bundle["dataset"] and semantic_mappings(again) == semantic_mappings(bundle)
            and nonfeature_text(again) == nonfeature_text(bundle), "reconstruction-mismatch", "GenBank reconstructed meaning differs")
    return content
