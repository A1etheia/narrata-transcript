---
name: chunk-commit
description: Close a chunk - auto-fix, quality gate, /simplify, re-check, conventional commit with the TOOL ticket number. Invoke when a chunk is ready to commit, not during the edit loop.
---

# Chunk-Commit

Run this when the edits are in place and no design question is open.

## Steps

### 1. Fix and check

```bash
scripts/check --fix
```

On failure, fix the cause and re-run. After two failed iterations, stop and ask the user.

For a docs-only diff, skip to step 3.

### 2. `/simplify`

Run `/simplify` and fix its findings in place, then re-run `scripts/check` if anything changed. Skip this for docs-only and tests-only diffs.

### 3. Review what will be committed

```bash
git status --short
git diff --stat HEAD
```

Before staging, check the diff for real session data: audio, transcripts, participant names, snapshots, tokens. If any appears, stop and tell the user.

Stage specific paths, never `git add -A` or `git add .`.

### 4. Commit

Derive the ticket number from the branch `tool-<n>-<slug>`.

```bash
git commit -F - <<'EOF'
<type>(<scope>): <description> (TOOL-<n>)

<optional 1-3 sentences on why>

Co-Authored-By: Claude <active model name> <noreply@anthropic.com>
EOF
```

- `<type>`: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
- `<scope>`: the pipeline area, such as `audio`, `asr`, `knowledge`, `review`, `export`.
- Description: imperative, at most 72 characters.

If a commit fails, fix the problem and create a new commit. Don't use `--amend`, which would change the previous commit.

### 5. Verify

```bash
git status --short
git log --oneline -3
```

Report the commit SHA.
