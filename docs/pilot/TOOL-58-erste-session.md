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

Interaktiv mit `transcript speakers <s> --assign` (TOOL-86): **4 min** für 7 Labels in 2 Segmenten, gemessen vom Befehl selbst (`effort_minutes`). Ergebnis: 6 Labels einer Person zugeordnet, 1 `multiple`, 0 offen, 0 `unknown`. Der Vorlauf mit 8 Labels hatte 8 min gebraucht.

## Review

Review in `review.csv`, sortiert nach `order`, Timebox **60 min**, gestoppt von der Projektverantwortlichen. Angehört wurde mit einem Hilfsskript, das eine Passage über ihre Kandidaten-ID abspielt (siehe Workarounds).

| | Anzahl |
| --- | --- |
| Kandidaten | 870 (185 `uncertain`, 685 `needs_review`), 160 pro Stunde Audio |
| entschieden | 35: 9 `confirmed`, 23 `corrected`, 3 `unintelligible`, 0 `kept` |
| offen | 835 |
| Hörfehler-Vorschläge | 4 neu, 32 Korrekturen ohne Glossar-Begriff |

- **Tempo:** 35 Entscheidungen pro Stunde. Hochgerechnet bräuchte das vollständige Review dieser Sitzung rund 25 Stunden, fast fünfmal so lange wie die Aufnahme.
- **Trefferquote oben in der Liste:** 26 der 35 entschiedenen Kandidaten waren falsch erkannt oder unverständlich (74 %). Die Reihenfolge `order` bringt die Fehler also nach vorn.
- **Die Auswahl trennt kaum:** 870 der 997 Passagen sind Kandidaten (87 %). Die 127 automatisch übernommenen Passagen decken nur 10:21 min der 5:26 h ab, also 3 %. Praktisch die ganze Aufnahme steht zur Prüfung. Ein Grund sind lange Passagen: Whisper-Passagen dauern im Mittel rund 20 s, und schon ein einziges unsicheres Wort macht die ganze Passage zum Kandidaten (Regel `very_low_confidence`).
- **Halluzination am Aufnahmeende:** Die letzte Passage von Segment 2 (1,7 s, Wort-Confidence nahezu 0) ist von Whisper erfundener Text. Sie wurde richtig als `uncertain` markiert und im Review als `unintelligible` entschieden.

## Ergebnis

`transcript process <s>` nach Zuordnung und Review: Exit 1, einzige Lücke `open_passages` in beiden Segmenten.

| Datei | Inhalt |
| --- | --- |
| `transcript.json` | Contract 1.1, `source.recordings[]` mit 2 Aufnahmen, 997 Passagen; vor dem Schreiben gegen die Schema-Kopie und die Regeln aus `contract.validate` geprüft |
| `transcript.txt`, `transcript.docx` | 481 Absätze, offene Passagen als `[unklar …]` markiert |
| `report.json`, `report.md` | 3 `unintelligible`, 3 `crosstalk`, 835 offen; 4 Personen hinter 7 Labels |

**Grober manueller Aufwand:** 4 min Zuordnung und 60 min Review (35 von 870 Kandidaten), dazu wenige Minuten für die Befehle. Ein vollständiges Review läge bei rund 25 h (siehe oben).

## Fehlerstichprobe

_folgt (Chunk 3)_

## Narrata-Gegenprobe

_folgt (Chunk 4)_

## Blockierende Fehler und Workarounds

- **Alte Handdateien vor `--redo transcribe`:** Die alte `speakers/assignment.json` und `review/review.csv` stammten aus einem früheren Lauf. Nach einer neuen ASR wären ihre Einträge `stale`, und `process` hätte keine frischen Vorlagen geschrieben. Deshalb wurden sie vorher nach `work/<s>/pre-tool58/` verschoben.
- **CUDA-Bibliotheken für faster-whisper:** Der erste Versuch scheiterte nach 6 min an beiden Segmenten mit `BackendUnavailableError … CUDA libraries not found`, weil `LD_LIBRARY_PATH` in der Shell fehlte (Voraussetzung laut README, Abschnitt „Spracherkennung“). Workaround: den Pfad setzen und `--redo transcribe` wiederholen. Das alte ASR-Ergebnis blieb dabei unverändert.
- **Preflight meldet die ASR zu früh als `ok`:** `transcript doctor` zeigte `asr: … on cuda` als `ok`, obwohl faster-whisper cuBLAS und cuDNN nicht laden konnte. Der Fehler fiel erst nach Snapshot und Diarisierung auf. Der Preflight sollte das Laden der Bibliotheken prüfen, ohne das Modell zu laden.
- **Aufruf ohne aktivierte venv:** Ohne `source .venv/bin/activate` kennt die Shell `transcript` nicht, und `LD_LIBRARY_PATH` muss in jeder Shell neu gesetzt werden. Workaround auf dem Pilotrechner: ein Startskript `~/.local/bin/transcript`, das beides übernimmt. Aufgerufen wird es weiterhin aus dem Projektordner, weil `paths.root` relativ ist.
- **Keine Abspielhilfe im Review:** Fast jede Zeile muss angehört werden, aber die Pipeline spielt nur im Sprecher-Dialog ab. Wer Segment und Zeit von Hand aus der CSV in einen Player überträgt, verliert viel Zeit, und bei der Spalte `start` (Session-Zeit statt Segment-Zeit) springt der Player hinter das Segmentende und bleibt stumm. Workaround: das Skript `~/.local/bin/hoer <id>`, das Segment und Zeiten aus `candidates.json` liest und die Passage mit 2 s Vorlauf und 1 s Nachlauf abspielt. Ein Review-Dialog nach dem Vorbild von `speakers --assign` würde den Aufwand vermutlich spürbar senken.
