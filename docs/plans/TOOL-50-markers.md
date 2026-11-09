# TOOL-50 — Ungeklärte und unverständliche Stellen einheitlich markieren

## Ziel
Ein zentrales Modul leitet aus jedem Block der Arbeitsfassung (TOOL-49) die Markierungen für ungeklärte Stellen ab, maschinenlesbar und als Text wie `[unverständlich 01:42:17]`. TXT (TOOL-51), DOCX (TOOL-52) und der JSON-Export (TOOL-69) nutzen dieselbe Funktion statt eigener Regeln. Heute trägt die Arbeitsfassung nur `text: null` und `origin: open`; wie das erscheint, ist nirgends festgelegt.

## Ist-Stand
- `Block` (`src/transcript/working.py:84-97`): `origin` (`automatic`/`decided`/`open`), `status`, `asr_text`, `text` (`None` bei `unintelligible`, `:239`), `start_ms`/`end_ms` segmentlokal, `speaker: SpeakerRef`.
- `SpeakerRef.assigned` ist `open|person|unknown|multiple`, `label` kann `None` sein (`src/transcript/speakers.py:39-45,107-113`).
- Sitzungszeit: `session_time.passage_span(segment, passage)` (`src/transcript/session_time.py:51`) mit Klemmung am Segmentende (`:93-99`); erwartet heute eine `Passage`, nutzt aber nur `start_ms`/`end_ms` (`:76-103`).
- `timecode.format_ms` liefert `HH:MM:SS.mmm` (`src/transcript/timecode.py:16`); eine Form ohne Millisekunden fehlt.
- Contract IOA-1214 (`ios-archiv-backend/resources/contracts/transcript-v1.schema.json:235-252`): `marker.type` ∈ `unintelligible|speaker_unclear|crosstalk|gap`, `at` in Sekunden (Pflicht); offene Passagen über `review_status` (`unreviewed|confirmed|corrected|open`, `:206-208`).

## Entscheidungen
- **Vier Markierungsarten**, abgeleitet beim Lesen, nicht gespeichert:

  | `kind` | Wann | Text |
  | --- | --- | --- |
  | `unintelligible` | `origin: decided`, `status: unintelligible` | `[unverständlich 01:42:17]`, ohne Wortlaut |
  | `unresolved` | `origin: open` | erkannter Text, dahinter `[unklar 01:42:17]` |
  | `speaker_unclear` | `speaker.assigned: unknown` | `[Sprecher unklar 01:42:17]` |
  | `crosstalk` | `speaker.assigned: multiple` | `[durcheinander 01:42:17]` |

  So ist „endgültig unverständlich“ klar von „noch offen“ getrennt. Der offene Text bleibt lesbar, die Markierung sagt, dass er ungeprüft ist. `unintelligible`, `speaker_unclear` und `crosstalk` heißen wie im Contract, damit TOOL-69 sie direkt übernimmt. Beide Punkte (offene Stelle mit Text, eigene Markierung für Durcheinanderreden) sind mit der fachlichen Entscheiderin abgestimmt.
- **Nicht markiert:** Sprecher `open` (fehlende Zuordnung, zählt die Konsole von `transcript working`) und `label: null` (kein Diarisierungs-Turn). Sonst wäre ohne `assignment.json` jeder Block markiert.
- **Zeit:** Sitzungszeit des Blockanfangs über `passage_span`, als `HH:MM:SS` abgerundet (neu `timecode.format_clock`), damit man an oder vor der Stelle landet. Ohne Startzeit entfällt die Zeit: `[unverständlich]`. Das Ende wird nicht ersatzweise genommen.
- **Reihenfolge:** erst die Inhaltsmarkierung (`unintelligible`/`unresolved`), dann die Sprechermarkierung, durch Leerzeichen getrennt.
- **API (`src/transcript/markers.py`):**
  - `Marker(kind, at_ms: int | None)` — maschinenlesbar, Sitzungszeit in ms.
  - `block_markers(block, manifest) -> tuple[Marker, ...]`; das Segment sucht die Funktion selbst, damit nicht jeder Exporter es nachschlägt.
  - `marker_label(marker) -> str` — die Textform.
  - `rendered_text(block, manifest) -> str` — der Blocktext für TXT/DOCX: bei `unintelligible` nur Markierungen, sonst `text` plus Markierungen. Kein Ersatzwortlaut.
- **`passage_span` nimmt alles mit `start_ms`/`end_ms`** (Protocol `Timed`), damit Blöcke dieselbe Umrechnung und Klemmung nutzen statt einer Kopie.

## Daten-Check
- handled — `rendered_text` enthält erkannten Text; das Modul loggt nichts und schreibt keine Datei. Ausgaben entstehen erst in TOOL-51/52 unter `output/`.
- handled — Fehlermeldungen (Segment fehlt im Manifest) nennen nur die Segmentnummer.
- handled — Tests nutzen die synthetischen Fixtures aus `tests/test_working.py` (`wort{n}`, `beispielgruppe/042`).
- N/A Klarnamen — Markierungen tragen weder Labels noch Personen.

## Contract-Check
- handled — Arten `unintelligible`, `speaker_unclear`, `crosstalk` entsprechen dem Enum aus IOA-1214 v1; `at` bildet TOOL-69 aus `at_ms / 1000`. `unresolved` ist kein Contract-Marker, sondern `review_status: open`. Ein Marker ohne Zeit hat im Contract kein `at`; wie TOOL-69 damit umgeht, steht als Hinweis in der Roadmap.
- N/A Narrata-Änderung — keine; das Enum deckt alle Contract-Arten ab, `gap` kommt aus TOOL-35 über TOOL-69.

## Resume-Check
- N/A — reine Ableitung im Speicher, kein Langlauf, kein Modell.

## Dependency-Check
- N/A — keine neue Abhängigkeit.

## Format-Check
- N/A — `working/transcript.json` bleibt `format_version: 1`; Markierungen werden nicht gespeichert, sondern beim Lesen abgeleitet. Kein bestehendes Artefakt ändert sich.

## Chunks
### Chunk 1 — Markierungen ableiten
- Dateien: `src/transcript/markers.py` (neu), `src/transcript/timecode.py`, `src/transcript/session_time.py`, `tests/test_markers.py` (neu), `tests/test_timecode.py`, `tests/test_session_time.py`
- Änderung: `format_clock`; Protocol `Timed` für `passage_span`; `Marker`, `block_markers`, `marker_label`, `rendered_text` nach den Regeln oben.
- Verify: `scripts/check`
- AC:
  - `unintelligible` ergibt nur `[unverständlich HH:MM:SS]`, nie `asr_text`.
  - Ein offener Block zeigt seinen Text plus `[unklar …]` und ist von `unintelligible` unterscheidbar.
  - `unknown` → `speaker_unclear`, `multiple` → `crosstalk`, `open`/`label: null` → keine Sprechermarkierung.
  - Zeit = Segmentstart + Blockstart, abgerundet; geklemmt am Segmentende; ohne Startzeit keine Zeit.
  - `automatic` und `decided` ohne Sprecherproblem: Text unverändert, keine Markierung.
  - Ein Test prüft, dass jede `kind` außer `unresolved` im Contract-Enum steht.

### Chunk 2 — Doku
- Dateien: `README.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung: README-Abschnitt „Markierungen“ nach „Arbeitsfassung“ (Tabelle, Zeitregel, nicht markierte Fälle, Contract-Bezug); Roadmap: TOOL-50 erledigt, Hinweise für TOOL-51/52 (`markers.rendered_text`) und TOOL-69 (Kind-Mapping, `unresolved` → `review_status`, Marker ohne Zeit); `.md` neu generieren.
- Verify: `scripts/check`
- AC: README dokumentiert die Konvention vollständig; Roadmap-`.md` aus der `.py` generiert.

## Folge-Tickets
- TXT- und DOCX-Rendering nutzen `markers.rendered_text`: TOOL-51, TOOL-52 (Roadmap-Hinweis).
- Markierungen in Contract-`markers`/`review_status` abbilden, Marker ohne Zeit behandeln: TOOL-69 (Roadmap-Hinweis).

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `markers.py`, Zeitform, `passage_span` | no |
| 2 | README, Roadmap | no |
