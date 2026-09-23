#!/usr/bin/env python3
"""Query validated explicit locations without substituting their scalar envelopes."""
import argparse
import json
from pathlib import Path
import sys

from feature_locations import overlap, distance
from validate_closed import load_validated

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    ov = commands.add_parser("overlap")
    ov.add_argument("reference")
    ov.add_argument("start", type=int)
    ov.add_argument("end", type=int)
    ov.add_argument("--mode", choices=("exact", "reported"), default="exact")
    gap = commands.add_parser("distance")
    gap.add_argument("left")
    gap.add_argument("right")
    args = parser.parse_args()
    try:
        data = load_validated(ROOT / "model/schema/ber_feature_model.yaml", args.dataset)
        if args.command == "overlap":
            result = overlap(data, args.reference, args.start, args.end, mode=args.mode)
        else:
            features = {f["feature_id"]: f for f in data["features"]}
            left, right = features[args.left], features[args.right]
            contig = next(c for c in data["contigs"] if c["contig_id"] == left["seqid"])
            result = {"intervening_bases": distance(left, right, contig), "reference": left["seqid"],
                      "metric": "minimum between occupied parts, circular shortest path when declared"}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
