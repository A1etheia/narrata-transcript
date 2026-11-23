# TOOL-104 — Recherche: Batched-Pipeline, neue lokale Modelle und sprecherbedingte Erkennung gegen Auslassungen

Stand 2026-11-23. Bericht zu [TOOL-104](../plans/TOOL-104-asr-research.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py) und [`scripts/spike/omissions.py`](../../scripts/spike/omissions.py). Alle Messungen liefen lokal. Der Bericht enthält nur Kennzahlen und öffentliche Quellen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

Folgt in Chunk 5, wenn Recherche und neue Handreferenz vorliegen. Bis dahin steht das Ergebnis der Messung unter [Ergebnis](#ergebnis).

## Punkt 4: die Batched-Pipeline von faster-whisper

### Was sie trägt

**Die `BatchedInferencePipeline` nimmt in faster-whisper 1.2.1 Hotwords und Wortzeiten an.** Belegt am Quelltext (`faster_whisper/transcribe.py`, `BatchedInferencePipeline.transcribe`) und am Lauf: Jede Batched-Wurzel hat die 48 Hotwords der Basis übergeben, und jedes Wort trägt eine Zeit und eine Konfidenz.

### Was sie anders macht

| | Pipeline (`WhisperModel.transcribe`) | Batched-Pipeline |
| --- | --- | --- |
| Zuschnitt | fortlaufende 30-s-Fenster über das VAD-Audio; das nächste Fenster beginnt, wo der Decoder aufgehört hat | ein Stück je Sprachabschnitt der VAD, höchstens 30 s, jedes für sich |
| VAD ohne `vad_parameters` | Schnitt ab 2000 ms Stille | Schnitt ab 160 ms Stille, Abschnitte auf 30 s begrenzt |
| Temperatur | Fallback 0 bis 1 in sechs Stufen nach `log_prob`, Kompression und `no_speech` | nur die erste Temperatur (0), die drei Schwellen wirken nicht |
| Zeitstempel-Tokens | ja | ohne (`without_timestamps`), mit `+ts` ja; Wortzeiten kommen in beiden Fällen aus der Ausrichtung |
| Text des vorigen Fensters | abgeschaltet (`condition_on_previous_text: false`) | nie |
| Stapel | 1 | 8 Stücke gleichzeitig |

- **Ein verlorenes Fenster kann kein folgendes mitreißen.** In der Pipeline bestimmt der Decoder selbst, wo das nächste Fenster beginnt. Überspringt er Sprache, fehlt sie. Die Batched-Pipeline legt die Stücke vor der Dekodierung fest.
- **Der Seed hat nichts mehr zu würfeln.** Ohne Fallback gibt es keine Stichprobe.

## Material und Methode

| | |
| --- | --- |
| Läufe | large-v3-turbo mit Hotwords, Segment 1 beider Sitzungen, Seeds 1–3 |
| Varianten | `base+batched`, `base+batched+ts`, `loud+batched` |
| Vergleich | `base` (Pipeline wie ausgeliefert), `base+temp0` (Pipeline ohne Fallback), `loud` (zweistufiges `loudnorm`, TOOL-103) |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |
| Referenz D | Pilotsitzung, 0:43:00–0:46:00, 449 Wörter |
| Referenz E | Pilotsitzung, 1:23:00–1:26:00, 369 Wörter |
| Hardware | RTX 3080 Ti, 12 GB |

- **Regel, vor der Messung festgelegt** (Plan): Eine Variante bekommt ein Umsetzungsticket, wenn an A und an B ihre höchste WER der drei Seeds unter der niedrigsten des Vergleichs liegt (`base+batched` gegen `base`, `loud+batched` gegen `loud`) und Einfügungen und Wiederholungsanteil im Mittel nicht darüber liegen. C, D und E sind Gegenprobe.
- **`base+temp0`** trennt zwei Wirkungen: den fehlenden Fallback und den Zuschnitt je VAD-Abschnitt.
- **Blockverluste** über zwei Zahlen: „Sprache ohne Wörter“ aus `omissions.py` (Stellen, an denen die Diarisierung Sprache hört und der Lauf kein Wort hat) und die Wortzahl je 5 Minuten gegen `base` (`asr.py sections`).

## Ergebnis

**`base+batched` verliert keine Blöcke mehr, ist an allen fünf Referenzen besser als `base` und liefert bei jedem Seed dasselbe. Die vorab festgelegte Regel verfehlt die Variante trotzdem knapp, am Wiederholungsanteil.** `loud+batched` fällt durch, `+ts` bringt nichts.

WER und Auslassungen als Mittel über drei Seeds, aus den Tabellen unter [Messwerte](#messwerte):

| Referenz | `base` | `loud` | `base+batched` | `base+batched+ts` | `loud+batched` | `base+temp0` |
| --- | --- | --- | --- | --- | --- | --- |
| A | 21,3 % / 33 | 20,2 % / 29 | 19,6 % / 29 | 20,5 % / 32 | 18,8 % / 27 | 29,8 % / 74 |
| B | 29,8 % / 44 | 26,5 % / 42 | 25,4 % / 38 | 25,4 % / 37 | 28,1 % / 39 | 40,8 % / 100 |
| C | 30,8 % / 138 | 23,9 % / 89 | 25,9 % / 110 | 32,2 % / 127 | 23,7 % / 97 | 47,9 % / 231 |
| D | 61,2 % / 138 | 36,7 % / 62 | 36,3 % / 65 | 36,3 % / 55 | 38,3 % / 77 | 52,8 % / 132 |
| E | 34,0 % / 56 | 29,6 % / 30 | 29,0 % / 40 | 28,7 % / 37 | 67,5 % / 96 | 46,6 % / 55 |

### Die Regel an A und B

| | `base+batched` gegen `base` | `loud+batched` gegen `loud` |
| --- | --- | --- |
| A: höchste WER unter der niedrigsten des Vergleichs | ja (19,6 % gegen 21,3 %) | ja (18,8 % gegen 20,2 %) |
| B: höchste WER unter der niedrigsten des Vergleichs | ja (25,4 % gegen 25,6 %) | nein (28,1 % gegen 26,5 %) |
| Einfügungen im Mittel nicht darüber | ja (A 15 gegen 17, B 4 gegen 18) | ja (A 16 gegen 17, B 5 gegen 6) |
| Wiederholungsanteil im Mittel nicht darüber | nein (1,0 % gegen 0,7 %) | nein (1,7 % gegen 0,6 %) |
| Gegenprobe C, D, E gegen das Mittel des Vergleichs | besser an allen drei | C gleich, D schlechter, E 67,5 % gegen 29,6 % |

- **`base+batched` verfehlt die Regel an einem Kriterium.** Der Wiederholungsanteil über das Segment liegt bei 1,0 % statt 0,7 % (zweite Sitzung 1,2 % statt 0,7 %). Die Einfügungen an den Referenzen sind dabei niedriger als bei `base`, die zusätzlichen Wiederholungen liegen also nicht in den Clips.
- **Der Abstand an B ist ein Wort.** 25,4 % gegen 25,6 % sind 112 gegen 113 Fehler. Gegen das Mittel von `base` (29,8 %) sind es 4,4 Punkte, weil `base` an B zwischen den Seeds um fast 10 Punkte streut.
- **Die Entscheidung über ein Umsetzungsticket fällt in Chunk 5** und liegt bei der Projektverantwortlichen, wie bei TOOL-103. Die Regel sagt nein, die Gegenprobe und die Blockverluste sprechen dafür.

### Blockverluste

Längste Folge ausgelassener Wörter je Seed (`omissions.py`):

| Referenz | `base` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- |
| A | 4 / 4 / 9 | 2 | 2 |
| B | 5 / 5 / 6 | 5 | 5 |
| C | 11 / 54 / 54 | 12 | 12 |
| D | 38 / 57 / 45 | 9 | 17 |
| E | 5 / 5 / 40 | 3 | 49 |

| Segment 1 | `base` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- |
| Pilotsitzung: Sprache ohne Wörter | 4,0 % | 4,7 % | 4,4 % |
| Pilotsitzung: Stellen ab 2 s | 59–62 | 67 | 67 |
| zweite Sitzung: Sprache ohne Wörter | 6,3–6,5 % | 4,8 % | 4,2 % |
| zweite Sitzung: Stellen ab 2 s | 103–114 | 62 | 40 |
| 5-min-Abschnitte mit Defizit gegen `base#1` (Pilot / zweite Sitzung) | 0 / 0–2 | 0 / 0 | 0 / 0 |

- **Die Blöcke aus TOOL-101 und TOOL-102 sind mit `base+batched` weg.** An C fehlten in zwei von drei Seeds 54 Wörter am Stück, an D in jedem Seed 38–57. Jetzt sind es höchstens 12 und 9. Kein 5-min-Abschnitt hat ein Defizit.
- **Der Gewinn kommt aus dem Zuschnitt, nicht aus dem fehlenden Fallback.** `base+temp0`, die Pipeline ohne Fallback, ist an vier von fünf Referenzen deutlich schlechter als `base`, mit 8,9 % Wiederholungsanteil und vier Abschnitten mit Defizit an der zweiten Sitzung. Ohne Fallback gerät der fortlaufende Decoder in Schleifen; je Stück dekodiert passiert das kaum.
- **Ohne Fallback bleibt ein misslungenes Stück stehen.** `loud+batched` hat an E 96 Auslassungen und 96 Einfügungen, die längste Folge sind 49 Wörter: Ein Stück ist entgleist, und nichts wiederholt es. `base+batched` zeigt das an keiner Referenz, der Wiederholungsanteil von 1,0–1,2 % deutet aber darauf, dass es anderswo im Segment vorkommt.
- **Die engere VAD kostet Wörter.** Die Batched-Pipeline behält 225,6 von 300,0 min (Pipeline: 241,3) und 207,0 von 286,9 min (222,6). In entferntem Audio liegen an C, D und E 24, 9 und 11 Referenzwörter (Pipeline: 20, 3 und 3), davon fehlen 12, 8 und 8. Das sind 11–20 % der Auslassungen von `base+batched` an diesen Referenzen. Eine Variante mit großzügigerer VAD ist nicht gemessen.

### Seeds, Laufzeit, Bewertung

- **Die drei Seeds sind identisch,** in jeder Batched-Variante und an beiden Sitzungen, bis auf das Wort. Die Streuung von `base` (an D 49–82 %, an C 80–177 Auslassungen) entfällt.
- **`base+batched` und `loud` landen fast gleich,** auf verschiedenen Wegen: A 19,6 / 20,2 %, B 25,4 / 26,5 %, C 25,9 / 23,9 %, D 36,3 / 36,7 %, E 29,0 / 29,6 %. Beide beseitigen die Blockverluste. Zusammen addieren sie sich nicht: `loud+batched` ist an A und C gleich gut oder leicht besser, an B, D und E schlechter.
- **`+ts` lohnt nicht.** An der Pilotsitzung gleich, an C 32,2 % statt 25,9 % mit 72 statt 34 Einfügungen, und doppelt so langsam.
- **Laufzeit und Speicher:** 0,33–0,38 min je Stunde Audio statt 1,25–1,42, also unter 2 min für ein 5-h-Segment statt 6–7 min. Peak-RAM 4,0–4,4 GiB statt 12,8–13,9, Peak-VRAM 4,6–4,8 GiB statt 3,6–4,3.
- **Die Bewertung passt nicht mehr.** Ohne Zeitstempel-Tokens ist jedes Stück eine Passage: 479 und 435 Passagen je Segment, davon 22 und 19 `confident`. An A und D liegen 15 und 44 Fehler in `confident`-Passagen (`base`: 0–5 und 5–10). Die Läufe sind nicht diarisiert, der Schnitt am Sprecherwechsel (TOOL-96) fehlt hier also; eine Umsetzung müsste Passagenzuschnitt und Schwellen neu prüfen.

### Offen nach dieser Messung

- Großzügigere VAD für die Batched-Pipeline (`speech_pad_ms`, `threshold`): 11–20 % ihrer Auslassungen an C, D und E liegen in entferntem Audio.
- Wo im Segment `base+batched` wiederholt, und ob sich ein entgleistes Stück erkennen und einzeln neu dekodieren lässt (Kompression, `avg_logprob`).
- `loud+batched` an E: Warum entgleist das Stück auf dem normalisierten Audio und nicht auf dem rohen?

## Messwerte

Die Tabellen kommen unverändert aus `asr.py score`. Nicht abgedruckt sind die Aufteilung nach Füllwörtern und der Sprecherfehler, der nur für diarisierte Wurzeln (`base`, `loud`) vorliegt.

### Pilotsitzung, Referenzen A, B, D und E

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 186e030dc24e | base, base+temp0, loud, base+batched, base+batched+ts, loud+batched |

| Variante | Seeds | Hotwords | WER A Mittel (Spanne) | Auslassungen A | WER B Mittel (Spanne) | Auslassungen B | WER D Mittel (Spanne) | Auslassungen D | WER E Mittel (Spanne) | Auslassungen E | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 21,3% (21,3%–21,3%) | 31/31/36 | 29,8% (25,6%–35,4%) | 44/42/45 | 61,2% (49,4%–81,5%) | 133/115/166 | 34,0% (29,8%–40,7%) | 43/46/78 | 33009 (32923–33067) | 0,7% (0,5%–0,8%) |
| base+temp0 | 3 | 48 | 29,8% (29,8%–29,8%) | 74/74/74 | 40,8% (40,8%–40,8%) | 100/100/100 | 52,8% (52,8%–52,8%) | 132/132/132 | 46,6% (46,6%–46,6%) | 55/55/55 | 33142 (33142–33142) | 8,9% (8,9%–8,9%) |
| loud | 3 | 48 | 20,2% (20,2%–20,2%) | 29/29/29 | 26,5% (26,5%–26,5%) | 42/42/42 | 36,7% (36,1%–38,1%) | 59/64/64 | 29,6% (29,5%–29,8%) | 30/30/30 | 33503 (33218–33672) | 0,6% (0,6%–0,7%) |
| base+batched | 3 | 48 | 19,6% (19,6%–19,6%) | 29/29/29 | 25,4% (25,4%–25,4%) | 38/38/38 | 36,3% (36,3%–36,3%) | 65/65/65 | 29,0% (29,0%–29,0%) | 40/40/40 | 32642 (32642–32642) | 1,0% (1,0%–1,0%) |
| base+batched+ts | 3 | 48 | 20,5% (20,5%–20,5%) | 32/32/32 | 25,4% (25,4%–25,4%) | 37/37/37 | 36,3% (36,3%–36,3%) | 55/55/55 | 28,7% (28,7%–28,7%) | 37/37/37 | 33134 (33134–33134) | 1,5% (1,5%–1,5%) |
| loud+batched | 3 | 48 | 18,8% (18,8%–18,8%) | 27/27/27 | 28,1% (28,1%–28,1%) | 39/39/39 | 38,3% (38,3%–38,3%) | 77/77/77 | 67,5% (67,5%–67,5%) | 96/96/96 | 32886 (32886–32886) | 1,7% (1,7%–1,7%) |

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) | WER D (E/A/Ei) | WER E (E/A/Ei) |
| --- | --- | --- | --- | --- |
| base#1 | 21,3% (65/31/17) | 25,6% (61/44/8) | 49,4% (77/133/12) | 29,8% (62/43/5) |
| base#2 | 21,3% (64/31/18) | 28,3% (67/42/16) | 52,6% (98/115/23) | 31,4% (62/46/8) |
| base#3 | 21,3% (61/36/16) | 35,4% (81/45/30) | 81,5% (86/166/114) | 40,7% (63/78/9) |
| base+temp0#1 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| base+temp0#2 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| base+temp0#3 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| loud#1 | 20,2% (61/29/17) | 26,5% (69/42/6) | 36,1% (93/59/10) | 29,5% (67/30/12) |
| loud#2 | 20,2% (61/29/17) | 26,5% (69/42/6) | 38,1% (87/64/20) | 29,8% (68/30/12) |
| loud#3 | 20,2% (61/29/17) | 26,5% (69/42/6) | 36,1% (85/64/13) | 29,5% (67/30/12) |
| base+batched#1 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched#2 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched#3 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched+ts#1 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| base+batched+ts#2 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| base+batched+ts#3 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| loud+batched#1 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |
| loud+batched#2 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |
| loud+batched#3 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen A | übersehen B | übersehen D | übersehen E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | 33067 | 0,8% | 14,5% | 699 / 1033 / 257 | 79,2% | 5 | 11 | 8 | 35 |
| base#2 | 33038 | 0,5% | 14,6% | 115 / 598 / 151 | 97,3% | 0 | 4 | 10 | 0 |
| base#3 | 32923 | 0,6% | 14,7% | 142 / 637 / 149 | 96,7% | 0 | 0 | 5 | 0 |
| base+temp0#1 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| base+temp0#2 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| base+temp0#3 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| loud#1 | 33620 | 0,6% | 13,9% | 777 / 1053 / 169 | 77,8% | 11 | 4 | 37 | 20 |
| loud#2 | 33672 | 0,7% | 13,8% | 202 / 598 / 110 | 95,0% | 0 | 0 | 2 | 0 |
| loud#3 | 33218 | 0,6% | 14,1% | 169 / 590 / 110 | 95,5% | 0 | 0 | 9 | 0 |
| base+batched#1 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched#2 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched#3 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched+ts#1 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| base+batched+ts#2 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| base+batched+ts#3 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| loud+batched#1 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |
| loud+batched#2 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |
| loud+batched#3 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |

| Lauf | ASR (min/h) | Diarisierung (min/h) | Peak-RAM (GiB) | Peak-VRAM (GiB, davor) |
| --- | --- | --- | --- | --- |
| base#1 | 1.25 | 0.77 | 13,9 | 4,0 (1,8) |
| base#2 | 1.28 | n/a | 13,9 | 3,6 (1,1) |
| base#3 | 1.30 | n/a | 13,8 | 3,6 (1,1) |
| base+temp0#1 | 0.98 | n/a | 13,9 | 3,8 (1,3) |
| base+temp0#2 | 0.98 | n/a | 13,9 | 3,7 (1,4) |
| base+temp0#3 | 0.99 | n/a | 13,9 | 3,7 (1,3) |
| loud#1 | 1.17 | 0.77 | 14,2 | 4,0 (1,6) |
| loud#2 | 1.19 | n/a | 14,1 | 4,0 (1,6) |
| loud#3 | 1.16 | n/a | 14,1 | 4,0 (1,6) |
| base+batched#1 | 0.38 | n/a | 4,4 | 4,8 (1,4) |
| base+batched#2 | 0.37 | n/a | 4,4 | 4,8 (1,5) |
| base+batched#3 | 0.37 | n/a | 4,3 | 4,8 (1,4) |
| base+batched+ts#1 | 0.71 | n/a | 4,3 | 4,7 (1,4) |
| base+batched+ts#2 | 0.66 | n/a | 4,3 | 4,7 (1,3) |
| base+batched+ts#3 | 0.66 | n/a | 4,3 | 4,7 (1,3) |
| loud+batched#1 | 0.35 | n/a | 4,4 | 4,7 (1,3) |
| loud+batched#2 | 0.38 | n/a | 4,3 | 4,6 (1,3) |
| loud+batched#3 | 0.38 | n/a | 4,3 | 4,6 (1,3) |

### Zweite Sitzung, Referenz C

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 8c3c941c5688 | base, base+temp0, loud, base+batched, base+batched+ts, loud+batched |

| Variante | Seeds | Hotwords | WER C Mittel (Spanne) | Auslassungen C | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 30,8% (27,3%–33,3%) | 80/156/177 | 28927 (28896–28960) | 0,7% (0,5%–0,9%) |
| base+temp0 | 3 | 48 | 47,9% (47,9%–47,9%) | 231/231/231 | 27872 (27872–27872) | 9,2% (9,2%–9,2%) |
| loud | 3 | 48 | 23,9% (23,2%–24,8%) | 88/92/88 | 29878 (29767–30021) | 0,4% (0,4%–0,5%) |
| base+batched | 3 | 48 | 25,9% (25,9%–25,9%) | 110/110/110 | 29450 (29450–29450) | 1,2% (1,2%–1,2%) |
| base+batched+ts | 3 | 48 | 32,2% (32,2%–32,2%) | 127/127/127 | 30031 (30031–30031) | 2,6% (2,6%–2,6%) |
| loud+batched | 3 | 48 | 23,7% (23,7%–23,7%) | 97/97/97 | 29974 (29974–29974) | 1,6% (1,6%–1,6%) |

| Lauf | WER C (E/A/Ei) |
| --- | --- |
| base#1 | 27,3% (111/80/57) |
| base#2 | 31,9% (110/156/24) |
| base#3 | 33,3% (93/177/33) |
| base+temp0#1 | 47,9% (126/231/78) |
| base+temp0#2 | 47,9% (126/231/78) |
| base+temp0#3 | 47,9% (126/231/78) |
| loud#1 | 23,9% (107/88/22) |
| loud#2 | 24,8% (112/92/21) |
| loud#3 | 23,2% (105/88/18) |
| base+batched#1 | 25,9% (91/110/34) |
| base+batched#2 | 25,9% (91/110/34) |
| base+batched#3 | 25,9% (91/110/34) |
| base+batched+ts#1 | 32,2% (94/127/72) |
| base+batched+ts#2 | 32,2% (94/127/72) |
| base+batched+ts#3 | 32,2% (94/127/72) |
| loud+batched#1 | 23,7% (92/97/26) |
| loud+batched#2 | 23,7% (92/97/26) |
| loud+batched#3 | 23,7% (92/97/26) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen C |
| --- | --- | --- | --- | --- | --- | --- |
| base#1 | 28960 | 0,6% | 15,5% | 565 / 919 / 337 | 80,9% | 77 |
| base#2 | 28896 | 0,5% | 15,9% | 140 / 505 / 216 | 96,1% | 6 |
| base#3 | 28926 | 0,9% | 15,8% | 168 / 555 / 218 | 95,7% | 6 |
| base+temp0#1 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| base+temp0#2 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| base+temp0#3 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| loud#1 | 29846 | 0,5% | 14,7% | 681 / 964 / 245 | 79,7% | 67 |
| loud#2 | 30021 | 0,5% | 14,7% | 183 / 548 / 108 | 95,7% | 28 |
| loud#3 | 29767 | 0,4% | 14,7% | 219 / 562 / 149 | 95,0% | 28 |
| base+batched#1 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched#2 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched#3 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched+ts#1 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| base+batched+ts#2 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| base+batched+ts#3 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| loud+batched#1 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |
| loud+batched#2 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |
| loud+batched#3 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |

| Lauf | ASR (min/h) | Diarisierung (min/h) | Peak-RAM (GiB) | Peak-VRAM (GiB, davor) |
| --- | --- | --- | --- | --- |
| base#1 | 1.30 | 0.74 | 0,2 | 1,3 (1,3) |
| base#2 | 1.42 | n/a | 12,8 | 3,9 (1,3) |
| base#3 | 1.42 | n/a | 12,8 | 4,3 (1,3) |
| base+temp0#1 | 0.98 | n/a | 12,9 | 3,6 (1,3) |
| base+temp0#2 | 0.98 | n/a | 13,0 | 3,6 (1,3) |
| base+temp0#3 | 0.97 | n/a | 13,0 | 3,6 (1,3) |
| loud#1 | 1.14 | 0.76 | 13,1 | 4,0 (1,6) |
| loud#2 | 1.17 | n/a | 13,1 | 4,0 (1,6) |
| loud#3 | 1.16 | n/a | 13,1 | 4,0 (1,6) |
| base+batched#1 | 0.34 | n/a | 4,0 | 4,6 (1,3) |
| base+batched#2 | 0.34 | n/a | 4,1 | 4,6 (1,3) |
| base+batched#3 | 0.33 | n/a | 4,0 | 4,6 (1,3) |
| base+batched+ts#1 | 0.64 | n/a | 4,1 | 4,6 (1,3) |
| base+batched+ts#2 | 0.67 | n/a | 4,0 | 4,8 (1,3) |
| base+batched+ts#3 | 0.72 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#1 | 0.34 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#2 | 0.35 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#3 | 0.37 | n/a | 4,1 | 4,6 (1,3) |
