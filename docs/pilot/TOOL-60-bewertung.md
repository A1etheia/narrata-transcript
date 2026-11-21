# TOOL-60 — Bewertung von V0.1 und V0.2-Backlog

Stand 2026-11-21. Grundlage sind die Pilotsitzung aus [TOOL-58](TOOL-58-erste-session.md) im Stand nach [TOOL-96](../spikes/TOOL-96-sprecherwechsel.md) und eine zweite Sitzung derselben Gruppe. Der Bericht enthält nur Kennzahlen: keine Session-Keys, keine Gruppe, keine Namen, keine Labels und keinen Transkripttext (TOOL-66). Handreferenzen und Bögen bleiben unter `work/`. Der Agent hat nur die Zählwerte von `transcript calibrate` gesehen. Plan: [`docs/plans/TOOL-60-pilot-review.md`](../plans/TOOL-60-pilot-review.md).

## Messungen

### Material

| | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Dauer | 5:26 h, 2 Aufnahmen | rund 4:52 h, 2 Aufnahmen |
| Stand | nach TOOL-96: 2.166 Passagen, geschnitten am Sprecherwechsel (500 ms) | neu verarbeitet mit `transcript process`, gleicher Stand der Pipeline |
| ASR | large-v3-turbo mit Hotwords (`base` aus TOOL-93), ein Lauf | ebenso |
| Review-Kandidaten | 1.424 (65,7 % der Passagen), 262 pro Stunde | 1.156, 237 pro Stunde |
| Handreferenz | A: Segment 1, 0:00:00–0:04:06, 531 Wörter, 4 Sprecher; B: Segment 1, 1:20:00–1:23:00, 441 Wörter, 2 Sprecher | C: Segment 1, 1:10:00–1:18:08, 905 Wörter, 4 Sprecher |

Referenz C hat die Projektverantwortliche für TOOL-60 neu abgetippt. Sie beginnt mit dem in TOOL-93 (Stufe 4) vorgeschlagenen Fenster und reicht 5 min davor. Mundart ist darin oft wörtlich geschrieben. Für die Messung „Mundart“ unten gibt es eine zweite Fassung, in der nur die Mundartformen ins Hochdeutsche übertragen sind.

### Wortlaut und Review-Auswahl

`transcript calibrate` mit den Schwellen der Projektkonfiguration. „Markiert“ heißt `needs_review` oder `uncertain`. „Übersehen“ sind Fehler in `confident`-Passagen, ein Fehlalarm ist eine markierte Passage ohne Fehler.

| | A | B | C (wörtlich) | C (Hochdeutsch) |
| --- | --- | --- | --- | --- |
| WER | 20,9 % | 25,6 % | 34,7 % | **31,5 %** |
| Ersetzungen / Auslassungen / Einfügungen | 65 / 30 / 16 | 61 / 44 / 8 | 158 / 131 / 25 | 132 / 131 / 23 |
| Auslassungen an allen Fehlern | 27 % | 39 % | 42 % | 46 % |
| Passagen markiert | 15 von 20 (75 %) | 7 von 10 (70 %) | 28 von 45 (62 %) | 28 von 45 (62 %) |
| markierte Zeit | 88,9 % | 80,4 % | 74,3 % | 74,3 % |
| Fehler in markierten Passagen | 95,5 % | 90,3 % | 84,4 % | 84,3 % |
| übersehen, davon Auslassungen | 5, 1 | 11, 6 | 49, 11 | 45, 11 |
| Fehlalarme | 1 | 0 | 4 | 4 |
| AUC der Word-Confidence | 0,78 | 0,75 | 0,78 | 0,78 |
| falsche Wörter unter den unsichersten 30 % | 67,9 % | 60,9 % | 57,4 % | 60,6 % |

- **Die WER an der Pilotsitzung liegt in der bekannten Spanne.** Nach der Neuwertung in TOOL-96 hat `base` über drei Seeds an A 21,3 % und an B 29,8 % (25,6–35,4). Ein Einzellauf kann an B um bis zu 8 Punkte vom Mittel abweichen. Die Werte hier stammen aus dem Lauf, der die Pilotsitzung ausmacht.
- **Die zweite Sitzung ist deutlich schlechter.** An C liegt die WER mit 31,5 % (Hochdeutsch) über beiden Pilot-Referenzen, und die Auslassungen machen fast die Hälfte der Fehler aus. Ob das an der Sitzung oder am Fenster liegt, zeigt eine einzelne Referenz nicht.
- **Die Confidence trägt über beide Sitzungen.** Die AUC ist an A und C gleich (0,78), an B fast gleich. Die Rangfolge der unsicheren Wörter ist übertragbar.
- **Der Schnitt am Sprecherwechsel grenzt ein, lässt aber mehr durch.** Vor TOOL-96 waren an A 100 % und an B 95,6 % der Zeit markiert, übersehen wurden 0 bzw. 4 Fehler (TOOL-58). Jetzt sind es 88,9 % und 80,4 % der Zeit bei 5 und 11 übersehenen Fehlern. An C liegen 15,7 % der Fehler in sicheren Passagen. Wer nur die markierten Passagen prüft, spart rund ein Viertel der Hörzeit und verpasst dafür an C jeden sechsten Fehler.
- **Fehlalarme bleiben selten:** 5 von 50 markierten Passagen an allen drei Referenzen.

### Fehler je Sprecher

`calibrate` zählt die Sprecher der Handreferenz in der Reihenfolge ihres Auftretens, deshalb ist S1 in A, B und C nicht dieselbe Person.

| Referenz | Sprecher (Wörter, falsch) |
| --- | --- |
| A | S1 379, 14,2 % · S2 4, 50,0 % · S3 103, 29,1 % · S4 45, 20,0 % |
| B | S1 383, 25,3 % · S2 58, 13,8 % |
| C (Hochdeutsch) | S1 185, **48,1 %** · S2 346, 28,9 % · S3 180, 17,2 % · S4 198, 21,7 % |

- **Der Mundartsprecher liegt an beiden Abenden beim Zwei- bis Dreifachen.** S1 an C ist laut Projektverantwortlicher dieselbe Person wie der Mundartsprecher aus TOOL-35 (dort 47,5 % gegen 14,0 %). An C sind es 48,1 % gegen 17–29 %. Das ist ein beobachteter Befund an zwei Sitzungen.
- **Wer viel und zusammenhängend spricht, wird besser erkannt.** Das passt zu TOOL-93: Bei kurzen Beiträgen ist der Anteil falscher Wörter am höchsten.

### Mundart

An Referenz C misst `calibrate` dasselbe Transkript gegen beide Fassungen.

| | wörtlich | Hochdeutsch | Differenz |
| --- | --- | --- | --- |
| WER | 34,7 % | 31,5 % | −3,2 Punkte |
| Ersetzungen | 158 | 132 | −26 |
| Auslassungen | 131 | 131 | ±0 |
| Mundartsprecher | 57,4 % | 48,1 % | −9,3 Punkte |
| übrige Sprecher | 21,2–29,2 % | 17,2–28,9 % | −0,3 bis −4,0 Punkte |

- **Whisper schreibt Mundart hochdeutsch.** Rund 26 Wörter, die gegen die wörtliche Referenz als Fehler zählen, sind richtig verstandene Mundart. Für das Archiv zählt der Inhalt, deshalb gilt die Hochdeutsch-Fassung.
- **Normalisierung erklärt den Abstand nicht.** Auch in der Hochdeutsch-Fassung ist beim Mundartsprecher fast jedes zweite Wort falsch. Die Auslassungen ändern sich gar nicht.
- **Alle Sprecher mischen Mundart ein**, laut Projektverantwortlicher stammt die ganze Gruppe aus derselben Gegend. Die übrigen Sprecher verlieren durch die Übertragung ebenfalls bis zu 4 Punkte. Mundart folgt also nicht sauber einer Person.
- **Die Werte aus TOOL-35 sind vermutlich ebenfalls überhöht.** Die Referenzen A und B sind nicht in eine Hochdeutsch-Fassung übertragen. Die 3 Punkte an C zeigen die Größenordnung.

### `similar`-Hinweise auf Archivbegriffe

Plan war ein neuer Bogen mit 50 Hinweisen über die ganze Pilotsitzung, die Urteile aus TOOL-83 übertragen, wo der Hinweis gleich blieb. Das ging nicht: Nach TOOL-96 gibt es 397 statt 403 Hinweise, die gleichmäßige Auswahl trifft deshalb andere Stellen, und 0 der 50 Zeilen liegen an derselben Stelle wie im Bogen aus TOOL-83. Gleichzeitig wäre die offene Frage damit kaum beantwortbar gewesen.

| Methode | `pc` | `recent` | `archive` |
| --- | --- | --- | --- |
| Klang | 2 | 270 | 45 |
| Schreibung | 2 | 60 | **18** |

Ein Bogen mit 50 Zufallszeilen enthielte nur etwa 2 der 18 Archiv-Schreibtreffer. Stattdessen hat die Projektverantwortliche **alle 18** beurteilt. Für die übrigen Kombinationen gilt der Bogen aus TOOL-83 weiter: gleiche ASR, gleicher Snapshot, und an seinen Stellen stehen dieselben Hinweise.

| Methode / Stufe | TOOL-83 (Bogen aus 50) | TOOL-60 (alle Archiv-Schreibtreffer) |
| --- | --- | --- |
| Schreibung / `recent` | 8 von 10 (80 %) | — |
| Schreibung / `archive` | 0 von 1 | **2 von 18 (11 %)** |
| Klang / `recent` | 10 von 32 (31 %) | — |
| Klang / `archive` | 0 von 5 | — |

Nach Score-Band sind die Archiv-Schreibtreffer unter 0,9 zu 0 % richtig (0 von 14), zwischen 0,9 und 0,95 zu 50 % (2 von 4). Über 0,95 gibt es keinen.

- **Archiv-Schreibtreffer sind fast immer Fehlalarm.** Mit 11 % liegen sie weit unter den Schreibtreffern bei `recent` (80 %) und noch unter den Klang-Treffern (28 %). Diese heben eine Passage seit TOOL-35 schon nicht mehr an.
- **Die Wirkung auf die Bewertung ist klein.** Laut TOOL-83 haben nur 15 Passagen ausschließlich Archiv-Schreibtreffer, und 5 davon sind auch aus anderem Grund markiert. Die Hinweisdatei und das Review würden aber um 16 falsche Vorschläge leichter.
