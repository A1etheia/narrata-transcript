# TOOL-64 — Lokales V0.1-Transkriptionsbackend (faster-whisper)

Branch `tool-64-whisper-backend` steht (`--no-track`, kein Upstream), TOOL-64 ist In Progress. Danach die Chunks in Reihenfolge mit `/chunk-commit`.

**Abhängigkeiten (`/check-ticket-deps`):** TOOL-62 und TOOL-63 sind Done, ohne Divergenz-Marker. Downstream ist TOOL-76 To Do. Das AK „Sprecherinformationen übernehmen“ entfällt praktisch: faster-whisper liefert keine Sprecher, die kommen aus TOOL-76. `speaker_labels` ist deshalb `false`. Keywords kommen über `TranscriptionRequest.keywords`; ihre Quelle (TOOL-38/39/67) ist noch offen.

## Ziel
Danach lässt sich ein Manifest-Segment vollständig lokal mit Whisper large-v3-turbo transkribieren. Das Backend liefert ein `BackendResult` mit Wortzeiten, Wort-Confidence, Segment-Signalen, ehrlichem `keywords_used` und unveränderter Rohantwort, die `reference.from_backend_result` und `write_reference` direkt speichern. Fehlende Runtime, ein fehlendes Modell, fehlende CUDA-Bibliotheken und Speichermangel werden als passende `BackendError`s gemeldet. Heute gibt es nur das `FakeBackend` (`src/transcript/asr/fake.py`) und die Wegwerf-Runner unter `scripts/spike/`.

## Ist-Stand
- `src/transcript/asr/backend.py:135-151`: Das Protokoll `Backend` mit `info`, `capabilities`, `load`, `transcribe`, `close`. `opened()` (`:154`) und `transcribe()` (`:164`) umhüllen es. `_guarded` (`:177`) macht fremde Exceptions zu `BackendError`s ohne Original-Message. `_result_problem` (`:196`) prüft `keywords_used`, Zeiten und Confidence.
- `src/transcript/asr/backend.py:49-84` `Capabilities` und `:86-93` `BackendInfo` (`model_version`, `runtime_version`).
- `docs/asr-backends.md`, Abschnitte „Regeln für Adapter“ und „Abbildung der Kandidaten“: Die Bibliothek wird erst in `load()` importiert, eigene Fehler bildet der Adapter selbst ab, `keywords_used` steht nach der 223-Token-Kürzung, und die Fähigkeitstabelle für faster-whisper ist schon festgelegt.
- `tests/test_asr_backend.py`: Ein Import-Guard hält `faster_whisper`/`ctranslate2` aus generischem Code und von der Modulebene der Adapter fern.
- `scripts/spike/run_whisper.py:8-50`: bewährte Einstellungen (`language de`, `beam_size 5`, `vad_filter`, `word_timestamps`, ohne `condition_on_previous_text`), Abbildung von Segmenten, Wörtern und Signalen, `device="cuda"` mit `compute_type="float16"`.
- Spike-venv (`~/.cache/narrata-spike/whisper`): faster-whisper 1.2.1, ctranslate2 4.8.4, nvidia-cublas-cu12 12.9, nvidia-cudnn-cu12 8.9. Die CUDA-Bibliotheken werden nur über `LD_LIBRARY_PATH` gefunden (`scripts/spike/README.md`, „Einrichtung“).
- faster-whisper 1.2.1 `transcribe.py:1545-1547`: Hotwords werden über `tokenizer.encode(" " + hotwords)` auf `max_length // 2 - 1` = 223 Tokens gekürzt. `utils.py:29` bildet `large-v3-turbo` auf `mobiuslabsgmbh/faster-whisper-large-v3-turbo` ab. `transcribe()` liefert einen lazy Generator, Fehler kommen also erst beim Iterieren.
- HF-Cache: Snapshot `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` des Turbo-Modells liegt lokal.
- `src/transcript/config.py:14-106`: Die Konfiguration kennt bisher `language`, `paths`, `segmentation`, `audio` und `debug`, aber noch nichts zu ASR. `config/example.yaml` spiegelt das.
- `src/transcript/reference.py:197-228` `from_backend_result`, `:251` `write_reference(paths, reference, raw)`. `src/transcript/debug_log.py` `transcript_logger`.
- `pyproject.toml`: einzige Laufzeitabhängigkeit `pyyaml`, Extra `dev`.
- Hardware des Testrechners: RTX 3080 Ti (12 GB VRAM), WSL mit 25 GB RAM. `ffmpeg` hat den Filter `flite`.

## Entscheidungen
- **Modul `src/transcript/asr/whisper.py`, Klasse `WhisperBackend`,** `backend_id = "faster-whisper"`. `faster_whisper` und `ctranslate2` werden nur in `load()` importiert. Das Modul wird nicht in `transcript.asr.__init__` re-exportiert. Grund: Wer nur das Fake-Backend braucht, soll den Adapter nicht laden müssen.
- **Abhängigkeit als optionales Extra `whisper`:** `faster-whisper>=1.2.1,<1.3`, `nvidia-cublas-cu12`, `nvidia-cudnn-cu12<9`, wie im Spike erprobt. `scripts/check` und die Unit-Tests laufen weiter ohne das Extra.
- **Konfiguration, neuer Abschnitt `asr`:**
  - `model`: Default `large-v3-turbo`, ein faster-whisper-Name oder ein lokales Verzeichnis.
  - `device`: `auto|cpu|cuda`, Default `auto`. `auto` nimmt `cuda`, wenn `ctranslate2.get_cuda_device_count() > 0`.
  - `compute_type`: Default `null`, dann `float16` auf CUDA und `int8` auf der CPU.
  - `beam_size`: Default 5.
  - **Fest im Code und nicht konfigurierbar:** `vad_filter`, `word_timestamps` und `condition_on_previous_text=False`. Grund: Diese Werte hat TOOL-62 entschieden, und TOOL-20 braucht die Wortzeiten. Die Sprache kommt aus `request.language`, also aus `config.language`.
  - Erzeugt wird das Backend mit `WhisperBackend.from_config(config)`.
- **Nur lokal laden (`local_files_only=True`).** Das Backend lädt nie etwas herunter. Ein fehlendes Modell ergibt `BackendUnavailableError` mit Modellname und Verweis auf den Download-Befehl im README. `model_version` ist der Name des Snapshot-Verzeichnisses (die Revision) oder bei einem lokalen Pfad `None`. `runtime_version` ist `faster_whisper.__version__`.
- **Hotwords selbst kürzen:** Die Keywords werden der Reihe nach übernommen, solange `len(hf_tokenizer.encode(" " + " ".join(kept)).ids) <= 223` gilt. Übergeben wird nur der übernommene Teil. `keywords_used` ist dann genau dieser Teil, und die interne Kürzung von faster-whisper greift nie. Ohne Keywords wird `hotwords=None` übergeben.
- **Abbildung:**
  - `ResultSegment(text=strip, start, end, words, signals={avg_logprob, no_speech_prob, compression_ratio})`.
  - `ResultWord(text=strip, start, end, confidence=probability)`.
  - `language` und `language_probability` aus `TranscriptionInfo`.
  - `settings`: model, device, compute_type, beam_size und die festen Werte.
  - `raw = {"info": {language, language_probability, duration, duration_after_vad}, "segments": [dataclasses.asdict(s) …]}`, unverändert und mit führenden Leerzeichen. Grund: Nur die Normalform trimmt Leerraum, das Original bleibt in der Rohdatei.
- **Fehler** (Abbildung im Adapter; die Message nennt nie die Original-Message, denn sie kann Hotwords enthalten):
  - `ImportError` → `BackendUnavailableError` mit „pip install -e '.[whisper]'“.
  - Modell nicht im Cache oder Pfad fehlt → `BackendUnavailableError`.
  - `device: cuda` ohne GPU → `BackendUnavailableError`.
  - `RuntimeError` mit „out of memory“ sowie `MemoryError` → `ResourceError`.
  - `RuntimeError` mit „Library … is not found“ oder „cannot be loaded“ (cuBLAS/cuDNN) → `BackendUnavailableError` mit Hinweis auf `LD_LIBRARY_PATH`.
  - Rest → `BackendRuntimeError`.
  - Der Generator wird innerhalb des `try` vollständig verbraucht.
- **`close()`** gibt die Modellreferenz frei und ruft `gc.collect()` auf. So ist der Speicher vor pyannote (TOOL-76) wieder frei.
- **`elapsed_ms`, CLI und Schreiben** gehören dem Aufrufer, also TOOL-15 und TOOL-17. TOOL-64 liefert das Backend und weist über einen Test nach, dass `from_backend_result` und `write_reference` sein Ergebnis aufnehmen.
- **Smoke-Test opt-in:** `tests/test_whisper_smoke.py` läuft nur mit `TRANSCRIPT_WHISPER_SMOKE=1`, installiertem Extra, Modell im Cache und `ffmpeg` mit `flite`. ffmpeg spricht einen erfundenen Satz in ein Temp-WAV (16 kHz mono). Der Test lädt dann das echte Modell auf `device` aus der Umgebung (Default `auto`) und prüft: nicht leerer Text, Wortzeiten, Confidence in 0..1, `info.model_version` gesetzt, Ergebnis über `from_backend_result` speicherbar.
- **`scripts/spike/` wird gelöscht,** einschließlich der Diarisierungs-Runner und `speakers.py` (Übergabe aus TOOL-20). Die Verweise in der Doku zeigen danach auf den letzten Commit, der die Runner noch enthält. TOOL-76 findet `run_pyannote.py` dort.

## Daten-Check
- Folgt TOOL-66: handled. Der Adapter schreibt nichts und loggt keinen Text. `raw` geht nur an den Aufrufer, der es über `write_reference` unter `work/` ablegt.
- Fehlermeldungen: handled. Eigene Texte mit Backend-ID, Modellname, Gerät und Pfad. Runtime-Messages werden nur auf Muster geprüft und nie übernommen. Ein Test stellt sicher, dass ein Keyword aus einer simulierten Runtime-Message nicht in der Fehlermeldung auftaucht.
- Fixtures und Tests: handled. Unit-Tests nutzen ein Stub-Modul `faster_whisper` über `sys.modules` mit erfundenen Sätzen. Der Smoke-Test synthetisiert einen erfundenen Satz in ein Temp-Verzeichnis. Kein Audio landet unter `tests/fixtures/`.
- Kann Echtes ins Repo gelangen? N/A, weil `work/` und `*.wav` ignoriert sind (`tests/test_gitignore.py`). Mit `scripts/spike/` verschwindet außerdem die letzte Stelle, die auf `work/…/spike` verweist.

## Contract-Check
N/A, weil das Backend weder Contract-JSON (IOA-1214) noch den Narrata-Endpoint berührt. Es liefert nur das interne `BackendResult`. Narrata braucht keine Änderung.

## Resume-Check
- Abbruch: handled. Das Backend schreibt nichts. Ein Abbruch mitten im Segment hinterlässt keine Datei, und `opened()` ruft `close()` auch nach Fehlern auf.
- Wiederverwendung: N/A für TOOL-64, das Überspringen fertiger Segmente macht TOOL-17.
- Gleiches Modell: handled als Vorleistung. `model_version` (Snapshot-Revision), `runtime_version` und `settings` stehen im Ergebnis und damit in `asr/segment-NN.json`. Da `local_files_only` gilt, wechselt das Modell nie still durch einen Download. Ein Snapshot des Domänenwissens ist N/A, weil die Keywords bereits im Request stehen und `keywords_used` sie festhält.

## Dependency-Check
- Nötig: handled. Das Modell ist durch TOOL-62 entschieden, und das Ticket verlangt es.
- Lokal: handled. CTranslate2-Inferenz auf CPU oder CUDA, Modell aus dem lokalen HF-Cache, kein Netz zur Laufzeit.
- Lizenzen: handled. faster-whisper und CTranslate2 stehen unter MIT. Die Konvertierung `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (auf HF inzwischen umgeleitet auf `dropbox-dash/…`, Revision `0a363e9…`) steht unter MIT und ist laut Modellkarte eine FP16-Konvertierung von `openai/whisper-large-v3-turbo`, das ebenfalls unter MIT steht. Die NVIDIA-Pakete fallen unter die NVIDIA-Lizenz für weitergegebene Laufzeitbibliotheken. Sie werden nur lokal installiert und nicht mitgeliefert. Alles kommt ins README.
- Hardware: handled, im README dokumentiert. Getestet auf einer NVIDIA-GPU mit 12 GB VRAM; die CPU geht, ist aber deutlich langsamer. Bis 10,5 GB RAM auf 5 h. Nicht gleichzeitig mit pyannote laufen lassen (bis 13,8 GB), und unter WSL das Speicherlimit über 15 GB setzen.

## Format-Check
N/A, weil sich kein versioniertes Format ändert: Das Referenzformat bleibt bei `format_version: 1`, und `config.yaml` hat kein Versionsfeld. Die neuen `asr`-Keys sind optional mit Defaults, bestehende Konfigurationen bleiben gültig.

## Chunks
### Chunk 1 — ASR-Konfiguration und Extra
- Dateien: `pyproject.toml`, `src/transcript/config.py`, `config/example.yaml`, `tests/test_config.py`
- Änderung: Extra `whisper` anlegen. Abschnitt `asr` mit `model`, `device`, `compute_type` und `beam_size` samt Validierung (Device aus `auto|cpu|cuda`, compute_type als String oder null, beam_size als positive ganze Zahl). Dazu Felder in `Config` und die Ausgabe in `format_config`.
- Verify: `scripts/check`
- AC: Defaults greifen ohne `asr`-Abschnitt. Ungültige Werte nennen Datei und Key. `transcript config` zeigt den Abschnitt.

### Chunk 2 — Whisper-Adapter
- Dateien: `src/transcript/asr/whisper.py`, `tests/test_asr_whisper.py`
- Änderung: `WhisperBackend` mit `from_config`, `load` (Import, Geräteauswahl, `WhisperModel(…, local_files_only=True)`, Revision ermitteln), `transcribe` (Hotword-Kürzung, Abbildung, `raw`, Fehlerabbildung inklusive Generator) und `close`. Die Tests laufen über ein Stub-Modul in `sys.modules`: Capabilities, Abbildung, `keywords_used` an der 223-Token-Grenze, jede Fehlerklasse, keine Runtime-Message in den Fehlern, `close` nach fehlgeschlagenem `load`, Ergebnis durch `reference.from_backend_result`/`write_reference` und `load_reference`.
- Verify: `scripts/check`
- AC: Der Adapter erfüllt das Protokoll, besteht `transcribe()`/`_result_problem` und den Import-Guard. Confidence und Signale bleiben erhalten.

### Chunk 3 — Smoke-Test mit echtem Modell
- Dateien: `tests/test_whisper_smoke.py`
- Änderung: Opt-in-Test wie unter „Entscheidungen“ beschrieben, mit Skip-Gründen pro fehlender Voraussetzung.
- Verify: `scripts/check` (übersprungen) und `TRANSCRIPT_WHISPER_SMOKE=1 LD_LIBRARY_PATH=… .venv/bin/python -m unittest tests.test_whisper_smoke` mit installiertem Extra
- AC: Der Test läuft auf dem Testrechner lokal und reproduzierbar durch.

### Chunk 4 — Doku
- Dateien: `README.md`, `docs/asr-backends.md`
- Änderung: README mit Installation des Extras, CUDA-Bibliotheken und `LD_LIBRARY_PATH`, einmaligem Modell-Download, `asr`-Konfiguration, Hardware-/RAM-Bedarf, Lizenzen, Smoke-Test-Befehl und Stand. `asr-backends.md` bekommt Verweis auf `whisper.py`, Konfiguration, Fehlerabbildung und Hotword-Kürzung.
- Verify: `scripts/check`
- AC: Installation und Voraussetzungen sind so dokumentiert, dass der Smoke-Test nach README läuft.

### Chunk 5 — `scripts/spike/` ablösen
- Dateien: `scripts/spike/` (löschen), Verweise in `docs/asr-backends.md`, `docs/spikes/*.md`, README
- Änderung: Verzeichnis entfernen. Verweise auf den letzten Commit mit den Runnern umstellen. Eingefrorene Pläne bleiben unverändert.
- Verify: `scripts/check`; `grep -rn "scripts/spike" --exclude-dir=plans .` findet nur noch Commit-Verweise
- AC: Kein Pipeline-Code und keine Doku setzt die Spike-Runner mehr voraus.

## Folge-Tickets
- CLI-Befehl zum Transkribieren eines Segments, `elapsed_ms` messen, `write_reference` aufrufen: TOOL-15
- Ganze Session, Resume mit Vergleich von `model_version`/`settings`: TOOL-17
- Retry auf `ResourceError`/`BackendRuntimeError`: TOOL-18
- Diarisierung nach freigegebenem Whisper-Modell: TOOL-76
- RAM-Vorabprüfung vor dem Laden: [kein Ticket: OOM wird als `ResourceError` gemeldet, eine Schätzung vorab wäre geraten]
- Automatisches Setzen von `LD_LIBRARY_PATH` für die pip-CUDA-Bibliotheken: [kein Ticket: einmalige Einrichtung, im README dokumentiert]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | ASR-Konfiguration und Extra | no |
| 2 | Whisper-Adapter mit Unit-Tests | no |
| 3 | Opt-in-Smoke-Test mit echtem Modell | no |
| 4 | README und `asr-backends.md` | no |
| 5 | `scripts/spike/` entfernen | no |
