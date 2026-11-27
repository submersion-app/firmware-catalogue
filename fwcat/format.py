"""Rewrites every data file in the repository's JSON spelling.

    python3.14 -m fwcat.format
"""

import sys

from . import catalogue


def main() -> int:
    for path in catalogue.data_files():
        text = path.read_text(encoding="utf-8")
        formatted = catalogue.dump(catalogue.load_json(path))
        if text != formatted:
            path.write_text(formatted, encoding="utf-8")
            print(f"formatted {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
