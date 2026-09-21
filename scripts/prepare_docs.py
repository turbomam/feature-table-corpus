#!/usr/bin/env python3
"""Stage an explicit set of tracked public artifacts; never traverse local research."""
from pathlib import Path
import shutil
import subprocess
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "local" / "site-src"
PUBLIC_ROOTS = {"docs", "model", "analyses", "corpus", "scripts", "tests"}
ROOT_FILES = {"README.md", "LICENSE", "justfile", "requirements-conversion.txt", "requirements-docs.txt"}
EXTENSIONS = {".md", ".yaml", ".yml", ".json", ".csv", ".tsv", ".gff", ".gff3", ".gtf",
              ".bed", ".gb", ".faa", ".fna", ".sql", ".py", ".txt", ".rst", ".svg", ".png", ".crisprs"}


def publishable(path):
    return (not any(part.startswith(".") for part in path.parts)
            and (path.as_posix() in ROOT_FILES or
                 (path.parts[0] in PUBLIC_ROOTS and path.suffix in EXTENSIONS)))


def prepare():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    # DEST is fixed and exclusively generated; no caller-supplied deletion target.
    if DEST.is_symlink():
        raise ValueError("Refusing a symlink at local/site-src")
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    count = 0
    for name in tracked:
        if not name:
            continue
        relative = Path(name)
        if not publishable(relative):
            continue
        source = ROOT / relative
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError(f"Refusing linked public artifact: {relative}")
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        count += 1
    # Directory links in the existing prose remain useful, including raw-source
    # downloads. Generate navigation only; all maintained prose stays in place.
    directories = [DEST] + sorted(p for p in DEST.rglob("*") if p.is_dir())
    for directory in directories:
        if (directory / "README.md").exists() or (directory / "index.md").exists():
            continue
        title = directory.relative_to(DEST).as_posix()
        lines = [f"# {title}", "", "Files published from the repository:", ""]
        for child in sorted(directory.iterdir()):
            name = child.name + ("/" if child.is_dir() else "")
            lines.append(f"- [{name}]({quote(name)})")
        (directory / "README.md").write_text("\n".join(lines) + "\n")
    # MkDocs needs explicit Markdown targets to rebase links for nested page
    # URLs. GitHub's directory links remain unchanged in maintained sources.
    for page in DEST.rglob("*.md"):
        def directory_link(match):
            url = urlsplit(match[2])
            if url.scheme or url.netloc or not url.path:
                return match[0]
            target = (page.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(DEST) or not target.is_dir():
                return match[0]
            index = "README.md" if (target / "README.md").exists() else "index.md"
            path = url.path.rstrip("/") + "/" + index
            return match[1] + urlunsplit(url._replace(path=path)) + match[3]
        page.write_text(re.sub(r"(\]\()([^\s)]+)(\))", directory_link, page.read_text()))
    print(f"Staged {count} tracked artifacts in {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    prepare()
