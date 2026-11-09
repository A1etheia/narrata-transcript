# TOOL-57 — Pipeline-Status und Resume über alle Verarbeitungsschritte

## Ziel
`transcript status <gruppe>/<ordinal>` zeigt den Gesamtstatus einer Sitzung und den Status jedes Schritts. Abgeleitet wird beides nur aus den Dateien unter `work/` und `output/`, nie aus einer Statusdatei. `transcript process` setzt nach einem Abbruch fort, wo es nötig ist. Es transkribiert aber nicht stillschweigend mit einem anderen Modell oder Snapshot neu. Schrittwechsel und Fehlversuche stehen dauerhaft in `work/<s>/pipeline.log` (dafür wird TOOL-77 aufgenommen). Heute sieht man den Stand nur in der Abschlusszeile eines `process`-Laufs, und Fehlversuche nur als `WARNING` auf stderr.

## Ist-Stand
- `src/transcript/pipeline.py:16-110`: `StepName`/`STEPS`, `Step`, `Result` mit `ran|reused|incomplete|halted|failed`, `run()`. Das Modul hat keinen Zustand und druckt nichts.
- `src/transcript/__main__.py:1115-1203` `_process`: verdrahtet die Handler und erkennt Wiederverwendung über den Dateistand (`_extracted` :1206, `_manifest_in_place` :1214). Halt über `_review_step` :1226 und `_speakers_step` :1234.
- `src/transcript/preflight.py:353` `_check_resume`: vergleicht `audio.json` mit den Aufnahmen (`_audio_metadata_problem` :440). Weicht `transcription.reusable` ab, gibt es nur eine **Warnung** (:416).
- Frische-Prüfungen gibt es schon: `working.load_current` (`working.py:335`) vergleicht die gespeicherte mit der neu berechneten Fassung. `report.compose` verweigert eine veraltete Arbeitsfassung (`report.py:409`). Export (`export.py:133`), TXT und DOCX (`docx_render.py:232`, feste `_ZIP_TIME`) sind deterministisch.
- `review_import.import_rows` (`review_import.py:79`) ist rein und meldet `changed`. Ein unverändertes Sheet schreibt keine `decisions.json` (`__main__.py:894`).
- Gaps des Berichts: `report._gaps` (`report.py:326`). Die Note `open_speakers` beruht auf `assigned == "open"`.
- Logs: `_log_to_stderr` (`__main__.py:1412`) hängt nur einen stderr-Handler an den Logger `transcript`. `retry.FailureLog` (`retry.py:86`) loggt bereinigte Meldungen ohne `exc_info`. Transkripttext läuft über `transcript.text.*` mit `propagate=False` (`debug_log.py:13`).
- `.gitignore:27-29` schließt `input/`, `work/` und `output/` aus.

## Entscheidungen
- **Status ohne Statusdatei.** Ein neues Modul `src/transcript/status.py` berechnet `SessionStatus(steps, overall, resume_from)` nur über die vorhandenen Lader und Prüfungen. Es schreibt nichts, ruft kein Netz und lädt kein Modell. Modellvergleiche bleiben beim Preflight.
- **Status je Schritt:** `pending` (nicht gestartet), `done` (erfolgreich), `partial` (teilweise erfolgreich), `failed`, `waiting` (wartet auf Review/Zuordnung), `stale` (vorhanden, aber veraltet oder inkonsistent; zählt nie als erfolgreich).
  - `extract`: Prüft `audio.extracted` und den Abgleich `audio.json` ↔ Aufnahmen. `_audio_metadata_problem` wandert dafür als `manifest.audio_metadata_problem` nach `manifest.py`.
  - `context`/`snapshot`/`manifest`: Datei vorhanden und ladbar. Eine Snapshot-Drift ist nur ein Hinweis, kein `stale`, weil der Snapshot gültig bleibt.
  - `transcribe`: Status jeder Referenz (`transcribed`/`failed`/fehlt). `stale` gilt, wenn `asr.knowledge_snapshot_id` nicht der aktuelle Snapshot ist oder die Kandidaten eine andere Version bewerten (`processed_at`).
  - `review`: Kein Sheet, aber offene Kandidaten ergibt `pending`. Ein Sheet, das noch nicht eingelesen wurde (`import_rows(...).changed`), oder ein unberührtes Sheet ohne Entscheidungen ergibt `waiting`. Nach dem Einlesen gilt `partial`, solange noch Kandidaten offen sind, sonst `done`.
  - `speakers`: `waiting`, wenn alle Labels `open` sind. `partial`, wenn nur einige offen sind. `failed`, wenn Einträge nicht anwendbar sind. Sonst `done`.
  - `working`, `export`, `txt`, `docx`, `report`: neu berechnen und mit der gespeicherten Datei vergleichen. Gleich ergibt `done`, oder `partial` bei Findings oder Gaps. Abweichend ergibt `stale`, fehlend `pending`. `preflight` hat kein Artefakt und taucht deshalb nicht auf.
- **Gesamtstatus**, in dieser Rangfolge: `running` (Lock mit lebendem Prozess) → `failed` → `waiting_for_review` → `interrupted` (Lock eines toten Prozesses) bzw. `open` (ein Schritt `pending`/`stale`) → `partial` (alles aktuell, aber Gaps) → `complete` (abgeschlossen). `not_started` gilt, wenn alle Schritte `pending` sind. Dazu werden der letzte erfolgreiche Schritt und „fortsetzen ab“ angegeben, samt Befehl (`transcript process <s>` bzw. `--redo <schritt>` bei `stale` in `extract`).
- **`transcript status [<session>]`:** Mit Session gibt es eine Zeile pro Schritt und eine Gesamtzeile. Ohne Session gibt es eine Gesamtzeile für jede Sitzung unter `input/`. Exit 0, oder 2 bei einem Fehler.
- **Resume-Guard:** `preflight.run(..., strict_resume=True)` macht aus „segment(s) … are transcribed again“ einen **Fehler**, mit dem Hinweis auf `--redo transcribe`. `process` ruft den Preflight streng auf, außer wenn `--redo` gesetzt ist, denn das ist eine ausdrückliche Neuverarbeitung. `transcript doctor` allein warnt weiter.
- **Lock** `work/<s>/process.lock` (PID, JSON): `process` legt ihn nach dem bestandenen Preflight an und entfernt ihn am Ende. Ein Lock mit lebender PID führt zu Exit 2, damit nicht zwei Läufe gleichzeitig laufen. Ein Lock mit toter PID wird ersetzt, und `status` meldet ihn als `interrupted`.
- **`work/<s>/pipeline.log` (TOOL-77 aufgenommen):** Der Logger `transcript` hängt dort Zeilen mit Zeitstempel an, und zwar bei jedem Befehl mit Session, sobald `work/<s>/` existiert. `process` legt das Verzeichnis nach dem Preflight an. Dazu schreibt `process` Schrittbeginn, Schrittstatus, Halt, Abbruch und Abschlusszeile über einen eigenen Logger, der nur in die Datei schreibt. Die Konsole sieht so keine doppelten Zeilen. Gelesen wird die Datei nur von Menschen, nie von `status`.

## Daten-Check
- Aufnahmen und Transkripte: *handled*. `status` liest nur Dateien, die es schon gibt, und gibt Schrittnamen, Status, Segmentnummern, Zähler und Pfade aus.
- Klarnamen und Wissens-Snapshot: *handled*. `status` nennt keine Personen, Labels oder Glossarbegriffe. Bei `speakers` gibt es nur Anzahlen.
- Logs (`pipeline.log`): *handled*. In die Datei kommt nur der Logger `transcript`. `transcript.text.*` propagiert nicht, und `FailureLog` loggt ohne `exc_info` mit bereinigter Meldung. Ein Test prüft mit einem Fake-Backend, dass weder Transkripttext noch Keywords, Labels oder Runtime-Originalmeldungen in der Datei stehen (TOOL-77-AK).
- Lock und Log liegen unter `work/`, das gitignored ist. Ein Test in `tests/test_gitignore.py` prüft das.
- Fixtures: *handled*. Alles läuft über `tmp_path`, Fake-Backend und synthetische Dateien.

## Contract-Check
- N/A: Export, Schema-Kopie und `stats` bleiben unverändert. `status` liest den Export nur, um ihn zu vergleichen. Narrata braucht keine Änderung und kein IOA-Ticket.

## Resume-Check
- Abbruch: *handled*. Der Zustand steht weiter in den Dateien. Nach einem Abbruch bleibt ein toter Lock zurück, `status` meldet `interrupted`, und der nächste `process`-Lauf ersetzt den Lock.
- Wiederverwendung: *handled*. Fertige Segmente verwendet `transcribe` wie bisher wieder (`transcription.reusable`), und `status` zeigt sie als `done`.
- Gleiches Modell und gleicher Snapshot: *handled*. Der strenge Preflight stoppt `process` bei jeder Abweichung, bis `--redo` gesetzt ist. Einen Snapshot-Wechsel zeigt `status` als `stale` bei `transcribe`.

## Dependency-Check
- N/A: keine neue Abhängigkeit, kein Modell.

## Format-Check
- `process.lock`: neu und flüchtig, ohne Versionsfeld. Ein unlesbarer Lock gilt als tot und wird ersetzt.
- `pipeline.log`: Text, nur zum Anhängen, kein Format mit Version.
- N/A für bestehende Formate: Referenz-, Arbeits-, Bericht- und Exportformat bleiben unverändert, keine `format_version` wird angehoben.

## Chunks
### Chunk 1 — Roadmap: TOOL-77 in TOOL-57
- Dateien: `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md` (generiert)
- Änderung: TOOL-57 von 1,0 auf 1,5 Tage, der Hinweis bekommt „TOOL-77 aufgenommen: `work/<s>/pipeline.log`“. Die TOOL-77-Zeile entfällt, unter „Nicht eingeplant“ steht „TOOL-77 in TOOL-57 aufgenommen“. `python3 docs/transcript-roadmap.py` ausführen und die geänderten Daten per `editJiraIssue` in Jira nachziehen.
- Verify: `scripts/check`; Diff der `.md` zeigt nur TOOL-57/77 und die Summenzeile.
- AC: Roadmap und Jira-Daten stimmen überein.

### Chunk 2 — Status der Vorbereitungs- und ASR-Schritte
- Dateien: `src/transcript/status.py`, `src/transcript/manifest.py` (`audio_metadata_problem`), `src/transcript/preflight.py` (nutzt es), `tests/test_status.py`
- Änderung: Typen `StepState`/`SessionState`, `StepStatus(step, state, detail)` und die Regeln für `extract`, `context`, `snapshot`, `manifest`, `transcribe`.
- Verify: `scripts/check`
- AC: Fehlende, veraltete und inkonsistente Artefakte ergeben `pending`/`stale`, nie `done`. Gemischte Segmente ergeben `partial`/`failed`. Ein anderer Snapshot ergibt `stale`.

### Chunk 3 — Status von Review bis Bericht, Gesamtstatus
- Dateien: `src/transcript/status.py`, `tests/test_status.py`
- Änderung: Regeln für `review`, `speakers`, `working`, `export`, `txt`, `docx`, `report`, dazu Gesamtstatus, letzter erfolgreicher Schritt und `resume_from`.
- Verify: `scripts/check`
- AC: Ein unberührtes Sheet oder eine unberührte Vorlage ergibt `waiting_for_review`. Eine veraltete Arbeitsfassung oder ein veralteter Export ergibt `stale`. Alles aktuell mit Gaps ergibt `partial`, ohne Gaps `complete`.

### Chunk 4 — CLI `transcript status`
- Dateien: `src/transcript/__main__.py`, `tests/test_status_cli.py`, `README.md` (neuer Abschnitt „Status einer Sitzung“)
- Änderung: Unterbefehl mit optionaler Session. Die Ausgabe nennt Schritt, Status, Detail und den Befehl zum Fortsetzen.
- Verify: `scripts/check`; manuell `transcript status` gegen eine lokale Sitzung.
- AC: Gesamtstatus und Status je Schritt sind sichtbar, ohne Session für alle Sitzungen. Die Ausgabe enthält keine Namen und keinen Text.

### Chunk 5 — Lock, `pipeline.log`, strenger Resume-Guard
- Dateien: `src/transcript/session.py` (`pipeline_log`, `process_lock`), `src/transcript/preflight.py` (`strict_resume`), `src/transcript/__main__.py` (`_process`, Log-Handler), `tests/test_process.py`, `tests/test_preflight.py`, `tests/test_gitignore.py`, `README.md` („Eine Sitzung in einem Befehl“, „Lauf“)
- Änderung: wie unter Entscheidungen beschrieben.
- Verify: `scripts/check`; manuell `process` abbrechen (Ctrl-C), dann `status` (zeigt `interrupted`), dann erneut `process` (setzt fort).
- AC: Ein Modell- oder Snapshot-Wechsel stoppt `process` mit Exit 2 und Segmentliste, `--redo transcribe` läuft durch. Ein zweiter gleichzeitiger Lauf wird verweigert. Fehlversuche und Schrittwechsel stehen mit Zeitstempel in `pipeline.log`, ohne Text, Keywords, Labels oder `exc_info`.

## Folge-Tickets
- TOOL-77: aufgenommen. Kommentar „in TOOL-57 umgesetzt“ jetzt, Abschluss als erledigt mit `/close-ticket` von TOOL-57.
- TOOL-61: Die E2E-Doku beschreibt `transcript status`, `pipeline.log` und den strengen Resume-Guard. Übergabe-Kommentar beim Abschluss.
- Maschinenlesbare Statusausgabe (`--json`): [kein Ticket: bisher kein Leser; TOOL-59 liest `report.json`]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Roadmap: TOOL-77 in TOOL-57 | no |
| 2 | Status Vorbereitung und ASR | no |
| 3 | Status Review bis Bericht, Gesamtstatus | no |
| 4 | CLI `transcript status` | no |
| 5 | Lock, `pipeline.log`, Resume-Guard | no |
