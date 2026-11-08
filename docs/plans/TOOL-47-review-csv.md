# TOOL-47 — Review-CSV für problematische Stellen

## Ziel
`transcript review-export <gruppe>/<ordinal>` schreibt die noch offenen Review-Kandidaten einer Session als CSV. Die Datei öffnet in einem deutschen Excel per Doppelklick mit richtigen Spalten, Umlauten und Zeilenumbrüchen. Jede Zeile zeigt ID, Zeit, Text, Stufe, Gründe und Hinweise und hat leere Felder für Status, Zieltext und Notiz. Heute liegen Kandidaten und Entscheidungen nur als JSON vor (TOOL-36, TOOL-46), und es gibt nichts, was sich für das Anhören eignet. TOOL-48 liest die ausgefüllte Datei später wieder ein.

## Ist-Stand
- `src/transcript/candidates.py:59` `ReviewCandidate`: `id` (`s01-p0042`, `:54`), `segment`, `passage`, `rating` (Stufe, Gründe, `missing`), `text` unverändert, `speaker`, `time: SessionSpan | None`, `hints`. Gespeichert wird in Review-Reihenfolge (`:214`: `uncertain` zuerst, dann starke Hinweise, dann Aufnahmereihenfolge). `load_candidates` (`:277`) liest `review/candidates.json`. `RatedSegment.reference_processed_at` (`:92`) nennt die Fassung je Segment.
- `src/transcript/decisions.py:147` `review_items(found, decisions)` liefert `ReviewState` mit `items` (Kandidat, gültige Entscheidung, `status`), `stale` und `orphaned` (`:141`). Laden mit `load_decisions` (`:188`), fehlende Datei heißt keine Entscheidungen. `ReviewStatus` steht in `:32`.
- `src/transcript/uncertainty.py:73` `Reason` (`rule`, `level`, `value`, `threshold`, `words`) und `:84` `PassageRating` (`missing`).
- `src/transcript/hints.py:78` `Hint` (`heard`, `signal`, `method`, `score`, `candidates`, `ambiguous`) und `:61` `Candidate` (`type`, `id`, `term`, `kind`, `field`, `relevance`, `biased`).
- `src/transcript/session_time.py:27` `SessionSpan` (`start_ms`/`end_ms` Session-Zeit, `local_start_ms` im Segment-WAV); `src/transcript/timecode.py:16` `format_ms`.
- `src/transcript/jsonfile.py:128` `write_bytes_atomic`.
- Vorbild CSV: `src/transcript/calibration.py:453` `write_sheet` (Komma, UTF-8 ohne BOM). Der Leser `:482` erkennt `;` schon automatisch.
- CLI: `src/transcript/__main__.py:62` Subparser, Fehlerbehandlung wie in `_calibrate` (`:654`). CLI-Tests stehen in `tests/test_smoke.py`.
- `src/transcript/session.py:123` `review_candidates`, `:128` `review_decisions`. Für die CSV gibt es noch keinen Pfad.

## Entscheidungen
- **Neues Modul `src/transcript/review_sheet.py`**, Pfad `work/<s>/review/review.csv` (`SessionPaths.review_sheet`). Die Datei liegt neben `candidates.json` und `decisions.json` unter `work/`.
- **Format für deutsches Excel** (entschieden mit der Nutzerin): Trennzeichen `;`, UTF-8 mit BOM (`utf-8-sig`), Zeilenende CRLF, Quoting über `csv` (`QUOTE_MINIMAL`). Mehrzeilige Texte, `;` und `"` stehen damit korrekt in einer Zelle.
- **Umfang** (entschieden mit der Nutzerin): Standard sind die Status `open` und `deferred`. Dazu zählt jeder Kandidat mit veralteter Entscheidung, denn `review_items` behandelt ihn als offen. `--all` nimmt alle Kandidaten auf. Status, Zieltext und Notiz einer gültigen Entscheidung sind dann schon eingetragen. Sichere Passagen erscheinen nie, sie sind keine Kandidaten.
- **Reihenfolge chronologisch** nach Segment und Passage, also nach Session-Zeit, wie das Ticket es verlangt. Die Spalte `order` hält die Position in der Review-Reihenfolge aus `candidates.json` fest. Wer nach ihr sortiert, bekommt `uncertain` und starke Hinweise zuerst. Die CSV enthält keinen Exportzeitstempel, gleiche Eingabe ergibt also byteweise die gleiche Datei.
- **Spalten**, in dieser Reihenfolge:
  `id`, `start` (Session-Zeit `HH:MM:SS.mmm`, leer ohne Zeit), `end`, `segment`, `segment_start` (Zeit im Segment-WAV, zum Suchen im Audio), `speaker`, `level`, `order`, `reasons` (je Grund `rule value/threshold`, getrennt durch `; `, ohne Werte nur `rule`), `missing`, `hints` (je Hinweis `signal „heard“ → type id term (kind, relevance)`, mehrere Einträge eines Hinweises mit ` | `, `ambiguous` angehängt, Hinweise durch Zeilenumbruch getrennt), `text`, `status`, `target_text`, `note`, `earlier_decision`, `version`.
  Für TOOL-48 sind nur `id`, `status`, `target_text`, `note` und `version` Eingabe, alle anderen Spalten dienen der Anzeige.
- **`version`** = `reference_processed_at` des Segments. Damit erkennt TOOL-48 eine CSV, die vor einer Neutranskription exportiert wurde, und hängt ihre Entscheidungen nicht an neuen Text.
- **Veraltete Entscheidungen** stehen beim Kandidaten in `earlier_decision` (`corrected 2027-02-01T…, older transcript`). Ihr Zieltext wird nicht vorausgefüllt, weil er zu anderem Text gehört. **Verwaiste Entscheidungen** haben keinen Kandidaten und damit weder Text noch Zeit. Die Konsole zählt sie und nennt ihre IDs, das sind nur Zahlen. Die CSV bleibt so reine Kandidatenliste, und TOOL-48 muss keine Fremdzeilen überspringen.
- **Formelschutz:** Excel hält eine Zelle, die mit `=`, `+`, `-` oder `@` beginnt, für eine Formel, etwa die ASR-Zeile „- Ja, genau“. Solchen Zellen in den Freitextspalten (`text`, `hints`, `target_text`, `note`) wird ein `'` vorangestellt. Das ist eine reine Anzeigekopie: `text` liest niemand zurück, das ASR-Ergebnis bleibt unverändert. TOOL-48 entfernt beim Einlesen von `target_text` und `note` genau dieses Präfix (Hinweis in der Roadmap).
- **Kein stilles Überschreiben:** Liegt `review.csv` schon vor, bricht der Befehl ab, denn sie kann ausgefüllte, noch nicht importierte Entscheidungen enthalten. `--force` überschreibt. Geschrieben wird atomar mit `write_bytes_atomic`.
- **Konsole nur mit Zahlen und IDs**, etwa `review sheet: 61 row(s): 54 open, 7 deferred; 2 stale, 1 orphaned decision(s): s02-p0113` und `wrote …/review.csv`.
- **Kein zusätzliches Tabellenformat** (xlsx/ods): Die CSV erfüllt die Kriterien, xlsx brächte eine Abhängigkeit.

## Daten-Check
- TOOL-66: handled. Die CSV enthält erkannten Text, Archivnamen, Zieltexte und Notizen und liegt deshalb nur unter `work/` (gitignored, `*.csv` ist nicht global ausgeschlossen). Fehlermeldungen nennen Datei und Feld, nie Inhalt.
- Logs und Konsole: handled. Gezeigt werden nur Zahlen und Kandidaten-IDs (`s01-p0042`), kein Text und kein Name. Das Modul loggt nichts.
- Repo und Fixtures: handled. Die Tests bauen Kandidaten und Entscheidungen synthetisch wie `tests/test_decisions.py`, mit erfundenem Text samt Umlauten, Zeilenumbruch, `;` und führendem `-`.

## Contract-Check
- N/A, weil die CSV eine interne Arbeitsdatei ist, die Narrata nie liest. Sie hat keinen Bezug zu IOA-1214, und Narrata braucht keine Änderung.

## Resume-Check
- N/A, weil weder Modell noch lange Laufzeit im Spiel sind. Ein Abbruch lässt dank atomarem Schreiben die alte CSV stehen.

## Dependency-Check
- N/A, weil nur `csv` aus der Standardbibliothek dazukommt.

## Format-Check
- handled. Die CSV ist ein neues Format ohne Versionsfeld: Die Kopfzeile ist die Schnittstelle zu TOOL-48, das die Pflichtspalten prüft. `version` je Zeile bindet sie an die Transkriptfassung. `candidates.json` und `decisions.json` bleiben unverändert v1. Bestehende Artefakte gibt es keine.

## Chunks
### Chunk 1 — CSV-Modul
- Dateien: `src/transcript/review_sheet.py`, `src/transcript/session.py` (`review_sheet`), `tests/test_review_sheet.py`
- Änderung: `SHEET_COLUMNS`, `sheet_rows(found, decisions, include_all)` aus `review_items` mit Auswahl, chronologischer Sortierung, `order`, `earlier_decision`, `version` und Formatierung von Gründen und Hinweisen; `render(rows) -> bytes` (BOM, `;`, CRLF, Formelschutz); `write_sheet(paths, rows, force)` mit Abbruch bei vorhandener Datei.
- Verify: `scripts/check`
- AC: Standard enthält nur `open`/`deferred`, ein veralteter Kandidat erscheint als `open` mit `earlier_decision` und ohne Zieltext; `--all` enthält alle mit vorausgefüllten Feldern; Reihenfolge chronologisch und zweimal byteweise gleich; Umlaute, Zeilenumbruch und `;` überstehen `csv`-Rundlauf mit `utf-8-sig`; Datei beginnt mit BOM; `- Ja` wird zu `'- Ja`; vorhandene Datei ohne `force` → Fehler, Inhalt unverändert; leere Kandidatenliste → nur Kopfzeile.

### Chunk 2 — Befehl `review-export`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`
- Änderung: Subparser `review-export <session> [--all] [--force] [--config]`; lädt `load_candidates` und `load_decisions`, schreibt, gibt Zahlen und verwaiste IDs aus; Exit 0, bei Fehlern 2 mit `error: …`.
- Verify: `scripts/check`; einmal manuell an einer echten Session ausführen und die Datei in Excel öffnen (Spalten, Umlaute, mehrzeiliger Text, `version` bleibt Text)
- AC: Ohne `candidates.json` Fehler mit Hinweis `run transcript assess`; vorhandene CSV ohne `--force` → Exit 2; Konsole ohne Text; zweiter Lauf mit `--force` erzeugt dieselbe Datei.

### Chunk 3 — Dokumentation
- Dateien: `README.md` (Abschnitt „Review-CSV“ nach „Review-Entscheidungen“, Satz in `:352` und Verzeichnisbaum `review/` anpassen), `docs/transcript-roadmap.py` (Hinweis TOOL-47 erledigt; Hinweis TOOL-48 ergänzt um `version`-Prüfung, Entfernen des `'`-Präfixes, Pflichtspalten, `;`/`,`-Erkennung wie `calibration.judged_precision`; `.md` neu generieren)
- Änderung: Befehl, Spalten, Umfang, Formelschutz, Überschreibschutz, Umgang mit veralteten und verwaisten Entscheidungen.
- Verify: `scripts/check`
- AC: README beschreibt alle Spalten und welche davon TOOL-48 liest.

## Folge-Tickets
- Reimport mit `version`-Prüfung und Entfernen des Formelschutz-Präfixes: TOOL-48 (Hinweis in der Roadmap)
- Zusätzliches xlsx/ods-Format: `[kein Ticket: CSV erfüllt die Kriterien; erst, wenn das Pilot-Review (TOOL-60) es verlangt]`
- Verwaiste Entscheidungen in einer eigenen Datei ausgeben: `[kein Ticket: Konsole mit IDs reicht, bis TOOL-48 zeigt, dass sie häufig vorkommen]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Modul `review_sheet.py`, Tests | no |
| 2 | CLI `review-export`, Smoke-Tests | no |
| 3 | README, Roadmap-Hinweise | no |
