# TOOL-55 — Zentraler End-to-End-CLI-Befehl für eine Session

## Ziel
`transcript process <gruppe>/<ordinal>` führt eine Sitzung in einem Befehl vom Preflight bis zum Abschlussbericht. An Sprecherzuordnung und Review hält er mit klarer Anweisung an. Ein zweiter Aufruf liest beides ein und läuft weiter. Heute braucht dieselbe Strecke 14 Einzelbefehle in der richtigen Reihenfolge, und welcher davon nötig ist, muss man selbst wissen.

## Ist-Stand
- Alle Schritte existieren als CLI-Handler in `src/transcript/__main__.py` mit Exit 0/1/2: `_doctor` (:337, ruft `preflight.run`), `_extract` (:364), `_context` (:396), `_snapshot` (:457, verwendet einen vorhandenen Snapshot ohne `--refresh` wieder), `_manifest` (:583), `_transcribe` (:613, inkl. Diarisierung, Hinweise und Bewertung über `_rate_passages` :1110; verwendet passende Segmente über `transcription.reusable` wieder), `_review_export` (:811), `_review_import` (:838), `_speakers` (:873, schreibt die Vorlage nur, wenn keine Zuordnung existiert: `speakers.write_template`, `speakers.py:276`), `_working` (:953), `_export` (:1011), `_render` (:1043), `_report` (:981).
- Wiederverwendung je Schritt: `extract`, `context` und `manifest` laufen jedes Mal neu. `context` ruft dabei Narrata über das Netz ab. `snapshot` und `transcribe` verwenden Vorhandenes wieder. `review-export` verweigert das Überschreiben eines vorhandenen Sheets (`review_sheet.write_sheet`, `review_sheet.py:178`).
- Preflight: `preflight.run` (`preflight.py:71`) prüft schon, ob `audio.json` zu den Aufnahmen passt (`_check_resume`, :356) und ob die WAVs da sind (`_check_disk`, :258, Prädikat „audio already extracted“).
- Bericht: `gaps` bedeuten unvollständig (Exit 1, `report.py:52`). Dass keine Sprecherzuordnung vorliegt, steht dort nur als `note` `no_assignment` (`report.py:356`). Eine unverändert übernommene Vorlage, in der alle Labels `open` sind, erzeugt weder Gap noch Note. `export.compose` übernimmt den Bericht als `stats` (`export.py:147`).
- TOOL-33 ist verworfen (M1). Schritt 5 des Tickets („Überlappungen konsolidieren“) entfällt deshalb, und „Audio vorbereiten“ heißt nur `extract`.

## Entscheidungen
- **Eigenes Modul `src/transcript/pipeline.py` als Ablaufsteuerung, die Handler bleiben die Schritte.** `pipeline.py` kennt die Schrittnamen, die Reihenfolge, die Regeln für Wiederverwendung, Halt und Abbruch und den Gesamt-Exit. Es druckt nichts und importiert keine Fachmodule. `__main__._process` verdrahtet jeden Schritt mit seinem vorhandenen Handler. So entsteht keine doppelte Fachlogik, und die Einzelbefehle bleiben unverändert.
- **Reihenfolge:** `preflight → extract → context → snapshot → manifest → transcribe → review → speakers → working → export → txt → docx → report`. `transcribe` umfasst wie heute Diarisierung und Bewertung.
- **Wiederverwendung nach Dateistand, ohne Statusdatei:**
  - `extract` wird übersprungen, wenn `audio.json` und alle Segment-WAVs vorhanden sind. Das Prädikat wandert als `audio.extracted(paths)` nach `audio.py`, und `preflight._check_disk` nutzt es mit.
  - `context` wird übersprungen, wenn `narrata/context.json` gespeichert ist. Ohne `--redo` gibt es also keinen Netzabruf.
  - `manifest` wird übersprungen, wenn das Manifest vorhanden ist. Es läuft trotzdem, wenn `--consent` übergeben wird und das Manifest noch keine Einwilligung enthält.
  - `snapshot` und `transcribe` laufen immer und verwenden selbst wieder.
  - `working`, `export`, `txt`, `docx` und `report` laufen immer, weil sie billig und deterministisch sind.
- **`--redo <schritt>`** für `extract`, `context`, `snapshot`, `manifest` und `transcribe`. Der genannte Schritt läuft erzwungen (`snapshot --refresh`, `transcribe --force`). Alle späteren dateibasiert übersprungenen Schritte laufen ebenfalls, damit z. B. nach neuem Audio auch das Manifest neu entsteht. Für die späteren Schritte gibt es kein `--redo`, weil sie ohnehin immer laufen.
- **Halt an den manuellen Schritten, ebenfalls über den Dateistand:**
  - `review`: Fehlt das Review-Sheet und gibt es mindestens eine offene Zeile (`review_sheet.review_sheet(...)`), schreibt `_review_export` das Sheet und der Schritt meldet `halted`. Ist das Sheet vorhanden, liest `_review_import` es ein, und es geht weiter.
  - `speakers`: Fehlt `assignment.json`, schreibt `_speakers` die Vorlage und die Hörproben und meldet `halted`. Ist die Datei vorhanden, wird sie geprüft, und es geht weiter.
  - Beide manuellen Schritte laufen vor dem Halt, damit Review und Zuordnung in einem Durchgang erledigt werden. Die Haltmeldung nennt nur Pfade: das Sheet, die Zuordnung, die Hörproben und den Befehl für den nächsten Lauf.
  - Ein zweiter Aufruf ohne Änderungen läuft durch, und offene Passagen und Labels bleiben offen. Damit ist ein Export ohne Zuordnung möglich.
- **Abbruch und Exit:**
  - Exit 2 bei Handler-Exit 2 an beliebiger Stelle.
  - Exit 1 sofort bei `transcribe` (Segment gescheitert oder offen; ein erneuter Lauf wiederholt nur diese Segmente) und bei `speakers` (die handgemachte Zuordnung enthält nicht anwendbare Einträge).
  - `working` mit Exit 1 läuft weiter, weil der Bericht die Befunde als Gap führt.
  - Exit 3 bei einem Halt für manuelle Schritte. Exit 1 am Ende, wenn `report` Gaps meldet, sonst 0.
  - Jeder Abbruch endet mit `process: stopped at <schritt> (exit <n>)`. Den Grund nennt die Fehlerzeile des Handlers unmittelbar davor.
- **Status je Schritt auf der Konsole:** `ran`, `reused` (übersprungen), `incomplete`, `halted` oder `failed`, als Abschlusszeile `process: extract reused, …`. Den Status dauerhaft speichern und Resume über alle Stufen sind Aufgabe von TOOL-57.
- **Neue Gap `open_speakers` im Bericht:** Segmente mit mindestens einem Label `assigned == "open"`. Grund: Das Akzeptanzkriterium „im Bericht als unvollständig gekennzeichnet“ erfüllt heute nur eine Note. Die unverändert übernommene Vorlage bleibt heute sogar ganz unmarkiert. Die Note `no_assignment` bleibt als Erklärung erhalten.
- **Optionen:** `--consent` und `--num-speakers` werden an `manifest` bzw. `transcribe` durchgereicht, und `--config` wie bei allen Befehlen. Der Audiostream bleibt 0. Wer einen anderen braucht, ruft vorher `transcript extract --stream` auf, und `process` verwendet das Ergebnis wieder.

## Daten-Check
- Aufnahmen: *handled*. `process` liest nichts selbst, die Handler arbeiten wie bisher in `input/` und `work/`.
- Transkripte, Namen, Wissens-Snapshot: *handled*. Auf die Konsole kommt nur, was die Handler schon heute nach TOOL-66 ausgeben, dazu Schrittnamen, Status und Pfade. Die Haltmeldung nennt Dateipfade, keine Inhalte.
- Logs und Fehlermeldungen: *handled*. Es gibt keinen neuen Logger. `process` läuft wie die anderen Schritte in `_log_to_stderr`, und die Abbruchzeile nennt nur Schritt und Exit.
- Neue Gap `open_speakers`: *handled*. Sie nennt nur Segmentnummern, keine Labels oder Personen.
- Fixtures: *handled*. Die `pipeline`-Tests arbeiten mit Fake-Schritten, die CLI-Tests mit gepatchten Handlern und `tmp_path`. Echte Daten kommen nicht vor.

## Contract-Check
- Export (IOA-1214, Contract 1.0): *handled*. Am Export ändert sich nichts. Die neue Gap steht in `stats`, das laut Schema ein offenes, von Narrata nicht interpretiertes Objekt ist (`transcript-v1.schema.json:115`). Narrata braucht keine Änderung und kein IOA-Ticket.
- Mehrere Aufnahmen: N/A. `export` verweigert sie bis TOOL-89 weiter, und `process` stoppt dann mit Exit 2 bei `export`. Der Preflight warnt vorher.
- Narrata-Endpoint: *handled*. `context` ruft nur ab, wenn kein gespeicherter Kontext existiert oder `--redo context` gesetzt ist.

## Resume-Check
- Abbruch: *handled*. `process` hat keinen eigenen Zustand. Ein erneuter Aufruf bestimmt den Stand aus den Dateien. Ein Abbruch mitten in `transcribe` hinterlässt nur fertige Segmente, und die verwendet `transcribe` wieder.
- Wiederverwendung: *handled*. Siehe Entscheidungen. Standardmäßig wird nichts erzwungen, `--redo` ist die einzige Ausnahme.
- Gleiches Modell und gleicher Snapshot: *handled*. Den Snapshot baut nur `--redo snapshot` neu. `transcribe` vergleicht Modell, Settings, Snapshot, Keywords und Sprache über `reusable`, und der Preflight warnt vorher, welche Segmente neu laufen würden.

## Dependency-Check
- N/A: keine neue Abhängigkeit und kein neues Modell.

## Format-Check
- `report.json` (`format_version: 1`): *handled, kein Bump*. `open_speakers` ist ein zusätzlicher Wert im bestehenden Feld `gaps[].code`, und bestehende Berichte bleiben gültig. Es gibt noch keinen Leser, der die Codes auswertet (TOOL-59 folgt). Der Bericht wird bei jedem `report`/`export` neu geschrieben, alte Artefakte veralten also nicht.
- Export-`stats`: N/A, weil das Feld offen ist (siehe Contract-Check).

## Chunks
### Chunk 1 — Gap `open_speakers` im Bericht
- Dateien: `src/transcript/report.py`, `tests/test_report.py`, `README.md` (Abschnitt „Abschlussbericht“)
- Änderung: neuer `GapCode` `open_speakers` mit den Segmenten der Labels `assigned == "open"`, deutscher Text in `report.md`. Der Export trägt die Gap automatisch über `stats`.
- Verify: `scripts/check`
- AC: Fehlende Zuordnung und unveränderte Vorlage erzeugen jeweils die Gap `open_speakers` (Exit 1). Eine vollständige Zuordnung erzeugt keine.

### Chunk 2 — Ablaufsteuerung `pipeline.py`
- Dateien: `src/transcript/pipeline.py`, `src/transcript/audio.py` (`extracted`), `src/transcript/preflight.py` (nutzt `audio.extracted`), `tests/test_pipeline.py`
- Änderung: `STEPS`/`StepName`, `Step(name, run, reusable, manual, stop_on_incomplete)`, `StepResult` (`ran`/`reused`/`incomplete`/`halted`/`failed`), `run(steps, redo) -> Outcome(exit_code, results, stopped_at)` mit den Regeln aus den Entscheidungen. Kein Druck, keine Fachimporte.
- Verify: `scripts/check`
- AC (mit Fake-Schritten): definierte Reihenfolge; Wiederverwendung als Standard; `--redo` erzwingt den Schritt und alle späteren dateibasierten; Halt erst nach dem letzten manuellen Schritt; der Abbruch nennt den Schritt; Exit 0/1/2/3 wie festgelegt.

### Chunk 3 — CLI `transcript process` und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_process.py`, `README.md` (neuer Abschnitt „Eine Sitzung in einem Befehl“)
- Änderung: Unterbefehl `process <session> [--redo SCHRITT] [--consent] [--num-speakers N] [--config]`. `_process` baut die Schritte aus den vorhandenen Handlern, die Prädikate aus `SessionPaths` und `audio.extracted`, und druckt Schrittköpfe, Haltanweisung, Abbruch- und Abschlusszeile.
- Verify: `scripts/check`; manuell `transcript process <session>` gegen eine lokale Sitzung in `input/`: erster Lauf hält an, zweiter Lauf läuft bis zum Bericht.
- AC: Der zentrale Befehl startet eine gültige Sitzung, hält an den manuellen Schritten mit Anweisung und läuft nach dem Einlesen weiter. Ein Fehler benennt den Schritt. Die Einzelbefehle bleiben unverändert (bestehende Tests grün).

## Folge-Tickets
- TOOL-57: dauerhafter Status und Resume über alle Stufen bauen auf `pipeline.STEPS` und `StepResult` auf. Übergabe-Kommentar beim Abschluss.
- TOOL-61: Die E2E-Doku beschreibt `transcript process`, die Haltpunkte und die Exit-Codes 0/1/2/3. Übergabe-Kommentar beim Abschluss.
- TOOL-86: Die Haltanweisung nennt für die Zuordnung dann `transcript speakers --assign` statt die Datei von Hand zu bearbeiten. Übergabe-Kommentar beim Abschluss.
- TOOL-89: Bis dahin stoppt `process` bei Sitzungen mit mehreren Aufnahmen an `export`. Übergabe-Kommentar beim Abschluss.
- Neue Review-Kandidaten nach einem schon eingelesenen Sheet (z. B. nach `--redo transcribe`): [kein Ticket: `transcript review-export --all --force` nach dem Import deckt das ab; im Pilot TOOL-58 beobachten]
- Ein dauerhaft scheiterndes Segment blockiert `process` an `transcribe`: [kein Ticket: Die Einzelbefehle bleiben nutzbar; ob es vorkommt, zeigt TOOL-58]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Gap `open_speakers` im Bericht | no |
| 2 | Ablaufsteuerung `pipeline.py` | no |
| 3 | CLI `transcript process` und Doku | no |
