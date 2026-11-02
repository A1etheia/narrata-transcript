---
name: close-ticket
description: Finish a TOOL ticket - commit leftovers, rebase on main, push the branch, open and merge a PR, clean up, route follow-ups and set the ticket to Done. Invoke on "close the ticket", "/close-ticket", or when only merge and Jira remain.
---

# Close-Ticket

The push never goes directly to `main`; it always goes through a PR from the ticket branch.

| Constant | Value |
| --- | --- |
| Jira `cloudId` | `alethe1a.atlassian.net` |
| GitHub repo | `A1etheia/narrata-transcript` |
| Default branch | `main` |

Pre-conditions: the branch matches `tool-<n>-<slug>`, and the Atlassian tools are available. `gh` is optional; see step 4. Stop if on `main`.

## Steps

### 1. Clean tree

`git status --short`. If anything is uncommitted, run `/chunk-commit`. The tree must be clean afterwards.

Run `scripts/check` once more; don't close a ticket on a red check.

### 2. Rebase

```bash
git fetch origin main
git rebase origin/main
```

On conflict, run `git rebase --abort`, tell the user and stop. If the branch has no commits beyond `origin/main`, stop and report.

### 3. Push

```bash
git push -u origin HEAD
```

If a rebase rewrote already-pushed history, `git push --force-with-lease origin HEAD` is allowed on the ticket branch only. Never use plain `--force`, and never force `main`.

### 4. PR and merge

Check `gh auth status`.

**With `gh`:**

```bash
gh pr create --base main --head <branch> --title "<title>" --body "<summary>

Closes TOOL-<n>."
gh pr merge --merge --delete-branch
```

Use `--squash` for a single commit. Use the commit subject as the title for a single commit, otherwise the ticket title with a conventional prefix. Prefix `gh` with `GODEBUG=netdns=cgo` if DNS fails under WSL.

**Without `gh`:** print `https://github.com/A1etheia/narrata-transcript/compare/main...<branch>?expand=1` and stop. Ask the user to merge the PR, and continue from step 5 when they confirm. Don't merge locally or push `main` as a workaround.

### 5. Local cleanup

```bash
git switch main
git pull --ff-only origin main
git branch -d <branch> || git branch -D <branch>
```

Use `-D` only after confirming the merge, since a squash merge makes `-d` fail. If the remote branch survives, delete it with `git push origin --delete <branch>`.

### 6. Route follow-ups

Read `## Folge-Tickets` in `docs/plans/TOOL-<n>-*.md`. For each item:

- `[kein Ticket: <reason>]`: count it, nothing else.
- Carries a key: fetch that ticket with `fields: ["summary", "status", "issuelinks", "comment"]`.
  - Missing or Done: stop and ask the user.
  - Open: link it as Relates with `createIssueLink`, and comment `Übergabe aus TOOL-<n>: <item, verbatim>` with `addCommentToJiraIssue`. Skip either half if it already exists.
- Neither: stop and ask the user.

Use comments, not description edits. A description edit containing SQL-like text can be blocked by Cloudflare.

### 7. Done

Only after the merge: fetch `getTransitionsForJiraIssue`, take the one with `to.name == "Done"`, and call `transitionJiraIssue`.

### 8. Report

The PR URL, branch cleanup, Jira status, and how many follow-ups were routed or carried `[kein Ticket: …]`. Note any skipped or changed step.

## Anti-patterns

- `git push origin HEAD:main`, or bypassing checks with `--admin`.
- Resolving rebase conflicts without the user.
- Setting Done before the merge.
