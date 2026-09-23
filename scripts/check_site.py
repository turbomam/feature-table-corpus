#!/usr/bin/env python3
"""Check every built local HTML link, fragment and resource without network access."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1] / "local" / "site"
BASE = "/feature-table-corpus/"


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.links = []
        self.ids = set()
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])


def check(root=ROOT):
    pages = {p.resolve(): Page(p) for p in root.rglob("*.html")}
    if not pages:
        raise ValueError("No built HTML pages")
    errors = []
    count = 0
    for path, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = unquote(url.path)
            if target.startswith(BASE):
                dest = root / target[len(BASE):]
            elif target.startswith("/"):
                errors.append(f"{path.relative_to(root)}: outside site base: {link}")
                continue
            else:
                dest = path.parent / target if target else path
            if dest.is_dir():
                dest /= "index.html"
            dest = dest.resolve()
            count += 1
            if not dest.is_relative_to(root.resolve()) or not dest.is_file():
                errors.append(f"{path.relative_to(root)}: missing target: {link}")
            elif url.fragment and dest in pages and unquote(url.fragment) not in pages[dest].ids:
                errors.append(f"{path.relative_to(root)}: missing fragment: {link}")
    if errors:
        raise ValueError("\n".join(errors))
    print(f"Checked {count} local links/resources across {len(pages)} HTML pages")


if __name__ == "__main__":
    check()
