#!/usr/bin/env python3
"""Regenerate, or check, the committed actinorhodin Dataset and Parquet files.

Usage: python scripts/actinorhodin_parquet.py [--check]

Runs the same two steps as docs/actinorhodin-walkthrough.md: import
corpus/derived-examples/actinorhodin.gff3 with gff3-contig/4.0.0, then export the Dataset with
scripts/lakehouse_export.py. Both run through their just recipes, so they use the pinned
requirements files. Output goes to a new directory under local/; without --check the results
are copied to model/examples/actinorhodin/.

With --check, dataset.json must equal the regenerated one byte for byte, and each Parquet file
must have the same schema, including its metadata, and the same rows in the same order. Parquet
bytes are not compared: with the same DuckDB build and the same rows, a few column chunks
compress to slightly different sizes on macOS and on Linux (measured 2026-10-02).
"""
import argparse
import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "corpus/derived-examples/actinorhodin.gff3"
PROFILE = "gff3-contig/4.0.0"
REFERENCE = "refseq:NC_003888.3"
TARGET = ROOT / "model" / "examples" / "actinorhodin"
DATASET = "dataset.json"
PARQUET = ["parquet/contig_collections.parquet", "parquet/contigs.parquet",
           "parquet/features.parquet"]


def build(work):
    bundle = work / "bundle.json"
    subprocess.run(["just", "conversion-import", SOURCE, PROFILE, REFERENCE, str(bundle),
                    "--metadata-profile", "ncbi"], cwd=ROOT, check=True)
    dataset = json.loads(bundle.read_text())["dataset"]
    (work / DATASET).write_text(json.dumps(dataset, indent=2) + "\n")
    subprocess.run(["just", "lakehouse-export", str(work / DATASET), str(work / "parquet")],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def same_parquet(new, old):
    import pyarrow.lib
    import pyarrow.parquet as pq
    try:
        expected = pq.read_table(old)
    except (OSError, pyarrow.lib.ArrowException):
        return False
    actual = pq.read_table(new)
    return actual.schema.equals(expected.schema, check_metadata=True) and actual.equals(expected)


def differences(work):
    differ = []
    if not (TARGET / DATASET).exists() or not filecmp.cmp(work / DATASET, TARGET / DATASET,
                                                          shallow=False):
        differ.append(DATASET)
    for name in PARQUET:
        if not (TARGET / name).exists() or not same_parquet(work / name, TARGET / name):
            differ.append(name)
    return differ


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed files instead of replacing them")
    args = parser.parse_args()
    work = None
    try:
        (ROOT / "local").mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="actinorhodin-", dir=ROOT / "local"))
        build(work)
        if args.check:
            differ = differences(work)
            if differ:
                print("error: differ from the regenerated files: " + ", ".join(differ),
                      file=sys.stderr)
                print("run `just actinorhodin-parquet` and commit the result", file=sys.stderr)
                return 1
            print(f"all {1 + len(PARQUET)} committed actinorhodin files reproduce")
        else:
            for name in [DATASET, *PARQUET]:
                (TARGET / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / name, TARGET / name)
            print(f"wrote {1 + len(PARQUET)} files under {TARGET.relative_to(ROOT)}")
        return 0
    except subprocess.CalledProcessError as error:
        print(f"error: {' '.join(error.cmd[:2])} exited with status {error.returncode}",
              file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
