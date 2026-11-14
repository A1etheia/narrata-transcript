# TOOL-94 — Preflight prüft, ob faster-whisper die CUDA-Bibliotheken laden kann

## Ziel
`transcript doctor` und der Preflight von `transcript process` melden einen Fehler, bevor ein Lauf startet, wenn faster-whisper auf der GPU laufen soll, cuBLAS aber nicht laden kann. Heute meldet der Preflight `asr: … on cuda` als `ok`, und der Fehler fällt erst beim ersten Segment auf. Im Pilot (TOOL-58) war das nach Snapshot und rund 6 min Laufzeit.

## Ist-Stand
- `src/transcript/preflight.py:170` `_check_asr` ruft `backend_identity(backend)` auf und meldet `ok` mit dem Gerät. Bei `asr.device: auto` auf der CPU kommt eine Warnung dazu (`:183`). Die Bibliotheken prüft er nicht.
- `src/transcript/asr/whisper.py:121` bestimmt das Gerät über `ctranslate2.get_cuda_device_count()`. Das sieht die GPU auch ohne `LD_LIBRARY_PATH` (gemessen: `1`, alle Compute-Typen). Ein CTranslate2-Aufruf ohne Modell erkennt den Fehler also nicht.
- `src/transcript/asr/whisper.py:182` `_error` bildet die Laufzeitmeldung „Library … is not found or cannot be loaded“ auf `BackendUnavailableError` mit `_LIBRARY_HINT` (`:55`) ab. Das passiert erst in `transcribe`, weil CTranslate2 cuBLAS lazy per `dlopen` lädt.
- `Probes` (`src/transcript/preflight.py:48`) ist die Naht für Tests. `tests/test_preflight.py:76` baut sie, `fake_asr` (`:49`) liefert ein Fake-Backend auf `cuda`.
- README „Spracherkennung“ (`README.md:221`) setzt `LD_LIBRARY_PATH` auf `nvidia/cublas/lib` und `nvidia/cudnn/lib`. README „Preflight“ (`README.md:44`) beschreibt, was `doctor` prüft.

## Entscheidungen
- **Geprüft wird `libcublas.so.12` über `ctypes.CDLL`.** `libctranslate2` 4.8.5 nennt als einzige CUDA-Bibliothek zum Nachladen `libcublas.so.12` (`strings`). cuDNN kommt in der Bibliothek nicht vor, der Wheel ist ohne cuDNN gebaut. `ctypes.CDLL` folgt denselben `dlopen`-Regeln wie CTranslate2: Ohne `LD_LIBRARY_PATH` scheitert es mit `cannot open shared object file`, mit dem Pfad lädt es. Das ist gemessen auf dem Pilotrechner. Die Liste der Bibliotheken ist eine Konstante in `whisper.py`, damit ein CTranslate2-Update nur eine Stelle ändert.
- **Die Prüfung liegt im Backend, der Preflight ruft sie über `Probes`.** `whisper.missing_cuda_library(load=ctypes.CDLL) -> str | None` gibt den ersten Namen zurück, der nicht lädt. `Probes.cuda_libraries` ist austauschbar, damit die Tests ohne GPU laufen (AK 3).
- **Fehler, sobald das gewählte Gerät `cuda` ist, auch bei `auto`.** `auto` fällt nicht auf die CPU zurück: `resolve_device` (`src/transcript/asr/backend.py:149`) wählt `cuda`, sobald eine GPU sichtbar ist, und der Lauf scheitert dann. Laut Ticket ist das ein `error`. Ohne GPU bleibt es bei der bestehenden CPU-Warnung, geprüft wird dann nicht. Die `ok`-Zeile wird zur `error`-Zeile, `_Asr` wird weiter zurückgegeben, damit die Resume-Prüfung läuft.
- **`WhisperBackend.load` prüft dieselbe Bibliothek, bevor das Modell gebaut wird.** So scheitert auch `transcript transcribe` ohne `process` sofort statt am ersten Segment. Das ist eine Zeile mit demselben Helfer und derselben Meldung (`_LIBRARY_HINT`).
- **Meldung:** `faster-whisper large-v3-turbo (…) on cuda, but libcublas.so.12 cannot be loaded; set LD_LIBRARY_PATH as in the README, section Spracherkennung`. Der `OSError`-Text wird nicht übernommen, die Meldung enthält keinen Pfad.

## Daten-Check
- Sitzungsdaten in der Meldung: handled, die Zeile nennt Backend, Modell, Gerät und den Bibliotheksnamen, keine Pfade aus `work/` und keine Sitzungsdaten.
- Fixtures: N/A, die Tests nutzen eine Fake-Ladefunktion und schreiben keine Aufnahme.
- TOOL-66: handled, wie oben; der Preflight liest weiter nur und schreibt nichts.

## Resume-Check
- Abbruch: N/A, der Preflight ist schreibfrei. `load` scheitert jetzt früher, also bevor ein Segment geschrieben wird; ein gespeichertes Ergebnis wird nie ersetzt (TOOL-15).
- Wiederverwendung fertiger Arbeit: N/A, unverändert.
- Gleiches Modell und gleicher Snapshot: N/A, Identität und Einstellungen bleiben gleich, nur die Prüfung kommt dazu.

## Chunks
### Chunk 1 — CUDA-Bibliotheken im Preflight und beim Laden
- Dateien: `src/transcript/asr/whisper.py`, `src/transcript/preflight.py`, `tests/test_preflight.py`, `tests/test_asr_whisper.py`
- Änderung: `CUDA_LIBRARIES = ("libcublas.so.12",)` und `missing_cuda_library` in `whisper.py`; `load` prüft auf `cuda` vor `WhisperModel`. `Probes.cuda_libraries`, `_check_asr` meldet `error` statt `ok`, wenn das Gerät `cuda` ist und eine Bibliothek fehlt.
- Tests: `cuda` und fehlende Bibliothek ergeben `error`, `process` ist `blocked`; `cuda` und geladene Bibliothek ergeben `ok`; CPU ruft die Prüfung nicht auf; die Meldung enthält keinen Pfad; `load` wirft `BackendUnavailableError` und baut kein Modell; `missing_cuda_library` mit einer Fake-Ladefunktion, die `OSError` wirft.
- Verify: `scripts/check`
- AC: AK 3 aus dem Ticket; die Logik für AK 1 und 2.

### Chunk 2 — README und Probe am Pilotrechner
- Dateien: `README.md`
- Änderung: Unter „Preflight“ ergänzen, dass `doctor` auf der GPU das Laden von cuBLAS prüft. Unter „Spracherkennung“ ergänzen, dass `doctor` den fehlenden Pfad meldet und `transcribe` vor dem ersten Segment abbricht.
- Verify: `scripts/check`; `env -u LD_LIBRARY_PATH transcript doctor` zeigt `error` bei `asr` und endet mit Exit 2; mit gesetztem `LD_LIBRARY_PATH` `ok` und Exit 0.
- AC: AK 1 und 2 aus dem Ticket am echten Rechner.

## Folge-Tickets
- cuDNN-Pfad in README „Spracherkennung“ (`README.md:225`): CTranslate2 4.8.5 lädt kein cuDNN, `nvidia/cudnn/lib` in `LD_LIBRARY_PATH` und das Paket `nvidia-cudnn-cu12` sind dann wohl überflüssig. [kein Ticket: in TOOL-61 (E2E-Doku) prüfen, die den `LD_LIBRARY_PATH`-Hinweis ohnehin überarbeitet]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Bibliotheksprüfung in `whisper.py` und `preflight.py`, Tests | no |
| 2 | README, Probe am Pilotrechner | no |
