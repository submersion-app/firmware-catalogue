import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from fwcat import catalogue
from fwcat.publish import apply_entry, publish
from fwcat.watch import Finding, ParseError, Watcher, branch_name, run

TODAY = date(2026, 11, 27)
PAGE = "https://maker.example.org/firmware"


def data_dir(tmp: str) -> Path:
    folder = Path(tmp)
    content = {"models": [{
        "id": "maker-thing",
        "manufacturer": "Maker",
        "model": "Thing",
        "equipmentTypes": ["computer"],
        "releases": [
            {"version": "V12", "reportedAs": ["12"], "date": "2026-06-01", "source": PAGE},
            {"version": "V11", "date": "2026-01-01", "source": PAGE},
        ],
    }]}
    (folder / "maker.json").write_text(catalogue.dump(content), encoding="utf-8")
    return folder


def watcher(parse) -> Watcher:
    return Watcher(maker="maker", data_file="maker.json", urls=(PAGE,),
                   model_ids=("maker-thing",), parse=parse)


def finds(version, day=None, model_id="maker-thing"):
    return lambda pages: [Finding(model_id, version, PAGE, date=day)]


class RunTest(unittest.TestCase):
    def plan(self, parse, fetcher=lambda url: "<html></html>"):
        with tempfile.TemporaryDirectory() as tmp:
            return run([watcher(parse)], fetcher, data_dir(tmp), TODAY)

    def test_a_known_version_proposes_nothing(self):
        for spelling in ["V12", "v12", "12"]:
            plan = self.plan(finds(spelling))
            self.assertEqual((plan.proposals, plan.failures, plan.healthy), ([], [], ["maker"]))

    def test_a_new_version_is_proposed(self):
        plan = self.plan(finds("V13", "2026-11-20"))
        self.assertEqual(plan.failures, [])
        [proposal] = plan.proposals
        self.assertEqual(proposal["entry"], {"version": "V13", "date": "2026-11-20", "source": PAGE})
        self.assertEqual(proposal["branch"], "watcher/maker-thing-v13")
        self.assertEqual(proposal["file"], "maker.json")
        self.assertIn("Maker Thing: firmware V13", proposal["title"])
        self.assertIn("summary", proposal["body"])

    def test_a_fetch_error_is_a_failure(self):
        def broken(url):
            raise OSError("HTTP Error 503")
        plan = self.plan(finds("V13"), fetcher=broken)
        [item] = plan.failures
        self.assertIn("503", item["reason"])
        self.assertEqual(plan.proposals, [])
        self.assertEqual(plan.healthy, [])

    def test_a_parser_error_is_a_failure(self):
        def parse(pages):
            raise ParseError("no release table")
        plan = self.plan(parse)
        self.assertIn("no release table", plan.failures[0]["reason"])

    def test_a_missing_model_is_a_failure(self):
        plan = self.plan(lambda pages: [])
        self.assertIn("no version found", plan.failures[0]["reason"])

    def test_an_unlisted_model_is_a_failure(self):
        plan = self.plan(finds("V13", model_id="maker-other"))
        self.assertIn("does not cover", plan.failures[0]["reason"])

    def test_something_that_is_not_a_version_is_a_failure(self):
        plan = self.plan(finds("Download the latest firmware here for your computer now " * 2))
        self.assertIn("does not look like a version", plan.failures[0]["reason"])

    def test_an_older_version_than_the_catalogue_is_a_failure(self):
        plan = self.plan(finds("V10", "2025-06-01"))
        self.assertEqual(plan.proposals, [])
        self.assertIn("older than", plan.failures[0]["reason"])

    def test_a_future_date_is_a_failure(self):
        plan = self.plan(finds("V13", "2027-01-01"))
        self.assertIn("future", plan.failures[0]["reason"])

    def test_branch_names_are_safe(self):
        self.assertEqual(branch_name("a-b", "Build 4567 (beta)"), "watcher/a-b-build-4567-beta")
        self.assertEqual(branch_name("a-b", "1.2.3"), "watcher/a-b-1-2-3")


class FakeGit:
    """Records commands and answers the gh queries publish asks."""

    def __init__(self, prs=(), issues=()):
        self.commands: list[list[str]] = []
        self.prs = list(prs)
        self.issues = list(issues)

    def __call__(self, command):
        self.commands.append(command)
        if command[:3] == ["gh", "pr", "list"]:
            branch = command[command.index("--head") + 1]
            return json.dumps([{"number": 1}] if branch in self.prs else [])
        if command[:3] == ["gh", "issue", "list"]:
            return json.dumps(self.issues)
        return ""

    def ran(self, *prefix):
        return [c for c in self.commands if c[:len(prefix)] == list(prefix)]


class PublishTest(unittest.TestCase):
    def proposal(self):
        return {
            "maker": "maker", "modelId": "maker-thing", "file": "maker.json",
            "entry": {"version": "V13", "source": PAGE},
            "branch": "watcher/maker-thing-v13", "title": "Maker Thing: firmware V13",
            "body": "body",
        }

    def test_a_proposal_opens_a_pr_and_dispatches_ci(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = data_dir(tmp)
            git = FakeGit()
            code = publish({"proposals": [self.proposal()], "failures": [], "healthy": ["maker"]},
                           git, TODAY, folder)
            self.assertEqual(code, 0)
            content = catalogue.load_json(folder / "maker.json")
            self.assertEqual(content["models"][0]["releases"][0]["version"], "V13")
        self.assertEqual(len(git.ran("gh", "pr", "create")), 1)
        self.assertEqual(git.ran("gh", "workflow", "run"),
                         [["gh", "workflow", "run", "ci.yml", "--ref", "watcher/maker-thing-v13"]])
        self.assertEqual(git.ran("git", "push"),
                         [["git", "push", "--force", "origin", "watcher/maker-thing-v13"]])
        # It never pushes main and always returns to it.
        self.assertFalse(any("main" == c[-1] for c in git.ran("git", "push")))
        self.assertIn(["git", "switch", "--force", "main"], git.commands)

    def test_a_proposal_with_any_pr_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            git = FakeGit(prs=["watcher/maker-thing-v13"])
            publish({"proposals": [self.proposal()], "failures": [], "healthy": []},
                    git, TODAY, data_dir(tmp))
        self.assertEqual(git.ran("gh", "pr", "create"), [])
        self.assertEqual(git.ran("git", "switch"), [])

    def test_an_invalid_proposal_is_not_pushed(self):
        proposal = self.proposal()
        proposal["entry"] = {"version": "V12b", "reportedAs": ["12"], "source": PAGE}
        with tempfile.TemporaryDirectory() as tmp:
            git = FakeGit()
            code = publish({"proposals": [proposal], "failures": [], "healthy": []},
                           git, TODAY, data_dir(tmp))
        self.assertEqual(code, 1)
        self.assertEqual(git.ran("git", "push"), [])
        self.assertIn(["git", "switch", "--force", "main"], git.commands)

    def test_a_failure_opens_an_issue(self):
        item = {"maker": "maker", "title": "Watcher: the maker firmware page could not be read",
                "reason": "no version found", "urls": [PAGE]}
        git = FakeGit()
        code = publish({"proposals": [], "failures": [item], "healthy": []}, git, TODAY)
        self.assertEqual(code, 1)
        [create] = git.ran("gh", "issue", "create")
        self.assertIn(item["title"], create)

    def test_a_repeated_failure_comments_on_the_open_issue(self):
        item = {"maker": "maker", "title": "Watcher: the maker firmware page could not be read",
                "reason": "no version found", "urls": [PAGE]}
        git = FakeGit(issues=[{"number": 7, "title": item["title"]},
                              {"number": 8, "title": item["title"] + " again"}])
        publish({"proposals": [], "failures": [item], "healthy": []}, git, TODAY)
        self.assertEqual(git.ran("gh", "issue", "create"), [])
        self.assertEqual(git.ran("gh", "issue", "comment")[0][3], "7")

    def test_a_clean_read_closes_the_open_issue(self):
        git = FakeGit(issues=[{"number": 7, "title": "Watcher: the maker firmware page could not be read"}])
        code = publish({"proposals": [], "failures": [], "healthy": ["maker"]}, git, TODAY)
        self.assertEqual(code, 0)
        self.assertEqual(git.ran("gh", "issue", "close")[0][3], "7")

    def test_apply_entry_puts_the_release_on_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = data_dir(tmp)
            apply_entry(folder / "maker.json", "maker-thing", {"version": "V13", "source": PAGE})
            text = (folder / "maker.json").read_text()
            self.assertEqual(text, catalogue.dump(json.loads(text)))
            versions = [r["version"] for r in json.loads(text)["models"][0]["releases"]]
            self.assertEqual(versions, ["V13", "V12", "V11"])
            with self.assertRaises(KeyError):
                apply_entry(folder / "maker.json", "nope", {"version": "1", "source": PAGE})


if __name__ == "__main__":
    unittest.main()
