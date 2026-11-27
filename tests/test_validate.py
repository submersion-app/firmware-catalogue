import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fwcat import catalogue
from fwcat.schema_lite import SchemaChecker
from fwcat.validate import (
    normalise_name,
    url_problem,
    validate_data_dir,
    validate_document,
)

TODAY = date(2026, 11, 27)


def sample() -> dict:
    return catalogue.load_json(catalogue.SAMPLE_PATH)


def minimal_model(**overrides) -> dict:
    model = {
        "id": "maker-thing",
        "manufacturer": "Maker",
        "model": "Thing",
        "equipmentTypes": ["computer"],
        "releases": [{"version": "1.0", "source": "https://maker.example.org/fw"}],
    }
    model.update(overrides)
    return model


def document(*models) -> dict:
    return {"format": 1, "generatedAt": "2026-11-27T00:00:00Z", "models": list(models)}


class SharedSampleTest(unittest.TestCase):
    """The sample both repositories test against."""

    def test_the_shared_sample_is_valid(self):
        self.assertEqual(validate_document(sample(), strict=False, today=TODAY), [])

    def test_the_sample_carries_an_unknown_key_the_app_ignores(self):
        # The format is open to new keys; only the repository's data is strict.
        errors = validate_document(sample(), strict=True, today=TODAY)
        self.assertEqual(len(errors), 1)
        self.assertIn("futureField", errors[0])

    def test_the_sample_is_the_app_repositorys_file_byte_for_byte(self):
        # Pinned to the hash of submersion's test/fixtures/firmware_catalogue/sample.json.
        import hashlib

        digest = hashlib.sha1(catalogue.SAMPLE_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, "bb182b85c75efc8bbc5b51e8087c9a16e745d25f")


class SchemaTest(unittest.TestCase):
    def errors(self, doc, strict=True):
        return validate_document(doc, strict=strict, today=TODAY)

    def test_unknown_format_is_rejected(self):
        doc = document(minimal_model())
        doc["format"] = 2
        self.assertTrue(any("format" in e for e in self.errors(doc)))

    def test_generated_at_must_be_a_timestamp(self):
        doc = document(minimal_model())
        doc["generatedAt"] = "yesterday"
        self.assertTrue(any("generatedAt" in e for e in self.errors(doc)))

    def test_source_is_required_on_every_release(self):
        model = minimal_model()
        del model["releases"][0]["source"]
        self.assertTrue(any("missing 'source'" in e for e in self.errors(document(model))))

    def test_equipment_types_are_the_apps_names(self):
        for good in ["computer", "transmitter", "rebreather", "dpv", "light", "camera",
                     "housing", "strobe", "videoLight"]:
            self.assertEqual(self.errors(document(minimal_model(equipmentTypes=[good]))), [], good)
        for bad in ["Dive Computer", "Computer", "scooter", ""]:
            errs = self.errors(document(minimal_model(equipmentTypes=[bad])))
            self.assertTrue(any("equipmentTypes" in e for e in errs), bad)

    def test_equipment_types_need_at_least_one(self):
        errs = self.errors(document(minimal_model(equipmentTypes=[])))
        self.assertTrue(any("at least 1" in e for e in errs))

    def test_the_enum_matches_the_apps_list(self):
        # The app's EquipmentType names (lib/core/constants/app_enums.dart).
        names = catalogue.load_schema()["$defs"]["equipmentType"]["enum"]
        self.assertEqual(len(names), len(set(names)))
        for name in ["computer", "transmitter", "rebreather", "dpv", "light", "camera",
                     "housing", "strobe", "o2Cell", "battery", "other"]:
            self.assertIn(name, names)

    def test_ids_are_lowercase_slugs(self):
        for bad in ["Shearwater-Perdix", "perdix_2", "-perdix", "perdix--2", ""]:
            errs = self.errors(document(minimal_model(id=bad)))
            self.assertTrue(any(".id" in e for e in errs), bad)

    def test_dates_are_real_calendar_days(self):
        model = minimal_model()
        for bad in ["2026-02-30", "2026-1-5", "05/01/2026", "2026-10-01T00:00:00Z"]:
            model["releases"][0]["date"] = bad
            errs = self.errors(document(model))
            self.assertTrue(any("date" in e for e in errs), bad)

    def test_strings_are_trimmed_and_non_empty(self):
        for field, bad in [("manufacturer", " Maker"), ("model", ""), ("model", "Thing ")]:
            errs = self.errors(document(minimal_model(**{field: bad})))
            self.assertTrue(errs, (field, bad))

    def test_strict_mode_catches_a_misspelt_key(self):
        model = minimal_model()
        model["releases"][0]["notesURL"] = "https://maker.example.org/notes"
        errs = self.errors(document(model), strict=True)
        self.assertTrue(any("notesURL" in e for e in errs))
        self.assertEqual(self.errors(document(model), strict=False), [])

    def test_safety_is_a_boolean(self):
        model = minimal_model()
        model["releases"][0]["safety"] = "yes"
        self.assertTrue(any("safety" in e for e in self.errors(document(model))))

    def test_the_checker_refuses_a_keyword_it_does_not_know(self):
        with self.assertRaises(ValueError):
            SchemaChecker({"type": "string", "oneOf": []}).check("x")


class RulesTest(unittest.TestCase):
    def errors(self, *models):
        return validate_document(document(*models), strict=True, today=TODAY)

    def test_ids_are_unique(self):
        errs = self.errors(minimal_model(), minimal_model(model="Other"))
        self.assertTrue(any("id is also used" in e for e in errs))

    def test_releases_run_newest_first(self):
        model = minimal_model(releases=[
            {"version": "2", "date": "2026-01-01", "source": "https://maker.example.org/a"},
            {"version": "3", "date": "2026-05-01", "source": "https://maker.example.org/b"},
        ])
        errs = self.errors(model)
        self.assertTrue(any("newest first" in e for e in errs))

    def test_order_skips_releases_without_a_date(self):
        model = minimal_model(releases=[
            {"version": "3", "date": "2026-05-01", "source": "https://maker.example.org/a"},
            {"version": "2b", "source": "https://maker.example.org/b"},
            {"version": "2", "date": "2026-01-01", "source": "https://maker.example.org/c"},
        ])
        self.assertEqual(self.errors(model), [])
        model["releases"][2]["date"] = "2026-06-01"
        self.assertTrue(any("newest first" in e for e in self.errors(model)))

    def test_same_day_releases_are_allowed(self):
        model = minimal_model(releases=[
            {"version": "3", "date": "2026-05-01", "source": "https://maker.example.org/a"},
            {"version": "2", "date": "2026-05-01", "source": "https://maker.example.org/b"},
        ])
        self.assertEqual(self.errors(model), [])

    def test_a_future_date_is_rejected(self):
        model = minimal_model()
        model["releases"][0]["date"] = "2026-12-25"
        self.assertTrue(any("future" in e for e in self.errors(model)))
        model["releases"][0]["date"] = "2026-11-28"  # a maker a timezone ahead
        self.assertEqual(self.errors(model), [])

    def test_one_spelling_names_one_release(self):
        model = minimal_model(releases=[
            {"version": "V95", "reportedAs": ["95"], "source": "https://maker.example.org/a"},
            {"version": "V94", "reportedAs": ["95"], "source": "https://maker.example.org/b"},
        ])
        self.assertTrue(any("also names release" in e for e in self.errors(model)))

    def test_spellings_compare_case_insensitively(self):
        model = minimal_model(releases=[
            {"version": "V95", "source": "https://maker.example.org/a"},
            {"version": "v95", "source": "https://maker.example.org/b"},
        ])
        self.assertTrue(any("also names release" in e for e in self.errors(model)))

    def test_a_version_listed_twice_is_rejected(self):
        model = minimal_model(releases=[
            {"version": "1.0", "source": "https://maker.example.org/a"},
            {"version": "1.0", "source": "https://maker.example.org/b"},
        ])
        self.assertTrue(any("listed twice" in e for e in self.errors(model)))

    def test_reported_as_may_not_repeat_the_version(self):
        model = minimal_model(releases=[
            {"version": "V95", "reportedAs": ["v95"], "source": "https://maker.example.org/a"},
        ])
        self.assertTrue(any("repeats the version" in e for e in self.errors(model)))

    def test_two_models_that_would_match_one_item_are_rejected(self):
        first = minimal_model(id="a", manufacturer="Mares", model="Quad")
        second = minimal_model(id="b", manufacturer="MARES", model="QUAD")
        self.assertTrue(any("could match the same item" in e for e in self.errors(first, second)))

    def test_aliases_count_toward_a_clash(self):
        first = minimal_model(id="a", manufacturer="Scubapro", model="G2")
        second = minimal_model(id="b", manufacturer="Uwatec", manufacturerAliases=["Scubapro"],
                               model="Galileo 2", aliases=["G 2"])
        self.assertTrue(any("could match" in e for e in self.errors(first, second)))

    def test_a_shared_name_on_other_gear_is_no_clash(self):
        # A "Mares Quad" computer is never matched to a light called "Quad".
        computer = minimal_model(id="a", manufacturer="Mares", model="Quad")
        light = minimal_model(id="b", manufacturer="Mares", model="Quad", equipmentTypes=["light"])
        self.assertEqual(self.errors(computer, light), [])

    def test_an_alias_that_only_differs_in_spacing_is_allowed(self):
        # The shared sample lists "Perdix2" beside "Perdix 2"; the app may
        # compare names more strictly than this validator normalises them.
        self.assertEqual(self.errors(minimal_model(model="Perdix 2", aliases=["Perdix2"])), [])

    def test_summary_is_one_line(self):
        model = minimal_model()
        model["releases"][0]["summary"] = "First line.\nSecond line."
        self.assertTrue(any("summary" in e for e in self.errors(model)))

    def test_urls_must_be_well_formed_https(self):
        for key in ["source", "notesUrl", "instructionsUrl"]:
            for bad in ["http://maker.example.org/fw", "https://", "https://localhost/x",
                        "https://maker example.org/x", "ftp://maker.example.org",
                        "https://user:pw@maker.example.org/", "https://maker.example.org:8443/"]:
                model = minimal_model()
                model["releases"][0][key] = bad
                self.assertTrue(self.errors(model), (key, bad))
        model = minimal_model(firmwarePageUrl="http://maker.example.org/")
        self.assertTrue(any("firmwarePageUrl" in e for e in self.errors(model)))


class HelpersTest(unittest.TestCase):
    def test_normalise_name_drops_case_spaces_and_punctuation(self):
        self.assertEqual(normalise_name("  Perdix-2 "), "perdix2")
        self.assertEqual(normalise_name("i330R"), "i330r")

    def test_url_problem(self):
        self.assertIsNone(url_problem("https://www.shearwater.com/firmware?x=1#y"))
        self.assertEqual(url_problem("http://www.shearwater.com"), "is not https")


class DataDirTest(unittest.TestCase):
    def write(self, folder: Path, name: str, content) -> None:
        text = content if isinstance(content, str) else catalogue.dump(content)
        (folder / name).write_text(text, encoding="utf-8")

    def test_the_repositorys_data_is_valid(self):
        self.assertEqual(validate_data_dir(), [])

    def test_ids_must_be_unique_across_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "a.json", {"models": [minimal_model()]})
            self.write(folder, "b.json", {"models": [minimal_model(model="Other")]})
            errs = validate_data_dir(folder, today=TODAY)
            self.assertTrue(any("id is also used" in e for e in errs))

    def test_a_file_holds_only_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "a.json", {"models": [minimal_model()], "note": "x"})
            self.assertTrue(validate_data_dir(folder, today=TODAY))

    def test_a_file_must_be_formatted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "a.json", json.dumps({"models": [minimal_model()]}))
            errs = validate_data_dir(folder, today=TODAY)
            self.assertTrue(any("fwcat.format" in e for e in errs))

    def test_data_is_checked_strictly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            model = minimal_model()
            model["releases"][0]["futureField"] = 1
            self.write(folder, "a.json", {"models": [model]})
            errs = validate_data_dir(folder, today=TODAY)
            self.assertTrue(any("futureField" in e for e in errs))

    def test_an_empty_folder_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(validate_data_dir(Path(tmp), today=TODAY))

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "a.json", "{")
            self.assertTrue(any("not valid JSON" in e for e in validate_data_dir(folder)))


if __name__ == "__main__":
    unittest.main()
