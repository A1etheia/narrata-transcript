# TOOL-101 — Auslassungen an den Handreferenzen verorten

Stand 2026-11-22. Spike-Bericht zu [TOOL-101](../plans/TOOL-101-omission-location.md), Werkzeug: [`scripts/spike/omissions.py`](../../scripts/spike/omissions.py). Alle Messungen liefen lokal auf gespeicherten Läufen, ohne neue Transkription. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

**Die Vermutung aus TOOL-93 trägt nur zum Teil: Überlappung und kurze Beiträge erhöhen die Auslassungen deutlich, erklären aber die Minderheit. Der Pegel erklärt nichts.** Je nach Referenz bleiben 51–77 % der Auslassungen ohne eines der vier Merkmale ([Erklärt und unerklärt](#erklärt-und-unerklärt)).

- **Überlappung:** drei- bis vierfache Auslassungsrate (22 % gegen 6 % an A, 46 % gegen 13 % an C), aber nur 3–6 % der Wörter liegen darin. An B gibt es keine Überlappung.
- **Beitragslänge:** Die Rate fällt an allen drei Referenzen mit der Länge des Beitrags, von 15–25 % unter 2 s auf 5–7 % über 10 s. Trotzdem liegen 55–95 % der Auslassungen in Beiträgen mit mehr als 10 Wörtern.
- **Pegel:** Die Sprecher liegen im RMS höchstens 4,6 dB auseinander, und an C haben die beiden leiseren Sprecher die wenigsten Auslassungen.
- **Fallback und VAD:** Fallback-Fenster haben keine durchgehend höhere Rate. Die VAD entfernt an A und B je ein Referenzwort, an C liegen 20 Referenzwörter in entferntem Audio.
- **Der Seed entscheidet über ein Drittel bis knapp drei Viertel der Fälle.** Von den Wörtern, die in mindestens einem Seed fehlen, fehlen an A 68 %, an B 45 % und an C 28 % in allen dreien. Der Rest ist in einem anderen Seed erkannt.
- **Zwei Arten von Auslassungen.** Verstreute Einzelwörter mitten im Redefluss hinterlassen keine Zeitlücke und kein Signal. Verlorene Blöcke (an C bis 54 Wörter in zwei Seeds) fallen als Sprache ohne Wörter auf.

**Empfohlene Reihenfolge im Epic:** TOOL-102 (Seed-Vereinigung), TOOL-107 (Hinweis „Sprache ohne Wörter“, neu), TOOL-104 (Recherche, Punkte 3 und 4 zuerst), TOOL-105 (Aufnahme, sobald ein Abend möglich ist), TOOL-103 (Pegelausgleich) zuletzt oder gar nicht. TOOL-82 erst nach TOOL-102 und zugeschnitten auf die Wörter, die in allen Seeds fehlen ([Empfehlung](#empfehlung)).

## Material und Methode

| | |
| --- | --- |
| Läufe | `base` aus TOOL-93 (large-v3-turbo mit Hotwords, Einstellungen der Pipeline), Seeds 1–3, Segment 1 beider Sitzungen |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter, 4 Sprecher |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter, 2 Sprecher |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter, 4 Sprecher |
| Diarisierung | gespeicherter Lauf der Sitzung (pyannote community-1), für alle Seeds derselbe |
| VAD | Silero mit den Optionen der Pipeline (`threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`), auf dem WAV nachgerechnet |

Das Ticket nennt B noch ohne Sprecher. Seit der Parser-Korrektur aus TOOL-96 trägt B zwei Sprecher, deshalb gelten an allen drei Referenzen die Sprecher der Handreferenz.

- **Ausrichtung** wie `calibration.measure`. Das Skript bricht ab, wenn seine Auslassungen von `calibration.align` abweichen. Die Auslassungen je Seed stimmen mit `asr.py score` überein.
- **Wortzeit.** Jedes Referenzwort bekommt eine Zeit, die für alle Seeds gilt: den Median der Zeiten aus den Seeds, die es erkannt haben (Wortanfang plus halbe Wortlänge, die Länge auf 1 s begrenzt). Ersetzte Wörter zählen als erkannt. Wörter, die in allen drei Seeds fehlen, werden gleichmäßig zwischen ihren Nachbarn verteilt.
- **Warum nicht die Nachbarwörter desselben Laufs.** So war es geplant, es trägt aber nicht: An C fehlt in zwei Seeds ein Block von 54 Wörtern, und Whisper dehnt dort das Wort davor über die Lücke. Zwischen den Nachbarn bleibt dann fast keine Zeit, und der Block landet an der falschen Stelle. Die Zeiten der Seeds für dasselbe Wort stimmen dagegen gut überein (Median 0,0 s, siehe „Verortung“ je Referenz).
- **VAD-Prüfung.** Die Summe der nachgerechneten Sprachabschnitte weicht bei jedem Lauf um weniger als 1 s von dessen `duration_after_vad` ab.
- **Schwellen** standen vor der Messung fest (Plan):

| Merkmal | Regel |
| --- | --- |
| Überlappung | Wortzeit in einem Bereich, in dem sich zwei Turns der Diarisierung überlappen |
| Beitragslänge (Diarisierung) | exklusiver Turn an der Wortzeit, gleiche Labels mit höchstens 500 ms Abstand verbunden: unter 2 s, 2–10 s, über 10 s, kein Turn |
| Beitrag laut Handreferenz | Wörter in Folge vom selben Sprecher: 1–3, 4–10, über 10 |
| Pegel des Beitrags | RMS des Turns mindestens 6 dB unter dem lautesten Sprecher des Clips |
| Fallback-Fenster | 30-s-Fenster des Laufs an der Wortzeit mit `temperature > 0` |
| dünnes Fenster | Fenster mit weniger als 0,5 Wörtern pro Sekunde (TOOL-81) |
| von der VAD entfernt | Wortzeit außerhalb aller Sprachabschnitte der VAD |
| Sprache ohne Wörter | Wortzeit in einer Stelle ab 1 s, an der ein Turn läuft und der Lauf kein Wort hat; Pausen zwischen Wörtern bis 1 s gelten als gedeckt |
| erklärt | mindestens eines von Überlappung, Beitrag unter 2 s, leiser Beitrag, Fallback-Fenster |

- **Lesart der Tabellen.** Je Klasse stehen die Auslassungen und die Referenzwörter je Seed, ihr Anteil an allen Auslassungen bzw. allen Referenzwörtern als Mittel und Spanne über die Seeds und die Auslassungen je Wort der Klasse. Ein Merkmal ist überrepräsentiert, wenn sein Anteil an den Auslassungen über seinem Anteil an allen Referenzwörtern liegt.
- **Pegel.** RMS über die Turns des Labels, das dem Sprecher der Handreferenz 1:1 zugeordnet ist, relativ zum lautesten Label im Clip. Die Zeile „ohne Sprache laut Diarisierung“ ist der Pegel außerhalb aller Turns und zeigt den Abstand zum Grundgeräusch.
- **Grenzen.** Je Referenz und Seed gibt es 31–177 Auslassungen. Klassen mit weniger als etwa 20 Referenzwörtern tragen keine Aussage, die absoluten Zahlen stehen deshalb in jeder Zeile. Die Sprecher sind nach Wortzahl nummeriert, Rang 1 ist an A, B und C nicht dieselbe Person.

## Erklärt und unerklärt

Anteil an den Auslassungen und, dahinter, an allen Referenzwörtern, jeweils als Mittel über die drei Seeds. Die Zahlen stammen aus den Tabellen unter [Messwerte](#messwerte).

| | A | B | C |
| --- | --- | --- | --- |
| Auslassungen je Seed | 31 / 31 / 36 | 44 / 42 / 45 | 80 / 156 / 177 |
| Auslassungen je Wort | 6,2 % | 9,9 % | 15,1 % (8,8–19,5) |
| Überlappung | 11,4 % / 3,2 % | 0,0 % / 0,2 % | 18,7 % / 5,7 % |
| Beitrag unter 2 s | 17,9 % / 5,8 % | 15,3 % / 10,2 % | 24,2 % / 14,6 % |
| leiser Beitrag | keiner | 0,0 % / 0,2 % | 16,2 % / 14,4 % |
| Fallback-Fenster | 13,5 % / 11,3 % | 8,9 % / 10,1 % | 14,6 % / 11,0 % |
| **erklärt** (mindestens eines) | 34,5 % / 17,7 % | 23,5 % / 20,0 % | 48,7 % / 33,9 % |
| erklärt, absolut je Seed | 10 / 10 / 14 | 6 / 8 / 17 | 41 / 72 / 86 |
| **unerklärt** | 65,5 % | 76,5 % | 51,3 % |
| Auslassungen je Wort ohne jedes Merkmal | 4,9 % | 9,4 % | 11,8 % |

- **Die vier Merkmale zusammen erklären 24–49 % der Auslassungen.** Sie decken dabei 18–34 % aller Wörter ab, der Überschuss über den Vergleichswert ist also kleiner: 17 Punkte an A, 4 an B, 15 an C.
- **Auch unter den besten Bedingungen fehlen Wörter.** In langen, lauten Beiträgen ohne Überlappung und ohne Fallback fehlen 5 % (A), 9 % (B) und 12 % (C) der Wörter. Das ist der Sockel, den keines der Merkmale erklärt.
- **B ist der Gegenbeleg zur Vermutung.** Dort spricht fast nur eine Person (383 von 441 Wörtern), es gibt keine Überlappung und keinen leisen Beitrag, und trotzdem fehlen 10 % der Wörter, 95 % davon in Beiträgen mit mehr als 10 Wörtern.

### Die Merkmale einzeln

- **Überlappung** ist das stärkste Merkmal je Wort und das seltenste. An A stehen 3–4 von 31–36 Auslassungen darin, an C 20–29 von 80–177. Ein Ansatz, der nur Überlappung behandelt, erreicht höchstens ein Fünftel der Auslassungen.
- **Beitragslänge.** Auslassungen je Wort nach Länge des Turns (unter 2 s / 2–10 s / über 10 s): A 19 % / 8 % / 5 %, B 15 % / 10 % / 7 %, C 25 % / 16 % / 5 %. Nach der Handreferenz fehlen in Beiträgen mit 1–3 Wörtern 44 % der Wörter an A und C, das sind aber nur 16 bzw. 23 Wörter. Kurze Einwürfe gehen also oft verloren, sie machen aber wenig von der Gesamtzahl aus.
- **Kein Turn.** An C liegen 59 Referenzwörter an Stellen, an denen die Diarisierung niemanden hört, und ein Drittel davon fehlt (20–44 % je Seed). An A und B sind es 11 und 23 Wörter.
- **Pegel.** An A liegen die Sprecher innerhalb von 0,9 dB, ihre Auslassungsraten reichen von 4 % bis 19 % (ohne den Sprecher mit nur 4 Wörtern). An C sind zwei Sprecher 3,2 und 4,6 dB leiser als der lauteste und haben mit 7 % und 10 % die niedrigsten Raten. Die höchste Rate (28,5 %) hat ein Sprecher mit 185 Wörtern, der fast so laut ist wie der lauteste; nach TOOL-60 ist das der Mundartsprecher. Der RMS über einen Turn misst allerdings den Raum mit, nicht den Abstand der Stimme zum Störgeräusch im einzelnen Wort.
- **Fallback-Fenster** enthalten 10–11 % der Wörter und 9–15 % der Auslassungen. An C ist die Rate darin höher (22 % gegen 14 %), an B niedriger (8 % gegen 10 %). Das passt zu TOOL-81: Der Fallback begleitet Verluste, er verursacht sie nicht.
- **VAD.** An A und B liegt je ein Referenzwort in entferntem Audio. An C sind es 20, davon fehlen 10–18 je Seed, das sind 7–13 % der Auslassungen. Die Aussage aus TOOL-93, der Decoder lasse die Wörter aus und nicht die VAD, gilt für B; an C entfernt die VAD einen kleinen Teil echter Sprache.

### Stabilität über die Seeds

| | A | B | C |
| --- | --- | --- | --- |
| fehlt in mindestens einem Seed | 41 | 62 | 210 |
| fehlt in allen drei Seeds | 28 (68 %) | 28 (45 %) | 59 (28 %) |
| fehlt nur in einem oder zwei Seeds | 13 | 34 | 151 |
| Auslassungen eines einzelnen Seeds | 31–36 | 42–45 | 80–177 |

- **Eine Vereinigung könnte die Auslassungen höchstens auf die Wörter senken, die in allen Seeds fehlen:** an A von 31–36 auf 28, an B von 42–45 auf 28, an C von 80–177 auf 59. Das ist eine Obergrenze. Sie zählt ersetzte Wörter als erkannt und sagt nichts über die zusätzlichen falschen Wörter, die eine Vereinigung brächte. Beides misst TOOL-102.
- **Die Spanne an C stammt aus Blöcken.** In Seed 2 und 3 fehlt jeweils eine Folge von 54 Wörtern, in Seed 1 ist die längste Folge 11 Wörter. An A und B sind die Folgen 4–9 Wörter lang, bei 21–25 Folgen je Seed. Dort fehlen also meist ein oder zwei Wörter am Stück.

### Sprache ohne Wörter

| | A | B | C |
| --- | --- | --- | --- |
| Clip-Zeit in solchen Stellen je Seed | 2,1 % / 2,1 % / 3,9 % | 1,9 % / 1,9 % / 2,9 % | 3,6 % / 9,8 % / 12,7 % |
| Auslassungen darin je Seed | 1 / 0 / 9 | 1 / 1 / 1 | 2 / 53 / 78 |
| Referenzwörter darin je Seed | 1 / 2 / 12 | 1 / 1 / 3 | 5 / 61 / 85 |

- **Das Signal findet verlorene Blöcke.** In Seed 2 und 3 an C liegen 34 % und 44 % der Auslassungen in solchen Stellen, und 87–92 % der Referenzwörter darin fehlen tatsächlich.
- **Verstreute Auslassungen findet es nicht.** An A und B liegt höchstens eine Auslassung je Seed darin (Ausnahme: A, Seed 3 mit 9). Verstreute Auslassungen haben keine Zeitlücke: Die Wortzeiten davor und danach schließen aneinander an.
- **Kosten über das Segment:** 4,0 % der Sprachzeit an der Pilotsitzung und 6,3–6,5 % an der zweiten Sitzung, mit 59–62 bzw. 103–114 Stellen ab 2 s (3,7–3,9 bzw. 6,7–7,5 min).
- **Offen** ist, wie viele dieser Stellen die Bewertung schon über `gap` oder `sparse` markiert. Das misst TOOL-107.

## Empfehlung

### Reihenfolge im Epic TOOL-100

1. **TOOL-102, Vereinigung mehrerer Seeds.** 32–72 % der betroffenen Wörter fehlen nur in einzelnen Seeds, die Läufe liegen vor, und es braucht kein neues Modell. Das ist der Hebel mit der größten gemessenen Obergrenze.
2. **TOOL-107, Hinweis „Sprache ohne Wörter“.** Kleiner Spike auf demselben Werkzeug. Er macht die Blöcke sichtbar, die ein Seed verliert, auch wenn TOOL-102 kein Go bekommt.
3. **TOOL-104, Recherche.** Die Auslassungen liegen nicht überwiegend in Überlappung und kurzen Beiträgen. Nach der Regel im Ticket haben damit Punkt 3 (neue lokale Modelle) und Punkt 4 (Batched-Pipeline) Vorrang vor sprecherbedingter Erkennung und Sprachtrennung. Die Batched-Pipeline dekodiert je VAD-Abschnitt und ist für die Blockverluste der naheliegendste Kandidat.
4. **TOOL-105, geänderte Aufnahme.** Unabhängig von den übrigen Tickets, sobald ein Abend möglich ist. Der Spike stützt die Begründung „leiser am Mikrofon“ nicht. Getrennte Spuren je Person bleiben trotzdem sinnvoll, weil sie Überlappung und kurze Einwürfe trennen; ein näher gerücktes Einzelmikrofon verspricht nach diesen Zahlen wenig.
5. **TOOL-103, Pegelausgleich.** Zuletzt oder zurückstellen. Kein Beitrag an A und B liegt 6 dB unter dem lautesten Sprecher, und an C haben die leiseren Sprecher die wenigsten Auslassungen. Die Entscheidung liegt bei der Projektverantwortlichen.

### Zuschnitt von TOOL-82

- **Nach TOOL-102, nicht davor.** Ein zweiter Seed ist dasselbe Mittel ohne neues Backend, ohne 9 GB VRAM und ohne zweite venv.
- **Ziel sind die Wörter, die in allen Seeds fehlen** (28 / 28 / 59 an A / B / C). Die holt kein weiterer Whisper-Lauf zurück. Vor dem Backend steht deshalb eine Orakel-Messung wie in TOOL-102: Wie viele dieser Wörter hat Parakeet richtig?
- **Als Alternativtext an der Stelle, nicht als Stufe für die Passage.** Verstreute Auslassungen haben keine Zeitlücke, ein Abgleich auf Wortebene ist das einzige Signal dafür. Auf Passagenebene kostet es nach TOOL-35 rund 32 Punkte markierte Zeit. Der Abnehmer wäre das Review mit Anhören in Narrata (IOA-1326).

## Messwerte

Die Tabellen kommen unverändert aus `omissions.py`.

### Pilotsitzung, Segment 1

VAD: 241,3 min von 300,0 min behalten

| Seed | Sprache laut Diarisierung (min) | davon ohne Wörter | Stellen ab 2 s | Zeit in diesen Stellen (min) |
| --- | --- | --- | --- | --- |
| 1 | 204,1 | 4,0 % | 61 | 3,9 |
| 2 | 204,1 | 4,0 % | 59 | 3,7 |
| 3 | 204,1 | 4,0 % | 62 | 3,8 |

### Referenz A

531 Referenzwörter, Auslassungen je Seed 31 / 31 / 36, je Wort 6,2 % (5,8 %–6,8 %)

| Merkmal | Klasse | Auslassungen je Seed | Anteil an den Auslassungen | Referenzwörter je Seed | Anteil an allen Referenzwörtern | Auslassungen je Wort der Klasse |
| --- | --- | --- | --- | --- | --- | --- |
| Überlappung | ja | 4 / 4 / 3 | 11,4 % (8,3 %–12,9 %) | 17 / 17 / 17 | 3,2 % (3,2 %–3,2 %) | 21,6 % (17,6 %–23,5 %) |
| Überlappung | nein | 27 / 27 / 33 | 88,6 % (87,1 %–91,7 %) | 514 / 514 / 514 | 96,8 % (96,8 %–96,8 %) | 5,6 % (5,3 %–6,4 %) |
| Beitragslänge (Diarisierung) | unter 2 s | 4 / 4 / 10 | 17,9 % (12,9 %–27,8 %) | 31 / 31 / 31 | 5,8 % (5,8 %–5,8 %) | 19,4 % (12,9 %–32,3 %) |
| Beitragslänge (Diarisierung) | 2–10 s | 8 / 8 / 8 | 24,6 % (22,2 %–25,8 %) | 106 / 106 / 106 | 20,0 % (20,0 %–20,0 %) | 7,5 % (7,5 %–7,5 %) |
| Beitragslänge (Diarisierung) | über 10 s | 19 / 19 / 17 | 56,6 % (47,2 %–61,3 %) | 383 / 383 / 383 | 72,1 % (72,1 %–72,1 %) | 4,8 % (4,4 %–5,0 %) |
| Beitragslänge (Diarisierung) | kein Turn | 0 / 0 / 1 | 0,9 % (0,0 %–2,8 %) | 11 / 11 / 11 | 2,1 % (2,1 %–2,1 %) | 3,0 % (0,0 %–9,1 %) |
| Beitrag laut Handreferenz | 1–3 Wörter | 6 / 8 / 7 | 21,5 % (19,4 %–25,8 %) | 16 / 16 / 16 | 3,0 % (3,0 %–3,0 %) | 43,8 % (37,5 %–50,0 %) |
| Beitrag laut Handreferenz | 4–10 Wörter | 6 / 6 / 12 | 24,0 % (19,4 %–33,3 %) | 94 / 94 / 94 | 17,7 % (17,7 %–17,7 %) | 8,5 % (6,4 %–12,8 %) |
| Beitrag laut Handreferenz | über 10 Wörter | 19 / 17 / 17 | 54,5 % (47,2 %–61,3 %) | 421 / 421 / 421 | 79,3 % (79,3 %–79,3 %) | 4,2 % (4,0 %–4,5 %) |
| Pegel des Beitrags | lauter | 31 / 31 / 35 | 99,1 % (97,2 %–100,0 %) | 520 / 520 / 520 | 97,9 % (97,9 %–97,9 %) | 6,2 % (6,0 %–6,7 %) |
| Pegel des Beitrags | kein Turn | 0 / 0 / 1 | 0,9 % (0,0 %–2,8 %) | 11 / 11 / 11 | 2,1 % (2,1 %–2,1 %) | 3,0 % (0,0 %–9,1 %) |
| Fallback-Fenster | ja | 5 / 5 / 3 | 13,5 % (8,3 %–16,1 %) | 60 / 60 / 60 | 11,3 % (11,3 %–11,3 %) | 7,2 % (5,0 %–8,3 %) |
| Fallback-Fenster | nein | 26 / 26 / 33 | 86,5 % (83,9 %–91,7 %) | 471 / 471 / 471 | 88,7 % (88,7 %–88,7 %) | 6,0 % (5,5 %–7,0 %) |
| dünnes Fenster | nein | 31 / 31 / 36 | 100,0 % (100,0 %–100,0 %) | 531 / 531 / 531 | 100,0 % (100,0 %–100,0 %) | 6,2 % (5,8 %–6,8 %) |
| von der VAD entfernt | ja | 1 / 0 / 0 | 1,1 % (0,0 %–3,2 %) | 1 / 1 / 1 | 0,2 % (0,2 %–0,2 %) | 33,3 % (0,0 %–100,0 %) |
| von der VAD entfernt | nein | 30 / 31 / 36 | 98,9 % (96,8 %–100,0 %) | 530 / 530 / 530 | 99,8 % (99,8 %–99,8 %) | 6,1 % (5,7 %–6,8 %) |
| Sprache ohne Wörter | ja | 1 / 0 / 9 | 9,4 % (0,0 %–25,0 %) | 1 / 2 / 12 | 0,9 % (0,2 %–2,3 %) | 58,3 % (0,0 %–100,0 %) |
| Sprache ohne Wörter | nein | 30 / 31 / 27 | 90,6 % (75,0 %–100,0 %) | 530 / 529 / 519 | 99,1 % (97,7 %–99,8 %) | 5,6 % (5,2 %–5,9 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | ja | 10 / 10 / 14 | 34,5 % (32,3 %–38,9 %) | 94 / 94 / 94 | 17,7 % (17,7 %–17,7 %) | 12,1 % (10,6 %–14,9 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | nein | 21 / 21 / 22 | 65,5 % (61,1 %–67,7 %) | 437 / 437 / 437 | 82,3 % (82,3 %–82,3 %) | 4,9 % (4,8 %–5,0 %) |

| Sprecher (Rang nach Wortzahl) | Wörter | Auslassungen je Seed | Auslassungen je Wort | Pegel zum lautesten Sprecher (dB) |
| --- | --- | --- | --- | --- |
| 1 | 379 | 15 / 13 / 14 | 3,7 % (3,4 %–4,0 %) | −0,9 |
| 2 | 103 | 8 / 8 / 8 | 7,8 % (7,8 %–7,8 %) | −0,4 |
| 3 | 45 | 6 / 8 / 12 | 19,3 % (13,3 %–26,7 %) | +0,0 |
| 4 | 4 | 2 / 2 / 2 | 50,0 % (50,0 %–50,0 %) | – |
| ohne Sprache laut Diarisierung | – | – | – | −12,7 |

| Stabilität | Referenzwörter |
| --- | --- |
| fehlt in 3 von 3 Seeds | 28 |
| fehlt in 2 von 3 Seeds | 1 |
| fehlt in 1 von 3 Seeds | 12 |
| fehlt in mindestens einem Seed | 41 |

| Seed | Folgen von Auslassungen | längste Folge (Wörter) | Clip-Zeit mit Sprache ohne Wörter |
| --- | --- | --- | --- |
| 1 | 25 | 4 | 2,1 % |
| 2 | 24 | 4 | 2,1 % |
| 3 | 22 | 9 | 3,9 % |

Verortung: 28 Referenzwörter hat kein Seed erkannt, sie liegen zwischen ihren Nachbarn. Bei 502 Wörtern mit Zeiten aus mehreren Seeds liegen die Zeiten im Median 0,0 s auseinander, bei den 10 % mit dem größten Abstand mindestens 0,0 s.

### Referenz B

441 Referenzwörter, Auslassungen je Seed 44 / 42 / 45, je Wort 9,9 % (9,5 %–10,2 %)

| Merkmal | Klasse | Auslassungen je Seed | Anteil an den Auslassungen | Referenzwörter je Seed | Anteil an allen Referenzwörtern | Auslassungen je Wort der Klasse |
| --- | --- | --- | --- | --- | --- | --- |
| Überlappung | ja | 0 / 0 / 0 | 0,0 % (0,0 %–0,0 %) | 1 / 1 / 1 | 0,2 % (0,2 %–0,2 %) | 0,0 % (0,0 %–0,0 %) |
| Überlappung | nein | 44 / 42 / 45 | 100,0 % (100,0 %–100,0 %) | 440 / 440 / 440 | 99,8 % (99,8 %–99,8 %) | 9,9 % (9,5 %–10,2 %) |
| Beitragslänge (Diarisierung) | unter 2 s | 6 / 7 / 7 | 15,3 % (13,6 %–16,7 %) | 45 / 45 / 45 | 10,2 % (10,2 %–10,2 %) | 14,8 % (13,3 %–15,6 %) |
| Beitragslänge (Diarisierung) | 2–10 s | 22 / 22 / 21 | 49,7 % (46,7 %–52,4 %) | 211 / 211 / 211 | 47,8 % (47,8 %–47,8 %) | 10,3 % (10,0 %–10,4 %) |
| Beitragslänge (Diarisierung) | über 10 s | 10 / 10 / 14 | 25,9 % (22,7 %–31,1 %) | 162 / 162 / 162 | 36,7 % (36,7 %–36,7 %) | 7,0 % (6,2 %–8,6 %) |
| Beitragslänge (Diarisierung) | kein Turn | 6 / 3 / 3 | 9,1 % (6,7 %–13,6 %) | 23 / 23 / 23 | 5,2 % (5,2 %–5,2 %) | 17,4 % (13,0 %–26,1 %) |
| Beitrag laut Handreferenz | 1–3 Wörter | 0 / 0 / 0 | 0,0 % (0,0 %–0,0 %) | 1 / 1 / 1 | 0,2 % (0,2 %–0,2 %) | 0,0 % (0,0 %–0,0 %) |
| Beitrag laut Handreferenz | 4–10 Wörter | 3 / 3 / 1 | 5,4 % (2,2 %–7,1 %) | 7 / 7 / 7 | 1,6 % (1,6 %–1,6 %) | 33,3 % (14,3 %–42,9 %) |
| Beitrag laut Handreferenz | über 10 Wörter | 41 / 39 / 44 | 94,6 % (92,9 %–97,8 %) | 433 / 433 / 433 | 98,2 % (98,2 %–98,2 %) | 9,5 % (9,0 %–10,2 %) |
| Pegel des Beitrags | mind. 6 dB leiser | 0 / 0 / 0 | 0,0 % (0,0 %–0,0 %) | 1 / 1 / 1 | 0,2 % (0,2 %–0,2 %) | 0,0 % (0,0 %–0,0 %) |
| Pegel des Beitrags | lauter | 38 / 39 / 42 | 90,9 % (86,4 %–93,3 %) | 417 / 417 / 417 | 94,6 % (94,6 %–94,6 %) | 9,5 % (9,1 %–10,1 %) |
| Pegel des Beitrags | kein Turn | 6 / 3 / 3 | 9,1 % (6,7 %–13,6 %) | 23 / 23 / 23 | 5,2 % (5,2 %–5,2 %) | 17,4 % (13,0 %–26,1 %) |
| Fallback-Fenster | ja | 0 / 1 / 11 | 8,9 % (0,0 %–24,4 %) | 0 / 49 / 85 | 10,1 % (0,0 %–19,3 %) | 7,5 % (2,0 %–12,9 %) |
| Fallback-Fenster | nein | 44 / 41 / 34 | 91,1 % (75,6 %–100,0 %) | 441 / 392 / 356 | 89,9 % (80,7 %–100,0 %) | 10,0 % (9,6 %–10,5 %) |
| dünnes Fenster | nein | 44 / 42 / 45 | 100,0 % (100,0 %–100,0 %) | 441 / 441 / 441 | 100,0 % (100,0 %–100,0 %) | 9,9 % (9,5 %–10,2 %) |
| von der VAD entfernt | ja | 0 / 0 / 0 | 0,0 % (0,0 %–0,0 %) | 1 / 1 / 1 | 0,2 % (0,2 %–0,2 %) | 0,0 % (0,0 %–0,0 %) |
| von der VAD entfernt | nein | 44 / 42 / 45 | 100,0 % (100,0 %–100,0 %) | 440 / 440 / 440 | 99,8 % (99,8 %–99,8 %) | 9,9 % (9,5 %–10,2 %) |
| Sprache ohne Wörter | ja | 1 / 1 / 1 | 2,3 % (2,2 %–2,4 %) | 1 / 1 / 3 | 0,4 % (0,2 %–0,7 %) | 77,8 % (33,3 %–100,0 %) |
| Sprache ohne Wörter | nein | 43 / 41 / 44 | 97,7 % (97,6 %–97,8 %) | 440 / 440 / 438 | 99,6 % (99,3 %–99,8 %) | 9,7 % (9,3 %–10,0 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | ja | 6 / 8 / 17 | 23,5 % (13,6 %–37,8 %) | 46 / 95 / 123 | 20,0 % (10,4 %–27,9 %) | 11,8 % (8,4 %–13,8 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | nein | 38 / 34 / 28 | 76,5 % (62,2 %–86,4 %) | 395 / 346 / 318 | 80,0 % (72,1 %–89,6 %) | 9,4 % (8,8 %–9,8 %) |

| Sprecher (Rang nach Wortzahl) | Wörter | Auslassungen je Seed | Auslassungen je Wort | Pegel zum lautesten Sprecher (dB) |
| --- | --- | --- | --- | --- |
| 1 | 383 | 42 / 41 / 44 | 11,1 % (10,7 %–11,5 %) | +0,0 |
| 2 | 58 | 2 / 1 / 1 | 2,3 % (1,7 %–3,4 %) | −0,8 |
| ohne Sprache laut Diarisierung | – | – | – | −24,2 |

| Stabilität | Referenzwörter |
| --- | --- |
| fehlt in 3 von 3 Seeds | 28 |
| fehlt in 2 von 3 Seeds | 13 |
| fehlt in 1 von 3 Seeds | 21 |
| fehlt in mindestens einem Seed | 62 |

| Seed | Folgen von Auslassungen | längste Folge (Wörter) | Clip-Zeit mit Sprache ohne Wörter |
| --- | --- | --- | --- |
| 1 | 25 | 5 | 1,9 % |
| 2 | 21 | 5 | 1,9 % |
| 3 | 24 | 6 | 2,9 % |

Verortung: 28 Referenzwörter hat kein Seed erkannt, sie liegen zwischen ihren Nachbarn. Bei 400 Wörtern mit Zeiten aus mehreren Seeds liegen die Zeiten im Median 0,0 s auseinander, bei den 10 % mit dem größten Abstand mindestens 0,2 s.


### Zweite Sitzung, Segment 1

VAD: 222,6 min von 286,9 min behalten

| Seed | Sprache laut Diarisierung (min) | davon ohne Wörter | Stellen ab 2 s | Zeit in diesen Stellen (min) |
| --- | --- | --- | --- | --- |
| 1 | 192,3 | 6,5 % | 103 | 7,5 |
| 2 | 192,3 | 6,5 % | 114 | 7,4 |
| 3 | 192,3 | 6,3 % | 114 | 6,7 |

### Referenz C

909 Referenzwörter, Auslassungen je Seed 80 / 156 / 177, je Wort 15,1 % (8,8 %–19,5 %)

| Merkmal | Klasse | Auslassungen je Seed | Anteil an den Auslassungen | Referenzwörter je Seed | Anteil an allen Referenzwörtern | Auslassungen je Wort der Klasse |
| --- | --- | --- | --- | --- | --- | --- |
| Überlappung | ja | 20 / 23 / 29 | 18,7 % (14,7 %–25,0 %) | 52 / 52 / 52 | 5,7 % (5,7 %–5,7 %) | 46,2 % (38,5 %–55,8 %) |
| Überlappung | nein | 60 / 133 / 148 | 81,3 % (75,0 %–85,3 %) | 857 / 857 / 857 | 94,3 % (94,3 %–94,3 %) | 13,3 % (7,0 %–17,3 %) |
| Beitragslänge (Diarisierung) | unter 2 s | 19 / 39 / 42 | 24,2 % (23,7 %–25,0 %) | 133 / 133 / 133 | 14,6 % (14,6 %–14,6 %) | 25,1 % (14,3 %–31,6 %) |
| Beitragslänge (Diarisierung) | 2–10 s | 35 / 82 / 97 | 50,4 % (43,8 %–54,8 %) | 434 / 434 / 434 | 47,7 % (47,7 %–47,7 %) | 16,4 % (8,1 %–22,4 %) |
| Beitragslänge (Diarisierung) | über 10 s | 14 / 14 / 12 | 11,1 % (6,8 %–17,5 %) | 283 / 283 / 283 | 31,1 % (31,1 %–31,1 %) | 4,7 % (4,2 %–4,9 %) |
| Beitragslänge (Diarisierung) | kein Turn | 12 / 21 / 26 | 14,4 % (13,5 %–15,0 %) | 59 / 59 / 59 | 6,5 % (6,5 %–6,5 %) | 33,3 % (20,3 %–44,1 %) |
| Beitrag laut Handreferenz | 1–3 Wörter | 6 / 12 / 12 | 7,3 % (6,8 %–7,7 %) | 23 / 23 / 23 | 2,5 % (2,5 %–2,5 %) | 43,5 % (26,1 %–52,2 %) |
| Beitrag laut Handreferenz | 4–10 Wörter | 29 / 32 / 56 | 29,5 % (20,5 %–36,2 %) | 142 / 142 / 142 | 15,6 % (15,6 %–15,6 %) | 27,5 % (20,4 %–39,4 %) |
| Beitrag laut Handreferenz | über 10 Wörter | 45 / 112 / 109 | 63,2 % (56,2 %–71,8 %) | 744 / 744 / 744 | 81,8 % (81,8 %–81,8 %) | 11,9 % (6,0 %–15,1 %) |
| Pegel des Beitrags | mind. 6 dB leiser | 12 / 20 / 37 | 16,2 % (12,8 %–20,9 %) | 131 / 131 / 131 | 14,4 % (14,4 %–14,4 %) | 17,6 % (9,2 %–28,2 %) |
| Pegel des Beitrags | lauter | 56 / 115 / 114 | 69,4 % (64,4 %–73,7 %) | 719 / 719 / 719 | 79,1 % (79,1 %–79,1 %) | 13,2 % (7,8 %–16,0 %) |
| Pegel des Beitrags | kein Turn | 12 / 21 / 26 | 14,4 % (13,5 %–15,0 %) | 59 / 59 / 59 | 6,5 % (6,5 %–6,5 %) | 33,3 % (20,3 %–44,1 %) |
| Fallback-Fenster | ja | 11 / 37 / 11 | 14,6 % (6,2 %–23,7 %) | 135 / 130 / 36 | 11,0 % (4,0 %–14,9 %) | 22,4 % (8,1 %–30,6 %) |
| Fallback-Fenster | nein | 69 / 119 / 166 | 85,4 % (76,3 %–93,8 %) | 774 / 779 / 873 | 89,0 % (85,1 %–96,0 %) | 14,4 % (8,9 %–19,0 %) |
| dünnes Fenster | ja | 0 / 13 / 16 | 5,8 % (0,0 %–9,0 %) | 0 / 25 / 19 | 1,6 % (0,0 %–2,8 %) | 68,1 % (52,0 %–84,2 %) |
| dünnes Fenster | nein | 80 / 143 / 161 | 94,2 % (91,0 %–100,0 %) | 909 / 884 / 890 | 98,4 % (97,2 %–100,0 %) | 14,4 % (8,8 %–18,1 %) |
| von der VAD entfernt | ja | 10 / 11 / 18 | 9,9 % (7,1 %–12,5 %) | 20 / 20 / 20 | 2,2 % (2,2 %–2,2 %) | 65,0 % (50,0 %–90,0 %) |
| von der VAD entfernt | nein | 70 / 145 / 159 | 90,1 % (87,5 %–92,9 %) | 889 / 889 / 889 | 97,8 % (97,8 %–97,8 %) | 14,0 % (7,9 %–17,9 %) |
| Sprache ohne Wörter | ja | 2 / 53 / 78 | 26,8 % (2,5 %–44,1 %) | 5 / 61 / 85 | 5,5 % (0,6 %–9,4 %) | 72,9 % (40,0 %–91,8 %) |
| Sprache ohne Wörter | nein | 78 / 103 / 99 | 73,2 % (55,9 %–97,5 %) | 904 / 848 / 824 | 94,5 % (90,6 %–99,4 %) | 10,9 % (8,6 %–12,1 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | ja | 41 / 72 / 86 | 48,7 % (46,2 %–51,2 %) | 336 / 314 / 275 | 33,9 % (30,3 %–37,0 %) | 22,1 % (12,2 %–31,3 %) |
| erklärt (Überlappung, kurz, leise oder Fallback) | nein | 39 / 84 / 91 | 51,3 % (48,8 %–53,8 %) | 573 / 595 / 634 | 66,1 % (63,0 %–69,7 %) | 11,8 % (6,8 %–14,4 %) |

| Sprecher (Rang nach Wortzahl) | Wörter | Auslassungen je Seed | Auslassungen je Wort | Pegel zum lautesten Sprecher (dB) |
| --- | --- | --- | --- | --- |
| 1 | 346 | 22 / 70 / 66 | 15,2 % (6,4 %–20,2 %) | +0,0 |
| 2 | 198 | 15 / 14 / 30 | 9,9 % (7,1 %–15,2 %) | −4,6 |
| 3 | 185 | 35 / 57 / 66 | 28,5 % (18,9 %–35,7 %) | −0,2 |
| 4 | 180 | 8 / 15 / 15 | 7,0 % (4,4 %–8,3 %) | −3,2 |
| ohne Sprache laut Diarisierung | – | – | – | −15,0 |

| Stabilität | Referenzwörter |
| --- | --- |
| fehlt in 3 von 3 Seeds | 59 |
| fehlt in 2 von 3 Seeds | 85 |
| fehlt in 1 von 3 Seeds | 66 |
| fehlt in mindestens einem Seed | 210 |

| Seed | Folgen von Auslassungen | längste Folge (Wörter) | Clip-Zeit mit Sprache ohne Wörter |
| --- | --- | --- | --- |
| 1 | 43 | 11 | 3,6 % |
| 2 | 42 | 54 | 9,8 % |
| 3 | 41 | 54 | 12,7 % |

Verortung: 59 Referenzwörter hat kein Seed erkannt, sie liegen zwischen ihren Nachbarn. Bei 765 Wörtern mit Zeiten aus mehreren Seeds liegen die Zeiten im Median 0,0 s auseinander, bei den 10 % mit dem größten Abstand mindestens 0,2 s.

