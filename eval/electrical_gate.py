"""Re-run the supplied electrical checklist on immutable Git blobs.

Usage: python -m eval.electrical_gate --repos-dir work/acceptance --output work/gate.json
Clone each manifest repo into REPOS_DIR/<repository basename> beforehand. No
checkout, export, firmware execution, native KiCad, or network access is used.
A score matches explicit reference/problem evidence; it is not a release gate.
The independently supplied PASS repositories are still required for acceptance.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch
from extrude import electrical_reasoning, github_history

MANIFEST = Path(__file__).with_name("electrical_manifest.json")


def run(repos_dir):
    manifest = json.loads(MANIFEST.read_text())
    results = {}
    for item in manifest["repositories"]:
        repo, sha = item["repo"], item["sha"]
        directory = (repos_dir / repo.split("/")[1]).resolve()
        resolved = subprocess.check_output(
            ["git", "-C", str(directory), "rev-parse", sha + "^{commit}"], text=True
        ).strip()
        if resolved != sha:
            raise ValueError("Pinned revision mismatch for " + repo)
        with patch.object(
            github_history, "_repository", return_value=directory / ".git"
        ):
            findings, coverage = electrical_reasoning.collect(repo, sha)
        results[repo] = dict(sha=sha, findings=findings, coverage=coverage)
    scored = []
    for criterion in manifest["checklist"]:
        rows = results[criterion["repo"]]["findings"]
        matching = [r for r in rows if r["rule_id"] in criterion["rules"]]
        text = "\n".join(r["summary"] for r in matching)
        caught = all(
            re.search(pattern, text, re.I) for pattern in criterion["requires"]
        )
        scored.append(
            dict(
                item=criterion["item"],
                repo=criterion["repo"],
                caught=bool(caught),
                evidence=[
                    r
                    for r in matching
                    if any(
                        re.search(pattern, r["summary"], re.I)
                        for pattern in criterion["requires"]
                    )
                ],
            )
        )
    score = sum(r["caught"] for r in scored if isinstance(r["item"], int))
    shashvat = sum(r["caught"] for r in scored if isinstance(r["item"], str))
    correct = json.loads(
        MANIFEST.with_name("electrical_correct_items.json").read_text()
    )
    false_flags = []
    correct_reviews = []
    for entry in correct["repositories"]:
        info = results[entry["repo"]]
        if info["sha"] != entry["sha"]:
            raise ValueError("Correct-list SHA mismatch")
        allowed = entry["reviewed_nonconflicting_findings"]
        conflicts = [
            row
            for row in info["findings"]
            if not any(
                re.search(pattern, row["summary"], re.I)
                for pattern in allowed.get(row["rule_id"], [])
            )
        ]
        false_flags.extend(dict(repo=entry["repo"], finding=row) for row in conflicts)
        correct_reviews.append(
            dict(
                repo=entry["repo"],
                sha=entry["sha"],
                correct_items=entry["correct_items"],
                conflicting_or_unreviewed_findings=conflicts,
            )
        )
    return dict(
        engine="whole-design electrical_reasoning.collect",
        new_repositories_score=f"{score}/13",
        shashvat_score=f"{shashvat}/4",
        pass_group=dict(
            method=correct["method"],
            false_flags=len(false_flags),
            correct_items_reviewed=sum(
                len(r["correct_items"]) for r in correct_reviews
            ),
            reviews=correct_reviews,
            conflicts=false_flags,
        ),
        acceptance=(
            "MEETS measured gate: >=10/13, 4/4, zero Correct-list false flags"
            if score >= 10 and shashvat == 4 and not false_flags
            else "OPEN: measured acceptance gate not met"
        ),
        still_open=[
            "Item 5 partial: J3/J5 omitted; SW1/SW2 present at pinned SHA, no credit",
            "Item 9: cutoff polarity lacks sourced operating limits",
        ],
        scoring="Reference/pin AND specific problem required; partial item 5 gets no credit. Suggestions count only when they name the problem; they remain suggestions in audit output.",
        checklist=scored,
        repositories=results,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.repos_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("New repos:", report["new_repositories_score"])
    print("Shashvat:", report["shashvat_score"])
    print(
        "Correct-list false flags:",
        report["pass_group"]["false_flags"],
        "across",
        report["pass_group"]["correct_items_reviewed"],
        "Correct items",
    )
    print(report["acceptance"])
    for row in report["checklist"]:
        print(row["item"], "caught" if row["caught"] else "open")
    if not report["acceptance"].startswith("MEETS"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
