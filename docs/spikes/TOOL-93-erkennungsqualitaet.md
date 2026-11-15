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

## Stufe 3: Modelle

Laut Plan laufen die Modelle ohne Hotwords und mit den Einstellungen der Pipeline, Vergleichsmaß ist `nohw` (large-v3-turbo ohne Hotwords). Dazu kommt `base+de-turbo`: Das deutsche Turbo-Modell trägt `turbo` im Namen und bekäme in der Pipeline Hotwords, es wäre also der echte Ersatz für `base`.

| Modifikator | Modell | Revision | Lizenz | Format |
| --- | --- | --- | --- | --- |
| `+large-v3` | Whisper large-v3 | `edaa852ec7e1` | MIT | CTranslate2, lag im Cache |
| `+de-turbo` | `primeline/whisper-large-v3-turbo-german` | `9e7012dad924` | Apache-2.0 | Transformers, selbst nach CTranslate2 konvertiert (float16, 1,6 GB), `tokenizer.json` ergänzt |
| `+crisper` | `nyralabs/faster_CrisperWhisper` (CrisperWhisper 1.0, Deutsch und Englisch) | `6a042898d09e` | CC-BY-NC-4.0 (vom Basismodell `nyralabs/CrisperWhisper`) | CTranslate2 (2,9 GB) |
| — | CrisperWhisper 2.0 (`nyralabs/CrisperWhisper2.0_*`) | — | nyra health Non-Commercial Research License | ausgeschlossen, siehe unten |

**Lizenzen für die private Gruppe.** MIT und Apache-2.0 sind unproblematisch. CC-BY-NC-4.0 erlaubt die nicht-kommerzielle Nutzung mit Namensnennung; eine private Spielrunde ohne Einnahmen fällt darunter. CrisperWhisper 2.0 ist enger: Die Lizenz schließt „any production or operational deployment“ auch ohne Gewinnabsicht aus. Ein Spike wäre erlaubt, ein Einsatz in V0.2 nicht. Außerdem braucht 2.0 die eigene Laufzeit `crisperwhisper` und damit ein eigenes Backend. Es bleibt deshalb draußen.

### Wortlaut

| Variante | Hotwords | WER A | Auslassungen A | WER B | Auslassungen B | Wörter Segment | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | 48 | **24,0 %** (24,0–24,0) | 50 / 50 / 55 | 36,1 % (32,9–41,1) | 92 / 84 / 90 | 33009 (32923–33067) | 0,7 % (0,5–0,8) |
| `nohw` | 0 | 28,3 % | 72 / 72 / 72 | **35,0 %** | 93 / 93 / 93 | 32617 | 0,3 % |
| `nohw+large-v3` | 0 | 30,9 % | 93 / 93 / 93 | 37,4 % | 110 / 110 / 110 | 32604 (32603–32605) | 0,4 % |
| `nohw+de-turbo` | 0 | 27,8 % | 77 / 77 / 77 | 38,0 % | 107 / 107 / 107 | 32653 (32645–32661) | 0,2 % |
| `nohw+crisper` | 0 | 69,9 % (68,2–71,7) | 262 / 208 / 322 | 60,8 % (55,6–63,4) | 236 / 236 / 173 | 16985 (16810–17288) | 7,1 % (4,2–9,0) |
| `base+de-turbo` | 48 | 27,1 % (25,8–27,8) | 70 / 75 / 60 | 47,0 % (46,8–47,2) | 147 / 148 / 151 | 32302 (32111–32558) | 0,2 % |

Ersetzungen / Auslassungen / Einfügungen je Lauf (ohne Hotwords sind die Seeds an A und B identisch, deshalb eine Zeile):

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) |
| --- | --- | --- |
| nohw#1–3 | 28,3 % (68/72/16) | 35,0 % (69/93/9) |
| nohw+large-v3#1–3 | 30,9 % (66/93/11) | 37,4 % (64/110/9) |
| nohw+de-turbo#1–3 | 27,8 % (61/77/15) | 38,0 % (73/107/6) |
| nohw+crisper#1 | 69,7 % (113/262/9) | 63,4 % (61/236/13) |
| nohw+crisper#2 | 68,2 % (67/208/101) | 63,4 % (61/236/13) |
| nohw+crisper#3 | 71,7 % (53/322/20) | 55,6 % (85/173/14) |
| base+de-turbo#1 | 25,8 % (60/70/12) | 47,0 % (73/147/10) |
| base+de-turbo#2 | 27,8 % (65/75/13) | 46,8 % (73/148/8) |
| base+de-turbo#3 | 27,8 % (69/60/24) | 47,2 % (71/151/9) |

### Bewertung

| Variante | confident / needs_review / uncertain je Seed | markierte Zeit | übersehen A | übersehen B |
| --- | --- | --- | --- | --- |
| `base` | 132/598/138, 114/599/151, 142/637/149 | 96,7–97,3 % | 0 / 0 / 0 | 4 / 7 / 0 |
| `nohw` | 2600/933/170 (alle drei) | 38,7 % | 114 | 89 |
| `nohw+large-v3` | 2391/963/134, 2391/963/134, 2392/962/134 | 42,1 % | 97 | 133 |
| `nohw+de-turbo` | 1724/761/113, 1723/765/113, 1718/762/117 | 42,4–42,5 % | 89 | 66 |
| `nohw+crisper` | 510/388/550, 524/374/573, 441/362/542 | 94,5–95,4 % | 5 / 9 / 0 | 0 / 0 / 0 |
| `base+de-turbo` | 409/609/95, 436/599/75, 440/605/90 | 80,2–80,9 % | 45 / 31 / 31 | 9 / 39 / 38 |

### Laufzeit und Speicher

| Variante | ASR (min/h) | Peak-RAM | Peak-VRAM (davor) |
| --- | --- | --- | --- |
| `base` | 1,25–1,30 | 13,8–13,9 GiB | 3,6–4,0 GiB (1,1–1,8) |
| `nohw` | 1,09–1,12 | 13,8–13,9 GiB | 3,5–4,1 GiB (1,1–1,6) |
| `nohw+large-v3` | 2,76–2,77 | 13,8–13,9 GiB | 6,1 GiB (0,9–1,0) |
| `nohw+de-turbo` | 1,05–1,07 | 13,8–13,9 GiB | 3,4 GiB (1,0) |
| `nohw+crisper` | 6,21–6,59 | 13,8–13,9 GiB | 6,1 GiB (0,9–1,0) |
| `base+de-turbo` | 1,19–1,23 | 13,9 GiB | 3,4 GiB (1,0) |

Alle Modelle bleiben weit unter 12 GB VRAM und laufen mit `float16` auf der GPU. Der RAM-Peak kommt vom Pipeline-Prozess, nicht vom Modell.

### Zwischenbewertung

- **Kein Modell schlägt `base`.** Keines liegt an A und B mindestens 3 Punkte darunter, auch nicht unter `nohw`.
- **large-v3 ist schlechter und langsamer.** An A und B 2–3 Punkte über `nohw`, mehr Auslassungen, doppelte Rechenzeit. Das deckt sich mit TOOL-62.
- **Das deutsche Turbo-Modell hilft nur an A.** Ohne Hotwords 0,5 Punkte unter `nohw` an A, aber 3 Punkte darüber an B. Mit Hotwords (`base+de-turbo`) ist es an A 3 Punkte und an B 11 Punkte schlechter als `base`: Es verliert an B rund 60 Wörter mehr. Die Hotwords verträgt das Feinmodell schlechter als das Original.
- **CrisperWhisper 1.0 halbiert das Transkript.** Rund 17 000 statt 33 000 Wörter, an A und B 200–320 Auslassungen, 7 % Wiederholung, fünfmal so langsam. Vermutlich verliert das Modell, das mit eigener Zeitstempel-Logik trainiert wurde, im Standard-Ablauf von faster-whisper ganze Fenster. Die Ursache ist nicht weiter untersucht, denn auch ein Erfolg bräuchte eine eigene Dekodierung und damit ein eigenes Backend.
- **Ohne Hotwords bleibt das Zerlegungsproblem.** Alle Modelle ohne Hotwords zerlegen das Segment in 2600–3700 Passagen statt rund 870, die Bewertung markiert nur noch rund 40 % der Zeit und übersieht an A und B 66–133 Fehler. Das ist ein Effekt der Pipeline ohne Hotwords, nicht des Modells (Stufe 1).
- **Die Seeds sind ohne Hotwords stabil**, bei allen drei Whisper-Modellen. Nur CrisperWhisper streut, und `base+de-turbo` streut mit Hotwords wie `base`.

**Ergebnis Stufe 3: Kein Modell für Stufe 4.** Mit Stufe 2 ohne Einstellung und Stufe 3 ohne Modell gibt es keinen Finalisten gegen `base`.

## Stufe 4: Finalisten und Fenster für Referenz C

**Keine Finalisten.** Die Kombination braucht Einstellungen, die einzeln mindestens 3 Punkte gebracht haben, und ein besseres Modell; beides gibt es nicht. Ein Diarisierungsvergleich mit WDER entfällt, weil kein Kandidat gegen `base` antritt. Nach der Go-Regel steht damit **No-Go**: Die Pipeline behält large-v3-turbo mit Hotwords und den bisherigen Einstellungen. Die Gegenprobe an Referenz C prüft nur noch, ob die Messwerte von `base` aus der Pilotsitzung auf eine zweite Sitzung übertragbar sind.

**Zweite Sitzung.** Segment 1 lief mit `base`, Seed 1 und Diarisierung: 29006 Wörter, 4 Labels, 93 % der Wörter mit Label, 148 / 565 / 231 Passagen `confident` / `needs_review` / `uncertain`. Die Diarisierung brauchte 212 s.

`windows` schlägt drei sich nicht überlappende 3-min-Fenster in Segment 1 vor:

| Fenster | Wörter/min | Sprecher (≥ 10 Wörter) | ohne Label | markiert |
| --- | --- | --- | --- | --- |
| 1:15:00–1:18:00 | 116 | 4 | 4,6 % | 65,6 % |
| 4:09:00–4:12:00 | 112 | 3 | 5,4 % | 67,2 % |
| 2:24:00–2:27:00 | 109 | 2 | 8,9 % | 66,6 % |

Empfohlen ist das erste Fenster: die höchste Wortdichte, alle vier Sprecher und die wenigsten Wörter ohne Label. Die Projektverantwortliche schreibt Referenz C von Hand und legt sie unter `work/<zweite Sitzung>/review/calibration/` ab.
