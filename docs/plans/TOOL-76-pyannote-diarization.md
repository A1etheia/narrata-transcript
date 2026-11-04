# TOOL-76 — Sprecher-Diarisierung mit pyannote integrieren

## Ziel
Nach der Transkription trägt jedes Wort im Referenztranskript (TOOL-16) ein Sprecher-Label aus pyannote `speaker-diarization-community-1`, jede Passage das Mehrheitslabel. Heute sind `diarization` und alle `speaker`-Felder leer, TOOL-68 hat also nichts zuzuordnen. Danach gibt es `transcript diarize <session>`, das die Diarisierung pro Segment rechnet oder eine gespeicherte wiederverwendet und die Labels in die Referenzdateien schreibt.

## Ist-Stand
- `src/transcript/reference.py:43-55` `Word.speaker`, `:58-73` `Passage.speaker`, `:106-131` `Overlap`/`Diarization`, `:156-164` Label-Prüfung gegen `diarization.labels`, `:182-188` `majority_speaker`, `:337-412` `to_json`/`from_json` inkl. `diarization`. Das Format ist für TOOL-76 schon vorbereitet; `docs/referenzformat.md`, Abschnitt „Sprecher“, beschreibt die Regeln.
- `src/transcript/reference.py:251-266` `write_reference` schreibt Roh- und Normalform; `:304-323` `load_reference`.
- `src/transcript/session.py:55-113` `SessionPaths`: `asr_dir`, `reference(i)`, `segment_wav(i)`; noch kein Diarisierungs-Pfad.
- `src/transcript/asr/whisper.py:86-151` Muster für Adapter: Import in `load()`, nur lokaler Cache (`local_files_only`), `_revision` aus dem Snapshot-Pfad (`:250-252`), Fehlerabbildung (`:178-193`), `close()` mit `gc.collect()`.
- `src/transcript/asr/backend.py:35-62` Fehlerklassen mit `retryable` (`BackendUnavailableError`, `ResourceError`, `BackendRuntimeError`, `AudioInputError`).
- `src/transcript/audio.py:300` `_sha256(path)` für Dateihashes.
- `src/transcript/config.py:14-110` Abschnittsmuster (`_section`, `_reject_unknown_keys`), `asr`-Abschnitt als Vorlage; `config/example.yaml`.
- `src/transcript/__main__.py:133-185` Subcommands `config|doctor|extract|manifest`, `_log_to_stderr`.
- `tests/test_asr_fake.py:23` `MODEL_LIBRARIES`-Import-Guard (kennt `torch`, nicht `pyannote`).
- Spike-Runner `scripts/spike/run_pyannote.py` im Stand `2f5b875`: WAV als float32-Tensor in den Speicher, `Pipeline.from_pretrained`, `.to(cuda)`, `output.speaker_diarization` / `output.exclusive_speaker_diarization`, `itertracks(yield_label=True)`.
- Spike-venv `~/.cache/narrata-spike/pyannote`: pyannote.audio 4.0.7, torch 2.14.1, `nvidia-cudnn-cu13` 9.x; `.venv` hat ctranslate2 4.8.5 mit `nvidia-cudnn-cu12` 8.9. Modell `models--pyannote--speaker-diarization-community-1` liegt im HF-Cache.
- Es gibt noch keinen Transkriptions-Befehl (TOOL-15/17 folgen); Referenzdateien entstehen bisher nur über Bibliothek und Smoke-Test.

## Entscheidungen
- **Eine venv, neues Extra `diarization`** (`pyannote.audio>=4.0.7,<4.1`). Chunk 1 installiert es in `.venv` und lässt den Whisper-Smoke-Test erneut laufen; cu12/cuDNN 8 und cu13/cuDNN 9 haben verschiedene Paketnamen und Sonames. Scheitert das, wird vor Chunk 2 auf einen Subprozess in eigener venv umgeplant.
- **Pro Segment diarisieren.** Ein pyannote-Lauf pro `audio/segment-NN.wav`; Labels gelten nur innerhalb des Segments. Die Zuordnung über Segmente hinweg gehört zu TOOL-68.
- **Paket `src/transcript/diarization/`:** `__init__.py` generisch (Typen, Zuordnung, Speicher, Ablauf, kein torch), `pyannote.py` Adapter mit Import in `load()`. Fehler nutzen die Klassen aus `transcript.asr.backend`.
- **Rohdaten getrennt:** `work/<session>/diarization/segment-NN.json` mit `format_version: 1`, `backend_id`, `model`, `model_version` (Snapshot-Revision), `runtime_version`, `settings` (`device`), `num_speakers`, `audio_sha256` (des Segment-WAVs), `turns` und `exclusive_turns` (`{start_ms, end_ms, label}`). Nur Zeiten und generische Labels, kein Text.
- **Zuordnung:** Wortmitte `(start_ms + end_ms) / 2` liegt in einem exklusiven Turn `[start, end)` → dessen Label; sonst oder ohne Wortzeiten `None`. Passagen-Label über `majority_speaker`. `Diarization.labels` sind alle Labels des Segments, `overlaps` die Bereiche, in denen sich mindestens zwei Turns überlappen (aus `turns`, nicht für die Zuordnung).
- **Das ASR-Ergebnis bleibt unangetastet:** `assign_speakers` ändert nur `speaker`-Felder und `diarization`; Text, Zeiten, Confidence, `asr`, `processing` und die ASR-Rohdatei bleiben gleich (Test). Die Normalform wird atomar neu geschrieben.
- **Resume:** Eine gespeicherte Diarisierung gilt, wenn `audio_sha256`, `model`, `model_version`, `settings` und `num_speakers` gleich sind. Die Revision kommt ohne Laden des Modells aus dem lokalen Cache (`huggingface_hub.snapshot_download(local_files_only=True)`). Das Modell wird erst geladen, wenn ein Segment wirklich gerechnet werden muss. `--force` rechnet neu.
- **Offline:** `load()` löst das Modell nur aus dem lokalen Cache auf und setzt `HF_HUB_OFFLINE=1` (setdefault) vor dem Import. Fehlt das Modell, kommt `BackendUnavailableError` mit Verweis auf den einmaligen Download im README (`hf auth login`, Token bleibt im HF-Cache, nie im Repo oder in `.env`).
- **Konfiguration, neuer Abschnitt `diarization`:** `model` (Default `pyannote/speaker-diarization-community-1`, auch lokales Verzeichnis), `device` (`auto|cpu|cuda`, Default `auto`). `num_speakers` nur als CLI-Option `--num-speakers`, bis der Snapshot (TOOL-41) die Zahl liefert.
- **CLI `transcript diarize <session> [--num-speakers N] [--force]`:** liest Manifest und Referenzen. Segmente mit `status: failed` oder ohne Referenz werden übersprungen und gezählt. Ausgabe pro Segment: Zahl der Labels, gelabelte Wörter / alle Wörter, Turns, wiederverwendet oder Laufzeit. Keine Labels, kein Text. Ein eigener Prozess nach der Transkription heißt automatisch nicht parallel zu Whisper; TOOL-17 ruft später `diarize_session` nach `WhisperBackend.close()` auf.

## Daten-Check
- Rohaudio bleibt lokal: handled. pyannote läuft offline auf dem WAV unter `work/`.
- Rohdaten der Diarisierung: handled. Liegen unter `work/` (gitignored), enthalten nur Zeiten und `SPEAKER_NN`.
- Konsole und Logs: handled. Nur Zähler und Laufzeiten; ein Test prüft, dass weder Wort-Text noch Labels in der CLI-Ausgabe stehen.
- Fehlermeldungen: handled. Nennen Modell, Gerät, Segmentdatei und Exception-Typ, nie die Runtime-Meldung (wie `whisper.py:178-193`).
- Fixtures: handled. Tests nutzen synthetische Turns und erfundene Wörter; der Smoke-Test spricht mit ffmpeg `flite` einen erfundenen Satz.
- Telemetrie: handled. pyannote 4 schickt per Default Laufmetadaten (Audiodauer, Sprecherzahl, Version, Session-ID) an `otel.pyannote.ai`. Der Adapter setzt vor dem Import `PYANNOTE_METRICS_ENABLED=false` und `HF_HUB_OFFLINE=1` hart, nicht als Default; ein Test prüft das.
- HF-Token: handled. Wird nie gelesen oder gespeichert, nur der einmalige Download im README beschreibt `hf auth login`.

## Contract-Check
N/A, weil TOOL-76 nur interne Arbeitsdateien schreibt; der JSON-Export (TOOL-69) und der Narrata-Endpoint sind nicht berührt.

## Resume-Check
- Abbruch: handled. Rohdatei zuerst, dann Normalform, beide atomar; ein Abbruch hinterlässt höchstens eine Rohdatei, die beim nächsten Lauf passt und wiederverwendet wird.
- Wiederverwendung: handled. Passende Rohdatei (Audio-Hash, Modell, Revision, Settings, `num_speakers`) wird ohne Modell-Laden übernommen; nach einem ASR-Neulauf (TOOL-17) setzt `diarize` die Labels so in Sekunden neu.
- Gleiches Modell/Snapshot: handled. Revision und Settings stehen in der Rohdatei und im `diarization`-Block; Abweichung → neu rechnen. Ein Wissens-Snapshot gibt es noch nicht (TOOL-41).

## Dependency-Check
- Nötig: handled. Entscheidung aus TOOL-20, vom Ticket verlangt.
- Lokal: handled. Inferenz auf CUDA oder CPU, Modell aus dem HF-Cache, `HF_HUB_OFFLINE=1`.
- Lizenz: handled. pyannote.audio MIT, Modell CC-BY-4.0 (gated) → Attribution im README.
- Hardware: handled, im README. Unter 4 GB VRAM, bis 13,8 GB RAM auf 5 h, etwa 4 min; nicht parallel zu Whisper; torch macht die venv um mehrere GB größer.
- Verträglichkeit mit dem Whisper-Extra: Gate in Chunk 1.

## Format-Check
- Referenzformat: handled. Bleibt `format_version: 1`; `diarization` und `speaker` sind seit TOOL-16 optional, alte Dateien bleiben gültig.
- Neue Rohdatei `diarization/segment-NN.json`: handled. Beginnt mit `format_version: 1`; eine andere Version gilt als nicht passend und wird neu gerechnet.
- `config.yaml`: handled. Hat kein Versionsfeld, der neue Abschnitt ist optional mit Defaults.

## Chunks
### Chunk 1 — Extra und Konfiguration
- Dateien: `pyproject.toml`, `src/transcript/config.py`, `config/example.yaml`, `tests/test_config.py`
- Änderung: Extra `diarization`; Abschnitt `diarization` (`model`, `device`) in `load_config`/`format_config`; Beispielkonfiguration auf Deutsch kommentiert.
- Verify: `scripts/check`; `.venv/bin/pip install -e '.[whisper,diarization]'` ohne Konflikt, danach `TRANSCRIPT_WHISPER_SMOKE=1 LD_LIBRARY_PATH=… .venv/bin/python -m unittest discover -s tests -p test_whisper_smoke.py` grün und `python -c "import pyannote.audio, torch; print(torch.cuda.is_available())"` → `True`
- AC: Beide Extras laufen in einer venv; sonst Stopp und Umplanung.

### Chunk 2 — Generischer Kern
- Dateien: `src/transcript/diarization/__init__.py`, `src/transcript/session.py`, `tests/test_diarization.py`, `tests/test_session.py`
- Änderung: `Turn`, `DiarizationResult`; `assign_speakers(reference, result)` (Wortmitte, `majority_speaker`, `labels`, `overlaps` per Sweep); Rohdatei schreiben/lesen mit `format_version`, `matches(...)` für Resume; `SessionPaths.diarization_dir`/`diarization_raw(i)`; `_sha256` aus `audio.py` gemeinsam nutzbar machen.
- Verify: `scripts/check`
- AC: Tests mit synthetischen Turns: Wort an Turngrenze, Wort ohne Turn → `None`, Wort ohne Zeiten → `None`, Gleichstand → Passage `None`, Overlap-Bereiche, nur Sprecherfelder geändert, Rohdatei-Rundlauf, Mismatch je Feld.

### Chunk 3 — pyannote-Adapter
- Dateien: `src/transcript/diarization/pyannote.py`, `tests/test_diarization_pyannote.py`, `tests/test_asr_fake.py`
- Änderung: `PyannoteDiarizer` mit `from_config`, `identity()` (Modell + Revision aus dem Cache, ohne torch), `load()`, `diarize(wav, num_speakers)`, `close()` (`gc.collect`, `torch.cuda.empty_cache`); WAV per `wave` + numpy wie im Spike; Fehlerabbildung OOM → `ResourceError`, Cache fehlt / kein CUDA / Runtime fehlt → `BackendUnavailableError`, Rest → `BackendRuntimeError`. Import-Guard um `pyannote` erweitern.
- Verify: `scripts/check`
- AC: Unit-Tests mit gefälschten Modulen decken Device-Wahl, fehlenden Cache, OOM-Abbildung und die Abbildung von Turns/exklusiven Turns auf ms ab; der Guard hält `pyannote`/`torch` aus generischem Code.

### Chunk 4 — Ablauf und CLI
- Dateien: `src/transcript/diarization/__init__.py`, `src/transcript/__main__.py`, `tests/test_diarization.py`, `tests/test_smoke.py`
- Änderung: `diarize_session(paths, manifest, diarizer, num_speakers, force)` mit lazy `load()`, Wiederverwendung, Überspringen von `failed`/fehlenden Referenzen, Zusammenfassung pro Segment; Subcommand `diarize` mit `--num-speakers`, `--force`, `--config`.
- Verify: `scripts/check`
- AC: Mit Fake-Diarisierer: zweiter Lauf lädt kein Modell, `--force` rechnet neu, geänderter WAV-Hash rechnet neu, Ausgabe enthält nur Zähler und Laufzeiten.

### Chunk 5 — Opt-in-Smoke-Test Ende zu Ende
- Dateien: `tests/test_diarization_smoke.py`
- Änderung: Nur mit `TRANSCRIPT_DIARIZATION_SMOKE=1`, beiden Extras, beiden Modellen im Cache und ffmpeg mit `flite`: zwei erfundene Sätze mit zwei flite-Stimmen → Whisper → `write_reference` → `close()` → `diarize_session` → Wörter mit Label im Referenzformat.
- Verify: `scripts/check` (übersprungen) und `TRANSCRIPT_DIARIZATION_SMOKE=1 LD_LIBRARY_PATH=… .venv/bin/python -m unittest discover -s tests -p test_diarization_smoke.py`
- AC: Eine Session läuft von der Transkription bis zu Wörtern mit Sprecher-Label; zweiter Aufruf nutzt die gespeicherte Diarisierung.

### Chunk 6 — Doku
- Dateien: `README.md`, `docs/referenzformat.md`, `docs/datenschutz.md` (nur falls ein Satz zu Diarisierungsdaten fehlt)
- Änderung: README-Abschnitt „Diarisierung“: Extra, einmaliger Download mit `hf auth login`, Offline-Betrieb, Konfiguration, `transcript diarize`, Hardware, Lizenz mit CC-BY-4.0-Attribution, Smoke-Test. `referenzformat.md`: Rohdatei `diarization/segment-NN.json`, Labels nur pro Segment gültig.
- Verify: `scripts/check`
- AC: Einrichtung und Lauf sind nach README reproduzierbar.

## Folge-Tickets
- `num_speakers` aus dem Wissens-Snapshot statt CLI-Option: TOOL-41 (Hinweis in der Roadmap)
- Labels über mehrere Segmente einer Session zusammenführen: TOOL-68
- Diarisierung im Session-Lauf nach `WhisperBackend.close()` aufrufen: TOOL-17
- Retry bei `ResourceError`/`BackendRuntimeError` der Diarisierung: TOOL-18

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Extra `diarization`, Konfiguration, venv-Gate | no |
| 2 | Generischer Kern: Zuordnung, Rohdatei, Resume-Abgleich | no |
| 3 | pyannote-Adapter mit Unit-Tests | no |
| 4 | `diarize_session` und `transcript diarize` | no |
| 5 | Opt-in-Smoke-Test Ende zu Ende | no |
| 6 | README und Referenzformat-Doku | no |
