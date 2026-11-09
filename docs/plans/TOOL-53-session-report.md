# TOOL-53 — Qualitäts- und Abschlussbericht für eine Session

## Ziel
`transcript report <session>` erzeugt nach Review und Arbeitsfassung einen Bericht: wie viel automatisch durchging, wie viel ins Review musste, was entschieden, offen oder unverständlich ist, wie es um die Sprecherzuordnung steht, welche Segmente fehlen oder fehlgeschlagen sind und mit welchem Backend, Modell, Wissensstand und welchen Schwellenwerten gearbeitet wurde. Heute stehen diese Zahlen verteilt in einem Dutzend Arbeitsdateien und teils nur auf der Konsole. Der Bericht liegt maschinenlesbar als `report.json` vor (TOOL-69 übernimmt ihn als `stats`) und kompakt als `report.md`, beides unter `output/<s>/`. Eine Genauigkeitsprozentzahl gibt es nicht, weil keine Ground Truth gemessen wird.

## Ist-Stand
- Arbeitsfassung `WorkingTranscript` (`src/transcript/working.py:128-138`): Blöcke mit `origin`, `status`, `level`, `start_ms`/`end_ms`, `speaker` (`:84-97`); `findings` (`missing_segment`, `stale_decision`, `orphaned_decision`, `speaker_entry`, `:76-81`); `inputs` mit Snapshot-ID, Datei-Hashes und Segmentversionen (`:109-125`). `compose` baut sie neu (`:250`), `load_working` liest die gespeicherte (`:300`).
- Markierungen pro Block: `markers.block_markers` (`src/transcript/markers.py:55`).
- Review-Kandidaten: `SessionCandidates` mit `rated`, `not_rated`, `audio_ms`, `per_hour` (`src/transcript/candidates.py:96-123`).
- Review-Status: `open`, `confirmed`, `corrected`, `unintelligible`, `kept`, `deferred`; `SETTLED` sind die ersten vier ohne `open` (`src/transcript/decisions.py:32-44`).
- Schwellenwerte und genutzte Hinweise pro Segment: `SegmentAssessment.thresholds`, `.knowledge_snapshot_id` (`src/transcript/uncertainty.py:342-350`), lesbar über `load_assessment` (`:450`).
- Referenz pro Segment: `status` `transcribed`/`failed`, `asr: AsrInfo` (Backend, Modell, Versionen, Settings, Sprache, Snapshot-ID), `diarization`, `error: Failure` (Kategorie, `retryable`) (`src/transcript/reference.py:89-172`); `load_reference` (`:361`).
- Aufnahme: `Manifest.duration_ms`, `Segment.duration_ms` (`src/transcript/manifest.py:40-82`).
- Wissen: `Snapshot.snapshot_id`, `source.contract_version` (Version des Transkriptionskontexts aus IOA-1215) (`src/transcript/knowledge.py:55-75`).
- Aufwand der Sprecherzuordnung: `SpeakerAssignment.effort_minutes` (`src/transcript/speakers.py:79`), `load_assignment`.
- Pfade: `SessionPaths.output_dir` existiert (`src/transcript/session.py:70`), noch ohne Nutzer; `output/` ist gitignored (`.gitignore:29`).
- CLI-Muster `_working` (`src/transcript/__main__.py:900-925`): nur Zähler auf der Konsole, Exit 0/1/2.
- Contract IOA-1214: `stats` ist ein offenes Objekt, das Narrata nicht auswertet („Pipeline report figures (TOOL-53)“, `ios-archiv-backend/resources/contracts/transcript-v1.schema.json:115-118`).
- Datenschutz (`docs/datenschutz.md:31`): Auswertungen pro Person namentlich nur mit Opt-in, sonst aggregiert oder nur mit Label. Der Snapshot trägt kein Opt-in-Feld (`src/transcript/narrata.py:63-71`).

## Entscheidungen
- **Grundlage ist die gespeicherte Arbeitsfassung**, denn aus ihr exportiert TOOL-69. Der Bericht baut sie zusätzlich mit `working.compose` neu. Weicht das Ergebnis von `load_working` ab, bricht er mit „working version outdated; run transcript working“ ab. Damit beschreibt der Bericht immer genau den Stand, der exportiert wird.
- **Neues Modul `src/transcript/report.py`**, reine Ableitung ohne eigene Regeln: Kandidat heißt `level != confident`, offen heißt `origin: open`, Markierungen kommen aus `markers.block_markers`.
- **Kennzahlen** (Zeiten in ms, Zähler als ganze Zahlen):

  | Abschnitt | Inhalt |
  | --- | --- |
  | `recording` | Gesamtdauer; pro Segment Dauer und Zustand `transcribed` / `failed` (mit `category`, `retryable`) / `missing` (keine Referenz) |
  | `passages` | Blöcke gesamt und je `origin`; Dauer der automatisch übernommenen Blöcke; Zahl der Blöcke ohne Zeit |
  | `review` | Kandidaten gesamt und je Stufe; bewertete Audiodauer; Kandidaten pro Stunde (`SessionCandidates.per_hour`); entschiedene Kandidaten je Status (`confirmed` = bestätigte ASR-Passage, `corrected` = manuelle Korrektur, `kept`, `unintelligible`) und offene je `open`/`deferred` |
  | `markers` | Anzahl je Art (`unintelligible`, `unresolved`, `speaker_unclear`, `crosstalk`) |
  | `speakers` | diarisierte Segmente; Labels (Paar Segment/Label, weil Labels nur pro Segment gelten) je `assigned`; Anzahl verschiedener Personen; `effort_minutes` (null = nicht erfasst); Redezeit je Segment/Label |
  | `findings` | Befunde der Arbeitsfassung je Art |
  | `pipeline` | `tool_version`; ASR-Konfigurationen (Backend, Modell, Versionen, Sprache, Settings) mit ihren Segmenten; Diarisierung ebenso; Schwellenwerte mit ihren Segmenten; Wissens-Snapshot-ID und Contract-Version des Transkriptionskontexts |
  | `gaps` / `notes` | benannte Lücken und Hinweise, siehe unten |

  Gleiche Konfigurationen werden zusammengefasst, damit ein abweichendes Segment sofort auffällt.
- **Redezeit nur pro Label, nie pro Person** (`docs/datenschutz.md:31`): Es gibt keine Opt-in-Angabe, also nennt der Bericht weder Namen noch User-IDs, sondern nur, wie viele Labels zugeordnet sind und wie viele verschiedene Personen das sind. Gemessen wird die Summe der Blockdauern nach Mehrheitslabel der Passage. Der Bericht nennt das so und gibt es nicht als exakte Redezeit aus.
- **`gaps` gegen `notes`:** `gaps` sind Stellen, an denen das Transkript unvollständig ist: `failed_segment`, `missing_segment`, `open_passages` und `working_findings`. `notes` stehen für fehlende Daten, die das Transkript selbst nicht schmälern: `no_diarization`, `no_assignment`, `effort_not_recorded`, `untimed_passages`, `segment_without_hints` (bewertet ohne Wissenshinweise) und `snapshot_differs` (ASR-Lauf mit anderem Snapshot als die Arbeitsfassung). Beide sind Listen von Codes mit Segmentnummern, wo das passt.
- **Keine Prozentzahlen.** Der Bericht enthält Zähler und Dauern, eine Quote nur als Kandidaten pro Stunde. Unter `report.md` steht ein fester Satz, dass keine Genauigkeit gemessen wurde.
- **Ablage unter `output/<s>/`:** `report.json` (`format_version: 1`) und `report.md` (Deutsch, kurz, Tabellen). Beide enthalten keinen Transkripttext, keine Namen und keine User-IDs. Sie liegen dort, wo später TXT/DOCX (TOOL-51/52) und der Export (TOOL-69) landen, und lassen sich gemeinsam archivieren. Beide Dateien enthalten keinen Zeitstempel; gleiche Eingaben ergeben byte-gleiche Dateien.
- **`stats` für TOOL-69:** `report.report_json(report)` liefert das Objekt ohne `format_version` und `session`. TOOL-69 bettet es unverändert als `stats` ein. Die Contract-Version des Exports trägt der Export selbst (`contract_version`); der Bericht kennt sie vor TOOL-69 nicht und führt sie nicht.
- **CLI `transcript report <session>`:** schreibt beide Dateien und gibt auf der Konsole nur Zähler und Codes aus. Exit 0 ohne `gaps`, 1 mit `gaps`, 2 bei Fehler (fehlende oder veraltete Arbeitsfassung, ungültige Datei).

## Daten-Check
- handled — `report.json`/`report.md` enthalten nur Zähler, Dauern, Segmentnummern, Sprecher-Labels (`SPEAKER_00`), Modell- und Konfigurationsangaben sowie den Session-Schlüssel. Es gibt keinen Text, keine Namen und keine User-IDs. Ein Test prüft das an einem Fixture mit Teilnehmenden.
- handled — Personenbezogene Auswertung: Redezeit nur pro Label (TOOL-66, `docs/datenschutz.md:31`); Personen nur als Anzahl.
- handled — Ablage unter `output/`, gitignored (`tests/test_gitignore.py`).
- handled — Konsole und Fehlermeldungen nennen nur Session, Segmentnummern, Zähler und Codes.
- handled — Tests nutzen die synthetischen Fixtures aus `tests/test_working.py` und `tests/test_speakers.py` (`beispielgruppe/042`, `wort{n}`).

## Contract-Check
- handled — `stats` ist in IOA-1214 v1 ein offenes Objekt, das Narrata nicht auswertet (`transcript-v1.schema.json:115-118`). Jede JSON-Struktur passt; Narrata muss nichts ändern.
- handled — Die Contract-Version des Exports setzt TOOL-69 am Exportobjekt. Übergabe als Roadmap-Hinweis an TOOL-69.
- N/A IOA-Ticket — keine Narrata-Änderung nötig.

## Resume-Check
- N/A — kein Langlauf und kein Modell. Der Bericht ist eine Ableitung in Sekunden; ein Abbruch hinterlässt dank `write_atomic` keine halbe Datei, ein neuer Lauf überschreibt.

## Dependency-Check
- N/A — keine neue Abhängigkeit; Markdown entsteht als einfacher String.

## Format-Check
- handled — Neues Artefakt `output/<s>/report.json` mit `format_version: 1`. Bestehende Formate (Arbeitsfassung, Kandidaten, Bewertung) bleiben unverändert. Ältere Artefakte gibt es keine.

## Chunks
### Chunk 1 — Bericht ableiten
- Dateien: `src/transcript/report.py` (neu), `tests/test_report.py` (neu)
- Änderung: Dataclasses für die Abschnitte oben; `build(working, manifest, references, found, assessments, snapshot, effort_minutes) -> SessionReport` als reine Funktion; `compose(paths, manifest)` liest alle Dateien, baut die Arbeitsfassung neu und vergleicht sie mit `load_working` (`ReportError` bei Abweichung); `report_json(report)`.
- Verify: `scripts/check`
- AC:
  - Blöcke je `origin`, Kandidaten je Stufe und je Status sowie Markierungen je Art stimmen mit der Arbeitsfassung überein.
  - Ein fehlgeschlagenes Segment erscheint mit `category`/`retryable`, ein Segment ohne Referenz als `missing`; beide auch in `gaps`.
  - Labels zählen pro Segment, je `assigned`; Personen nur als Anzahl; Redezeit pro Segment/Label.
  - `effort_minutes: null` ergibt `effort_not_recorded` in `notes`.
  - Abweichende Schwellenwerte oder ASR-Konfigurationen erscheinen als getrennte Einträge mit ihren Segmenten.
  - Veraltete oder fehlende Arbeitsfassung ergibt `ReportError`.
  - Das JSON enthält keine User-ID, keinen Namen und keinen `asr_text`/`text` des Fixtures.

### Chunk 2 — Dateien und Befehl
- Dateien: `src/transcript/report.py`, `src/transcript/session.py`, `src/transcript/__main__.py`, `tests/test_report.py`, `tests/test_smoke.py`
- Änderung: `SessionPaths.report_json`/`report_markdown` unter `output_dir`; `render_markdown(report)` (Deutsch, Tabellen, Satz zur fehlenden Genauigkeitsmessung, Lücken und Hinweise ausgeschrieben); `write_report` (atomar, beide Dateien); Unterbefehl `report` mit Konsolenzeile aus Zählern und Codes, Exit 0/1/2.
- Verify: `scripts/check`
- AC:
  - Zwei Läufe auf gleichen Eingaben ergeben byte-gleiche Dateien.
  - `report.md` nennt jede Lücke und jeden Hinweis in Worten und enthält keine Prozentangabe.
  - Exit 1 genau dann, wenn `gaps` nicht leer ist; Exit 2 bei veralteter Arbeitsfassung mit Hinweis auf `transcript working`.

### Chunk 3 — Doku
- Dateien: `README.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung: README-Abschnitt „Abschlussbericht“ nach „Markierungen“: Befehl, Ablage, Kennzahlen, `gaps`/`notes`, Redezeit nur pro Label, keine Genauigkeit. Roadmap: TOOL-53 erledigt; Hinweise an TOOL-69 (`report_json` → `stats`, Contract-Version am Export), TOOL-51/52 (Bericht liegt schon in `output/<s>/`), TOOL-59 (`speakers.effort_minutes` aus `report.json`); `.md` neu generieren.
- Verify: `scripts/check`
- AC: README beschreibt Befehl und Kennzahlen vollständig; die Roadmap-`.md` ist aus der `.py` generiert.

## Folge-Tickets
- `report_json` als `stats` in den Export übernehmen, Contract-Version am Export: TOOL-69 (Roadmap-Hinweis).
- TXT/DOCX neben `report.md` in `output/<s>/` ablegen: TOOL-51, TOOL-52 (Roadmap-Hinweis).
- `effort_minutes` und Kandidaten pro Stunde sessionübergreifend auswerten, gelesen aus `report.json`: TOOL-59 (Kommentar am Ticket).
- Veralteter Verweis „Abschlussbericht (TOOL-59)“ in TOOL-68: [kein Ticket: TOOL-68 ist Done; die Zuständigkeit klärt der Kommentar an TOOL-59]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `report.py`: Ableitung, JSON, Aktualitätsprüfung | no |
| 2 | Markdown, Dateien unter `output/`, CLI | no |
| 3 | README, Roadmap | no |
