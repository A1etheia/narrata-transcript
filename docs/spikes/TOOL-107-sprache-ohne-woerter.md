# TOOL-107 — Hinweis „Sprache ohne Wörter“ gegen `gap` und `sparse`

Stand 2026-11-27, Messung an den gespeicherten Läufen abgeschlossen, Hörstichprobe gezogen und noch nicht abgetippt, Entscheidung offen. Bericht zu [TOOL-107](../plans/TOOL-107-speech-without-words.md), Werkzeug: [`scripts/spike/hint.py`](../../scripts/spike/hint.py). Es wurde nichts neu transkribiert, alles lief lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel, keine Zeitfenster der Stichprobe.

## Ergebnis

**Nach der vorab festgelegten Regel steht der Hinweis auf No-Go: Punkt 1 ist knapp verfehlt.** Mit dem Hinweis liegen 20,0 Auslassungen mehr an einer gezeigten Stelle als mit `gap` und `sparse` allein (verlangt: mindestens 20), das sind 40,8 % mehr (verlangt: mindestens 50 %). Die Kosten sind klein. Die Hörstichprobe steht noch aus ([Stand gegen die Go-Regel](#stand-gegen-die-go-regel)).

- **Kosten:** Der Hinweis markiert 9 bis 11 bisher `confident`-Passagen je Segment neu, das sind 0,3 und 0,4 Punkte markierte Zeit ([Segment](#segment)).
- **Wo die Stellen liegen:** Rund vier von fünf Stellen ab 2 s liegen zwischen zwei Passagen, wo heute keine Regel hinsieht. Nur 2,7 und 10,3 der 34,3 und 52,3 Stellen je Segment fallen in eine Pause, die `gap` schon nennt.
- **Nutzen an den Referenzen:** Der Zuwachs kommt aus zwei Referenzen, C (9 Auslassungen je Seed) und J (15 in zwei von drei Seeds), dazu eine an A. An den anderen acht Referenzen zeigt der Hinweis nichts ([Referenzen](#referenzen)).
- **Blockverluste von `norm` sieht der Hinweis meist nicht:** an G 0 von 14 / 29 / 18 Wörtern der längsten Folge, an H 0 von 15, an F 0 von 12, an J 6 von 38 in Seed 1 und 15 von 16 in Seed 3. `sparse` zeigt den Block an J in Seed 1 (43 Auslassungen) und einen an G in Seed 3 (13).
- **Variation:** Drei der zehn Einstellungen lägen über beiden Schwellen von Punkt 1 und blieben unter 2 Punkten Kosten: Stellen ab 1 s (76,9 % mehr), ab 1 s mit 2 s Brücke (55,8 %) und ab 2 s mit gekappter Wortlänge (57,1 %). Sie waren nicht die vorab festgelegte Einstellung ([Variation](#variation)).
- **`base` zum Vergleich:** Bei einem Lauf mit Blockverlusten bringt derselbe Hinweis 116,0 Auslassungen mehr (83,5 %) bei 0,4 und 0,8 Punkten ([`base`](#base-zum-vergleich)).

## Material und Methode

| | |
| --- | --- |
| Läufe | `norm` (Hauptlauf seit TOOL-109) und `base`, je Seeds 1–3, beide Sitzungen, aus TOOL-93 und TOOL-109 |
| Referenzen | A bis K wie in [TOOL-108](TOOL-108-blockverlust.md#material-und-methode): A, B, D, E, F, G, I in der Pilotsitzung, C, H, J, K in der zweiten Sitzung |
| Diarisierung | die der Sitzung auf dem Roh-WAV, für alle Läufe |
| Schwellen | `review.uncertainty` mit den Defaults seit TOOL-109 (`word_low` 0,8, `avg_logprob` −0,5, `gap_ms` 2500, `min_words_per_second` 1,0) |

- **Passagen und Bewertung im Speicher:** Jeder Lauf wird mit der Diarisierung der Sitzung am Sprecherwechsel geteilt (`min_turn_ms` 500) und ohne Wissens-Hinweise bewertet. Die Seeds 2 und 3 sind ohne Diarisierung gespeichert und wären sonst nicht vergleichbar.
- **Stelle:** Die Diarisierung hört Sprache, und der Lauf hat dort kein Wort (Definition aus TOOL-101). Die Go-Regel gilt an Stellen ab 2 s mit 1 s Brücke zwischen zwei Wörtern.
- **Gezeigte Stelle:** für `gap` die Pause vor dem Wort, das der Grund nennt; für `sparse` die ganze Spanne der Passage; für den Hinweis die Stelle selbst. Eine Auslassung zählt, wenn ihre Wortzeit darin liegt. Wortzeit wie in TOOL-101, Median über die drei Seeds.
- **Passage zur Stelle:** jede Passage, die die Stelle berührt; berührt sie keine, die davor und die danach. „Neu markiert“ sind die `confident`-Passagen darunter.
- **Go-Regel**, festgelegt am 2026-11-27 vor der Messung. Go, wenn alle drei Punkte gelten:
  1. *Zusatznutzen:* Über A bis K, Mittel der drei `norm`-Seeds, liegen mit dem Hinweis mindestens 50 % mehr Auslassungen an einer gezeigten Stelle als mit `gap` und `sparse` allein, und mindestens 20 Auslassungen mehr.
  2. *Treffsicherheit:* In der Hörstichprobe fehlt an mindestens der Hälfte der beantworteten Stellen wirklich Sprache.
  3. *Kosten:* Bisher `confident`-Passagen, die der Hinweis neu markiert, erhöhen die markierte Zeit je Sitzung um höchstens 2 Punkte (Mittel der `norm`-Seeds).
- **Variation:** Mindestlänge 1 / 2 / 3 s, Brücke 0,5 / 1 / 2 s, dazu einmal die Wortlänge auf 1 s gekappt. Sie zählt nicht für die Go-Regel.
- **Kontrolle:**
  - Zahl der Stellen ab 2 s je Seed wie in [TOOL-113](TOOL-113-stellen.md#material-und-methode): 32 / 33 / 38 und 52 / 44 / 61.
  - Auslassungen je Lauf und Referenz wie in [TOOL-109](TOOL-109-hauptlauf.md#wer).
  - Die gespeicherte Fassung von `norm#1` markiert mit ihren Wissens-Hinweisen 87,7 % und 90,3 % der Zeit, wie dort berichtet. Ohne Wissens-Hinweise sind es 87,0 % und 89,9 %.

## Segment

`norm`, Mittel über drei Läufe. Passagen je Lauf: 2007 / 2028 / 2003 (Pilotsitzung) und 1870 / 1763 / 1864 (zweite Sitzung).

Pilotsitzung:

| Stellen | Stellen | Zeit in den Stellen (min) | in einer `gap`-Pause | in einer `sparse`-Passage | in einer sonst markierten Passage | nur in `confident`-Passagen | zwischen zwei Passagen | neu markierte Passagen | deren Zeit (min) | markierte Zeit heute | Zuwachs (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ab 1,0 s, Brücke 0,5 s | 190,3 | 5,5 | 20,3 | 1,7 | 45,7 | 5,7 | 117,0 | 35,3 | 4,2 | 86,6% | 1,6 |
| ab 1,0 s, Brücke 1,0 s | 187,0 | 5,4 | 20,3 | 1,7 | 44,3 | 4,7 | 116,0 | 34,3 | 3,9 | 86,6% | 1,5 |
| ab 1,0 s, Brücke 2,0 s | 105,0 | 3,6 | 20,3 | 0,0 | 11,3 | 1,0 | 72,3 | 17,7 | 1,9 | 86,6% | 0,7 |
| ab 2,0 s, Brücke 0,5 s | 34,3 | 2,0 | 2,7 | 0,0 | 2,3 | 1,0 | 28,3 | 8,7 | 0,8 | 86,6% | 0,3 |
| ab 2,0 s, Brücke 1,0 s | 34,3 | 2,0 | 2,7 | 0,0 | 2,3 | 1,0 | 28,3 | 8,7 | 0,8 | 86,6% | 0,3 |
| ab 2,0 s, Brücke 2,0 s | 34,3 | 2,0 | 2,7 | 0,0 | 2,3 | 1,0 | 28,3 | 8,7 | 0,8 | 86,6% | 0,3 |
| ab 3,0 s, Brücke 0,5 s | 12,7 | 1,1 | 0,3 | 0,0 | 0,0 | 0,0 | 12,3 | 3,3 | 0,2 | 86,6% | 0,1 |
| ab 3,0 s, Brücke 1,0 s | 12,7 | 1,1 | 0,3 | 0,0 | 0,0 | 0,0 | 12,3 | 3,3 | 0,2 | 86,6% | 0,1 |
| ab 3,0 s, Brücke 2,0 s | 12,7 | 1,1 | 0,3 | 0,0 | 0,0 | 0,0 | 12,3 | 3,3 | 0,2 | 86,6% | 0,1 |
| ab 2,0 s, Brücke 1,0 s, Wortlänge gekappt | 50,0 | 2,9 | 2,7 | 6,7 | 13,7 | 1,3 | 25,7 | 8,7 | 0,8 | 86,6% | 0,3 |

Zweite Sitzung:

| Stellen | Stellen | Zeit in den Stellen (min) | in einer `gap`-Pause | in einer `sparse`-Passage | in einer sonst markierten Passage | nur in `confident`-Passagen | zwischen zwei Passagen | neu markierte Passagen | deren Zeit (min) | markierte Zeit heute | Zuwachs (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ab 1,0 s, Brücke 0,5 s | 252,0 | 7,7 | 37,3 | 5,7 | 55,3 | 4,3 | 149,3 | 49,0 | 5,0 | 89,6% | 2,0 |
| ab 1,0 s, Brücke 1,0 s | 247,0 | 7,7 | 37,3 | 5,7 | 54,3 | 4,0 | 145,7 | 46,0 | 4,9 | 89,6% | 1,9 |
| ab 1,0 s, Brücke 2,0 s | 150,7 | 5,5 | 37,3 | 4,0 | 16,3 | 0,0 | 93,0 | 27,7 | 2,9 | 89,6% | 1,1 |
| ab 2,0 s, Brücke 0,5 s | 52,3 | 3,2 | 10,3 | 0,3 | 2,0 | 0,0 | 39,7 | 11,3 | 1,1 | 89,6% | 0,4 |
| ab 2,0 s, Brücke 1,0 s | 52,3 | 3,2 | 10,3 | 0,3 | 2,0 | 0,0 | 39,7 | 11,3 | 1,1 | 89,6% | 0,4 |
| ab 2,0 s, Brücke 2,0 s | 52,3 | 3,2 | 10,3 | 0,3 | 2,0 | 0,0 | 39,7 | 11,3 | 1,1 | 89,6% | 0,4 |
| ab 3,0 s, Brücke 0,5 s | 25,7 | 2,1 | 5,3 | 0,0 | 0,0 | 0,0 | 20,3 | 6,0 | 0,8 | 89,6% | 0,3 |
| ab 3,0 s, Brücke 1,0 s | 25,7 | 2,1 | 5,3 | 0,0 | 0,0 | 0,0 | 20,3 | 6,0 | 0,8 | 89,6% | 0,3 |
| ab 3,0 s, Brücke 2,0 s | 25,7 | 2,1 | 5,3 | 0,0 | 0,0 | 0,0 | 20,3 | 6,0 | 0,8 | 89,6% | 0,3 |
| ab 2,0 s, Brücke 1,0 s, Wortlänge gekappt | 69,7 | 4,2 | 10,3 | 7,0 | 12,3 | 1,7 | 38,3 | 13,0 | 1,3 | 89,6% | 0,5 |

Je Lauf an der Einstellung der Go-Regel (ab 2 s, Brücke 1 s):

| Sitzung | Lauf | Stellen | Zeit in den Stellen (min) | in einer `gap`-Pause | in einer `sparse`-Passage | in einer sonst markierten Passage | nur in `confident`-Passagen | zwischen zwei Passagen | neu markierte Passagen | deren Zeit (min) | markierte Zeit heute | Zuwachs (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Pilotsitzung | norm#1 | 32,0 | 1,6 | 2,0 | 0,0 | 2,0 | 1,0 | 27,0 | 10,0 | 1,4 | 87,0% | 0,5 |
| Pilotsitzung | norm#2 | 33,0 | 1,9 | 2,0 | 0,0 | 3,0 | 1,0 | 27,0 | 8,0 | 0,5 | 85,8% | 0,2 |
| Pilotsitzung | norm#3 | 38,0 | 2,5 | 4,0 | 0,0 | 2,0 | 1,0 | 31,0 | 8,0 | 0,6 | 86,8% | 0,2 |
| zweite Sitzung | norm#1 | 52,0 | 3,0 | 10,0 | 1,0 | 2,0 | 0,0 | 39,0 | 12,0 | 1,1 | 89,9% | 0,4 |
| zweite Sitzung | norm#2 | 44,0 | 2,7 | 11,0 | 0,0 | 3,0 | 0,0 | 30,0 | 12,0 | 1,4 | 90,1% | 0,6 |
| zweite Sitzung | norm#3 | 61,0 | 3,9 | 10,0 | 0,0 | 1,0 | 0,0 | 50,0 | 10,0 | 0,8 | 88,9% | 0,3 |

- **Die meisten Stellen liegen zwischen zwei Passagen:** 28,3 von 34,3 und 39,7 von 52,3 an der Einstellung der Go-Regel. `gap` sieht nur Pausen innerhalb einer Passage; seit dem Teilen am Sprecherwechsel (TOOL-96) fallen die langen Pausen meist zwischen zwei Passagen.
- **Die Nachbarn sind fast immer schon markiert:** Aus 34,3 und 52,3 Stellen werden 8,7 und 11,3 neu markierte Passagen. Der Hinweis wäre deshalb vor allem ein neuer Grund an schon markierten Passagen und eine Ortsangabe, kaum eine neue Markierung.
- **Die Brücke ändert unterhalb der Mindestlänge nichts.** Eine Stelle liegt immer in einer einzigen Pause zwischen zwei Wörtern; eine Brücke bis zur Mindestlänge kann sie nicht schließen. Die Zeilen mit 0,5 s, 1 s und 2 s Brücke sind ab 2 s und ab 3 s deshalb gleich. Nur „ab 1 s, Brücke 2 s“ ist eine eigene Einstellung: Stellen ab 1 s in Pausen über 2 s.
- **Gekappte Wortlänge:** 50,0 statt 34,3 und 69,7 statt 52,3 Stellen. Die zusätzlichen Stellen liegen fast alle in schon markierten Passagen (`sparse` und sonst markiert), die Kosten bleiben bei 0,3 und 0,5 Punkten.

## Referenzen

`norm`, Stellen ab 2 s mit 1 s Brücke. Je Zelle die drei Seeds.

| Referenz | Wörter | Auslassungen | an einer `gap`-Pause | in einer `sparse`-Passage | `gap` oder `sparse` | in einer Stelle | alles zusammen | Zuwachs | in neu markierter Passage | längste Folge ausgelassener Wörter | davon in einer Stelle |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 531 | 29 / 29 / 29 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 | 0 / 0 / 0 | 2 / 2 / 2 | 0 / 0 / 0 |
| B | 441 | 42 / 42 / 42 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 5 / 5 / 5 | 0 / 0 / 0 |
| C | 909 | 88 / 92 / 88 | 2 / 2 / 2 | 7 / 7 / 7 | 8 / 8 / 8 | 10 / 10 / 10 | 17 / 17 / 17 | 9 / 9 / 9 | 1 / 1 / 1 | 8 / 8 / 8 | 8 / 8 / 8 |
| D | 449 | 59 / 64 / 64 | 9 / 9 / 9 | 9 / 9 / 9 | 9 / 9 / 9 | 0 / 0 / 0 | 9 / 9 / 9 | 0 / 0 / 0 | 0 / 0 / 0 | 9 / 9 / 9 | 0 / 0 / 0 |
| E | 369 | 30 / 30 / 30 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 3 / 3 / 3 | 0 / 0 / 0 |
| F | 584 | 80 / 80 / 76 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 12 / 12 / 12 | 0 / 0 / 0 |
| G | 551 | 73 / 95 / 87 | 1 / 1 / 1 | 0 / 0 / 13 | 1 / 1 / 14 | 0 / 0 / 0 | 1 / 1 / 14 | 0 / 0 / 0 | 0 / 0 / 0 | 14 / 29 / 18 | 0 / 0 / 0 |
| H | 470 | 66 / 68 / 67 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 15 / 15 / 15 | 0 / 0 / 0 |
| I | 597 | 60 / 60 / 60 | 0 / 0 / 0 | 6 / 6 / 6 | 6 / 6 / 6 | 0 / 0 / 0 | 6 / 6 / 6 | 0 / 0 / 0 | 0 / 0 / 0 | 9 / 9 / 9 | 0 / 0 / 0 |
| J | 394 | 92 / 41 / 56 | 1 / 2 / 7 | 43 / 0 / 0 | 44 / 2 / 7 | 21 / 0 / 15 | 59 / 2 / 22 | 15 / 0 / 15 | 0 / 0 / 0 | 38 / 4 / 16 | 6 / 0 / 15 |
| K | 437 | 41 / 34 / 39 | 0 / 0 / 0 | 1 / 7 / 1 | 1 / 7 / 1 | 0 / 0 / 0 | 1 / 7 / 1 | 0 / 0 / 0 | 0 / 1 / 0 | 6 / 6 / 6 | 0 / 0 / 0 |

- **Jedes Referenzwort in einer Stelle fehlt auch.** Die Spalte „in einer Stelle“ ist an jeder Referenz gleich der Zahl der Referenzwörter in den Stellen des Laufs (A 1, C 10, J 21 und 15). An den Referenzen hört die Diarisierung dort also Sprache, die der Lauf nicht hat. Das sind 11 bis 32 Wörter je Seed an drei Referenzen; ob es über das Segment gilt, klärt erst die Hörstichprobe.
- **Verstreute Auslassungen bleiben unsichtbar.** Von 644,3 Auslassungen (Summe der Referenzen, Mittel der Seeds) liegen 49,0 an einer Stelle, die `gap` oder `sparse` zeigt, und 69,0 mit dem Hinweis. Rund neun von zehn haben keine Zeitlücke.
- **An J zeigt in Seed 1 schon `sparse` den Block:** 43 der 92 Auslassungen liegen in einer dünnen Passage, der Hinweis fügt 15 hinzu. In Seed 3 zeigt nur der Hinweis die Folge von 16 Wörtern (15 davon).
- **An G, H und F zeigt nichts die langen Folgen**, mit einer Ausnahme: `sparse` an G in Seed 3 (13 Auslassungen).

Summe über die Referenzen, je Referenz das Mittel der Seeds, an der Einstellung der Go-Regel:

| | Auslassungen | `gap` oder `sparse` | in einer Stelle | alles zusammen | Zuwachs | in neu markierter Passage |
| --- | --- | --- | --- | --- | --- | --- |
| Pilotsitzung (A, B, D, E, F, G, I) | 387,0 | 20,3 | 1,0 | 21,3 | 1,0 | 0,0 |
| zweite Sitzung (C, H, J, K) | 257,3 | 28,7 | 22,0 | 47,7 | 19,0 | 1,3 |
| beide | 644,3 | 49,0 | 23,0 | 69,0 | 20,0 | 1,3 |

Die Zeile „beide“ ist die Summe der beiden Aufrufe.

## Stand gegen die Go-Regel

| Punkt | verlangt | gemessen | Stand |
| --- | --- | --- | --- |
| 1, Zusatznutzen | mindestens 50 % mehr Auslassungen an einer gezeigten Stelle und mindestens 20 mehr | 69,0 statt 49,0: 20,0 mehr, 40,8 % | absolut erreicht, relativ verfehlt |
| 2, Treffsicherheit | an mindestens der Hälfte der beantworteten Stellen fehlt Sprache | Stichprobe gezogen, nicht abgetippt | offen |
| 3, Kosten | höchstens 2 Punkte markierte Zeit je Sitzung | 0,3 und 0,4 Punkte | erfüllt |

- **Punkt 1 ist knapp und hängt an zwei Referenzen.** Die 20,0 sind 1 (A), 9 (C) und 10 (J, Mittel aus 15 / 0 / 15). Ein Seed mehr oder weniger mit dem Block an J verschiebt beide Zahlen.
- **Die 49,0 für `gap` und `sparse` sind großzügig gezählt:** `sparse` gilt für die ganze Passage, auch wenn sie den Ort nicht nennt. An J in Seed 1 sind das allein 43.
- **Nach der Regel ist das ein No-Go**, weil alle drei Punkte gelten müssen. Die Stichprobe kann daran nichts ändern; sie beantwortet aber die Frage des Tickets, ob an den Stellen über das Segment wirklich Sprache fehlt.

## Variation

Summe beider Sitzungen für `norm`, je Einstellung. Die Zeilen mit anderer Brücke unterhalb der Mindestlänge sind gleich und weggelassen.

| Stellen | `gap` oder `sparse` | in einer Stelle | alles zusammen | Zuwachs | Zuwachs in Prozent | Kosten in Punkten (Pilot / zweite) |
| --- | --- | --- | --- | --- | --- | --- |
| ab 1 s, Brücke 1 s | 49,0 | 41,7 | 86,7 | 37,7 | 76,9 % | 1,5 / 1,9 |
| ab 1 s, Brücke 2 s | 49,0 | 31,3 | 76,3 | 27,3 | 55,8 % | 0,7 / 1,1 |
| ab 2 s, Brücke 1 s (Go-Regel) | 49,0 | 23,0 | 69,0 | 20,0 | 40,8 % | 0,3 / 0,4 |
| ab 3 s, Brücke 1 s | 49,0 | 0,0 | 49,0 | 0,0 | 0,0 % | 0,1 / 0,3 |
| ab 2 s, Brücke 1 s, Wortlänge gekappt | 49,0 | 39,7 | 77,0 | 28,0 | 57,1 % | 0,3 / 0,5 |

Je Sitzung stehen die Zeilen in der Ausgabe des Skripts:

| Stellen | Pilotsitzung: in einer Stelle | Pilotsitzung: Zuwachs | zweite Sitzung: in einer Stelle | zweite Sitzung: Zuwachs |
| --- | --- | --- | --- | --- |
| ab 1,0 s, Brücke 0,5 s | 11,0 | 11,0 | 30,7 | 26,7 |
| ab 1,0 s, Brücke 1,0 s | 11,0 | 11,0 | 30,7 | 26,7 |
| ab 1,0 s, Brücke 2,0 s | 4,0 | 4,0 | 27,3 | 23,3 |
| ab 2,0 s, Brücke 1,0 s | 1,0 | 1,0 | 22,0 | 19,0 |
| ab 3,0 s, Brücke 1,0 s | 0,0 | 0,0 | 0,0 | 0,0 |
| ab 2,0 s, Brücke 1,0 s, Wortlänge gekappt | 3,0 | 3,0 | 36,7 | 25,0 |

- **Ab 3 s zeigt der Hinweis an den Referenzen nichts mehr.** Die Stellen, in denen Auslassungen liegen, sind 1 bis 3 s lang.
- **Ab 1 s verdoppelt sich fast der Zuwachs**, bei rund fünfmal so vielen Stellen (187,0 und 247,0 je Segment) und 1,5 und 1,9 Punkten Kosten, knapp unter der Grenze von Punkt 3.
- **Die gekappte Wortlänge ist die billigste Verbesserung:** 28,0 statt 20,0 bei fast gleichen Kosten. Sie deckt Stellen auf, die ein über die Lücke gedehntes Wort verdeckt.
- **Vorbehalt:** Diese Einstellungen sind nach dem Blick auf die Zahlen ausgewählt. Die Regel galt an 2 s mit 1 s Brücke.

## `base` zum Vergleich

Stellen ab 2 s mit 1 s Brücke, Mittel über drei Läufe.

| | Pilotsitzung | zweite Sitzung | beide |
| --- | --- | --- | --- |
| Stellen je Segment | 60,7 | 110,3 | |
| davon zwischen zwei Passagen | 46,7 | 91,7 | |
| neu markierte Passagen | 9,7 | 10,0 | |
| Zuwachs markierte Zeit (Punkte) | 0,4 | 0,8 | |
| Auslassungen an den Referenzen | 487,3 | 456,3 | 943,7 |
| davon `gap` oder `sparse` | 38,7 | 100,3 | 139,0 |
| davon in einer Stelle | 33,3 | 86,0 | 119,3 |
| alles zusammen | 69,7 | 185,3 | 255,0 |
| Zuwachs | 31,0 | 85,0 | 116,0 |
| Zuwachs in Prozent | 80,2 % | 84,7 % | 83,5 % |

- **Bei `base` trüge der Hinweis.** Er zeigt die Blöcke, die einzelne Seeds verlieren: an C 40 und 65 zusätzliche Auslassungen in Seed 2 und 3, an D 71 in Seed 1, an K 22 und 41, an J 48 in Seed 1.
- **Der Pegelausgleich hat dem Hinweis den Gegenstand weitgehend genommen.** `norm` verliert weniger Blöcke, und die verbliebenen (G, H, F) haben keine Zeitlücke, in der die Diarisierung Sprache hört.

## Hörstichprobe

- **Gezogen:** je Sitzung 10 Stellen ab 2 s aus `norm#1`, mit festem Zufallswert, außerhalb der Fenster A bis K. Die Zeitfenster (Stelle mit 3 s Rand) stehen in `review/calibration/hint-sample.txt` der jeweiligen Sitzung.
- **Offen:** Die Projektverantwortliche tippt je Fenster ab, was gesagt wird, oder vermerkt „keine Sprache“. `hint.py --sampled` zählt danach aus; das Ergebnis kommt in diesen Abschnitt.

## Grenzen

- **Zwei Sitzungen, elf Fenster**, fast alle dort gewählt, wo Läufe stark voneinander abweichen. Der Zuwachs an den Referenzen stammt aus zwei Fenstern derselben Sitzung.
- **Bewertung ohne Wissens-Hinweise.** Mit ihnen ist rund ein Punkt mehr Zeit markiert (87,7 % statt 87,0 % bei `norm#1`); die Zahl der neu markierten Passagen ist deshalb eher zu hoch als zu niedrig.
- **Wortzeit ausgelassener Wörter ist geschätzt:** Ein Wort, das kein Seed erkannt hat, liegt zwischen seinen Nachbarn. Bei einem Block verteilt das die Wörter gleichmäßig über die Lücke.
- **`sparse` zählt als ganze Passage**, `gap` nur als die eine Pause, die der Grund nennt.
- **Die Schwellen in den Schattenwurzeln sind Kopien vom Tag des `prepare`.** `hint.py` liest sie deshalb aus `--config`; andere Spike-Skripte rechnen an alten Wurzeln mit den Schwellen von damals.
