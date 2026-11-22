# TOOL-102 — Vereinigung mehrerer Seeds gegen Auslassungen

Stand 2026-11-22, Zwischenstand nach Segmentvergleich und Orakel. Spike-Bericht zu [TOOL-102](../plans/TOOL-102-seed-union.md), Werkzeug: [`scripts/spike/seeds.py`](../../scripts/spike/seeds.py). Alle Messungen liefen lokal auf gespeicherten Läufen, ohne neue Transkription. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Stand

**Das Orakel erreicht die 3 Punkte nur an C, und dort nur, wenn die Basis einer der beiden Seeds mit Blockverlust ist.** Die Regeln ohne Referenz sind deshalb noch nicht gemessen. Weil B und C auf verschiedenen Seiten der Schwelle liegen, sieht der Plan eine zusätzliche Handreferenz vor ([Entscheidung über Schritt 2](#entscheidung-über-schritt-2)).

- **Orakel im Mittel über die Basis-Seeds:** 0,7 Punkte WER an A, 1,5 an B, 6,3 an C. An C sind es 1,0 Punkte mit Seed 1 als Basis und 8,0 bzw. 9,8 mit Seed 2 und 3.
- **Die Obergrenze aus TOOL-101 war zu günstig.** An B fehlen einem Seed 14–17 Wörter, die nicht in allen Seeds fehlen. Davon hat ein anderer Seed nur 5–9 richtig, die übrigen 8–11 nur als Ersetzung.
- **Eine naive Vereinigung schadet an B** (−2,9 bis −8,2 Punkte): Sie holt 4–6 Auslassungen zurück und bringt 18–38 Einfügungen. An C gewinnt sie nur mit Seed 2 oder 3 als Basis (2,6 und 3,2 Punkte), bei rund 50 Einfügungen.
- **Blockverluste sind die Regel, kein Ausreißer.** Über das Segment verliert jeder Seed an der Pilotsitzung 14–18 Stellen mit mindestens 20 Wörtern, an der zweiten Sitzung 31–35. An 3–9 bzw. 17–21 davon haben beide anderen Seeds den Block.

## Material und Methode

| | |
| --- | --- |
| Läufe | `base` aus TOOL-93 (large-v3-turbo mit Hotwords, Einstellungen der Pipeline), Seeds 1–3, Segment 1 beider Sitzungen |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |

- **Kontrolle.** Die Auslassungen je Seed (31 / 31 / 36, 44 / 42 / 45, 80 / 156 / 177) und die Wörter, die in allen Seeds fehlen (28 / 28 / 59), stimmen mit TOOL-101 überein. Die WER der Basis stimmt an A und B mit `asr.py score` überein.
- **Segmentvergleich, ohne Handreferenz.** Die Tokenfolgen der Seeds werden paarweise ausgerichtet, abschnittsweise je 5 Minuten. Ein Wort zählt dort, wo es beginnt.
  - *Fehlt, steht im anderen:* Wörter, die ein Seed an einer Stelle weniger hat als der andere.
  - *Block:* mindestens 20 solche Wörter in Folge. Die Schwelle stand vor der Messung fest.
  - *Stelle mit Blockverlust:* Blöcke eines Seeds gegen die anderen, zeitlich zusammengefasst. „Gegen alle anderen" heißt, dass beide anderen Seeds dort einen Block mehr haben.
- **Grenze des Segmentvergleichs.** Ohne Referenz ist nicht zu sehen, ob dem einen Seed Wörter fehlen oder der andere welche erfunden hat. Hat nur ein Seed den Block, ist beides möglich. Haben ihn beide anderen, spricht das für einen Verlust.
- **Orakel, je Seed einmal als Basis.**
  - *Rückgewinn:* Für jede Auslassung der Basis, ob ein anderer Seed das Wort richtig hat, nur als Ersetzung, oder ob es in allen fehlt. Die WER des Orakels setzt nur die richtigen Wörter ein und nichts Falsches. Sie ist die Obergrenze für jede Regel, die Wörter aus anderen Seeds an Lücken der Basis einsetzt.
  - *Naive Vereinigung:* Die anderen Läufe werden gegen die Basis ausgerichtet. Was sie an einer Stelle mehr haben, kommt dazu, und die vereinigte Folge wird wie in `calibration.measure` gegen die Handreferenz gemessen.
  - Der Gewinn steht in Punkten WER gegenüber der Basis, negativ heißt schlechter.
- **Schwelle für Schritt 2** (Plan, vor der Messung): Die Regeln ohne Referenz werden nur gemessen, wenn das Orakel im Mittel über die Basis-Seeds an mindestens zwei Referenzen 3 Punkte bringt. Unterschiede unter 3 Punkten gelten seit TOOL-93 als Rauschen.

## Segmentvergleich

| | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Wörter je Seed | 32 972–33 114 | 28 968–29 001 |
| fehlt, steht im anderen (je Paar und Richtung) | 1226–1386, 3,7–4,2 % | 2249–2428, 7,8–8,4 % |
| Blöcke ab 20 Wörtern (je Paar und Richtung) | 8–14 | 27–31 |
| Wörter in diesen Blöcken | 344–572 | 1077–1285 |
| größter Block | 67–106 | 73–107 |
| Stellen mit Blockverlust je Seed | 14 / 14 / 18 | 34 / 31 / 35 |
| davon gegen beide anderen Seeds | 9 / 3 / 5 | 17 / 21 / 21 |
| Zeit in diesen Stellen je Seed (min) | 6,4 / 5,0 / 7,6 | 13,6 / 17,0 / 15,6 |
| 30-s-Fenster mit Abweichung ab 5 Wörtern | 46,2 % | 63,5 % |

- **Jeder Seed verliert Blöcke, und jeder andere.** Die Wortzahl über das Segment ist bei allen Seeds fast gleich (Spanne 0,4 % bzw. 0,1 %). Die Verluste gleichen sich also aus und fallen an der Gesamtzahl nicht auf.
- **Die zweite Sitzung ist doppelt so stark betroffen.** Dort fehlen einem Seed gegenüber einem anderen rund 8 % der Wörter, an der Pilotsitzung rund 4 %. In Blöcken steht davon an der zweiten Sitzung rund die Hälfte, an der Pilotsitzung ein Viertel bis knapp die Hälfte.
- **Die Blöcke an C sind typisch.** Der Block von 54 Wörtern aus TOOL-101 liegt in der Mitte dessen, was über das Segment vorkommt (20 bis über 100 Wörter).
- **Was eine Vereinigung über das Segment höchstens bringt, lässt sich daraus abschätzen:** Die Wörter in Blöcken machen 1,0–1,7 % der Wörter an der Pilotsitzung und 3,7–4,4 % an der zweiten Sitzung aus. Das gilt nur, wenn jeder Block ein echter Verlust ist. Das ist nicht gemessen.
- **Abweichung als Hinweis wäre teuer.** In 46 % bzw. 64 % der 30-s-Fenster weichen zwei Seeds um mindestens 5 Wörter voneinander ab.

## Orakel

### Rückgewinn

Gewinn des Orakels in Punkten WER, je Basis-Seed und im Mittel.

| | A | B | C |
| --- | --- | --- | --- |
| WER der Basis je Seed | 21,3 % / 21,3 % / 21,3 % | 25,6 % / 28,3 % / 35,4 % | 27,3 % / 31,9 % / 33,3 % |
| Auslassungen je Seed | 31 / 31 / 36 | 44 / 42 / 45 | 80 / 156 / 177 |
| ein anderer Seed hat das Wort richtig | 2 / 3 / 6 | 5 / 6 / 9 | 9 / 73 / 89 |
| nur als Ersetzung | 1 / 0 / 2 | 11 / 8 / 8 | 12 / 24 / 29 |
| fehlt in allen Seeds | 28 | 28 | 59 |
| Gewinn je Basis-Seed | 0,4 / 0,6 / 1,1 | 1,1 / 1,4 / 2,0 | 1,0 / 8,0 / 9,8 |
| **Gewinn im Mittel** | **0,7** | **1,5** | **6,3** |

- **A und B bleiben unter der Schwelle**, mit jedem Seed als Basis. An A fehlen 28 der 31–36 Auslassungen in allen Seeds. An B sind die Wörter, die ein anderer Seed an der Stelle hat, zu mehr als der Hälfte falsch erkannt.
- **C hängt am Basis-Seed.** Seed 2 und 3 verlieren dort Blöcke, die Seed 1 hat. Mit einem von ihnen als Basis bringt das Orakel 8–10 Punkte, mit Seed 1 als Basis 1 Punkt.
- **Das Orakel gleicht aus, es verbessert nicht den besten Lauf.** Es senkt die WER an C auf 23,5–26,3 %, an B auf 24,5–33,3 %. An B bleibt die Streuung zwischen den Seeds bestehen, weil sie dort aus Ersetzungen und Einfügungen stammt und nicht aus Auslassungen.

### Naive Vereinigung

| | A | B | C |
| --- | --- | --- | --- |
| Wörter dazu je Basis-Seed | 4 / 4 / 10 | 44 / 33 / 22 | 28 / 130 / 149 |
| Auslassungen weniger | 3 / 3 / 8 | 6 / 4 / 4 | 4 / 81 / 95 |
| Einfügungen mehr | 1 / 1 / 2 | 38 / 29 / 18 | 24 / 49 / 54 |
| Ersetzungen mehr | 1 / 0 / 2 | 4 / 3 / −1 | 1 / 8 / 12 |
| Gewinn je Basis-Seed | 0,2 / 0,4 / 0,8 | −8,2 / −6,3 / −2,9 | −2,3 / 2,6 / 3,2 |
| **Gewinn im Mittel** | **0,4** | **−5,8** | **1,2** |

- **An B sind die zusätzlichen Wörter fast alle falsch:** 22–44 Wörter kommen dazu, 4–6 Auslassungen fallen weg. Die übrigen zählen als Einfügungen. Seed 3 hat dort schon allein 30 Einfügungen.
- **An C trägt die Vereinigung nur, wo ein Block fehlt.** Mit Seed 2 oder 3 als Basis fallen 81 und 95 Auslassungen weg, bei 49 und 54 Einfügungen. Mit Seed 1 als Basis ist sie schlechter als Seed 1 allein.
- **Eine Regel muss also unterscheiden,** ob die Wörter eines anderen Seeds einen verlorenen Block füllen oder nur dessen Einfügungen sind. Die naive Vereinigung kann das nicht.

## Entscheidung über Schritt 2

- **Die Schwelle ist nicht erreicht:** 3 Punkte im Mittel nur an C, nicht an zwei Referenzen.
- **B und C liegen auf verschiedenen Seiten der Schwelle.** Für diesen Fall sieht der Plan eine zusätzliche Handreferenz vor, bevor Schritt 2 entfällt.
- **Was das Fenster klären soll:** A und B liegen nicht an einem Blockverlust (längste Folge 4–9 Wörter), C liegt an einem. Offen ist, ob die Blöcke, die über das Segment auffallen, echte Verluste sind wie an C, und wie viele falsche Wörter die anderen Seeds dort mitbringen.
- **Vorschlag aus dem Segmentvergleich** (`seeds.py --suggest`, die Stellen mit der größten Abweichung zwischen den Seeds, außerhalb der vorhandenen Referenzen):

| Sitzung | Fenster | abweichende Wörter | größtes 30-s-Fenster |
| --- | --- | --- | --- |
| Pilotsitzung | 0:43:00–0:46:00 | 290 | 114 |
| Pilotsitzung | 3:56:00–3:59:00 | 283 | 183 |
| Pilotsitzung | 0:51:30–0:54:30 | 274 | 93 |
| zweite Sitzung | 1:23:00–1:26:00 | 395 | 93 |
| zweite Sitzung | 1:52:30–1:55:30 | 341 | 90 |
| zweite Sitzung | 2:44:30–2:47:30 | 308 | 78 |

- **Empfohlen: Pilotsitzung, 0:43:00–0:46:00.** Beide Referenzen dieser Sitzung liegen unter der Schwelle. Zeigt das Orakel dort einen Gewinn wie an C, gibt es eine zweite Referenz über 3 Punkten aus der anderen Sitzung.
- **Das Fenster ist nicht repräsentativ.** Es liegt dort, wo die Seeds am stärksten abweichen. Es zeigt, was an einem Blockverlust zu holen ist, nicht den Gewinn über die Sitzung. Der liegt nach der Abschätzung oben bei höchstens 1–2 Punkten an der Pilotsitzung und rund 4 Punkten an der zweiten Sitzung.

## Messwerte

Die Tabellen kommen unverändert aus `seeds.py`.

### Pilotsitzung, Segment 1

| Seed | Wörter | ohne Zeit | Wiederholungsanteil |
| --- | --- | --- | --- |
| 1 | 33114 | 0 | 0,8% |
| 2 | 33090 | 0 | 0,6% |
| 3 | 32972 | 0 | 0,6% |

| Seed | gegen Seed | andere Wörter an derselben Stelle | fehlt, steht im anderen | Anteil an dessen Wörtern | Blöcke ab 20 Wörtern | Wörter in Blöcken | größter Block |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 1563 | 1245 | 3,8% | 14 | 572 | 80 |
| 2 | 1 | 1563 | 1269 | 3,8% | 11 | 452 | 67 |
| 1 | 3 | 1591 | 1226 | 3,7% | 12 | 530 | 77 |
| 3 | 1 | 1591 | 1368 | 4,1% | 12 | 526 | 106 |
| 2 | 3 | 1595 | 1268 | 3,8% | 8 | 344 | 78 |
| 3 | 2 | 1595 | 1386 | 4,2% | 11 | 437 | 95 |

| Seed | Stellen mit Blockverlust | davon gegen alle anderen Seeds | Zeit in diesen Stellen (min) |
| --- | --- | --- | --- |
| 1 | 14 | 9 | 6,4 |
| 2 | 14 | 3 | 5,0 |
| 3 | 18 | 5 | 7,6 |

Raster: 277 von 600 Fenstern à 30 s mit Wörtern haben eine Abweichung ab 5 Wörtern (46,2%).

### Referenz A

531 Referenzwörter

| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 21,3% | 65 / 31 / 17 | 2 | 1 | 28 | 20,9% | 0,4 |
| 2 | 21,3% | 64 / 31 / 18 | 3 | 0 | 28 | 20,7% | 0,6 |
| 3 | 21,3% | 61 / 36 / 16 | 6 | 2 | 28 | 20,2% | 1,1 |

| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 4 | 66 / 28 / 18 | 21,1% | 0,2 | 3 | 1 | 1 |
| 2 | 4 | 64 / 28 / 19 | 20,9% | 0,4 | 3 | 1 | 0 |
| 3 | 10 | 63 / 28 / 18 | 20,5% | 0,8 | 8 | 2 | 2 |

Im Mittel über die Basis-Seeds: Orakel 0,7 Punkte, naive Vereinigung 0,4 Punkte.

### Referenz B

441 Referenzwörter

| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 25,6% | 61 / 44 / 8 | 5 | 11 | 28 | 24,5% | 1,1 |
| 2 | 28,3% | 67 / 42 / 16 | 6 | 8 | 28 | 27,0% | 1,4 |
| 3 | 35,4% | 81 / 45 / 30 | 9 | 8 | 28 | 33,3% | 2,0 |

| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 44 | 65 / 38 / 46 | 33,8% | −8,2 | 6 | 38 | 4 |
| 2 | 33 | 70 / 38 / 45 | 34,7% | −6,3 | 4 | 29 | 3 |
| 3 | 22 | 80 / 41 / 48 | 38,3% | −2,9 | 4 | 18 | −1 |

Im Mittel über die Basis-Seeds: Orakel 1,5 Punkte, naive Vereinigung −5,8 Punkte.

### Zweite Sitzung, Segment 1

| Seed | Wörter | ohne Zeit | Wiederholungsanteil |
| --- | --- | --- | --- |
| 1 | 29001 | 0 | 0,6% |
| 2 | 28968 | 0 | 0,5% |
| 3 | 28988 | 0 | 0,9% |

| Seed | gegen Seed | andere Wörter an derselben Stelle | fehlt, steht im anderen | Anteil an dessen Wörtern | Blöcke ab 20 Wörtern | Wörter in Blöcken | größter Block |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 1973 | 2249 | 7,8% | 28 | 1204 | 79 |
| 2 | 1 | 1973 | 2282 | 7,9% | 28 | 1243 | 77 |
| 1 | 3 | 2224 | 2282 | 7,9% | 28 | 1077 | 73 |
| 3 | 1 | 2224 | 2295 | 7,9% | 27 | 1193 | 73 |
| 2 | 3 | 2358 | 2428 | 8,4% | 30 | 1243 | 107 |
| 3 | 2 | 2358 | 2408 | 8,3% | 31 | 1285 | 73 |

| Seed | Stellen mit Blockverlust | davon gegen alle anderen Seeds | Zeit in diesen Stellen (min) |
| --- | --- | --- | --- |
| 1 | 34 | 17 | 13,6 |
| 2 | 31 | 21 | 17,0 |
| 3 | 35 | 21 | 15,6 |

Raster: 363 von 572 Fenstern à 30 s mit Wörtern haben eine Abweichung ab 5 Wörtern (63,5%).

### Referenz C

909 Referenzwörter

| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 27,3% | 111 / 80 / 57 | 9 | 12 | 59 | 26,3% | 1,0 |
| 2 | 31,9% | 110 / 156 / 24 | 73 | 24 | 59 | 23,9% | 8,0 |
| 3 | 33,3% | 93 / 177 / 33 | 89 | 29 | 59 | 23,5% | 9,8 |

| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 28 | 112 / 76 / 81 | 29,6% | −2,3 | 4 | 24 | 1 |
| 2 | 130 | 118 / 75 / 73 | 29,3% | 2,6 | 81 | 49 | 8 |
| 3 | 149 | 105 / 82 / 87 | 30,1% | 3,2 | 95 | 54 | 12 |

Im Mittel über die Basis-Seeds: Orakel 6,3 Punkte, naive Vereinigung 1,2 Punkte.
