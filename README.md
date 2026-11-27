# Submersion firmware catalogue

The latest firmware releases of dive computers and other electronic diving
gear, for [Submersion](https://github.com/submersion-app/submersion), a dive
log app. The app records which firmware each of a diver's items runs and,
using this list, tells the diver when the maker has published a newer one,
with the release notes and the maker's update instructions one tap away.

Submersion never installs or downloads firmware. It compares versions and
links to the maker.

## How the app reads it

Each release of this repository carries one asset, `firmware-catalogue.json`.
The app fetches

```
https://github.com/submersion-app/firmware-catalogue/releases/latest/download/firmware-catalogue.json
```

at most once a day: a plain GET with no query and no diver data. All
matching happens on the device. A merged change to `data/` publishes a new
release on its own (tagged `YYYY.MM.DD`, then `.2`, `.3` on the same day).

## The format (format 1)

The full contract is [schema/format-1.schema.json](schema/format-1.schema.json),
and [schema/sample.json](schema/sample.json) is the sample both this
repository and the app test against (it is the app's
`test/fixtures/firmware_catalogue/sample.json`, byte for byte).

```json
{
  "format": 1,
  "generatedAt": "2026-11-27T00:00:00Z",
  "models": [
    {
      "id": "shearwater-perdix-2",
      "manufacturer": "Shearwater",
      "manufacturerAliases": ["Shearwater Research"],
      "model": "Perdix 2",
      "aliases": ["Perdix2"],
      "equipmentTypes": ["computer"],
      "firmwarePageUrl": "https://...",
      "releases": [
        {
          "version": "V95",
          "reportedAs": ["95"],
          "date": "2026-10-01",
          "notesUrl": "https://...",
          "instructionsUrl": "https://...",
          "summary": "Short plain-text summary of what changed.",
          "safety": false,
          "source": "https://..."
        }
      ]
    }
  ]
}
```

| Key | Meaning |
| --- | --- |
| `format` | Integer. The app ignores a file whose format it does not know and keeps its last good copy. |
| `id` | Stable, unique, lowercase with hyphens. Never shown, never reused. |
| `manufacturer`, `model` | The maker's spelling. |
| `manufacturerAliases` | Other maker spellings and former brand names ("Uwatec" under Scubapro). |
| `aliases` | Other model spellings divers or devices use. |
| `equipmentTypes` | The app's `EquipmentType` names (`computer`, `transmitter`, `rebreather`, `dpv`, `light`, `camera`, `housing`, `strobe`, ...). Narrows matching, so a "Quad" computer never matches a light called "Quad". |
| `releases` | Newest first. Order, not version parsing, decides what is newer, because makers write versions differently. |
| `version` | The maker's spelling. |
| `reportedAs` | Other spellings of the same release: what libdivecomputer or the maker's cloud reports. See [docs/reported-as.md](docs/reported-as.md). |
| `date`, `notesUrl`, `instructionsUrl`, `summary`, `safety`, `firmwarePageUrl` | Optional. `safety` is true only when the maker calls the release a safety or critical fix. |
| `source` | **Required on every release**: the page the version was read on. The app ignores it; it is the entry's provenance. |

The app ignores keys it does not know, so a new optional field needs no app
release. This repository's own data is checked strictly, so a misspelt key
fails CI.

## Adding or updating an entry

The data lives in `data/`, one file per maker. To add a release, put it at
the **top** of the model's `releases`:

1. Read the version on the maker's own page (release notes, firmware page,
   or the maker's published changelog). Never guess a version, never take
   one from a forum or a reseller, and never infer one from a pattern.
   Fewer correct entries beat many guessed ones: a wrong version makes the
   app tell divers an update exists when it does not.
2. Set `source` to the page you read it on. Every release needs one.
3. Add `date`, `notesUrl` and `instructionsUrl` when the maker publishes
   them, and a one-line `summary` in your own words (no copied text).
4. Add `reportedAs` only when you can establish what the device reports
   (see [docs/reported-as.md](docs/reported-as.md)).
5. Run the checks and open a PR:

```bash
python3.14 -m fwcat.format      # rewrite data/ in the house JSON spelling
python3.14 -m fwcat.validate    # schema and rules, data and sample
python3.14 tests/run_tests.py   # every test
```

A new model needs an `id` that will never change, the maker's spelling of
the maker and model, and the `equipmentTypes` it can be filed under. The
validator refuses two models that could match the same item (same maker,
model name and equipment type after normalising case, spaces and
punctuation), two releases sharing a spelling, releases out of date order,
dates in the future, and any URL that is not a well-formed https URL.

## The watcher

`.github/workflows/watch.yml` runs daily. For each maker page with a usable,
stable format there is a small parser in `fwcat/parsers/`, tested against a
saved copy of the page in `tests/fixtures/`. When a page shows a version the
catalogue does not know, the watcher opens a PR adding it at the top of that
model's releases, for a person to check against the page, complete
(`summary`, `safety`) and merge. When a page cannot be fetched or no longer
parses, it opens or updates an issue instead of guessing, and closes that
issue after the next clean read. It never commits to main.

Watched today: Shearwater, Heinrichs Weikamp (hwdiving), Suunto, Mares,
Ratio, Divesoft (Liberty) and Halcyon (Symbios). Garmin is seeded but not
watched: its announcements live in forum threads that Garmin edits after
posting.

To add a parser: write it in `fwcat/parsers/`, list its watcher in
`fwcat/parsers/__init__.py`, save its pages with
`python3.14 -m fwcat.capture <maker>` (gzipped, with any key the page embeds
for its own scripts redacted), and add its test to `tests/test_parsers.py`.
When a maker redesigns a page, re-capture it and fix the parser until the
test passes.

## Releases

`.github/workflows/release.yml` builds `firmware-catalogue.json` from
`data/` (`python3.14 -m fwcat.build`), compares it with the last release, and
publishes a new release when the models changed. It can also be run by hand
from the Actions tab.

## Working on this repository

Python 3.14, standard library only. No em-dash or en-dash as punctuation in
any file (CI checks).

## Licence

GNU General Public License v3.0, as the app is. See [LICENSE](LICENSE).
Version numbers and dates are the makers' published facts; summaries are
written for this catalogue. Maker and model names are their owners'
trademarks.
