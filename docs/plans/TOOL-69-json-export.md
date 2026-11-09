# TOOL-69 — Strukturiertes Transkript als JSON-Contract v1 exportieren

## Ziel
`transcript export <session>` schreibt die geprüfte Arbeitsfassung einer Sitzung als `output/<s>/transcript.json` nach Contract v1 (IOA-1214). Narrata importiert diese Datei über IOA-1218, und TXT/DOCX (TOOL-51/52) rendern aus ihr. Heute endet die Pipeline bei `work/<s>/working/transcript.json` und `report.json`: Beides ist kein Contract-Format, und Narrata liest es nicht. Jede Passage bekommt eine stabile ID, absolute Zeit, ein sessionweites Sprecherlabel, die Person oder `null`, Text, Stufe, Review-Status und Marker. Die Datei wird vor dem Schreiben gegen das Narrata-Schema geprüft und ist bei gleichen Eingaben byte-gleich.

## Ist-Stand
- Arbeitsfassung: `working.load_current` (`src/transcript/working.py:335-347`) liefert die gespeicherte Fassung und verweigert eine veraltete. `Block` (`:84-109`) trägt `segment`, `passage`, segmentlokale `start_ms`/`end_ms`, `level`, `origin`, `status`, `asr_text`, `text` (`None` bei `unintelligible`) und `speaker`. Der Ergebnistext entsteht in `_outcome` (`:242-255`). `inputs.knowledge_snapshot_id` steht in `:130-137`.
- Sitzungszeit: `session_time.passage_span(segment, block)` (`src/transcript/session_time.py:61-63`) gibt `start_ms`/`end_ms` in Sitzungszeit und `clamped` zurück. Ohne Zeiten liefert es `None`. Einzelne Grenzen dürfen fehlen (`reference.check_span`, `src/transcript/reference.py:578-583`).
- Marker: `markers.block_markers` (`src/transcript/markers.py:55-75`) liefert `unintelligible`/`unresolved`/`speaker_unclear` (`unknown`)/`crosstalk` (`multiple`), jeweils mit `at_ms` = Sitzungszeit des Blockanfangs oder `None`.
- Sprecher: `SpeakerRef` (`src/transcript/speakers.py:106-116`) mit `label` (`None` = kein Turn), `assigned` (`open`/`person`/`unknown`/`multiple`) und `user_id` (`int | str`, `narrata.is_narrata_id`). Labels gelten nur pro Segment (`:3-4`). Anzeigenamen kommen aus `Participant.display_name` (`src/transcript/narrata.py:60-69`) im Snapshot (`knowledge.load_snapshot`).
- Bericht: `report.compose` (`src/transcript/report.py:396-417`) liest selbst `load_current`. `report.report_json` (`:420-422`) ist laut TOOL-53 für `stats` gedacht. `report.pipeline` hält ASR-, Diarisierungs- und Schwellenwert-Konfigurationen mit ihren Segmenten (`:127-143`).
- Manifest: `Manifest.key`, `play_session_id: int | str`, `session_date`, `duration_ms`, `segments[].source` (`file`, `sha256`) (`src/transcript/manifest.py:30-82`). Jede Aufnahme in `input/` wird ein Segment.
- Gruppen-ID: Der Transkriptionskontext liefert keine Gruppen-ID (`NarrataSession`, `src/transcript/narrata.py:42-46`). Die Konfiguration bildet Slug auf ID ab: `Config.narrata_groups` (`src/transcript/config.py:149-150`).
- Pfade: `SessionPaths.output_dir` (`src/transcript/session.py:70-72`), daneben `report_json`/`report_markdown` (`:161-169`).
- JSON schreiben: `jsonfile.write_atomic` (`src/transcript/jsonfile.py:135-137`) sortiert keine Keys. `write_bytes_atomic` (`:140-151`) schreibt Bytes unverändert.
- CLI-Muster: `report` (`src/transcript/__main__.py:233-300`).
- Werkzeugversion: `transcript.__version__` (`src/transcript/__init__.py:6`).
- Contract (ios-archiv `41f7393d8`): Schema `ios-archiv-backend/resources/contracts/transcript-v1.schema.json`, Doku `docs/transcript-contract.md`, Fixture `ios-archiv-backend/tests/Fixtures/transcripts/session-v1.json`, Validator `scripts/artisan transcript:validate`. Der Import gleicht `group` + `ordinal` + `play_session_id` exakt mit der Zielsitzung ab (`TranscriptImporter.php:205-211`).
- Testgerüst: `_ReportCase`/`_WorkingCase` (`tests/test_report.py:40-61`, `tests/test_working.py`) bauen synthetische Sitzungen (`beispielgruppe/042`).

## Entscheidungen
- **Grundlage:** `working.load_current` plus `report.compose`. Eine veraltete Arbeitsfassung bricht wie beim Bericht ab. `stats` = `report.report_json(report)`, unverändert (TOOL-53).
- **Sessionweites Label:** `s<NN>-<Diarisierungslabel>`, z. B. `s01-SPEAKER_00`, auch bei nur einem Segment, damit die Form immer gleich ist. Passagen ohne Label (`label: None` oder ohne Diarisierung) bekommen `unlabelled`. Das Präfix schließt eine Kollision mit diarisierten Labels aus.
- **`speakers`:** Jedes vorkommende Label steht dort. Bei `person` steht `{participant_id: user_id, display_name}` mit dem Namen aus dem Snapshot. `open`, `unknown`, `multiple` und `unlabelled` werden zu `null`. Zusammengeführte Labels (TOOL-68) tragen dieselbe `participant_id`. `passages[].participant_id` folgt dem Label. Eine `user_id`, die keine ganze Zahl ist, bricht den Export ab, denn der Contract verlangt `integer`.
- **Passagen-ID:** `p-<Sitzungsstart in ms, 8-stellig>-<Slug des sessionweiten Labels>`, z. B. `p-00734120-s01-speaker-00`. Der Slug folgt der Contract-Regel. Steht dieselbe ID zweimal da (gleicher Start, gleiches Label), bekommt die zweite in Sitzungsreihenfolge `-2`, die dritte `-3` usw. Die ID wird aus Referenzwerten geprägt (Start, Diarisierungslabel), die das Review nie ändert. Ein Re-Export nach weiterem Review behält sie deshalb ohne eigenes ID-Register. Grenzen ändern sich nur durch neue Transkription oder Diarisierung, und dann ist die Passage ohnehin eine andere (`labels_version`). README und Docstring halten das fest.
- **Zeiten:** `start`/`end` = `passage_span(...).start_ms/end_ms / 1000`, also höchstens drei Nachkommastellen. Eine Passage ohne Start oder Ende bricht den Export ab und nennt Segment und Passagennummer. Der Contract verlangt beide Zeiten, und aus Nachbarn wird keine Zeit abgeleitet. `clamped` und die Granularität kommen nicht in den Contract, denn eine geklemmte Zeit ist eine gültige Sitzungszeit (Antwort an TOOL-19). Die Passagen werden stabil nach `(start, segment, passage)` sortiert.
- **Text:** `text` = `block.text`, bei `unintelligible` `""`. Der Marker sagt dann, dass dort nichts steht. `asr_text` = `block.asr_text`, wenn es von `text` abweicht, sonst `null`. Das ASR-Ergebnis bleibt so immer sichtbar.
- **Stufe und Status:** `confidence_tier` = `block.level`, 1:1. Für `review_status`:

  | Block | `review_status` |
  | --- | --- |
  | `origin: automatic` | `unreviewed` |
  | `confirmed`, `kept` | `confirmed` |
  | `corrected`, `unintelligible` | `corrected` |
  | `origin: open` (`open`, `deferred`) | `open` |

- **Marker:** aus `markers.block_markers`, keine eigene Regel. `unintelligible`/`speaker_unclear`/`crosstalk` werden direkt übernommen (`multiple` erscheint also als `crosstalk`). `unresolved` ist kein Marker, sondern `review_status: open`. `at` = `at_ms / 1000`. Ein Marker ohne Zeit kann nicht vorkommen, weil eine Passage ohne Start schon vorher abbricht. Kein `note`. `gap` erzeugt v1 nicht, weil `markers.py` es nicht kennt.
- **Übrige Passagenfelder:** `review_note: null`, `knowledge_hints: []`, `layers: {}`. `segment_ref` = `segment-NN` bei mehr als einem Segment, sonst `null`.
- **Kopf:** `contract_version: "1.0"` und `tool_version` = `__version__`. `session`: `group` = `narrata.groups[<slug>]`; fehlt der Eintrag, bricht der Export mit einem Hinweis auf `narrata.groups` ab. `ordinal` = Schlüssel, `play_session_id` (Integer, sonst Abbruch), `session_date` aus dem Manifest. `source`: genau eine Aufnahme (gleicher `sha256` in allen Segmenten), dazu `file_name`, `audio_sha256` und `duration_seconds` = `manifest.duration_ms / 1000`. Bei mehreren Aufnahmen bricht der Export mit Verweis auf IOA-1287 ab. `pipeline`: `backend`/`model` aus `report.pipeline.asr`, mehrere verschiedene Werte mit `+` verbunden in Segmentreihenfolge. `config_hash` = die ersten 16 Hex-Zeichen des SHA-256 über das kanonische JSON von `report.pipeline.asr`/`diarization`/`thresholds`, also über das, womit transkribiert wurde, nicht über die aktuelle Konfigurationsdatei. `knowledge_snapshot_id` aus `inputs`, `thresholds` = `{"uncertainty": [{values, segments}, …]}`.
- **Schema und Validierung:** Das Schema kommt als Kopie nach `src/transcript/contracts/transcript-v1.schema.json` (Package-Data), Herkunft (ios-archiv-Commit) und Version stehen in `contract.py`. `contract.validate(document)` prüft mit `jsonschema` (Draft 2020-12) und zusätzlich die Regeln jenseits des Schemas aus `transcript-contract.md`: Major bekannt, IDs eindeutig, `start` fällt nie, `end >= start`, Label in `speakers`. Die Meldungen nennen JSON-Pfad, Regel und Passagen-ID, nie einen Wert, denn `jsonschema`-Meldungen enthalten Werte und damit Text. Gibt es Verstöße, wird nichts geschrieben.
- **Determinismus:** `json.dumps(sort_keys=True, indent=2, ensure_ascii=False) + "\n"` über `write_bytes_atomic`. Ohne Zeitstempel ergeben gleiche Eingaben byte-gleiche Dateien.
- **CLI `transcript export <session>`:** schreibt `output/<s>/transcript.json` (neue Property `SessionPaths.transcript_export`) und gibt Pfad, Zahl der Passagen und offenen Passagen sowie die `gaps`-Codes aus. Exit 0, wenn geschrieben (offene Passagen sind im Contract gültig), 2 bei Fehler oder Verweigerung.
- **TXT/DOCX lesen diese Datei** (AK). Die Roadmap-Hinweise zu TOOL-51/52 (`working.load_current`, `markers.rendered_text`) werden beim Abschluss angepasst. Einen Reader liefern TOOL-51/52 selbst.
- **AK TOOL-58:** Hier wird ein synthetischer Export mit `transcript:validate` und `transcript:import` in der lokalen Narrata-Instanz geprüft. Der Import einer echten Sitzung bleibt AK von TOOL-58.

## Daten-Check
- handled — Die Exportdatei enthält Transkripttext, Anzeigenamen und User-IDs und liegt deshalb nur unter `output/` (gitignored, `tests/test_gitignore.py`). Nach Narrata geht sie nur über den Import, den eine Person anstößt (IOA-1218).
- handled — `source` enthält nur Dateiname (ohne Pfad) und Hash, keine Pfade, keine Secrets, kein Rohaudio (Schema-Muster `^[^/\\]+$`).
- handled — `export.py` und `contract.py` loggen nichts. Fehlermeldungen nennen Datei, Segment, Passagennummer, Passagen-ID, JSON-Pfad und Regel, nie Text, Namen oder IDs. Ein Test erzwingt das mit einem Schemaverstoß in einem Textfeld.
- handled — Tests nutzen die synthetischen Fixtures (`beispielgruppe/042`, `wort{n}`, `PARTICIPANTS`). Die Narrata-Fixture `session-v1.json` ist erfunden (`transcript-contract.md:172-178`) und kommt als Testdatei nach `tests/fixtures/contract/`.
- handled — Die Konsole zeigt nur Pfad, Zähler und Codes.

## Contract-Check
- handled — Writer gegen IOA-1214 v1, `contract_version: "1.0"`. Das Schema ist eine Kopie mit Herkunftsangabe. Ein Test vergleicht sie mit `../ios-archiv/…/transcript-v1.schema.json`, wenn das Nachbar-Repo da ist (sonst `skipTest`).
- handled — Die Narrata-Fixture besteht `contract.validate`. Damit ist gezeigt, dass unser Validator nicht strenger ist als Narratas.
- handled — Manuelle Gegenprobe mit `scripts/artisan transcript:validate` und `transcript:import` in der lokalen Instanz (Chunk 3).
- handled — Mehrere Aufnahmen pro Sitzung passen nicht in `source` v1: Der Export verweigert sie. Der Minor-Bump `source.recordings[]` liegt in IOA-1287.
- N/A weitere Narrata-Änderung — `knowledge_hints: []`, `review_note: null` und `layers: {}` sind gültige v1-Werte.

## Dependency-Check
- handled — `jsonschema` (>=4.18,<5, MIT) als Laufzeitabhängigkeit in `pyproject.toml`. Es zieht `attrs`, `jsonschema-specifications`, `referencing` und `rpds-py` nach (alle MIT, Wheels für Linux x86_64). Es läuft rein lokal ohne Netz, `$ref` sind intern. Es wird jetzt gebraucht, weil das Ticket Validierung vor dem Schreiben gegen genau die Narrata-Schemadatei verlangt. Keine Hardware-Anforderung.

## Resume-Check
- N/A — kein Langlauf und kein Modell. Der Export ist eine Ableitung in Sekunden. `write_bytes_atomic` hinterlässt keine halbe Datei, ein neuer Lauf überschreibt.

## Format-Check
- handled — Neue Ausgabedatei mit `contract_version` (Narrata-Versionierung, nicht unsere). Interne Formate (`working`, `report`, `manifest`) bleiben unverändert, also gibt es keinen Bump und keine Folgen für bestehende Artefakte.

## Chunks
### Chunk 1 — Contract-Schema und Validator
- Dateien: `src/transcript/contracts/transcript-v1.schema.json` (Kopie), `src/transcript/contract.py`, `pyproject.toml` (`jsonschema`, Package-Data), `tests/fixtures/contract/session-v1.json` (Kopie der Narrata-Fixture), `tests/test_contract.py`.
- Änderung: `CONTRACT_VERSION = "1.0"`, `SCHEMA_SOURCE` (ios-archiv-Commit), `load_schema()`, `validate(document) -> tuple[str, ...]` mit Schema und den fünf Regeln jenseits des Schemas. Die Meldungen tragen Pfad, Regel und ID, nie Werte.
- Verify: `.venv/bin/pip install -e '.[dev]'`, dann `scripts/check`
- AK: Die Narrata-Fixture ist gültig. Doppelte ID, Passage außer Reihe, `end < start`, unbekanntes Label, unbekannte Major und ein Schemaverstoß werden je mit ID bzw. Pfad gemeldet. Keine Meldung enthält den Wert. Die Schema-Kopie ist gleich dem Original, falls das Nachbar-Repo vorhanden ist.

### Chunk 2 — Export ableiten
- Dateien: `src/transcript/export.py`, `tests/test_export.py`.
- Änderung: `ExportError(DataFileError)`. `build(stored, manifest, report, participants, group_id) -> dict` nach den Entscheidungen oben (Labels, `speakers`, IDs mit Kollisionssuffix, Zeiten, Text, Status, Marker, Kopf, `config_hash`). Abbrüche bei Passage ohne Zeit, mehreren Aufnahmen, nicht ganzzahliger `user_id`/`play_session_id` und leerer Arbeitsfassung.
- Verify: `scripts/check`
- AK: Jede Passage trägt absolute Zeit, Label, Person oder `null`, Text, Stufe und Status. `unintelligible` hat `text: ""`, den ASR-Text in `asr_text` und einen Marker. Offene Passagen haben `review_status: open` und keinen `unresolved`-Marker. `multiple` ergibt `crosstalk` und `null`, nicht zugeordnete Labels ergeben `null`. Passagen ohne Label stehen unter `unlabelled`. Das Ergebnis besteht `contract.validate`. Nach einer geänderten Entscheidung bleiben die IDs gleich.

### Chunk 3 — Schreiben, CLI, README
- Dateien: `src/transcript/export.py` (`compose`, `write_export`), `src/transcript/session.py` (`transcript_export`), `src/transcript/__main__.py` (`export`), `README.md` (Abschnitt „JSON-Export“, Verzeichnisstruktur), `tests/test_export.py`.
- Änderung: `compose(paths, manifest, config)` liest `report.compose` und `working.load_current`, Snapshot-Teilnehmende und `narrata.groups`. `write_export` validiert, verweigert bei Verstößen und schreibt deterministisch und atomar. Dazu der CLI-Befehl mit Exit 0/2.
- Verify: `scripts/check`. Danach manuell: einen synthetischen Export aus dem Testgerüst ins Scratchpad schreiben (einmaliger Lauf, nicht committet), `group`/`ordinal`/`play_session_id` auf eine lokale Spielsitzung setzen, dann in ios-archiv `scripts/artisan transcript:validate <datei>` (Exit 0) und `scripts/artisan transcript:import` gegen die lokale Instanz.
- AK: Zwei Exporte derselben Eingaben sind byte-gleich. Eine veraltete Arbeitsfassung, ein fehlender `narrata.groups`-Eintrag und ein Validierungsverstoß schreiben nichts und enden mit Exit 2. Die Datei liegt unter `output/<s>/transcript.json`, und der README beschreibt Felder, ID-Regel und Grenzen (eine Aufnahme, keine Hinweise und Notizen in v1).

## Folge-Tickets
- Contract 1.1 mit `source.recordings[]` für Sitzungen mit mehreren Aufnahmen: IOA-1287. Den Pipeline-Teil legt IOA-1287 als TOOL-Ticket an, sobald das Schema steht.
- Roadmap-Hinweise TOOL-51/52 auf „rendern aus `output/<s>/transcript.json`“ umstellen: [kein Ticket: Übergabekommentar an TOOL-51/TOOL-52 und Roadmap-Update beim Abschluss]
- AK „Import der Testsession ohne Korrektur“ nach TOOL-58 übertragen: [kein Ticket: Kommentar an TOOL-58 und TOOL-69 beim Abschluss]
- Antwort an TOOL-19 (Granularität und `clamped` nicht im Contract): [kein Ticket: Kommentar an TOOL-69/TOOL-19 beim Abschluss]
- `review_note` aus den Review-Entscheidungen füllen: [kein Ticket: die Notizen sind persönliche Prüfvermerke, ob sie nach Narrata sollen, entscheidet der Pilot TOOL-60]
- `knowledge_hints` füllen: [kein Ticket: es gibt keine Datenquelle; Review-Hinweise sind Vermutungen und haben den Text nicht beeinflusst, das Keyword-Biasing wirkt pro Segment, nicht pro Passage]
- Marker `gap` erzeugen: [kein Ticket: `markers.py` (TOOL-50) kennt keine Lücke im Text; bei Bedarf dort ergänzen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Contract-Schema, `jsonschema`, `contract.validate` | no |
| 2 | `export.build`: Abbildung Arbeitsfassung → Contract v1 | no |
| 3 | Schreiben, CLI `export`, README, manuelle Narrata-Gegenprobe | no |
