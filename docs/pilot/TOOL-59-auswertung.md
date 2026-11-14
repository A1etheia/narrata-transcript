# TOOL-59 — Laufzeit, Ressourcen und manueller Aufwand

Stand 2026-11-14. Grundlage ist die Pilotsitzung aus [TOOL-58](TOOL-58-erste-session.md): `work/<s>/pipeline.log`, `output/<s>/report.json` (`format_version: 2`) und ein Messlauf auf einer Kopie. Hier stehen nur Kennzahlen, kein Session-Key, keine Gruppe, keine Namen und kein Text (TOOL-66). Plan: [`docs/plans/TOOL-59-runtime-evaluation.md`](../plans/TOOL-59-runtime-evaluation.md).

## Ergebnis in Kürze

- **Die Maschine ist alltagstauglich.** Ein vollständiger Neulauf von ASR und Diarisierung braucht für 5:26 h Audio rund 12 min, das ist 27-fache Echtzeit. Mit wiederverwendeter Diarisierung waren es im Pilot knapp 7 min.
- **Die Ressourcen reichen mit Abstand.** Der Spitzenwert liegt bei 13,9 GiB RAM (ASR) von 25 GiB in WSL und bei rund 2,5 GiB VRAM von 12 GiB. Beide Modelle laufen nacheinander und nie gleichzeitig.
- **Der Engpass ist der Mensch, nicht die Maschine.** Auf eine Stunde Audio kommen rund 2 min Rechenzeit, 0,7 min Sprecherzuordnung und 4,6 h Review, wenn vollständig geprüft wird.
- **Es gibt keine API-Kosten.** Der V0.1-Pfad rechnet lokal, deshalb fehlt eine Kostenkennzahl absichtlich.
- **TOOL-78 entfällt.** Fehlversuche sind in `pipeline.log` vollständig nachvollziehbar, und eine Fehlerrate pro Segment wird nicht gebraucht (siehe unten).

## Aufnahme und Segmente

| | Wert |
| --- | --- |
| Dauer | 05:26:17 (2 Aufnahmen: 05:00:00 und 00:26:17) |
| erzeugte Audiosegmente | 2, eins pro Aufnahme, ohne eigene Segmentierung (TOOL-62) |
| transkribiert | 2 von 2, 0 fehlgeschlagen, 0 fehlend |
| Passagen | 997 |

## Laufzeit je Schritt

Pilotlauf, Wanduhr aus `pipeline.log`, nach dem Lauf mit den CUDA-Bibliotheken:

| Schritt | Ergebnis | Dauer |
| --- | --- | --- |
| preflight, snapshot | ok, Snapshot unverändert | < 1 s |
| extract, context, manifest | wiederverwendet | — |
| transcribe: ASR mit Modell-Laden | 2 Segmente neu | 6:54 min (`runtime.asr_ms`: 377 s + 28 s) |
| transcribe: Diarisierung, Hinweise, Bewertung | Diarisierung wiederverwendet | rund 3 s |
| review, speakers | angehalten für Handarbeit (Exit 3) | < 1 s |
| working, export, txt, docx, report | nach Review und Zuordnung | 1,9 s zusammen |
| **automatischer Durchlauf** | | **6:57 min** |

Messlauf auf der Kopie, ASR und Diarisierung getrennt und beide mit `--force` neu gerechnet:

| Schritt | Wanduhr | `elapsed_ms` je Segment | CPU | Peak-RAM | Peak-VRAM |
| --- | --- | --- | --- | --- | --- |
| ASR (faster-whisper large-v3-turbo, CUDA) | 7:36 min | 437,7 s + 33,2 s | 119 % | 13,9 GiB | 2,5 GiB |
| Diarisierung (pyannote community-1, CUDA) | 4:29 min | 252,9 s + 19,7 s | 222 % | 12,0 GiB | 2,2 GiB |
| **zusammen** | **12:05 min** | | | | |

- **Peak-VRAM** ist der Höchstwert von `nvidia-smi` im 500-ms-Takt, abzüglich der Grundlast von 1,7 GiB, die vor dem Lauf schon belegt war (Desktop). **Peak-RAM** ist die maximale Resident Set Size aus GNU `time -v`.
- **Die Uhren weichen ab.** `elapsed_ms` misst mit `perf_counter` und liegt beim ASR-Lauf 3,4 % über der Wanduhr des ganzen Prozesses (470,9 s gegen 455,5 s, Modell-Laden eingeschlossen). Unter WSL2 laufen monotone Uhr und Wanduhr offenbar auseinander. Für Gesamtzeiten gilt die Wanduhr, `runtime` taugt für den Vergleich von Läufen auf demselben Rechner.
- **Der Messlauf war 16 % langsamer als der Pilot** (ASR 471 s gegen 405 s) und lieferte 956 statt 997 Passagen. Der Grund ist nicht geklärt. Die Kopie wurde danach verworfen, die Pilotsession blieb unverändert.
- **Das Modell-Laden** ist in `elapsed_ms` nicht enthalten. Aus der Differenz zur Wanduhr lässt es sich wegen der Uhrenabweichung nicht sauber ableiten.

## Fehlversuche und Wiederverwendung

- **Fehlversuche:** Im Pilot gab es 2, beide im ersten Lauf und je einer pro Segment (`BackendUnavailableError`, CUDA-Bibliotheken fehlten, nicht wiederholbar). Mit `asr.retries` = 2 wurde deshalb nicht wiederholt. Im erfolgreichen Lauf und im Messlauf gab es 0. Jeder Fehlversuch steht mit Segment, Versuchsnummer und Fehlerklasse in `pipeline.log`.
- **Wiederverwendung:** `pipeline.log` zeigt für jeden Lauf, welche Schritte liefen (`ran`) und welche wiederverwendet wurden (`reused`). Im Pilot wurden Extraktion, Kontext und Manifest in allen drei Läufen nach dem Preflight-Abbruch wiederverwendet. Die Diarisierung wurde im erfolgreichen Lauf wiederverwendet, weil die Rohdatei des gescheiterten Versuchs zu Audio und Modell passte. Das sparte rund 4,5 min. Der letzte Lauf nach Review und Zuordnung brauchte 4,7 s, weil die ASR übernommen wurde.
- **`runtime` in `report.json`** gibt die Rechenzeit, mit der die gespeicherten Dateien entstanden sind. Eine wiederverwendete Datei behält ihre Zeit. In der Pilotsession fehlt die Diarisierungszeit (`runtime_not_recorded`), weil ihre Rohdateien von vor TOOL-59 stammen.

## Review und manueller Aufwand

| | Wert | pro Stunde Audio |
| --- | --- | --- |
| Review-Kandidaten | 870 (685 `needs_review`, 185 `uncertain`) | 160 |
| entschieden in 60 min | 35 (9 bestätigt, 23 korrigiert, 3 unverständlich) | — |
| Review vollständig, hochgerechnet | rund 25 h | 4,6 h |
| Sprecherzuordnung (`effort_minutes`) | 4 min für 7 Labels | 0,7 min |
| Befehle aufrufen | wenige Minuten | — |

Die Kandidaten pro Stunde stammen aus `review.per_hour`, der Zuordnungsaufwand aus `speakers.effort_minutes` in `report.json`. Das Review-Tempo ist die Timebox aus TOOL-58.

## Engpässe (Beobachtungen, keine Optimierung)

- **Review:** Ein vollständiges Review dauert über 100-mal so lange wie die Rechenzeit (25 h gegen 12 min). Hebel sind laut TOOL-58 die Erkennung (TOOL-93, TOOL-92) und der Review-Umfang (TOOL-60), nicht die Laufzeit.
- **RAM der ASR:** 13,9 GiB sind der größte Ressourcenbedarf. Bei 25 GiB in WSL bleibt Reserve, aber beide Modelle gleichzeitig würden nicht passen. Die Pipeline lädt sie deshalb nacheinander (`diarize_session`).
- **Diarisierung des langen Segments:** 253 s für 5 h, rund ein Drittel der Rechenzeit. Bei mehreren Abenden hintereinander ist das unkritisch.
- **GPU-Auslastung:** Der VRAM ist zu einem Fünftel belegt. Ein größeres Modell oder ein Zweitlauf (TOOL-82) hätte Platz, die Laufzeit wäre dann neu zu messen.

## Entscheidung zu TOOL-78

TOOL-78 („Versuche pro Segment im Referenzformat“) entfällt. TOOL-59 wertet keine Fehlerraten aus. Fehlversuche sind selten, im Pilot gab es nur einen Konfigurationsfehler, und sie stehen vollständig in `pipeline.log`. Eine neue `format_version` des Referenzformats wäre dafür zu teuer.
