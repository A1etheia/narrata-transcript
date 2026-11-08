# TOOL-48 — Review-CSV-Reimport

## Ziel
Die in LibreOffice/Excel bearbeitete `work/<s>/review/review.csv` lässt sich mit `transcript review-import <gruppe>/<ordinal>` wieder einlesen. Gültige Entscheidungen landen in `review/decisions.json`. Fehlerhafte Zeilen werden mit Zeile, ID und Feld gemeldet und nicht übernommen. Bisher führt der Weg nur hinaus (TOOL-47), Entscheidungen lassen sich nicht zurückholen.

## Ist-Stand
- `src/transcript/decisions.py:90` `decide()` setzt eine Entscheidung und ersetzt eine frühere. `ValueError` bei unbekannter ID oder ungültiger Entscheidung, Prüfung in `ReviewDecision.__post_init__` (`:57`): Status, Zieltext nur und zwingend bei `corrected`, keine leere Notiz.
- `src/transcript/decisions.py:167` `write_decisions()` schreibt atomar, `:187` `load_decisions()` lädt ohne CSV.
- `src/transcript/decisions.py:144` `review_items()` paart Kandidaten mit gültiger, veralteter oder verwaister Entscheidung.
- `src/transcript/review_sheet.py:38` `SHEET_COLUMNS`, `:58` `_FORMULA_START`, `:161` `_text()` setzt das `'` und `:168` `render()` schreibt `;`, UTF-8 mit BOM, CRLF. `version` ist `found.processed_at[segment]` (`:79`).
- `src/transcript/calibration.py:482-487` erkennt `;`/`,` aus der Kopfzeile und liest mit `utf-8-sig`.
- `src/transcript/__main__.py:193`, `:725` `review-export`: Fehler auf stderr, Exit 2, Konsole nur Zahlen und IDs.
- `src/transcript/session.py:128`, `:133` `review_decisions`, `review_sheet`.
- Tests: `tests/test_review_sheet.py`, `tests/test_decisions.py`, CLI in `tests/test_smoke.py:1232`.

## Entscheidungen
- **Gültige Zeilen übernehmen, fehlerhafte melden** (Vorgabe der Nutzerin): Jede gültige Zeile geht über `decide()`, jede fehlerhafte wird übersprungen und gemeldet, Exit 2. Ganz ab bricht der Import nur bei Dateifehlern: Datei unlesbar, Pflichtspalte fehlt (`id`, `status`, `target_text`, `note`, `version`) oder eine ID kommt doppelt vor. Bei einer doppelten ID ist unklar, welche Zeile gilt. `decisions.json` wird nur bei mindestens einer Änderung geschrieben, einmal und atomar.
- **Unveränderte Zeilen sind kein Import:** Stimmen Status, Zieltext und Notiz mit der geltenden Entscheidung überein (ohne Entscheidung: `open`, leer, leer), wird die Zeile übersprungen, und `decided_at` bleibt. So ändert eine unverändert reimportierte Datei nichts (AC 1). Ein zweiter Import derselben Datei nach einer Korrektur ist ebenfalls folgenlos.
- **Zeilenfehler:** unbekannte ID; `version` ≠ `processed_at` des Segments (veraltet), geprüft nur bei geänderten Zeilen, damit eine unberührte Zeile eines älteren Exports nach neuer Transkription keinen Fehler erzeugt; Status nach `strip().casefold()` nicht in `STATUSES`; `corrected` ohne Zieltext; Zieltext bei anderem Status. Die drei letzten meldet `ReviewDecision` selbst als `ValueError`, die Meldung wird übernommen.
- **Toleranz:** Zellen werden getrimmt, leerer `status` gilt als `open`. Leere Zeilen werden übersprungen, auch `;;;`-Zeilen, die Tabellenprogramme anhängen. Weitere Spalten werden ignoriert, `text` wird nie gelesen.
- **Formelschutz rückgängig:** Ein führendes `'` wird in `target_text`/`note` nur entfernt, wenn danach ein Zeichen aus `_FORMULA_START` folgt. Ein gewolltes `'s` bleibt so erhalten.
- **Zeilennummer = Tabellenzeile:** Datensatznummer + 1 (Kopfzeile = 1), auch bei mehrzeiligen Zellen. So entspricht sie der Zeilennummer in Excel.
- **CSV lesen geteilt:** Die Trennzeichen-Erkennung aus `calibration.judged_precision` wandert in eine kleine Funktion `read_sheet(path) -> (columns, rows)` in einem neuen Modul `src/transcript/sheetfile.py`. Kalibrierung und Reimport nutzen sie.
- **Neues Modul `src/transcript/review_import.py`:** reine Funktion `import_sheet(found, decisions, rows, now) -> ImportResult` (neue `SessionDecisions`, Zähler je Status, unverändert, Fehlerliste) plus `read_review_sheet(path)`. Die CLI bleibt dünn.
- **`review.csv` bleibt liegen.** Der nächste Export braucht weiter `--force`. Den Hinweis in `write_sheet` (`:186`) lasse ich, wie er ist.

## Daten-Check
- *handled:* Fehlermeldungen nennen nur Datei, Zeile, ID und Feld, nie Zellinhalt. Konsole nur Zähler und IDs, wie bei `review-export` (TOOL-66).
- *handled:* Das Modul loggt nichts. Gelesen wird nur unter `work/`, geschrieben nur `decisions.json` unter `work/`.
- *handled:* Test-Fixtures entstehen aus den anonymisierten Bausteinen in `tests/test_uncertainty.py` / `test_candidates.py`, ohne echte Sitzungsdaten.
- *handled:* `candidates.json` und das Referenztranskript werden nie geschrieben (Test prüft Bytes vor/nach), ASR-Ergebnis bleibt unberührt.

## Contract-Check
- N/A, weil weder Contract-JSON noch der Narrata-Endpoint berührt werden. `decisions.json` ist intern.

## Resume-Check
- N/A, weil der Import kurz und lokal läuft und kein Modell nutzt. Bei einem Abbruch bleibt `decisions.json` durch `write_atomic` alt oder neu, nie halb. Ein erneuter Import ist idempotent.

## Dependency-Check
- N/A, weil nur die Standardbibliothek (`csv`) genutzt wird.

## Format-Check
- *handled:* `decisions.json` behält Struktur und `format_version: 1`, es kommen nur Einträge hinzu. Bestehende Dateien bleiben lesbar.
- *handled:* `review.csv` hat kein Versionsfeld und bleibt unverändert. Der Reimport hängt nur an fünf Spaltennamen, nicht an der Spaltenreihenfolge.

## Chunks
### Chunk 1 — CSV-Leser teilen
- Dateien: `src/transcript/sheetfile.py` (neu), `src/transcript/calibration.py`, `tests/test_calibration.py` (bestehende Tests müssen grün bleiben, ggf. ein Test für `,`)
- Änderung: `read_sheet(path) -> tuple[set[str], list[dict[str, str]]]` mit `utf-8-sig`, Erkennung `;`/`,` und `OSError/UnicodeDecodeError/csv.Error` → eigener Fehler. `judged_precision` nutzt sie.
- Verify: `scripts/check`
- AC: Kalibrierung verhält sich unverändert.

### Chunk 2 — Reimport-Logik
- Dateien: `src/transcript/review_import.py` (neu), `tests/test_review_import.py` (neu)
- Änderung: Pflichtspalten, doppelte IDs, Zeilenprüfung, Formelschutz zurück, Abgleich mit geltender Entscheidung, `decide()` je geänderter Zeile, `ImportResult`.
- Verify: `scripts/check`
- AC: Export → unveränderter Reimport gibt 0 Änderungen. Eine gültige Zeile ist dem richtigen Kandidaten zugeordnet. Unbekannte ID, ungültiger Status, `corrected` ohne Zieltext, Zieltext bei `confirmed` und veraltete `version` werden gemeldet und nicht übernommen, die übrigen Zeilen schon. Doppelte ID und fehlende Spalte brechen ab. `'=…` wird zu `=…`, `'s` bleibt. Kandidaten-Objekt unverändert.

### Chunk 3 — Command `review-import`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`
- Änderung: `transcript review-import <gruppe>/<ordinal> [--config]` liest `paths.review_sheet`; fehlt die Datei, Hinweis auf `transcript review-export`; fehlen Kandidaten, Hinweis auf `assess`. Ausgabe `review import: N decision(s): …, M unchanged`, Zeilenfehler auf stderr, Exit 0 ohne, 2 mit Fehlern. `decisions.json` wird nur bei Änderungen geschrieben.
- Verify: `scripts/check`
- AC: Export, Zeile in Datei ändern, Import → `load_decisions` liefert die Entscheidung ohne CSV. Fehlerzeile → Exit 2, gültige trotzdem gespeichert, `candidates.json` byte-gleich. Kein Zellinhalt auf der Konsole.

### Chunk 4 — Doku
- Dateien: `README.md` (neuer Abschnitt „Review-Import“ nach „Review-CSV“; Verweise in „Review-Entscheidungen“ `:352` und „Review-CSV“ `:361` auf den Import aktualisieren), `src/transcript/review_sheet.py:11` Docstring auf das Modul zeigen lassen
- Verify: `scripts/check`
- AC: Regeln (Pflichtspalten, Zeilenfehler, unveränderte Zeilen, Formelschutz, Exit-Codes) beschrieben.

## Folge-Tickets
- Vorschlagsdatei aus `corrected`-Entscheidungen: TOOL-80 (besteht, liest `decisions.json`).
- Anwenden der Entscheidungen auf die Arbeitsfassung: TOOL-49 (besteht).
- Markierung „importiert“ an `review.csv`, damit der nächste Export ohne `--force` geht: [kein Ticket: erst nach dem Pilot (TOOL-60) beurteilbar, ob das stört]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | CSV-Leser in `sheetfile.py`, Kalibrierung umstellen | no |
| 2 | `review_import.py` mit Tests | no |
| 3 | CLI `review-import` mit Smoke-Tests | no |
| 4 | README und Docstrings | no |
