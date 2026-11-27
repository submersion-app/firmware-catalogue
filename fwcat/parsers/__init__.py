"""One watcher per maker page with a usable, stable format.

To add one: save the page with `python3.14 -m fwcat.capture <maker>` (after
adding its watcher here), write the parser and its test in
tests/test_parsers.py, and list the watcher below.
"""

from . import hwdiving, mares, shearwater, small_makers, suunto

WATCHERS = [
    shearwater.WATCHER,
    hwdiving.WATCHER,
    suunto.WATCHER,
    mares.WATCHER,
    small_makers.RATIO_WATCHER,
    small_makers.LIBERTY_WATCHER,
    small_makers.HALCYON_WATCHER,
]
