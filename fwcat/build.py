"""Builds `firmware-catalogue.json` from `data/` and writes the release notes.

    python3.14 -m fwcat.build --out build/firmware-catalogue.json \
        [--previous last.json] [--notes build/notes.md]

The build validates what it writes and refuses to write an invalid file.
With `--previous` (the last release's file) it lists what changed in the
notes, and exits with NOTHING_CHANGED when the models are identical, so the
release workflow publishes nothing new.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from . import catalogue
from .validate import validate_data_dir, validate_document

NOTHING_CHANGED = 3


def _by_id(document: dict | None) -> dict[str, dict]:
    if not document:
        return {}
    return {m["id"]: m for m in document.get("models", []) if isinstance(m, dict) and "id" in m}


def _label(model: dict) -> str:
    return f"{model['manufacturer']} {model['model']}"


def changes(previous: dict | None, current: dict) -> list[str]:
    """One line per change between two catalogues, for the release notes."""
    before, after = _by_id(previous), _by_id(current)
    lines = []
    for model_id, model in sorted(after.items(), key=lambda kv: catalogue.sort_key(kv[1])):
        old = before.get(model_id)
        if old is None:
            latest = model["releases"][0]["version"]
            lines.append(f"Added {_label(model)} (latest {latest})")
            continue
        old_versions = {r["version"] for r in old.get("releases", [])}
        new_versions = [r["version"] for r in model["releases"] if r["version"] not in old_versions]
        gone = sorted(old_versions - {r["version"] for r in model["releases"]})
        if new_versions:
            lines.append(f"{_label(model)}: new release {', '.join(new_versions)}")
        if gone:
            lines.append(f"{_label(model)}: removed release {', '.join(gone)}")
        if not new_versions and not gone and old != model:
            lines.append(f"{_label(model)}: details corrected")
    for model_id in sorted(set(before) - set(after)):
        lines.append(f"Removed {_label(before[model_id])}")
    return lines


def notes_text(lines: list[str], document: dict) -> str:
    count = len(document["models"])
    makers = len({m["manufacturer"] for m in document["models"]})
    body = [f"{count} models from {makers} makers.", ""]
    if lines:
        body.append("Changes since the last release:")
        body.append("")
        body.extend(f"- {line}" for line in lines)
    else:
        body.append("First release.")
    return "\n".join(body) + "\n"


def build(out: Path, previous: Path | None = None, notes: Path | None = None,
          today: date | None = None) -> int:
    errors = validate_data_dir(today=today)
    if errors:
        for error in errors:
            print(f"data/: {error}")
        return 1
    models = [model for _, model in catalogue.load_models()]
    document = catalogue.build_document(models)
    errors = validate_document(document, strict=True, today=today)
    if errors:
        for error in errors:
            print(f"built catalogue: {error}")
        return 1

    old = catalogue.load_json(previous) if previous else None
    lines = changes(old, document)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(catalogue.dump(document), encoding="utf-8")
    if notes:
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.write_text(notes_text(lines if old else [], document), encoding="utf-8")
    print(f"wrote {out} ({len(document['models'])} models)")
    if old is not None and not lines:
        print("nothing changed since the previous release")
        return NOTHING_CHANGED
    return 0


def next_tag(existing: list[str], today: date) -> str:
    """The next free date tag: YYYY.MM.DD, then .2, .3 on the same day."""
    base = today.strftime("%Y.%m.%d")
    if base not in existing:
        return base
    n = 2
    while f"{base}.{n}" in existing:
        n += 1
    return f"{base}.{n}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--notes", type=Path)
    arguments = parser.parse_args(argv)
    return build(arguments.out, arguments.previous, arguments.notes)


if __name__ == "__main__":
    sys.exit(main())
