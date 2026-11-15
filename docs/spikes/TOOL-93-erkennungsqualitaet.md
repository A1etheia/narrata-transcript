# TOOL-93 — Erkennungsqualität an den Pilot-Handreferenzen

Stand 2026-11-14. Spike-Bericht zu [TOOL-93](../plans/TOOL-93-asr-quality.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py). Alle Läufe liefen lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

*Folgt nach Stufe 4.*

## Material und Methode

| | |
| --- | --- |
| Aufnahme | Segment 1 der Pilotsitzung, 5:00:00, 16 kHz mono |
| Referenz A | 0:00:00–0:04:06, 551 Wörter, 3 Sprecher (WER, für Finalisten auch WDER) |
| Referenz B | 1:20:00–1:23:00, 489 Wörter, ohne Sprecher (nur WER) |
| Pipeline | `transcript transcribe --no-diarize`, sonst unverändert: ASR, Hinweise, Bewertung. Whisper über faster-whisper 1.2.1, CTranslate2 4.8.5 |
| Hardware | RTX 3080 Ti (12 GB VRAM), 20 Threads, 25 GB RAM in WSL2 |
| Wiederholungen | Seeds 1–3 pro Variante |

Jede Variante bekommt pro Seed eine eigene Wurzel (`paths.root`) mit Kopien von Manifest, Audio-Metadaten und Wissens-Snapshot und einem Hardlink auf das WAV. Ein Wrapper um die CLI setzt vor der Transkription `ctranslate2.set_random_seed(<seed>)`, schaltet bei Bedarf die Hotwords ab und ergänzt die Whisper-Settings. `seed`, `hotwords` und die Overrides stehen in `asr.settings` des Transkripts, `score` prüft sie gegen die Variante. Innerhalb einer Variante müssen Modell-Revision und Snapshot gleich sein.

Gemessen wird wie in TOOL-92:

- WER über `calibration.measure`, also wie `transcript calibrate`
- Wortzahl und Wiederholungsanteil (5-Wort-Folgen, die mindestens dreimal vorkommen) über das ganze Segment
- Bewertung: Passagen je Stufe, markierte Zeit und die Fehler, die in `confident`-Passagen liegen („übersehen“)
- Laufzeit der ASR pro Stunde Audio, Peak-RAM des Kindprozesses (`os.wait4`) und Peak-VRAM der ganzen GPU (`nvidia-smi` im Sekundentakt)

### Seed

Derselbe Seed in zwei getrennten Wurzeln (`base` und `base+twin`) ergibt an A und B exakt dieselbe Zählung, Wort für Wort dieselbe Wortzahl und dieselben Stufen. Ein Lauf ist damit auf der GPU reproduzierbar. Die Streuung zwischen Läufen bleibt aber, sie hängt jetzt am Seed statt am Zufall: Mit Hotwords liegen die drei Seeds von `base` an B zwischen 32,9 % und 41,1 %. Deshalb läuft jede Variante weiter mit drei Seeds.

## Stufe 1: Hotwords

| Variante | Hotwords | Wirkung |
| --- | --- | --- |
| `base` | 48 (alle, die ins Token-Budget passen) | wie die Pipeline |
| `pchw` | 9 (nur die 3 `pc`-Einträge mit Namen und Aliasen) | jedes Budget in `knowledge.keyword_budget` auf 0, Snapshot neu gebaut |
| `nohw` | 0 | Hotwords abgeschaltet |
| `nohw-hp` | 0 | dazu `highpass=f=80` (Kandidat aus TOOL-92) |

### Wortlaut

Mittel und Spanne über drei Seeds. Auslassungen je Seed:

| Variante | WER A | Auslassungen A | WER B | Auslassungen B | Wörter Segment | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| `base` | **24,0 %** (24,0–24,0) | 50 / 50 / 55 | 36,1 % (32,9–41,1) | 92 / 84 / 90 | 33009 (32923–33067) | 0,7 % (0,5–0,8) |
| `pchw` | 35,5 % (26,0–47,5) | 107 / 146 / 64 | 86,6 % (73,6–96,1) | 265 / 270 / 273 | 27941 (27744–28055) | 3,3 % (2,1–4,4) |
| `nohw` | 28,3 % (28,3–28,3) | 72 / 72 / 72 | **35,0 %** (35,0–35,0) | 93 / 93 / 93 | 32617 | 0,3 % |
| `nohw-hp` | 28,1 % (28,1–28,1) | 71 / 71 / 71 | 40,4 % (39,7–40,7) | 131 / 127 / 131 | 32495 (32425–32548) | 0,2 % (0,1–0,2) |

Ersetzungen / Auslassungen / Einfügungen je Lauf:

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) |
| --- | --- | --- |
| base#1 | 24,0 % (66/50/16) | 32,9 % (61/92/8) |
| base#2 | 24,0 % (65/50/17) | 34,2 % (73/84/10) |
| base#3 | 24,0 % (62/55/15) | 41,1 % (84/90/27) |
| pchw#1 | 33,0 % (66/107/9) | 73,6 % (91/265/4) |
| pchw#2 | 47,5 % (58/146/58) | 96,1 % (112/270/88) |
| pchw#3 | 26,0 % (68/64/11) | 90,0 % (71/273/96) |
| nohw#1–3 | 28,3 % (68/72/16) | 35,0 % (69/93/9) |
| nohw-hp#1 | 28,1 % (69/71/15) | 40,7 % (57/131/11) |
| nohw-hp#2 | 28,1 % (69/71/15) | 39,7 % (57/127/10) |
| nohw-hp#3 | 28,1 % (69/71/15) | 40,7 % (57/131/11) |

### Bewertung

| Lauf | Passagen | confident / needs_review / uncertain | markierte Zeit | übersehen A | übersehen B |
| --- | --- | --- | --- | --- | --- |
| base#1 | 868 | 132 / 598 / 138 | 96,9 % | 0 | 4 |
| base#2 | 864 | 114 / 599 / 151 | 97,3 % | 0 | 7 |
| base#3 | 928 | 142 / 637 / 149 | 96,7 % | 0 | 0 |
| pchw#1 | 1734 | 539 / 747 / 448 | 76,9 % | 38 | 5 |
| pchw#2 | 1794 | 562 / 787 / 445 | 78,7 % | 26 | 0 |
| pchw#3 | 1846 | 617 / 762 / 467 | 75,4 % | 36 | 14 |
| nohw#1–3 | 3703 | 2600 / 933 / 170 | 38,7 % | 114 | 89 |
| nohw-hp#1 | 3636 | 2495 / 946 / 195 | 40,8 % | 118 | 92 |
| nohw-hp#2 | 3635 | 2529 / 920 / 186 | 39,9 % | 118 | 97 |
| nohw-hp#3 | 3660 | 2536 / 929 / 195 | 39,7 % | 118 | 92 |

### Laufzeit und Speicher

| Variante | ASR (min/h) | Peak-RAM | Peak-VRAM (davor) |
| --- | --- | --- | --- |
| `base` | 1,25–1,30 | 13,8–13,9 GiB | 3,6–4,0 GiB (1,1–1,8) |
| `pchw` | 2,53–2,66 | 13,8–13,9 GiB | 3,6–4,3 GiB (1,1–1,6) |
| `nohw` | 1,09–1,12 | 13,8–13,9 GiB | 3,5–4,1 GiB (1,1–1,6) |
| `nohw-hp` | 1,08–1,10 | 13,8 GiB | 3,6–3,7 GiB (1,1–1,2) |

### Zwischenbewertung

- **`base` passt zu TOOL-92.** Mit 24,0 % an A und 36,1 % (32,9–41,1) an B liegt es in derselben Größenordnung wie dort (24,2 % bzw. 33,7–46,6 %).
- **`base` bleibt.** Keine Variante liegt an A und B mindestens 3 Punkte darunter. `base` ist an A klar am besten und an allen drei Seeds gleich, an B streut es um 8 Punkte.
- **`pchw` scheidet aus.** Die kurze Liste mit 9 Hotwords ist an beiden Clips die schlechteste Variante. Sie verliert rund 15 % der Wörter über das Segment, an B fehlt mehr als die Hälfte, und die Wiederholung steigt auf 2–4 %. Die Läufe brauchen doppelt so lange. Eine gekürzte Liste ist also kein Ausweg aus dem Hotword-Problem von TOOL-81, sie macht es schlimmer.
- **`nohw` ist kein Gewinner.** An B liegt es 1 Punkt unter dem Mittel von `base`, aber innerhalb seiner Spanne, an A 4 Punkte darüber. Die rund 16 % fehlenden Wörter aus TOOL-81 zeigen sich hier nicht: Mit Hotwords erkennt Whisper über das Segment sogar 1 % mehr Wörter.
- **Ohne Hotwords teilt Whisper anders.** `nohw` liefert 3703 statt rund 870 Passagen bei fast gleicher Wortzahl. Kurze Passagen fallen öfter unter die Schwellen der Bewertung, die markierte Zeit sinkt von 97 % auf 39 %, und 114 bzw. 89 Fehler liegen in `confident`-Passagen statt 0 bzw. 0–7. Für die Go-Regel ist das ein Ausschlussgrund. Es betrifft auch Stufe 3: Jedes Modell ohne Hotwords muss diese Zahl mit ausweisen, und ein Modellwechsel braucht eine neue Kalibrierung der Bewertung (TOOL-35).
- **`nohw-hp` hilft nicht.** An A gleichauf mit `nohw`, an B 5 Punkte schlechter mit rund 35 Auslassungen mehr. Der Vorteil des Hochpasses aus TOOL-92 an B (dort mit Hotwords) wiederholt sich ohne Hotwords nicht.
- **Seed und Hotwords:** Ohne Hotwords sind die Seeds fast oder ganz gleich (`nohw` dreimal identisch), mit Hotwords streuen sie. Die Hotwords bringen den Decoder offenbar öfter in den Temperatur-Fallback, wo der Seed wirkt.

**Basis für Stufe 2: `base`** (large-v3-turbo mit allen Hotwords).

## Stufe 2: VAD und Dekodierung

Jede Variante ist `base` plus genau eine Änderung. VAD-Defaults von faster-whisper 1.2.1: `threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`.

| Variante | Änderung |
| --- | --- |
| `+novad` | `vad_filter: false` |
| `+vad-t35` | `vad_parameters.threshold: 0.35` |
| `+vad-pad800` | `vad_parameters.speech_pad_ms: 800` |
| `+vad-sil500` | `vad_parameters.min_silence_duration_ms: 500` |
| `+beam10` | `asr.beam_size: 10` statt 5 |
| `+nospeech-off` | `no_speech_threshold: null` |
| `+logprob-lax` | `log_prob_threshold: -1.5` statt -1.0 |
| `+cond-prev` | `condition_on_previous_text: true` |

### Wortlaut

Mittel und Spanne über drei Seeds. Auslassungen je Seed:

| Variante | WER A | Auslassungen A | WER B | Auslassungen B | Wörter Segment | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| `base` | 24,0 % (24,0–24,0) | 50 / 50 / 55 | 36,1 % (32,9–41,1) | 92 / 84 / 90 | 33009 (32923–33067) | 0,7 % (0,5–0,8) |
| `+novad` | 35,5 % (29,8–45,4) | 81 / 51 / 50 | 36,5 % (36,0–37,4) | 84 / 84 / 91 | 33067 (32883–33387) | 0,6 % |
| `+vad-t35` | **23,4 %** (23,4–23,4) | 52 / 52 / 52 | 41,2 % (34,6–52,4) | 101 / 189 / 85 | 32527 (32267–32931) | 0,6 % (0,5–0,6) |
| `+vad-pad800` | 35,5 % (29,0–44,6) | 48 / 104 / 49 | 40,7 % (36,4–49,3) | 94 / 94 / 143 | 32942 (32863–33075) | 0,6 % (0,4–0,8) |
| `+vad-sil500` | 24,7 % (24,7–24,7) | 40 / 40 / 40 | 42,3 % (34,4–57,7) | 80 / 165 / 100 | 32637 (32552–32708) | 0,5 % (0,3–0,8) |
| `+beam10` | 24,3 % (23,0–25,2) | 54 / 57 / 58 | 38,9 % (33,5–48,1) | 88 / 84 / 111 | 32662 (32380–33066) | 0,4 % (0,4–0,5) |
| `+nospeech-off` | 24,0 % (24,0–24,0) | 50 / 50 / 55 | 36,1 % (32,9–41,1) | 92 / 84 / 90 | 33009 (32923–33067) | 0,7 % (0,5–0,8) |
| `+logprob-lax` | 24,0 % (24,0–24,0) | 50 / 50 / 55 | 36,1 % (33,3–41,1) | 85 / 89 / 90 | 32880 (32585–33316) | 0,9 % (0,6–1,4) |
| `+cond-prev` | 75,2 % (70,2–80,8) | 302 / 351 / 344 | 100,0 % | 489 / 489 / 489 | 271 (229–304) | 4,8 % (0,0–9,3) |

Ersetzungen / Auslassungen / Einfügungen je Lauf:

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) |
| --- | --- | --- |
| base+novad#1 | 45,4 % (82/81/87) | 36,0 % (87/84/5) |
| base+novad#2 | 31,2 % (75/51/46) | 36,0 % (87/84/5) |
| base+novad#3 | 29,8 % (80/50/34) | 37,4 % (78/91/14) |
| base+vad-t35#1 | 23,4 % (60/52/17) | 34,6 % (62/101/6) |
| base+vad-t35#2 | 23,4 % (60/52/17) | 52,4 % (61/189/6) |
| base+vad-t35#3 | 23,4 % (60/52/17) | 36,8 % (82/85/13) |
| base+vad-pad800#1 | 32,7 % (90/48/42) | 36,4 % (72/94/12) |
| base+vad-pad800#2 | 44,6 % (61/104/81) | 36,4 % (72/94/12) |
| base+vad-pad800#3 | 29,0 % (81/49/30) | 49,3 % (77/143/21) |
| base+vad-sil500#1 | 24,7 % (73/40/23) | 34,4 % (79/80/9) |
| base+vad-sil500#2 | 24,7 % (73/40/23) | 57,7 % (90/165/27) |
| base+vad-sil500#3 | 24,7 % (73/40/23) | 35,0 % (64/100/7) |
| base+beam10#1 | 23,0 % (58/54/15) | 35,0 % (74/88/9) |
| base+beam10#2 | 25,2 % (59/57/23) | 33,5 % (74/84/6) |
| base+beam10#3 | 24,5 % (62/58/15) | 48,1 % (109/111/15) |
| base+nospeech-off#1–3 | wie base#1–3 | wie base#1–3 |
| base+logprob-lax#1 | 24,0 % (66/50/16) | 33,7 % (76/85/4) |
| base+logprob-lax#2 | 24,0 % (65/50/17) | 33,3 % (67/89/7) |
| base+logprob-lax#3 | 24,0 % (62/55/15) | 41,1 % (84/90/27) |
| base+cond-prev#1 | 70,2 % (30/302/55) | 100,0 % (0/489/0) |
| base+cond-prev#2 | 74,6 % (31/351/29) | 100,0 % (0/489/0) |
| base+cond-prev#3 | 80,8 % (29/344/72) | 100,0 % (0/489/0) |

### Bewertung

| Variante | confident / needs_review / uncertain je Seed | markierte Zeit | übersehen A | übersehen B |
| --- | --- | --- | --- | --- |
| `base` | 132/598/138, 114/599/151, 142/637/149 | 96,7–97,3 % | 0 / 0 / 0 | 4 / 7 / 0 |
| `+novad` | 242/702/251, 244/750/275, 224/697/269 | 89,9–90,8 % | 0 / 0 / 0 | 0 / 0 / 0 |
| `+vad-t35` | 170/583/200, 174/561/149, 120/590/152 | 95,0–95,3 % | 35 / 35 / 35 | 0 / 0 / 0 |
| `+vad-pad800` | 141/629/235, 173/593/190, 137/648/200 | 95,5–95,9 % | 0 / 0 / 0 | 0 / 0 / 45 |
| `+vad-sil500` | 164/563/185, 120/499/120, 112/508/125 | 94,4–95,0 % | 0 / 0 / 0 | 17 / 0 / 0 |
| `+beam10` | 58/583/177, 101/591/190, 60/612/216 | 96,0–97,3 % | 0 / 0 / 0 | 0 / 0 / 0 |
| `+nospeech-off` | wie `base` | wie `base` | 0 / 0 / 0 | 4 / 7 / 0 |
| `+logprob-lax` | 137/610/147, 96/558/125, 125/610/139 | 96,4–96,8 % | 0 / 0 / 0 | 17 / 7 / 0 |
| `+cond-prev` | 0/3/2, 0/2/3, 0/4/3 | 100 % | 0 / 0 / 0 | 0 / 0 / 0 |

### Laufzeit und Speicher

| Variante | ASR (min/h) | Peak-RAM | Peak-VRAM (davor) |
| --- | --- | --- | --- |
| `base` | 1,25–1,30 | 13,8–13,9 GiB | 3,6–4,0 GiB (1,1–1,8) |
| `+novad` | 1,33–1,39 | 16,0 GiB | 3,7 GiB (1,2) |
| `+vad-t35` | 1,28–1,35 | 14,1 GiB | 3,7 GiB (1,2) |
| `+vad-pad800` | 1,36–1,41 | 14,6–14,7 GiB | 3,7 GiB (1,2) |
| `+vad-sil500` | 1,61–1,65 | 13,0 GiB | 3,7 GiB (1,2) |
| `+beam10` | 2,28–2,44 | 13,8–13,9 GiB | 3,7 GiB (1,2) |
| `+nospeech-off` | 1,19–1,27 | 13,8–13,9 GiB | 3,7 GiB (1,2) |
| `+logprob-lax` | 1,21–1,26 | 13,8 GiB | 3,7 GiB (1,2) |
| `+cond-prev` | 0,47 | 13,9 GiB | 3,6–3,7 GiB (1,2) |

### Zwischenbewertung

- **Kein Gewinner.** Keine Variante liegt an A und B mindestens 3 Punkte unter `base`. Damit gibt es für Stufe 4 keine Einstellung, die einzeln 3 Punkte gebracht hat. Die Kombination entfällt, Stufe 4 vergleicht nur noch das beste Modell aus Stufe 3 mit `base`.
- **`+vad-t35` ist an A am besten, aber nur um 0,6 Punkte**, und legt dort 35 Fehler in `confident`-Passagen. An B verliert ein Seed einen ganzen Block (189 Auslassungen).
- **`+vad-sil500` hat an A die wenigsten Auslassungen** (40 statt 50–55), dafür mehr Ersetzungen und Einfügungen. An B ist es die unruhigste Variante (34,4–57,7 %). Es kostet rund 30 % mehr Rechenzeit.
- **`+novad` und `+vad-pad800` erfinden an A Text**, mit bis zu 87 bzw. 81 Einfügungen statt 15–17. Ohne VAD oder mit längerem Rand hört Whisper Sprache, wo keine ist.
- **`+beam10` bringt nichts** außer der doppelten Rechenzeit.
- **`+nospeech-off` ist wirkungslos.** Das Transkript ist Wort für Wort gleich mit `base`, die Einstellung steht aber in `asr.settings` und kommt im Decoder an. Whisper verwirft ein Fenster nur, wenn es wahrscheinlich stumm *und* der Decoder unsicher ist (`avg_logprob` unter `log_prob_threshold`). Nach der VAD kommt das auf dieser Aufnahme nicht vor.
- **`+logprob-lax` ändert fast nichts.** An A gleich, an B innerhalb der Spanne von `base`.
- **`+cond-prev` bricht zusammen.** Mit dem vorherigen Text als Prompt bleibt Whisper nach wenigen Minuten hängen und liefert über 5 Stunden nur rund 270 Wörter. Das bestätigt die feste Einstellung `condition_on_previous_text: false` der Pipeline.
- **Die größte Wirkung hat der Seed, nicht die Einstellung.** In fast jeder Variante verliert ein Seed an B einen Block von 70–100 Wörtern (z. B. 189 statt 85–101 Auslassungen bei `+vad-t35`). Diese Sprünge sind größer als jeder Unterschied zwischen den Varianten. Ohne Hotwords streuen die Seeds kaum (Stufe 1). Das ist ein Hinweis darauf, dass die Hotwords den Decoder an B instabil machen; die Ursache gehört zu TOOL-81.

**Ergebnis Stufe 2: `base` bleibt unverändert.** Stufe 3 vergleicht die Modelle mit den Pipeline-Einstellungen.
