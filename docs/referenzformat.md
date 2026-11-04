# Referenztranskript-Format

Das Referenztranskript ist das interne, versionierte Ergebnis der Spracherkennung für ein Segment, also für eine Aufnahme laut Manifest (TOOL-16). Konfidenzbewertung, Review und Export lesen nur dieses Format und müssen nicht wissen, welches Backend gelaufen ist. Code: `src/transcript/reference.py`.

## Dateien

Pro Segment gibt es zwei Dateien unter `work/<gruppe>/<ordinal>/asr/`:

| Datei | Inhalt |
| --- | --- |
| `segment-NN.json` | Normalform, `format_version: 1` |
| `segment-NN.raw.json` | `{"backend_id": …, "raw": …}`: die Antwort des Backends, unverändert |

`NN` ist der Segmentindex aus dem Manifest, wie bei `audio/segment-NN.wav`. Geschrieben wird zuerst die Rohform, dann die Normalform, beide atomar. Erst die Normalform markiert ein Segment als fertig. Bricht ein Lauf dazwischen ab, liegt höchstens eine Rohdatei ohne Normalform da, und das Segment gilt als nicht transkribiert.

```python
from transcript.reference import from_backend_result, load_reference, write_reference

result = transcribe(backend, request)
reference = from_backend_result(result, backend, manifest, segment, elapsed_ms=…)
write_reference(paths, reference, result.raw)

reference = load_reference(paths, segment.index)   # ohne Backend
```

Schlägt ein Segment fehl, hält `failed_reference(error, backend, manifest, segment)` das fest.

## Normalform

| Feld | Pflicht | Inhalt |
| --- | --- | --- |
| `format_version` | ja | `1` |
| `session` | ja | `group`, `ordinal`; muss zum Pfad passen |
| `play_session_id` | ja | aus dem Manifest |
| `segment` | ja | `index`, `file` (WAV-Name), `source_sha256` der Originalaufnahme |
| `status` | ja | `transcribed` oder `failed` |
| `error` | bei `failed` | `category` (Name der Fehlerklasse, z. B. `ResourceError`), `retryable`; nie die Message |
| `asr` | ja | siehe unten |
| `processing` | ja | `pipeline_version`, `processed_at` (ISO 8601 mit Offset), `elapsed_ms` oder `null` |
| `diarization` | nein | `null` oder siehe unten |
| `raw_file` | ja | Name der Rohdatei |
| `passages` | ja | Liste der Passagen, bei `failed` leer |

**`asr`:** `backend_id`, `model`, `model_version`, `runtime_version`, `capabilities` (wie `Capabilities.to_dict()`), `settings` (Inferenzparameter), `language`, `language_probability`, `keywords_used` (die Begriffe, die tatsächlich gewirkt haben). Nur `backend_id` und `model` sind Pflicht, alles andere darf `null` oder leer sein.

**Passage:** ein Stück Sprache, so wie das Backend es abgegrenzt hat, bei Whisper ein Segment der Ausgabe. Felder: `index` (fortlaufend ab 1), `text` (wie erkannt), `start_ms`, `end_ms`, `speaker`, `signals` (Zahlen pro Passage, z. B. `avg_logprob`), `words`.

**Wort:** `text`, `start_ms`, `end_ms`, `confidence` (0–1), `speaker`.

Optional sind die Zeiten, die Confidence und der Sprecher, jeweils `null`. Ein Backend ohne Zeiten wie Granite liefert Passagen nur mit Text, ein Backend ohne Wörter liefert leere `words`. Das Format verlangt keine Felder eines bestimmten Backends.

## Regeln

- **Zeiten sind ganze Millisekunden, lokal zum Segment-WAV.** Absolute Session-Zeiten werden nicht gespeichert, sondern über `Segment.to_absolute_ms` aus dem Manifest berechnet (TOOL-19). Dadurch bleiben sie richtig, wenn das Manifest neu gebaut wird. Es gilt `start_ms ≤ end_ms`, und kein Wert ist negativ.
- **Der Text wird nie korrigiert.** `text` steht so da, wie das Backend ihn geliefert hat, einschließlich führender Leerzeichen. `ReferenceTranscript.text` fügt die Passagen für die Anzeige zusammen. Gespeichert wird dieser Gesamttext nicht.
- **Confidence-Skalen sind modellabhängig** (siehe [`asr-backends.md`](asr-backends.md)). Vergleichbar ist nur die Rangfolge innerhalb eines Modells. Welches Modell gelaufen ist, steht in `asr`.
- **Rohform und Normalform sind getrennt.** `raw` steht nur in der Rohdatei. Die Normalform enthält nichts, was nur ein bestimmtes Backend versteht.

## Sprecher

Sprecher kommen aus einer separaten Diarisierung mit pyannote (TOOL-76, Grundlage [`spikes/TOOL-20-diarisierung.md`](spikes/TOOL-20-diarisierung.md)):

- **Das Wort-Label ist maßgeblich.** `null` ist ein gültiger Wert: Im Test lagen 6–14 % der Wörter in keinem Turn.
- **`speaker` einer Passage** ist das Label, das die meisten ihrer Wörter tragen (`majority_speaker`). Bei Gleichstand oder ohne Wort-Labels ist es `null`. Liefert ein Backend nur ein Label pro Passage, wird dieses übernommen. Wechsel innerhalb einer Passage bleiben an den Wörtern sichtbar.
- **Labels sind generisch** (`SPEAKER_00`), nie Namen. Die Zuordnung zu Personen gehört zu TOOL-68 und kommt nicht in diese Datei.
- **`diarization`** hält die Metadaten getrennt von `asr`: `backend_id`, `model`, `model_version`, `settings`, `num_speakers` (die Vorgabe, nicht das Ergebnis), `labels` (alle Labels des Segments) und `overlaps` (`[{start_ms, end_ms}]`, Bereiche mit Übersprechen). Ist es gesetzt, darf kein Wort und keine Passage ein Label außerhalb von `labels` tragen.

## Versionierung

`format_version` steht an erster Stelle. `load_reference` lehnt jede andere Version ab und verlangt, das Segment neu zu transkribieren. Eine Änderung, die alte Dateien unlesbar macht, erhöht die Version. Fehlermeldungen beim Laden nennen Datei, Feld und Passagennummer, nie Text, Keywords oder Labels.

## Beispiel

Erfundener Inhalt, gekürzt auf eine Passage:

```json
{
  "format_version": 1,
  "session": {"group": "beispielgruppe", "ordinal": 42},
  "play_session_id": 4711,
  "segment": {"index": 1, "file": "segment-01.wav", "source_sha256": "abab…"},
  "status": "transcribed",
  "error": null,
  "asr": {
    "backend_id": "faster-whisper",
    "model": "large-v3-turbo",
    "model_version": null,
    "runtime_version": "1.1.0",
    "capabilities": {"word_timestamps": true, "segment_timestamps": true, "speaker_labels": false, "keyword_biasing": true, "word_confidence": true, "segment_signals": true, "devices": ["cpu", "cuda"], "max_audio_seconds": null},
    "settings": {"beam_size": 5},
    "language": "de",
    "language_probability": 1.0,
    "keywords_used": ["Drachenhort"]
  },
  "processing": {"pipeline_version": "0.0.1", "processed_at": "2026-11-04T20:00:00+01:00", "elapsed_ms": 812000},
  "diarization": {
    "backend_id": "pyannote",
    "model": "speaker-diarization-community-1",
    "model_version": null,
    "settings": {},
    "num_speakers": null,
    "labels": ["SPEAKER_00", "SPEAKER_01"],
    "overlaps": [{"start_ms": 1180, "end_ms": 1420}]
  },
  "raw_file": "segment-01.raw.json",
  "passages": [
    {
      "index": 1,
      "text": " Wir betreten den Drachenhort.",
      "start_ms": 0,
      "end_ms": 1500,
      "speaker": "SPEAKER_00",
      "signals": {"avg_logprob": -0.21, "no_speech_prob": 0.01, "compression_ratio": 1.3},
      "words": [
        {"text": "Wir", "start_ms": 0, "end_ms": 300, "confidence": 0.95, "speaker": "SPEAKER_00"},
        {"text": "betreten", "start_ms": 300, "end_ms": 800, "confidence": 0.9, "speaker": "SPEAKER_00"},
        {"text": "den", "start_ms": 800, "end_ms": 1000, "confidence": 0.5, "speaker": null},
        {"text": "Drachenhort.", "start_ms": 1000, "end_ms": 1500, "confidence": 0.31, "speaker": "SPEAKER_00"}
      ]
    }
  ]
}
```
