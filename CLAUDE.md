# CLAUDE.md

## Projekt
**narrata-transcript** — lokale Python-Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte JSON-Transkripte für Narrata überführt. Jira-Projekt `TOOL`; die Narrata-Seite läuft als Epic `IOA-1213` im Repo `ios-archiv`.

Reihenfolge und Meilensteine: [`docs/transcript-roadmap.md`](docs/transcript-roadmap.md). Quelle ist `docs/transcript-roadmap.py`, die `.md` wird daraus generiert.

## Grenzen
- **Nur der JSON-Contract koppelt beide Seiten.** Narrata liest keine Arbeitsdateien, die Pipeline schreibt nie in die Datenbank. Das Schema gehört `ios-archiv` (IOA-1214); hier liegt höchstens eine versionierte Kopie.
- **V0.1 läuft vollständig lokal.** Rohaudio verlässt den Rechner nie.
- **Echte Sitzungsdaten kommen nie ins Repo.** Audio, Transkripte, Klarnamen und Wissens-Snapshots bleiben in `input/`, `work/`, `output/`; Fixtures sind anonymisiert. Das GitHub-Repo ist als öffentlich zu behandeln, solange es nicht privat gestellt ist.
- **Das ASR-Ergebnis wird nie überschrieben.** Unsicherheit bleibt sichtbar, kein Schritt erfindet Text.

## Sprache
Code, Identifier, Kommentare, Tests und Commits auf Englisch. README, Pläne und Doku auf Deutsch.

## Commands
```bash
scripts/check        # Lint, Formatprüfung, Tests
scripts/check --fix  # vorher automatisch korrigieren
```

## Shell-Befehle
`blockReadsOutsideWorkingDirectories` ist aktiv; Befehle, deren Pfade der Parser nicht prüfen kann, lösen eine Rückfrage aus. Deshalb:
- Kein `cd … &&` / `cd …;` vor Befehlen. Die Shell startet im Projektordner; relative oder absolute Pfade direkt verwenden.
- Keine Python- oder Shell-Heredocs (`python3 - <<'EOF'`) zum Bearbeiten von Dateien. Dateien mit Read/Edit/Write lesen und ändern.
- Dateien lieber mit dem Read-Tool lesen als mit `cat`; suchen mit `grep -n` und expliziten Pfaden.
- Temporäre Dateien nur im Scratchpad der aktuellen Sitzung, nie in dem einer früheren.
- Diese Regeln gelten auch für Subagents (Explore usw.) und gehören in deren Prompt.

## Workflow
`/plan-story TOOL-<n>` → umsetzen → `/chunk-commit` → `/close-ticket`.

- **Branch:** `tool-<n>-<1-3 keywords>`, immer `git fetch origin main && git switch -c <name> --no-track origin/main`.
- **Commit:** Conventional Commits mit Ticket-Suffix, z. B. `feat(audio): extract audio track (TOOL-10)`.
- **Plan:** `docs/plans/TOOL-<n>-<slug>.md`, vor der Umsetzung committet, nach dem Merge eingefroren.
- **Folge-Tickets:** Jeder Eintrag trägt einen Ticket-Key oder `[kein Ticket: <Grund>]`.
