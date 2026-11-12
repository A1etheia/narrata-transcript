# TOOL-89 — Sitzungen mit mehreren Aufnahmen gegen Transkript-Contract 1.1 exportieren

## Ziel
Danach exportiert `transcript export` eine Sitzung aus mehreren Audiodateien als ein Transkript nach Contract 1.1, mit `source.recordings[]`. Heute bricht der Export mit `ExportError` ab („contract v1 holds one“), und `process` hält deshalb an `export`. Sitzungen mit einer Aufnahme exportieren byte-gleich wie bisher (1.0).

## Ist-Stand
- Export: `_source` (`src/transcript/export.py:273-287`) sammelt die Aufnahmen nach `sha256` und verweigert mehr als eine. `duration_seconds` ist die ganze Sitzung (`manifest.duration_ms`). `contract_version` kommt fest aus `CONTRACT_VERSION` (`export.py:117`). `segment_ref` wird gesetzt, sobald es mehr als ein Segment gibt (`export.py:104`, `:250`). Der Docstring nennt die Verweigerung (`export.py:23-25`).
- Zeitachse: Die Segmente liegen lückenlos hintereinander, Pausen sind unbekannt (`src/transcript/manifest.py:7-9`, `_check_timeline` `:273-287`). `Segment` trägt `source: SourceRecording` (`file`, `sha256`) und `start_ms`/`end_ms` (`manifest.py:41-62`). Eine Aufnahme kann mehrere Segmente haben, mit `overlap_before_ms` (`tests/test_session_time.py:43`, `MANIFEST`/`SECOND` mit derselben `SOURCE`).
- Contract-Kopie: `src/transcript/contract.py:35-41` hat `CONTRACT_VERSION = "1.0"` und `SCHEMA_SOURCE` = ios-archiv `303cd6562` mit SHA `05bf…352f`. `validate` (`contract.py:69-87`) prüft das Schema und die Regeln aus `_rules` (`:104-128`), die Recording-Regeln fehlen dort.
- Narrata (ios-archiv `f5de4aed2`): Das Schema hat seit `e8bfb9702` `source.recordings[]` und `$defs/recording` (SHA `019a…e41d`), danach wurde es nicht mehr geändert. `TranscriptContractValidator::recordingViolations` bringt vier Regeln: `recordings` erst ab 1.1, `recordings[0]` gleich den Top-Level-Feldern und `starts_at` 0, `starts_at` fällt nie (Überlappung erlaubt), jede Passage beginnt in einer Aufnahme (`[starts_at, starts_at + duration_seconds]`, nur wenn alle Spannen nutzbar sind). In `docs/transcript-contract.md` heißt der Abschnitt „Mehrere Aufnahmen“. Die Referenz-Fixture `tests/Fixtures/transcripts/session-v1-multi.json` (1.1, zwei Aufnahmen, 320 Passagen) stammt aus `050134ffb`. Der Import speichert `recordings` nicht, die Gesamtlänge nimmt er aus dem spätesten Ende (`f59b8d871`).
- Tests: `tests/test_contract.py:22` (Fixture `tests/fixtures/contract/session-v1.json`, unverändert gleich der Narrata-Fixture), `:51-54` (Kopie gleich Narratas Schema, schlägt seit dem Pull fehl), `:56-57` (Version = Fixture). `tests/test_export.py:92-94` (erwartetes `source`), `:266-277` (Verweigerung).
- Preflight-Warnung: `src/transcript/preflight.py:241-250` und Test `tests/test_preflight.py:360-366`.
- README: `README.md:53` (Warnung), `:614`, `:621` (Regeln von `contract.validate`), `:640` (Verweigert).

## Entscheidungen
- **Version pro Dokument:** Mit einer Aufnahme bleibt es bei `"1.0"` ohne `recordings`, ab zwei Aufnahmen gilt `"1.1"` mit `recordings`. So bleiben Sitzungen mit einer Aufnahme byte-gleich (AK 2), und die Doku sagt dasselbe: „Ohne `recordings` ist der Abend eine einzige Aufnahme, wie in 1.0.“ In `contract.py` heißt das `CONTRACT_VERSION = "1.1"` (neueste bekannte Version) und `SINGLE_RECORDING_VERSION = "1.0"`. `RECORDINGS_SINCE = "1.1"` gilt für die Regel.
- **Aufnahme = aufeinanderfolgende Segmente mit gleichem (`file`, `sha256`):** `starts_at` ist der Start des ersten Segments, `duration_seconds` reicht vom ersten Start bis zum letzten Ende. Grund: Eine Aufnahme kann mehrere Segmente haben, und zwei Dateien mit gleichem Hash bleiben zwei Aufnahmen. Bei einer Aufnahme ist das genau `manifest.duration_ms`, also unverändert. Top-Level `source` = `recordings[0]`.
- **Recording-Regeln in `contract.validate`:** Die vier Regeln aus Narrata kommen nach `contract.py`, damit `write_export` keine Datei schreibt, die `transcript:validate` ablehnen würde. Wie bisher nennen die Meldungen Pfad und Regel, aber keinen Wert. Was das Schema schon meldet, wird übersprungen, so wie bei Narrata.
- **Preflight-Warnung entfällt:** Mehrere Aufnahmen halten den Lauf nicht mehr auf. Die `ok`-Zeile nennt die Zahl der Aufnahmen schon.
- **Gegenprobe mit `transcript:validate`:** Lokal gibt es kein PHP und kein `vendor/`. Deshalb wird nach den gespiegelten Regeln geprüft, und die Narrata-Fixture `session-v1-multi.json` muss lokal gültig sein. Die echte Gegenprobe macht TOOL-58, wo sie laut Roadmap schon liegt.

## Daten-Check
- Fixture: *handled — `session-v1-multi.json` kommt unverändert aus Narrata. Ein Generator (`build-session-fixture.php`) hat sie erzeugt, ohne reale Personen und ohne reale Rede (`docs/transcript-contract.md`, „Referenz-Fixture“). Sie landet in `tests/fixtures/contract/`, wie `session-v1.json`.*
- Export-Inhalt: *handled — `recordings` bringt nur Dateiname, Länge, Hash und Start, dieselben Felder wie das bisherige `source`. Pfade und Audio enthält es nie, der Dateiname steht schon heute im Export. Die Datei liegt unter `output/`.*
- Fehlermeldungen: *handled — die neuen Verstöße nennen JSON-Pfad und Regel (`/source/recordings/1/starts_at: …`, `/passages/n (<id>): …`), keine Zeitwerte und keinen Dateinamen.*
- Logs: *N/A because Export und Contract loggen nichts (`export.py:30-32`, `contract.py:22-23`).*
- Tests: *handled — synthetische Manifeste aus `tests/test_session_time.py` mit erfundenen Dateinamen und Hashes.*

## Contract-Check
- Version: *handled — ab zwei Aufnahmen 1.1 nach IOA-1287 (Schema `e8bfb9702`), sonst 1.0. Beide sind gültig, weil Narrata jede Minor von Major 1 annimmt.*
- Reader vor Writer: *handled — Narrata hat 1.1 deployt (Auskunft der Nutzerin, 12.11.2026).*
- Schema-Kopie: *handled — die Bytes stammen aus ios-archiv `f5de4aed2`, identisch mit `e8bfb9702`. `SCHEMA_SOURCE` nennt `e8bfb9702`, `SCHEMA_SHA256` wird `019ae2df…e41d`. Der Test gegen Narratas Schema wird wieder grün.*
- Regeln jenseits des Schemas: *handled — die vier Recording-Regeln stehen nach Chunk 1 in `contract.validate`.*
- Narrata-Änderung: *N/A because IOA-1287 ist Done und deployt, der Import (`f59b8d871`) verarbeitet `recordings`.*

## Resume-Check
- *N/A because `export` braucht kein Modell und läuft in Sekunden. Abbrechen und erneut starten schreibt `transcript.json` atomar neu (`write_export`, `export.py:169-180`).*

## Dependency-Check
- *N/A because es kommen kein neues Paket und kein Modell dazu. `jsonschema` ist schon da.*

## Format-Check
- Contract `contract_version`: *handled — ab zwei Aufnahmen auf 1.1 erhöht. Bestehende Exporte stammen alle aus Sitzungen mit einer Aufnahme (mehr wurden verweigert), sie bleiben 1.0 und byte-gleich. TXT und DOCX rendern beide Versionen, weil sie gegen dieselbe Schema-Kopie prüfen. DOCX zeigt die Version an (`docx_render.py:200`).*
- Interne Formate (`manifest.json`, Arbeitsfassung, Bericht): *N/A because sie bleiben unverändert, gelesen wird nur `Segment.source`.*

## Chunks
### Chunk 1 — Contract 1.1 in der Kopie
- Dateien: `src/transcript/contracts/transcript-v1.schema.json`, `src/transcript/contract.py`, neu `tests/fixtures/contract/session-v1-multi.json`, `tests/test_contract.py`
- Änderung: Schema und Fixture aus ios-archiv kopieren, `SCHEMA_SOURCE` und `SCHEMA_SHA256` anpassen, `CONTRACT_VERSION = "1.1"`, `SINGLE_RECORDING_VERSION = "1.0"`, `RECORDINGS_SINCE = "1.1"`. In `validate` kommen die vier Recording-Regeln dazu: Version, erster Eintrag, Reihenfolge, Passage innerhalb. Der Docstring nennt sie.
- Verify: `scripts/check`
- AC: Beide Narrata-Fixtures sind gültig. Je ein Test pro Regel (1.0 mit `recordings`, abweichendes `recordings[0]`, fallendes `starts_at`, Passage außerhalb). Eine Überlappung ist erlaubt. Keine Meldung nennt einen Wert. Die Kopie gleicht Narratas Schema.

### Chunk 2 — Export mehrerer Aufnahmen
- Dateien: `src/transcript/export.py`, `src/transcript/preflight.py`, `tests/test_export.py`, `tests/test_preflight.py`, `README.md`
- Änderung: `_source` fasst aufeinanderfolgende Segmente gleicher Aufnahme zusammen. Bei einer Aufnahme schreibt es das bisherige `source` mit 1.0, bei mehreren `source` = erste Aufnahme plus `recordings` mit 1.1. `build` übernimmt die Version aus `_source`. Docstring ergänzt. Preflight-Warnung und ihr Test entfallen. README: `:53` ohne die Warnung, „JSON-Export“ beschreibt 1.0/1.1 und `recordings`, die neuen Regeln von `contract.validate` und die Liste „Verweigert“ ohne mehrere Aufnahmen.
- Verify: `scripts/check`
- AC: Eine Sitzung mit zwei Aufnahmen exportiert 1.1 mit zwei `recordings` (`starts_at` 0 und Start des zweiten Segments), und `validate` meldet nichts. Eine Aufnahme mit zwei Segmenten bleibt 1.0 ohne `recordings`, mit dem bisherigen erwarteten `source`. Der Verweigerungstest wird zum Positivtest.

## Folge-Tickets
- TOOL-58: Gegenprobe des ersten echten Exports mit `transcript:validate`/`transcript:import` in Narrata, auch für eine Sitzung mit mehreren Aufnahmen, falls der Pilotabend eine hat (laut Roadmap schon dort).

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schema-Kopie, Fixture, Recording-Regeln in `contract.validate` | no |
| 2 | `export._source` mit `recordings[]`, Preflight, README | no |
