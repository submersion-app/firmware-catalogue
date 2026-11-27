"""Mares: one store page per firmware download, with a JSON-LD Product.

The Product's `name` ends in the version (`FW. Genius V1.06.07`) and its
`sku` (`MA-FIRM-013`) identifies the download, so the parser checks the sku
before trusting the name. The URL slugs keep old version numbers and are
never read. Pages without a locale prefix are current; some `en_US` copies
lag behind.
"""

import json
import re

from ..watch import Finding, ParseError, Watcher

URL = "https://www.mares.com/product/{}"

# model id: (page slug, sku)
MODELS = {
    "mares-genius": ("fw-genius-v1-04-00-ma-firm-013", "MA-FIRM-013"),
    "mares-horizon": ("fw-horizon-scr-v01-10-18-ma-firm-014", "MA-FIRM-014"),
    "mares-puck-4": ("fw-puck-4-v01-05-01-ma-firm-20", "MA-FIRM-20"),
    "mares-puck-pro-ultra": ("fw-puck-lite-puck-pro-ultra-puck-pro-ez-v01-05-01-ma-firm-18", "MA-FIRM-18"),
    "mares-quad-2": ("fw-quad-2-v01-01-00-ma-firm-21", "MA-FIRM-21"),
    "mares-quad-ci": ("fw-quad-ci-v01-01-01-ma-firm-22", "MA-FIRM-22"),
    "mares-sirius": ("fw-sirius-ma-firm-016", "MA-FIRM-016"),
    "mares-smart-air": ("fw-smart-air-v1-00-ma-firm-015", "MA-FIRM-015"),
}

_LD = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_VERSION = re.compile(r"\b(V\d+(?:\.\d+)+)\s*$")


def product(page: str) -> dict:
    for block in _LD.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    raise ParseError("no JSON-LD Product on the page")


def parse(pages: dict[str, str]) -> list[Finding]:
    findings = []
    for model_id, (slug, sku) in MODELS.items():
        url = URL.format(slug)
        item = product(pages[url])
        if str(item.get("sku", "")).upper() != sku:
            raise ParseError(f"{url} now holds {item.get('sku')!r}, not {sku}")
        match = _VERSION.search(str(item.get("name", "")))
        if not match:
            raise ParseError(f"{url}: no version at the end of {item.get('name')!r}")
        findings.append(Finding(model_id, match.group(1), url, notes_url=url))
    return findings


WATCHER = Watcher(
    maker="mares",
    data_file="mares.json",
    urls=tuple(URL.format(slug) for slug, _ in MODELS.values()),
    model_ids=tuple(MODELS),
    parse=parse,
)
