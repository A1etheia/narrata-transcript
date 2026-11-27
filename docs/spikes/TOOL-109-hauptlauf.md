# TOOL-109 — Pegelausgleich als Hauptlauf: Messung an A bis K

Stand 2026-11-27, Messung abgeschlossen, Entscheidung: `loudnorm` wird Default. Bericht zu [TOOL-109](../plans/TOOL-109-level-filter.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py), Variante `norm`. Neu transkribiert wurden sechs Läufe von `norm` (zwei Sitzungen, Seeds 1 bis 3), alles lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Ergebnis

**Der Filter der Pipeline liefert dasselbe wie der Filter des Spikes, und `norm` hat an A bis K das beste Mittel und den mildesten schlechtesten Fall der vier Kandidaten.** Auf dieser Grundlage ist `loudnorm` Default geworden ([Entscheidungstabelle](#entscheidungstabelle), [Entscheidung](#entscheidung)).

- **Pipeline gegen Spike:** Das gefilterte WAV der Pipeline ist in beiden Sitzungen Byte für Byte das WAV der Spike-Variante `loud`. Die Transkripte von `norm` und `loud` haben an allen elf Referenzen und in allen drei Seeds dieselben Zahlen für Ersetzungen, Auslassungen und Einfügungen ([Pipeline gegen Spike](#pipeline-gegen-spike)).
- **WER:** `norm` ist an neun Referenzen besser als `base` (0,9 bis 38,8 Punkte) und an zwei schlechter (G 6,3 Punkte, I 3,1 Punkte). Mittel über die elf Referenzen 30,2 % gegen 37,8 % ([WER](#wer)).
- **Streuung:** Der schlechteste einzelne Lauf von `norm` liegt bei 45,0 % (G), der von `base` bei 88,8 % (J).
- **Sprecherfehler:** Mit Diarisierung auf dem Roh-WAV liegt `norm` an fünf Referenzen über `base` (höchstens 1,6 Punkte), an fünf darunter, an einer gleich. Der Nachteil aus dem Spike an E (8,7 % gegen 5,3 %) schrumpft auf 6,0 % ([Sprecherfehler](#sprecherfehler)).
- **Übersehene Fehler in `confident`-Passagen:** in Summe 325 gegen 385 bei `base`, aber an A, D, H und K mehr als `base`. Das Kriterium des Tickets hält damit nicht an jeder Referenz; bei Default `loudnorm` ist Chunk 5 nötig ([Bewertung](#bewertung)).
- **Kosten:** rund 5 bis 6 Minuten Filterzeit je Segment von knapp 5 Stunden, einmalig je Roh-WAV, und der doppelte Platz für das Audio ([Filter](#filter)).

## Material und Methode

| | |
| --- | --- |
| Läufe | `base`, `loud` (Seeds 1–3), `base+batched`, `loud+batched` (Seeds 1–3, Wort für Wort gleich) aus TOOL-93, TOOL-103 und TOOL-104; neu `norm`, Seeds 1–3, Seed 1 mit Diarisierung |
| `norm` | Roh-WAV verlinkt, `asr.level_filter: loudnorm` in der Konfiguration der Schattenwurzel; die Pipeline filtert selbst nach `audio/level/`. Seed 2 und 3 verwenden das gefilterte WAV von Seed 1 wieder (Hardlink, von der Pipeline als „reused“ gemeldet) |
| `loud` | Spike-Variante aus TOOL-103: dieselbe Kette, vom Spike-Werkzeug gefiltert und als Segment-WAV verlinkt; auch die Diarisierung liest dort das gefilterte WAV |
| Kette | `loudnorm=I=-16:TP=-1.5:LRA=11`, zweistufig, ffmpeg 4.4.2 |
| Modell | `large-v3-turbo`, dieselbe Revision und je Sitzung derselbe Wissens-Snapshot in allen fünf Varianten |
| Referenzen | A bis K wie in [TOOL-108](TOOL-108-blockverlust.md#material-und-methode): A, B, D, E, F, G, I in der Pilotsitzung, C, H, J, K in der zweiten Sitzung |

- **WER** gegen die Handreferenz wie in `calibration.measure`; E/A/Ei sind Ersetzungen, Auslassungen, Einfügungen.
- **WDER** an Seed 1, nur an Wörtern, die Lauf und Referenz gemeinsam haben; die Zahl in Klammern ist deren Anzahl.
- **Übersehene Fehler:** Fehler in Passagen, die die Bewertung mit den heutigen Schwellen aus `review.uncertainty` als `confident` einstuft.
- **Kontrolle:** `base` gibt weiter 21,3 % an A und 29,8 % an B.

## Pipeline gegen Spike

| | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| SHA-256 des gefilterten WAV, Pipeline gegen Spike | gleich | gleich |
| Frames gegen Manifest | gleich | gleich |
| Roh-WAV | unverändert (derselbe Hardlink) | unverändert (derselbe Hardlink) |
| WER, E/A/Ei je Referenz und Seed, `norm` gegen `loud` | gleich an A, B, D, E, F, G, I | gleich an C, H, J, K |
| Wörter im Segment je Seed, `norm` gegen `loud` | gleich | gleich |

Abweichung zum Spike gibt es bei der Erkennung keine. Verschieden sind nur die Größen, die an der Diarisierung hängen (Sprecherfehler, Passagen und ihre Bewertung), weil `norm` auf dem Roh-WAV diarisiert und `loud` auf dem gefilterten.

## WER

Mittel über drei Seeds, in Klammern die Spanne. Bei den Batched-Läufen sind die Seeds gleich.

| Referenz | `base` | `norm` | `norm` − `base` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- | --- | --- |
| A | 21,3 % (21,3–21,3) | 20,2 % (20,2–20,2) | −1,1 | 19,6 % | 18,8 % |
| B | 29,8 % (25,6–35,4) | 26,5 % (26,5–26,5) | −3,3 | 25,4 % | 28,1 % |
| C | 30,8 % (27,3–33,3) | 23,9 % (23,2–24,8) | −6,9 | 25,9 % | 23,7 % |
| D | 61,2 % (49,4–81,5) | 36,7 % (36,1–38,1) | −24,5 | 36,3 % | 38,3 % |
| E | 34,0 % (29,8–40,7) | 29,6 % (29,5–29,8) | −4,4 | 29,0 % | 67,5 % |
| F | 28,4 % (26,7–31,0) | 27,5 % (26,7–27,9) | −0,9 | 26,4 % | 26,7 % |
| G | 36,0 % (33,4–39,2) | 42,3 % (39,7–45,0) | +6,3 | 39,6 % | 35,6 % |
| H | 36,5 % (34,9–37,2) | 32,8 % (32,3–33,2) | −3,7 | 53,6 % | 37,2 % |
| I | 27,2 % (26,6–28,3) | 30,3 % (30,3–30,3) | +3,1 | 33,2 % | 31,7 % |
| J | 74,8 % (64,2–88,8) | 36,0 % (32,2–43,4) | −38,8 | 37,6 % | 30,2 % |
| K | 35,5 % (35,2–36,2) | 26,5 % (21,3–29,5) | −9,0 | 21,5 % | 22,0 % |

Je Lauf von `norm` (E/A/Ei):

| Referenz | Wörter | Seed 1 | Seed 2 | Seed 3 |
| --- | --- | --- | --- | --- |
| A | 531 | 20,2 % (61/29/17) | 20,2 % (61/29/17) | 20,2 % (61/29/17) |
| B | 441 | 26,5 % (69/42/6) | 26,5 % (69/42/6) | 26,5 % (69/42/6) |
| C | 909 | 23,9 % (107/88/22) | 24,8 % (112/92/21) | 23,2 % (105/88/18) |
| D | 449 | 36,1 % (93/59/10) | 38,1 % (87/64/20) | 36,1 % (85/64/13) |
| E | 369 | 29,5 % (67/30/12) | 29,8 % (68/30/12) | 29,5 % (67/30/12) |
| F | 584 | 27,9 % (71/80/12) | 27,7 % (70/80/12) | 26,7 % (68/76/12) |
| G | 551 | 42,1 % (117/73/42) | 45,0 % (104/95/49) | 39,7 % (103/87/29) |
| H | 470 | 32,3 % (71/66/15) | 33,2 % (73/68/15) | 32,8 % (72/67/15) |
| I | 597 | 30,3 % (74/60/47) | 30,3 % (74/60/47) | 30,3 % (74/60/47) |
| J | 394 | 43,4 % (62/92/17) | 32,2 % (68/41/18) | 32,2 % (54/56/17) |
| K | 437 | 29,5 % (64/41/24) | 21,3 % (49/34/10) | 28,8 % (64/39/23) |

Zum Vergleich `base` an den Referenzen mit großer Spanne: D 49,4 % (77/133/12), 52,6 % (98/115/23), 81,5 % (86/166/114); J 71,3 % (49/210/22), 88,8 % (96/118/136), 64,2 % (83/121/49). `base` verliert dort ganze Blöcke (Auslassungen) oder erfindet welche (Einfügungen); `norm` hat an D höchstens 64 Auslassungen und an J höchstens 92.

Wo `norm` verliert: an G mehr Einfügungen (29 bis 49 gegen 21 bis 36) und in zwei Seeds mehr Auslassungen, an I 47 Einfügungen gegen 12 bis 18 bei weniger Auslassungen (60 gegen 66 bis 82).

## Sprecherfehler

Seed 1. `norm` diarisiert auf dem Roh-WAV; die Sprecherwechsel stimmen deshalb zu 100,0 % mit `base` überein (bei `loud` 96,3 % und 96,1 %). Unterschiede zu `base` kommen allein aus anderen Wörtern und Wortzeiten.

| Referenz | `base` | `norm` (Diarisierung roh) | `loud` (Diarisierung gefiltert, Spike) | `norm` − `base` |
| --- | --- | --- | --- | --- |
| A | 5,7 % (423) | 6,5 % (429) | 6,1 % (425) | +0,8 |
| B | 3,4 % (320) | 3,2 % (316) | 4,1 % (314) | −0,2 |
| C | 4,7 % (684) | 4,1 % (678) | 4,1 % (677) | −0,6 |
| D | 12,3 % (227) | 11,1 % (280) | 10,9 % (276) | −1,2 |
| E | 5,3 % (245) | 6,0 % (252) | 8,7 % (252) | +0,7 |
| F | 8,6 % (421) | 9,4 % (417) | 11,1 % (415) | +0,8 |
| G | 10,0 % (361) | 11,6 % (354) | 11,9 % (352) | +1,6 |
| H | 13,9 % (281) | 13,9 % (302) | 14,8 % (311) | 0,0 |
| I | 6,5 % (433) | 8,1 % (444) | 11,7 % (443) | +1,6 |
| J | 11,1 % (126) | 6,4 % (218) | 4,1 % (218) | −4,7 |
| K | 3,6 % (278) | 1,9 % (321) | 1,9 % (321) | −1,7 |
| Mittel der Referenzen | 7,7 % | 7,5 % | 8,1 % | |

- Gegen `base`: an A, E, F, G und I höher, an B, C, D, J und K niedriger, an H gleich. An D und J misst `norm` an deutlich mehr gemeinsamen Wörtern, weil `base` dort Blöcke verliert.
- Gegen den Spike: Das Roh-WAV ist an sechs Referenzen besser als das gefilterte (am stärksten an I, E und F), an A, D und J schlechter, an C und K gleich. Eine Option „Diarisierung auf dem gefilterten WAV“ verlangt die Messung nicht.
- Labels: vier in jedem Lauf. Wörter ohne Label: 7,3 % bei `norm` gegen 6,8 % und 7,1 % bei `base`.

## Bewertung

Seed 1, heutige Schwellen. Die Seeds 2 und 3 laufen ohne Diarisierung und markieren in jeder Variante 95 bis 97 % der Zeit; sie sind für diese Tabelle nicht vergleichbar. Die Ursache ist hier nicht untersucht.

| | `base` | `norm` | `loud` |
| --- | --- | --- | --- |
| Pilotsitzung: `confident` / `needs_review` / `uncertain` | 699 / 1033 / 257 | 755 / 1076 / 176 | 777 / 1053 / 169 |
| Pilotsitzung: markierte Zeit | 79,2 % | 78,5 % | 77,8 % |
| zweite Sitzung: `confident` / `needs_review` / `uncertain` | 565 / 919 / 337 | 658 / 974 / 238 | 681 / 964 / 245 |
| zweite Sitzung: markierte Zeit | 80,9 % | 80,4 % | 79,7 % |

Übersehene Fehler in `confident`-Passagen:

| Referenz | `base` | `norm` | `loud` |
| --- | --- | --- | --- |
| A | 5 | 11 | 11 |
| B | 11 | 4 | 4 |
| C | 77 | 67 | 67 |
| D | 8 | 37 | 37 |
| E | 35 | 15 | 20 |
| F | 37 | 19 | 20 |
| G | 45 | 17 | 19 |
| H | 17 | 47 | 30 |
| I | 52 | 24 | 26 |
| J | 72 | 24 | 13 |
| K | 26 | 60 | 60 |
| Summe | 385 | 325 | 307 |

`norm` übersieht in Summe weniger als `base`, an A, D, H und K aber mehr (zusammen 155 gegen 56). Der Maßstab des Tickets („nicht über dem heutigen Stand von `base`“) ist in Summe erfüllt, je Referenz nicht. Wird `loudnorm` Default, misst Chunk 5 mit der Methode aus TOOL-35 nach.

## Filter

| | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Länge des Segments | 5,00 h | 4,78 h |
| Lautheit des Eingangs | −26,6 LUFS | −26,5 LUFS |
| Umfang (LRA) | 16,0 LU | 17,6 LU |
| Spitze | +1,9 dBTP | +2,0 dBTP |
| `target_offset` | 2,11 | 2,35 |
| `linear_expected` | nein | nein |
| Filterzeit (beide Durchgänge) | 362 s, 1,2 min je Stunde | 289 s, 1,0 min je Stunde |
| Versatz der Hüllkurve an drei Stellen | 0 / 0 / 0 ms | 0 / 0 / 0 ms |
| Verstärkung, Median (10. bis 90. Perzentil) | 12,6 dB (8,0 bis 17,0) | 15,6 dB (11,7 bis 19,4) |
| Anteil der Samples auf Vollausschlag | 0 | 0 |

- **Kein Versatz:** Die Zeitachse des gefilterten WAV stimmt mit dem Roh-WAV überein; Wortzeiten und Diarisierung passen ohne Korrektur zusammen.
- **Dynamischer Betrieb:** Der Umfang des Eingangs liegt über dem Ziel von 11 LU, `loudnorm` arbeitet deshalb trotz `linear=true` als Leveller. Die Spanne der Verstärkung von rund 8 bis 9 dB zeigt das.
- **Zeit:** Die Erkennung selbst braucht mit `norm` 1,2 bis 1,3 min je Stunde Audio (`base` 1,3 bis 1,4). Der Filter kommt einmal je Roh-WAV dazu und verdoppelt beim ersten Lauf ungefähr die Zeit von `transcribe`; jeder weitere Lauf verwendet das WAV wieder.
- **Platz:** Das gefilterte WAV ist so groß wie das Roh-WAV.

## Entscheidungstabelle

WER, Mittel über drei Seeds.

| | `base` | `norm` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- | --- |
| Mittel der elf Referenzen | 37,8 % | 30,2 % | 31,6 % | 32,7 % |
| Schlechtestes Fenster (Mittel) | 74,8 % (J) | 42,3 % (G) | 53,6 % (H) | 67,5 % (E) |
| Schlechtester einzelner Lauf | 88,8 % (J) | 45,0 % (G) | 53,6 % (H) | 67,5 % (E) |
| Referenzen besser als `base` | – | 9 | 8 | 8 |
| Referenzen schlechter als `base` | – | 2 (G, I) | 3 (G, H, I) | 3 (E, H, I) |
| Größter Verlust gegen `base` | – | 6,3 Punkte (G) | 17,1 Punkte (H) | 33,5 Punkte (E) |
| Größter Gewinn gegen `base` | – | 38,8 Punkte (J) | 37,2 Punkte (J) | 44,6 Punkte (J) |
| Größte Spanne über die Seeds | 32,1 Punkte (D) | 11,2 Punkte (J) | 0 | 0 |
| WDER, Mittel der Referenzen (Seed 1) | 7,7 % | 7,5 % | nicht gemessen | nicht gemessen |
| Übersehene Fehler, Summe (Seed 1) | 385 | 325 | – | – |
| Erkennung, min je Stunde Audio | 1,3 bis 1,4 | 1,2 bis 1,3, dazu einmalig 1,0 bis 1,2 für den Filter | 0,3 bis 0,4 | 0,3 bis 0,4, dazu der Filter |

Die Bewertung der Batched-Läufe ist nicht vergleichbar: Sie liefen ohne Diarisierung und markieren 96 bis 98 % der Zeit.

### Was mit der Entscheidung zusammenhängt

- **Default `loudnorm`:** Gespeicherte Transkripte werden `stale`, `process` verlangt `--redo transcribe`. Chunk 5 misst die Bewertung nach, weil an vier Referenzen mehr Fehler in `confident`-Passagen stehen als bei `base`.
- **Regel A aus TOOL-108** ist mit `base` als Hauptlauf entschieden; unter den `loud`-Seeds reichte dort kein Block in eine Referenz. Mit `loudnorm` als Hauptlauf bringt die Regel nach heutigem Stand nichts, TOOL-114 müsste das neu bewerten.
- **Default `none`:** Der Schalter bleibt als Option, `base` bleibt Hauptlauf, TOOL-114 gilt unverändert. Der schlechteste Fall an D und J bleibt.
- **Vorbehalt aus TOOL-103:** Beide Sitzungen haben fast denselben Eingangspegel (−26,6 und −26,5 LUFS). Wie sich `loudnorm` an einer deutlich lauteren oder leiseren Aufnahme verhält, ist nicht gemessen (TOOL-105).

## Entscheidung

**2026-11-27, Projektverantwortliche: `loudnorm` wird Default.** `asr.level_filter` steht ohne Angabe auf `loudnorm`; `none` bleibt als Option.

- **Begründung:** bestes Mittel der vier Kandidaten (30,2 % gegen 37,8 % bei `base`), mildester schlechtester Fall (42,3 % gegen 74,8 %), an neun von elf Referenzen besser, Sprecherfehler mit Diarisierung auf dem Roh-WAV auf dem Stand von `base`.
- **In Kauf genommen:** G und I werden um 6,3 und 3,1 Punkte schlechter; der erste Lauf je Roh-WAV braucht 5 bis 6 Minuten länger und das Audio den doppelten Platz.
- **Folgen:** Gespeicherte Transkripte gelten als veraltet, `process` verlangt einmal `--redo transcribe`. Die Bewertung wird auf gefiltertem Audio nachgemessen ([Kalibrierung](TOOL-35-kalibrierung.md)). TOOL-114 bewertet Regel A mit dem neuen Hauptlauf neu.
