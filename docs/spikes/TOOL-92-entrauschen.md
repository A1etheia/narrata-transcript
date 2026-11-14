# TOOL-92 — Entrauschen vor der Erkennung

Stand 2026-11-14. Spike-Bericht zu [TOOL-92](../plans/TOOL-92-denoise-spike.md), Werkzeug: [`scripts/spike/denoise.py`](../../scripts/spike/denoise.py). Alle Filter und Läufe liefen lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

- **Entscheidung: No-Go.** Kein Kandidat erfüllt die Go-Regel. Die eigentlichen Rauschfilter (`afftdn`, RNNoise, DeepFilterNet) verschlechtern die WER an A um 2 bis 9 Punkte. Außerdem lassen sie mehr Wörter ohne Sprecher-Label, und DeepFilterNet verschiebt die Bewertung so, dass Fehler übersehen werden.
- **Hochpass 80 Hz ist der einzige Kandidat ohne Nachteil.** An A ist er gleichauf mit dem Roh-WAV, an B im Mittel 8,7 Punkte besser, und alle drei Läufe liegen eng beieinander. Die Spannen überlappen sich aber knapp mit denen von `base`, und der Vorteil kommt allein daher, dass zwei von drei `base`-Läufen an B einen Block verlieren. Er geht deshalb als Kandidat an TOOL-93 und nicht als Umsetzung.
- **Wichtigster Befund: Whisper ist zwischen Läufen nicht stabil.** Auf demselben WAV liegen drei `base`-Läufe an B zwischen 33,7 % und 46,6 % WER. Ursache ist der Temperatur-Fallback: Mit `temperature=0` ist der Lauf exakt reproduzierbar, aber schlechter (32,1 % / 46,4 %) und gerät in Wiederholungsschleifen (8,9 % statt 0,4–0,9 %). Die Annahme aus TOOL-62, dass 1–2 Punkte Rauschen sind, gilt nur für einen einzelnen Lauf. Jeder Vergleich zwischen Läufen braucht mehrere Wiederholungen oder einen festen Seed.

## Material und Methode

| | |
| --- | --- |
| Aufnahme | Segment 1 der Pilotsitzung, 5:00:00, 16 kHz mono |
| Referenz A | 0:00:00–0:04:06, 551 Wörter, 3 Sprecher (WER und WDER) |
| Referenz B | 1:20:00–1:23:00, 489 Wörter, ohne Sprecher (nur WER) |
| Pipeline | `transcript transcribe` unverändert, mit ASR, Hinweisen, Bewertung und Diarisierung; Whisper large-v3-turbo über faster-whisper 1.2.1, pyannote.audio 4.0.7 |
| Hardware | RTX 3080 Ti (12 GB VRAM), 20 Threads, 15 GB RAM in WSL2 |
| Wiederholungen | 3 Läufe pro Kandidat auf demselben gefilterten WAV, `base-t0` 2 Läufe |

Jeder Kandidat bekommt eine eigene Wurzel (`paths.root`) mit Kopien von Manifest, Audio-Metadaten und Wissens-Snapshot sowie dem gefilterten WAV. Alle Wurzeln nutzen dieselbe Modell-Revision und denselben Snapshot, `score` prüft das. Jeder Filter endet mit `aresample=16000,apad,atrim` auf die Frame-Zahl des Manifests, sodass die Zeitachse exakt erhalten bleibt.

Gemessen werden:

- WER über `calibration.measure`, also wie `transcript calibrate`
- Halluzination wie in TOOL-62: Anteil der 5-Wort-Folgen, die mindestens dreimal vorkommen, und Anteil verschiedener Wörter über das Segment
- Bewertung: Passagen je Stufe, markierte Zeit und die Fehler, die in `confident`-Passagen liegen („übersehen“)
- Diarisierung wie in TOOL-20: WDER an A nach bester 1:1-Zuordnung, Wörter ohne Label und die Übereinstimmung der Labels mit `base` auf einem 100-ms-Raster

## Kandidaten

| Kandidat | Kette | Werkzeug, Lizenz |
| --- | --- | --- |
| `base` | Roh-WAV | — |
| `base-t0` | Roh-WAV, Whisper mit `temperature=0` (nur im Spike) | — |
| `hp` | `highpass=f=80` | ffmpeg 4.4.2 |
| `hp-afftdn` | `highpass=f=80,afftdn=nf=-25` (mittlere Kette aus TOOL-91) | ffmpeg 4.4.2 |
| `arnndn` | 48 kHz, `arnndn` mit Modell `lq.rnnn` (Stimme samt Lachen unter allgemeinem Störgeräusch) | ffmpeg 4.4.2; Modell aus GregorR/rnnoise-models, laut README nicht urheberrechtlich geschützt |
| `dfn` | 48 kHz, DeepFilterNet 3 (`deep-filter -D`, Verzögerung ausgeglichen) | `deep-filter` 0.5.6, MIT/Apache-2.0, statisches Binary auf der CPU |

Die `hp`-Varianten von `arnndn` und `dfn` sind laut Plan entfallen, weil keiner der beiden `base` schlägt.

## Ergebnisse

### Wortlaut

Mittel und Spanne über drei Läufe. Auslassungen je Lauf:

| Kandidat | WER A | Auslassungen A | WER B | Auslassungen B |
| --- | --- | --- | --- | --- |
| `base` | 24,2 % (23,6–25,4) | 47 / 59 / 51 | 42,3 % (33,7–46,6) | 159 / 85 / 164 |
| `hp` | **23,6 %** (23,6–23,6) | 52 / 52 / 52 | **33,6 %** (32,9–33,9) | 93 / 89 / 93 |
| `hp-afftdn` | 32,8 % (26,5–44,3) | 81 / 60 / 68 | 38,4 % (37,0–39,7) | 101 / 105 / 79 |
| `arnndn` | 26,5 % (26,5–26,5) | 58 / 58 / 58 | 38,7 % (38,2–39,7) | 92 / 92 / 101 |
| `dfn` | 27,5 % (27,0–28,1) | 62 / 65 / 59 | 35,5 % (35,2–36,2) | 86 / 88 / 86 |
| `base-t0` (2 Läufe) | 32,1 % (32,1–32,1) | 93 / 93 | 46,4 % (46,4–46,4) | 147 / 147 |

- Die Streuung von `base` an B ist zweigeteilt: Zwei Läufe verlieren rund 75 Wörter mehr als der dritte. Der Sprung liegt fast ganz bei den Auslassungen, Ersetzungen und Einfügungen bleiben ähnlich (58–76 bzw. 4–6). Alle drei `hp`-Läufe liegen auf dem guten Niveau. Bei drei Läufen ist das ein Hinweis, kein Beleg.
- Der erste Lauf von `hp-afftdn` hat an A 85 Einfügungen statt 12–19, Whisper erfindet dort also Text. Die beiden anderen Läufe nicht. Die Kette, die in TOOL-91 für Menschen am besten klang, ist für die Erkennung die unruhigste.
- `arnndn` und `hp` liefern an A in allen drei Läufen exakt dieselbe Zählung. Gefiltertes Audio scheint den Fallback seltener auszulösen als das Roh-WAV.

### Halluzination und Bewertung

Spanne über die Läufe, Segment 1:

| Kandidat | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen A | übersehen B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | 32 655–33 148 | 0,4–0,9 % | 14,6–14,9 % | 100–134 / 601–623 / 163–187 | 96,2–97,6 % | 0 | 0–17 |
| `hp` | 32 794–33 107 | 0,2–0,5 % | 14,4–14,9 % | 89–135 / 569–608 / 145–168 | 96,3–97,3 % | 0 | 0 |
| `hp-afftdn` | 31 813–32 044 | 0,8–1,0 % | 14,5–14,8 % | 88–103 / 549–564 / 105–172 | 97,0–97,9 % | 0 | 0–41 |
| `arnndn` | 31 871–32 120 | 0,8–1,0 % | 14,9–15,1 % | 141–162 / 609–670 / 193–228 | 94,7–95,7 % | 0 | 12 |
| `dfn` | 33 061–33 346 | 0,5–0,9 % | 14,4–14,8 % | 162–189 / 629–654 / 200–225 | 95,1–96,0 % | 14 | 18–34 |
| `base-t0` | 33 142 | **8,9 %** | 13,2 % | 112 / 506 / 124 | 96,9 % | 0 | 7 |

- Die Filter mit Modell (`arnndn`, `dfn`) erzeugen mehr `confident`-Passagen. Darin stecken aber Fehler: Bei `dfn` liegen an A in jedem Lauf 14 Fehler in Passagen, die nicht ins Review kämen. Die Schwellen der Bewertung sind am Roh-WAV kalibriert (TOOL-35) und passen offenbar nicht auf gefiltertes Audio.
- `base-t0` hat 10- bis 20-mal so viele Wiederholungen wie `base`. Ohne Fallback bleibt Whisper in Schleifen hängen, dafür ist der Fallback da.

### Sprecher

| Kandidat | Labels | Wörter ohne Label | WDER A | gewertete Wörter A | Übereinstimmung mit `base` |
| --- | --- | --- | --- | --- | --- |
| `base` | 4 | 6,7–6,8 % | 15,3–15,7 % | 413–428 | 100 % |
| `hp` | 4 | 7,0–7,2 % | 15,3 % | 426 | 97,9 % |
| `hp-afftdn` | 4 | 7,3–7,4 % | 13,3–15,4 % | 370–398 | 95,7 % |
| `arnndn` | 4 | 10,7 % | 12,5 % | 391 | 94,9 % |
| `dfn` | 4 | 9,4–9,6 % | 13,7–14,3 % | 386–392 | 95,1 % |
| `base-t0` | 4 | 6,9 % | 17,0 % | 377 | 100 % |

Die Diarisierung ist deterministisch: Auf demselben WAV liefert sie immer dieselben Labels. `arnndn` und `dfn` senken die WDER um 1–3 Punkte, aber auf weniger gewerteten Wörtern, weil 3–4 Punkte mehr Wörter gar kein Label bekommen. Unterm Strich ist das kein Gewinn. `hp` ändert an der Sprecherzuordnung praktisch nichts.

### Laufzeit

Minuten pro Stunde Audio:

| Kandidat | Filter | ASR | Diarisierung |
| --- | --- | --- | --- |
| `base` | 0 | 1,35–1,42 | 0,83–0,85 |
| `base-t0` | 0 | 1,03–1,07 | 0,84–0,86 |
| `hp` | 0,01 | 1,32–1,41 | 0,84–0,86 |
| `hp-afftdn` | 0,11 | 1,21–1,30 | 0,81–0,84 |
| `arnndn` | 0,39 | 1,34–1,48 | 0,79–0,83 |
| `dfn` | 7,43 | 1,30–1,37 | 0,80–0,84 |

DeepFilterNet braucht auf der CPU mehr als dreimal so lange wie ASR und Diarisierung zusammen (5 h in 37 min, 6,8 GB RAM). Ein Hochpass kostet nichts.

## Entscheidung

**No-Go** für ein Entrauschen in V0.1. Die Go-Regel aus dem Plan verlangt, dass ein Kandidat an A und B im Mittel so viel besser ist, dass sich seine Spanne nicht mit der von `base` überlappt, ohne dass Halluzinationen oder WDER steigen.

- `hp-afftdn`, `arnndn` und `dfn` sind an A im Mittel 2,3 bis 8,6 Punkte schlechter als `base`. Damit scheiden sie aus, egal wie B aussieht.
- `hp` überlappt an A (23,6 % gegen 23,6–25,4 %) und an B knapp (32,9–33,9 % gegen 33,7–46,6 %). Er ist der einzige Kandidat, der nirgends schadet. Sein Vorteil an B hängt aber daran, ob der Fallback einen Block verliert, und das ist ein Effekt der Dekodierung, kein Effekt des Rauschens. Ob `hp` diese Verluste wirklich verhindert, klärt TOOL-93 zusammen mit den Dekodier-Einstellungen. Ein eigenes Umsetzungsticket entsteht deshalb nicht.

## Offen

- **Lauf-zu-Lauf-Streuung (TOOL-93):** Die Rauschannahme von 1–2 Punkten aus TOOL-62 gilt nicht für den Vergleich verschiedener Läufe. TOOL-93 braucht mehrere Läufe je Variante oder einen festen Seed. `temperature=0` scheidet als Lösung aus (Schleifen, höhere WER). Zu prüfen sind ein fester Seed und der Fallback mit anderen Schwellen (`compression_ratio_threshold`, `log_prob_threshold`). `hp` läuft dort als zusätzliche Variante mit.
- **Pilotwerte (TOOL-60):** Die WER aus TOOL-58 (23,6 % / 32,9 %) ist ein einzelner Lauf. An B liegt der Mittelwert von drei Läufen auf dem Roh-WAV bei 42,3 %. Die V0.1-Bewertung sollte die Spanne nennen, nicht den einen Wert.
- **Bewertung auf gefiltertem Audio:** Sollte später doch gefiltert werden, muss die Bewertung auf dem gefilterten Audio neu kalibriert werden (TOOL-35), weil sonst Fehler in `confident`-Passagen landen. [kein Ticket: nur relevant, falls ein Filter kommt]
- **Hörstichprobe der Diarisierung:** entfällt, weil es kein Go gibt. [kein Ticket: entfällt mit No-Go]
