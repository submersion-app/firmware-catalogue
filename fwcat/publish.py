"""Acts on a watcher plan: one PR per new release, one issue per failing page.

    python3.14 -m fwcat.publish build/plan.json

Run in the watcher workflow, with `gh` signed in and the checkout on main.

- A proposal becomes a branch from origin/main holding only that release,
  checked by the validator, pushed, and opened as a PR. A proposal whose
  branch already has a PR (open, merged or closed) is skipped, so a release
  a person rejected is not proposed again. PRs opened with the workflow's
  own token start no workflows, so this step dispatches CI on the branch.
- A failure opens an issue, or comments on the open one with the same title.
- A maker read cleanly closes its open failure issue, if there is one.

The watcher never commits to main. Exits 1 when any page failed, so the
run shows red as well as opening the issue.
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from . import catalogue
from .validate import validate_data_dir
from .watch import failure_title

Runner = Callable[[list[str]], str]


def run_command(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          cwd=catalogue.ROOT).stdout


def apply_entry(data_file: Path, model_id: str, entry: dict) -> None:
    """Adds `entry` as the newest release of `model_id` in `data_file`."""
    content = catalogue.load_json(data_file)
    for model in content["models"]:
        if model["id"] == model_id:
            model["releases"] = [entry, *model["releases"]]
            break
    else:
        raise KeyError(f"{model_id} is not in {data_file.name}")
    data_file.write_text(catalogue.dump(content), encoding="utf-8")


def pr_exists(run: Runner, branch: str) -> bool:
    found = json.loads(run(["gh", "pr", "list", "--head", branch, "--state", "all",
                            "--json", "number"]) or "[]")
    return bool(found)


def open_issue_number(run: Runner, title: str) -> int | None:
    found = json.loads(run(["gh", "issue", "list", "--state", "open", "--search",
                            f"in:title {title}", "--json", "number,title"]) or "[]")
    for issue in found:
        if issue["title"] == title:
            return issue["number"]
    return None


def publish_proposal(run: Runner, proposal: dict, data_dir: Path = catalogue.DATA_DIR) -> str:
    branch = proposal["branch"]
    if pr_exists(run, branch):
        return f"skipped {branch}: a PR already exists"
    run(["git", "switch", "--force-create", branch, "origin/main"])
    try:
        apply_entry(data_dir / proposal["file"], proposal["modelId"], proposal["entry"])
        errors = validate_data_dir(data_dir)
        if errors:
            raise ValueError(f"the proposal for {branch} fails validation: {errors}")
        run(["git", "add", "--", str(Path("data") / proposal["file"])])
        run(["git", "commit", "-m", f"feat: {proposal['title']}"])
        run(["git", "push", "--force", "origin", branch])
        run(["gh", "pr", "create", "--base", "main", "--head", branch,
             "--title", proposal["title"], "--body", proposal["body"]])
        run(["gh", "workflow", "run", "ci.yml", "--ref", branch])
    finally:
        run(["git", "switch", "--force", "main"])
    return f"opened a PR for {branch}"


def failure_body(item: dict, today: date) -> str:
    pages = "\n".join(f"- {url}" for url in item["urls"])
    return (
        f"The {item['maker']} watcher could not read its firmware page on {today}, "
        "so it proposed nothing for that maker.\n\n"
        f"Reason: {item['reason']}\n\nPages:\n{pages}\n\n"
        "Check the page by hand. If its layout changed, update the parser in "
        f"`fwcat/parsers/` and its saved page in `tests/fixtures/`. "
        "This issue closes itself after the next clean read.\n"
    )


def publish_failure(run: Runner, item: dict, today: date) -> str:
    title = item["title"]
    body = failure_body(item, today)
    number = open_issue_number(run, title)
    if number is None:
        run(["gh", "issue", "create", "--title", title, "--body", body])
        return f"opened an issue: {title}"
    run(["gh", "issue", "comment", str(number), "--body", body])
    return f"commented on issue #{number}"


def close_recovered(run: Runner, maker: str, today: date) -> str | None:
    number = open_issue_number(run, failure_title(maker))
    if number is None:
        return None
    run(["gh", "issue", "close", str(number), "--comment",
         f"The {maker} page was read cleanly on {today}."])
    return f"closed issue #{number}"


def publish(plan: dict, run: Runner = run_command, today: date | None = None,
            data_dir: Path = catalogue.DATA_DIR) -> int:
    today = today or date.today()
    failed = False
    for proposal in plan["proposals"]:
        try:
            print(publish_proposal(run, proposal, data_dir))
        except Exception as error:  # noqa: BLE001  report, then carry on
            failed = True
            print(f"could not propose {proposal['branch']}: {error}")
    for item in plan["failures"]:
        failed = True
        print(publish_failure(run, item, today))
    for maker in plan["healthy"]:
        message = close_recovered(run, maker, today)
        if message:
            print(message)
    return 1 if failed else 0


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print("usage: python3.14 -m fwcat.publish PLAN.json")
        return 2
    return publish(catalogue.load_json(Path(argv[0])))


if __name__ == "__main__":
    sys.exit(main())
