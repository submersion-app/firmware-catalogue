"""Makers with a single short firmware page each: Ratio, Divesoft, Halcyon.

- Ratio: each update page opens with the version (`OS 5.2.11 .x`,
  `OS 4.1.34`, `1.0.8`). No dates.
- Divesoft Liberty: newest first, `Liberty 2.18.3-10252` then
  `9th September 2025`.
- Halcyon: a news post kept up to date, `Release Date: October 8, 2026`
  followed by `Symbios Handset & HUD Firmware V2.36.12`.
"""

import re

from ..watch import Finding, ParseError, Watcher
from ._text import day_month_name_year, month_name_day_year, text_lines

RATIO = "https://www.ratio-computers.com/update/{}/index.htm"
RATIO_MODELS = {
    "ratio-ix3m-2": "ix3m2",
    "ratio-idive-color": "color",
    "ratio-wireless-transmitter": "transmitter",
}
LIBERTY = "https://www.divesoft.com/en/downloads/ccr-liberty-rebreather/firmware"
HALCYON = "https://halcyon.net/news/latest-symbios-firmware-updates-and-enhancements"

_RATIO_VERSION = re.compile(r"(?:OS\s*)?(\d+\.\d+\.\d+)(?:\s*\.x)?")
_LIBERTY = re.compile(r"Liberty\s+(\d+\.\d+\.\d+(?:-\d+)?)")
_HALCYON = re.compile(r"Symbios Handset(?: & HUD)? Firmware (V\d+(?:\.\d+)+)", re.I)
_RELEASE_DATE = re.compile(r"Release Date:\s*(.+)", re.I)


def parse_ratio(pages: dict[str, str]) -> list[Finding]:
    findings = []
    for model_id, slug in RATIO_MODELS.items():
        url = RATIO.format(slug)
        version = next((m.group(1) for line in text_lines(pages[url])
                        if (m := _RATIO_VERSION.fullmatch(line))), None)
        if version is None:
            raise ParseError(f"no version at the top of {url}")
        findings.append(Finding(model_id, version, url, notes_url=url))
    return findings


def parse_liberty(pages: dict[str, str]) -> list[Finding]:
    lines = text_lines(pages[LIBERTY])
    for index, line in enumerate(lines):
        match = _LIBERTY.fullmatch(line)
        if match:
            day = None
            if index + 1 < len(lines):
                try:
                    day = day_month_name_year(lines[index + 1])
                except ParseError:
                    day = None
            return [Finding("divesoft-liberty", match.group(1), LIBERTY, date=day, notes_url=LIBERTY)]
    raise ParseError("no 'Liberty x.y.z' release on the page")


def parse_halcyon(pages: dict[str, str]) -> list[Finding]:
    lines = text_lines(pages[HALCYON])
    day = None
    for line in lines:
        released = _RELEASE_DATE.fullmatch(line)
        if released:
            day = month_name_day_year(released.group(1))
            continue
        match = _HALCYON.search(line)
        if match:
            return [Finding("halcyon-symbios-handset", match.group(1), HALCYON,
                            date=day, notes_url=HALCYON)]
    raise ParseError("no 'Symbios Handset Firmware' release on the page")


RATIO_WATCHER = Watcher(
    maker="ratio",
    data_file="ratio.json",
    urls=tuple(RATIO.format(slug) for slug in RATIO_MODELS.values()),
    model_ids=tuple(RATIO_MODELS),
    parse=parse_ratio,
)
LIBERTY_WATCHER = Watcher(
    maker="divesoft",
    data_file="divesoft.json",
    urls=(LIBERTY,),
    model_ids=("divesoft-liberty",),
    parse=parse_liberty,
)
HALCYON_WATCHER = Watcher(
    maker="halcyon",
    data_file="halcyon.json",
    urls=(HALCYON,),
    model_ids=("halcyon-symbios-handset",),
    parse=parse_halcyon,
)
