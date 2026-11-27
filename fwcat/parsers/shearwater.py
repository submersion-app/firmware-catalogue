"""Shearwater: one support page per model, `Current Firmware Version: V102`.

The version sits in the server-rendered HTML near the top of each page. The
Petrel 2 page lists two models on one line: `V97 (Petrel 2) | V72 (Petrel 1)`.
Dates are only inside the release-notes PDF, so findings carry none; the
English notes link is kept when its file name repeats the version.

libdivecomputer reads the version string and keeps its digits (`V102` is
reported as 102), so each finding is also reported as the bare number.
"""

import re

from ..watch import Finding, ParseError, Watcher
from ._text import flat_text

URL = "https://shearwater.com/pages/{}-support"

# model id: (page slug, label on the page when it lists several models)
MODELS = {
    "shearwater-perdix-3": ("perdix-3", None),
    "shearwater-perdix-2": ("perdix-2", None),
    "shearwater-perdix-ai": ("perdix-ai", None),
    "shearwater-perdix": ("perdix", None),
    "shearwater-petrel-3": ("petrel-3", None),
    "shearwater-petrel-2": ("petrel-2", "Petrel 2"),
    "shearwater-petrel": ("petrel-2", "Petrel 1"),
    "shearwater-nerd-2": ("nerd-2", None),
    "shearwater-nerd": ("nerd-1", None),
    "shearwater-teric": ("teric", None),
    "shearwater-tern": ("tern", None),
    "shearwater-tern-tx": ("tern-tx", None),
    "shearwater-peregrine": ("peregrine", None),
    "shearwater-peregrine-tx": ("peregrine-tx", None),
    "shearwater-predator": ("predator", None),
}

_CURRENT = re.compile(
    r"Current Firmware Version:\s*((?:V\s?\d+\s*(?:\([^)]*\))?\s*\|?\s*)+)", re.I)
_PART = re.compile(r"V\s?(\d+)\s*(?:\(([^)]*)\))?", re.I)
_NOTES = re.compile(r'href="([^"]+\.pdf[^"]*)"[^>]*>\s*English\s*<', re.I)


def current_versions(page: str) -> dict[str | None, int]:
    """The page's current version numbers, by model label (None when unlabelled)."""
    match = _CURRENT.search(flat_text(page))
    if not match:
        raise ParseError("no 'Current Firmware Version' line")
    found: dict[str | None, int] = {}
    for number, label in _PART.findall(match.group(1)):
        key = " ".join(label.split()) or None
        if key in found:
            raise ParseError(f"two versions for {key or 'the page'}")
        found[key] = int(number)
    if not found:
        raise ParseError("the 'Current Firmware Version' line holds no version")
    return found


def notes_url(page: str, number: int) -> str | None:
    """The English release-notes PDF, when its file name names this version."""
    for href in _NOTES.findall(page):
        name = href.split("?")[0].rsplit("/", 1)[-1]
        if "release" in name.casefold() and re.search(rf"(?i)v{number}(?!\d)", name):
            return href
    return None


def parse(pages: dict[str, str]) -> list[Finding]:
    findings = []
    for model_id, (slug, label) in MODELS.items():
        url = URL.format(slug)
        versions = current_versions(pages[url])
        if label is not None:
            if label not in versions:
                raise ParseError(f"{url} lists no version for {label}")
            number = versions[label]
        elif len(versions) == 1:
            number = next(iter(versions.values()))
        else:
            raise ParseError(f"{url} lists several versions: {versions}")
        findings.append(Finding(
            model_id=model_id,
            version=f"V{number}",
            source=url,
            notes_url=notes_url(pages[url], number),
            reported_as=(str(number),),
        ))
    return findings


WATCHER = Watcher(
    maker="shearwater",
    data_file="shearwater.json",
    urls=tuple(dict.fromkeys(URL.format(slug) for slug, _ in MODELS.values())),
    model_ids=tuple(MODELS),
    parse=parse,
)
