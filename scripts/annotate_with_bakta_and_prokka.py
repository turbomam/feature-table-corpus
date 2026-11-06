#!/usr/bin/env python3
"""Annotate one genome with Bakta and Prokka in Docker, so their GFF3 and GenBank output can be vendored.

Usage: python scripts/annotate_with_bakta_and_prokka.py GENOME_FASTA BAKTA_DB_DIR OUTPUT_DIR
           [--translation-table N] [--locus-tag TAG] [--threads N]

The images are pinned by tag (oschwengers/bakta:v1.12.2, staphb/prokka:1.15.6) and run as
linux/amd64. Bakta needs its database unpacked in BAKTA_DB_DIR, for example the light database
6.0 from https://doi.org/10.5281/zenodo.14916843. With Bakta v1.12.2 and that database, the
AMRFinderPlus step exited with error code 1 until its database was updated in place with
`docker run --rm --platform linux/amd64 -v BAKTA_DB_DIR:/db oschwengers/bakta:v1.12.2
amrfinder_update --force_update --database /db/amrfinderplus-db/` (2026-11-06). Bakta keeps the
input's sequence names (--keep-contig-headers), so its files and Prokka's name the same contig. Both tools write into OUTPUT_DIR/bakta and
OUTPUT_DIR/prokka, and OUTPUT_DIR/versions.txt records what each tool reported about itself.
"""
import argparse
from pathlib import Path
import subprocess

BAKTA_IMAGE = "oschwengers/bakta:v1.12.2"
PROKKA_IMAGE = "staphb/prokka:1.15.6"


def docker(image, mounts, args):
    command = ["docker", "run", "--rm", "--platform", "linux/amd64"]
    for host, container in mounts:
        command += ["-v", f"{host.resolve()}:{container}"]
    return subprocess.run(command + [image] + args, check=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("genome", type=Path)
    parser.add_argument("db", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--translation-table", type=int, default=11)
    parser.add_argument("--locus-tag", default="MG")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    genome_dir, name = args.genome.parent, args.genome.name
    versions = [
        "bakta " + docker(BAKTA_IMAGE, [], ["bakta", "--version"]).stdout.strip(),
        "prokka " + docker(PROKKA_IMAGE, [], ["prokka", "--version"]).stderr.strip(),
    ]
    docker(BAKTA_IMAGE, [(genome_dir, "/in"), (args.db, "/db"), (args.output, "/out")],
           ["bakta", "--db", "/db", "--output", "/out/bakta", "--prefix", args.locus_tag,
            "--locus-tag", args.locus_tag, "--keep-contig-headers", "--translation-table", str(args.translation_table),
            "--threads", str(args.threads), "--force", f"/in/{name}"])
    docker(PROKKA_IMAGE, [(genome_dir, "/in"), (args.output, "/out")],
           ["prokka", "--outdir", "/out/prokka", "--prefix", args.locus_tag, "--locustag",
            args.locus_tag, "--gcode", str(args.translation_table), "--cpus", str(args.threads),
            "--force", f"/in/{name}"])
    (args.output / "versions.txt").write_text("\n".join(versions) + "\n")
    print("\n".join(versions))


if __name__ == "__main__":
    main()
