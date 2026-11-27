# TOOL-113 — Auffällige Stellen neu dekodieren: Stufe 1 an A bis K

Stand 2026-11-27, Stufe 1 gemessen, Entscheidung am Stufentor offen. Bericht zu [TOOL-113](../plans/TOOL-113-redecode-spots.md), Werkzeug: [`scripts/spike/spots.py`](../../scripts/spike/spots.py) und [`scripts/spike/blocks.py`](../../scripts/spike/blocks.py). Kein Lauf wurde neu transkribiert, alles lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

**Nach dem vorab festgelegten Stufentor ist die Go-Regel nicht erreichbar: Nur an einer Referenz (J) liegen genug Auslassungen an auffälligen Stellen, um 3 Punkte WER zu gewinnen. Die Regel verlangt zwei.**

- **Harte Obergrenze** (S2, Mittel der drei Hauptläufe): 7,7 Punkte an J, 2,6 an G, 1,4 an C, sonst höchstens 0,6. An sechs von elf Referenzen liegt keine einzige Auslassung an einer auffälligen Stelle ([Obergrenzen](#obergrenzen)).
- **Anteil an allen Auslassungen:** 61,7 der 584,3 Auslassungen von `norm` liegen in einem Stück (10,6 %), mit „Sprache ohne Wörter“ allein 30,3 (5,2 %) ([Obergrenzen](#obergrenzen)).
- **Der größte Blockverlust wird nicht gefunden:** Die 29 Wörter am Stück an G (Seed 2) liegen an keiner auffälligen Stelle. Die 38 Wörter an J (Seed 1) liegen ganz in einem Stück ([Je Hauptlauf](#je-hauptlauf)).
- **Regel A mit `norm` als Hauptlauf** bringt an J 2,5 Punkte im Mittel (7,6 für den einen Hauptlauf mit Blockverlust), sonst nichts; kein Hauptlauf verliert mehr als 0,7 Punkte ([Regel A mit `norm`](#regel-a-mit-norm-als-hauptlauf)).
- **Kosten wären klein:** Die Stücke umfassen 3,7 bis 13,8 min Audio je Segment von knapp 5 Stunden ([Stellen und Stücke](#stellen-und-stücke)).
- **Stand am Stufentor:** No-Go ohne Stufe 2; die Entscheidung liegt bei der Projektverantwortlichen ([Stufentor](#stufentor)).

## Material und Methode

| | |
| --- | --- |
| Frage | Reicht es, nur die auffälligen Stellen des Hauptlaufs neu zu dekodieren, statt einen zweiten vollen Lauf zu rechnen (TOOL-114)? |
| Zuschnitt | Hauptlauf ist `norm` (TOOL-109, TOOL-112), nicht der Batched-Lauf, von dem das Ticket ausging. Gestuft: Stufe 1 misst aus vorhandenen Läufen, Stufe 2 dekodiert nur nach dem Stufentor (Projektverantwortliche, 2026-11-27) |
| Hauptläufe | `norm`, Seeds 1–3, beide Sitzungen, aus TOOL-109 |
| Läufe für das Orakel | die jeweils anderen `norm`-Seeds, `loud+batched`, `loud+batched+clips+pack`, `loud+batched+clips+join+pad+min` (je Seed 1) aus TOOL-104 und TOOL-112 |
| Modell | `large-v3-turbo`, dieselbe Revision und je Sitzung derselbe Wissens-Snapshot in allen Läufen |
| Referenzen | A bis K wie in [TOOL-108](TOOL-108-blockverlust.md#material-und-methode): A, B, D, E, F, G, I in der Pilotsitzung, C, H, J, K in der zweiten Sitzung. Summen laufen über A bis H, J und K |

- **Auffällige Stelle**, ohne Handreferenz aus dem Hauptlauf selbst. Die Schwellen sind die festen Zahlen aus TOOL-108.
  - *S1:* Die Diarisierung hört mindestens 2 s Sprache, und der Hauptlauf hat dort kein Wort.
  - *S2:* S1, dazu jede Passage des Hauptlaufs mit `compression_ratio` ab 2,4 oder `avg_logprob` bis −1.
- **Stück:** die Stelle mit 2 s Polster je Seite, sich berührende Stücke verbunden. Das ist das Audio, das ein zweiter Dekodiergang bekäme.
- **Harte Obergrenze:** die Auslassungen des Hauptlaufs mit Wortzeit in einem Stück, als Punkte WER. Mehr kann das Neu-Dekodieren dieser Stücke nicht bringen: Jedes dieser Wörter käme richtig zurück und kein falsches dazu.
- **Orakel:** wie viele dieser Auslassungen ein anderer vorhandener Lauf richtig hat.
- **Wortzeit:** eine Zeit je Referenzwort wie in `omissions.py`, als Median über alle geladenen Läufe, die das Wort erkannt haben.
- **Kontrolle:** `base` gibt weiter 21,3 % an A und 29,8 % an B. Die Zahl der Stellen S1 je Seed stimmt mit „Stellen ab 2 s“ in [TOOL-112](TOOL-112-redebeitrag.md#abschnitte) überein (32 / 33 / 38 und 52 / 44 / 61), die Auslassungen je Lauf und Referenz mit der Tabelle dort.

### Go-Regel

Vor der Messung festgelegt, im Wortlaut des Plans. Go, wenn alle drei Punkte gelten:

1. An mindestens zwei Referenzen sinkt die WER um 3 Punkte gegenüber dem Mittel der drei Hauptläufe. F und I zählen zusammen als eine Referenz.
2. An keiner Referenz A bis K verliert ein Hauptlauf mehr als 1 Punkt.
3. Das Mittel über die Referenzen liegt nicht unter dem von Regel A am selben Hauptlauf mit der besten gemessenen Quelle.

### Stufentor

Vor der Messung festgelegt, im Wortlaut des Plans:

- Harte Obergrenze (S2, Mittel der Hauptläufe) erreicht nicht an zwei Referenzen 3 Punkte: Punkt 1 der Go-Regel ist unerreichbar, No-Go ohne Stufe 2.
- Orakel erreicht an zwei Referenzen 3 Punkte: Stufe 2 läuft.
- Dazwischen entscheidet die Projektverantwortliche mit den Zahlen.

## Stellen und Stücke

Pilotsitzung, Segment von 5,00 h:

| Stellen | Hauptlauf | Stellen | Zeit in den Stellen (min) | Stücke | Median Stück (s) | längstes Stück (s) | Summe der Stücke (min) | Anteil am Segment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 32 | 1,6 | 30 | 6,7 | 12,1 | 3,7 | 1,2% |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 33 | 1,9 | 30 | 6,8 | 21,8 | 4,1 | 1,4% |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 38 | 2,5 | 37 | 6,7 | 27,3 | 5,0 | 1,7% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 44 | 5,4 | 36 | 6,8 | 43,4 | 7,9 | 2,6% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 72 | 7,9 | 39 | 7,6 | 65,8 | 11,3 | 3,8% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 79 | 8,3 | 47 | 7,2 | 64,7 | 11,9 | 4,0% |

Zweite Sitzung, Segment von 4,78 h:

| Stellen | Hauptlauf | Stellen | Zeit in den Stellen (min) | Stücke | Median Stück (s) | längstes Stück (s) | Summe der Stücke (min) | Anteil am Segment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 52 | 3,0 | 45 | 6,9 | 19,9 | 6,2 | 2,2% |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 44 | 2,7 | 40 | 7,2 | 19,8 | 5,4 | 1,9% |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 61 | 3,9 | 48 | 7,5 | 35,2 | 7,5 | 2,6% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 95 | 7,8 | 57 | 7,6 | 36,8 | 12,3 | 4,3% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 80 | 8,3 | 53 | 7,6 | 43,6 | 12,3 | 4,3% |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 88 | 9,3 | 58 | 7,8 | 57,4 | 13,8 | 4,8% |

- **Wenig Audio:** S1 ergibt 30 bis 48 Stücke mit 3,7 bis 7,5 min je Segment, S2 36 bis 58 Stücke mit 7,9 bis 13,8 min. Das sind 1,2 bis 4,8 % des Segments.
- **Die Dekodierwerte verdoppeln die Zeit:** Die Stellen selbst wachsen von 1,6 bis 3,9 min auf 5,4 bis 9,3 min, weil S2 ganze Passagen aufnimmt.
- **Die Seeds markieren verschieden viel:** In der Pilotsitzung hat S2 bei Seed 1 44 Stellen, bei Seed 3 79.

## Obergrenzen

Je Zelle harte Obergrenze · Orakel aus den vorhandenen Läufen, in Punkten WER, Mittel über die drei Hauptläufe.

| Stellen | A | B | C | D | E | F | G | H | I | J | K |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | 0,4 · 0,2 | 0,0 · 0,0 | 1,2 · 0,6 | 0,0 · 0,0 | 0,0 · 0,0 | 0,0 · 0,0 | 0,0 · 0,0 | 0,0 · 0,0 | 0,0 · 0,0 | 4,4 · 2,8 | 0,0 · 0,0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | 0,4 · 0,2 | 0,0 · 0,0 | 1,4 · 0,7 | 0,6 · 0,1 | 0,0 · 0,0 | 0,0 · 0,0 | 2,6 · 1,2 | 0,0 · 0,0 | 0,0 · 0,0 | 7,7 · 5,3 | 0,0 · 0,0 |

Auslassungen im Mittel der Hauptläufe, Summe über A bis H, J und K:

| | Wörter | Anteil |
| --- | --- | --- |
| Auslassungen von `norm` | 584,3 | 100 % |
| davon in einem Stück, S1 | 30,3 | 5,2 % |
| davon in einem Stück, S2 | 61,7 | 10,6 % |
| davon in einem anderen Lauf richtig, S2 | 35,3 | 6,0 % |

- **3 Punkte erreicht nur J.** Mit S2 liegt die harte Obergrenze an J bei 7,7 Punkten, an G bei 2,6 und an C bei 1,4. An B, E, F, H, I und K liegt in keinem Hauptlauf eine Auslassung in einem Stück.
- **Neun von zehn Auslassungen liegen woanders.** Sie stehen an Stellen, an denen der Hauptlauf Wörter hat und der Decoder sie selbst nicht schlecht bewertet.
- **„Sprache ohne Wörter“ allein** erreicht an J 4,4 Punkte und sonst höchstens 1,2.
- **Das Orakel liegt bei gut der Hälfte der harten Obergrenze:** Von den 61,7 Auslassungen in einem Stück hat ein anderer vorhandener Lauf 35,3 richtig.

### Je Hauptlauf

Die Referenzen, an denen eine Auslassung in einem Stück liegt, 1:1 aus dem Skript.

Referenz A, 531 Referenzwörter:

| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | längste Folge ausgelassener Wörter | davon in einem Stück |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 20,2% | 29 | 2 | 0,4 | 1 | 0,2 | 2 | 0 |

Referenz C, 909 Referenzwörter:

| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | längste Folge ausgelassener Wörter | davon in einem Stück |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 23,9% | 88 | 11 | 1,2 | 5 | 0,6 | 8 | 8 |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 24,8% | 92 | 11 | 1,2 | 5 | 0,6 | 8 | 8 |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 23,2% | 88 | 11 | 1,2 | 5 | 0,6 | 8 | 8 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 23,9% | 88 | 11 | 1,2 | 5 | 0,6 | 8 | 8 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 24,8% | 92 | 15 | 1,7 | 8 | 0,9 | 8 | 8 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 23,2% | 88 | 11 | 1,2 | 5 | 0,6 | 8 | 8 |

Referenz D, 449 Referenzwörter:

| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | längste Folge ausgelassener Wörter | davon in einem Stück |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 36,1% | 59 | 0 | 0,0 | 0 | 0,0 | 9 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 38,1% | 64 | 0 | 0,0 | 0 | 0,0 | 9 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 36,1% | 64 | 0 | 0,0 | 0 | 0,0 | 9 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 36,1% | 59 | 0 | 0,0 | 0 | 0,0 | 9 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 38,1% | 64 | 8 | 1,8 | 2 | 0,4 | 9 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 36,1% | 64 | 0 | 0,0 | 0 | 0,0 | 9 | 0 |

Referenz G, 551 Referenzwörter:

| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | längste Folge ausgelassener Wörter | davon in einem Stück |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 42,1% | 73 | 0 | 0,0 | 0 | 0,0 | 14 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 45,0% | 95 | 0 | 0,0 | 0 | 0,0 | 29 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 39,7% | 87 | 0 | 0,0 | 0 | 0,0 | 18 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 42,1% | 73 | 43 | 7,8 | 20 | 3,6 | 14 | 14 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 45,0% | 95 | 0 | 0,0 | 0 | 0,0 | 29 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 39,7% | 87 | 0 | 0,0 | 0 | 0,0 | 18 | 0 |

Referenz J, 394 Referenzwörter:

| Stellen | Hauptlauf | WER | Auslassungen | davon in einem Stück | harte Obergrenze (Punkte) | davon in einem anderen Lauf richtig | Orakel (Punkte) | längste Folge ausgelassener Wörter | davon in einem Stück |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1: Sprache ohne Wörter ab 2 s | norm#1 | 43,4% | 92 | 36 | 9,1 | 25 | 6,3 | 38 | 20 |
| S1: Sprache ohne Wörter ab 2 s | norm#2 | 32,2% | 41 | 0 | 0,0 | 0 | 0,0 | 4 | 0 |
| S1: Sprache ohne Wörter ab 2 s | norm#3 | 32,2% | 56 | 16 | 4,1 | 8 | 2,0 | 16 | 16 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#1 | 43,4% | 92 | 59 | 15,0 | 45 | 11,4 | 38 | 38 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#2 | 32,2% | 41 | 8 | 2,0 | 5 | 1,3 | 4 | 0 |
| S2: dazu Passagen mit schlechten Dekodierwerten | norm#3 | 32,2% | 56 | 24 | 6,1 | 13 | 3,3 | 16 | 16 |

- **J ist der Fall, für den der Weg gedacht ist:** Seed 1 verliert 38 Wörter am Stück, alle liegen in einem S2-Stück, und ein anderer Lauf hat 45 der 59 Auslassungen in den Stücken richtig. Für diesen einen Lauf wären bis zu 15,0 Punkte möglich.
- **An G greifen die Signale am falschen Lauf.** Seed 2 hat mit 95 Auslassungen und 29 am Stück den größten Verlust, aber keine davon liegt an einer auffälligen Stelle. Die 43 Auslassungen in einem Stück gehören zu Seed 1, dessen längste Folge 14 Wörter hat.
- **„Sprache ohne Wörter“ sieht die Blöcke nur teilweise:** an J 20 der 38 Wörter, an G keines.

## Regel A mit `norm` als Hauptlauf

`blocks.py --main norm --rules`, Blöcke ab 20 Wörtern, Regel A wie in [TOOL-108](TOOL-108-blockverlust.md#regeln). Je Zelle richtige/falsche Wörter der angenommenen Blöcke, summiert über die drei Hauptläufe, dann der Gewinn im Mittel der Hauptläufe und in Klammern der kleinste Gewinn eines Hauptlaufs. „–“ heißt: kein angenommener Block reicht in die Referenz.

| Quelle | A | B | C | D | E | F | G | H | I | J | K |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `norm`, die anderen zwei Seeds | – | – | – | – | – | – | – | – | – | – | 0/3 · −0,2 (−0,7) |
| `loud+batched` | – | – | – | – | – | – | – | – | – | 30/4 · 2,5 (0,0) | 1/0 · 0,1 (0,0) |
| `loud+batched+clips+pack` | – | – | – | – | – | – | – | – | – | 30/4 · 2,5 (0,0) | 1/0 · 0,1 (0,0) |

Über das Segment nimmt Regel A an (Blöcke / Wörter / Zeit in min, je Hauptlauf Seed 1 / 2 / 3):

| Quelle | Pilotsitzung | zweite Sitzung |
| --- | --- | --- |
| `norm`, die anderen zwei Seeds | 3 / 75 / 0,3 · 5 / 260 / 2,0 · 10 / 420 / 3,1 | 5 / 181 / 1,7 · 4 / 143 / 1,2 · 9 / 409 / 3,8 |
| `loud+batched` | 5 / 163 / 2,0 · 6 / 274 / 2,3 · 10 / 405 / 3,4 | 9 / 360 / 3,3 · 5 / 204 / 1,4 · 12 / 500 / 4,9 |
| `loud+batched+clips+pack` | 5 / 176 / 1,3 · 7 / 310 / 2,3 · 10 / 329 / 2,6 | 7 / 261 / 2,0 · 8 / 323 / 2,7 · 10 / 388 / 3,8 |

- **Regel A gewinnt nur an J.** Ein Batched-Lauf gibt Seed 1 dort einen Block mit 30 richtigen und 4 falschen Wörtern zurück, seine WER sinkt von 43,4 % auf 35,8 % (7,6 Punkte). Im Mittel der Hauptläufe sind das 2,5 Punkte.
- **Unter den `norm`-Seeds reicht nur ein Block in eine Referenz**, an K mit 3 falschen Wörtern (0,7 Punkte Verlust für einen Hauptlauf). Das ist dieselbe Zahl wie für `loud` in TOOL-108.
- **Die Go-Regel aus TOOL-108** (3 Punkte an zwei Referenzen) erreicht Regel A mit `norm` als Hauptlauf in keiner Paarung. Das bestätigt den Stand aus TOOL-108 und TOOL-109 für TOOL-114.
- **Über das Segment** nimmt die Regel 3 bis 12 Blöcke je Hauptlauf an, mit 75 bis 500 Wörtern. Ob sie richtig sind, ist außerhalb der Referenzen nicht gemessen.

## Stand gegen das Stufentor

| Maßstab | Referenzen ab 3 Punkten | Stand |
| --- | --- | --- |
| Harte Obergrenze, S2, Mittel der Hauptläufe | J (7,7); G bleibt bei 2,6 | eine Referenz statt zwei: Punkt 1 der Go-Regel ist unerreichbar |
| Orakel, S2, Mittel der Hauptläufe | J (5,3) | eine Referenz statt zwei |
| Regel A, beste Quelle, zum Vergleich | keine (J 2,5) | – |

Nach dem ersten Punkt des Stufentors heißt das: **No-Go ohne Stufe 2.**

- **Was dagegen spräche:** G liegt mit 2,6 Punkten knapp unter der Schwelle, und für den einzelnen Hauptlauf mit Blockverlust wären an J bis zu 15,0 Punkte möglich, doppelt so viel wie Regel A dort bringt (7,6).
- **Was dafür spricht:** Die harte Obergrenze ist großzügig gerechnet, kein falsches Wort zählt mit. Das Orakel aus fünf anderen Läufen erreicht an G 1,2 Punkte. Der größte Blockverlust an G wird von keinem der Signale gefunden.

## Einschränkungen

- **Die Obergrenze gilt für diese Signale.** Eine andere Regel für auffällige Stellen (etwa ein Vergleich mit einem zweiten Lauf) fände andere Stellen; das ist der Weg von TOOL-114.
- **Wortzeiten ausgelassener Wörter sind geschätzt.** Fehlt ein Wort in allen geladenen Läufen, liegt seine Zeit gleichmäßig zwischen den Nachbarn. Mit sechs Läufen je Sitzung betrifft das wenige Wörter, kann aber ein Wort an einer Stückgrenze auf die falsche Seite legen.
- **Polster von 2 s** ist eine Festlegung vor der Messung. Ein größeres Polster hebt die Obergrenze, weil mehr unauffälliges Audio dazukommt.
- **G und J sind die einzigen Fenster mit Blockverlust von `norm`**, und J ist nach der Abweichung der `base`-Seeds ausgesucht (TOOL-108). Wie häufig solche Stellen über eine ganze Sitzung sind, zeigen elf Fenster von je drei Minuten nicht.
- **Die Seeds 2 und 3 von `norm` sind ohne Diarisierung transkribiert.** „Sprache ohne Wörter“ nutzt für alle Läufe die Diarisierung der Sitzung auf dem Roh-WAV.
