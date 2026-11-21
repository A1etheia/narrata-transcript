---
name: backlog-review
description: Periodic TOOL backlog review - list ALL open TOOL tickets with their epic, ordered by the priority they should be done in (blockers, IOA gates, docs/transcript-roadmap.py as baseline), and flag lost tickets (no epic, Done epic, empty epics, missing label, unlinked dependencies, roadmap and date drift). Report first; Jira and roadmap changes only after the user approves. Invoke on "/backlog-review", "list all open tickets and their epics", "check the state of the TOOL project", "prioritize the open work", "what's lost in Jira".
---

# Backlog Review

A recurring health check of the TOOL project. **The main deliverable is the ordered list:** every open TOOL ticket with its epic, in the order it should be done, and what blocks it. Everything else supports that list:

1. **Ordered list (core):** all open tickets with epic and blocker, numbered in priority order and grouped in tiers.
2. **Lost tickets:** open work that no open epic carries, which the ordered list would otherwise miss or misplace.
3. **Roadmap drift:** places where `docs/transcript-roadmap.py` (the baseline order) disagrees with Jira.

**Phases 1–3 are read-only.** Every write (transition, link, parent, label, roadmap edit, date) waits for the user's go in phase 4.

## Constants

| Purpose | Value |
|---|---|
| Jira `cloudId` | `alethe1a.atlassian.net` |
| Roadmap source | `docs/transcript-roadmap.py` (task list `P`); the `.md` is generated |
| Roadmap label | `transcript` (overview: `project in (TOOL, IOA) AND labels = transcript`) |
| Date fields | `customfield_10015` (start) · `duedate` (end) |
| Parser | `.claude/skills/backlog-review/triage.py` |

## Phase 1: Fetch

Load `searchJiraIssuesUsingJql` via ToolSearch. The evidence view with **explicit** fields returns parent, due date and links in one call:

```
searchJiraIssuesUsingJql(cloudId, jql="project = TOOL AND statusCategory != Done ORDER BY key ASC",
  fields=["summary","status","issuetype","parent","duedate","description","issuelinks","labels"],
  view="evidence", maxResults=100)
```

The result exceeds the inline limit and is saved to the `tool-results/*.txt` path named in the error. If `pageInfo.hasNextPage` is true, page with `nextPageToken` and pass every page file. If it comes back inline (a very small backlog), save it verbatim to a file in the session scratchpad with Write.

Save the roadmap's dates as well; for an unchanged source, this regenerates the `.md` byte for byte:

```bash
python3 docs/transcript-roadmap.py > <scratchpad>/dates.jsonl
git status --short docs   # must be empty; otherwise stop and report
```

`jq` is not installed; never reach for it.

## Phase 2: Triage

```bash
python3 -I .claude/skills/backlog-review/triage.py <page file>... --dates <scratchpad>/dates.jsonl --today <YYYY-MM-DD>
```

It prints all open issues grouped by parent, then the findings:

| Finding | Meaning | Usual fix |
|---|---|---|
| No parent | Not in any epic | Propose the epic it belongs to (by topic and sibling tickets) |
| Parent epic is Done | Open work under a closed epic | Move to an open epic, or reopen the epic |
| Open subtasks under a Done parent | Usually shipped but never ticked off | **Verify in code** (`grep -n` the named modules and CLI commands) before proposing Done |
| Open epics without open children | Nothing planned | Cut tickets or close the epic; the user decides |
| Missing label `transcript` | Not in the Jira overview | Add the label |
| Overdue due date | The Jira date has passed | Report it; never bulk-reset dates without asking |
| Named but not linked | The description says "blocked by / braucht TOOL-n" without a link | Propose a `Blocks` link after reading the sentence |
| Open blockers outside this result | IOA blockers | Fetch them (see below) |
| Roadmap: TOOL row open, ticket not open | Done or dropped in Jira, roadmap not updated | Note `erledigt …`, or remove the row and record it under "Nicht eingeplant" |
| Roadmap: row `erledigt`, ticket open | Shipped but not closed, or reopened | Verify in code, then close in Jira or reopen the row |
| Roadmap: open ticket without a row | Not scheduled | Add a row, or confirm it is listed in the "Nicht eingeplant" assumption |
| Jira due date differs from the roadmap | Dates not mirrored | List them; mirror only on an explicit yes |
| Unblocked now | No open blocker | Input for phase 3 |

Then check what the script cannot see:

- **IOA gates:** for every IOA key under "Open blockers outside this result" and "Open IOA rows", fetch status and due date (`key in (...)`, fields summary, status, duedate). An open IOA blocker on the critical path is the headline finding.
- **The "Nicht eingeplant" list:** read the assumption bullet in `docs/transcript-roadmap.py` (`Nicht eingeplant: …`) and drop the tickets it names from "open ticket without a row". It also names discarded tickets; one that is still open in Jira is drift.
- **Scope:** the pipeline only transcribes (audio to text, speakers, confidence). Flag open tickets that need campaign knowledge but not audio (classification, correction from the glossary, IT/OT) as candidates for Narrata (IOA). Don't move them without the user's go.

## Phase 3: Prioritize

Jira priority is uniformly "Medium", so the order is a judgment call. Start from the order in `P` and change only what needs changing, with a reason. Rules, in order:

1. **Risk fixes first:** breaks of the CLAUDE.md boundaries (raw audio leaves the machine, real session data in the repo, an ASR result overwritten or text invented), and correctness bugs in the pipeline. These are usually small.
2. **Decision gates:** a ticket that decides scope for others (such as TOOL-60 at M4) comes before the tickets it decides on. Tickets that wait for that decision go after it, with the gate named.
3. **Critical-path unblockers:** a ticket that unblocks several others goes before its siblings (count the `blocks` links).
4. **One person, one time budget:** TOOL and IOA tickets compete for the same days, so the plan is linear. Don't invent parallel lanes; the only overlap is ASR runs or model downloads in the background.
5. **IOA gates:** tickets behind an open IOA blocker go after independent work; name the gate and its due date.
6. **Concepts and reflection points** (phases 7–8) after the pilot review, as the roadmap's maintenance notes say.
7. **Parked:** V0.2 candidates (label `transcript-v0.2`, such as TOOL-14) and anything waiting for an outside decision. List them separately and don't schedule them.

Capacity for dates comes from `WORKDAYS` and `PAUSES` in the roadmap source (currently 3 development days per week, Mon, Tue and Thu, with a holiday break).

## Report (chat)

One opening line: total open tickets, how many can start now, and the biggest blocker (e.g. "10 open, 8 ready now; TOOL-60 decides the scope of 4").

Then, in this order:

1. **Recommended order (the core, never shortened):** numbered tables per tier, `# | Ticket (summary) | Epic (key + name) | Blocked by / why now`. **Every** open ticket that isn't an epic shows up exactly once: no epic → "— none —", Done epic → "(Done)" after its name. Waiting tickets go in the last tier, "Parked", with what they wait for. The rows must add up to the script's work-item count (minus any stale subtasks you list separately).
2. **Lost tickets:** one table per finding type, with ticket, current parent and proposed fix.
3. **Roadmap drift:** a short list.
4. **Proposed actions:** a checklist the user can approve item by item.

Use the epic's name next to its key. Explain jargon in plain words.

## Phase 4: Act (only what the user approves)

- **Transition:** `executeRead({ name: "listJiraIssueTransitions", cloudId, inputs: { issueIdOrKey } })`, then `transitionJiraIssue` with the transition whose `to.name` fits: Done for shipped work, the closing status for dropped work. If no status fits, ask.
- **Link:** discover `createJiraIssueLink`, run it via `executeWrite` with `linkType: "Blocks"`, `inwardIssue` = the blocker, `outwardIssue` = the blocked ticket.
- **Parent or label:** `editJiraIssue` with `fields: {parent: {key: "TOOL-n"}}` or `fields: {labels: [...]}`. Send the full label list, since the call replaces it.
- **Roadmap:** edit `P` (and the assumption bullets, guidelines or reflection points if the order changed their story) in `docs/transcript-roadmap.py`, never the `.md`. Set `GENERATED` to today, regenerate into a second dates file and diff it against the phase-1 file. Commit `.py` and `.md` together:
  - On a ticket branch: in that branch, so it lands in the ticket's PR.
  - Otherwise: a branch `backlog-review-<YYYY-MM-DD>` from `origin/main` (`git fetch origin main && git switch -c <name> --no-track origin/main`), commit `docs(roadmap): reorder after backlog review`, then push and open a PR. The merge needs the user's go; this is not `/close-ticket`.
- **Dates:** mirror the changed rows from the new dates file with `editJiraIssue` (`customfield_10015`, `duedate`), but only after the user says yes to the list.
- **Comment, not description edit:** if a ticket needs a note about the review (such as a changed scope), add it with `addOrEditJiraIssueComment`. Description edits with SQL-like text can be blocked by Cloudflare.

## Gotchas

- **Never mirror dates to Jira in bulk without an explicit yes.** In ios-archiv, a stale generator once overwrote 18 tickets' dates, which had to be restored from the changelog. If dates are wrong, list them and ask.
- **Don't run the roadmap generator on a dirty `docs/`**: it rewrites `transcript-roadmap.md`. Check `git status --short docs` first.
- **Keep the explicit `fields` list in phase 1:** the evidence view without it drops `issuelinks`, and the full view drops `parent` and `duedate`.
- **Subtasks of a Done epic are not automatically done**; check the code first.
- **IOA is a separate project in the `ios-archiv` repo, in English.** Only read it here; IOA changes belong to the Narrata side.
- **No real session data in the report or in Jira:** names, transcript text and recording content stay in `input/`, `work/` and `output/`.
