"""Shared validation and explicit query semantics for ordered feature locations."""


def location_errors(feature, contig):
    location = feature.get("location")
    if not location:
        return []
    parts, errors = location["parts"], []
    if not parts:
        return ["location needs at least one part"]
    if feature["coordinate_system"] != "contig":
        errors.append("structured locations currently require contig coordinates")
    if (location["location_operator"] == "single") != (len(parts) == 1):
        errors.append("single requires one part; join/order require at least two")
    if {p["seqid"] for p in parts} != {feature["seqid"]}:
        errors.append("all parts must use the feature's qualified reference")
    strands = {p["strand"] for p in parts}
    if len(strands) != 1 or not strands <= {"+", "-"} or feature.get("strand") not in strands:
        errors.append("parts require one consistent explicit feature strand")
    if any(p["start"] > p["end"] for p in parts):
        errors.append("each part requires start <= end")
    ordered = sorted(parts, key=lambda p: (p["start"], p["end"]))
    if any(a["end"] >= b["start"] for a, b in zip(ordered, ordered[1:])):
        errors.append("location parts must not overlap")
    if feature["start"] != min(p["start"] for p in parts) or feature["end"] != max(p["end"] for p in parts):
        errors.append("scalar bounds must equal the reported part envelope")
    if not contig or not contig.get("length_bp"):
        errors.append("structured locations require known reference length_bp")
    elif any(p["end"] > contig["length_bp"] for p in parts):
        errors.append("part exceeds reference length_bp")
    reverse = feature.get("strand") == "-"
    traversal = ordered[::-1] if reverse else ordered
    pivot = traversal.index(parts[0])
    if parts != traversal[pivot:] + traversal[:pivot]:
        errors.append("parts must follow coordinate order within one reference circuit")
    crossings = sum((b["start"] > a["start"] if reverse else b["start"] < a["start"])
                    for a, b in zip(parts, parts[1:]))
    if bool(crossings) != location["crosses_origin"] or crossings > 1:
        errors.append("crosses_origin must match a single origin transition in traversal order")
    if crossings and (not contig or contig.get("topology") != "circular"):
        errors.append("origin crossing requires a declared circular reference")
    return errors


def reported_parts(feature):
    return feature["location"]["parts"] if feature.get("location") else [feature]


def is_partial(feature):
    return any(p.get("start_status", "exact") != "exact" or p.get("end_status", "exact") != "exact"
               for p in reported_parts(feature))


def overlap(data, seqid, start, end, *, mode="exact"):
    """Reported-bounds mode explicitly queries nominal parts, not unknown extensions."""
    if type(start) is not int or type(end) is not int or not 1 <= start <= end:
        raise ValueError("query bounds must be one-based inclusive integers")
    if mode not in ("exact", "reported"):
        raise ValueError("choose exact or reported bounds explicitly")
    contigs = {c["contig_id"]: c for c in data.get("contigs", [])}
    if seqid not in contigs:
        raise ValueError("unknown qualified reference")
    if contigs[seqid].get("length_bp") and end > contigs[seqid]["length_bp"]:
        raise ValueError("query exceeds the presented reference")
    features = [f for f in data.get("features", []) if f["seqid"] == seqid and f["coordinate_system"] == "contig"]
    if mode == "exact" and any(is_partial(f) for f in features):
        raise ValueError("reference has uncertain endpoints; choose reported bounds or a fully exact subset")
    return [{"feature_id": f["feature_id"], "bounds": "partial-reported" if is_partial(f) else "exact"}
            for f in features if any(p["start"] <= end and p["end"] >= start for p in reported_parts(f))]


def distance(left, right, contig):
    """Shortest count of intervening bases between exact occupied parts; 0 if adjacent/overlapping."""
    if left["seqid"] != right["seqid"] or left["seqid"] != contig["contig_id"]:
        raise ValueError("distance requires the same qualified reference")
    if left["coordinate_system"] != "contig" or right["coordinate_system"] != "contig":
        raise ValueError("genomic distance requires contig coordinates")
    if is_partial(left) or is_partial(right):
        raise ValueError("exact distance is undefined for uncertain endpoints")
    offsets = [0]
    if contig.get("topology") == "circular":
        if not contig.get("length_bp"):
            raise ValueError("circular distance requires length_bp")
        offsets += [-contig["length_bp"], contig["length_bp"]]
    return min(max(a["start"] - (b["end"] + shift) - 1, b["start"] + shift - a["end"] - 1, 0)
               for a in reported_parts(left) for b in reported_parts(right) for shift in offsets)
