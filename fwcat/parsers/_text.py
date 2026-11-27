"""Small helpers shared by the parsers."""

import html
import re
from datetime import date

from ..watch import ParseError

_MONTHS = {name: number for number, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


def flat_text(page: str) -> str:
    """The page's text on one line: tags become spaces, entities are decoded."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.split())


def text_lines(page: str) -> list[str]:
    """The page's text, one non-empty line per block between tags."""
    text = re.sub(r"<(script|style)\b.*?</\1>", "\n", page, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    return [line for line in (" ".join(raw.split()) for raw in text.splitlines()) if line]


def iso_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError as error:
        raise ParseError(f"not a date: {year}-{month}-{day}") from error


def day_month_name_year(text: str) -> str:
    """'9th September 2025' or '16 March 2022' as YYYY-MM-DD."""
    match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", text.strip())
    if not match or match.group(2).casefold() not in _MONTHS:
        raise ParseError(f"not a date: {text!r}")
    return iso_date(int(match.group(3)), _MONTHS[match.group(2).casefold()], int(match.group(1)))


def month_name_day_year(text: str) -> str:
    """'October 8, 2026' as YYYY-MM-DD."""
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text.strip())
    if not match or match.group(1).casefold() not in _MONTHS:
        raise ParseError(f"not a date: {text!r}")
    return iso_date(int(match.group(3)), _MONTHS[match.group(1).casefold()], int(match.group(2)))


def dotted_day_month_year(text: str) -> str:
    """'12.5.2026' (day first, as Suunto writes it) as YYYY-MM-DD."""
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text.strip())
    if not match:
        raise ParseError(f"not a date: {text!r}")
    return iso_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
