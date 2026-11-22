# TOOL-102 — Vereinigung mehrerer Seeds gegen Auslassungen

Stand 2026-11-22, nach Segmentvergleich, Orakel und den Regeln R1 bis R3. Die Entscheidung über Go oder No-Go steht noch aus. Spike-Bericht zu [TOOL-102](../plans/TOOL-102-seed-union.md), Werkzeug: [`scripts/spike/seeds.py`](../../scripts/spike/seeds.py). Alle Messungen liefen lokal auf gespeicherten Läufen, ohne neue Transkription. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Stand

**Das Orakel trägt an drei von fünf Referenzen, aber keine der drei Regeln hebt den Gewinn, ohne anderswo zu schaden.** Wo ein Seed einen Block verliert, haben die anderen ihn oft richtig. Wo kein Block fehlt, sind die zusätzlichen Wörter der anderen Seeds überwiegend falsch, und ohne Referenz unterscheidet keine der Regeln die beiden Fälle.

- **Orakel im Mittel über die Basis-Seeds:** 0,7 Punkte WER an A, 1,5 an B, 6,3 an C, 12,3 an D, 5,2 an E ([Rückgewinn](#rückgewinn)). Die Schwelle von 3 Punkten an zwei Referenzen ist mit C, D und E erreicht.
- **R1, Fensterwahl:** gegenüber dem Mittel der Seeds 6,2 Punkte besser an C und 3,3 an E, aber 6,7 Punkte schlechter an B und 12,5 an D. Gegenüber dem besten einzelnen Seed erreicht R1 an keiner Referenz 3 Punkte ([R1](#r1-fensterwahl)).
- **R2, Alternative an der Lücke:** gibt an C, D und E 26–75 Auslassungen eines Seeds mit Blockverlust ein richtiges Wort. Dafür sind an B 17–43 der 31–48 Alternativ-Wörter falsch, an D bis zu 143 von 193 ([R2](#r2-alternative-an-der-lücke)).
- **R3, Abweichung als Hinweis:** findet 6 der 10 Auslassungen in `confident`-Passagen. Mehr gibt es dort nicht, weil 96–97 % der Zeit schon markiert sind ([R3](#r3-abweichung-als-review-hinweis)).
- **Die Go-Regel für R2 und R3 misst fast nichts.** Sie zählt Auslassungen in `confident`-Passagen. Davon gibt es je Referenz und Seed 0 bis 3, bei 31 bis 177 Auslassungen insgesamt ([Bewertung](#bewertung-nach-der-go-regel)).
- **Blockverluste sind die Regel, kein Ausreißer.** Über das Segment verliert jeder Seed an der Pilotsitzung 14–18 Stellen mit mindestens 20 Wörtern, an der zweiten Sitzung 31–35 ([Segmentvergleich](#segmentvergleich)).

## Material und Methode

| | |
| --- | --- |
| Läufe | `base` aus TOOL-93 (large-v3-turbo mit Hotwords, Einstellungen der Pipeline), Seeds 1–3, Segment 1 beider Sitzungen |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |
| Referenz D | Pilotsitzung, 0:43:00–0:46:00, 449 Wörter, für diesen Spike getippt |
| Referenz E | Pilotsitzung, 1:23:00–1:26:00, 369 Wörter, für diesen Spike getippt |

- **D ist ausgesucht, E nicht.** D liegt dort, wo die Seeds an der Pilotsitzung am stärksten abweichen ([Vorschlag](#zusätzliche-handreferenzen)). Es zeigt, was an einem Blockverlust zu holen ist, nicht den Durchschnitt. E schließt direkt an B an und wurde nicht nach Abweichung gewählt.
- **E war an der zweiten Sitzung vorgesehen.** Vorgeschlagen war dasselbe Fenster dort. Die Referenz passt zur Pilotsitzung (WER 30–41 % gegen deren Läufe, über 130 % gegen die der zweiten Sitzung) und wird deshalb dort gemessen. Die zweite Sitzung hat damit weiter nur C.
- **Kontrolle.** Die Auslassungen je Seed an A, B und C (31 / 31 / 36, 44 / 42 / 45, 80 / 156 / 177) und die Wörter, die in allen Seeds fehlen (28 / 28 / 59), stimmen mit TOOL-101 überein. Die WER der Basis stimmt an A und B mit `asr.py score` überein. R1 über einen einzelnen Seed gibt an jeder Referenz und über das Segment genau dessen Wörter zurück.
- **Segmentvergleich, ohne Handreferenz.** Die Tokenfolgen der Seeds werden paarweise ausgerichtet, abschnittsweise je 5 Minuten. Ein Wort zählt dort, wo es beginnt.
  - *Fehlt, steht im anderen:* Wörter, die ein Seed an einer Stelle weniger hat als der andere.
  - *Block:* mindestens 20 solche Wörter in Folge. Die Schwelle stand vor der Messung fest.
  - *Stelle mit Blockverlust:* Blöcke eines Seeds gegen die anderen, zeitlich zusammengefasst. „Gegen alle anderen" heißt, dass beide anderen Seeds dort einen Block mehr haben.
- **Grenze des Segmentvergleichs.** Ohne Referenz ist nicht zu sehen, ob dem einen Seed Wörter fehlen oder der andere welche erfunden hat.
- **Orakel, je Seed einmal als Basis.**
  - *Rückgewinn:* Für jede Auslassung der Basis, ob ein anderer Seed das Wort richtig hat, nur als Ersetzung, oder ob es in allen fehlt. Die WER des Orakels setzt nur die richtigen Wörter ein und nichts Falsches.
  - *Naive Vereinigung:* Die anderen Läufe werden gegen die Basis ausgerichtet. Was sie an einer Stelle mehr haben, kommt dazu, und die vereinigte Folge wird wie in `calibration.measure` gegen die Handreferenz gemessen.
  - Der Gewinn steht in Punkten WER gegenüber der Basis, negativ heißt schlechter.
- **Regeln ohne Referenz.** Sie nutzen die Ausrichtung aus dem Segmentvergleich. Die Schwellen standen im Plan, vor der Messung.
  - *R1, Fensterwahl:* Je 30-s-Fenster gewinnt der Lauf mit den meisten Wörtern, bei Gleichstand der niedrigste Seed. Ein Lauf scheidet in einem Fenster aus, wenn dort eine Passage die `compression_ratio`-Schwelle erreicht oder der Wiederholungsanteil seiner Wörter über 0 liegt.
  - *R2, Alternative an der Lücke:* Die Basis bleibt. Was ein anderer Seed an einer Stelle mehr hat, gilt als Alternative.
  - *R3, Abweichung als Review-Hinweis:* Eine `confident`-Passage der Basis bekommt einen Hinweis, wenn ein anderer Seed dort um mindestens 1, 2 oder 3 Wörter abweicht.
- **Nach der ersten Zählung ergänzt:** bei R2 die Zeilen „nur Blöcke ab 20 Wörtern" und „nur Blöcke, die jeder andere Seed anbietet". Sie gehören nicht zur Go-Regel.
- **Grenze bei R2 und R3:** Die gespeicherten Läufe haben keine Diarisierung, ihre Passagen sind also nicht am Sprecherwechsel geteilt. Ungeteilt sind 96–97 % der Zeit markiert, geteilt waren es in TOOL-96 79 %. Wie viele Auslassungen dann in `confident`-Passagen lägen, ist nicht gemessen.

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
- **Die zweite Sitzung ist doppelt so stark betroffen.** Dort fehlen einem Seed gegenüber einem anderen rund 8 % der Wörter, an der Pilotsitzung rund 4 %.
- **Die Blöcke an C sind typisch.** Der Block von 54 Wörtern aus TOOL-101 liegt in der Mitte dessen, was über das Segment vorkommt (20 bis über 100 Wörter).
- **Nicht jeder Block ist ein Verlust.** An D stammt ein Block aus Seed 3, der dort 114 Wörter einfügt, die in der Handreferenz nicht stehen ([R2](#r2-alternative-an-der-lücke)).

## Orakel

### Rückgewinn

Gewinn des Orakels in Punkten WER, je Basis-Seed und im Mittel.

| | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| WER der Basis je Seed | 21,3 % / 21,3 % / 21,3 % | 25,6 % / 28,3 % / 35,4 % | 27,3 % / 31,9 % / 33,3 % | 49,4 % / 52,6 % / 81,5 % | 29,8 % / 31,4 % / 40,7 % |
| Auslassungen je Seed | 31 / 31 / 36 | 44 / 42 / 45 | 80 / 156 / 177 | 133 / 115 / 166 | 43 / 46 / 78 |
| ein anderer Seed hat das Wort richtig | 2 / 3 / 6 | 5 / 6 / 9 | 9 / 73 / 89 | 45 / 46 / 75 | 7 / 11 / 40 |
| nur als Ersetzung | 1 / 0 / 2 | 11 / 8 / 8 | 12 / 24 / 29 | 38 / 19 / 41 | 7 / 6 / 9 |
| fehlt in allen Seeds | 28 | 28 | 59 | 50 | 29 |
| Gewinn je Basis-Seed | 0,4 / 0,6 / 1,1 | 1,1 / 1,4 / 2,0 | 1,0 / 8,0 / 9,8 | 10,0 / 10,2 / 16,7 | 1,9 / 3,0 / 10,8 |
| **Gewinn im Mittel** | **0,7** | **1,5** | **6,3** | **12,3** | **5,2** |

- **Der Gewinn hängt daran, ob die Basis dort einen Block verliert.** An C sind es 1,0 Punkte mit Seed 1 und 8,0 bzw. 9,8 mit Seed 2 und 3. An E 1,9 und 3,0 gegen 10,8 mit Seed 3. An A und B verliert kein Seed einen Block, das Orakel bleibt unter 2 Punkten.
- **An D bringt das Orakel mit jeder Basis 10 Punkte oder mehr.** D ist das Fenster mit der größten Abweichung und zugleich das schwerste: Die WER der Basis liegt bei 49–82 %, und 50 der 449 Wörter fehlen in allen Seeds.
- **E zeigt, dass es kein ausgesuchtes Fenster braucht.** E wurde nicht nach Abweichung gewählt und liegt direkt hinter B. Trotzdem verliert Seed 3 dort 40 Wörter, die ein anderer Seed richtig hat.
- **Das Orakel gleicht aus, es verbessert nicht den besten Lauf.** Es senkt die WER an C auf 23,5–26,3 %, an E auf 27,9–29,8 %. Der beste einzelne Seed liegt dort bei 27,3 % und 29,8 %.

### Naive Vereinigung

| | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Wörter dazu je Basis-Seed | 4 / 4 / 10 | 44 / 33 / 22 | 28 / 130 / 149 | 179 / 126 / 83 | 21 / 22 / 50 |
| Auslassungen weniger | 3 / 3 / 8 | 6 / 4 / 4 | 4 / 81 / 95 | 46 / 13 / 38 | 6 / 9 / 45 |
| Einfügungen mehr | 1 / 1 / 2 | 38 / 29 / 18 | 24 / 49 / 54 | 107 / 110 / 44 | 15 / 13 / 5 |
| Ersetzungen mehr | 1 / 0 / 2 | 4 / 3 / −1 | 1 / 8 / 12 | 14 / −10 / −6 | −2 / −1 / 9 |
| Gewinn je Basis-Seed | 0,2 / 0,4 / 0,8 | −8,2 / −6,3 / −2,9 | −2,3 / 2,6 / 3,2 | −16,7 / −19,4 / 0,0 | −1,9 / −0,8 / 8,4 |
| **Gewinn im Mittel** | **0,4** | **−5,8** | **1,2** | **−12,0** | **1,9** |

- **Die Vereinigung trägt nur, wo der Basis ein Block fehlt:** an C mit Seed 2 oder 3 und an E mit Seed 3 als Basis.
- **Sonst kommen vor allem Einfügungen dazu.** An B 18–38, an D mit Seed 1 oder 2 als Basis 107 und 110. Dort übernimmt die Vereinigung die Einfügungen von Seed 3.

## Regeln ohne Referenz

### R1: Fensterwahl

| | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| WER je Seed | 21,3 % / 21,3 % / 21,3 % | 25,6 % / 28,3 % / 35,4 % | 27,3 % / 31,9 % / 33,3 % | 49,4 % / 52,6 % / 81,5 % | 29,8 % / 31,4 % / 40,7 % |
| WER R1 | 20,5 % | 36,5 % | 24,6 % | 73,7 % | 30,6 % |
| E / A / Ei bei R1 | 63 / 28 / 18 | 76 / 45 / 40 | 101 / 81 / 42 | 88 / 129 / 114 | 68 / 38 / 7 |
| **Gewinn gegenüber dem Mittel der Seeds** | **0,8** | **−6,7** | **6,2** | **−12,5** | **3,3** |
| Gewinn gegenüber dem besten Seed | 0,8 | −10,9 | 2,6 | −24,3 | −0,8 |

| über das Segment | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Wörter je Seed | 32 972–33 114 | 28 968–29 001 |
| Wörter R1 | 34 181 | 31 050 |
| Wiederholungsanteil je Seed / R1 | 0,6–0,8 % / 0,2 % | 0,5–0,9 % / 0,3 % |
| markierte Zeit je Seed / R1 | 96,7–97,3 % / 97,2 % | 95,7–96,1 % / 95,7 % |
| Fenster aus Seed 1 / 2 / 3 | 427 / 112 / 61 | 323 / 138 / 111 |
| Fenster, in denen ein Lauf wegen Wiederholung ausschied | 16 | 17 |

- **R1 holt Blöcke zurück:** An C sinken die Auslassungen von 156 und 177 (Seed 2 und 3) auf 81, an E von 78 (Seed 3) auf 38.
- **R1 wählt aber auch den Lauf, der am meisten erfindet.** „Die meisten Wörter" heißt an D Seed 3 mit seinen 114 Einfügungen, an B kommen 40 Einfügungen zusammen statt 8–30. Der Ausschluss wegen Wiederholung greift dort nicht: Er trifft über das Segment nur 16 bzw. 17 Fenster.
- **Über das Segment liefert R1 3 % bzw. 7 % mehr Wörter als ein einzelner Seed.** Ob das zurückgeholte Blöcke oder Einfügungen sind, lässt sich ohne Referenz nicht sagen. An den fünf Referenzen ist es beides.
- **Die markierte Zeit ändert sich nicht.**

### R2: Alternative an der Lücke

Je Basis-Seed, jede Alternative.

| | A | B | C | D | E |
| --- | --- | --- | --- | --- | --- |
| Auslassungen | 31 / 31 / 36 | 44 / 42 / 45 | 80 / 156 / 177 | 133 / 115 / 166 | 43 / 46 / 78 |
| mit richtiger Alternative | 2 / 3 / 6 | 3 / 1 / 4 | 3 / 66 / 75 | 38 / 26 / 52 | 4 / 7 / 36 |
| Alternativ-Wörter | 5 / 4 / 17 | 48 / 33 / 31 | 35 / 156 / 173 | 193 / 126 / 145 | 21 / 23 / 94 |
| davon falsch | 3 / 1 / 5 | 43 / 31 / 17 | 27 / 68 / 76 | 143 / 95 / 42 | 13 / 11 / 24 |
| Zeit der Stellen am Clip | 0,9–1,7 % | 7,4–10,2 % | 6,2–27,8 % | 26,6–39,3 % | 9,9–17,1 % |
| Auslassungen in `confident` | 0 / 0 / 0 | 0 / 3 / 0 | 2 / 1 / 1 | 0 / 2 / 1 | 0 / 0 / 0 |
| davon mit richtiger Alternative | 0 | 0 | 0 | 0 / 1 / 0 | 0 |

Nur Blöcke ab 20 Wörtern, Alternativ-Wörter und davon falsch. An A und B gibt es keine.

| Basis-Seed | C | D | E |
| --- | --- | --- | --- |
| 1 | keine | 130, davon 118 falsch | keine |
| 2 | 52, davon 5 falsch | 61, davon 60 falsch | keine |
| 3 | 115, davon 38 falsch | 121, davon 28 falsch | 62, davon 7 falsch |
| 1, Block in jedem anderen Seed | keine | 95, davon 89 falsch | keine |
| 2, Block in jedem anderen Seed | keine | keine | keine |
| 3, Block in jedem anderen Seed | 63, davon 33 falsch | 121, davon 28 falsch | 62, davon 7 falsch |

| über das Segment, je Basis-Seed | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Stellen mit Alternative | 498 / 541 / 542 | 703 / 635 / 664 |
| Alternativ-Wörter | 2471 / 2537 / 2754 | 4531 / 4710 / 4703 |
| Zeit der Stellen (min) | 18,6 / 19,2 / 20,5 | 32,1 / 34,7 / 32,2 |
| davon außerhalb markierter Passagen (min) | 4,1 / 4,2 / 5,0 | 11,3 / 11,6 / 11,4 |
| markierte Zeit mehr (Punkte) | 1,5 / 1,5 / 1,8 | 4,3 / 4,4 / 4,4 |
| Stellen mit Block ab 20 Wörtern | 16 / 14 / 18 | 35 / 32 / 35 |
| davon Block in jedem anderen Seed | 10 / 3 / 5 | 18 / 20 / 21 |

- **R2 erreicht fast alles, was das Orakel zählt.** An C bekommen 66 und 75 Auslassungen von Seed 2 und 3 ein richtiges Wort (Orakel 73 und 89), an D 26–52 (Orakel 45–75), an E mit Seed 3 als Basis 36 (Orakel 40).
- **Der Preis sind falsche Alternativen.** An B sind 17–43 der 31–48 Alternativ-Wörter falsch, an D mit Seed 1 als Basis 143 von 193. Wer die Alternative liest, bekommt an B fast nur Falsches angeboten.
- **Die Blockgröße trennt nicht.** Ein Block ist an C (Basis Seed 2) und an E zu rund 90 % richtig, an D mit Seed 1 oder 2 als Basis zu über 90 % falsch. Dort stammt er aus den Einfügungen von Seed 3.
- **Übereinstimmung der anderen Seeds trennt auch nicht sicher.** Sie entfernt den falschen Block an D für Seed 2, lässt ihn für Seed 1 aber stehen (89 von 95 falsch) und nimmt Seed 2 an C den richtigen Block. Mit drei Seeds heißt „jeder andere" nur zwei gegen einen.
- **Die Zeit ist kein Hindernis.** Die Stellen nehmen 19–21 min bzw. 32–35 min des Segments ein, und nur 4–5 bzw. 11–12 min davon liegen außerhalb schon markierter Passagen.
- **Zwei Seeds können dasselbe Wort anbieten.** Dann zählt es bei den Alternativ-Wörtern doppelt und bei den Auslassungen einmal.

### R3: Abweichung als Review-Hinweis

An A und E sind alle Passagen im Clip schon markiert, R3 hat dort nichts zu tun. Je Basis-Seed, Hinweis ab 1 Wort Abweichung:

| | B | C | D |
| --- | --- | --- | --- |
| markierte Zeit am Clip vorher | 95,6 % / 99,5 % / 100 % | 89,0 % / 93,4 % / 92,9 % | 100 % / 89,9 % / 97,2 % |
| Fehler in `confident` | 0 / 4 / 0 | 27 / 6 / 6 | 0 / 10 / 5 |
| davon in Passagen mit Hinweis | 0 / 0 / 0 | 23 / 6 / 6 | 0 / 10 / 5 |
| Auslassungen in `confident` | 0 / 3 / 0 | 2 / 1 / 1 | 0 / 2 / 1 |
| davon in Passagen mit Hinweis | 0 / 0 / 0 | 1 / 1 / 1 | 0 / 2 / 1 |
| Passagen mit Hinweis | 1 / 0 / 0 | 2 / 1 / 1 | 0 / 11 / 2 |
| davon ohne Fehler | 1 / 0 / 0 | 0 / 0 / 0 | 0 / 7 / 1 |
| markierte Zeit am Clip mehr (Punkte) | 4,4 / 0,0 / 0,0 | 7,7 / 6,6 / 7,1 | 0,0 / 9,2 / 2,8 |

| über das Segment, je Basis-Seed | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| Passagen `confident` | 133 / 115 / 142 | 148 / 140 / 168 |
| mit Hinweis ab 1 Wort | 50 / 51 / 50 | 71 / 62 / 77 |
| markierte Zeit vorher | 96,8 % / 97,3 % / 96,7 % | 96,1 % / 96,1 % / 95,7 % |
| mehr ab 1 Wort (Punkte) | 1,5 / 1,3 / 1,6 | 2,4 / 2,5 / 3,0 |
| mehr ab 3 Wörtern (Punkte) | 0,9 / 0,9 / 1,2 | 1,7 / 1,5 / 2,2 |

- **R3 findet, was in `confident`-Passagen liegt, an C und D fast vollständig:** 35 von 39 Fehlern an C und alle 15 an D, bei 3–9 Punkten mehr markierter Zeit am Clip. An B findet es die 4 Fehler von Seed 2 nicht.
- **Es liegt dort aber kaum etwas.** Über alle fünf Referenzen und drei Seeds sind es 10 Auslassungen in `confident`-Passagen, 6 davon in Passagen mit Hinweis. Alle übrigen Auslassungen liegen in Passagen, die schon markiert sind.
- **Der Vergleich mit Parakeet aus TOOL-35 passt nicht mehr.** Parakeet fand dort 16 von 17 Fehlern in `confident`-Passagen bei 32 Punkten mehr markierter Zeit über die Sitzung, als die Regeln 49 % der Zeit markierten. Heute sind es an diesen Läufen 96–97 %, ein Hinweis auf Passagenebene kann nur noch 1–3 Punkte hinzufügen.
- **Der Hinweis müsste die Stelle in der Passage nennen, nicht die Passage.** Das leistet R2, mit den falschen Alternativen als Preis.

## Bewertung nach der Go-Regel

Die Go-Regel stand im Plan, vor der Messung.

| Regel | Go-Regel | Ergebnis |
| --- | --- | --- |
| R1 | 3 Punkte WER an mindestens zwei Referenzen | Gegenüber dem Mittel der Seeds an C (6,2) und E (3,3) erreicht, an B und D 6,7 und 12,5 Punkte schlechter. Gegenüber dem besten Seed an keiner Referenz erreicht. |
| R2 | an mindestens zwei Referenzen bekommt die Hälfte der Auslassungen in `confident`-Passagen eine richtige Alternative, bei höchstens 10 Punkten mehr markierter Zeit | Nicht erreicht: 1 von 10 Auslassungen in `confident`. Die Zeit bliebe mit 1,5–4,4 Punkten darunter. |
| R3 | wie R2, mit Hinweis statt Alternative | Dem Wortlaut nach an C (3 von 4) und D (3 von 3) erreicht, bei 1,3–3,0 Punkten mehr markierter Zeit. Das sind 6 Auslassungen von mehreren hundert. |

- **R1 erfüllt den Wortlaut und schadet trotzdem.** Die Go-Regel fragt nur nach dem Gewinn an zwei Referenzen und nicht nach Verlusten an den anderen. Über alle fünf Referenzen liegt R1 im Mittel 1,8 Punkte schlechter als das Mittel der Seeds und 6,5 Punkte schlechter als der beste Seed. Die Pipeline rechnet heute einen Lauf. Gegen Seed 1 allein gewinnt R1 0,8 Punkte an A und 2,7 an C und verliert 10,9 an B, 24,3 an D und 0,8 an E.
- **Die Go-Regel für R2 und R3 hat ihren Gegenstand verloren.** Sie setzt voraus, dass Auslassungen in `confident`-Passagen liegen. Bei 96–97 % markierter Zeit tun das 10 von rund 1200 (Summe über Referenzen und Seeds).
- **Was die Messung über die Go-Regel hinaus zeigt:** Der Gewinn sitzt in den Blockverlusten, und die betreffen jeden Seed. Ein Hinweis „hier hat ein anderer Lauf einen Block mehr" trifft an C und E überwiegend richtige Wörter (67–90 %), an D übernimmt er mit Seed 1 oder 2 als Basis eine Halluzination. Ob sich die beiden Fälle ohne Referenz trennen lassen, hat dieser Spike nicht beantwortet. Blockgröße und Übereinstimmung zweier Seeds reichen dafür nicht.

## Zusätzliche Handreferenzen

Nach A, B und C lag das Orakel nur an C über 3 Punkten, B und C also auf verschiedenen Seiten der Schwelle. Für diesen Fall sah der Plan eine zusätzliche Handreferenz vor. `seeds.py --suggest` schlug die Stellen mit der größten Abweichung zwischen den Seeds vor, außerhalb der vorhandenen Referenzen:

| Sitzung | Fenster | abweichende Wörter | größtes 30-s-Fenster |
| --- | --- | --- | --- |
| Pilotsitzung | 0:43:00–0:46:00 | 290 | 114 |
| Pilotsitzung | 3:56:00–3:59:00 | 283 | 183 |
| Pilotsitzung | 0:51:30–0:54:30 | 274 | 93 |
| zweite Sitzung | 1:23:00–1:26:00 | 395 | 93 |
| zweite Sitzung | 1:52:30–1:55:30 | 341 | 90 |
| zweite Sitzung | 2:44:30–2:47:30 | 308 | 78 |

Getippt wurden das erste Fenster der Pilotsitzung (D) und 1:23:00–1:26:00 an der Pilotsitzung (E, siehe [Material und Methode](#material-und-methode)).

## Messwerte

Die Tabellen kommen unverändert aus `seeds.py`, nur die Überschriften sind zwei Ebenen tiefer gesetzt.

### Pilotsitzung, Segment 1

#### Segment

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

#### Regeln über das Segment

##### R1: Fensterwahl

| Lauf | Wörter | Wiederholungsanteil | Passagen (confident / needs_review / uncertain) | markierte Zeit |
| --- | --- | --- | --- | --- |
| Seed 1 | 33114 | 0,8% | 133 / 596 / 137 | 96,8% |
| Seed 2 | 33090 | 0,6% | 115 / 598 / 151 | 97,3% |
| Seed 3 | 32972 | 0,6% | 142 / 636 / 149 | 96,7% |
| R1 | 34181 | 0,2% | 127 / 820 / 159 | 97,2% |

R1 nimmt 427 Fenster aus Seed 1, 112 Fenster aus Seed 2, 61 Fenster aus Seed 3. In 16 Fenstern schied ein Lauf wegen Wiederholung aus, in 1 davon jeder.

##### R2: Alternative an der Lücke

| Basis-Seed | Alternative ab Wörtern | Stellen mit Alternative | Alternativ-Wörter | Zeit der Stellen (min) | davon außerhalb markierter Passagen (min) | markierte Zeit vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 498 | 2471 | 18,6 | 4,1 | 96,8% | 1,5 |
| 1 | 20 | 16 | 1102 | 5,9 | 2,3 | 96,8% | 0,8 |
| 1 | 20, in jedem anderen Seed | 10 | 865 | 4,4 | 2,0 | 96,8% | 0,7 |
| 2 | 1 | 541 | 2537 | 19,2 | 4,2 | 97,3% | 1,5 |
| 2 | 20 | 14 | 796 | 4,8 | 2,0 | 97,3% | 0,7 |
| 2 | 20, in jedem anderen Seed | 3 | 340 | 1,1 | 0,7 | 97,3% | 0,2 |
| 3 | 1 | 542 | 2754 | 20,5 | 5,0 | 96,7% | 1,8 |
| 3 | 20 | 18 | 963 | 6,5 | 2,2 | 96,7% | 0,8 |
| 3 | 20, in jedem anderen Seed | 5 | 494 | 2,8 | 0,9 | 96,7% | 0,3 |

##### R3: Abweichung als Review-Hinweis

| Basis-Seed | Abweichung ab Wörtern | Passagen `confident` | davon mit Hinweis | Anteil | markierte Zeit vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 133 | 50 | 37,6% | 96,8% | 1,5 |
| 1 | 2 | 133 | 33 | 24,8% | 96,8% | 1,1 |
| 1 | 3 | 133 | 19 | 14,3% | 96,8% | 0,9 |
| 2 | 1 | 115 | 51 | 44,3% | 97,3% | 1,3 |
| 2 | 2 | 115 | 30 | 26,1% | 97,3% | 1,0 |
| 2 | 3 | 115 | 23 | 20,0% | 97,3% | 0,9 |
| 3 | 1 | 142 | 50 | 35,2% | 96,7% | 1,6 |
| 3 | 2 | 142 | 30 | 21,1% | 96,7% | 1,3 |
| 3 | 3 | 142 | 20 | 14,1% | 96,7% | 1,2 |

#### Referenz A

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

##### R1 an A

| Lauf | Wörter im Clip | WER | E / A / Ei |
| --- | --- | --- | --- |
| Seed 1 | 517 | 21,3% | 65 / 31 / 17 |
| Seed 2 | 518 | 21,3% | 64 / 31 / 18 |
| Seed 3 | 511 | 21,3% | 61 / 36 / 16 |
| R1 | 521 | 20,5% | 63 / 28 / 18 |

R1 gegenüber dem Mittel der Seeds: 0,8 Punkte, gegenüber dem besten Seed: 0,8 Punkte.

##### R2 an A

| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger Alternative | Auslassungen in `confident` | mit richtiger Alternative | Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | Zeit der Stellen am Clip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 31 | 2 | 0 | 0 | 5 | 2 | 0 | 3 | 0 | 1,7% |
| 1 | 20 | 31 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 1 | 20, in jedem anderen Seed | 31 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 1 | 31 | 3 | 0 | 0 | 4 | 3 | 0 | 1 | 0 | 1,4% |
| 2 | 20 | 31 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 20, in jedem anderen Seed | 31 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 1 | 36 | 6 | 0 | 0 | 17 | 12 | 0 | 5 | 0 | 0,9% |
| 3 | 20 | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 20, in jedem anderen Seed | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |

Im Mittel über die Basis-Seeds bekommen 0,0% der Auslassungen in `confident` eine richtige Alternative.

##### R3 an A

| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |

Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: 0,0% der Auslassungen in `confident` ab 1, 0,0% der Auslassungen in `confident` ab 2, 0,0% der Auslassungen in `confident` ab 3.

#### Referenz B

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

##### R1 an B

| Lauf | Wörter im Clip | WER | E / A / Ei |
| --- | --- | --- | --- |
| Seed 1 | 405 | 25,6% | 61 / 44 / 8 |
| Seed 2 | 415 | 28,3% | 67 / 42 / 16 |
| Seed 3 | 426 | 35,4% | 81 / 45 / 30 |
| R1 | 436 | 36,5% | 76 / 45 / 40 |

R1 gegenüber dem Mittel der Seeds: −6,7 Punkte, gegenüber dem besten Seed: −10,9 Punkte.

##### R2 an B

| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger Alternative | Auslassungen in `confident` | mit richtiger Alternative | Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | Zeit der Stellen am Clip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 44 | 3 | 0 | 0 | 48 | 5 | 0 | 43 | 0 | 10,2% |
| 1 | 20 | 44 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 1 | 20, in jedem anderen Seed | 44 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 1 | 42 | 1 | 3 | 0 | 33 | 1 | 1 | 31 | 0 | 7,4% |
| 2 | 20 | 42 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 20, in jedem anderen Seed | 42 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 1 | 45 | 4 | 0 | 0 | 31 | 7 | 7 | 17 | 0 | 8,2% |
| 3 | 20 | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 20, in jedem anderen Seed | 45 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |

Im Mittel über die Basis-Seeds bekommen 0,0% der Auslassungen in `confident` eine richtige Alternative.

##### R3 an B

| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | 95,6% | 4,4 |
| 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 95,6% | 0,0 |
| 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 95,6% | 0,0 |
| 2 | 1 | 4 | 0 | 3 | 0 | 0 | 0 | 99,5% | 0,0 |
| 2 | 2 | 4 | 0 | 3 | 0 | 0 | 0 | 99,5% | 0,0 |
| 2 | 3 | 4 | 0 | 3 | 0 | 0 | 0 | 99,5% | 0,0 |
| 3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |

Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: 0,0% der Auslassungen in `confident` ab 1, 0,0% der Auslassungen in `confident` ab 2, 0,0% der Auslassungen in `confident` ab 3.

#### Referenz D

449 Referenzwörter

| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 49,4% | 77 / 133 / 12 | 45 | 38 | 50 | 39,4% | 10,0 |
| 2 | 52,6% | 98 / 115 / 23 | 46 | 19 | 50 | 42,3% | 10,2 |
| 3 | 81,5% | 86 / 166 / 114 | 75 | 41 | 50 | 64,8% | 16,7 |

| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 179 | 91 / 87 / 119 | 66,1% | −16,7 | 46 | 107 | 14 |
| 2 | 126 | 88 / 102 / 133 | 71,9% | −19,4 | 13 | 110 | −10 |
| 3 | 83 | 80 / 128 / 158 | 81,5% | 0,0 | 38 | 44 | −6 |

Im Mittel über die Basis-Seeds: Orakel 12,3 Punkte, naive Vereinigung −12,0 Punkte.

##### R1 an D

| Lauf | Wörter im Clip | WER | E / A / Ei |
| --- | --- | --- | --- |
| Seed 1 | 330 | 49,4% | 77 / 133 / 12 |
| Seed 2 | 357 | 52,6% | 98 / 115 / 23 |
| Seed 3 | 397 | 81,5% | 86 / 166 / 114 |
| R1 | 434 | 73,7% | 88 / 129 / 114 |

R1 gegenüber dem Mittel der Seeds: −12,5 Punkte, gegenüber dem besten Seed: −24,3 Punkte.

##### R2 an D

| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger Alternative | Auslassungen in `confident` | mit richtiger Alternative | Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | Zeit der Stellen am Clip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 133 | 38 | 0 | 0 | 193 | 43 | 7 | 143 | 0 | 39,3% |
| 1 | 20 | 133 | 7 | 0 | 0 | 130 | 7 | 5 | 118 | 0 | 22,6% |
| 1 | 20, in jedem anderen Seed | 133 | 2 | 0 | 0 | 95 | 2 | 4 | 89 | 0 | 16,5% |
| 2 | 1 | 115 | 26 | 2 | 1 | 126 | 26 | 4 | 95 | 1 | 26,8% |
| 2 | 20 | 115 | 0 | 2 | 0 | 61 | 0 | 1 | 60 | 0 | 2,8% |
| 2 | 20, in jedem anderen Seed | 115 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 1 | 166 | 52 | 1 | 0 | 145 | 94 | 7 | 42 | 2 | 26,6% |
| 3 | 20 | 166 | 51 | 1 | 0 | 121 | 91 | 0 | 28 | 2 | 20,6% |
| 3 | 20, in jedem anderen Seed | 166 | 51 | 1 | 0 | 121 | 91 | 0 | 28 | 2 | 20,6% |

Im Mittel über die Basis-Seeds bekommen 16,7% der Auslassungen in `confident` eine richtige Alternative.

##### R3 an D

| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 1 | 10 | 10 | 2 | 2 | 11 | 7 | 89,9% | 9,2 |
| 2 | 2 | 10 | 5 | 2 | 2 | 8 | 5 | 89,9% | 5,8 |
| 2 | 3 | 10 | 1 | 2 | 0 | 5 | 4 | 89,9% | 3,2 |
| 3 | 1 | 5 | 5 | 1 | 1 | 2 | 1 | 97,2% | 2,8 |
| 3 | 2 | 5 | 0 | 1 | 0 | 1 | 1 | 97,2% | 0,5 |
| 3 | 3 | 5 | 0 | 1 | 0 | 0 | 0 | 97,2% | 0,0 |

Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: 66,7% der Auslassungen in `confident` ab 1, 33,3% der Auslassungen in `confident` ab 2, 0,0% der Auslassungen in `confident` ab 3.

#### Referenz E

369 Referenzwörter

| Basis-Seed | WER | E / A / Ei | Auslassungen: ein anderer Seed hat das Wort richtig | nur als Ersetzung | fehlt in allen Seeds | WER Orakel | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 29,8% | 62 / 43 / 5 | 7 | 7 | 29 | 27,9% | 1,9 |
| 2 | 31,4% | 62 / 46 / 8 | 11 | 6 | 29 | 28,5% | 3,0 |
| 3 | 40,7% | 63 / 78 / 9 | 40 | 9 | 29 | 29,8% | 10,8 |

| Basis-Seed | Wörter dazu | E / A / Ei | WER Vereinigung | Gewinn (Punkte) | Auslassungen weniger | Einfügungen mehr | Ersetzungen mehr |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 21 | 60 / 37 / 20 | 31,7% | −1,9 | 6 | 15 | −2 |
| 2 | 22 | 61 / 37 / 21 | 32,2% | −0,8 | 9 | 13 | −1 |
| 3 | 50 | 72 / 33 / 14 | 32,2% | 8,4 | 45 | 5 | 9 |

Im Mittel über die Basis-Seeds: Orakel 5,2 Punkte, naive Vereinigung 1,9 Punkte.

##### R1 an E

| Lauf | Wörter im Clip | WER | E / A / Ei |
| --- | --- | --- | --- |
| Seed 1 | 331 | 29,8% | 62 / 43 / 5 |
| Seed 2 | 331 | 31,4% | 62 / 46 / 8 |
| Seed 3 | 300 | 40,7% | 63 / 78 / 9 |
| R1 | 338 | 30,6% | 68 / 38 / 7 |

R1 gegenüber dem Mittel der Seeds: 3,3 Punkte, gegenüber dem besten Seed: −0,8 Punkte.

##### R2 an E

| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger Alternative | Auslassungen in `confident` | mit richtiger Alternative | Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | Zeit der Stellen am Clip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 43 | 4 | 0 | 0 | 21 | 4 | 4 | 13 | 0 | 9,9% |
| 1 | 20 | 43 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 1 | 20, in jedem anderen Seed | 43 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 1 | 46 | 7 | 0 | 0 | 23 | 8 | 4 | 11 | 0 | 9,9% |
| 2 | 20 | 46 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 20, in jedem anderen Seed | 46 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 1 | 78 | 36 | 0 | 0 | 94 | 70 | 0 | 24 | 0 | 17,1% |
| 3 | 20 | 78 | 28 | 0 | 0 | 62 | 55 | 0 | 7 | 0 | 11,6% |
| 3 | 20, in jedem anderen Seed | 78 | 28 | 0 | 0 | 62 | 55 | 0 | 7 | 0 | 11,6% |

Im Mittel über die Basis-Seeds bekommen 0,0% der Auslassungen in `confident` eine richtige Alternative.

##### R3 an E

| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 1 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 2 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |
| 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 100,0% | 0,0 |

Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: 0,0% der Auslassungen in `confident` ab 1, 0,0% der Auslassungen in `confident` ab 2, 0,0% der Auslassungen in `confident` ab 3.

### Zweite Sitzung, Segment 1

#### Segment

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

#### Regeln über das Segment

##### R1: Fensterwahl

| Lauf | Wörter | Wiederholungsanteil | Passagen (confident / needs_review / uncertain) | markierte Zeit |
| --- | --- | --- | --- | --- |
| Seed 1 | 29001 | 0,6% | 148 / 562 / 231 | 96,1% |
| Seed 2 | 28968 | 0,5% | 140 / 498 / 216 | 96,1% |
| Seed 3 | 28988 | 0,9% | 168 / 552 / 218 | 95,7% |
| R1 | 31050 | 0,3% | 183 / 795 / 240 | 95,7% |

R1 nimmt 323 Fenster aus Seed 1, 138 Fenster aus Seed 2, 111 Fenster aus Seed 3. In 17 Fenstern schied ein Lauf wegen Wiederholung aus, in 1 davon jeder.

##### R2: Alternative an der Lücke

| Basis-Seed | Alternative ab Wörtern | Stellen mit Alternative | Alternativ-Wörter | Zeit der Stellen (min) | davon außerhalb markierter Passagen (min) | markierte Zeit vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 703 | 4531 | 32,1 | 11,3 | 96,1% | 4,3 |
| 1 | 20 | 35 | 2281 | 12,6 | 7,0 | 96,1% | 2,7 |
| 1 | 20, in jedem anderen Seed | 18 | 1764 | 9,3 | 6,2 | 96,1% | 2,3 |
| 2 | 1 | 635 | 4710 | 34,7 | 11,6 | 96,1% | 4,4 |
| 2 | 20 | 32 | 2486 | 15,8 | 8,7 | 96,1% | 3,3 |
| 2 | 20, in jedem anderen Seed | 20 | 2039 | 10,1 | 5,0 | 96,1% | 1,9 |
| 3 | 1 | 664 | 4703 | 32,2 | 11,4 | 95,7% | 4,4 |
| 3 | 20 | 35 | 2478 | 14,5 | 7,6 | 95,7% | 2,9 |
| 3 | 20, in jedem anderen Seed | 21 | 2014 | 11,7 | 6,2 | 95,7% | 2,4 |

##### R3: Abweichung als Review-Hinweis

| Basis-Seed | Abweichung ab Wörtern | Passagen `confident` | davon mit Hinweis | Anteil | markierte Zeit vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 148 | 71 | 48,0% | 96,1% | 2,4 |
| 1 | 2 | 148 | 44 | 29,7% | 96,1% | 2,0 |
| 1 | 3 | 148 | 31 | 20,9% | 96,1% | 1,7 |
| 2 | 1 | 140 | 62 | 44,3% | 96,1% | 2,5 |
| 2 | 2 | 140 | 45 | 32,1% | 96,1% | 2,1 |
| 2 | 3 | 140 | 34 | 24,3% | 96,1% | 1,5 |
| 3 | 1 | 168 | 77 | 45,8% | 95,7% | 3,0 |
| 3 | 2 | 168 | 46 | 27,4% | 95,7% | 2,6 |
| 3 | 3 | 168 | 29 | 17,3% | 95,7% | 2,2 |

#### Referenz C

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

##### R1 an C

| Lauf | Wörter im Clip | WER | E / A / Ei |
| --- | --- | --- | --- |
| Seed 1 | 886 | 27,3% | 111 / 80 / 57 |
| Seed 2 | 777 | 31,9% | 110 / 156 / 24 |
| Seed 3 | 765 | 33,3% | 93 / 177 / 33 |
| R1 | 870 | 24,6% | 101 / 81 / 42 |

R1 gegenüber dem Mittel der Seeds: 6,2 Punkte, gegenüber dem besten Seed: 2,6 Punkte.

##### R2 an C

| Basis-Seed | Alternative ab Wörtern | Auslassungen | mit richtiger Alternative | Auslassungen in `confident` | mit richtiger Alternative | Alternativ-Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | Zeit der Stellen am Clip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 80 | 3 | 2 | 0 | 35 | 5 | 3 | 27 | 0 | 6,2% |
| 1 | 20 | 80 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 1 | 20, in jedem anderen Seed | 80 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 2 | 1 | 156 | 66 | 1 | 0 | 156 | 73 | 15 | 68 | 0 | 20,5% |
| 2 | 20 | 156 | 47 | 1 | 0 | 52 | 47 | 0 | 5 | 0 | 8,1% |
| 2 | 20, in jedem anderen Seed | 156 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0,0% |
| 3 | 1 | 177 | 75 | 1 | 0 | 173 | 85 | 12 | 76 | 0 | 27,8% |
| 3 | 20 | 177 | 66 | 1 | 0 | 115 | 68 | 9 | 38 | 0 | 23,2% |
| 3 | 20, in jedem anderen Seed | 177 | 19 | 1 | 0 | 63 | 21 | 9 | 33 | 0 | 15,1% |

Im Mittel über die Basis-Seeds bekommen 0,0% der Auslassungen in `confident` eine richtige Alternative.

##### R3 an C

| Basis-Seed | Abweichung ab Wörtern | Fehler in `confident` | davon mit Hinweis | Auslassungen in `confident` | davon mit Hinweis | Passagen mit Hinweis | davon ohne Fehler | markierte Zeit am Clip vorher | mehr (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 27 | 23 | 2 | 1 | 2 | 0 | 89,0% | 7,7 |
| 1 | 2 | 27 | 22 | 2 | 1 | 1 | 0 | 89,0% | 6,7 |
| 1 | 3 | 27 | 22 | 2 | 1 | 1 | 0 | 89,0% | 6,7 |
| 2 | 1 | 6 | 6 | 1 | 1 | 1 | 0 | 93,4% | 6,6 |
| 2 | 2 | 6 | 6 | 1 | 1 | 1 | 0 | 93,4% | 6,6 |
| 2 | 3 | 6 | 6 | 1 | 1 | 1 | 0 | 93,4% | 6,6 |
| 3 | 1 | 6 | 6 | 1 | 1 | 1 | 0 | 92,9% | 7,1 |
| 3 | 2 | 6 | 6 | 1 | 1 | 1 | 0 | 92,9% | 7,1 |
| 3 | 3 | 6 | 6 | 1 | 1 | 1 | 0 | 92,9% | 7,1 |

Im Mittel über die Basis-Seeds liegen in Passagen mit Hinweis: 83,3% der Auslassungen in `confident` ab 1, 83,3% der Auslassungen in `confident` ab 2, 83,3% der Auslassungen in `confident` ab 3.

