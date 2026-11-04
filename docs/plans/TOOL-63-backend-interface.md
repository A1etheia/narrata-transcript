# TOOL-63 — Gemeinsame Schnittstelle für Transkriptions-Backends

Branch `tool-63-backend-interface` steht (`--no-track`, kein Upstream), TOOL-63 ist In Progress. Nach der Freigabe: diesen Plan als `docs/plans/TOOL-63-backend-interface.md` committen (`docs(plans): plan transcription backend interface (TOOL-63)`), dann die Chunks.

**Abhängigkeiten (`/check-ticket-deps`):** Es gibt keine Blocked-by-Links. TOOL-62 (Evaluation, Prosa-Abhängigkeit) ist Done. Downstream steht TOOL-64 auf To Do. Zwei Findings, beide entschieden:
- AK „Das ausgewählte V0.1-Backend implementiert die Schnittstelle“ wandert nach TOOL-64, das dasselbe AK schon trägt. TOOL-63 belegt die Schnittstelle mit dem Fake-Backend und einer Abbildungstabelle für faster-whisper und Parakeet.
- Fehlerkategorien: TOOL-63 definiert die Klassen samt `retryable`-Flag und verpflichtet die Adapter, darauf abzubilden. TOOL-18 baut Retry, Resume, Force und Protokollierung darauf auf.

## Ziel
Danach ruft die Pipeline ein lokales ASR-Backend über eine dokumentierte Schnittstelle auf: Laden, Fähigkeiten abfragen, ein Segment transkribieren, ein einheitliches Ergebnis und einheitliche Fehler erhalten. Dafür braucht sie weder faster-whisper noch NeMo. Ein Fake-Backend erlaubt Tests von TOOL-15/17/18 ohne Modell. Heute gibt es Backend-Code nur als Wegwerf-Skripte in `scripts/spike/`, jedes mit eigenem Ausgabeformat.

## Ist-Stand
- `scripts/spike/run_whisper.py:8` und `:23-46`: Einstellungen von faster-whisper und die Rohform pro Segment (`start`, `end`, `text`, `signals{avg_logprob, no_speech_prob, compression_ratio}`, `words[{start, end, word, confidence}]`). Diese Form ist die Vorlage für das Backend-Ergebnis.
- `scripts/spike/run_parakeet.py:34-59`: dieselbe Form aus NeMo, aber ohne Segment-Signale, nur in 300-s-Blöcken (`:73`), ohne Biasing (`:74`).
- `scripts/spike/README.md`, Tabelle „Einstellungen“: Whisper kürzt `hotwords` auf 223 Tokens. Was hinten steht, fällt still weg.
- `docs/spikes/TOOL-62-asr-vergleich.md:93-111`: Zeiten liefern Whisper und Parakeet, Granite nicht. Confidence liefern Whisper und Parakeet. Sprecher liefert keines der Modelle.
- `src/transcript/manifest.py:51` `Segment.to_absolute_ms(local_seconds)` und `src/transcript/timecode.py:51` `seconds_to_ms` nehmen segmentlokale Sekunden „as ASR backends report it“.
- Fehlermuster: `src/transcript/audio_tools.py:18` und `src/transcript/config.py:21`: eine Exception pro Modul, die Message ist für die Nutzerin gedacht. `src/transcript/jsonfile.py:1-4`: Messages nennen nie Feldwerte.
- `src/transcript/debug_log.py:13` `transcript_logger` ist der einzige Weg, auf dem Transkripttext in ein Log kommt.
- Tests mit `unittest` unter `tests/`, Stil wie `tests/test_timecode.py`. `pyproject.toml`: Python ≥ 3.10, als Laufzeitabhängigkeit nur `pyyaml`.

## Entscheidungen
- **Paket `src/transcript/asr/`.** `backend.py` enthält Protokoll, Datentypen, Fehler und die Aufruf-Hülle, `fake.py` das Fake-Backend, `__init__.py` re-exportiert die öffentliche API. TOOL-64 legt `asr/whisper.py` daneben und importiert faster-whisper erst in `load()`. Grund: Generischer Code importiert nur `transcript.asr`.
- **`typing.Protocol` statt ABC.** Adapter müssen nicht erben, das Fake braucht keine Basisklasse. `Backend` hat `info: BackendInfo`, `capabilities: Capabilities`, `load()`, `transcribe(request) -> BackendResult`, `close()` und funktioniert als Kontextmanager über eine Hilfsfunktion `opened(backend)`. Grund: Laden dauert und belegt VRAM (TOOL-62: 10,5 GB), deshalb wird einmal geladen und mehrere Segmente laufen durch.
- **`Capabilities` als frozen Dataclass:** `word_timestamps`, `segment_timestamps`, `speaker_labels`, `keyword_biasing`, `word_confidence`, `segment_signals` (bool), `devices: frozenset[str]` (`"cpu"`, `"cuda"`), `max_audio_seconds: float | None` (Parakeet: 300, braucht dann TOOL-11). `to_dict()` liefert JSON-fähige Werte, damit sind die Fähigkeiten maschinenlesbar.
- **Fehlende Fähigkeit ist kein Fehler.** Felder bleiben `None` bzw. leer. Nur `require(capabilities, name)` wirft `UnsupportedCapabilityError`, und zwar für Schritte, die eine Fähigkeit zwingend brauchen. Keywords an ein Backend ohne Biasing werden ignoriert, das Ergebnis meldet `keywords_used=()`. Grund: AK „ohne sie allen Backends aufzuzwingen“. Der Parakeet-Spike brach in diesem Fall ab (`run_parakeet.py:75`).
- **`TranscriptionRequest`:** `audio: Path` (16-kHz-Mono-WAV aus dem Manifest), `language: str | None`, `keywords: tuple[str, ...] = ()`. Gerät, Modell und Inferenzparameter sind Konstruktor-Optionen des Adapters (TOOL-64), sie gehören nicht in den Request.
- **`BackendResult` ist flüchtig, kein gespeichertes Format.** Es enthält `info`, `language`, `language_probability | None`, `segments: tuple[ResultSegment, ...]` mit `start`/`end` als segmentlokalen Sekunden, `text`, `speaker: str | None`, `signals: Mapping[str, float]`, `words: tuple[ResultWord(start, end, text, confidence | None)]`, außerdem `settings: Mapping`, `keywords_used: tuple[str, ...]` (was nach Kürzung wirklich wirkte) und `raw: Any` (die unveränderte Backend-Antwort, JSON-fähig). Grund: TOOL-16 kommt danach, definiert das versionierte Format und speichert Roh- und Normalform getrennt. Sekunden statt ms, weil `Segment.to_absolute_ms` Sekunden nimmt.
- **`BackendInfo`:** `backend_id`, `model`, `model_version | None`, `runtime_version | None`. TOOL-17 kann beim Resume damit prüfen, ob dasselbe Modell läuft.
- **Fehler:** Basis `BackendError(Exception)` mit Klassenattribut `retryable: bool`. Unterklassen: `AudioInputError` (Eingabe defekt oder falsches Format, nicht wiederholbar), `BackendUnavailableError` (Modell oder Runtime fehlt, nicht wiederholbar), `ResourceError` (OOM, GPU belegt, wiederholbar), `BackendRuntimeError` (unerwarteter Laufzeitfehler, wiederholbar), `UnsupportedCapabilityError` (nicht wiederholbar). Ob und wie oft wiederholt wird, entscheidet TOOL-18.
- **Aufruf-Hülle `transcribe(backend, request)`** im generischen Code. Sie prüft, ob die Datei existiert, ruft das Backend und gibt `BackendError` unverändert weiter. Jede andere Exception wird zu `BackendRuntimeError("<backend_id>: <ExceptionType>")` mit `__cause__`, ohne die Original-Message. Danach prüft sie das Ergebnis: Zeiten ≥ 0, `start ≤ end`, Confidence in [0, 1]. Grund: AK „nicht ungefiltert weitergereicht“. Runtime-Messages könnten Hotwords oder Text enthalten.
- **Kein Registry und keine Config in TOOL-63.** Auswahl und Konfiguration des Backends macht TOOL-64 mit nur einem echten Backend. Ein Registry für ein einziges Backend wäre Vorrat.
- **Doku `docs/asr-backends.md`** (Deutsch): Schnittstelle, Fähigkeiten, Fehlerkategorien, Regeln für Adapter, Abbildungstabelle faster-whisper/Parakeet auf Capabilities und Ergebnis. Dazu ein Link aus dem README.

## Daten-Check
- Folgt TOOL-66: handled. Das Modul schreibt nichts auf die Platte und loggt keinen Text. `raw` und `text` darf ein Adapter nur über `transcript_logger` (`debug_log.py:13`) ausgeben. Diese Regel steht in der Adapter-Doku.
- Fehlermeldungen: handled. Die Hülle verwirft die Messages fremder Exceptions und nennt nur Backend-ID und Typ. Die eigenen Fehler nennen Pfad und Backend, nie Text oder Keywords.
- Fixtures: handled. Das Fake-Backend und die Tests nutzen erfundene Sätze und Keywords („Drachenhort“, „Beispielfigur“), das Audio entsteht synthetisch über `tests/media.py`. Echte Daten kommen nicht ins Repo.
- Logs: handled. Es gibt höchstens INFO mit Backend-ID, Segmentdauer und Wortanzahl.

## Contract-Check
N/A, weil weder Contract-JSON (IOA-1214) noch der Narrata-Endpoint gelesen oder geschrieben werden. Das Backend-Ergebnis ist intern und flüchtig. Eine Narrata-Änderung ist nicht nötig, es gibt kein IOA-Ticket.

## Resume-Check
- Abbruch: N/A in TOOL-63. Die Schnittstelle transkribiert ein Segment und speichert nichts. Resume pro Segment kommt mit TOOL-17 und TOOL-18.
- Wiederverwendung: handled als Vorleistung. Das Ergebnis trägt `BackendInfo` und `settings`, so kann TOOL-17 fertige Segmente einem Modell zuordnen.
- Gleiches Modell und gleicher Snapshot: handled als Vorleistung. `model`/`model_version` stehen in `BackendInfo`, `keywords_used` zeigt, welche Begriffe aus dem Wissens-Snapshot gewirkt haben. Die Prüfung beim Resume macht TOOL-17.

## Dependency-Check
N/A, weil keine Abhängigkeit hinzukommt: `dataclasses`, `typing.Protocol` und `pathlib` gehören zur Standardbibliothek. faster-whisper kommt erst mit TOOL-64.

## Format-Check
N/A, weil kein internes Format mit Versionsfeld entsteht oder sich ändert. `BackendResult` wird nicht gespeichert, das versionierte Format kommt mit TOOL-16.

## Chunks
### Chunk 1 — Schnittstelle, Datentypen, Fehler
- Dateien: `src/transcript/asr/__init__.py`, `src/transcript/asr/backend.py`, `tests/test_asr_backend.py`
- Änderung: `Backend` (Protocol), `opened()`, `Capabilities` mit `to_dict()`, `require()`, `BackendInfo`, `TranscriptionRequest`, `BackendResult`/`ResultSegment`/`ResultWord`, die Fehlerhierarchie mit `retryable`.
- Verify: `scripts/check`
- AC: `Capabilities.to_dict()` lässt sich mit `json.dumps` serialisieren und enthält alle Felder. `require` wirft nur bei einer fehlenden Fähigkeit. Jede Fehlerklasse hat das erwartete `retryable`. Ein `ResultWord` ohne Confidence ist gültig.

### Chunk 2 — Fake-Backend, Aufruf-Hülle, Importgrenze
- Dateien: `src/transcript/asr/fake.py`, `src/transcript/asr/backend.py`, `tests/test_asr_fake.py`
- Änderung: `FakeBackend(result | callable, capabilities=…, error=…)` merkt sich Requests und Lade-/Schließ-Aufrufe, ignoriert Keywords ohne `keyword_biasing` und kann einen konfigurierten Fehler werfen. `transcribe(backend, request)` prüft die Eingabe, filtert Exceptions und validiert das Ergebnis. Ein Test durchsucht `src/transcript/` (ohne künftige Adapter-Module in `asr/`) per `ast` nach Importen von `faster_whisper`, `nemo`, `torch`, `transformers` und `ctranslate2`.
- Verify: `scripts/check`
- AC: Ein Fake-Lauf ohne Modell liefert das erwartete Ergebnis. `ValueError("geheimer Text")` aus dem Backend kommt als `BackendRuntimeError` an, ohne den Text in `str()`, und mit `__cause__`. Ein `ResourceError` geht unverändert durch. Keywords ohne Biasing ergeben `keywords_used == ()`, keinen Fehler. Eine negative Zeit oder eine Confidence über 1 führt zu `BackendRuntimeError`. Eine fehlende Audiodatei führt zu `AudioInputError`.

### Chunk 3 — Doku
- Dateien: `docs/asr-backends.md`, `README.md`
- Änderung: Schnittstelle und Ablauf (`opened` → `transcribe` pro Segment), Capability-Tabelle, Fehlerkategorien mit `retryable`, Adapter-Regeln (Import erst in `load()`, Fehler abbilden, Text nur über `transcript_logger`, `keywords_used` nach Kürzung ehrlich setzen), Abbildungstabelle faster-whisper und Parakeet (Parakeet: `max_audio_seconds=300`, `keyword_biasing=False`, `segment_signals=False`). README bekommt einen Abschnitt mit Link, und „Nächste Schritte“ wird angepasst.
- Verify: `scripts/check`, die Tabelle von Hand gegen `run_whisper.py`/`run_parakeet.py` gelesen.
- AC: Alle ACs von TOOL-63 sind belegt, das V0.1-AK ist an TOOL-64 übergeben.

## Folge-Tickets
- TOOL-64: Übernimmt das AK „V0.1-Backend implementiert die Schnittstelle“. Das Backend als `transcript/asr/whisper.py` umsetzen, faster-whisper erst in `load()` importieren, CUDA-OOM auf `ResourceError` und fehlendes Modell auf `BackendUnavailableError` abbilden, `keywords_used` nach der 223-Token-Kürzung setzen. Kommentar ans Ticket beim Abschluss.
- TOOL-18: Die Fehlerklassen und `retryable` stehen in `transcript.asr`. TOOL-18 ergänzt Retry, Resume, Force und die Protokollierung, aber keine neuen Kategorien ohne Grund. Kommentar ans Ticket beim Abschluss.
- TOOL-16: `BackendResult` ist die Eingabe des Adapters ins interne Format. `raw` wird getrennt gespeichert, Zeiten sind segmentlokale Sekunden. Kommentar ans Ticket beim Abschluss.
- TOOL-63: Kommentar, dass das V0.1-AK nach TOOL-64 verschoben ist. [kein Ticket: Kommentar an diesem Ticket, Teil von /close-ticket]
- [kein Ticket: Backend-Registry und Config-Auswahl erst, wenn es ein zweites echtes Backend gibt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schnittstelle, Datentypen, Fehler | no |
| 2 | Fake-Backend, Aufruf-Hülle, Importgrenze | no |
| 3 | Doku `docs/asr-backends.md`, README | no |
