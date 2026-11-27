"""Suunto: one release-notes page per product family.

Two layouts, both server-rendered:

- Ocean, Nautic and Nautic S list bare build numbers (`2.51.28`), newest
  first, sometimes followed by `Update on 12.5.2026` (day first).
- The EON collection and D5 pages use headings such as
  `EON Core software update 4.0`, `Suunto EON software update 3.0` (for the
  whole EON family) or `Version 2.5.2059`, each followed by
  `Release date 19.12.2024` or `Released 16 March 2022`.

The newest entry that names a model is that model's latest release.
"""

import re

from ..watch import Finding, ParseError, Watcher
from ._text import day_month_name_year, dotted_day_month_year, text_lines

URL = "https://www.suunto.com/Support/Software-updates/Release-notes/{}-software-updates/"
BUILD_PAGES = {
    "suunto-ocean": "suunto-ocean",
    "suunto-nautic": "suunto-nautic",
    "suunto-nautic-s": "suunto-nautic-s",
}
EON = URL.format("suunto-eon-collection")
D5 = URL.format("suunto-d5")

# What each heading name on the EON page covers.
EON_HEADINGS = {
    "eon": ("suunto-eon-core", "suunto-eon-steel", "suunto-eon-steel-black"),
    "eon core": ("suunto-eon-core",),
    "eon steel": ("suunto-eon-steel",),
    "eon steel black": ("suunto-eon-steel-black",),
}

_BUILD = re.compile(r"\d+\.\d+\.\d+")
_UPDATE_ON = re.compile(r"Update on (\d{1,2}\.\d{1,2}\.\d{4})", re.I)
_HEADING = re.compile(r"(?:Suunto\s+)?(.*?)\s*software update\s+(\d+(?:\.\d+)*)", re.I)
_RELEASED = re.compile(r"(?:Release date|Released)\s+(.+)", re.I)


def _date_after(lines: list[str], index: int) -> str | None:
    for line in lines[index + 1:index + 4]:
        released = _RELEASED.fullmatch(line)
        if released:
            value = released.group(1)
            if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", value):
                return dotted_day_month_year(value)
            return day_month_name_year(value)
        update = _UPDATE_ON.fullmatch(line)
        if update:
            return dotted_day_month_year(update.group(1))
    return None


def latest_build(page: str) -> tuple[str, str | None]:
    lines = text_lines(page)
    for index, line in enumerate(lines):
        if _BUILD.fullmatch(line):
            return line, _date_after(lines, index)
    raise ParseError("no build number on the page")


def headings(page: str) -> list[tuple[str, str, str | None]]:
    """(heading name, version, date) for every release heading, newest first."""
    lines = text_lines(page)
    found = []
    for index, line in enumerate(lines):
        match = _HEADING.fullmatch(line)
        if match:
            found.append((match.group(1).casefold(), match.group(2), _date_after(lines, index)))
            continue
        version = re.fullmatch(r"Version\s+(\d+(?:\.\d+)+)", line, re.I)
        if version:
            found.append(("", version.group(1), _date_after(lines, index)))
    return found


def parse(pages: dict[str, str]) -> list[Finding]:
    findings = []
    for model_id, slug in BUILD_PAGES.items():
        url = URL.format(slug)
        version, day = latest_build(pages[url])
        findings.append(Finding(model_id, version, url, date=day, notes_url=url))

    seen: set[str] = set()
    for name, version, day in headings(pages[EON]):
        for model_id in EON_HEADINGS.get(name, ()):
            if model_id not in seen:
                seen.add(model_id)
                findings.append(Finding(model_id, version, EON, date=day, notes_url=EON))

    d5 = headings(pages[D5])
    if not d5:
        raise ParseError("no release heading on the D5 page")
    _, version, day = d5[0]
    findings.append(Finding("suunto-d5", version, D5, date=day, notes_url=D5))
    return findings


WATCHER = Watcher(
    maker="suunto",
    data_file="suunto.json",
    urls=(*(URL.format(slug) for slug in BUILD_PAGES.values()), EON, D5),
    model_ids=(*BUILD_PAGES, "suunto-eon-core", "suunto-eon-steel", "suunto-eon-steel-black",
               "suunto-d5"),
    parse=parse,
)
