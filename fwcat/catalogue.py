"""Loading the data files and assembling the published catalogue.

The catalogue's source is `data/<maker>.json`, one file per maker, each
holding `{"models": [...]}` in the published model format. Keeping makers
apart keeps a watcher PR for one maker from conflicting with another's.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCHEMA_PATH = ROOT / "schema" / "format-1.schema.json"
SAMPLE_PATH = ROOT / "schema" / "sample.json"
FORMAT = 1


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema() -> dict:
    return load_json(SCHEMA_PATH)


def data_files(data_dir: Path = DATA_DIR) -> list[Path]:
    return sorted(data_dir.glob("*.json"))


def load_models(data_dir: Path = DATA_DIR) -> list[tuple[Path, dict]]:
    """Every model with the file it came from, in file order."""
    found = []
    for path in data_files(data_dir):
        content = load_json(path)
        for model in content.get("models", []) if isinstance(content, dict) else []:
            found.append((path, model))
    return found


def sort_key(model: dict) -> tuple:
    return (
        str(model.get("manufacturer", "")).casefold(),
        str(model.get("model", "")).casefold(),
        str(model.get("id", "")),
    )


def build_document(models: list[dict], generated_at: datetime | None = None) -> dict:
    """The published catalogue: models sorted by maker, then model."""
    moment = (generated_at or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    return {
        "format": FORMAT,
        "generatedAt": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models": sorted(models, key=sort_key),
    }


def dump(document) -> str:
    """The repository's one JSON spelling: two-space indent, UTF-8, final newline."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"
