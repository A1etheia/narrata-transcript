# TOOL-17 — Komplette Session segmentweise transkribieren

## Ziel
Danach transkribiert `transcript transcribe <session>` alle Segmente des Manifests in einem Lauf. Whisper lädt dabei einmal, fertige Segmente werden wiederverwendet, solange Modell, Revision und Settings passen, und am Ende wird diarisiert. Der Lauf zeigt pro Segment `transcribed`, `reused`, `failed` oder `open`. Heute ist `--segment` Pflicht, und jeder Aufruf lädt das Modell neu. Eine 5-Stunden-Session braucht deshalb viele Handaufrufe mit je mehreren Minuten Ladezeit.

## Ist-Stand
- `src/transcript/transcription.py:55-118` `transcribe_segment` öffnet das Backend selbst per `opened` (`:92`). Es prüft Index, WAV und vorhandenes Ergebnis vor dem Laden (`:71-87`) und schreibt `failed` nur, wo kein `transcribed` liegt (`:96-102`).
- `src/transcript/asr/backend.py:207-231` `Backend`-Protokoll (`info`, `capabilities`, `load`, `transcribe`, `close`), `opened`. `:112-123` `hub_revision`, `resolve_device`; `:126` `cached_model_dir`.
- `src/transcript/asr/whisper.py:86-124` `load()` ermittelt Gerät, Modellpfad, Revision und `settings` erst beim Laden; vorher steht in `info` nur der Modellname (`:73`).
- `src/transcript/asr/fake.py:22-66` `FakeBackend` zählt `load`/`close`.
- `src/transcript/diarization/__init__.py:94-111` `DiarizationRun.matches` lässt `runtime_version` außen vor. `:154-218` `diarize_session` überspringt Segmente ohne oder mit fehlgeschlagener Transkription und lädt das Modell erst, wenn ein Segment es braucht. `diarization/pyannote.py:61` `identity()` vor dem Laden.
- `src/transcript/__main__.py:59-73` Subcommand `transcribe` mit `--segment` (Pflicht) und `--force`. `:193-227` `_transcribe`, `:230-265` `_diarize` mit Zeilen pro Segment.
- `src/transcript/reference.py:87-98` `AsrInfo` mit `backend_id`, `model`, `model_version`, `settings`, `language`.

## Entscheidungen
- **`Backend.identity() -> BackendIdentity(info, settings)`** in `asr/backend.py`. Es liefert Modell, Revision und Settings, ohne das Modell zu laden, wie `Diarizer.identity()`. Whisper prüft dafür den Import, löst Gerät, Modellpfad (`cached_model_dir`, `hub_revision`) und `compute_type` auf und baut daraus dasselbe `settings`-Dict wie heute `load()`, das darauf zurückgreift. `FakeBackend` bekommt `identity()` ebenfalls. Grund: Ein vollständig fertiger Lauf wiederholt sich in Sekunden, und fehlende Runtime, fehlendes Modell oder fehlende GPU fallen vor jeder Arbeit auf.
- **Wiederverwendung:** Ein gespeichertes `transcribed` bleibt stehen, wenn `backend_id`, `model`, `model_version` und `settings` der Identität entsprechen und `config.language` leer ist oder zu `asr.language` passt. `runtime_version` zählt nicht mit, wie bei `DiarizationRun.matches`. `--force` rechnet alle gewählten Segmente neu. Passt ein Segment nicht, wird es neu transkribiert. Seine Labels fallen dabei weg, und `diarize_session` setzt sie aus der Rohform wieder, ohne das Modell zu laden.
- **`transcribe_session(paths, manifest, backend, language, keywords=(), force=False, indices=None, progress=None) -> list[SegmentOutcome]`** in `transcription.py`. Vor dem Laden prüft es die Identität, ob jeder gewählte Index im Manifest steht und ob jedes WAV existiert; sonst bricht es mit `TranscriptionError` ab. Danach umschließt ein `opened(backend)` alle offenen Segmente in Manifest-Reihenfolge. `transcribe_segment` verliert das eigene `opened` und wird zum Körper pro Segment; seine Regeln für `failed` bleiben. `SegmentOutcome.status` ist `transcribed`, `reused`, `failed` oder `open`, mit Zählern und Fehlerklasse, ohne Text. Ein `BackendError` an einem Segment wird `failed`, und der Lauf geht weiter. Ein Fehler beim Laden lässt alle offenen Segmente `open`. `progress` wird nach jedem Segment aufgerufen. Kein Code für einzelne Backends.
- **Session-Status:** Er ergibt sich aus den Referenzdateien und steht am Ende des Laufs: Zähler je Status, dazu einmal Backend, Modell und Revision. Eine eigene Statusdatei gibt es nicht, sie könnte veralten.
- **CLI `transcript transcribe <session> [--segment N] [--force] [--no-diarize] [--num-speakers N] [--config]`:**
  - Ausgabe: eine Zeile pro Segment, sobald es fertig ist, danach eine Zusammenfassung.
  - Diarisierung: Ohne `--no-diarize` prüft die CLI vor dem ASR `PyannoteDiarizer.identity()` und ruft nach dem Schließen von Whisper `diarize_session` auf (Übergabe aus TOOL-76). Die Ausgabe teilt sie sich mit `_diarize`.
  - Exit-Codes: 0, wenn alle Segmente `transcribed` oder `reused` sind; 1 bei `failed` oder `open`; 2 bei Fehlern vor dem Lauf.
  - `--segment N` beschränkt den Lauf auf ein Segment. Ein passendes Ergebnis wird wiederverwendet; der Abbruch „already transcribed“ aus TOOL-15 entfällt. Das ist eine Verhaltensänderung und kommt ins README.

## Daten-Check
- Rohaudio: handled, wird nur gelesen. Ein Test prüft die WAV-Hashes vor und nach dem Lauf; alles läuft lokal.
- Arbeitsdateien: handled. Referenzen, Rohformen und Diarisierung liegen unter `work/` (gitignored).
- Konsole und Fortschritt: handled. Nur Zähler, Zeiten, Modell, Revision und Fehlerklasse; ein Test prüft, dass `SECRET` nicht in stdout/stderr steht.
- Fehlermeldungen: handled. Sie nennen Segment, Datei und Fehlerklasse, nie Text oder Keywords.
- Fixtures: handled. Tests nutzen `FakeBackend`, einen Fake-Diarizer und erfundene Daten.

## Contract-Check
N/A. Nur interne Arbeitsdateien; Export und Narrata-Endpoint sind nicht berührt.

## Resume-Check
- Abbruch: handled. Jedes fertige Segment ist schon atomar geschrieben (Rohform zuerst). Ein abgebrochener Lauf verwendet sie beim nächsten Mal wieder, offene Segmente laufen neu.
- Wiederverwendung: handled. Die Regel oben gilt, geprüft über `identity()` vor dem Laden; die Diarisierung verwendet ihre Rohform weiter wie bisher.
- Gleiches Modell und gleicher Snapshot: handled für Modell, Revision und Settings. Einen Wissens-Snapshot mit ID gibt es noch nicht (TOOL-41), und `keywords_used` bleibt leer.

## Dependency-Check
- Neue Abhängigkeit: N/A, kein neues Paket und kein neues Modell.
- Lokal, Lizenz, Hardware: N/A, unverändert gegenüber TOOL-64 und TOOL-76. Whisper und pyannote laufen nacheinander, nie gleichzeitig im Speicher.

## Format-Check
- Referenzformat: handled. Es bleibt bei `format_version: 1` ohne Feldänderung.
- Diarisierungs-Rohform: N/A, unverändert.
- `Backend`-Protokoll: N/A, es ist kein gespeichertes Format.

## Chunks
### Chunk 1 — Backend-Identität vor dem Laden
- Dateien: `src/transcript/asr/backend.py`, `src/transcript/asr/whisper.py`, `src/transcript/asr/fake.py`, `src/transcript/asr/__init__.py`, Tests in `tests/test_asr_*.py`
- Änderung: `BackendIdentity` und `identity()` im Protokoll; Whisper berechnet sie ohne `WhisperModel`, `load()` nutzt sie; `FakeBackend.identity()`.
- Verify: `scripts/check`
- AC: Die Whisper-Identität entspricht `info` und `settings` nach `load()` und baut kein `WhisperModel`; fehlende Runtime oder fehlendes Modell kommen als `BackendUnavailableError` aus `identity()`.

### Chunk 2 — `transcribe_session` mit Resume
- Dateien: `src/transcript/transcription.py`, `tests/test_transcription.py`
- Änderung: `transcribe_session`, `SegmentOutcome`, Wiederverwendungsregel; `transcribe_segment` ohne eigenes `opened`.
- Verify: `scripts/check`
- AC: Tests mit `FakeBackend` prüfen:
  - Bei mehreren Segmenten ist `load_calls == 1`, und die Reihenfolge folgt dem Manifest.
  - Ein passendes Ergebnis wird ohne `load` wiederverwendet; abweichende Revision oder Settings und `force` rechnen neu.
  - Ein Fehler in Segment 2 lässt Segment 3 trotzdem transkribieren; ein Fehler beim Laden lässt alle Segmente `open`.
  - Unbekannter Index oder fehlendes WAV brechen vor `load` ab; `close` läuft immer.

### Chunk 3 — CLI mit Diarisierung
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `tests/test_whisper_smoke.py`
- Änderung: `--segment` optional, `--no-diarize`, `--num-speakers`, Ausgabe pro Segment und Zusammenfassung, Exit-Codes, gemeinsame Diarisierungsausgabe.
- Verify: `scripts/check`; `TRANSCRIPT_WHISPER_SMOKE=1 python -m unittest discover -s tests -p test_whisper_smoke.py`
- AC: Tests mit gepatchtem `from_config` prüfen:
  - Ganzer Lauf, zweiter Lauf (alles `reused`), `--segment`, `--no-diarize`.
  - Die Diarisierung läuft erst nach `close` des ASR-Backends.
  - Exit-Codes 0/1/2; kein Text auf der Konsole.

### Chunk 4 — Doku
- Dateien: `README.md`, `docs/asr-backends.md`, `docs/referenzformat.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung: README „Lauf“: ganze Session, Wiederverwendungsregel, Exit-Codes, Änderung bei `--segment`. `asr-backends.md`: `identity()`. `referenzformat.md`: ein Satz zum Session-Lauf. Roadmap-Hinweise für TOOL-18 und TOOL-41.
- Verify: `scripts/check`
- AC: Nach dem README lässt sich eine Session vom MP4 bis zu den gelabelten Referenzdateien mit `extract` → `manifest` → `transcribe` verarbeiten.

## Folge-Tickets
- Retry und Protokollierung für `failed` aus dem Session-Lauf: TOOL-18
- Snapshot-ID und Keywords in die Wiederverwendungsregel: TOOL-41, TOOL-43
- Angefragte Sprache wird nicht gespeichert, der Abgleich läuft über `asr.language`: [kein Ticket: Sprache steht fest in der Konfiguration, reicht für V0.1]
- Parallelisierung: [kein Ticket: laut Ticket nicht im Scope, kein Performancebedarf]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `Backend.identity()` | no |
| 2 | `transcribe_session` mit Resume | no |
| 3 | CLI inkl. Diarisierung | no |
| 4 | Doku | no |
