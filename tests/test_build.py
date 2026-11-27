import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from fwcat import catalogue
from fwcat.build import NOTHING_CHANGED, build, changes, next_tag, notes_text
from fwcat.validate import validate_document


def model(model_id, maker, name, *versions):
    return {
        "id": model_id,
        "manufacturer": maker,
        "model": name,
        "equipmentTypes": ["computer"],
        "releases": [{"version": v, "source": "https://maker.example.org/fw"} for v in versions],
    }


class BuildDocumentTest(unittest.TestCase):
    def test_models_are_sorted_by_maker_then_model(self):
        doc = catalogue.build_document([
            model("b", "Suunto", "Ocean", "1"),
            model("a", "shearwater", "Teric", "1"),
            model("c", "Shearwater", "Perdix 2", "1"),
        ], datetime(2026, 11, 27, 8, 30, 15, 123, tzinfo=UTC))
        self.assertEqual([m["id"] for m in doc["models"]], ["c", "a", "b"])
        self.assertEqual(doc["generatedAt"], "2026-11-27T08:30:15Z")
        self.assertEqual(doc["format"], 1)

    def test_the_built_document_passes_the_published_schema(self):
        doc = catalogue.build_document([model("a", "Maker", "Thing", "2", "1")])
        self.assertEqual(validate_document(doc, strict=False), [])


class ChangesTest(unittest.TestCase):
    def test_first_release_lists_every_model(self):
        current = catalogue.build_document([model("a", "Maker", "Thing", "2", "1")])
        self.assertEqual(changes(None, current), ["Added Maker Thing (latest 2)"])

    def test_new_removed_and_corrected(self):
        before = catalogue.build_document([
            model("a", "Maker", "Thing", "2", "1"),
            model("b", "Maker", "Gone", "1"),
            model("c", "Maker", "Fixed", "1"),
        ])
        after_models = [
            model("a", "Maker", "Thing", "3", "2"),
            model("c", "Maker", "Fixed", "1"),
            model("d", "Maker", "New", "1"),
        ]
        after_models[1]["releases"][0]["summary"] = "Corrected."
        after = catalogue.build_document(after_models)
        self.assertEqual(changes(before, after), [
            "Maker Fixed: details corrected",
            "Added Maker New (latest 1)",
            "Maker Thing: new release 3",
            "Maker Thing: removed release 1",
            "Removed Maker Gone",
        ])

    def test_generated_at_alone_is_no_change(self):
        models = [model("a", "Maker", "Thing", "1")]
        before = catalogue.build_document(models, datetime(2026, 1, 1, tzinfo=UTC))
        after = catalogue.build_document(models, datetime(2026, 2, 1, tzinfo=UTC))
        self.assertEqual(changes(before, after), [])

    def test_notes_text(self):
        doc = catalogue.build_document([model("a", "Maker", "Thing", "1")])
        self.assertIn("First release.", notes_text([], doc))
        self.assertIn("- Added", notes_text(["Added Maker Thing (latest 1)"], doc))


class BuildTest(unittest.TestCase):
    def test_build_writes_a_valid_catalogue_and_reports_no_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "firmware-catalogue.json"
            notes = Path(tmp) / "notes.md"
            self.assertEqual(build(out, notes=notes), 0)
            built = catalogue.load_json(out)
            self.assertEqual(validate_document(built, strict=True), [])
            self.assertIn("First release.", notes.read_text())
            # Rebuilding against itself finds nothing to publish.
            self.assertEqual(build(Path(tmp) / "again.json", previous=out), NOTHING_CHANGED)


class NextTagTest(unittest.TestCase):
    def test_tags(self):
        today = date(2026, 11, 27)
        self.assertEqual(next_tag([], today), "2026.11.27")
        self.assertEqual(next_tag(["2026.11.27"], today), "2026.11.27.2")
        self.assertEqual(next_tag(["2026.11.27", "2026.11.27.2"], today), "2026.11.27.3")


if __name__ == "__main__":
    unittest.main()
