# TOOL-15 — Einzelnes Audiosegment über konfiguriertes Backend transkribieren

## Ziel
Danach transkribiert `transcript transcribe <session> --segment N` ein Segment aus dem Manifest über das konfigurierte Backend (V0.1: Whisper). Ergebnis ist eine Referenzdatei mit Rohform, Backend, Modell, Revision und `elapsed_ms` unter `work/<session>/asr/`. Bisher entstehen Referenzdateien nur über die Bibliothek und den Smoke-Test, einen Befehl dafür gibt es nicht. `diarize` setzt deshalb voraus, dass jemand per Hand Python aufruft. TOOL-17 baut den Session-Lauf mit Resume auf derselben Funktion auf.

## Ist-Stand
- `src/transcript/asr/backend.py:165-171` `TranscriptionRequest(audio, language, keywords)`, `:224-231` `opened` (load/close), `:234-244` `transcribe` mit Audio-Existenzprüfung und Ergebnisprüfung, `:36-63` Fehlerklassen mit `retryable`.
- `src/transcript/asr/whisper.py:76-84` `WhisperBackend.from_config`; `load()` lädt nur aus dem Cache und dauert; `:126-154` liefert `info`, `settings`, `keywords_used` und `raw`.
- `src/transcript/asr/fake.py:22-66` `FakeBackend` für Tests: zählt load/close, kann einen Fehler werfen.
- `src/transcript/reference.py:197-228` `from_backend_result(..., elapsed_ms)`, `:231-248` `failed_reference`, `:251-264` `write_reference` (Rohform zuerst, dann Normalform, beide atomar), `:334-351` `load_reference`.
- `src/transcript/manifest.py:145-164` `load_manifest`, `:40-49` `Segment.index`/`file`/`source.sha256`.
- `src/transcript/session.py:78-100` `segment_wav(i)`, `reference(i)`, `reference_raw(i)`.
- `src/transcript/config.py:37-48` `language`, `asr_*`.
- `src/transcript/__main__.py:156-191` `_diarize` als Vorlage: Fehler → `error: …` auf stderr, Exit 2, nur Zähler auf der Konsole. `diarization/__init__.py:196-198` misst `elapsed_ms` mit `perf_counter` nur um den Modellaufruf.
- `tests/test_smoke.py:282-345` `DiarizeCommandTest` patcht `load_manifest` und `from_config`. `tests/test_reference.py` liefert `KEY`, `MANIFEST`, `SEGMENT`, `SECRET`, `minimal`. `tests/test_whisper_smoke.py` ruft heute `transcribe` + `write_reference` direkt auf.

## Entscheidungen
- **Neues Modul `src/transcript/transcription.py`** mit `transcribe_segment(paths, manifest, index, backend, language, keywords=(), force=False) -> SegmentResult`. Es kennt nur die `Backend`-Schnittstelle; welches Backend läuft, entscheidet der Aufrufer (CLI: `WhisperBackend.from_config`). TOOL-17 ruft es pro Segment auf. Für viele Segmente hebt TOOL-17 `opened` dann aus der Funktion heraus.
- **Vorprüfung vor dem Laden.** Die Prüfungen laufen in dieser Reihenfolge, alle bevor das Modell lädt: Ist der Index im Manifest (sonst Fehler mit dem gültigen Bereich)? Existiert das WAV (`paths.segment_wav(index)`)? Liegt schon ein `transcribed`-Ergebnis vor? Das Laden dauert Minuten und soll nicht für einen Tippfehler anfallen. `transcribe` prüft die Datei zusätzlich.
- **Vorhandenes Ergebnis:** Ein `transcribed` ohne `force` bricht mit Hinweis auf `--force` ab. `force` transkribiert neu, die Sprecher-Labels fallen dann weg, und `diarize` setzt sie ohne Modell neu. Ein vorhandenes `failed` wird ohne `force` neu versucht. Den Vergleich von Modell und Settings für die Wiederverwendung macht TOOL-17.
- **Fehler:**
  - Ein `BackendError` aus `load()` (Modell, Runtime, GPU) schreibt nichts und geht an den Aufrufer.
  - Ein `BackendError` aus `transcribe` schreibt `failed_reference` mit `raw=None`, die Fehlerklasse geht an den Aufrufer. Ausnahme: Ein vorhandenes `transcribed` (nur mit `force` möglich) bleibt stehen und wird nie durch ein `failed` ersetzt.
  - Ein Ergebnis gilt also nie fälschlich als erfolgreich. Retry kommt mit TOOL-18.
- **Keywords:** Der Parameter `keywords` ist die Nahtstelle. Die CLI übergibt `()`, bis TOOL-43/44 liefern. Die Sprache kommt aus `config.language`.
- **`elapsed_ms`** misst nur `transcribe(...)` per `perf_counter`, nicht das Laden. So ist es pro Segment vergleichbar, wie bei `diarize`.
- **`SegmentResult`** hält nur Zähler: Index, Outcome (`transcribed`/`failed`), Passagen, Wörter, Wörter mit Confidence, `elapsed_ms`, Backend, Modell, Revision und erkannte Sprache. Kein Text.
- **CLI `transcript transcribe <session> --segment N [--force] [--config]`.** `--segment` ist vorerst Pflicht. TOOL-17 macht es optional, dann laufen alle Segmente. Die Ausgabe ist eine Zeile mit Backend/Modell/Revision, Laufzeit, Passagen, Wörtern und Sprache, danach `wrote <reference>`. Fehler laufen wie bei `diarize` ohne Traceback auf Exit 2.

## Daten-Check
- Rohaudio: handled, wird nur gelesen. Ein Test prüft den SHA-256 von WAV und Original vor und nach dem Lauf; Whisper läuft lokal.
- Arbeitsdateien: handled. Referenz und Rohform liegen unter `work/` (gitignored).
- Konsole und Logs: handled. Nur Zähler, Laufzeit, Modell und Sprache. Ein Test prüft, dass erfundener Text (`SECRET`) nicht in stdout/stderr steht; Keywords sind vorerst leer.
- Fehlermeldungen: handled. Sie nennen Segmentindex, Datei und Fehlerklasse; Backend-Meldungen sind schon textfrei (`backend.py:247-255`).
- Fixtures: handled. Unit-Tests nutzen `FakeBackend` und erfundene Daten; der Smoke-Test spricht einen erfundenen Satz per flite.
- `debug.log`: N/A. Der Befehl schreibt keinen Text in Logs; der Text steht ohnehin in der Referenzdatei unter `work/`.

## Contract-Check
N/A. Nur interne Arbeitsdateien (Referenzformat v1); Export (TOOL-69) und Narrata-Endpoint sind nicht berührt.

## Resume-Check
- Abbruch: handled. Rohform vor Normalform, beide atomar (`write_reference`). Ein Abbruch hinterlässt höchstens eine Rohdatei ohne Normalform, das Segment gilt als nicht transkribiert, und der nächste Aufruf rechnet ohne `--force` neu.
- Wiederverwendung: handled. Ein fertiges `transcribed` bleibt erhalten, ein Neulauf braucht `--force`. Den automatischen Abgleich von Modell und Settings macht TOOL-17.
- Gleiches Modell/Snapshot: handled. `model`, `model_version`, `runtime_version` und `settings` stehen im `asr`-Block jeder Datei. Einen Wissens-Snapshot gibt es noch nicht (TOOL-41), `keywords_used` bleibt leer.

## Dependency-Check
- Neue Abhängigkeit: N/A, nutzt das vorhandene Extra `whisper` und kein neues Modell.
- Lokal / Lizenz / Hardware: N/A, unverändert gegenüber TOOL-64 (README „Spracherkennung“).

## Format-Check
- Referenzformat: handled. Bleibt `format_version: 1`, keine Feldänderung; `elapsed_ms` gibt es seit TOOL-16.
- Konfiguration: N/A, keine neuen Schlüssel.

## Chunks
### Chunk 1 — Einzelsegment-Transkription als Bibliotheksfunktion
- Dateien: `src/transcript/transcription.py`, `tests/test_transcription.py`
- Änderung: `transcribe_segment` und `SegmentResult` wie oben, mit eigener Fehlerklasse `TranscriptionError` für unbekanntes Segment, fehlendes WAV und vorhandenes Ergebnis.
- Verify: `scripts/check`
- AC: Tests mit `FakeBackend` prüfen:
  - Erfolg schreibt Roh- und Normalform mit Backend, Modell und `elapsed_ms`, Confidence und Signale bleiben erhalten.
  - Ein unbekannter Index oder ein fehlendes WAV bricht ab, bevor `load` läuft (`load_calls == 0`).
  - Ein vorhandenes `transcribed` bricht ohne `force` ab; `force` ersetzt es.
  - Ein Fehler in `transcribe` schreibt `failed`; ein Fehler in `load` schreibt nichts.
  - Ein Fehler mit `force` lässt ein vorhandenes `transcribed` unverändert.
  - Das Backend wird immer geschlossen; WAV-Bytes sind unverändert; Keywords und Sprache kommen im Request an.

### Chunk 2 — CLI `transcript transcribe`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `tests/test_whisper_smoke.py`
- Änderung: Subcommand `transcribe` mit `--segment` (positive Zahl, Pflicht), `--force` und `--config`; das Backend kommt aus `WhisperBackend.from_config`. Der Whisper-Smoke-Test läuft über `transcribe_segment`, damit der echte Pfad abgedeckt ist.
- Verify: `scripts/check`; `TRANSCRIPT_WHISPER_SMOKE=1 LD_LIBRARY_PATH=… .venv/bin/python -m unittest discover -s tests -p test_whisper_smoke.py`
- AC: Ein Test mit gepatchtem `from_config` (FakeBackend) prüft:
  - Exit 0 mit Zählern und ohne Text.
  - Zweiter Lauf: Exit 2 mit Hinweis auf `--force`; `--force` läuft durch.
  - Ein Backendfehler kommt ohne Traceback.
  - Ein unbekanntes Segment kommt als Fehler.

### Chunk 3 — Doku
- Dateien: `README.md`, `docs/asr-backends.md`, `docs/referenzformat.md`
- Änderung: README bekommt im Abschnitt „Spracherkennung“ einen Absatz **Lauf** mit `transcript transcribe` und der Reihenfolge `extract` → `manifest` → `transcribe` → `diarize`, dazu `--force` und das Verhalten bei Fehlern. `asr-backends.md`: Codebeispiel verweist auf `transcribe_segment`. `referenzformat.md`: Satz zur Entstehung der Datei per Befehl.
- Verify: `scripts/check`
- AC: Nach dem README lässt sich ein Segment von MP4 bis Referenzdatei transkribieren.

## Folge-Tickets
- Keywords aus der Wissensschnittstelle statt `()`: TOOL-43 (Schnittstelle), TOOL-44 (Keyword-Biasing); das AK „Keyword-Hinweise übergeben“ geht hiermit an TOOL-43.
- Alle Segmente einer Session, `--segment` optional, Wiederverwendung über `model_version`/`settings`, `opened` einmal für alle Segmente, danach `diarize_session`: TOOL-17
- Retry bei `ResourceError`/`BackendRuntimeError`, Protokollierung: TOOL-18

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `transcribe_segment` mit Vorprüfung, Fehler- und Neulauf-Regeln | no |
| 2 | CLI `transcript transcribe`, Smoke-Test über den echten Pfad | no |
| 3 | README, asr-backends, referenzformat | no |
