# ASR-Backends

Die Pipeline ruft lokale Spracherkennung nur über die Schnittstelle in `transcript.asr` auf (TOOL-63). Welches Modell dahinter läuft, steckt im Adapter. Konfidenzbewertung, Review und Export sehen nur die gemeinsamen Typen. Die Modellwahl für V0.1 steht in [`docs/spikes/TOOL-62-asr-vergleich.md`](spikes/TOOL-62-asr-vergleich.md).

## Ablauf

```python
from transcript.asr import TranscriptionRequest, opened, transcribe

with opened(backend):                      # load() einmal, close() immer
    for segment in manifest.segments:
        request = TranscriptionRequest(
            audio=paths.audio_dir / segment.file,
            language="de",
            keywords=hints,                # Begriffe aus dem Wissens-Snapshot
        )
        result = transcribe(backend, request)
```

- **`opened(backend)`** lädt Modell und Runtime einmal für viele Segmente und schließt immer, auch nach einem Fehler. Ein Modell zu laden dauert und belegt die GPU, bei Whisper turbo bis 10,5 GB RAM über 5 h.
- **`transcribe(backend, request)`** prüft, ob die Audiodatei existiert, ruft das Backend und prüft das Ergebnis. Was dort ankommt, ist immer ein `BackendError`.
- Gerät, Modellvariante und Inferenzparameter gibt man dem Adapter beim Erzeugen mit, nicht im Request.

## Ergebnis

`BackendResult` ist die Antwort für ein Segment. Es ist flüchtig und kein gespeichertes Format. Gespeichert wird es über `transcript.reference` im versionierten Referenzformat, Roh- und Normalform getrennt, siehe [`referenzformat.md`](referenzformat.md).

| Feld | Inhalt |
| --- | --- |
| `info` | `backend_id`, `model`, `model_version`, `runtime_version`. Damit lässt sich beim Resume prüfen, ob dasselbe Modell gelaufen ist |
| `segments` | `ResultSegment`s mit `text`, `start`/`end`, `words`, `speaker`, `signals` |
| `words` | `ResultWord`s mit `text`, `start`/`end`, `confidence` (0–1) |
| `language`, `language_probability` | erkannte oder vorgegebene Sprache |
| `keywords_used` | die Begriffe, die tatsächlich gewirkt haben, nach jeder Kürzung |
| `settings` | Inferenzparameter des Laufs |
| `raw` | die unveränderte Antwort des Backends, JSON-fähig |

Zeiten sind Sekunden, lokal zum Segment-WAV, so wie Backends sie liefern. In Session-Zeit rechnet sie `Segment.to_absolute_ms` um. `speaker` ist ein generisches Label des Backends, nie ein Name. Die Confidence-Skalen der Modelle unterscheiden sich (Mittel 0,86 bei Whisper, 0,22 bei Parakeet). Vergleichbar ist nur die Rangfolge innerhalb eines Modells.

## Fähigkeiten

Jedes Backend deklariert `Capabilities`. `capabilities.to_dict()` liefert sie als JSON.

| Feld | Bedeutung |
| --- | --- |
| `word_timestamps`, `segment_timestamps` | Zeiten pro Wort bzw. Segment |
| `speaker_labels` | Sprecher-Labels im Ergebnis |
| `keyword_biasing` | Begriffe aus dem Request beeinflussen die Erkennung |
| `word_confidence` | Confidence pro Wort |
| `segment_signals` | Signale pro Segment, etwa `avg_logprob` |
| `devices` | `cpu`, `cuda` |
| `max_audio_seconds` | längste Eingabe pro Aufruf; `None` heißt ganze Aufnahmen |

**Eine fehlende Fähigkeit ist kein Fehler.** Die passenden Felder bleiben `None` oder leer. Keywords an ein Backend ohne Biasing werden ignoriert, `keywords_used` bleibt leer. Nur ein Schritt, der ohne eine Fähigkeit nicht arbeiten kann, ruft `capabilities.require("…")` und bekommt sonst `UnsupportedCapabilityError`.

## Fehler

| Klasse | Wann | `retryable` |
| --- | --- | --- |
| `AudioInputError` | Audio fehlt, ist unlesbar oder hat ein falsches Format | nein |
| `BackendUnavailableError` | Modell, Runtime oder Gerät fehlt | nein |
| `ResourceError` | Speicher oder GPU erschöpft | ja |
| `BackendRuntimeError` | unerwarteter Fehler im Backend, ungültiges Ergebnis | ja |
| `UnsupportedCapabilityError` | ein Schritt braucht eine nicht deklarierte Fähigkeit | nein |

`retryable` sagt nur, ob derselbe Aufruf später gelingen kann. Ob und wie oft wiederholt wird, entscheidet TOOL-18. Fremde Exceptions macht `transcribe` zu `BackendUnavailableError` (`ImportError`), `ResourceError` (`MemoryError`) oder `BackendRuntimeError`. Die Message nennt dann nur Backend und Exception-Typ, das Original hängt als `__cause__` daran. Runtime-Meldungen können Hotwords oder Transkripttext enthalten.

## Regeln für Adapter

- **Modellbibliothek erst in `load()` importieren.** Ein Test hält `faster_whisper`, `ctranslate2`, `nemo`, `torch` und `transformers` aus allem generischen Code heraus und in Adaptern aus der Modulebene.
- **Eigene Fehler selbst abbilden,** zum Beispiel CUDA-OOM auf `ResourceError` und fehlende Gewichte auf `BackendUnavailableError`. Die Hülle fängt nur, was durchrutscht.
- **Kein Text in Messages oder Logs.** Transkripttext und `raw` gehen höchstens über `transcript_logger` (`src/transcript/debug_log.py`) in den Debug-Log unter `work/`, siehe [`docs/datenschutz.md`](datenschutz.md).
- **`keywords_used` ehrlich setzen.** Kürzt die Runtime die Liste, stehen dort nur die übrigen Begriffe. Ohne `keyword_biasing` bleibt das Feld leer, sonst lehnt `transcribe` das Ergebnis ab.
- **Fähigkeiten so deklarieren, wie der Adapter sie wirklich liefert,** nicht so, wie das Modell sie könnte.

## Abbildung der Kandidaten

Grundlage sind die Spike-Runner `scripts/spike/run_whisper.py` und `run_parakeet.py`. Den Whisper-Adapter baut TOOL-64. Parakeet ist der Fallback und zeigt, dass ein zweites Backend ohne Änderung der Schnittstelle passt.

| | faster-whisper (V0.1) | Parakeet TDT 0.6B v3 (NeMo) |
| --- | --- | --- |
| `word_timestamps`, `segment_timestamps` | ja | ja |
| `speaker_labels` | nein (Diarisierung separat, TOOL-76) | nein |
| `keyword_biasing` | ja, `hotwords`; gekürzt auf 223 Tokens | nein |
| `word_confidence` | ja, `word.probability` | ja, `word_confidence` (eigene Skala) |
| `segment_signals` | ja: `avg_logprob`, `no_speech_prob`, `compression_ratio` | nein |
| `devices` | `cpu`, `cuda` | `cuda` (im Spike nur so getestet) |
| `max_audio_seconds` | `None`, 5 h am Stück | 300, braucht dann eigene Segmentierung (TOOL-11) |
| `raw` | Segmente und Wörter aus `model.transcribe` | Hypothesen mit `timestamp["word"/"segment"]` |
