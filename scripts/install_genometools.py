#!/usr/bin/env python3
"""Install a checksum-pinned upstream validator under gitignored local/tools/."""
import hashlib
import platform
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.6.6"
ARCHIVES = {
    ("Darwin", "arm64"): ("Darwin_arm64", "40142adb1466823f5e9da98c3e92c1263b3958c5344aedfd1b76c7d61cfdb957"),
    ("Linux", "x86_64"): ("Linux_x86_64", "f74c1d2ab23b71308d09fec738abb364ee8b85ade3c929d2886f10856ed73fe8"),
}


def default_binary():
    system = (platform.system(), platform.machine())
    if system not in ARCHIVES:
        raise ValueError(f"No pinned binary for {system}; set GENOMETOOLS to a GenomeTools {VERSION} binary")
    name = f"gt-{VERSION}-{ARCHIVES[system][0]}-64bit-barebone"
    return ROOT / "local" / "tools" / name / "bin" / "gt"


def install():
    # Extraction filters were backported to Python 3.11.4. The launcher requests
    # >=3.11.8; also fail clearly when this file is invoked with an older Python.
    if not hasattr(tarfile, "data_filter"):
        raise SystemExit("Safe extraction filters unavailable; run just validity-install (Python 3.11.8+)")
    binary = default_binary()
    directory = ROOT / "local" / "tools"
    directory.mkdir(parents=True, exist_ok=True)
    name = binary.parent.parent.name
    archive = directory / f"{name}.tar.gz"
    url = f"https://github.com/genometools/genometools/releases/download/v{VERSION}/{archive.name}"
    if not archive.exists():
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", url, "--output", str(archive)], check=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != ARCHIVES[(platform.system(), platform.machine())][1]:
        raise ValueError(f"Checksum mismatch for {archive}; refusing extraction")
    with tarfile.open(archive) as source:
        source.extractall(directory, filter="data")
    subprocess.run([str(binary), "-version"], check=True)
    print(binary)


if __name__ == "__main__":
    install()
