"""Saves the pages a watcher reads, for its parser test.

    python3.14 -m fwcat.capture shearwater [mares ...]

Each page is fetched exactly as the watcher fetches it and stored gzipped
under tests/fixtures/<maker>/, named after its URL. Keys a page embeds for
its own scripts (store API keys, access tokens) are replaced with REDACTED,
so the public repository never carries a third party's key. Run it when a maker
changes a page layout, then update the parser until its test passes again.
"""

import gzip
import re
import sys
from pathlib import Path

from . import catalogue
from .watch import fetch

FIXTURES = catalogue.ROOT / "tests" / "fixtures"
EMBEDDED_KEY = re.compile(
    r"""(?i)("?[a-z_]*(?:api[_-]?key|apikey|access[_-]?token|secret)[a-z_]*"?\s*[:=]\s*")([^"]{8,})(")""")


def redact(text: str) -> str:
    return EMBEDDED_KEY.sub(lambda m: m.group(1) + "REDACTED" + m.group(3), text)


def fixture_path(maker: str, url: str) -> Path:
    name = re.sub(r"[^A-Za-z0-9]+", "-", url.split("://", 1)[-1]).strip("-")[:120]
    return FIXTURES / maker / f"{name}.gz"


def load_fixture(maker: str, url: str) -> str:
    return gzip.decompress(fixture_path(maker, url).read_bytes()).decode("utf-8")


def save_fixture(maker: str, url: str, text: str) -> Path:
    path = fixture_path(maker, url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(redact(text).encode("utf-8"), mtime=0))
    return path


def main(argv=None) -> int:
    from .parsers import WATCHERS

    makers = argv if argv is not None else sys.argv[1:]
    known = {w.maker: w for w in WATCHERS}
    unknown = [m for m in makers if m not in known]
    if not makers or unknown:
        print(f"usage: python3.14 -m fwcat.capture MAKER...; makers: {', '.join(known)}")
        return 2
    for maker in makers:
        for url in known[maker].urls:
            print(save_fixture(maker, url, fetch(url)).relative_to(catalogue.ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
