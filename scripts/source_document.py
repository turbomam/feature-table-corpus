#!/usr/bin/env python3
"""Preserve a UTF-8 GFF3/GTF document and interpret scoped metadata.

This is a source-document reader, not a biological feature converter or full GFF
validator. Feature columns remain lexical strings; column 9 is not interpreted.
Only the standard library is needed. See docs/source-documents.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

FORMATS = ("gff3", "gtf")
PROFILES = ("generic", "prodigal", "ncbi")
GFF_DOCUMENT_DIRECTIVES = {
    "gff-version", "feature-ontology", "attribute-ontology", "source-ontology",
    "species", "genome-build",
}
NCBI_DIRECTIVES = {
    "gff-spec-version", "processor", "genome-build", "genome-build-accession",
    "annotation-source", "annotation-date", "annotation-data-source",
}


def named_payload(text):
    """Separate a directive name and payload without changing the raw record."""
    parts = text.split(None, 1)
    return (parts[0], parts[1] if len(parts) > 1 else "") if parts else ("", "")


def prodigal_attributes(text):
    """Split semicolons outside double quotes; retain source spelling and quotes.

    The raw record remains authoritative. This profile does not URL-decode values
    or assume the rules for GFF column 9 apply to Prodigal comments.
    """
    parts, begin, quoted, escaped = [], 0, False, False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            parts.append(text[begin:i])
            begin = i + 1
    if quoted:
        raise ValueError("unterminated double quote in Prodigal metadata")
    parts.append(text[begin:])
    attributes = []
    for part in parts:
        if not part.strip():
            continue
        key, separator, value = part.strip().partition("=")
        if not separator or not key or key.strip() != key:
            raise ValueError("expected key=value in Prodigal metadata")
        attributes.append({"key": key, "value": value})
    return attributes


def single_value(attributes, key):
    values = [a["value"] for a in attributes if a["key"] == key]
    if len(values) != 1:
        raise ValueError(f"expected exactly one {key} in Prodigal Sequence Data")
    return values[0]


def prodigal_sequence_id(attributes):
    header = single_value(attributes, "seqhdr")
    if not (header.startswith('"') and header.endswith('"') and header[1:-1].split()):
        raise ValueError("expected a nonempty quoted seqhdr in Prodigal Sequence Data")
    if not re.fullmatch(r"[1-9][0-9]*", single_value(attributes, "seqnum")):
        raise ValueError("expected a positive seqnum in Prodigal Sequence Data")
    if not re.fullmatch(r"[0-9]+", single_value(attributes, "seqlen")):
        raise ValueError("expected a nonnegative seqlen in Prodigal Sequence Data")
    return header[1:-1].split()[0]


def valid_region(values):
    if len(values) != 3 or not all(re.fullmatch(r"[1-9][0-9]*", v) for v in values[1:]):
        return False
    try:
        return int(values[1]) <= int(values[2])
    except ValueError:
        return False


def parse_bytes(content, *, source_uri, format, profile="generic"):
    """Return a SourceDocument instance with ordered, byte-replayable records.

    Unknown semantics get stream scope, never guessed document/sequence scope.
    Sequence contexts use record IDs, so repeated sequence names remain distinct.
    All input is retained in memory; compressed and non-UTF-8 input are unsupported.
    """
    if format not in FORMATS or profile not in PROFILES:
        raise ValueError("unsupported format or metadata profile")
    if profile == "prodigal" and format != "gff3":
        raise ValueError("the Prodigal profile requires GFF3")
    if not isinstance(source_uri, str) or not source_uri:
        raise ValueError("a source URI is required")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("input must be uncompressed UTF-8 text") from error
    document = {
        "artifact": {"uri": source_uri, "sha256": hashlib.sha256(content).hexdigest(),
                     "byte_size": len(content)},
        "format": format, "profile": profile, "records": [],
    }
    context = None
    fasta = False
    fasta_context = None
    # Unlike str.splitlines, only physical CR/LF line endings delimit records.
    for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text):
        raw = match.group()
        if not raw:
            continue
        number = len(document["records"]) + 1
        body = raw.rstrip("\r\n")
        if number == 1 and body.startswith("\ufeff"):
            body = body[1:]
        record = {"record_id": f"line-{number}", "line_number": number,
                  "raw_text": raw, "kind": "unparsed", "scope": "stream"}
        document["records"].append(record)

        def warn(message):
            record.setdefault("warnings", []).append(message)

        def scoped(sequence_id, anchor=None):
            record.update(scope="sequence", sequence_id=sequence_id)
            if anchor is not None:
                record["context_record"] = anchor

        # GFF3 also permits an implied FASTA transition at the first > header.
        if format == "gff3" and body.startswith(">"):
            fasta, context = True, None
        if fasta:
            if body.startswith(">"):
                fasta_context = None
                header = body[1:]
                record.update(kind="fasta_header", metadata_type="fasta-header",
                              metadata=[{"key": "defline", "value": header}])
                if header.split():
                    sequence_id = header.split()[0]
                    scoped(sequence_id)
                    fasta_context = (sequence_id, record["record_id"])
                else:
                    warn("empty FASTA header")
            elif not body.strip():
                record["kind"] = "blank"
            else:
                chunk = "".join(body.split())
                if fasta_context and re.fullmatch(r"[A-Za-z.*-]+", chunk):
                    record.update(kind="fasta_sequence", sequence_text=chunk)
                    scoped(*fasta_context)
                else:
                    warn("expected sequence text after a FASTA header; annotation parsing has ended")
            continue

        if not body.strip():
            record["kind"] = "blank"
        elif format == "gff3" and body.rstrip(" \t") == "###":
            record["kind"] = "boundary"
            context = None
        elif format == "gff3" and body.rstrip(" \t") == "##FASTA":
            record["kind"] = "fasta_start"
            fasta, context = True, None
        elif body.startswith("##"):
            name, payload = named_payload(body[2:])
            record.update(kind="directive", metadata_type=name)
            if format == "gff3" and name == "sequence-region":
                values = payload.split()
                if valid_region(values):
                    scoped(values[0])
                    record["metadata"] = [dict(key=k, value=v) for k, v in
                                          zip(("seqid", "start", "end"), values)]
                else:
                    warn("invalid sequence-region; expected seqid and positive ordered bounds")
            elif format == "gff3" and name in GFF_DOCUMENT_DIRECTIVES:
                if payload:
                    record.update(scope="document", metadata=[{"key": name, "value": payload}])
                else:
                    warn(f"missing payload for {name}")
        elif body.startswith("#"):
            record["kind"] = "comment"
            if profile == "prodigal" and body.startswith(("# Sequence Data:", "# Model Data:")):
                sequence_comment = body.startswith("# Sequence Data:")
                record["metadata_type"] = "prodigal-sequence" if sequence_comment else "prodigal-model"
                # A malformed new sequence header must not reuse the previous context.
                if sequence_comment:
                    context = None
                try:
                    attributes = prodigal_attributes(body.split(":", 1)[1].strip())
                    record["metadata"] = attributes
                    if sequence_comment:
                        sequence_id = prodigal_sequence_id(attributes)
                        scoped(sequence_id)
                        context = (sequence_id, record["record_id"])
                    elif context:
                        scoped(*context)
                    else:
                        warn("Prodigal Model Data has no valid preceding Sequence Data context")
                except ValueError as error:
                    warn(str(error))
            elif profile == "ncbi":
                prefix = "#!" if body.startswith("#!") else "#"
                name, payload = named_payload(body[len(prefix):])
                if ((prefix == "#!" and name in NCBI_DIRECTIVES)
                        or (format == "gtf" and prefix == "#" and name == "gtf-version")):
                    record["metadata_type"] = name
                    if payload:
                        record.update(scope="document", metadata=[{"key": name, "value": payload}])
                    else:
                        warn(f"missing payload for {name}")
        else:
            columns = body.split("\t")
            if len(columns) == 9:
                record.update(kind="feature", feature_columns=columns)
                if columns[0]:
                    scoped(columns[0])
                else:
                    warn("empty feature sequence ID")
                if context:
                    if context[0] == columns[0]:
                        record["context_record"] = context[1]
                    else:
                        warn("feature sequence ID disagrees with the Prodigal sequence context")
                        context = None
            else:
                warn(f"unrecognized annotation line: expected 9 tab-separated columns, got {len(columns)}")
    return document


def replay_bytes(document):
    """Validate the stored projection and reproduce exactly the original bytes.

    Re-parsing checks scopes, references, order, line numbers, and parsed values as
    well as the checksum. Editing a parsed field cannot silently change a source.
    """
    try:
        content = "".join(r["raw_text"] for r in document["records"]).encode("utf-8")
        expected = parse_bytes(content, source_uri=document["artifact"]["uri"],
                               format=document["format"], profile=document["profile"])
        if json.dumps(document, sort_keys=True) != json.dumps(expected, sort_keys=True):
            raise ValueError("source document differs from its checksum or re-parsed records")
        return content
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError("invalid source document structure") from error


def write_new(path, content):
    """Never overwrite a source or an existing output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("parse", help="emit a SourceDocument JSON instance")
    read.add_argument("input", type=Path)
    read.add_argument("--format", choices=FORMATS, required=True)
    read.add_argument("--profile", choices=PROFILES, default="generic")
    read.add_argument("--source-uri", help="provenance only; no URL is fetched")
    read.add_argument("--output", type=Path, help="new JSON path; default stdout")
    read.add_argument("--strict", action="store_true", help="emit the document but exit 1 if parsing warned")
    replay = commands.add_parser("replay", help="validate JSON and reconstruct the original source bytes")
    replay.add_argument("input", type=Path)
    replay.add_argument("--output", type=Path, required=True, help="new path; existing files are never overwritten")
    validate = commands.add_parser("validate", help="check JSON integrity, scopes, and parsed metadata")
    validate.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "parse":
            document = parse_bytes(args.input.read_bytes(), format=args.format, profile=args.profile,
                                   source_uri=args.source_uri or args.input.resolve().as_uri())
            encoded = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if args.output:
                write_new(args.output, encoded)
            else:
                sys.stdout.buffer.write(encoded)
            warnings = [(r["line_number"], w) for r in document["records"] for w in r.get("warnings", [])]
            for line, warning in warnings:
                print(f"line {line}: {warning}", file=sys.stderr)
            return 1 if args.strict and warnings else 0
        document = json.loads(args.input.read_text(encoding="utf-8"))
        content = replay_bytes(document)
        if args.command == "replay":
            write_new(args.output, content)
        else:
            print(f"SourceDocument integrity verified: {len(content)} source bytes")
        return 0
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
