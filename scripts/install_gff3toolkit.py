#!/usr/bin/env python3
"""Install the pinned, dependency-free GFF3toolkit QC entry point locally."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tarfile

from install_genometools import ROOT

VERSION = "2.1.0"
PYTHON_VERSION = (3, 11, 15)
SHA256 = "53a0efa1fbf67100aac85092d281e94907f0daaae92d3c873b3888711ba26520"
URL = f"https://codeload.github.com/NAL-i5K/GFF3toolkit/tar.gz/refs/tags/v{VERSION}"


def default_binary():
    return ROOT / "local/tools" / f"GFF3toolkit-{VERSION}" / "bin/gff3_QC"


def install():
    if sys.version_info[:3] != PYTHON_VERSION:
        raise ValueError("Use just validity-install-gff3toolkit (Python 3.11.15)")
    directory = ROOT / "local/tools"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"gff3toolkit-{VERSION}.tar.gz"
    if not archive.exists():
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", URL,
                        "--output", str(archive)], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise ValueError(f"Checksum mismatch for {archive}; refusing extraction")
    with tarfile.open(archive) as source:
        source.extractall(directory, filter="data")
    binary = default_binary()
    binary.parent.mkdir(exist_ok=True)
    # The upstream console entry point, without setup.py's unverified BLAST
    # download. The supported -noncg QC invocation uses only Python's stdlib.
    binary.write_text(
        f"#!{sys.executable}\n"
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from gff3tool.bin.gff3_QC import script_main\nscript_main()\n"
    )
    binary.chmod(0o755)
    subprocess.run([str(binary), "--version"], check=True)
    print(binary)


if __name__ == "__main__":
    install()
