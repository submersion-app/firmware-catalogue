# Instructions for AI agents working in this repository

## Attribution

No output written to this repository or to GitHub may mention the AI tool,
its maker or its model in any form: no co-author or other trailers naming
them, no "generated with" lines, no session links, in commits, PR titles and
bodies, issues, comments, review replies or release notes. Write the
substantive summary only.

## Writing style

Never use an em-dash or an en-dash as punctuation, in any file, commit or
comment. Rewrite the sentence with commas, a colon, a semicolon or two
sentences.

## Data

- Every version comes from the maker's own page, read for this change, and
  that page is the release's `source`. Never guess a version or a date.
- Summaries are your own words; no copied release-note text.
- `reportedAs` only from a derivation you can show (docs/reported-as.md).
- An entry that fails `python3.14 -m fwcat.validate` is fixed or dropped,
  never forced.

## Working

- Python 3.14, standard library only.
- Run `python3.14 tests/run_tests.py` and `python3.14 -m fwcat.validate`
  before committing.
- Stage explicit paths. Commit only when asked.
