"""Heinrichs Weikamp (hwdiving): one firmware page for every OSTC family.

The page is WordPress; its REST endpoint returns the page content, where each
download carries text such as `hwOS tech for OSTC 3 / ... (v3.38)` or
`hwOS4 for OSTC 4 and OSTC 5 (V 1.7.5)`. The REST JSON changes less than the
theme's HTML, so the parser reads it.

hwOS tech and sport both run on the OSTC plus, 2, 2 TR and nano, and a diver
chooses which, so those models are not in the catalogue; this parser covers
the models that run one line only. libdivecomputer packs the version into a
number (see docs/reported-as.md), which the findings carry as `reportedAs`.
"""

import html
import json
import re

from ..watch import Finding, ParseError, Watcher

API_URL = "https://hwdiving.com/wp-json/wp/v2/pages/2215"
PAGE_URL = "https://hwdiving.com/firmware/?lang=en"
CHANGELOG = "https://www.heinrichsweikamp.net/autofirmware/{}_changelog.txt"

FAMILIES = {
    "hwOS4": (("heinrichs-weikamp-ostc-4", "heinrichs-weikamp-ostc-5"), "ostc4"),
    "hwOS tech": (("heinrichs-weikamp-ostc-3", "heinrichs-weikamp-ostc-cr"), "hwos_tech"),
    "hwOS sport": (("heinrichs-weikamp-ostc-sport",), "hwos_sport"),
}

_ENTRY = re.compile(r"(hwOS4|hwOS tech|hwOS sport)\s+for\s+[^()]{1,120}?\(\s*[Vv]\s?(\d+(?:\.\d+)+)\s*\)")


def reported_as(family: str, version: str) -> str:
    """The number libdivecomputer reports for this version (hw_ostc3.c)."""
    parts = [int(p) for p in version.split(".")]
    if family == "hwOS4":
        if len(parts) != 3:
            raise ParseError(f"hwOS4 version {version!r} is not major.minor.patch")
        major, minor, patch = parts
        return str((major << 11) | (minor << 6) | (patch << 1))
    if len(parts) != 2:
        raise ParseError(f"{family} version {version!r} is not major.minor")
    return str((parts[0] << 8) | parts[1])


def parse(pages: dict[str, str]) -> list[Finding]:
    try:
        content = json.loads(pages[API_URL])["content"]["rendered"]
    except (ValueError, KeyError, TypeError) as error:
        raise ParseError(f"the page JSON has no content: {error}") from error
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", content)).split())
    versions: dict[str, str] = {}
    for family, version in _ENTRY.findall(text):
        if versions.setdefault(family, version) != version:
            raise ParseError(f"{family} is listed with two versions")
    findings = []
    for family, (model_ids, changelog) in FAMILIES.items():
        if family not in versions:
            raise ParseError(f"no {family} entry on the page")
        version = versions[family]
        for model_id in model_ids:
            findings.append(Finding(
                model_id=model_id,
                version=version,
                source=PAGE_URL,
                notes_url=CHANGELOG.format(changelog),
                reported_as=(reported_as(family, version),),
            ))
    return findings


WATCHER = Watcher(
    maker="heinrichs-weikamp",
    data_file="heinrichs-weikamp.json",
    urls=(API_URL,),
    model_ids=tuple(m for ids, _ in FAMILIES.values() for m in ids),
    parse=parse,
)
