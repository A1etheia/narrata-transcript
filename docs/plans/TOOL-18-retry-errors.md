# TOOL-18 — Fehlerbehandlung und Wiederaufnahme der Transkription

## Ziel
Danach übersteht ein mehrstündiger Lauf vorübergehende Fehler: `ResourceError` und `BackendRuntimeError` werden pro Segment höchstens `retries`-mal wiederholt, deterministische Fehler gar nicht. Jeder Fehlversuch steht mit Session, Segment, Backend und Versuch auf stderr. Die Diarisierung markiert ein fehlgeschlagenes Segment und macht mit dem nächsten weiter. Heute wird ein vorübergehender Fehler sofort `failed`, die Konsole zeigt nur die Fehlerklasse, und ein Diarisierungsfehler an einem Segment bricht den ganzen Diarisierungslauf mit Exit 2 ab.

## Ist-Stand
- `src/transcript/asr/backend.py:37-64`: Fehlerklassen. `retryable` ist bei `ResourceError` und `BackendRuntimeError` gesetzt. `:283-299` `_guarded` entfernt die Meldung fremder Exceptions, das Original hängt als `__cause__` daran. `:178-187` `runtime_error` bildet OOM auf `ResourceError` ab.
- `src/transcript/transcription.py:82-148` `transcribe_session`: Wiederverwendung, `failed` läuft weiter, ein Ladefehler lässt Segmente `open`. `:151-189` `_run` ist der Körper pro Segment und die Nahtstelle für den Retry. `:48-65` `SegmentOutcome` hat nur `error` (die Klasse) und `retryable`.
- `src/transcript/diarization/__init__.py:151-215` `diarize_session`: Der Segment-Körper (`:170-211`) hat keinen Fehlerpfad. Ein `BackendError` aus `diarizer.diarize` (`:194`) bricht die Schleife ab. `SegmentSummary.outcome` (`:142`) kennt nur `diarized`, `reused` und `skipped`.
- `src/transcript/diarization/pyannote.py:93-110`: `diarize` liefert `AudioInputError` oder über `runtime_error` `ResourceError`/`BackendRuntimeError`.
- `src/transcript/__main__.py:216-281` `_transcribe` und `:304-325` `_diarize`, beide ohne `_log_to_stderr` (`:355-368`). `_print_outcome` (`:284-301`) druckt `failed: <Klasse> (retryable)`, `_diarize` endet immer mit 0.
- `src/transcript/config.py:27-28`: Schlüssel von `asr` und `diarization`. `:96-114` Parsing über `_positive_number`. `format_config` steht in `:133-160`, die Beispielwerte in `config/example.yaml`.
- `src/transcript/asr/fake.py:21-79`: `FakeBackend` kann eine feste `error` werfen.
- Doku: README „Lauf“ (Wiederaufnahme, Fehlschlag, Exit-Code) und README „Konfiguration“. `docs/asr-backends.md:57-67` „Fehler“ sagt: „Ob und wie oft wiederholt wird, entscheidet TOOL-18.“

## Entscheidungen
- **Keine neuen Fehlerklassen** (Übergabe TOOL-63). Die Ticket-Punkte „Kategorien definieren“ und „Exceptions überführen“ sind mit TOOL-63, TOOL-64 und TOOL-76 schon erledigt. Wiederholt wird genau dann, wenn `error.retryable` gilt.
- **`src/transcript/retry.py`: `attempt(call, retries, on_failure, sleep=time.sleep, delay_s=5.0)`**. Der Helfer ruft `call()` auf, bei einem `BackendError` mit `retryable` bis zu `retries` weitere Male mit fester Pause. Vor jedem Neuversuch und beim endgültigen Fehlschlag ruft er `on_failure(error, attempt, final)` auf und wirft am Ende den letzten Fehler. Nicht wiederholbare Fehler gehen beim ersten Mal durch. Die Pause ist fest, ohne Backoff, und Tests übergeben ein `sleep` ohne Wirkung. Ein eigenes Modul, weil ASR und Diarisierung ihn teilen und er in keinem der beiden Pakete zu Hause ist.
- **Konfiguration:** `asr.retries` und `diarization.retries`, ganze Zahl von 0 bis 5, Default 2. Ein Wert außerhalb ergibt einen `ConfigError`. Die Obergrenze schließt Endlosschleifen aus, und 0 schaltet den Retry ab. Getrennte Werte, weil die beiden Modelle unterschiedlich speicherhungrig sind.
- **Nur Segmentaufrufe werden wiederholt**, nicht `load`. Ein Ladefehler bleibt wie bisher: Die Segmente bleiben `open` (ASR) bzw. der Lauf endet mit Exit 2 (Diarisierung). Fehlt ein Modell oder eine GPU, wiederholt man das nicht sinnvoll im selben Prozess.
- **`SegmentOutcome`** bekommt `message` (die bereinigte Meldung des `BackendError`) und `attempts`. Die CLI-Zeile wird zu `failed after 3 attempt(s): ResourceError (retryable): faster-whisper: …`. Die Meldungen sind laut TOOL-63 und TOOL-64 schon frei von Text und Keywords, das Original aus `__cause__` erscheint nie.
- **Protokollierung:** `logging.getLogger("transcript.transcription")` bzw. `"transcript.diarization"`, jeweils mit einem `WARNING` pro Fehlversuch: `<session> segment <n>: <backend> attempt <k>/<max> failed: <Klasse>: <Meldung>`, dazu `retrying in 5 s` oder `giving up`. Nie mit `exc_info`, denn der Traceback würde `__cause__` mit Runtime-Text zeigen. Die Ausgabe geht nur über `_log_to_stderr` an die Konsole, eine Logdatei gibt es nicht. Dauerhaft bleibt der Fehler als `status: failed` in der Referenzdatei.
- **Diarisierung pro Segment:** Den Segment-Körper aus `diarize_session` als `_diarize_segment` herauslösen (Übergabe TOOL-76). Ein endgültiger `BackendError` macht daraus `SegmentSummary(outcome="failed", reason=<Klasse>, message=…)`, und die Schleife geht weiter. Es wird nichts geschrieben: Die vorhandene Rohform und die Labels bleiben, und der nächste Lauf versucht es ohne `--force` erneut, weil keine passende Rohform existiert. `transcript diarize` endet mit 1, wenn ein Segment `failed` ist. Bei `transcript transcribe` führt ein Diarisierungsfehler ebenfalls zu 1.
- **Resume und Force** bleiben unverändert. Die AK sind erfüllt, sie bekommen nur Tests, die das Verhalten mit Retry absichern.

## Daten-Check
- Fehlermeldungen und Logs: handled. Sie nennen Session-Key, Segment, Backend, Fehlerklasse und die bereinigte Meldung (Backend, Aktion, Exception-Typ, Audiopfad). Nie `exc_info` oder `__cause__`. Ein Test mit `FakeBackend`, dessen Original-Exception `SECRET` trägt, prüft, dass `SECRET` weder in stdout noch in stderr noch im Log steht.
- Arbeitsdateien: handled. Am Format ändert sich nichts, `failed` steht wie bisher unter `work/` (gitignored).
- Fixtures: handled. Nur `FakeBackend`, Fake-Diarizer und erfundene Daten.
- Rohaudio: N/A, es wird nur gelesen, wie bisher.

## Contract-Check
N/A. Nur interne Arbeitsdateien und die Konsole, Export und Narrata-Endpoint sind nicht berührt.

## Resume-Check
- Abbruch: handled. Ein Retry schreibt erst nach dem letzten Versuch, ein Abbruch mitten im Retry lässt das Segment so, wie es vorher war.
- Wiederverwendung: handled. Die Regel `_reusable` bleibt unverändert, `failed` wird ohne `--force` erneut versucht, `transcribed` nur mit `--force`. Tests decken das mit Retry ab.
- Gleiches Modell, gleicher Snapshot: handled. Ein Retry nutzt dasselbe geladene Backend, also dasselbe Modell und dieselben Settings. Einen Snapshot gibt es noch nicht (TOOL-41).

## Dependency-Check
N/A. Kein neues Paket, kein neues Modell.

## Format-Check
- Referenzformat: N/A. `error.category` und `retryable` bleiben, die Zahl der Versuche wird nicht gespeichert, `format_version: 1` bleibt.
- Diarisierungs-Rohform: N/A, unverändert.
- Konfiguration: handled. Sie hat keine Versionsnummer. Die neuen Schlüssel sind optional mit Default, alte Dateien bleiben gültig.

## Chunks
### Chunk 1 — Retry-Helfer und Konfiguration
- Dateien: `src/transcript/retry.py`, `src/transcript/config.py`, `config/example.yaml`, `tests/test_retry.py`, `tests/test_config.py`
- Änderung: `attempt(...)`. `asr.retries` und `diarization.retries` (0–5, Default 2) in `Config`, `load_config` und `format_config`.
- Verify: `scripts/check`
- AC: Ein wiederholbarer Fehler wird höchstens `retries`-mal wiederholt und gelingt beim zweiten Versuch. Ein nicht wiederholbarer läuft genau einmal. Nach dem letzten Versuch kommt der letzte Fehler heraus. `on_failure` sieht jeden Versuch. `retries: 6`, `-1` und `true` ergeben `ConfigError`.

### Chunk 2 — Retry und Protokoll im Session-Lauf
- Dateien: `src/transcript/transcription.py`, `tests/test_transcription.py`, ggf. `src/transcript/asr/fake.py` (Fehlerfolge statt einer festen `error`)
- Änderung: `transcribe_session(..., retries=0, sleep=…)`. `_run` ruft `transcribe` über `attempt` auf. `SegmentOutcome.message` und `.attempts`. Ein `WARNING`-Log pro Fehlversuch mit Session, Segment, Backend und Versuch.
- Verify: `scripts/check`
- AC: Tests mit `FakeBackend`:
  - Erst `ResourceError`, dann Erfolg → `transcribed`, `attempts == 2`, `load_calls == 1`.
  - `AudioInputError` → `failed` nach einem Versuch.
  - `retries` erschöpft → `failed` mit `attempts == retries + 1`, Segment 3 läuft trotzdem.
  - Der Log nennt Key, Segment und Backend, `SECRET` aus `__cause__` steht nirgends.
  - Ein späterer Lauf versucht `failed` erneut und verwendet `transcribed` wieder.

### Chunk 3 — Diarisierung pro Segment
- Dateien: `src/transcript/diarization/__init__.py`, `tests/test_diarization.py`
- Änderung: `_diarize_segment` herauslösen. `diarize_session(..., retries=0, sleep=…)`. Outcome `failed` mit Klasse und Meldung, Log wie in Chunk 2, die Schleife läuft weiter.
- Verify: `scripts/check`
- AC: Ein Fehler in Segment 1 lässt Segment 2 diarisieren. Rohform und Labels von Segment 1 bleiben unverändert. Erst Fehler, dann Erfolg ergibt `diarized`. Ein nicht wiederholbarer Fehler wird nicht wiederholt. `close` läuft immer.

### Chunk 4 — CLI
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`
- Änderung: `retries` aus der Konfiguration übergeben. `_transcribe` und `_diarize` laufen unter `_log_to_stderr`. Die Zeile `failed` zeigt Versuche, Klasse und Meldung. `_print_diarization` zeigt `failed`. Exit 1 bei `failed` in der Diarisierung.
- Verify: `scripts/check`
- AC: Tests mit gepatchtem `from_config`: Ein vorübergehender Fehler endet mit Exit 0 und einem `WARNING` mit Session und Segment auf stderr. Ein endgültiger endet mit Exit 1 und einer verständlichen Zeile. `diarize` mit einem fehlgeschlagenen Segment endet mit Exit 1. Kein `SECRET` auf der Konsole.

### Chunk 5 — Doku
- Dateien: `README.md` („Lauf“, „Diarisierung“, „Konfiguration“), `docs/asr-backends.md` („Fehler“), `docs/transcript-roadmap.py` und `.md` (Hinweis TOOL-18 als erledigt kommt mit `/close-ticket`, hier nur Hinweise an Folgetickets)
- Änderung: Retry-Regel, `retries`, das Protokoll auf stderr und Exit 1 der Diarisierung dokumentieren. Den Satz „entscheidet TOOL-18“ durch die Regel ersetzen.
- Verify: `scripts/check`
- AC: Das README erklärt, was bei einem vorübergehenden und bei einem dauerhaften Fehler passiert und wie man `failed` erneut versucht.

## Folge-Tickets
- Protokoll in eine Datei unter `work/<session>/`: TOOL-77 (Epic TOOL-54, zusammen mit TOOL-57 entwerfen).
- Zahl der Versuche im Referenzformat speichern: TOOL-78 (Epic TOOL-54), umsetzen nur, wenn TOOL-59 Fehlerraten auswerten will.
- Retry beim Laden des Modells: [kein Ticket: Ladefehler sind fehlendes Modell, Runtime oder GPU, ein Retry im selben Prozess hilft nicht]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Retry-Helfer, Konfiguration | no |
| 2 | Retry und Protokoll in `transcribe_session` | no |
| 3 | Diarisierung pro Segment mit Retry | no |
| 4 | CLI: Logging, Ausgabe, Exit-Codes | no |
| 5 | Doku | no |
