---
name: check-ticket-deps
description: Audit a TOOL ticket's blocked-by chain, including IOA dependencies, before locking a plan. Reports each dependency's status and flags rescoped dependencies. Read-only. Use from /plan-story or when the user asks whether a ticket can start.
---

# Check Ticket Dependencies

Checks that a ticket's assumptions about its dependencies still hold. This is diagnostic only: no edits, no commits.

Invoked with a key, e.g. `/check-ticket-deps TOOL-41`.

## Steps

### 1. Fetch the ticket

`mcp__claude_ai_Atlassian_Rovo__getJiraIssue` with `cloudId: alethe1a.atlassian.net`, the key, and `fields: ["summary", "status", "description", "issuelinks"]`.

Collect dependencies from both `issuelinks` and the description (`Blocked by`, `braucht`, ticket keys named as prerequisites). The two are not always identical, and many pipeline dependencies are written only in prose.

### 2. Walk the direct blocked-by links

Fetch each dependency with `fields: ["summary", "status", "description"]`. Stop at depth 1. Dependencies may live in `TOOL` or `IOA`.

Note the status and any divergence marker in the description, case-insensitive: `scope-rewrite`, `scope-change`, `rescoped`, `scope out`, `Divergenzen vs.`, `deprecated`, `verworfen`, `zusammengeführt`.

### 3. Check downstream

Fetch only the status of each `blocks` link. An In Progress consumer limits how freely the plan can change an interface.

### 4. Report

Under 500 words, with the key anchoring every line:

- **Ticket:** key, summary, status.
- **Clean:** Done, no divergence marker.
- **Needs attention:** a divergence marker, or not Done while the ticket assumes it is. Say what changed and which acceptance criterion may be stale.
- **Downstream:** key, summary, status.

If a dependency is open but the ticket documents a fallback (TOOL-67's file fallback for IOA-1215), report it as clean with the fallback named.

### 5. Recommend

All clean: say the plan can be locked. Otherwise ask the user how to resolve each finding; never decide between ticket wording and dependency reality yourself.
