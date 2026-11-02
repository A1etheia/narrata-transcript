---
name: plan-story
description: Start a TOOL ticket - create the branch, audit dependencies, read the code, write and commit the plan doc under docs/plans/. Invoke at the start of any ticket before the first edit, e.g. "/plan-story TOOL-4", "plan TOOL-4", "start TOOL-4".
---

# Plan-Story

Produces `docs/plans/TOOL-<n>-<slug>.md` before the implementation. Skip it for one-line fixes and for tickets whose plan is already merged, since merged plans are frozen.

## Rules

1. The branch carries the ticket number: `tool-<n>-<1-3 keywords>`.
2. Every commit carries it too: `<type>(<scope>): … (TOOL-<n>)`.
3. The chunk table is the last section of the plan.
4. Stop at the first chunk marked `Clear context after: yes`.

## Steps

### 1. Branch

Enter plan mode; the recon below is read-only. Then:

```bash
git status --short    # must be clean or show only your own work
git fetch origin main && git switch -c tool-<n>-<slug> --no-track origin/main
git config --get branch.tool-<n>-<slug>.merge    # must be empty, never refs/heads/main
```

The slug mirrors the plan filename.

### 2. Ticket and dependencies

Fetch the ticket with `getJiraIssue` (`cloudId: alethe1a.atlassian.net`), then run `/check-ticket-deps TOOL-<n>`. Resolve any needs-attention finding with the user before chunking.

Move the ticket to In Progress with `getTransitionsForJiraIssue` and `transitionJiraIssue`.

### 3. Recon

Read the code the ticket touches, plus `docs/transcript-roadmap.md` for its position and any hint. Base the plan on what exists, with `path:line` references.

### 4. Checks

Each trigger that applies produces a named plan section with one *handled — … / N/A because …* line per item. An N/A is a valid entry; a missing section is not.

| Trigger | Section | Question |
| --- | --- | --- |
| Touches recordings, transcripts, participant names, logs or fixtures | Daten-Check | Does it follow TOOL-66? Can anything real reach the repo, a log or an error message? |
| Reads or writes contract JSON, or the Narrata endpoint | Contract-Check | Does it match IOA-1214 and its version? Does Narrata need a change, and which IOA ticket carries it? |
| Long-running or model-backed step | Resume-Check | What happens on abort? Is finished work reused? Does a resume keep the same model and snapshot? |
| New dependency or model | Dependency-Check | Is it needed now, does it run locally, what are its license and hardware needs? |
| Changes an internal format with a version field | Format-Check | Is the version bumped? What happens to existing artifacts? |

### 5. Chunk

A chunk is one commit with its own Verify line. A chunk that needs its own sub-plan is too big, so split it.

### 6. Write and commit

Write the plan from the skeleton, then exit plan mode. Create any ticket a follow-up names before committing, so every key exists. Commit the plan on its own as `docs(plans): plan <topic> (TOOL-<n>)`.

Run the chunks in order, using `/chunk-commit` for each.

## Plan skeleton

```markdown
# TOOL-<n> — <title>

## Ziel
<2-4 Sätze: was danach möglich ist, was heute nicht geht>

## Ist-Stand
<was existiert, mit Pfad:Zeile>

## Entscheidungen
<getroffene Wahl plus ein Satz Grund; Optionen nur, wo echt offen>

## <Check-Sektionen aus Schritt 4>

## Chunks
### Chunk 1 — <name>
- Dateien: …
- Änderung: …
- Verify: `scripts/check`
- AC: …

## Folge-Tickets
<jeder Eintrag mit Ticket-Key oder `[kein Ticket: <Grund>]`>

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | … | no |
```

Mark `Clear context after: yes` when the next chunk works on an unrelated part of the code.

## Anti-patterns

- Calling `ExitPlanMode` on a mid-plan directive. Do what was asked and stay in plan mode.
- Omitting a check section because the answer seems obvious.
- A follow-up bullet with neither a key nor `[kein Ticket: …]`.
- A branch without `--no-track`: later pushes would target remote `main`.
