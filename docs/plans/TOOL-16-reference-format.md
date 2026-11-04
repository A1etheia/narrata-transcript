# TOOL-16 — Internes Format für Referenztranskriptionen

Branch `tool-16-reference-format` steht (`--no-track`, kein Upstream), TOOL-16 ist In Progress. Nach der Freigabe: diesen Plan als `docs/plans/TOOL-16-reference-format.md` committen (`docs(plans): plan reference transcript format (TOOL-16)`), dann die Chunks.

**Abhängigkeiten (`/check-ticket-deps`):** Es gibt keine Blocked-by-Links. TOOL-63 und TOOL-20 sind Done und haben keine Divergenz-Marker; ihre Übergaben stehen als Kommentare am Ticket. Downstream sind TOOL-76 und TOOL-64 To Do, das Format kann also frei gestaltet werden.

## Ziel
Danach liegt das Ergebnis eines Segments als versionierte JSON-Datei unter `work/<session>/asr/` vor, und zwar unabhängig vom Backend. Die unveränderte Backend-Antwort steht getrennt daneben. Ein Loader liest das Ergebnis ohne Backend wieder ein. TOOL-64 schreibt über den Adapter in dieses Format, TOOL-76 ergänzt Sprecher-Labels, TOOL-35 und die folgenden Tickets lesen nur dieses Format. Heute ist `BackendResult` flüchtig (`src/transcript/asr/backend.py:138-148`), es gibt also nichts, was sich speichern, fortsetzen oder auswerten ließe.

## Ist-Stand
- `src/transcript/asr/backend.py:101-148`: `BackendInfo`, `ResultWord`/`ResultSegment`/`BackendResult`. Zeiten sind segmentlokale Sekunden, `confidence` und `speaker` sind optional, außerdem gibt es `signals`, `keywords_used`, `settings` und `raw`. Das ist die Eingabe des Adapters.
- `src/transcript/asr/backend.py:84` `Capabilities.to_dict()`: die Fähigkeiten als JSON.
- `src/transcript/timecode.py:49` `seconds_to_ms`: Sekunden → ganze ms, lehnt negative und nicht-endliche Werte ab.
- `src/transcript/manifest.py:23,40-62`: `MANIFEST_FORMAT_VERSION`, `Segment` (index, file, source.sha256, `duration_ms`, `to_absolute_ms`). Diese Muster werden übernommen: `format_version` an erster Stelle, `_to_json`/`_from_json`, eine eigene Fehlerklasse auf `DataFileError`.
- `src/transcript/jsonfile.py:14-59`: `read_object`, `field`, `write_atomic`. Messages nennen nie Feldwerte.
- `src/transcript/session.py:448-496` `SessionPaths`: Pfade für `asr/` gibt es noch nicht. Das README-Layout (`README.md`, Abschnitt „Sessions“) reserviert `asr/` bereits für „ASR-Zwischenergebnisse“.
- `src/transcript/asr/fake.py`: `FakeBackend` liefert `BackendResult`s für Tests.
- Übergabe aus TOOL-20 (Kommentar am Ticket, `docs/spikes/TOOL-20-diarisierung.md:106-111`): optionales Label pro Wort, Segment-Label aus der Mehrheit, Label-Menge und Diarisierungs-Metadaten getrennt, Overlap optional.

## Entscheidungen
- **Modul `src/transcript/reference.py`, nicht unter `asr/`.** Das Format ist bewusst vom Backend unabhängig, und auch die Diarisierung (TOOL-76) schreibt hinein. Das Modul importiert `transcript.asr` nur für den Adapter.
- **Eine Datei pro Manifest-Segment:** `work/<session>/asr/segment-NN.json` (Normalform) und `segment-NN.raw.json` (Rohform). Grund: Resume pro Segment (TOOL-17), und der Name entspricht `audio/segment-NN.wav`. `SessionPaths` bekommt `asr_dir`, `reference(index)` und `reference_raw(index)`.
- **Begriffe:** Die Datei gehört zu einem *Segment* (einer Aufnahme laut Manifest). Die zeitlichen Einheiten darin heißen *Passagen*, nicht Segmente. Sonst wären „Segment“ im Manifest und „Segment“ von Whisper zweierlei. `datenschutz.md` spricht schon von Passagen-IDs.
- **Zeiten in ganzen Millisekunden, lokal zum Segment-WAV** (`start_ms`/`end_ms`, jeweils `null`, wenn das Backend keine liefert), umgerechnet mit `seconds_to_ms`. Absolute Zeiten werden **nicht gespeichert**. Sie ergeben sich aus `Segment.to_absolute_ms` des Manifests und bleiben so richtig, wenn das Manifest neu gebaut wird. Wie sie ins Format oder in die Ausgabe kommen, entscheidet TOOL-19.
- **Aufbau der Normalform (`format_version: 1`):**
  - `session` {group, ordinal}, `play_session_id`, `segment` {index, file, source_sha256}: Zuordnung und Prüfung beim Laden.
  - `status`: `"transcribed"` oder `"failed"`. Bei `failed` gibt es ein `error` {category, retryable}, also nur den Klassennamen und keine Message, und keine Passagen. So kann TOOL-18 Fehler festhalten, ohne das Format zu ändern.
  - `asr`: backend_id, model, model_version, runtime_version, `capabilities` (`to_dict()`), `settings`, `language`, `language_probability`, `keywords_used`.
  - `processing`: `pipeline_version` (`transcript.__version__`), `processed_at` (ISO 8601 mit Offset), `elapsed_ms`.
  - `diarization`: `null` oder {backend_id, model, model_version, settings, num_speakers | null, labels [..], overlaps [{start_ms, end_ms}]}. TOOL-16 definiert und validiert das Feld, befüllt wird es von TOOL-76.
  - `passages`: [{index, text, start_ms, end_ms, speaker | null, signals {}, words [{text, start_ms, end_ms, confidence | null, speaker | null}]}].
  - `raw_file`: Name der Rohdatei.
- **Sprecher:** Das Wort-Label ist die Wahrheit. `speaker` einer Passage ist das Mehrheits-Label ihrer Wörter, bei Gleichstand oder ganz ohne Wort-Labels `null`. Liefert das Backend nur ein Passagen-Label (`ResultSegment.speaker`), wird dieses übernommen. Eine Hilfsfunktion `majority_speaker(words)` gilt auch für TOOL-76. Labels sind generisch (`SPEAKER_00`), Namen kommen erst mit TOOL-68 und nie in diese Datei.
- **Kein gespeicherter Gesamttext.** `ReferenceTranscript.text` setzt ihn aus den Passagen zusammen. Doppelte Daten könnten auseinanderlaufen.
- **Rohform:** `{"backend_id": …, "raw": <BackendResult.raw unverändert>}`, geschrieben mit `write_atomic`. **Reihenfolge: zuerst roh, dann normal.** Erst die Normalform markiert ein Segment als fertig.
- **Validierung im Loader:** `format_version`, Session-Schlüssel, Segmentindex, Typen, `start ≤ end`, Confidence in [0, 1], Passagen-Index fortlaufend, Speaker-Labels einer Passage ⊆ `diarization.labels`, wenn eine Diarisierung vorliegt. Die Fehlerklasse ist `ReferenceError(DataFileError)`. Messages nennen Datei und Feld, nie Text.
- **Kein JSON-Schema-File, keine neue Abhängigkeit.** Das Ticket erlaubt „klar dokumentierte Python-Datenmodelle“: frozen Dataclasses plus `docs/referenzformat.md`.
- **Keine Prüfung gegen die Segmentdauer im Adapter.** Ob Backend-Zeiten knapp hinter dem WAV-Ende liegen dürfen, gehört zur absoluten Umrechnung (TOOL-19), und `to_absolute_ms` lehnt sie schon ab. Kein Schritt korrigiert Zeiten still.

## Daten-Check
- Folgt TOOL-66: handled. Text steht nur in Dateien unter `work/`, die laut `docs/datenschutz.md:12` lokal bleiben. Neue Logs gibt es keine.
- Fehlermeldungen: handled. `ReferenceError` nennt Datei, Feld und Passagen-Index, nie Text, Keywords oder Labels. Der `failed`-Status speichert nur Klasse und `retryable`, keine Message.
- Fixtures und Tests: handled. Die Sätze sind erfunden (`Drachenhort`, `Beispielfigur`), es gibt die Labels `SPEAKER_00/01`, die `play_session_id` ist erfunden (4711), alles liegt in Temp-Verzeichnissen, nichts unter `tests/fixtures/`.
- Können echte Daten ins Repo gelangen? N/A, weil `work/` laut `.gitignore` in jeder Tiefe ignoriert wird (`tests/test_gitignore.py`).

## Contract-Check
N/A, weil das Format intern ist und weder Contract-JSON (IOA-1214) noch den Endpoint berührt. Die Abbildung auf den Contract macht TOOL-69. Narrata braucht keine Änderung, es gibt kein IOA-Ticket.

## Resume-Check
- Abbruch: handled. Pro Segment gibt es zwei atomare Schreibvorgänge, erst roh, dann normal. Ein Abbruch dazwischen hinterlässt höchstens eine Rohdatei ohne Normalform, und das Segment gilt als nicht fertig.
- Wiederverwendung: handled als Vorleistung. `load_reference` liest fertige Segmente ohne Backend. Wann übersprungen wird, entscheidet TOOL-17.
- Gleiches Modell und gleicher Snapshot: handled als Vorleistung. `asr.backend_id/model/model_version`, `settings` und `keywords_used` stehen in der Datei, und TOOL-17 vergleicht sie. Eine Snapshot-ID gibt es noch nicht, sie kommt mit TOOL-41 (siehe Folge-Tickets).

## Dependency-Check
N/A, weil keine Abhängigkeit dazukommt (nur `dataclasses`, `json`, `datetime`).

## Format-Check
- Version: handled. Das Format ist neu, `REFERENCE_FORMAT_VERSION = 1`, und der Loader lehnt andere Versionen mit dem Hinweis ab, das Segment neu zu transkribieren.
- Vorhandene Artefakte: N/A, weil bisher keine `asr/`-Dateien existieren.

## Chunks
### Chunk 1 — Datenmodell, Pfade, Loader
- Dateien: `src/transcript/reference.py`, `src/transcript/session.py`, `tests/test_reference.py`, `tests/test_session.py`
- Änderung: Dataclasses `ReferenceTranscript`, `AsrInfo`, `Processing`, `Diarization`, `Overlap`, `Passage`, `Word`, `FailureInfo`; `REFERENCE_FORMAT_VERSION`; `to_json`/`from_json`; `load_reference(paths, index)` mit Validierung; `ReferenceError`; `majority_speaker`; Eigenschaft `text`. `SessionPaths.asr_dir`, `reference(index)`, `reference_raw(index)`.
- Verify: `scripts/check`
- AC: Ein Round-Trip mit allen optionalen Feldern gefüllt und mit allen leer ergibt jeweils dasselbe Objekt. Falsche Version, fremde Session, fremder Segmentindex, `start > end`, Confidence 1,5 und ein unbekanntes Label werden jeweils als `ReferenceError` abgelehnt, ohne Text in der Message. `majority_speaker` liefert die Mehrheit, bei Gleichstand oder ohne Labels `None`.

### Chunk 2 — Adapter und Schreiben
- Dateien: `src/transcript/reference.py`, `tests/test_reference.py`
- Änderung: `from_backend_result(result, capabilities, manifest, segment, processed_at, elapsed_ms) -> ReferenceTranscript` rechnet Sekunden in ms um, übernimmt Passagen und Wörter samt Labels, setzt `diarization=None`. `failed_reference(...)` erzeugt den Fehlerfall aus einem `BackendError`. `write_reference(paths, reference, raw)` schreibt roh, dann normal.
- Verify: `scripts/check`
- AC: `FakeBackend`-Ergebnisse mit Wortzeiten und Confidence und solche ohne Zeiten (wie Granite) landen im selben Format und lassen sich unverändert wieder laden. `raw` steht nur in der Rohdatei und nicht in der Normalform. Ein `ResourceError` ergibt `status: failed` mit `retryable: true` und ohne Message. Der Adapter importiert nichts Backend-Spezifisches.

### Chunk 3 — Doku
- Dateien: `docs/referenzformat.md`, `docs/asr-backends.md`, `README.md`
- Änderung: Format auf Deutsch (Felder, Pflicht/optional, Einheiten, Sprecherregel, Status, Datei-Paar, Versionierung, Beispiel mit erfundenem Inhalt). In `asr-backends.md` wird der Satz „kommen mit TOOL-16“ durch einen Link ersetzt. Im README werden die Layout-Zeile `asr/` und der Stand angepasst und ein Link gesetzt.
- Verify: `scripts/check`, das Doku-Beispiel einmal durch `load_reference` geprüft (im Test aus Chunk 2 oder per Hand).
- AC: Alle AKs von TOOL-16 sind belegt.

## Folge-Tickets
- TOOL-64: Der Adapter `reference.from_backend_result` und `write_reference` sind die Ausgabe des Whisper-Backends. Pro Segment wird `elapsed_ms` gemessen. Kommentar ans Ticket beim Abschluss.
- TOOL-76: Füllt `diarization` und die Wort-Labels und leitet `speaker` der Passage mit `majority_speaker` ab. Hinweis: Läuft pyannote pro Aufnahme, sind die Labels über mehrere Segmente nicht automatisch dieselben. Das muss TOOL-76 oder TOOL-68 klären. Kommentar ans Ticket beim Abschluss.
- TOOL-19: Absolute Zeiten werden nicht gespeichert und ergeben sich aus `Segment.to_absolute_ms`. Zeiten knapp hinter dem WAV-Ende müssen dort behandelt werden. Kommentar ans Ticket beim Abschluss.
- TOOL-17/TOOL-18: Die Normalform ist der Fertig-Marker, `asr`-Block und `keywords_used` dienen dem Modellvergleich, `status: failed` mit `error.category`/`retryable` nimmt Fehler auf. Kommentar an beide Tickets beim Abschluss.
- TOOL-41: Sobald der Snapshot eine ID hat, gehört sie in den `asr`-Block (Minor-Bump des Formats). Kommentar ans Ticket beim Abschluss.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Datenmodell, Pfade, Loader | no |
| 2 | Adapter und Schreiben | no |
| 3 | Doku `docs/referenzformat.md`, README, asr-backends | no |
