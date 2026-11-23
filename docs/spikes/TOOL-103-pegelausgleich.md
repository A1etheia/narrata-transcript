# TOOL-103 — Pegelausgleich vor der Erkennung

Stand 2026-11-23. Spike-Bericht zu [TOOL-103](../plans/TOOL-103-level-normalization.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py) und [`scripts/spike/omissions.py`](../../scripts/spike/omissions.py). Alle Filter und Läufe liefen lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Zwischenstand

Gemessen sind die fünf Kandidaten an allen fünf Referenzen. Der beste Kandidat nach der vorab festgelegten Regel ist `loud` ([Auswahl](#auswahl-des-besten-kandidaten)). Es fehlen noch: `loud` mit Hochpass, der Sprecherfehler, die Auslassungen je Sprecher und die Entscheidung Go oder No-Go.

## Material und Methode

| | |
| --- | --- |
| Aufnahmen | Segment 1 der Pilotsitzung (5:00:00) und der zweiten Sitzung (4:46:51), 16 kHz mono |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |
| Referenz D | Pilotsitzung, 0:43:00–0:46:00, 449 Wörter |
| Referenz E | Pilotsitzung, 1:23:00–1:26:00, 369 Wörter |
| Pipeline | `transcript transcribe` unverändert, Whisper large-v3-turbo (Revision 0a363e9161cb) mit Hotwords |
| Seeds | 1–3 je Kandidat und Sitzung; `base` sind die gespeicherten Läufe aus TOOL-93 |
| Filter | ffmpeg 4.4.2, einmal je Kette und Sitzung, alle Seeds lesen dasselbe WAV |

- **Prüfstand ist `asr.py`.** Das Ticket nennt `denoise.py`, Seeds und Referenz C gibt es aber nur in `asr.py`. Die Kandidaten sind dort Basen mit Filterkette, also die Pipeline wie sie ist plus Filter.
- **Zeitachse.** Jede Kette endet auf der Frame-Zahl des Manifests. `prepare` misst zusätzlich den Versatz der Hüllkurve gegen das Roh-WAV an drei Stellen und bricht über 10 ms ab.
- **`loudnorm` zweistufig.** Der erste Durchgang misst die Aufnahme, der zweite bekommt die Messwerte. Beide Aufnahmen haben einen Lautheitsumfang über dem Zielwert (16,0 und 17,6 LU gegen 11 LU) und Spitzen über 0 dBTP. ffmpeg kann deshalb nicht mit fester Verstärkung arbeiten und regelt dynamisch.
- **Abweichung vom Plan.** Der Plan hatte `loud` auch als Kontrolle mit fester Verstärkung vorgesehen. Das ist es nicht, die Verstärkung schwankt je Sekunde um rund 9 dB. Eine Kontrolle mit fester Verstärkung fehlt in dieser Messung.
- **Grenzen.** Je Referenz gibt es 369–909 Wörter und drei Seeds. An D und E gibt es keine Sprecher in der Auswertung, sie sind Gegenprobe für die WER.

## Kandidaten

Die Parameter standen vor der Messung fest (Plan). Verstärkung ist der Median der Verstärkung je Sekunde gegen das Roh-WAV, in Klammern das 10. und 90. Perzentil.

| Kandidat | Kette | Verstärkung Pilotsitzung | Verstärkung zweite Sitzung | Versatz | Filterzeit je Segment |
| --- | --- | --- | --- | --- | --- |
| `base` | Roh-WAV | — | — | — | — |
| `dyn` | `dynaudnorm=f=500:g=31:m=5` | 4,8 dB (−0,1 bis 7,9) | 9,6 dB (6,0 bis 13,5) | 0 ms | 2 s |
| `dynx` | `dynaudnorm=f=200:g=11:m=30` | 11,7 dB (3,9 bis 21,3) | 17,3 dB (9,3 bis 27,0) | 0 ms | 2 s |
| `comp` | `acompressor=threshold=0.05:ratio=4:attack=5:release=200:makeup=4,alimiter=limit=0.95:level=false` | 8,9 dB (3,8 bis 12,0) | 11,5 dB (5,9 bis 12,1) | 5 ms | 6 s |
| `loud` | `loudnorm=I=-16:TP=-1.5:LRA=11`, zweistufig | 12,6 dB (8,0 bis 17,0) | 15,6 dB (11,7 bis 19,4) | 0 ms | 295 s und 278 s |
| `spn` | `speechnorm=e=12.5:r=0.0001:l=1` | 9,1 dB (3,8 bis 12,6) | 13,1 dB (8,3 bis 18,9) | 0 ms | 3 s |

Kein gefiltertes WAV hat Samples am Vollausschlag. Messwerte des ersten `loudnorm`-Durchgangs:

| Sitzung | Lautheit | Lautheitsumfang | Spitze | Schwelle | Offset |
| --- | --- | --- | --- | --- | --- |
| Pilotsitzung | −26,6 LUFS | 16,0 LU | +1,9 dBTP | −38,9 LUFS | 2,1 LU |
| zweite Sitzung | −26,5 LUFS | 17,6 LU | +2,0 dBTP | −38,9 LUFS | 2,4 LU |

## Ergebnisse

### Überblick

WER als Mittel über drei Seeds, in Klammern die Spanne. Die Zahlen stammen aus den Tabellen unter [Messwerte](#messwerte).

| Kandidat | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| `base` | 21,3 % (21,3–21,3) | 29,8 % (25,6–35,4) | 30,8 % (27,3–33,3) | 61,2 % (49,4–81,5) | 34,0 % (29,8–40,7) |
| `dyn` | 32,3 % (20,9–45,4) | 26,8 % (26,5–27,0) | 31,3 % (29,8–33,0) | 35,6 % (34,5–37,4) | 29,5 % (28,7–31,2) |
| `dynx` | 22,1 % (21,3–22,8) | 26,5 % (26,5–26,5) | 29,7 % (29,4–29,9) | 41,0 % (38,3–46,1) | 29,3 % (29,3–29,3) |
| `comp` | 22,4 % (22,4–22,4) | 37,2 % (27,0–46,7) | 31,7 % (30,3–33,0) | 36,1 % (36,1–36,1) | 36,5 % (31,7–41,7) |
| `loud` | 20,2 % (20,2–20,2) | 26,5 % (26,5–26,5) | 23,9 % (23,2–24,8) | 36,7 % (36,1–38,1) | 29,6 % (29,5–29,8) |
| `spn` | 20,9 % (20,0–21,7) | 29,7 % (29,7–29,7) | 25,6 % (25,2–26,0) | 37,3 % (35,6–38,8) | 31,7 % (31,7–31,7) |

Auslassungen als Mittel über drei Seeds:

| Kandidat | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| `base` | 32,7 | 43,7 | 137,7 | 138,0 | 55,7 |
| `dyn` | 68,0 | 46,3 | 153,0 | 62,7 | 48,7 |
| `dynx` | 39,3 | 40,0 | 137,3 | 64,7 | 33,0 |
| `comp` | 31,0 | 89,0 | 148,0 | 60,0 | 66,7 |
| `loud` | 29,0 | 42,0 | 89,3 | 62,3 | 30,0 |
| `spn` | 35,0 | 44,0 | 96,3 | 63,3 | 53,0 |

- **D gewinnt mit jedem Kandidaten.** Die Auslassungen halbieren sich von 115–166 auf 58–70 je Seed, und der schlechteste Lauf jedes Kandidaten (höchstens 46,1 %) liegt unter dem besten von `base` (49,4 %).
- **A und B bewegen sich kaum.** An A liegt kein Kandidat mehr als 1,1 Punkte unter `base`. An B liegen `dyn`, `dynx` und `loud` im Mittel 3 Punkte darunter, aber über dem besten `base`-Lauf (25,6 %).
- **C gewinnt nur mit `loud` und `spn`.** Beide liegen mit allen Seeds unter dem besten `base`-Lauf, die Auslassungen fallen von 80–177 auf 88–105. `dyn`, `dynx` und `comp` bleiben auf dem Niveau von `base`.
- **Zwei Kandidaten verlieren Blöcke, die `base` nicht verliert.** `dyn` an A in zwei von drei Seeds (87 und 89 Auslassungen gegen 28), `comp` an B und E (bis 129 und 101 Auslassungen).
- **`loud` und `dynx` sind zwischen den Seeds am stabilsten.** `loud` liefert an A und B in allen drei Seeds dasselbe Ergebnis, an C, D und E liegt die Spanne bei höchstens 2,0 Punkten. `base` streut an B um 9,8 und an D um 32,1 Punkte.
- **Die Bewertung verschiebt sich.** Alle Kandidaten außer `dyn` haben mehr `confident`-Passagen als `base` (Pilotsitzung: 169–261 gegen 115–142). Die übersehenen Fehler an D steigen bei den meisten Läufen, an C liegt `loud` bei 28 in jedem Seed gegen 27/6/6. Auf gefiltertem Audio wäre die Bewertung neu zu kalibrieren.
- **Wiederholung und Wortzahl.** Kein Kandidat hat einen höheren Wiederholungsanteil als `base`. `loud` liefert 1,5 % (Pilotsitzung) und 3,3 % (zweite Sitzung) mehr Wörter über das Segment.

### Auswahl des besten Kandidaten

Die Regel aus dem Plan: kleinstes Mittel der WER über A und B unter den Kandidaten, deren Einfügungen und Wiederholungsanteil im Mittel nicht über `base` liegen. Einfügungen sind hier das Mittel der drei Seeds, gemittelt über A und B.

| Kandidat | WER, Mittel über A und B | Einfügungen A | Einfügungen B | Einfügungen, Mittel | Wiederholung Pilotsitzung | zugelassen |
| --- | --- | --- | --- | --- | --- | --- |
| `base` | 25,6 % | 17,0 | 18,0 | 17,5 | 0,7 % | — |
| `dyn` | 29,6 % | 45,3 | 7,3 | 26,3 | 0,5 % | nein |
| `dynx` | 24,3 % | 12,7 | 5,0 | 8,8 | 0,5 % | ja |
| `comp` | 29,8 % | 23,0 | 6,3 | 14,7 | 0,5 % | ja |
| `loud` | 23,4 % | 17,0 | 6,0 | 11,5 | 0,6 % | ja |
| `spn` | 25,3 % | 15,7 | 16,0 | 15,8 | 0,4 % | ja |

**Bester Kandidat ist `loud`.** Er hat das kleinste Mittel über A und B und ist zugleich an C der beste. Mit Hochpass wird deshalb `loud-hp` gemessen.

## Messwerte

Die Tabellen stammen unverändert aus `asr.py score`. Weggelassen sind die Tabellen zu Füllwörtern und Ressourcen sowie bei D und E die Spalten, die schon in der Tabelle zu A und B stehen. E/A/Ei sind Ersetzungen, Auslassungen und Einfügungen.

### Pilotsitzung, A und B

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 186e030dc24e | base, dyn, dynx, comp, loud, spn |

| Variante | Seeds | Hotwords | WER A Mittel (Spanne) | Auslassungen A | WER B Mittel (Spanne) | Auslassungen B | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 21,3% (21,3%–21,3%) | 31/31/36 | 29,8% (25,6%–35,4%) | 44/42/45 | 33009 (32923–33067) | 0,7% (0,5%–0,8%) |
| dyn | 3 | 48 | 32,3% (20,9%–45,4%) | 28/87/89 | 26,8% (26,5%–27,0%) | 51/37/51 | 32734 (32664–32870) | 0,5% (0,4%–0,5%) |
| dynx | 3 | 48 | 22,1% (21,3%–22,8%) | 35/42/41 | 26,5% (26,5%–26,5%) | 40/40/40 | 33489 (33437–33559) | 0,5% (0,4%–0,8%) |
| comp | 3 | 48 | 22,4% (22,4%–22,4%) | 31/31/31 | 37,2% (27,0%–46,7%) | 129/48/90 | 32987 (32944–33057) | 0,5% (0,5%–0,6%) |
| loud | 3 | 48 | 20,2% (20,2%–20,2%) | 29/29/29 | 26,5% (26,5%–26,5%) | 42/42/42 | 33503 (33218–33672) | 0,6% (0,6%–0,7%) |
| spn | 3 | 48 | 20,9% (20,0%–21,7%) | 35/39/31 | 29,7% (29,7%–29,7%) | 44/44/44 | 33043 (32980–33114) | 0,4% (0,4%–0,5%) |

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) |
| --- | --- | --- |
| base#1 | 21,3% (65/31/17) | 25,6% (61/44/8) |
| base#2 | 21,3% (64/31/18) | 28,3% (67/42/16) |
| base#3 | 21,3% (61/36/16) | 35,4% (81/45/30) |
| dyn#1 | 20,9% (61/28/22) | 27,0% (61/51/7) |
| dyn#2 | 30,7% (62/87/14) | 26,5% (72/37/8) |
| dyn#3 | 45,4% (52/89/100) | 27,0% (61/51/7) |
| dynx#1 | 21,3% (65/35/13) | 26,5% (72/40/5) |
| dynx#2 | 22,2% (66/42/10) | 26,5% (72/40/5) |
| dynx#3 | 22,8% (65/41/15) | 26,5% (72/40/5) |
| comp#1 | 22,4% (65/31/23) | 46,7% (73/129/4) |
| comp#2 | 22,4% (65/31/23) | 27,0% (64/48/7) |
| comp#3 | 22,4% (65/31/23) | 37,9% (69/90/8) |
| loud#1 | 20,2% (61/29/17) | 26,5% (69/42/6) |
| loud#2 | 20,2% (61/29/17) | 26,5% (69/42/6) |
| loud#3 | 20,2% (61/29/17) | 26,5% (69/42/6) |
| spn#1 | 20,0% (58/35/13) | 29,7% (71/44/16) |
| spn#2 | 21,7% (59/39/17) | 29,7% (71/44/16) |
| spn#3 | 21,1% (64/31/17) | 29,7% (71/44/16) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen A | übersehen B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | 33067 | 0,8% | 14,5% | 133 / 597 / 138 | 96,8% | 0 | 0 |
| base#2 | 33038 | 0,5% | 14,6% | 115 / 598 / 151 | 97,3% | 0 | 4 |
| base#3 | 32923 | 0,6% | 14,7% | 142 / 637 / 149 | 96,7% | 0 | 0 |
| dyn#1 | 32667 | 0,5% | 14,2% | 137 / 566 / 117 | 96,3% | 0 | 8 |
| dyn#2 | 32664 | 0,5% | 14,1% | 141 / 565 / 126 | 96,4% | 0 | 0 |
| dyn#3 | 32870 | 0,4% | 14,5% | 244 / 561 / 146 | 94,0% | 0 | 8 |
| dynx#1 | 33437 | 0,8% | 13,9% | 261 / 590 / 103 | 94,0% | 0 | 0 |
| dynx#2 | 33472 | 0,4% | 13,8% | 247 / 584 / 88 | 94,4% | 0 | 0 |
| dynx#3 | 33559 | 0,4% | 14,0% | 257 / 569 / 103 | 93,5% | 0 | 0 |
| comp#1 | 32959 | 0,6% | 14,4% | 217 / 588 / 145 | 94,4% | 0 | 19 |
| comp#2 | 33057 | 0,6% | 14,4% | 186 / 576 / 125 | 94,8% | 0 | 7 |
| comp#3 | 32944 | 0,5% | 14,7% | 185 / 553 / 173 | 94,6% | 0 | 19 |
| loud#1 | 33620 | 0,6% | 13,9% | 192 / 594 / 91 | 96,1% | 0 | 0 |
| loud#2 | 33672 | 0,7% | 13,8% | 202 / 598 / 110 | 95,0% | 0 | 0 |
| loud#3 | 33218 | 0,6% | 14,1% | 169 / 590 / 110 | 95,5% | 0 | 0 |
| spn#1 | 33034 | 0,4% | 14,1% | 239 / 609 / 145 | 94,9% | 0 | 0 |
| spn#2 | 33114 | 0,4% | 13,8% | 258 / 605 / 118 | 94,6% | 0 | 0 |
| spn#3 | 32980 | 0,5% | 14,0% | 247 / 578 / 87 | 94,6% | 0 | 0 |

### Pilotsitzung, D und E

| Variante | Seeds | Hotwords | WER D Mittel (Spanne) | Auslassungen D | WER E Mittel (Spanne) | Auslassungen E |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 61,2% (49,4%–81,5%) | 133/115/166 | 34,0% (29,8%–40,7%) | 43/46/78 |
| dyn | 3 | 48 | 35,6% (34,5%–37,4%) | 62/63/63 | 29,5% (28,7%–31,2%) | 47/52/47 |
| dynx | 3 | 48 | 41,0% (38,3%–46,1%) | 68/65/61 | 29,3% (29,3%–29,3%) | 33/33/33 |
| comp | 3 | 48 | 36,1% (36,1%–36,1%) | 60/60/60 | 36,5% (31,7%–41,7%) | 63/36/101 |
| loud | 3 | 48 | 36,7% (36,1%–38,1%) | 59/64/64 | 29,6% (29,5%–29,8%) | 30/30/30 |
| spn | 3 | 48 | 37,3% (35,6%–38,8%) | 70/62/58 | 31,7% (31,7%–31,7%) | 53/53/53 |

| Lauf | WER D (E/A/Ei) | WER E (E/A/Ei) | übersehen D | übersehen E |
| --- | --- | --- | --- | --- |
| base#1 | 49,4% (77/133/12) | 29,8% (62/43/5) | 0 | 0 |
| base#2 | 52,6% (98/115/23) | 31,4% (62/46/8) | 10 | 0 |
| base#3 | 81,5% (86/166/114) | 40,7% (63/78/9) | 5 | 0 |
| dyn#1 | 37,4% (96/62/10) | 28,7% (52/47/7) | 32 | 0 |
| dyn#2 | 35,0% (77/63/17) | 31,2% (58/52/5) | 7 | 0 |
| dyn#3 | 34,5% (77/63/15) | 28,7% (52/47/7) | 7 | 0 |
| dynx#1 | 38,3% (84/68/20) | 29,3% (68/33/7) | 19 | 6 |
| dynx#2 | 38,5% (89/65/19) | 29,3% (68/33/7) | 12 | 6 |
| dynx#3 | 46,1% (99/61/47) | 29,3% (68/33/7) | 18 | 6 |
| comp#1 | 36,1% (85/60/17) | 36,0% (62/63/8) | 16 | 0 |
| comp#2 | 36,1% (85/60/17) | 31,7% (69/36/12) | 16 | 0 |
| comp#3 | 36,1% (85/60/17) | 41,7% (49/101/4) | 16 | 0 |
| loud#1 | 36,1% (93/59/10) | 29,5% (67/30/12) | 14 | 0 |
| loud#2 | 38,1% (87/64/20) | 29,8% (68/30/12) | 2 | 0 |
| loud#3 | 36,1% (85/64/13) | 29,5% (67/30/12) | 9 | 0 |
| spn#1 | 38,8% (77/70/27) | 31,7% (62/53/2) | 10 | 0 |
| spn#2 | 37,6% (83/62/24) | 31,7% (62/53/2) | 5 | 0 |
| spn#3 | 35,6% (86/58/16) | 31,7% (62/53/2) | 8 | 0 |

### Zweite Sitzung, C

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 8c3c941c5688 | base, dyn, dynx, comp, loud, spn |

| Variante | Seeds | Hotwords | WER C Mittel (Spanne) | Auslassungen C | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 30,8% (27,3%–33,3%) | 80/156/177 | 28927 (28896–28960) | 0,7% (0,5%–0,9%) |
| dyn | 3 | 48 | 31,3% (29,8%–33,0%) | 143/136/180 | 29407 (28899–29810) | 0,6% (0,5%–0,6%) |
| dynx | 3 | 48 | 29,7% (29,4%–29,9%) | 139/136/137 | 29759 (29511–30048) | 0,5% (0,3%–0,7%) |
| comp | 3 | 48 | 31,7% (30,3%–33,0%) | 157/153/134 | 29590 (29469–29654) | 0,5% (0,4%–0,6%) |
| loud | 3 | 48 | 23,9% (23,2%–24,8%) | 88/92/88 | 29878 (29767–30021) | 0,4% (0,4%–0,5%) |
| spn | 3 | 48 | 25,6% (25,2%–26,0%) | 94/105/90 | 29697 (29616–29771) | 0,5% (0,3%–0,8%) |

| Lauf | WER C (E/A/Ei) |
| --- | --- |
| base#1 | 27,3% (111/80/57) |
| base#2 | 31,9% (110/156/24) |
| base#3 | 33,3% (93/177/33) |
| dyn#1 | 31,1% (117/143/23) |
| dyn#2 | 29,8% (115/136/20) |
| dyn#3 | 33,0% (99/180/21) |
| dynx#1 | 29,8% (99/139/33) |
| dynx#2 | 29,4% (109/136/22) |
| dynx#3 | 29,9% (104/137/31) |
| comp#1 | 33,0% (113/157/30) |
| comp#2 | 31,9% (109/153/28) |
| comp#3 | 30,3% (112/134/29) |
| loud#1 | 23,9% (107/88/22) |
| loud#2 | 24,8% (112/92/21) |
| loud#3 | 23,2% (105/88/18) |
| spn#1 | 25,5% (104/94/34) |
| spn#2 | 26,0% (96/105/35) |
| spn#3 | 25,2% (107/90/32) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen C |
| --- | --- | --- | --- | --- | --- | --- |
| base#1 | 28960 | 0,6% | 15,5% | 148 / 565 / 231 | 96,1% | 27 |
| base#2 | 28896 | 0,5% | 15,9% | 140 / 505 / 216 | 96,1% | 6 |
| base#3 | 28926 | 0,9% | 15,8% | 168 / 555 / 218 | 95,7% | 6 |
| dyn#1 | 29513 | 0,6% | 15,1% | 169 / 570 / 176 | 95,9% | 29 |
| dyn#2 | 29810 | 0,6% | 15,4% | 215 / 548 / 180 | 94,7% | 25 |
| dyn#3 | 28899 | 0,5% | 15,2% | 200 / 544 / 160 | 95,4% | 11 |
| dynx#1 | 30048 | 0,7% | 14,8% | 232 / 588 / 160 | 95,5% | 11 |
| dynx#2 | 29719 | 0,5% | 14,6% | 237 / 624 / 174 | 95,2% | 8 |
| dynx#3 | 29511 | 0,3% | 14,8% | 267 / 614 / 184 | 94,8% | 11 |
| comp#1 | 29648 | 0,6% | 15,4% | 163 / 530 / 191 | 95,5% | 1 |
| comp#2 | 29469 | 0,4% | 15,6% | 159 / 514 / 160 | 94,3% | 37 |
| comp#3 | 29654 | 0,5% | 15,5% | 139 / 558 / 197 | 95,6% | 41 |
| loud#1 | 29846 | 0,5% | 14,7% | 214 / 561 / 154 | 95,7% | 28 |
| loud#2 | 30021 | 0,5% | 14,7% | 183 / 548 / 108 | 95,7% | 28 |
| loud#3 | 29767 | 0,4% | 14,7% | 219 / 562 / 149 | 95,0% | 28 |
| spn#1 | 29705 | 0,3% | 15,0% | 231 / 559 / 155 | 94,4% | 0 |
| spn#2 | 29616 | 0,8% | 14,9% | 188 / 540 / 137 | 95,5% | 9 |
| spn#3 | 29771 | 0,5% | 14,9% | 160 / 534 / 132 | 96,0% | 0 |
