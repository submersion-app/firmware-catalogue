"""Checks the catalogue: the schema, then the rules a schema cannot say.

    python3.14 -m fwcat.validate                 # data/ (strict) and the sample
    python3.14 -m fwcat.validate --file out.json # any built catalogue

The rules guard the app's promise never to claim a false update:

- every `id` is unique;
- releases run newest first wherever two releases both have a date;
- no release date lies in the future;
- one spelling (`version` or `reportedAs`, trimmed and case-folded, as the
  app compares them) names one release only, so a reported version can
  never match two releases;
- no two models could match one item: they may not share a maker name, a
  model name and an equipment type after the app's normalising;
- every URL is a well-formed https URL, and every release has a `source`.
"""

import argparse
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from . import catalogue
from .schema_lite import SchemaChecker

URL_KEYS = ("firmwarePageUrl", "notesUrl", "instructionsUrl", "source")
_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalise_name(value: str) -> str:
    """Case, spaces and punctuation removed, as the app matches names."""
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def normalise_version(value: str) -> str:
    """Trimmed and case-folded, as the app compares versions."""
    return value.strip().casefold()


def url_problem(value) -> str | None:
    """Why `value` is not a well-formed https URL, or None when it is."""
    if not isinstance(value, str):
        return "is not a string"
    if any(ch.isspace() for ch in value) or any(ord(ch) < 32 for ch in value):
        return "holds whitespace or a control character"
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        return f"does not parse ({error})"
    if parts.scheme != "https":
        return "is not https"
    if parts.username or parts.password:
        return "carries credentials"
    if port is not None:
        return "names a port"
    if not parts.hostname or not _HOST.match(parts.hostname):
        return "has no valid host name"
    return None


def _names(model: dict, key: str, aliases_key: str) -> set[str]:
    names = []
    if isinstance(model.get(key), str):
        names.append(model[key])
    names.extend(x for x in model.get(aliases_key, []) or [] if isinstance(x, str))
    return {normalise_name(n) for n in names if normalise_name(n)}


def semantic_errors(document: dict, today: date | None = None) -> list[str]:
    """Every rule the schema cannot express. Assumes the schema passed."""
    today = today or datetime.now(UTC).date()
    latest_allowed = today + timedelta(days=1)  # a maker a timezone ahead
    errors: list[str] = []
    models = document.get("models", [])

    seen_ids: dict[str, int] = {}
    for index, model in enumerate(models):
        where = f"model {model.get('id', index)!r}"
        model_id = model.get("id")
        if model_id in seen_ids:
            errors.append(f"{where}: id is also used by model #{seen_ids[model_id]}")
        else:
            seen_ids[model_id] = index

        if "firmwarePageUrl" in model:
            problem = url_problem(model["firmwarePageUrl"])
            if problem:
                errors.append(f"{where}: firmwarePageUrl {problem}")

        spellings: dict[str, str] = {}
        dated: list[tuple[int, date, str]] = []
        for position, release in enumerate(model.get("releases", [])):
            version = release.get("version", "")
            here = f"{where} release {version!r}"
            for spelling in [version, *(release.get("reportedAs", []) or [])]:
                key = normalise_version(spelling)
                if key in spellings and spellings[key] != version:
                    errors.append(
                        f"{here}: spelling {spelling!r} also names release {spellings[key]!r}"
                    )
                elif key in spellings and spelling != version:
                    errors.append(f"{here}: reportedAs {spelling!r} repeats the version")
                elif key in spellings:
                    errors.append(f"{here}: version is listed twice")
                else:
                    spellings[key] = version
            for key in URL_KEYS:
                if key in release:
                    problem = url_problem(release[key])
                    if problem:
                        errors.append(f"{here}: {key} {problem}")
            if not release.get("source"):
                errors.append(f"{here}: missing source")
            if "date" in release:
                try:
                    day = date.fromisoformat(release["date"])
                except (TypeError, ValueError):
                    continue  # the schema already reported it
                if day > latest_allowed:
                    errors.append(f"{here}: date {day} is in the future")
                dated.append((position, day, version))
            summary = release.get("summary")
            if isinstance(summary, str) and any(ord(ch) < 32 for ch in summary):
                errors.append(f"{here}: summary holds a line break or control character")

        for (_, newer_day, newer), (_, older_day, older) in zip(dated, dated[1:]):
            if newer_day < older_day:
                errors.append(
                    f"{where}: release {newer!r} ({newer_day}) is listed above "
                    f"{older!r} ({older_day}); releases run newest first"
                )

    for i, first in enumerate(models):
        for second in models[i + 1:]:
            shared_types = set(first.get("equipmentTypes", [])) & set(second.get("equipmentTypes", []))
            if not shared_types:
                continue
            makers = _names(first, "manufacturer", "manufacturerAliases") & _names(
                second, "manufacturer", "manufacturerAliases"
            )
            names = _names(first, "model", "aliases") & _names(second, "model", "aliases")
            if makers and names:
                errors.append(
                    f"models {first.get('id')!r} and {second.get('id')!r} could match the same "
                    f"item (maker {sorted(makers)[0]!r}, name {sorted(names)[0]!r}, "
                    f"type {sorted(shared_types)[0]!r})"
                )
    return errors


def validate_document(document, *, strict: bool, today: date | None = None) -> list[str]:
    checker = SchemaChecker(catalogue.load_schema())
    errors = checker.check(document, strict=strict)
    if errors:
        return errors  # the semantic rules assume a well-shaped document
    return semantic_errors(document, today)


def validate_data_dir(data_dir: Path = catalogue.DATA_DIR, today: date | None = None) -> list[str]:
    """The repository's data files, checked strictly and as one catalogue."""
    errors: list[str] = []
    files = catalogue.data_files(data_dir)
    if not files:
        return [f"{data_dir}: no data files"]
    models = []
    for path in files:
        try:
            content = catalogue.load_json(path)
        except ValueError as error:
            errors.append(f"{path.name}: not valid JSON ({error})")
            continue
        if not isinstance(content, dict) or set(content) != {"models"}:
            errors.append(f"{path.name}: must be an object holding only 'models'")
            continue
        if not isinstance(content["models"], list) or not content["models"]:
            errors.append(f"{path.name}: 'models' must be a non-empty list")
            continue
        if path.read_text(encoding="utf-8") != catalogue.dump(content):
            errors.append(
                f"{path.name}: not in the repository's JSON spelling; "
                "run python3.14 -m fwcat.format"
            )
        models.extend(content["models"])
    if errors:
        return errors
    document = catalogue.build_document(models)
    return validate_document(document, strict=True, today=today)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, help="check one built catalogue instead")
    arguments = parser.parse_args(argv)

    if arguments.file:
        results = {str(arguments.file): validate_document(
            catalogue.load_json(arguments.file), strict=False)}
    else:
        results = {
            "data/": validate_data_dir(),
            "schema/sample.json": validate_document(
                catalogue.load_json(catalogue.SAMPLE_PATH), strict=False),
        }
    failed = False
    for name, errors in results.items():
        for error in errors:
            print(f"{name}: {error}")
        failed = failed or bool(errors)
        if not errors:
            print(f"{name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
