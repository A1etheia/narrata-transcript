#!/usr/bin/env python3
"""Backlog triage over a saved TOOL Jira search result (see SKILL.md, phase 1).

Usage: python3 -I triage.py <page.json>... [--dates <dates.jsonl>] [--today YYYY-MM-DD]

page.json  = searchJiraIssuesUsingJql, view "evidence" with explicit fields
             (parent, duedate, description, issuelinks, labels); one file per page
dates.jsonl = stdout of `python3 docs/transcript-roadmap.py` (key, start, end per line)

The roadmap task list P is read from docs/transcript-roadmap.py without running
its main(), so the roadmap file stays untouched.
"""

import argparse
import json
import re
import runpy
from datetime import date
from pathlib import Path

ROADMAP = Path(__file__).resolve().parents[3] / "docs" / "transcript-roadmap.py"
KEY = re.compile(r"\b(?:IOA|TOOL)-\d+\b")
# Explicit dependency phrases only; prose mentions of done prerequisites are not dependencies.
BLOCKED_PHRASE = re.compile(
    r"(?:blocked by|depends on|hängt an|wartet auf|braucht|setzt voraus)\s+([^\n.;]*)",
    re.IGNORECASE,
)
LABEL = "transcript"


def key_order(key):
    project, number = key.split("-")
    return project, int(number)


def nodes(paths):
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            out += [n for n in json.load(fh)["issues"]["nodes"] if n.get("fields")]
    return out


def parse(node):
    f = node["fields"]
    blockers, blocks, related = [], [], []
    for link in f.get("issuelinks") or []:
        for side in ("inwardIssue", "outwardIssue"):
            other = link.get(side)
            if not other:
                continue
            ref = (
                other["key"],
                other["fields"]["status"]["statusCategory"]["key"] == "done",
            )
            if link["type"]["name"] != "Blocks":
                related.append(ref)
            elif side == "inwardIssue":
                blockers.append(ref)
            else:
                blocks.append(ref)
    parent = None
    if p := f.get("parent"):
        pf = p["fields"]
        done = pf["status"]["statusCategory"]["key"] == "done"
        parent = (p["key"], pf["summary"], pf["issuetype"]["name"], done)
    return {
        "summary": f["summary"],
        "type": f["issuetype"]["name"],
        "status": f["status"]["name"],
        "labels": f.get("labels") or [],
        "blockers": blockers,
        "blocks": blocks,
        "related": related,
        "parent": parent,
        "due": f.get("duedate"),
        "desc": f.get("description") or "",
    }


def open_blockers(v):
    return [k for k, done in v["blockers"] if not done]


def section(title, lines):
    print(f"\n### {title} ({len(lines)})")
    for line in lines:
        print(f"- {line}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--dates")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args()
    today = args.today

    issues = {n["key"]: parse(n) for n in nodes(args.pages)}
    epics = {k for k, v in issues.items() if v["type"] == "Epic"}
    work = sorted((k for k in issues if k not in epics), key=key_order)
    children = {}
    for k, v in issues.items():
        if v["parent"]:
            children.setdefault(v["parent"][0], []).append(k)

    print(
        f"# Open TOOL issues: {len(issues)} ({len(epics)} epics, {len(work)} work items), today {today}\n"
    )
    print("## By parent")
    groups = {}
    for k in work:
        p = issues[k]["parent"]
        label = (
            f"{p[0]} {p[1]} [{p[2]}{', DONE' if p[3] else ''}]" if p else "(no parent)"
        )
        groups.setdefault(label, []).append(k)
    for label in sorted(groups):
        print(f"\n### {label}")
        for k in groups[label]:
            v = issues[k]
            due = f" due {v['due']}" if v["due"] else ""
            blockers = ", ".join(open_blockers(v)) or "-"
            blocks = ", ".join(o for o, done in v["blocks"] if not done) or "-"
            print(
                f"- {k} [{v['type']}, {v['status']}]{due} {v['summary']} | blocked by: {blockers} | blocks: {blocks}"
            )

    print("\n## Findings")
    section(
        "No parent -> assign an epic",
        [f"{k} {issues[k]['summary']}" for k in work if not issues[k]["parent"]],
    )
    section(
        "Parent epic is Done -> move to an open epic or reopen",
        [
            f"{k} -> {issues[k]['parent'][0]} {issues[k]['parent'][1]}"
            for k in work
            if issues[k]["parent"]
            and issues[k]["parent"][3]
            and issues[k]["parent"][2] == "Epic"
        ],
    )
    section(
        "Open subtasks under a Done parent -> probably stale, verify in code",
        [
            f"{k} (parent {issues[k]['parent'][0]}) {issues[k]['summary']}"
            for k in work
            if issues[k]["type"] == "Subtask"
            and issues[k]["parent"]
            and issues[k]["parent"][3]
        ],
    )
    section(
        "Open epics without open children -> cut tickets, or close",
        [
            f"{e} {issues[e]['summary']}"
            for e in sorted(epics, key=key_order)
            if not children.get(e)
        ],
    )
    section(
        f"Missing label `{LABEL}`",
        [
            f"{k} {issues[k]['summary']}"
            for k in work
            if LABEL not in issues[k]["labels"]
        ],
    )
    section(
        "Overdue due date",
        [
            f"{k} due {issues[k]['due']} {issues[k]['summary']}"
            for k in sorted(work, key=lambda s: issues[s]["due"] or "")
            if issues[k]["due"] and issues[k]["due"] < today
        ],
    )

    unlinked = []
    for k, v in issues.items():
        linked = {o for o, _ in v["blockers"] + v["blocks"] + v["related"]}
        named = {
            key
            for m in BLOCKED_PHRASE.finditer(v["desc"])
            for key in KEY.findall(m.group(1))
        }
        if missing := sorted(named - linked - {k}, key=key_order):
            unlinked.append(f"{k}: {', '.join(missing)}")
    section(
        "Dependencies named in the description but not linked (check the wording)",
        unlinked,
    )

    external = sorted(
        {b for k in work for b in open_blockers(issues[k]) if b not in issues},
        key=key_order,
    )
    section("Open blockers outside this result -> fetch status and due date", external)

    roadmap_drift(issues, work)
    if args.dates:
        date_drift(issues, args.dates)

    section(
        "Unblocked now",
        [f"{k} {issues[k]['summary']}" for k in work if not open_blockers(issues[k])],
    )


def roadmap_drift(issues, work):
    rows = {
        key: note
        for _, _, items in runpy.run_path(str(ROADMAP))["P"]
        for key, _, _, note in items
    }
    print(f"\n## Roadmap ({ROADMAP.name})")
    section(
        "TOOL row open, ticket not open in Jira -> Done or dropped? mark `erledigt` or remove the row",
        [
            k
            for k, note in rows.items()
            if k.startswith("TOOL-")
            and not note.startswith("erledigt")
            and k not in issues
        ],
    )
    section(
        "Row `erledigt`, ticket still open -> close in Jira or reopen the row",
        [k for k, note in rows.items() if note.startswith("erledigt") and k in issues],
    )
    section(
        "Open ticket without a row -> add, or confirm it is in the 'Nicht eingeplant' list",
        [f"{k} {issues[k]['summary']}" for k in work if k not in rows],
    )
    section(
        "Open IOA rows -> fetch their status",
        [
            k
            for k, note in rows.items()
            if k.startswith("IOA-") and not note.startswith("erledigt")
        ],
    )


def date_drift(issues, path):
    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            row = json.loads(raw)
            v = issues.get(row["key"])
            if v and v["due"] != row["end"]:
                lines.append(
                    f"{row['key']} Jira due {v['due'] or '-'}, roadmap end {row['end']}"
                )
    section("Jira due date differs from the roadmap", lines)


if __name__ == "__main__":
    main()
