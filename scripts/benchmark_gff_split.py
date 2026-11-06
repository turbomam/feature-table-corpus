#!/usr/bin/env python3
"""Time the stdlib GFF3 reader and the split prototype on corpus files, one fresh process per run.

Usage: python scripts/benchmark_gff_split.py [--case PATH PROFILE ...] [--repeats N] [--json OUT]
           [--roundtrip-img-functional PATH] [--work-dir DIR]

For each case it runs, each in a new Python process so that peak memory never carries over:

- parse: scripts/source_document.py parse_bytes alone, on bytes already read into memory;
- split: scripts/split_gff_prototype.py main(), which parses, validates every row, writes DuckDB and
  rebuilds the file from DuckDB.

Optionally it also times scripts/img_functional_map.py roundtrip (linkml-map forward and back) on one
IMG functional annotation GFF, for comparison with the split.

Times are time.perf_counter wall seconds around the measured call only, after imports. Peak memory is
resource.getrusage(RUSAGE_SELF).ru_maxrss of that process, so it includes the interpreter and the
imported libraries. Each measurement runs --repeats times and the median is reported. With no --case,
the baseline set below is used. Prints a Markdown table and, with --json, writes every run.
"""
import argparse
import contextlib
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# The largest GFF3 files in the corpus plus the files the split prototype README covers.
# NCBI RefSeq files carry #! lines, so they use the ncbi metadata profile; the rest are generic.
BASELINE_CASES = (
    ("corpus/sources/ncbi-refseq/NC_003888.3_2026-09-21.gff3", "ncbi"),
    ("corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_functional_annotation.gff", "generic"),
    ("corpus/sources/ncbi-refseq/NC_014649.1_2026-10-30.gff3", "ncbi"),
    ("corpus/sources/prokka/Mycoplasma_genitalium_G37_NC_000908.2_prokka-1.15.6.gff", "generic"),
    ("corpus/sources/bakta/Mycoplasma_genitalium_G37_NC_000908.2_bakta-1.12.2.gff3", "generic"),
    ("corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_prodigal.gff", "prodigal"),
    ("corpus/sources/ensembl/Saccharomyces_cerevisiae.R64-1-1.63.chromosome.Mito.gff3", "generic"),
    ("corpus/sources/ncbi-refseq/NC_001417.2_2026-10-30.gff3", "ncbi"),
)
ROUNDTRIP_DEFAULT = "corpus/sources/jgi-img/IMG_AP-1268149/Ga0423362_functional_annotation.gff"


def peak_rss_mb():
    """Peak resident set size of this process in MB; macOS reports bytes, Linux kilobytes."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"benchmarked_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child(mode, path, profile, work_dir):
    """Run one measurement in this process and print one JSON object."""
    sys.path.insert(0, str(SCRIPTS))
    start = time.perf_counter()
    if mode == "parse":
        from source_document import parse_bytes
    elif mode == "split":
        module = load_script("split_gff_prototype")
    else:
        module = load_script("img_functional_map")
    import_s = time.perf_counter() - start
    if mode == "parse":
        content = path.read_bytes()
    rss_before = peak_rss_mb()
    output = io.StringIO()
    start = time.perf_counter()
    if mode == "parse":
        parse_bytes(content, source_uri=path.resolve().as_uri(), format="gff3", profile=profile)
        status = 0
    elif mode == "split":
        database = work_dir / f"{path.name}.duckdb"
        argv = [str(path), str(database), "--metadata-profile", profile]
        with contextlib.redirect_stdout(output):
            saved, sys.argv = sys.argv, ["split_gff_prototype.py", *argv]
            try:
                module.main()
                status = 0
            except SystemExit as stop:
                status = stop.code or 0
            finally:
                sys.argv = saved
    else:
        with contextlib.redirect_stdout(output):
            status = module.main(["roundtrip", str(path)]) or 0
    seconds = time.perf_counter() - start
    result = {"mode": mode, "seconds": seconds, "import_seconds": import_s, "status": status,
              "peak_rss_mb": peak_rss_mb(), "peak_rss_mb_after_imports": rss_before}
    if mode == "split" and status == 0:
        summary = json.loads(output.getvalue())
        result.update(lines=summary["lines"], rebuilt_identical=summary["rebuilt_identical"],
                      model_tables_written=summary["model_tables_written"],
                      gff3_contig_refusal=summary["gff3_contig_refusal"], stages=summary["seconds"])
    if mode == "roundtrip":
        result["held"] = status == 0
    print(json.dumps(result))


def measure(mode, path, profile, work_dir):
    command = [sys.executable, __file__, "--child", mode, str(path), profile, "--work-dir", str(work_dir)]
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    if result.returncode:
        raise SystemExit(f"{mode} failed on {path}:\n{result.stdout}{result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def median_of(runs, key):
    return statistics.median(run[key] for run in runs)


def machine():
    cpu = platform.processor()
    if sys.platform == "darwin":
        brand = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True)
        cpu = brand.stdout.strip() or cpu
    elif Path("/proc/cpuinfo").exists():
        names = [line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                 if line.startswith("model name")]
        cpu = names[0] if names else cpu
    return {"platform": platform.platform(), "machine": platform.machine(), "cpu": cpu,
            "cpu_count": os.cpu_count(), "python": platform.python_version(),
            "date": datetime.date.today().isoformat()}


def file_size_and_lines(path, chunk_size=1 << 20):
    """Byte size and bytes.splitlines() line count, read in chunks so the controller never holds the file.

    On Linux a child's ru_maxrss can start at the controller's resident size, so holding a whole input here
    could raise every reported peak.
    """
    breaks = 0
    last = b""
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            breaks += chunk.count(b"\n") + chunk.count(b"\r") - chunk.count(b"\r\n")
            if last == b"\r" and chunk.startswith(b"\n"):
                breaks -= 1
            last = chunk[-1:]
    return os.stat(path).st_size, breaks + (1 if last and last not in b"\r\n" else 0)


def benchmark(cases, repeats, work_dir, roundtrip=None):
    # Children run with cwd=ROOT, so a relative --work-dir must be resolved against the caller's cwd here.
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {"machine": machine(), "repeats": repeats, "files": []}
    for path, profile in cases:
        path = Path(path)
        size, lines = file_size_and_lines(path if path.is_absolute() else ROOT / path)
        parse = [measure("parse", path, profile, work_dir) for _ in range(repeats)]
        split = [measure("split", path, profile, work_dir) for _ in range(repeats)]
        report["files"].append({
            "file": path.as_posix(), "profile": profile, "bytes": size,
            "lines": lines,
            "parse_s": median_of(parse, "seconds"), "split_s": median_of(split, "seconds"),
            "parse_peak_mb": median_of(parse, "peak_rss_mb"), "split_peak_mb": median_of(split, "peak_rss_mb"),
            "split_peak_mb_after_imports": median_of(split, "peak_rss_mb_after_imports"),
            "rebuilt_identical": all(run["rebuilt_identical"] for run in split),
            "model_tables_written": split[0]["model_tables_written"],
            "gff3_contig_refusal": split[0]["gff3_contig_refusal"],
            "runs": {"parse": parse, "split": split},
        })
    if roundtrip:
        path = Path(roundtrip)
        runs = [measure("roundtrip", path, "generic", work_dir) for _ in range(repeats)]
        report["roundtrip"] = {"file": path.as_posix(), "seconds": median_of(runs, "seconds"),
                               "peak_mb": median_of(runs, "peak_rss_mb"),
                               "held": all(run["held"] for run in runs), "runs": runs}
    return report


def markdown(report):
    rows = ["| file | bytes | lines | parse s | split s | peak MB | notes |", "|---|---|---|---|---|---|---|"]
    for item in report["files"]:
        notes = [f"{item['profile']} profile", f"parse peak {item['parse_peak_mb']:.0f} MB"]
        notes.append("rebuilt byte for byte" if item["rebuilt_identical"] else "rebuild differs")
        if not item["model_tables_written"]:
            notes.append(f"feature model refused ({(item['gff3_contig_refusal'] or '').split(':')[0]})")
        rows.append(f"| `{item['file']}` | {item['bytes']} | {item['lines']} | {item['parse_s']:.3f} | "
                    f"{item['split_s']:.3f} | {item['split_peak_mb']:.0f} | {'; '.join(notes)} |")
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", nargs=2, action="append", metavar=("PATH", "PROFILE"),
                        help="a GFF3 file and its metadata profile (generic, ncbi or prodigal); repeatable")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", type=Path, help="also write the full report, every run included, here")
    parser.add_argument("--roundtrip-img-functional", nargs="?", const=ROUNDTRIP_DEFAULT, default=None,
                        help=f"also time img_functional_map.py roundtrip on this file (default {ROUNDTRIP_DEFAULT})")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "local/splitter-baseline")
    parser.add_argument("--child", nargs=3, metavar=("MODE", "PATH", "PROFILE"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        mode, path, profile = args.child
        return child(mode, Path(path), profile, args.work_dir)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    report = benchmark(args.case or BASELINE_CASES, args.repeats, args.work_dir, args.roundtrip_img_functional)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report["machine"]))
    print(markdown(report))
    if "roundtrip" in report:
        trip = report["roundtrip"]
        print(f"roundtrip {trip['file']}: {trip['seconds']:.3f} s, peak {trip['peak_mb']:.0f} MB, "
              f"{'held' if trip['held'] else 'FAILED'}")


if __name__ == "__main__":
    main()
