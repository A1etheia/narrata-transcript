---
name: close-ticket
description: Finish a TOOL ticket in one go - commit leftovers, update the roadmap, rebase on main, push, create and merge the PR, delete the branch, route follow-ups and set the ticket to Done. Invoke on "close the ticket", "/close-ticket", or when only merge and Jira remain.
---

# Close-Ticket

Runs from a finished branch to a closed ticket without stopping. Invoking it is the approval to push and merge, so don't ask again. Stop only where a step says so.

The push never goes directly to `main`; it always goes through a PR from the ticket branch.

| Constant | Value |
| --- | --- |
| Jira `cloudId` | `alethe1a.atlassian.net` |
| GitHub repo | `A1etheia/narrata-transcript` |
| Default branch | `main` |

Pre-conditions, checked before anything else:

- The branch matches `tool-<n>-<slug>`. Stop if on `main`.
- The Atlassian tools are available.
- `gh auth status` succeeds. Prefix `gh` with `GODEBUG=netdns=cgo` if DNS fails under WSL. If `gh` is missing or logged out, stop and ask the user to run `! sudo apt install gh` and `! gh auth login --web`. Don't merge locally or push `main` as a workaround.

## Steps

### 1. Clean tree

`git status --short`. If anything is uncommitted, run `/chunk-commit`. The tree must be clean afterwards.

Run `scripts/check` once more; don't close a ticket on a red check.

### 2. Roadmap

Update the roadmap on the ticket branch so it lands in the same PR. Skip this step if the ticket has no row in `docs/transcript-roadmap.py`.

Run `python3 docs/transcript-roadmap.py` and save its output to a file in the scratchpad as the date baseline. Then edit the task list `P` in `docs/transcript-roadmap.py`, which is the source; never edit the `.md` by hand:

- Set the ticket's note to `erledigt`, plus a pointer to its main artifact if it has one.
- Add each open item from `## Folge-Tickets` in `docs/plans/TOOL-<n>-*.md` to the note of the ticket it was handed to, as `aus TOOL-<n>: <item>`.
- Set `GENERATED` to today if anything changed.

Regenerate into a second file and compare it with the first. If the dates differ, mirror the changed tickets to Jira in step 8 with `editJiraIssue` (`customfield_10015`, `duedate`).

Commit `docs/transcript-roadmap.py` and `docs/transcript-roadmap.md` as `docs(roadmap): mark TOOL-<n> done (TOOL-<n>)`.

### 3. Rebase

```bash
git fetch origin main
git rebase origin/main
```

On conflict, run `git rebase --abort`, tell the user and stop. If the branch has no commits beyond `origin/main`, stop and report.

### 4. Push

```bash
git push -u origin HEAD
```

If a rebase rewrote already-pushed history, `git push --force-with-lease origin HEAD` is allowed on the ticket branch only. Never use plain `--force`, and never force `main`.

### 5. PR and merge

```bash
gh pr create --base main --head <branch> --title "<title>" --body "<summary>

Closes TOOL-<n>."
gh pr merge --merge --delete-branch
```

Use `--squash` for a single commit. Use the commit subject as the title for a single commit, otherwise the ticket title with a conventional prefix. End the PR body with the attribution line from the session, if there is one.

If the merge fails, stop and report the PR URL and the reason. Never bypass checks with `--admin`.

### 6. Local cleanup

```bash
git switch main
git pull --ff-only origin main
git branch -d <branch> || git branch -D <branch>
```

Use `-D` only after confirming the merge, since a squash merge makes `-d` fail. If the remote branch survives, delete it with `git push origin --delete <branch>`.

### 7. Route follow-ups

Run any chunk the plan schedules for after the merge.

Read `## Folge-Tickets` in `docs/plans/TOOL-<n>-*.md`. For each item:

- `[kein Ticket: <reason>]`: count it, nothing else.
- Carries a key: fetch that ticket with `fields: ["summary", "status", "issuelinks", "comment"]`.
  - Missing or Done: stop and ask the user.
  - Open: link it as Relates with `createIssueLink`, and comment `Übergabe aus TOOL-<n>: <item, verbatim>` with `addCommentToJiraIssue`. Skip either half if it already exists.
- Neither: stop and ask the user.

Use comments, not description edits. A description edit containing SQL-like text can be blocked by Cloudflare.

### 8. Done

Only after the merge: fetch `getTransitionsForJiraIssue`, take the one with `to.name == "Done"`, and call `transitionJiraIssue`. Mirror any changed roadmap dates from step 2.

### 9. Report

The PR URL, branch cleanup, Jira status, what changed in the roadmap, and how many follow-ups were routed or carried `[kein Ticket: …]`. Note any skipped or changed step.

## Anti-patterns

- `git push origin HEAD:main`, or bypassing checks with `--admin`.
- Resolving rebase conflicts without the user.
- Setting Done before the merge.
- Asking for confirmation before the push or merge.
- Updating the roadmap in a separate PR after the merge.
