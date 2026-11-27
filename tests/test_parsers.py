"""Each parser against its saved maker pages (tests/fixtures/<maker>/)."""

import json
import unittest
from datetime import date

from fwcat.capture import load_fixture
from fwcat.parsers import WATCHERS, hwdiving, mares, shearwater, small_makers, suunto
from fwcat.parsers._text import day_month_name_year, dotted_day_month_year, month_name_day_year
from fwcat.watch import ParseError, run

TODAY = date(2026, 11, 27)


def pages(watcher):
    return {url: load_fixture(watcher.maker, url) for url in watcher.urls}


def versions(watcher):
    return {f.model_id: f.version for f in watcher.parse(pages(watcher))}


class SavedPagesTest(unittest.TestCase):
    """What each maker page showed when it was saved (2026-11-27)."""

    def test_shearwater(self):
        found = {f.model_id: f for f in shearwater.WATCHER.parse(pages(shearwater.WATCHER))}
        self.assertEqual({k: f.version for k, f in found.items()}, {
            "shearwater-perdix-3": "V39", "shearwater-perdix-2": "V102",
            "shearwater-perdix-ai": "V102", "shearwater-perdix": "V93",
            "shearwater-petrel-3": "V103", "shearwater-petrel-2": "V97",
            "shearwater-petrel": "V72", "shearwater-nerd-2": "V102", "shearwater-nerd": "V10",
            "shearwater-teric": "V37", "shearwater-tern": "V36", "shearwater-tern-tx": "V37",
            "shearwater-peregrine": "V89", "shearwater-peregrine-tx": "V104",
            "shearwater-predator": "V63",
        })
        self.assertEqual(found["shearwater-perdix-2"].reported_as, ("102",))
        self.assertIn("Perdix_2-Release-Notes-v102-English.pdf", found["shearwater-perdix-2"].notes_url)
        self.assertIsNone(found["shearwater-petrel"].notes_url)

    def test_heinrichs_weikamp(self):
        found = {f.model_id: (f.version, f.reported_as) for f in hwdiving.WATCHER.parse(pages(hwdiving.WATCHER))}
        self.assertEqual(found, {
            "heinrichs-weikamp-ostc-4": ("1.7.5", ("2506",)),
            "heinrichs-weikamp-ostc-5": ("1.7.5", ("2506",)),
            "heinrichs-weikamp-ostc-3": ("3.38", ("806",)),
            "heinrichs-weikamp-ostc-cr": ("3.38", ("806",)),
            "heinrichs-weikamp-ostc-sport": ("10.99", ("2659",)),
        })

    def test_suunto(self):
        found = {f.model_id: (f.version, f.date) for f in suunto.WATCHER.parse(pages(suunto.WATCHER))}
        self.assertEqual(found["suunto-nautic-s"], ("2.54.12", "2026-06-16"))
        self.assertEqual(found["suunto-nautic"], ("2.55.46", None))
        self.assertEqual(found["suunto-ocean"][0], "2.51.28")
        self.assertEqual(found["suunto-eon-core"], ("4.0", "2024-12-19"))
        self.assertEqual(found["suunto-eon-steel"], ("3.0", "2022-03-16"))
        self.assertEqual(found["suunto-eon-steel-black"], ("3.0", "2022-03-16"))
        self.assertEqual(found["suunto-d5"], ("3.0", "2022-03-16"))

    def test_mares(self):
        self.assertEqual(versions(mares.WATCHER), {
            "mares-genius": "V1.06.07", "mares-horizon": "V01.11.01", "mares-puck-4": "V01.06.00",
            "mares-puck-pro-ultra": "V01.06.00", "mares-quad-2": "V01.02.00",
            "mares-quad-ci": "V02.01.01", "mares-sirius": "V01.10.00", "mares-smart-air": "V01.00.08",
        })

    def test_ratio(self):
        self.assertEqual(versions(small_makers.RATIO_WATCHER), {
            "ratio-ix3m-2": "5.2.11", "ratio-idive-color": "4.1.34",
            "ratio-wireless-transmitter": "1.0.8",
        })

    def test_divesoft(self):
        [finding] = small_makers.LIBERTY_WATCHER.parse(pages(small_makers.LIBERTY_WATCHER))
        self.assertEqual((finding.version, finding.date), ("2.18.3-10252", "2025-09-09"))

    def test_halcyon(self):
        [finding] = small_makers.HALCYON_WATCHER.parse(pages(small_makers.HALCYON_WATCHER))
        self.assertEqual((finding.version, finding.date), ("V2.36.12", "2026-10-08"))

    def test_every_watcher_agrees_with_the_catalogue(self):
        # On the saved pages the only version the catalogue lacks is Tern TX
        # V37: the page says V37, but Shearwater's notes call V37 Teric-only,
        # so the catalogue stops at V36 and a person decides on the PR.
        def fetcher(url):
            maker = next(w.maker for w in WATCHERS if url in w.urls)
            return load_fixture(maker, url)

        plan = run(WATCHERS, fetcher, today=TODAY)
        self.assertEqual(plan.failures, [])
        self.assertEqual([(p["modelId"], p["entry"]["version"]) for p in plan.proposals],
                         [("shearwater-tern-tx", "V37")])
        self.assertEqual(sorted(plan.healthy), sorted(w.maker for w in WATCHERS))


class BrokenPageTest(unittest.TestCase):
    """A redesigned page is a ParseError, never a guess."""

    def test_every_watcher_rejects_an_empty_page(self):
        for watcher in WATCHERS:
            with self.subTest(watcher.maker), self.assertRaises(ParseError):
                watcher.parse({url: "<html><body>Page moved</body></html>" for url in watcher.urls})

    def test_saved_pages_carry_no_embedded_keys(self):
        from fwcat.capture import EMBEDDED_KEY

        for watcher in WATCHERS:
            for url, text in pages(watcher).items():
                leaked = [m.group(2) for m in EMBEDDED_KEY.finditer(text) if m.group(2) != "REDACTED"]
                self.assertEqual(leaked, [], url)

    def test_watchers_cover_catalogue_models_only_once(self):
        ids = [model_id for w in WATCHERS for model_id in w.model_ids]
        self.assertEqual(len(ids), len(set(ids)))


class ShearwaterTest(unittest.TestCase):
    def line(self, text):
        return f"<div><p><strong>Current Firmware Version: {text}</strong></p><p>Here you will find</p></div>"

    def test_variants(self):
        self.assertEqual(shearwater.current_versions(self.line("V102")), {None: 102})
        self.assertEqual(shearwater.current_versions(self.line("V36 ")), {None: 36})
        self.assertEqual(
            shearwater.current_versions(
                "<strong>Current Firmware Version: </strong>V97 (Petrel 2) | V72 (Petrel 1)"),
            {"Petrel 2": 97, "Petrel 1": 72})

    def test_missing_line(self):
        with self.assertRaises(ParseError):
            shearwater.current_versions("<p>Current firmware: see the app</p>")

    def test_notes_must_name_the_version(self):
        page = '<li>Notes - <a href="https://cdn.example.org/Perdix-Release-Notes-v101-English.pdf?v=1">English</a></li>'
        self.assertIsNone(shearwater.notes_url(page, 102))
        self.assertIsNone(shearwater.notes_url(page, 10))
        self.assertTrue(shearwater.notes_url(page, 101))


class HeinrichsWeikampTest(unittest.TestCase):
    def test_reported_as_follows_libdivecomputer(self):
        self.assertEqual(hwdiving.reported_as("hwOS4", "1.7.5"), "2506")
        self.assertEqual(hwdiving.reported_as("hwOS tech", "3.38"), "806")
        self.assertEqual(hwdiving.reported_as("hwOS sport", "10.99"), "2659")
        with self.assertRaises(ParseError):
            hwdiving.reported_as("hwOS4", "1.7")

    def test_two_versions_for_one_family_fail(self):
        content = ("hwOS tech for OSTC 3 (v3.38) hwOS tech for OSTC 3 (v3.39) "
                   "hwOS sport for OSTC sport (v10.99) hwOS4 for OSTC 4 (V 1.7.5)")
        page = json.dumps({"content": {"rendered": content}})
        with self.assertRaises(ParseError):
            hwdiving.parse({hwdiving.API_URL: page})


class MaresTest(unittest.TestCase):
    def page(self, name, sku):
        product = {"@type": "Product", "name": name, "sku": sku}
        return f'<script type="application/ld+json">{json.dumps(product)}</script>'

    def test_a_page_reused_for_another_download_fails(self):
        all_pages = {mares.URL.format(slug): self.page("FW. X V1.0", sku)
                     for slug, sku in mares.MODELS.values()}
        self.assertEqual(len(mares.parse(all_pages)), len(mares.MODELS))
        slug, _ = mares.MODELS["mares-genius"]
        all_pages[mares.URL.format(slug)] = self.page("FW. Other V9.9", "MA-FIRM-999")
        with self.assertRaises(ParseError):
            mares.parse(all_pages)


class DatesTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(day_month_name_year("9th September 2025"), "2025-09-09")
        self.assertEqual(day_month_name_year("16 March 2022"), "2022-03-16")
        self.assertEqual(month_name_day_year("October 8, 2026"), "2026-10-08")
        self.assertEqual(dotted_day_month_year("12.5.2026"), "2026-05-12")
        for bad in ["31.2.2026", "Smarch 3 2026"]:
            with self.assertRaises(ParseError):
                dotted_day_month_year(bad) if "." in bad else month_name_day_year(bad)


if __name__ == "__main__":
    unittest.main()
