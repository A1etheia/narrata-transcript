# Referenztranskript-Format

Das Referenztranskript ist das interne, versionierte Ergebnis der Spracherkennung für ein Segment, also für eine Aufnahme laut Manifest (TOOL-16). Konfidenzbewertung, Review und Export lesen nur dieses Format und müssen nicht wissen, welches Backend gelaufen ist. Code: `src/transcript/reference.py`.

## Dateien

Pro Segment gibt es zwei Dateien unter `work/<gruppe>/<ordinal>/asr/`:

| Datei | Inhalt |
| --- | --- |
| `segment-NN.json` | Normalform, `format_version: 2` |
| `segment-NN.raw.json` | `{"backend_id": …, "raw": …}`: die Antwort des Backends, unverändert |

`NN` ist der Segmentindex aus dem Manifest, wie bei `audio/segment-NN.wav`. Geschrieben wird zuerst die Rohform, dann die Normalform, beide atomar. Erst die Normalform markiert ein Segment als fertig. Bricht ein Lauf dazwischen ab, liegt höchstens eine Rohdatei ohne Normalform da, und das Segment gilt als nicht transkribiert.

```python
from transcript.reference import from_backend_result, load_reference, write_reference

result = transcribe(backend, request)
reference = from_backend_result(result, backend, manifest, segment, elapsed_ms=…)
write_reference(paths, reference, result.raw)

reference = load_reference(paths, segment.index)   # ohne Backend
```

Schlägt ein Segment fehl, hält `failed_reference(error, backend, manifest, segment)` das fest. Beides zusammen, samt Laufzeitmessung und den Regeln für vorhandene Ergebnisse, erledigt `transcript.transcription.transcribe_session` für alle Segmente einer Session, auf der Kommandozeile `transcript transcribe <session>`. Ein vorhandenes `transcribed` wird wiederverwendet, solange `asr.backend_id`, `model`, `model_version` und `settings` zum Backend passen, `asr.knowledge_snapshot_id` zum vorhandenen Wissens-Snapshot der Session und `asr.language` zur konfigurierten Sprache; `runtime_version` zählt nicht mit. Ein neu gebauter oder aktualisierter Snapshot mit anderer ID führt also zur Neutranskription, ebenso ein erster Snapshot für eine schon transkribierte Session. `transcribe` liest die ID nur, es baut keinen Snapshot.

## Normalform

| Feld | Pflicht | Inhalt |
| --- | --- | --- |
| `format_version` | ja | `2` (gelesen werden `1` und `2`) |
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

**`asr`:** `backend_id`, `model`, `model_version`, `runtime_version`, `capabilities` (wie `Capabilities.to_dict()`), `settings` (Inferenzparameter), `language`, `language_probability`, `keywords_used` (die Begriffe, die tatsächlich gewirkt haben), `knowledge_snapshot_id` (die `snapshot_id` des Wissens-Snapshots, mit dem der Lauf gestartet wurde, `null` ohne Snapshot). Nur `backend_id` und `model` sind Pflicht, alles andere darf `null` oder leer sein.

**Passage:** ein Stück Sprache, so wie das Backend es abgegrenzt hat, bei Whisper ein Segment der Ausgabe. Felder: `index` (fortlaufend ab 1), `text` (wie erkannt), `start_ms`, `end_ms`, `speaker`, `signals` (Zahlen pro Passage, z. B. `avg_logprob`), `words`.

**Wort:** `text`, `start_ms`, `end_ms`, `confidence` (0–1), `speaker`.

Optional sind die Zeiten, die Confidence und der Sprecher, jeweils `null`. Ein Backend ohne Zeiten wie Granite liefert Passagen nur mit Text, ein Backend ohne Wörter liefert leere `words`. Das Format verlangt keine Felder eines bestimmten Backends.

## Regeln

- **Zeiten sind ganze Millisekunden, lokal zum Segment-WAV.** Absolute Session-Zeiten werden nicht gespeichert, sondern beim Lesen aus dem Manifest berechnet, siehe [Session-Zeit](#session-zeit). Dadurch bleiben sie richtig, wenn das Manifest neu gebaut wird. Es gilt `start_ms ≤ end_ms`, und kein Wert ist negativ.
- **Der Text wird nie korrigiert.** `text` steht so da, wie das Backend ihn geliefert hat, einschließlich führender Leerzeichen. `ReferenceTranscript.text` fügt die Passagen für die Anzeige zusammen. Gespeichert wird dieser Gesamttext nicht.
- **Confidence-Skalen sind modellabhängig** (siehe [`asr-backends.md`](asr-backends.md)). Vergleichbar ist nur die Rangfolge innerhalb eines Modells. Welches Modell gelaufen ist, steht in `asr`.
- **Rohform und Normalform sind getrennt.** `raw` steht nur in der Rohdatei. Die Normalform enthält nichts, was nur ein bestimmtes Backend versteht.

## Session-Zeit

`src/transcript/session_time.py` rechnet die lokalen Zeiten einer Passage oder eines Worts in Zeit der Gesamtaufnahme um (TOOL-19). Nachgelagerte Schritte brauchen dafür nur Manifest und Referenztranskript, nicht das Backend:

```python
from transcript.session_time import passage_span, segment_of, time_granularity, word_span

segment = segment_of(manifest, reference)   # prüft Index, WAV-Name und Quell-Hash
for passage in reference.passages:
    span = passage_span(segment, passage)    # SessionSpan oder None
    words = [word_span(segment, word) for word in passage.words]
```

Ein `SessionSpan` enthält `granularity` (`word` oder `passage`), die lokalen Werte `local_start_ms`/`local_end_ms`, die Session-Werte `start_ms`/`end_ms` und `clamped`. `timecode()` liefert `HH:MM:SS.mmm–HH:MM:SS.mmm` über `timecode.format_ms`. Die Stunden laufen über 99 hinaus, eine fehlende Grenze erscheint als `?`.

- **Granularität:** `time_granularity(reference)` liefert die feinste Stufe, für die das Transkript tatsächlich Zeiten hat: `word`, `passage` oder `none`. Entscheidend sind die gespeicherten Daten, nicht `asr.capabilities`, denn ein Backend mit Wortzeiten kann für ein stilles Segment trotzdem keine liefern. Woher die Zeiten stammen, steht in `asr.backend_id` und `asr.capabilities`.
- **Nur Passagenzeiten:** `passage_span` liefert einen Span, `word_span` liefert `None` für jedes Wort. Die Passagenzeit wird nicht auf die Wörter verteilt.
- **Gar keine Zeiten** (z. B. Granite): Jeder Span ist `None`, `time_granularity` ist `none`. Nichts wird geschätzt oder von Nachbarn übernommen. Hat eine Einheit nur Start oder nur Ende, bleibt die andere Grenze `None`.
- **WAV-Ende:** Backends runden und polstern das letzte Wort. Eine lokale Zeit bis `END_TOLERANCE_MS` (1000 ms) hinter dem Segmentende wird auf das Segmentende gesetzt, und der Span trägt dann `clamped: true`. Der lokale Wert bleibt unverändert. Alles darüber hinaus ist ein `ValueError`, denn dann passt das Transkript nicht zum WAV. `Segment.to_absolute_ms` selbst ist streng und nimmt nur 0 bis `duration_ms`.
- **Überlappung:** Ein Segment mit `overlap_before_ms` beginnt vor dem Ende des vorigen. Ein Span ist nie negativ und endet nie nach `manifest.duration_ms`. Doppelte Passagen im Überlappungsbereich bleiben doppelt, Deduplizieren ist nicht Teil dieses Schritts.
- **Fehlermeldungen** nennen Segmentnummer und Millisekunden, nie Text.

## Sprecher

Sprecher kommen aus einer separaten Diarisierung mit pyannote (TOOL-76, Grundlage [`spikes/TOOL-20-diarisierung.md`](spikes/TOOL-20-diarisierung.md)):

- **Das Wort-Label ist maßgeblich.** `null` ist ein gültiger Wert: Im Test lagen 6–14 % der Wörter in keinem Turn.
- **`speaker` einer Passage** ist das Label, das die meisten ihrer Wörter tragen (`majority_speaker`). Bei Gleichstand oder ohne Wort-Labels ist es `null`. Liefert ein Backend nur ein Label pro Passage, wird dieses übernommen. Wechsel innerhalb einer Passage bleiben an den Wörtern sichtbar.
- **Labels sind generisch** (`SPEAKER_00`), nie Namen. Die Zuordnung zu Personen steht getrennt in `work/<gruppe>/<ordinal>/speakers/assignment.json` (TOOL-68, README „Sprecherzuordnung“) und kommt nie in diese Datei.
- **Labels gelten pro Segment.** Jede Aufnahme wird für sich diarisiert; `SPEAKER_00` in zwei Segmenten ist nicht automatisch dieselbe Person.
- **Rohform getrennt:** Die Turns des Modells liegen unverändert unter `work/<gruppe>/<ordinal>/diarization/segment-NN.json` (`format_version: 1`): `backend_id`, `model`, `model_version`, `runtime_version`, `settings`, `num_speakers`, `audio_sha256` des Segment-WAVs, `turns` und `exclusive_turns` (`[{start_ms, end_ms, label}]`). Nur die exklusiven Turns, in denen immer genau eine Person spricht, bestimmen die Wort-Labels; aus den überlappenden Turns entstehen `overlaps`. `transcript diarize` schreibt danach nur die Normalform neu (`update_reference`), die ASR-Rohdatei bleibt unberührt. Code: `src/transcript/diarization/`.
- **`diarization`** hält die Metadaten getrennt von `asr`: `backend_id`, `model`, `model_version`, `settings`, `num_speakers` (die Vorgabe, nicht das Ergebnis), `labels` (alle Labels des Segments) und `overlaps` (`[{start_ms, end_ms}]`, Bereiche mit Übersprechen). Ist es gesetzt, darf kein Wort und keine Passage ein Label außerhalb von `labels` tragen.

## Versionierung

`format_version` steht an erster Stelle. Geschrieben wird immer `2`. `load_reference` liest `1` und `2`, bei `1` ist `knowledge_snapshot_id` `null`. Jede andere Version lehnt es ab und verlangt, das Segment neu zu transkribieren. Schreibt `transcript diarize` eine Datei der Version `1` neu, wird sie dabei zu `2`. Eine Änderung, die alte Dateien unlesbar macht, erhöht die Version. Fehlermeldungen beim Laden nennen Datei, Feld und Passagennummer, nie Text, Keywords oder Labels.

## Beispiel

Erfundener Inhalt, gekürzt auf eine Passage:

```json
{
  "format_version": 2,
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
    "keywords_used": ["Drachenhort"],
    "knowledge_snapshot_id": "3f2a…"
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
