#!/usr/bin/env python3
"""Regenerate, or check, the committed actinorhodin Dataset and Parquet files.

Usage: python scripts/actinorhodin_parquet.py [--check]

Runs the same two steps as docs/actinorhodin-walkthrough.md: import
corpus/derived-examples/actinorhodin.gff3 with gff3-contig/4.0.0, then export the Dataset with
scripts/lakehouse_export.py. Both run through their just recipes, so they use the pinned
requirements files. Output goes to a new directory under local/; without --check the results
are copied to model/examples/actinorhodin/, and with --check each committed file must equal the
regenerated one byte for byte.
"""
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
FILES = ["dataset.json", "parquet/contig_collections.parquet", "parquet/contigs.parquet",
         "parquet/features.parquet"]


def build(work):
    bundle = work / "bundle.json"
    subprocess.run(["just", "conversion-import", SOURCE, PROFILE, REFERENCE, str(bundle),
                    "--metadata-profile", "ncbi"], cwd=ROOT, check=True)
    dataset = json.loads(bundle.read_text())["dataset"]
    (work / "dataset.json").write_text(json.dumps(dataset, indent=2) + "\n")
    subprocess.run(["just", "lakehouse-export", str(work / "dataset.json"), str(work / "parquet")],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def main(check):
    (ROOT / "local").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="actinorhodin-", dir=ROOT / "local"))
    try:
        build(work)
        if check:
            differ = [name for name in FILES
                      if not (TARGET / name).exists()
                      or not filecmp.cmp(work / name, TARGET / name, shallow=False)]
            if differ:
                print("differ from the regenerated files: " + ", ".join(differ), file=sys.stderr)
                print("run `just actinorhodin-parquet` and commit the result", file=sys.stderr)
                return 1
            print(f"all {len(FILES)} committed actinorhodin files reproduce byte for byte")
        else:
            for name in FILES:
                (TARGET / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / name, TARGET / name)
            print(f"wrote {len(FILES)} files under {TARGET.relative_to(ROOT)}")
        return 0
    finally:
        shutil.rmtree(work)


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv[1:]))
