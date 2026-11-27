"""Reads the makers' firmware pages and plans the PRs and issues to open.

    python3.14 -m fwcat.watch --plan build/plan.json [--only shearwater]

Each watcher in `fwcat/parsers/` names its pages, the catalogue models it
covers and a parser. A run fetches the pages, parses them, and compares the
latest version the page shows for each model with the catalogue:

- a version the catalogue does not know becomes a proposal (a new release
  at the top of that model's list, for a PR a person checks and merges);
- a page that cannot be fetched, a parser that raises, or a parser that
  finds no version for a model it covers becomes a failure (an issue). A
  failure never guesses: nothing is proposed for that watcher.

Nothing here writes to the repository; `fwcat.publish` acts on the plan.
"""

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from . import catalogue
from .validate import normalise_version

USER_AGENT = "firmware-catalogue-watcher/1.0 (+https://github.com/submersion-app/firmware-catalogue)"
MAX_BYTES = 5_000_000
TIMEOUT_SECONDS = 30
_VERSION = re.compile(r"^\S(.{0,58}\S)?$")


class ParseError(Exception):
    """The page no longer looks the way the parser expects."""


@dataclass(frozen=True)
class Finding:
    """The latest release a page shows for one catalogue model."""

    model_id: str
    version: str
    source: str
    date: str | None = None
    notes_url: str | None = None
    reported_as: tuple[str, ...] = ()


@dataclass(frozen=True)
class Watcher:
    maker: str
    """Short name, also used in branch names and issue titles."""
    data_file: str
    """The file under data/ holding this maker's models."""
    urls: tuple[str, ...]
    """Every page the parser reads."""
    model_ids: tuple[str, ...]
    """The catalogue models this watcher covers; each must get a finding."""
    parse: Callable[[dict[str, str]], list[Finding]]
    """Page text by URL in, one finding per covered model out."""


@dataclass
class Plan:
    proposals: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    healthy: list[str] = field(default_factory=list)


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ParseError(f"{url} is larger than {MAX_BYTES} bytes")
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")


def known_spellings(model: dict) -> set[str]:
    spellings = set()
    for release in model.get("releases", []):
        spellings.add(normalise_version(release["version"]))
        spellings.update(normalise_version(s) for s in release.get("reportedAs", []))
    return spellings


def entry_for(finding: Finding) -> dict:
    """The release entry a proposal adds, in the catalogue's key order."""
    entry: dict = {"version": finding.version}
    if finding.reported_as:
        entry["reportedAs"] = list(finding.reported_as)
    if finding.date:
        entry["date"] = finding.date
    if finding.notes_url:
        entry["notesUrl"] = finding.notes_url
    entry["source"] = finding.source
    return entry


def branch_name(model_id: str, version: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", version.casefold()).strip("-") or "version"
    return f"watcher/{model_id}-{slug}"


def failure(watcher: Watcher, reason: str) -> dict:
    return {
        "maker": watcher.maker,
        "title": failure_title(watcher.maker),
        "reason": reason,
        "urls": list(watcher.urls),
    }


def failure_title(maker: str) -> str:
    return f"Watcher: the {maker} firmware page could not be read"


def proposal_body(model: dict, finding: Finding) -> str:
    lines = [
        f"The watcher read a new firmware version for {model['manufacturer']} {model['model']}.",
        "",
        f"- Version: `{finding.version}`",
    ]
    if finding.reported_as:
        lines.append(f"- Reported by the device as: {', '.join(f'`{s}`' for s in finding.reported_as)}")
    if finding.date:
        lines.append(f"- Date: {finding.date}")
    if finding.notes_url:
        lines.append(f"- Release notes: {finding.notes_url}")
    lines += [
        f"- Read on: {finding.source}",
        "",
        "Before merging, open the page and check that the version (and date) are right,",
        "then add a one-line `summary` in your own words and set `safety` to true if the",
        "maker calls it a safety or critical fix. Merging publishes a new catalogue release.",
    ]
    return "\n".join(lines) + "\n"


def run(watchers: list[Watcher], fetcher: Callable[[str], str] = fetch,
        data_dir: Path = catalogue.DATA_DIR, today: date | None = None) -> Plan:
    models = {m["id"]: (path, m) for path, m in catalogue.load_models(data_dir)}
    today_text = (today or date.today()).isoformat()
    plan = Plan()
    for watcher in watchers:
        try:
            pages = {url: fetcher(url) for url in watcher.urls}
        except Exception as error:  # noqa: BLE001  any fetch problem is a failure
            plan.failures.append(failure(watcher, f"fetching failed: {error}"))
            continue
        try:
            findings = watcher.parse(pages)
        except Exception as error:  # noqa: BLE001  a parser bug or a redesign
            plan.failures.append(failure(watcher, f"parsing failed: {type(error).__name__}: {error}"))
            continue

        problems = []
        by_model = {}
        for finding in findings:
            if finding.model_id not in watcher.model_ids:
                problems.append(f"found {finding.model_id!r}, which this watcher does not cover")
            elif finding.model_id in by_model:
                problems.append(f"found {finding.model_id!r} twice")
            elif not _VERSION.match(finding.version):
                problems.append(f"{finding.model_id}: {finding.version!r} does not look like a version")
            elif finding.date and finding.date > today_text:
                problems.append(f"{finding.model_id}: date {finding.date} is in the future")
            else:
                by_model[finding.model_id] = finding
        for model_id in watcher.model_ids:
            if model_id not in models:
                problems.append(f"{model_id!r} is not in the catalogue")
            elif model_id not in by_model:
                problems.append(f"no version found for {model_id!r}")
        if problems:
            plan.failures.append(failure(watcher, "; ".join(problems)))
            continue

        proposals = []
        for model_id, finding in by_model.items():
            path, model = models[model_id]
            spellings = known_spellings(model)
            if normalise_version(finding.version) in spellings:
                continue
            newest = model["releases"][0]
            if finding.date and newest.get("date") and finding.date < newest["date"]:
                problems.append(
                    f"{model_id}: the page shows {finding.version} ({finding.date}), "
                    f"older than the catalogue's newest {newest['version']} ({newest['date']})"
                )
                continue
            proposals.append({
                "maker": watcher.maker,
                "modelId": model_id,
                "file": path.name,
                "entry": entry_for(finding),
                "branch": branch_name(model_id, finding.version),
                "title": f"{model['manufacturer']} {model['model']}: firmware {finding.version}",
                "body": proposal_body(model, finding),
            })
        if problems:
            plan.failures.append(failure(watcher, "; ".join(problems)))
            continue
        plan.proposals.extend(proposals)
        plan.healthy.append(watcher.maker)
    return plan


def main(argv=None) -> int:
    from .parsers import WATCHERS

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--only", action="append", help="run only these makers")
    arguments = parser.parse_args(argv)
    watchers = [w for w in WATCHERS if not arguments.only or w.maker in arguments.only]
    plan = run(watchers)
    arguments.plan.parent.mkdir(parents=True, exist_ok=True)
    arguments.plan.write_text(json.dumps(asdict(plan), indent=2) + "\n", encoding="utf-8")
    for item in plan.proposals:
        print(f"new: {item['title']}")
    for item in plan.failures:
        print(f"failed: {item['maker']}: {item['reason']}")
    for maker in plan.healthy:
        print(f"read: {maker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
