# TOOL-58 — Erste reale Session: Pilotbericht

Stand 2026-11-12. Dieser Bericht enthält nur Kennzahlen, Codes und nachgestellte Beispiele. Session-Key, Gruppe, Namen und Transkripttext stehen nicht darin (TOOL-66). Plan: [`docs/plans/TOOL-58-pilot-session.md`](../plans/TOOL-58-pilot-session.md).

## Pilotsitzung

| Merkmal | Wert |
| --- | --- |
| Aufnahmen | 2, zusammen 05:26:17 |
| Contract | 1.1 (`source.recordings[]`) |
| Sprecher-Labels (Vorlauf) | 8 |

## Umgebung

| | |
| --- | --- |
| GPU | RTX 3080 Ti, 12 GB VRAM |
| ASR | faster-whisper large-v3-turbo, Revision `0a363e91`, CUDA |
| Diarisierung | pyannote/speaker-diarization-community-1, Revision `3533c8cf` |
| Wissens-Snapshot | `186e030dc24e`, ab `transcribe` eingefroren |

## Automatischer Lauf

`transcript process <s> --redo transcribe`, Zeiten aus `work/<s>/pipeline.log`:

| Schritt | Ergebnis | Dauer |
| --- | --- | --- |
| preflight, snapshot | ok, Snapshot wiederverwendet | < 1 s |
| extract, context, manifest | wiederverwendet | — |
| transcribe (ASR, Diarisierung, Hinweise, Bewertung) | 2 von 2 Segmenten | 6:57 min |
| review, speakers | angehalten (Exit 3), Vorlagen geschrieben | < 1 s |

- **Tempo:** 5:26 h Audio in knapp 7 min, also rund 47-fache Echtzeit für den ganzen Schritt. Die Diarisierung allein brauchte im ersten, an der ASR gescheiterten Versuch 231 s und 18 s für die beiden Segmente.
- **Ressourcen:** Im ersten Versuch (nur Diarisierung, die ASR scheiterte vor dem Laden) lagen der Peak-RAM bei 14,5 GB und der Peak-VRAM bei 3,6 GB. Die Messwerte des erfolgreichen Laufs gingen verloren, weil das temporäre Verzeichnis mit den Mitschnitten geleert wurde. Nach TOOL-62 und TOOL-20 sind für die ASR bis 10,5 GB RAM zu erwarten, beide Modelle laufen nacheinander.
- **Bewertung:** 870 Review-Kandidaten, davon 185 `uncertain` und 685 `needs_review`, das sind 160 pro Stunde Audio. Im Vorlauf mit älterem Snapshot waren es 1371 (252 pro Stunde).
- **Diarisierung:** 7 Sprecher-Labels über beide Segmente, alle offen.

## Sprecherzuordnung

_folgt (Chunk 2)_

## Review

_folgt (Chunk 2)_

## Fehlerstichprobe

_folgt (Chunk 3)_

## Narrata-Gegenprobe

_folgt (Chunk 4)_

## Blockierende Fehler und Workarounds

- **Alte Handdateien vor `--redo transcribe`:** Die alte `speakers/assignment.json` und `review/review.csv` stammten aus einem früheren Lauf. Nach einer neuen ASR wären ihre Einträge `stale`, und `process` hätte keine frischen Vorlagen geschrieben. Deshalb wurden sie vorher nach `work/<s>/pre-tool58/` verschoben.
- **CUDA-Bibliotheken für faster-whisper:** Der erste Versuch scheiterte nach 6 min an beiden Segmenten mit `BackendUnavailableError … CUDA libraries not found`, weil `LD_LIBRARY_PATH` in der Shell fehlte (Voraussetzung laut README, Abschnitt „Spracherkennung“). Workaround: den Pfad setzen und `--redo transcribe` wiederholen. Das alte ASR-Ergebnis blieb dabei unverändert.
- **Preflight meldet die ASR zu früh als `ok`:** `transcript doctor` zeigte `asr: … on cuda` als `ok`, obwohl faster-whisper cuBLAS und cuDNN nicht laden konnte. Der Fehler fiel erst nach Snapshot und Diarisierung auf. Der Preflight sollte das Laden der Bibliotheken prüfen, ohne das Modell zu laden.
