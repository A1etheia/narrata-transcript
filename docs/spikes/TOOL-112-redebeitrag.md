# TOOL-112 — Dekodierung je Redebeitrag über `clip_timestamps`: Messung an A bis K

Stand 2026-11-27, abgeschlossen: No-Go, `norm` bleibt Hauptlauf ([Entscheidung](#entscheidung)). Bericht zu [TOOL-112](../plans/TOOL-112-clip-timestamps.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py), [`scripts/spike/clips.py`](../../scripts/spike/clips.py) und [`scripts/spike/omissions.py`](../../scripts/spike/omissions.py). Neu transkribiert wurden 28 Läufe, alles lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

**Nach der vorab festgelegten Regel erfüllt keine der fünf Varianten auf `loudnorm`-Audio einen der vier Punkte vollständig. Die Dekodierung je Redebeitrag lässt an A bis K nicht weniger aus als `norm`.**

- **Auslassungen:** 607 bis 722 gegen 584,3 bei `norm`. Nur die gepackte Variante liegt unter `loud+batched` (628) ([Auslassungen](#auslassungen)).
- **Einwürfe mit 1–3 Wörtern:** 34,9 bis 46,9 % gegen 34,3 % bei `norm`. Auf Rohaudio ist ein Stück je Turn besser als `base` und `base+batched` ([Nach Klassen](#nach-klassen)).
- **Einziger klarer Gewinn:** In Beiträgen unter 2 s laut Diarisierung fehlen mit einem Stück je Turn 10,8 bis 11,5 % der Wörter gegen 13,4 % ([Nach Klassen](#nach-klassen)).
- **Preis dafür:** rund doppelt so viele Einfügungen und eine WER von 39,5 bis 41,1 % gegen 30,2 % ([WER](#wer), [Einfügungen und Wiederholung](#einfügungen-und-wiederholung)).
- **Packen bis 30 s** kommt `norm` im Mittel am nächsten (30,7 %), verliert aber an H 77 Wörter am Stück und entgleist an G ([Längste Folge](#längste-folge-ausgelassener-wörter), [WER](#wer)).
- **Seeds und Laufzeit:** Die Seeds sind gleich; ein Lauf braucht 2,3 bis 11 min je Segment ([Seeds](#seeds), [Laufzeit und Speicher](#laufzeit-und-speicher)).
- **Als Zusatzlauf** hat ein Lauf je Redebeitrag höchstens 19 % der Auslassungen von `norm` richtig; ohne Auswahlregel verschlechtert er die WER an zehn von elf Referenzen ([Als Zusatzlauf zum Hauptlauf](#als-zusatzlauf-zum-hauptlauf)).
- **Die Regel je Variante** steht unter [Regeltabelle](#regeltabelle), die Grenzen des Wegs unter [Was der Weg nicht erreicht](#was-der-weg-nicht-erreicht).
- **Entscheidung vom 2026-11-27:** No-Go. `norm` bleibt Hauptlauf ([Entscheidung](#entscheidung)).

## Material und Methode

| | |
| --- | --- |
| Frage | Lässt die Batched-Pipeline weniger aus, wenn sie statt der Sprachabschnitte ihrer VAD die Turns der gespeicherten Diarisierung dekodiert (`clip_timestamps`, faster-whisper 1.2.1)? |
| Neue Läufe | fünf Varianten auf Rohaudio (`base+batched+…`) und auf `loudnorm`-Audio (`loud+batched+…`), beide Sitzungen, Seed 1; für `+clips+join` zusätzlich die Seeds 2 und 3 |
| Vergleichsläufe | `base`, `norm` (Seeds 1–3), `base+batched`, `loud+batched` (Seeds 1–3, Wort für Wort gleich) aus TOOL-93, TOOL-104 und TOOL-109 |
| Abschnitte | aus den exklusiven Turns der Diarisierung von Segment 1 der Sitzung, gerechnet auf dem Roh-WAV; `base` und `loud` dekodieren dieselben Abschnitte (gleicher Hash) |
| Modell | `large-v3-turbo`, dieselbe Revision und je Sitzung derselbe Wissens-Snapshot in allen Varianten |
| Referenzen | A bis K wie in [TOOL-108](TOOL-108-blockverlust.md#material-und-methode): A, B, D, E, F, G, I in der Pilotsitzung, C, H, J, K in der zweiten Sitzung. Summen laufen über A bis H, J und K; I steht wegen der gemeinsamen Minute mit F daneben |

Die fünf Varianten, vor der Messung festgelegt. Alle teilen Abschnitte über 30 s.

| Modifikatoren nach `+batched` | Abschnitte |
| --- | --- |
| `+clips` | ein Abschnitt je exklusivem Turn |
| `+clips+join` | Turns gleichen Labels mit höchstens 500 ms Abstand verbunden |
| `+clips+join+pad` | dazu 400 ms Polster je Seite, nur in freie Lücken |
| `+clips+join+pad+min` | dazu Mindestlänge 2 s: ein kürzerer Abschnitt geht im näheren Nachbarn auf, wenn die Lücke höchstens 1 s beträgt |
| `+clips+pack` | verbunden und gepolstert, dann über Labels hinweg bis 30 s gepackt (Lücke höchstens 2 s) |

- **WER** gegen die Handreferenz wie in `calibration.measure`; E/A/Ei sind Ersetzungen, Auslassungen, Einfügungen.
- **Klassen der Auslassungen** aus `omissions.py`. Die Wortzeit eines Referenzworts kommt aus dem Lauf selbst, die Zahl der Referenzwörter je Klasse unterscheidet sich deshalb zwischen den Varianten. Nur die Klasse „Beitrag mit 1–3 Wörtern“ hängt allein an der Handreferenz.
- **`norm` in den Klassentabellen** ist an `loud` gemessen: `omissions.py` findet das gefilterte WAV nur über die Kette von `loud`. Beide haben an jeder Referenz und in jedem Seed dieselben Zahlen für E/A/Ei (in dieser Messung nachgeprüft).
- **Mittel:** Bei `base` und `norm` das Mittel der drei Seeds. Die Batched-Läufe sind über die Seeds gleich.
- **Kontrolle:** `base` gibt weiter 21,3 % an A und 29,8 % an B, die Mittel der elf Referenzen stimmen mit [TOOL-109](TOOL-109-hauptlauf.md#entscheidungstabelle) überein (37,8 %, 30,2 %, 31,6 %, 32,7 %). Die Auslassungen aus `omissions.py` stimmen in jedem Lauf und an jeder Referenz mit `asr.py score` überein.

### Go-Regel

Vor der Messung festgelegt, im Wortlaut des Plans. Eine Variante auf `loudnorm`-Audio bekommt ein Umsetzungsticket, wenn alle vier Punkte gelten:

1. Die Summe der Auslassungen über A bis H, J und K liegt unter der von `norm` (Mittel der drei Seeds) und unter der von `loud+batched`.
2. Die Auslassungsrate in Beiträgen mit 1–3 Wörtern (Handreferenz) liegt über dieselben Referenzen unter der von `norm`.
3. An keiner Referenz A bis K liegt die WER über dem schlechtesten einzelnen Lauf von `norm` an dieser Referenz, und an keiner fehlen 30 oder mehr Wörter am Stück.
4. Die Summe der Einfügungen und der Wiederholungsanteil über das Segment liegen nicht über `norm`.

Die Varianten auf Rohaudio sind Gegenprobe gegen `base` und `base+batched` und bekommen kein eigenes Go.

## Abschnitte

| Abschnitte | Pilotsitzung: Zahl | Pilotsitzung: Median (s) | Pilotsitzung: unter 2 s | Pilotsitzung: längster (s) | Pilotsitzung: Summe (min) | zweite Sitzung: Zahl | zweite Sitzung: Median (s) | zweite Sitzung: unter 2 s | zweite Sitzung: längster (s) | zweite Sitzung: Summe (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `+clips` | 4993 | 1,2 | 64,5 % | 29,9 | 204,1 | 4534 | 1,2 | 64,4 % | 29,9 | 192,3 |
| `+clips+join` | 4550 | 1,3 | 61,1 % | 29,9 | 205,8 | 4135 | 1,3 | 61,2 % | 29,9 | 194,0 |
| `+clips+join+pad` | 4552 | 1,9 | 51,0 % | 29,3 | 240,0 | 4136 | 1,9 | 51,1 % | 29,9 | 225,6 |
| `+clips+join+pad+min` | 2584 | 4,3 | 5,9 % | 29,9 | 241,7 | 2334 | 4,3 | 5,4 % | 29,9 | 227,5 |
| `+clips+pack` | 917 | 18,4 | 4,9 % | 29,9 | 259,9 | 902 | 16,3 | 4,7 % | 30,0 | 243,9 |

Zum Vergleich die Zeit, die jede Variante dekodiert, und die Zeit, in der die Diarisierung Sprache hört und der Lauf kein Wort hat (Pausen zwischen Wörtern bis 1 s gelten als gedeckt). Bei `base` und `norm` ist „behalten“ die VAD der Pipeline, bei `+batched` die der Batched-Pipeline, bei `+clips` die Summe der Abschnitte.

| Variante | Pilotsitzung: behalten | Pilotsitzung: Sprache ohne Wörter | Pilotsitzung: Stellen ab 2 s | Pilotsitzung: Zeit darin (min) | zweite Sitzung: behalten | zweite Sitzung: Sprache ohne Wörter | zweite Sitzung: Stellen ab 2 s | zweite Sitzung: Zeit darin (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | 241,3 min von 300,0 min | 4,0% / 4,0% / 4,0% | 61 / 59 / 62 | 3,9 / 3,7 / 3,8 | 222,6 min von 286,9 min | 6,5% / 6,5% / 6,3% | 103 / 114 / 114 | 7,5 / 7,4 / 6,7 |
| `base+batched` | 225,6 min von 300,0 min | 4,7% | 67 | 5,1 | 207,0 min von 286,9 min | 4,8% | 62 | 4,1 |
| `base+batched+clips` | 204,1 min von 300,0 min | 2,9% | 34 | 1,5 | 192,3 min von 286,9 min | 4,2% | 56 | 3,5 |
| `base+batched+clips+join` | 205,8 min von 300,0 min | 2,8% | 33 | 1,5 | 194,0 min von 286,9 min | 4,2% | 56 | 3,4 |
| `base+batched+clips+join+pad` | 240,0 min von 300,0 min | 3,0% | 31 | 1,8 | 225,6 min von 286,9 min | 4,0% | 52 | 3,1 |
| `base+batched+clips+join+pad+min` | 241,7 min von 300,0 min | 3,6% | 52 | 2,5 | 227,5 min von 286,9 min | 4,4% | 60 | 3,4 |
| `base+batched+clips+pack` | 259,9 min von 300,0 min | 3,1% | 43 | 2,8 | 243,9 min von 286,9 min | 4,1% | 61 | 4,4 |
| `norm` | 243,7 min von 300,0 min | 2,4% / 2,5% / 3,0% | 32 / 33 / 38 | 1,6 / 1,9 / 2,5 | 224,4 min von 286,9 min | 3,9% / 3,5% / 4,5% | 52 / 44 / 61 | 3,0 / 2,7 / 3,9 |
| `loud+batched` | 227,4 min von 300,0 min | 4,4% | 67 | 5,0 | 208,5 min von 286,9 min | 4,2% | 40 | 3,5 |
| `loud+batched+clips` | 204,1 min von 300,0 min | 2,7% | 27 | 1,6 | 192,3 min von 286,9 min | 3,9% | 51 | 3,4 |
| `loud+batched+clips+join` | 205,8 min von 300,0 min | 2,6% | 26 | 1,5 | 194,0 min von 286,9 min | 3,9% | 51 | 3,4 |
| `loud+batched+clips+join+pad` | 240,0 min von 300,0 min | 2,6% | 26 | 1,4 | 225,6 min von 286,9 min | 3,9% | 57 | 3,4 |
| `loud+batched+clips+join+pad+min` | 241,7 min von 300,0 min | 3,4% | 42 | 2,5 | 227,5 min von 286,9 min | 4,1% | 62 | 3,6 |
| `loud+batched+clips+pack` | 259,9 min von 300,0 min | 3,2% | 42 | 3,6 | 243,9 min von 286,9 min | 3,6% | 51 | 3,7 |

- **Ein Stück je Turn ist kurz:** Median 1,2 s, knapp zwei Drittel der Abschnitte unter 2 s. Erst die Mindestlänge senkt den Anteil auf 5 bis 6 %.
- **Abdeckung:** Ohne Polster dekodieren `+clips` und `+clips+join` rund 20 min weniger als die Batched-VAD und rund 37 min (Pilotsitzung) bzw. 30 min (zweite Sitzung) weniger als die VAD der Pipeline. Mit Polster liegen sie auf dem Stand der Pipeline-VAD, gepackt 18 bis 21 min darüber.

## WER

| Variante | A | B | C | D | E | F | G | H | I | J | K | Mittel A–K |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 21,3 % | 29,8 % | 30,8 % | 61,2 % | 34,0 % | 28,4 % | 36,0 % | 36,5 % | 27,2 % | 74,8 % | 35,5 % | 37,8 % |
| `base+batched` (Mittel) | 19,6 % | 25,4 % | 25,9 % | 36,3 % | 29,0 % | 26,4 % | 39,6 % | 53,6 % | 33,2 % | 37,6 % | 21,5 % | 31,6 % |
| `base+batched+clips` | 25,0 % | 33,6 % | 36,3 % | 46,5 % | 46,6 % | 42,8 % | 55,7 % | 53,8 % | 35,7 % | 35,8 % | 30,0 % | 40,2 % |
| `base+batched+clips+join` | 24,9 % | 32,9 % | 34,7 % | 46,5 % | 46,3 % | 42,3 % | 52,8 % | 54,3 % | 36,9 % | 35,5 % | 28,1 % | 39,6 % |
| `base+batched+clips+join+pad` | 23,5 % | 32,4 % | 35,6 % | 49,9 % | 45,3 % | 40,4 % | 51,7 % | 53,8 % | 35,2 % | 34,0 % | 28,8 % | 39,1 % |
| `base+batched+clips+join+pad+min` | 22,6 % | 32,2 % | 25,4 % | 41,9 % | 38,2 % | 31,3 % | 39,0 % | 44,9 % | 29,8 % | 30,2 % | 26,5 % | 32,9 % |
| `base+batched+clips+pack` | 20,7 % | 25,6 % | 26,1 % | 38,1 % | 27,6 % | 28,9 % | 41,9 % | 41,3 % | 29,5 % | 29,7 % | 25,4 % | 30,4 % |
| `norm` (Mittel) | 20,2 % | 26,5 % | 23,9 % | 36,7 % | 29,6 % | 27,5 % | 42,3 % | 32,8 % | 30,3 % | 36,0 % | 26,5 % | 30,2 % |
| `loud+batched` (Mittel) | 18,8 % | 28,1 % | 23,7 % | 38,3 % | 67,5 % | 26,7 % | 35,6 % | 37,2 % | 31,7 % | 30,2 % | 22,0 % | 32,7 % |
| `loud+batched+clips` | 25,6 % | 33,1 % | 38,6 % | 44,3 % | 47,4 % | 42,8 % | 57,7 % | 65,3 % | 34,8 % | 34,8 % | 27,7 % | 41,1 % |
| `loud+batched+clips+join` | 23,9 % | 33,6 % | 36,6 % | 43,7 % | 46,6 % | 41,3 % | 56,1 % | 65,3 % | 36,0 % | 34,5 % | 25,6 % | 40,3 % |
| `loud+batched+clips+join+pad` | 24,9 % | 32,2 % | 35,6 % | 46,8 % | 44,2 % | 39,7 % | 54,6 % | 58,3 % | 36,7 % | 35,3 % | 26,3 % | 39,5 % |
| `loud+batched+clips+join+pad+min` | 23,2 % | 31,7 % | 25,5 % | 42,3 % | 37,9 % | 33,4 % | 43,0 % | 41,3 % | 32,7 % | 31,5 % | 25,4 % | 33,4 % |
| `loud+batched+clips+pack` | 19,8 % | 25,2 % | 24,9 % | 36,1 % | 27,9 % | 27,1 % | 54,8 % | 39,8 % | 29,3 % | 28,9 % | 23,6 % | 30,7 % |
| `norm`, schlechtester Lauf | 20,2 % | 26,5 % | 24,8 % | 38,1 % | 29,8 % | 27,9 % | 45,0 % | 33,2 % | 30,3 % | 43,4 % | 29,5 % | – |

Je Lauf (E/A/Ei):

| Variante | A | B | C | D | E | F | G | H | I | J | K |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` #1 | 65/31/17 | 61/44/8 | 111/80/57 | 77/133/12 | 62/43/5 | 74/74/12 | 108/72/36 | 73/86/16 | 78/70/12 | 49/210/22 | 52/96/6 |
| `base` #2 | 64/31/18 | 67/42/16 | 110/156/24 | 98/115/23 | 62/46/8 | 75/71/10 | 104/70/21 | 73/86/16 | 79/66/14 | 96/118/136 | 70/83/5 |
| `base` #3 | 61/36/16 | 81/45/30 | 93/177/33 | 86/166/114 | 63/78/9 | 72/99/10 | 115/48/21 | 72/73/19 | 69/82/18 | 83/121/49 | 55/83/16 |
| `base+batched` #1 | 60/29/15 | 70/38/4 | 91/110/34 | 87/65/11 | 61/40/6 | 63/81/10 | 104/74/40 | 60/149/43 | 61/124/13 | 45/88/15 | 54/31/9 |
| `base+batched` #2 | 60/29/15 | 70/38/4 | 91/110/34 | 87/65/11 | 61/40/6 | 63/81/10 | 104/74/40 | 60/149/43 | 61/124/13 | 45/88/15 | 54/31/9 |
| `base+batched` #3 | 60/29/15 | 70/38/4 | 91/110/34 | 87/65/11 | 61/40/6 | 63/81/10 | 104/74/40 | 60/149/43 | 61/124/13 | 45/88/15 | 54/31/9 |
| `base+batched+clips` | 66/43/24 | 95/36/17 | 163/107/60 | 86/100/23 | 98/57/17 | 102/98/50 | 132/114/61 | 115/97/41 | 92/84/37 | 79/42/20 | 67/35/29 |
| `base+batched+clips+join` | 67/43/22 | 84/43/18 | 158/103/54 | 84/102/23 | 96/56/19 | 95/106/46 | 135/106/50 | 113/106/36 | 89/94/37 | 78/43/19 | 62/35/26 |
| `base+batched+clips+join+pad` | 63/40/22 | 81/44/18 | 151/104/69 | 83/107/34 | 93/54/20 | 93/100/43 | 132/106/47 | 111/107/35 | 87/87/36 | 75/41/18 | 69/28/29 |
| `base+batched+clips+join+pad+min` | 54/45/21 | 79/47/16 | 118/80/33 | 91/87/10 | 73/60/8 | 62/109/12 | 120/86/9 | 72/114/25 | 70/97/11 | 59/46/14 | 54/40/22 |
| `base+batched+clips+pack` | 59/38/13 | 71/37/5 | 111/99/27 | 80/83/8 | 59/38/5 | 63/96/10 | 109/70/52 | 42/147/5 | 63/90/23 | 61/43/13 | 52/46/13 |
| `norm` #1 | 61/29/17 | 69/42/6 | 107/88/22 | 93/59/10 | 67/30/12 | 71/80/12 | 117/73/42 | 71/66/15 | 74/60/47 | 62/92/17 | 64/41/24 |
| `norm` #2 | 61/29/17 | 69/42/6 | 112/92/21 | 87/64/20 | 68/30/12 | 70/80/12 | 104/95/49 | 73/68/15 | 74/60/47 | 68/41/18 | 49/34/10 |
| `norm` #3 | 61/29/17 | 69/42/6 | 105/88/18 | 85/64/13 | 67/30/12 | 68/76/12 | 103/87/29 | 72/67/15 | 74/60/47 | 54/56/17 | 64/39/23 |
| `loud+batched` #1 | 57/27/16 | 80/39/5 | 92/97/26 | 84/77/11 | 57/96/96 | 63/75/18 | 113/59/24 | 76/70/29 | 59/117/13 | 51/59/9 | 55/29/12 |
| `loud+batched` #2 | 57/27/16 | 80/39/5 | 92/97/26 | 84/77/11 | 57/96/96 | 63/75/18 | 113/59/24 | 76/70/29 | 59/117/13 | 51/59/9 | 55/29/12 |
| `loud+batched` #3 | 57/27/16 | 80/39/5 | 92/97/26 | 84/77/11 | 57/96/96 | 63/75/18 | 113/59/24 | 76/70/29 | 59/117/13 | 51/59/9 | 55/29/12 |
| `loud+batched+clips` | 67/41/28 | 88/42/16 | 181/99/71 | 92/85/22 | 98/54/23 | 108/98/44 | 133/116/69 | 112/103/92 | 97/77/34 | 77/42/18 | 66/36/19 |
| `loud+batched+clips+join` | 66/40/21 | 85/46/17 | 173/97/63 | 91/85/20 | 95/53/24 | 104/97/40 | 131/112/66 | 108/113/86 | 91/89/35 | 74/43/19 | 61/36/15 |
| `loud+batched+clips+join+pad` | 65/44/23 | 79/47/16 | 172/88/64 | 83/96/31 | 86/51/26 | 97/94/41 | 138/107/56 | 117/95/62 | 92/90/37 | 79/43/17 | 70/28/17 |
| `loud+batched+clips+join+pad+min` | 57/43/23 | 78/47/15 | 120/81/31 | 88/81/21 | 74/56/10 | 67/113/15 | 122/94/21 | 72/110/12 | 82/100/13 | 62/49/13 | 58/37/16 |
| `loud+batched+clips+pack` | 57/30/18 | 72/35/4 | 104/96/26 | 85/65/12 | 59/39/5 | 78/67/13 | 116/81/105 | 56/125/6 | 76/83/16 | 62/40/12 | 61/29/13 |

- **Ein Stück je Turn** (`+clips`, `+clips+join`, `+clips+join+pad`) liegt im Mittel bei 39,1 bis 41,1 % und damit über jedem Vergleichslauf, auf beiden Audios.
- **Mindestlänge und Packen** bringen das Mittel auf 32,9 und 33,4 % (`+min`) bzw. 30,4 und 30,7 % (`+pack`); `norm` hat 30,2 %.
- **Schlechtester Fall:** `loud+batched+clips+pack` hat an G 54,8 % mit 105 Einfügungen, die drei Varianten mit einem Stück je Turn auf `loudnorm`-Audio haben an H 58,3 bis 65,3 %.

## Auslassungen

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 32,7 | 43,7 | 137,7 | 138 | 55,7 | 81,3 | 63,3 | 81,7 | 72,7 | 149,7 | 87,3 | 871,0 |
| `base+batched` (Mittel) | 29 | 38 | 110 | 65 | 40 | 81 | 74 | 149 | 124 | 88 | 31 | 705,0 |
| `base+batched+clips` | 43 | 36 | 107 | 100 | 57 | 98 | 114 | 97 | 84 | 42 | 35 | 729,0 |
| `base+batched+clips+join` | 43 | 43 | 103 | 102 | 56 | 106 | 106 | 106 | 94 | 43 | 35 | 743,0 |
| `base+batched+clips+join+pad` | 40 | 44 | 104 | 107 | 54 | 100 | 106 | 107 | 87 | 41 | 28 | 731,0 |
| `base+batched+clips+join+pad+min` | 45 | 47 | 80 | 87 | 60 | 109 | 86 | 114 | 97 | 46 | 40 | 714,0 |
| `base+batched+clips+pack` | 38 | 37 | 99 | 83 | 38 | 96 | 70 | 147 | 90 | 43 | 46 | 697,0 |
| `norm` (Mittel) | 29 | 42 | 89,3 | 62,3 | 30 | 78,7 | 85 | 67 | 60 | 63 | 38 | 584,3 |
| `loud+batched` (Mittel) | 27 | 39 | 97 | 77 | 96 | 75 | 59 | 70 | 117 | 59 | 29 | 628,0 |
| `loud+batched+clips` | 41 | 42 | 99 | 85 | 54 | 98 | 116 | 103 | 77 | 42 | 36 | 716,0 |
| `loud+batched+clips+join` | 40 | 46 | 97 | 85 | 53 | 97 | 112 | 113 | 89 | 43 | 36 | 722,0 |
| `loud+batched+clips+join+pad` | 44 | 47 | 88 | 96 | 51 | 94 | 107 | 95 | 90 | 43 | 28 | 693,0 |
| `loud+batched+clips+join+pad+min` | 43 | 47 | 81 | 81 | 56 | 113 | 94 | 110 | 100 | 49 | 37 | 711,0 |
| `loud+batched+clips+pack` | 30 | 35 | 96 | 65 | 39 | 67 | 81 | 125 | 83 | 40 | 29 | 607,0 |

- **Summe über A bis H, J und K:** `norm` 584,3, `loud+batched` 628. Keine Variante liegt unter `norm`; am nächsten kommt `loud+batched+clips+pack` mit 607, die übrigen auf `loudnorm`-Audio haben 693 bis 722.
- **Rohaudio:** 697 bis 743 gegen 705 bei `base+batched` und 871,0 bei `base`.
- **Verteilung:** An J und K lassen alle neuen Varianten weniger oder ähnlich viel aus wie `norm`, an D, F und G (außer gepackt) und H deutlich mehr.

### Längste Folge ausgelassener Wörter

| Variante | A | B | C | D | E | F | G | H | I | J | K | größte |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | 4 / 4 / 9 | 5 / 5 / 6 | 11 / 54 / 54 | 38 / 57 / 45 | 5 / 5 / 40 | 12 / 12 / 20 | 15 / 7 / 5 | 15 / 15 / 15 | 9 / 9 / 10 | 66 / 62 / 46 | 27 / 44 / 45 | 66 |
| `base+batched` | 2 | 5 | 12 | 9 | 3 | 12 | 16 | 94 | 48 | 19 | 4 | 94 |
| `base+batched+clips` | 13 | 6 | 34 | 15 | 6 | 12 | 15 | 25 | 9 | 5 | 8 | 34 |
| `base+batched+clips+join` | 13 | 6 | 34 | 15 | 6 | 12 | 15 | 25 | 9 | 5 | 8 | 34 |
| `base+batched+clips+join+pad` | 13 | 5 | 34 | 15 | 6 | 12 | 15 | 25 | 9 | 5 | 4 | 34 |
| `base+batched+clips+join+pad+min` | 13 | 5 | 8 | 15 | 8 | 20 | 15 | 15 | 9 | 6 | 8 | 20 |
| `base+batched+clips+pack` | 10 | 5 | 12 | 17 | 3 | 20 | 16 | 77 | 12 | 5 | 8 | 77 |
| `norm` | 2 / 2 / 2 | 5 / 5 / 5 | 8 / 8 / 8 | 9 / 9 / 9 | 3 / 3 / 3 | 12 / 12 / 12 | 14 / 29 / 18 | 15 / 15 / 15 | 9 / 9 / 9 | 38 / 4 / 16 | 6 / 6 / 6 | 38 |
| `loud+batched` | 2 | 5 | 12 | 17 | 49 | 12 | 5 | 12 | 48 | 16 | 6 | 49 |
| `loud+batched+clips` | 13 | 6 | 21 | 17 | 9 | 12 | 16 | 33 | 9 | 5 | 5 | 33 |
| `loud+batched+clips+join` | 13 | 6 | 21 | 17 | 9 | 12 | 16 | 33 | 9 | 5 | 5 | 33 |
| `loud+batched+clips+join+pad` | 13 | 6 | 21 | 17 | 6 | 12 | 16 | 14 | 9 | 5 | 4 | 21 |
| `loud+batched+clips+join+pad+min` | 13 | 5 | 12 | 17 | 8 | 29 | 16 | 15 | 10 | 6 | 6 | 29 |
| `loud+batched+clips+pack` | 4 | 5 | 12 | 9 | 3 | 12 | 16 | 77 | 14 | 5 | 6 | 77 |

Gepackt verlieren beide Audios an H 77 Wörter am Stück, `base+batched` verliert dort 94. Ein Stück je Turn bleibt bei höchstens 34 (C) bzw. 33 (H). Über das Segment zeigt der Vergleich mit `base#1` in Abschnitten von 5 min ein einziges Defizit:

Vergleich: base#1, Abschnitte à 5 min, Defizit ab 20% und 30 Wörtern weniger

| Lauf | Wörter | ohne Zeit | Abschnitte | mit Defizit | fehlende Wörter darin | größtes Defizit |
| --- | --- | --- | --- | --- | --- | --- |
| base#1 | 29006 | 0 | 58 | 0 | 0 | – |
| base+batched#1 | 29481 | 0 | 58 | 0 | 0 | – |
| norm#1 | 29877 | 0 | 58 | 0 | 0 | – |
| loud+batched#1 | 30010 | 0 | 58 | 0 | 0 | – |
| base+batched+clips#1 | 30799 | 0 | 58 | 0 | 0 | – |
| base+batched+clips+join#1 | 30611 | 0 | 58 | 0 | 0 | – |
| base+batched+clips+join+pad#1 | 30739 | 0 | 58 | 0 | 0 | – |
| base+batched+clips+join+pad+min#1 | 29638 | 0 | 58 | 0 | 0 | – |
| base+batched+clips+pack#1 | 30000 | 0 | 58 | 1 | 131 | 20,0% |
| loud+batched+clips#1 | 31162 | 0 | 58 | 0 | 0 | – |
| loud+batched+clips+join#1 | 30973 | 0 | 58 | 0 | 0 | – |
| loud+batched+clips+join+pad#1 | 31173 | 0 | 58 | 0 | 0 | – |
| loud+batched+clips+join+pad+min#1 | 30009 | 0 | 58 | 0 | 0 | – |
| loud+batched+clips+pack#1 | 30386 | 0 | 58 | 0 | 0 | – |

| Lauf | Abschnitt | Wörter | base#1 |
| --- | --- | --- | --- |
| base+batched+clips+pack#1 | 00:45:00–00:50:00 | 523 | 654 |

In der Pilotsitzung hat kein Lauf einen Abschnitt mit Defizit (61 Abschnitte je Lauf).

### Nach Klassen

Je Zelle Auslassungen von Referenzwörtern der Klasse. Die Rate steht über A bis H, J und K.

**Beitrag mit 1–3 Wörtern (Handreferenz):**

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I | Rate ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 7 von 16 | 0 von 1 | 10 von 23 | 17,7 von 38 | 2,3 von 13 | 5 von 13 | 4,3 von 5 | 7,7 von 43 | 1 von 10 | 11 von 16 | 6 von 7 | 71,0 von 175,0 | 40,6 % |
| `base+batched` (Mittel) | 5 von 16 | 0 von 1 | 11 von 23 | 25 von 38 | 4 von 13 | 5 von 13 | 3 von 5 | 13 von 43 | 5 von 10 | 8 von 16 | 6 von 7 | 80,0 von 175,0 | 45,7 % |
| `base+batched+clips` | 4 von 16 | 0 von 1 | 7 von 23 | 21 von 38 | 2 von 13 | 4 von 13 | 2 von 5 | 20 von 43 | 1 von 10 | 5 von 16 | 1 von 7 | 66,0 von 175,0 | 37,7 % |
| `base+batched+clips+join` | 4 von 16 | 0 von 1 | 7 von 23 | 21 von 38 | 2 von 13 | 4 von 13 | 2 von 5 | 21 von 43 | 1 von 10 | 6 von 16 | 1 von 7 | 68,0 von 175,0 | 38,9 % |
| `base+batched+clips+join+pad` | 5 von 16 | 0 von 1 | 6 von 23 | 21 von 38 | 1 von 13 | 3 von 13 | 2 von 5 | 20 von 43 | 1 von 10 | 5 von 16 | 1 von 7 | 64,0 von 175,0 | 36,6 % |
| `base+batched+clips+join+pad+min` | 5 von 16 | 0 von 1 | 8 von 23 | 22 von 38 | 2 von 13 | 4 von 13 | 2 von 5 | 21 von 43 | 1 von 10 | 8 von 16 | 5 von 7 | 77,0 von 175,0 | 44,0 % |
| `base+batched+clips+pack` | 6 von 16 | 0 von 1 | 8 von 23 | 21 von 38 | 1 von 13 | 5 von 13 | 1 von 5 | 17 von 43 | 1 von 10 | 10 von 16 | 5 von 7 | 74,0 von 175,0 | 42,3 % |
| `norm` (Mittel) | 5 von 16 | 0 von 1 | 6 von 23 | 18 von 38 | 2 von 13 | 4 von 13 | 3 von 5 | 8,7 von 43 | 0 von 10 | 8,7 von 16 | 4,7 von 7 | 60,0 von 175,0 | 34,3 % |
| `loud+batched` (Mittel) | 5 von 16 | 0 von 1 | 9 von 23 | 18 von 38 | 3 von 13 | 5 von 13 | 4 von 5 | 9 von 43 | 4 von 10 | 9 von 16 | 4 von 7 | 66,0 von 175,0 | 37,7 % |
| `loud+batched+clips` | 4 von 16 | 0 von 1 | 7 von 23 | 21 von 38 | 1 von 13 | 5 von 13 | 3 von 5 | 15 von 43 | 1 von 10 | 4 von 16 | 1 von 7 | 61,0 von 175,0 | 34,9 % |
| `loud+batched+clips+join` | 4 von 16 | 0 von 1 | 8 von 23 | 21 von 38 | 1 von 13 | 5 von 13 | 2 von 5 | 19 von 43 | 1 von 10 | 5 von 16 | 1 von 7 | 66,0 von 175,0 | 37,7 % |
| `loud+batched+clips+join+pad` | 5 von 16 | 0 von 1 | 7 von 23 | 20 von 38 | 1 von 13 | 4 von 13 | 2 von 5 | 18 von 43 | 1 von 10 | 5 von 16 | 1 von 7 | 63,0 von 175,0 | 36,0 % |
| `loud+batched+clips+join+pad+min` | 5 von 16 | 0 von 1 | 8 von 23 | 25 von 38 | 1 von 13 | 4 von 13 | 3 von 5 | 23 von 43 | 1 von 10 | 8 von 16 | 5 von 7 | 82,0 von 175,0 | 46,9 % |
| `loud+batched+clips+pack` | 5 von 16 | 0 von 1 | 8 von 23 | 19 von 38 | 4 von 13 | 10 von 13 | 1 von 5 | 13 von 43 | 1 von 10 | 8 von 16 | 5 von 7 | 73,0 von 175,0 | 41,7 % |

**Beitrag unter 2 s (Diarisierung):**

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I | Rate ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 6 von 31 | 6,7 von 45 | 33,3 von 133 | 12,7 von 38 | 14 von 88 | 16 von 107 | 1,7 von 75 | 9,3 von 93 | 6 von 53 | 18 von 45 | 16 von 48 | 133,7 von 703,0 | 19,0 % |
| `base+batched` (Mittel) | 2 von 30 | 7 von 46 | 18 von 121 | 15 von 45 | 9 von 90 | 17 von 112 | 9 von 87 | 29 von 105 | 21 von 66 | 2 von 53 | 11 von 48 | 119,0 von 737,0 | 16,1 % |
| `base+batched+clips` | 4 von 28 | 10 von 54 | 13 von 153 | 3 von 36 | 13 von 93 | 11 von 117 | 17 von 93 | 4 von 108 | 5 von 62 | 5 von 60 | 7 von 50 | 87,0 von 792,0 | 11,0 % |
| `base+batched+clips+join` | 1 von 29 | 10 von 54 | 14 von 155 | 3 von 36 | 13 von 93 | 12 von 117 | 17 von 94 | 4 von 109 | 6 von 62 | 5 von 60 | 7 von 50 | 86,0 von 797,0 | 10,8 % |
| `base+batched+clips+join+pad` | 2 von 28 | 12 von 47 | 16 von 141 | 4 von 32 | 14 von 82 | 10 von 109 | 18 von 93 | 4 von 99 | 4 von 52 | 5 von 53 | 4 von 42 | 89,0 von 726,0 | 12,3 % |
| `base+batched+clips+join+pad+min` | 2 von 29 | 12 von 48 | 12 von 126 | 5 von 42 | 13 von 80 | 23 von 112 | 5 von 75 | 23 von 97 | 7 von 51 | 6 von 52 | 11 von 46 | 112,0 von 707,0 | 15,8 % |
| `base+batched+clips+pack` | 3 von 26 | 7 von 45 | 21 von 120 | 2 von 34 | 8 von 85 | 28 von 116 | 3 von 68 | 30 von 94 | 2 von 47 | 4 von 47 | 16 von 47 | 122,0 von 682,0 | 17,9 % |
| `norm` (Mittel) | 3 von 30 | 7 von 46 | 21,7 von 135 | 5,3 von 34 | 9 von 93 | 16,7 von 118 | 7,7 von 68 | 14,7 von 100 | 7 von 53 | 1 von 50 | 10,7 von 47 | 96,7 von 721,0 | 13,4 % |
| `loud+batched` (Mittel) | 3 von 31 | 7 von 47 | 18 von 131 | 6 von 40 | 59 von 108 | 17 von 117 | 7 von 78 | 14 von 101 | 18 von 66 | 2 von 48 | 13 von 51 | 146,0 von 752,0 | 19,4 % |
| `loud+batched+clips` | 7 von 27 | 11 von 52 | 13 von 145 | 1 von 38 | 16 von 95 | 11 von 116 | 16 von 84 | 2 von 100 | 5 von 63 | 7 von 61 | 3 von 47 | 87,0 von 765,0 | 11,4 % |
| `loud+batched+clips+join` | 4 von 28 | 11 von 52 | 13 von 144 | 1 von 38 | 16 von 95 | 13 von 117 | 13 von 82 | 2 von 100 | 6 von 62 | 7 von 61 | 3 von 48 | 83,0 von 765,0 | 10,8 % |
| `loud+batched+clips+join+pad` | 4 von 27 | 12 von 44 | 14 von 130 | 2 von 35 | 14 von 84 | 7 von 107 | 14 von 87 | 3 von 101 | 6 von 53 | 5 von 53 | 7 von 47 | 82,0 von 715,0 | 11,5 % |
| `loud+batched+clips+join+pad+min` | 2 von 28 | 12 von 48 | 15 von 128 | 1 von 32 | 8 von 79 | 25 von 115 | 5 von 75 | 26 von 100 | 10 von 53 | 6 von 53 | 17 von 52 | 117,0 von 710,0 | 16,5 % |
| `loud+batched+clips+pack` | 2 von 30 | 6 von 47 | 19 von 118 | 2 von 34 | 12 von 86 | 8 von 110 | 8 von 74 | 18 von 85 | 7 von 50 | 4 von 47 | 14 von 47 | 93,0 von 678,0 | 13,7 % |

**Überlappung:**

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I | Rate ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 3,7 von 17 | 0 von 1 | 24 von 52 | 18,3 von 38 | 2 von 17 | 29,3 von 110 | 13,3 von 83 | 21,3 von 44 | 27,3 von 114 | 6 von 16 | 10,7 von 34 | 128,7 von 412,0 | 31,2 % |
| `base+batched` (Mittel) | 2 von 16 | 0 von 1 | 13 von 41 | 14 von 41 | 1 von 14 | 29 von 110 | 25 von 90 | 13 von 35 | 40 von 97 | 33 von 59 | 7 von 30 | 137,0 von 437,0 | 31,4 % |
| `base+batched+clips` | 2 von 16 | 0 von 1 | 10 von 41 | 8 von 25 | 3 von 15 | 41 von 99 | 33 von 76 | 6 von 39 | 18 von 102 | 3 von 27 | 9 von 28 | 115,0 von 367,0 | 31,3 % |
| `base+batched+clips+join` | 1 von 15 | 0 von 1 | 12 von 43 | 8 von 25 | 3 von 15 | 40 von 99 | 34 von 77 | 6 von 34 | 19 von 102 | 3 von 27 | 9 von 28 | 116,0 von 364,0 | 31,9 % |
| `base+batched+clips+join+pad` | 1 von 15 | 0 von 1 | 23 von 53 | 8 von 25 | 2 von 15 | 40 von 104 | 34 von 80 | 7 von 35 | 18 von 109 | 6 von 31 | 5 von 29 | 126,0 von 388,0 | 32,5 % |
| `base+batched+clips+join+pad+min` | 2 von 17 | 0 von 1 | 9 von 32 | 14 von 39 | 1 von 12 | 36 von 99 | 13 von 65 | 23 von 47 | 21 von 104 | 5 von 28 | 11 von 30 | 114,0 von 370,0 | 30,8 % |
| `base+batched+clips+pack` | 3 von 12 | 0 von 1 | 12 von 39 | 6 von 26 | 0 von 14 | 31 von 94 | 24 von 92 | 34 von 52 | 16 von 96 | 1 von 20 | 8 von 29 | 119,0 von 379,0 | 31,4 % |
| `norm` (Mittel) | 3 von 16 | 0 von 1 | 11 von 32 | 10 von 33 | 1 von 14 | 27,3 von 106 | 36 von 93 | 8 von 39 | 17 von 110 | 3,3 von 23 | 10 von 34 | 109,7 von 391,0 | 28,0 % |
| `loud+batched` (Mittel) | 2 von 16 | 0 von 1 | 12 von 37 | 13 von 44 | 0 von 14 | 34 von 119 | 7 von 78 | 3 von 37 | 37 von 96 | 3 von 25 | 8 von 34 | 82,0 von 405,0 | 20,2 % |
| `loud+batched+clips` | 6 von 16 | 0 von 1 | 10 von 36 | 11 von 36 | 9 von 23 | 41 von 100 | 19 von 61 | 11 von 43 | 17 von 105 | 8 von 30 | 8 von 33 | 123,0 von 379,0 | 32,5 % |
| `loud+batched+clips+join` | 3 von 14 | 0 von 1 | 12 von 38 | 11 von 36 | 9 von 23 | 34 von 98 | 25 von 68 | 11 von 40 | 17 von 105 | 9 von 30 | 8 von 33 | 122,0 von 381,0 | 32,0 % |
| `loud+batched+clips+join+pad` | 3 von 14 | 0 von 1 | 12 von 36 | 11 von 36 | 3 von 16 | 29 von 96 | 26 von 69 | 11 von 42 | 16 von 105 | 6 von 28 | 5 von 32 | 106,0 von 370,0 | 28,6 % |
| `loud+batched+clips+join+pad+min` | 2 von 18 | 0 von 1 | 12 von 34 | 14 von 43 | 0 von 11 | 34 von 94 | 20 von 67 | 20 von 45 | 21 von 106 | 5 von 26 | 11 von 36 | 118,0 von 375,0 | 31,5 % |
| `loud+batched+clips+pack` | 2 von 17 | 0 von 1 | 11 von 37 | 7 von 28 | 3 von 14 | 25 von 114 | 39 von 104 | 18 von 45 | 21 von 104 | 1 von 22 | 8 von 33 | 114,0 von 415,0 | 27,5 % |

**Kein Turn an der Wortzeit:**

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I | Rate ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 0,3 von 11 | 4 von 23 | 19,7 von 59 | 7,7 von 27 | 10,7 von 32 | 11 von 28 | 4 von 20 | 3 von 35 | 8,7 von 22 | 42,3 von 63 | 7 von 21 | 109,7 von 319,0 | 34,4 % |
| `base+batched` (Mittel) | 0 von 12 | 3 von 20 | 13 von 47 | 12 von 30 | 10 von 30 | 15 von 30 | 4 von 13 | 26 von 50 | 12 von 26 | 25 von 43 | 4 von 13 | 112,0 von 288,0 | 38,9 % |
| `base+batched+clips` | 1 von 3 | 4 von 5 | 20 von 23 | 30 von 32 | 18 von 22 | 9 von 10 | 7 von 7 | 8 von 11 | 19 von 19 | 4 von 7 | 9 von 11 | 110,0 von 131,0 | 84,0 % |
| `base+batched+clips+join` | 1 von 2 | 4 von 5 | 15 von 18 | 31 von 32 | 18 von 22 | 9 von 11 | 4 von 4 | 27 von 31 | 19 von 19 | 4 von 7 | 9 von 11 | 122,0 von 143,0 | 85,3 % |
| `base+batched+clips+join+pad` | 1 von 13 | 4 von 13 | 12 von 49 | 29 von 44 | 15 von 38 | 7 von 23 | 5 von 15 | 29 von 47 | 11 von 26 | 2 von 21 | 4 von 17 | 108,0 von 280,0 | 38,6 % |
| `base+batched+clips+join+pad+min` | 1 von 12 | 3 von 12 | 15 von 56 | 19 von 34 | 23 von 38 | 11 von 27 | 7 von 21 | 26 von 52 | 17 von 30 | 8 von 26 | 7 von 16 | 120,0 von 294,0 | 40,8 % |
| `base+batched+clips+pack` | 1 von 12 | 2 von 16 | 14 von 52 | 12 von 34 | 11 von 32 | 5 von 24 | 4 von 18 | 28 von 53 | 23 von 37 | 15 von 35 | 8 von 16 | 100,0 von 292,0 | 34,2 % |
| `norm` (Mittel) | 1 von 12 | 3 von 20 | 19 von 59 | 15,3 von 41 | 3 von 24 | 9 von 27 | 2,3 von 12 | 13 von 45 | 6 von 24 | 8,7 von 31 | 5,3 von 15 | 79,7 von 286,0 | 27,9 % |
| `loud+batched` (Mittel) | 1 von 10 | 2 von 20 | 16 von 57 | 8 von 33 | 24 von 45 | 7 von 22 | 1 von 17 | 9 von 40 | 7 von 18 | 28 von 45 | 3 von 13 | 99,0 von 302,0 | 32,8 % |
| `loud+batched+clips` | 1 von 3 | 8 von 9 | 21 von 24 | 18 von 20 | 12 von 15 | 5 von 6 | 18 von 18 | 8 von 12 | 15 von 15 | 2 von 4 | 6 von 9 | 99,0 von 120,0 | 82,5 % |
| `loud+batched+clips+join` | 1 von 2 | 8 von 9 | 16 von 19 | 18 von 20 | 12 von 15 | 5 von 7 | 18 von 18 | 25 von 29 | 15 von 15 | 2 von 4 | 6 von 8 | 111,0 von 131,0 | 84,7 % |
| `loud+batched+clips+join+pad` | 1 von 11 | 9 von 18 | 16 von 55 | 17 von 31 | 13 von 35 | 6 von 22 | 9 von 20 | 35 von 60 | 13 von 26 | 2 von 22 | 2 von 15 | 110,0 von 289,0 | 38,1 % |
| `loud+batched+clips+join+pad+min` | 1 von 13 | 5 von 14 | 19 von 60 | 12 von 27 | 25 von 39 | 9 von 25 | 11 von 25 | 23 von 50 | 17 von 31 | 9 von 26 | 3 von 12 | 117,0 von 291,0 | 40,2 % |
| `loud+batched+clips+pack` | 1 von 12 | 2 von 17 | 14 von 53 | 17 von 40 | 9 von 32 | 8 von 28 | 1 von 16 | 30 von 52 | 18 von 35 | 11 von 32 | 1 von 10 | 94,0 von 292,0 | 32,2 % |

**Außerhalb der VAD bzw. der Abschnitte:**

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I | Rate ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 0,3 von 1 | 0 von 1 | 13 von 20 | 1,7 von 3 | 3 von 3 | 7 von 8 | 0,3 von 1 | 1 von 1 | 0 von 0 | 6,3 von 11 | 2 von 6 | 34,7 von 55,0 | 63,0 % |
| `base+batched` (Mittel) | 0 von 8 | 1 von 6 | 12 von 24 | 8 von 9 | 8 von 11 | 10 von 11 | 3 von 4 | 13 von 16 | 3 von 3 | 5 von 7 | 2 von 2 | 62,0 von 98,0 | 63,3 % |
| `base+batched+clips` | 1 von 3 | 5 von 6 | 20 von 23 | 30 von 32 | 18 von 22 | 9 von 12 | 7 von 8 | 8 von 13 | 19 von 19 | 4 von 7 | 9 von 11 | 111,0 von 137,0 | 81,0 % |
| `base+batched+clips+join` | 1 von 2 | 4 von 5 | 15 von 18 | 31 von 32 | 18 von 22 | 9 von 11 | 4 von 4 | 27 von 31 | 19 von 19 | 4 von 7 | 9 von 11 | 122,0 von 143,0 | 85,3 % |
| `base+batched+clips+join+pad` | 1 von 1 | 1 von 1 | 6 von 6 | 16 von 16 | 8 von 8 | 1 von 1 | 3 von 3 | 19 von 19 | 2 von 2 | 2 von 2 | 3 von 3 | 60,0 von 60,0 | 100,0 % |
| `base+batched+clips+join+pad+min` | 1 von 1 | 1 von 1 | 9 von 9 | 10 von 10 | 10 von 10 | 2 von 2 | 1 von 1 | 16 von 16 | 4 von 4 | 2 von 2 | 2 von 2 | 54,0 von 54,0 | 100,0 % |
| `base+batched+clips+pack` | 1 von 1 | 0 von 0 | 4 von 4 | 2 von 2 | 1 von 1 | 2 von 2 | 0 von 0 | 20 von 20 | 2 von 2 | 0 von 0 | 1 von 1 | 31,0 von 31,0 | 100,0 % |
| `norm` (Mittel) | 1 von 2 | 0 von 1 | 9 von 11 | 9,3 von 10 | 0 von 1 | 3 von 4 | 1 von 1 | 1 von 2 | 0 von 0 | 3,7 von 4 | 1 von 1 | 29,0 von 37,0 | 78,4 % |
| `loud+batched` (Mittel) | 1 von 6 | 1 von 5 | 17 von 26 | 5 von 6 | 17 von 20 | 3 von 4 | 1 von 5 | 0 von 0 | 0 von 0 | 20 von 22 | 0 von 1 | 65,0 von 95,0 | 68,4 % |
| `loud+batched+clips` | 1 von 3 | 9 von 10 | 21 von 24 | 18 von 20 | 12 von 15 | 7 von 8 | 18 von 19 | 8 von 13 | 15 von 15 | 2 von 4 | 6 von 9 | 102,0 von 125,0 | 81,6 % |
| `loud+batched+clips+join` | 1 von 2 | 8 von 9 | 16 von 19 | 18 von 20 | 12 von 15 | 5 von 7 | 18 von 18 | 25 von 29 | 15 von 15 | 2 von 4 | 6 von 8 | 111,0 von 131,0 | 84,7 % |
| `loud+batched+clips+join+pad` | 1 von 1 | 3 von 3 | 9 von 9 | 10 von 10 | 8 von 8 | 1 von 1 | 5 von 5 | 16 von 16 | 2 von 2 | 2 von 2 | 2 von 2 | 57,0 von 57,0 | 100,0 % |
| `loud+batched+clips+join+pad+min` | 1 von 1 | 1 von 1 | 12 von 12 | 5 von 6 | 11 von 11 | 1 von 1 | 6 von 6 | 9 von 9 | 1 von 1 | 2 von 2 | 1 von 1 | 49,0 von 50,0 | 98,0 % |
| `loud+batched+clips+pack` | 1 von 1 | 0 von 0 | 4 von 4 | 6 von 6 | 0 von 0 | 0 von 0 | 0 von 0 | 20 von 20 | 1 von 1 | 1 von 1 | 1 von 1 | 33,0 von 33,0 | 100,0 % |

- **Einwürfe mit 1–3 Wörtern:** `norm` 34,3 %. Die Varianten auf `loudnorm`-Audio liegen bei 34,9 % (`+clips`) bis 46,9 % (`+min`), keine darunter. Auf Rohaudio liegen `+clips`, `+join` und `+pad` mit 36,6 bis 38,9 % unter `base` (40,6 %) und `base+batched` (45,7 %).
- **Beiträge unter 2 s:** Ein Stück je Turn senkt die Rate auf 10,8 bis 12,3 % (`norm` 13,4 %, `base+batched` 16,1 %). Mindestlänge und Packen geben den Gewinn wieder ab (13,7 bis 17,9 %).
- **Überlappung:** kein klarer Unterschied, 27,5 bis 32,5 % gegen 28,0 % bei `norm`.
- **Kein Turn:** Ohne Polster fehlen 82 bis 85 % der Wörter, die der Lauf außerhalb aller Turns verortet. Mit Polster sind es 38 bis 41 %, gepackt 32 bis 34 %; `norm` hat 27,9 %.
- **Außerhalb der Abschnitte:** Ohne Polster liegen 125 bis 143 Referenzwörter außerhalb, davon fehlen 102 bis 122. Mit Polster bleiben 50 bis 60, gepackt 31 bis 33, und sie fehlen fast alle. Bei `norm` liegen 37 Wörter außerhalb der VAD, 29,0 fehlen.

## Einfügungen und Wiederholung

| Variante | A | B | C | D | E | F | G | H | I | J | K | Summe ohne I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` (Mittel) | 17 | 18 | 38 | 49,7 | 7,3 | 10,7 | 26 | 17 | 14,7 | 69 | 9 | 261,7 |
| `base+batched` (Mittel) | 15 | 4 | 34 | 11 | 6 | 10 | 40 | 43 | 13 | 15 | 9 | 187,0 |
| `base+batched+clips` | 24 | 17 | 60 | 23 | 17 | 50 | 61 | 41 | 37 | 20 | 29 | 342,0 |
| `base+batched+clips+join` | 22 | 18 | 54 | 23 | 19 | 46 | 50 | 36 | 37 | 19 | 26 | 313,0 |
| `base+batched+clips+join+pad` | 22 | 18 | 69 | 34 | 20 | 43 | 47 | 35 | 36 | 18 | 29 | 335,0 |
| `base+batched+clips+join+pad+min` | 21 | 16 | 33 | 10 | 8 | 12 | 9 | 25 | 11 | 14 | 22 | 170,0 |
| `base+batched+clips+pack` | 13 | 5 | 27 | 8 | 5 | 10 | 52 | 5 | 23 | 13 | 13 | 151,0 |
| `norm` (Mittel) | 17 | 6 | 20,3 | 14,3 | 12 | 12 | 40 | 15 | 47 | 17,3 | 19 | 173,0 |
| `loud+batched` (Mittel) | 16 | 5 | 26 | 11 | 96 | 18 | 24 | 29 | 13 | 9 | 12 | 246,0 |
| `loud+batched+clips` | 28 | 16 | 71 | 22 | 23 | 44 | 69 | 92 | 34 | 18 | 19 | 402,0 |
| `loud+batched+clips+join` | 21 | 17 | 63 | 20 | 24 | 40 | 66 | 86 | 35 | 19 | 15 | 371,0 |
| `loud+batched+clips+join+pad` | 23 | 16 | 64 | 31 | 26 | 41 | 56 | 62 | 37 | 17 | 17 | 353,0 |
| `loud+batched+clips+join+pad+min` | 23 | 15 | 31 | 21 | 10 | 15 | 21 | 12 | 13 | 13 | 16 | 177,0 |
| `loud+batched+clips+pack` | 18 | 4 | 26 | 12 | 5 | 13 | 105 | 6 | 16 | 12 | 13 | 214,0 |

| Variante | Pilotsitzung: Wörter | Pilotsitzung: Wiederholung | zweite Sitzung: Wörter | zweite Sitzung: Wiederholung |
| --- | --- | --- | --- | --- |
| `base` | 33009 (32923–33067) | 0,7% (0,5%–0,8%) | 28927 (28896–28960) | 0,7% (0,5%–0,9%) |
| `base+batched` | 32642 (32642–32642) | 1,0% (1,0%–1,0%) | 29450 (29450–29450) | 1,2% (1,2%–1,2%) |
| `base+batched+clips` | 34572 (34572–34572) | 2,6% (2,6%–2,6%) | 30741 (30741–30741) | 2,4% (2,4%–2,4%) |
| `base+batched+clips+join` | 34275 (34275–34275) | 2,4% (2,4%–2,4%) | 30558 (30558–30558) | 2,5% (2,5%–2,5%) |
| `base+batched+clips+join+pad` | 34132 (34132–34132) | 1,9% (1,9%–1,9%) | 30686 (30686–30686) | 2,2% (2,2%–2,2%) |
| `base+batched+clips+join+pad+min` | 32896 (32896–32896) | 1,2% (1,2%–1,2%) | 29605 (29605–29605) | 1,4% (1,4%–1,4%) |
| `base+batched+clips+pack` | 33151 (33151–33151) | 2,3% (2,3%–2,3%) | 29969 (29969–29969) | 3,2% (3,2%–3,2%) |
| `norm` | 33503 (33218–33672) | 0,6% (0,6%–0,7%) | 29878 (29767–30021) | 0,4% (0,4%–0,5%) |
| `loud+batched` | 32886 (32886–32886) | 1,7% (1,7%–1,7%) | 29974 (29974–29974) | 1,6% (1,6%–1,6%) |
| `loud+batched+clips` | 34667 (34667–34667) | 2,5% (2,5%–2,5%) | 31122 (31122–31122) | 3,3% (3,3%–3,3%) |
| `loud+batched+clips+join` | 34344 (34344–34344) | 2,2% (2,2%–2,2%) | 30938 (30938–30938) | 3,4% (3,4%–3,4%) |
| `loud+batched+clips+join+pad` | 34417 (34417–34417) | 1,7% (1,7%–1,7%) | 31118 (31118–31118) | 3,4% (3,4%–3,4%) |
| `loud+batched+clips+join+pad+min` | 33040 (33040–33040) | 1,2% (1,2%–1,2%) | 29956 (29956–29956) | 2,0% (2,0%–2,0%) |
| `loud+batched+clips+pack` | 33133 (33133–33133) | 1,5% (1,5%–1,5%) | 30251 (30251–30251) | 2,9% (2,9%–2,9%) |

- **Einfügungen:** `norm` 173,0. Ein Stück je Turn fügt auf `loudnorm`-Audio 353 bis 402 Wörter ein, mit Mindestlänge 177, gepackt 214 (davon 105 an G).
- **Wiederholungsanteil:** `norm` 0,6 % und 0,4 %. Jede neue Variante liegt darüber, am niedrigsten `+clips+join+pad+min` mit 1,2 % und 1,4 % (Rohaudio) bzw. 1,2 % und 2,0 %.
- **Wörter im Segment:** Ein Stück je Turn schreibt 1000 bis 1300 Wörter mehr als `norm`, bei mehr Auslassungen an den Referenzen.

## Laufzeit und Speicher

RTX 3080 Ti, 12 GB. Wall-Zeit je Segment von 5,00 h (Pilotsitzung) und 4,78 h (zweite Sitzung), je Seed.

| Variante | Pilotsitzung: Wall (min) | Pilotsitzung: min je Stunde Audio | Pilotsitzung: Peak-RAM (GiB) | Pilotsitzung: Peak-VRAM (GiB, davor) | zweite Sitzung: Wall (min) | zweite Sitzung: min je Stunde Audio | zweite Sitzung: Peak-RAM (GiB) | zweite Sitzung: Peak-VRAM (GiB, davor) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | 6,3 / 6,5 / 6,6 | 1,25 / 1,28 / 1,30 | 13,9 / 13,9 / 13,8 | 4,0 (1,8) / 3,6 (1,1) / 3,6 (1,1) | – / 6,8 / 6,9 | 1,30 / 1,42 / 1,42 | 0,2 / 12,8 / 12,8 | 1,3 (1,3) / 3,9 (1,3) / 4,3 (1,3) |
| `norm` | – / 6,5 / 6,4 | 1,32 / 1,29 / 1,26 | 14,2 / 14,1 / 14,1 | 3,9 (1,5) / 3,9 (1,4) / 3,9 (1,4) | – / 6,1 / 5,9 | 1,23 / 1,27 / 1,22 | 13,7 / 13,1 / 13,1 | 3,9 (1,4) / 3,9 (1,4) / 3,9 (1,4) |
| `base+batched` | 2,0 / 1,9 / 1,9 | 0,38 / 0,37 / 0,37 | 4,4 / 4,4 / 4,3 | 4,8 (1,4) / 4,8 (1,5) / 4,8 (1,4) | 1,7 / 1,7 / 1,7 | 0,34 / 0,34 / 0,33 | 4,0 / 4,1 / 4,0 | 4,6 (1,3) / 4,6 (1,3) / 4,6 (1,3) |
| `loud+batched` | 1,8 / 2,0 / 2,0 | 0,35 / 0,38 / 0,38 | 4,4 / 4,3 / 4,3 | 4,7 (1,3) / 4,6 (1,3) / 4,6 (1,3) | 1,7 / 1,7 / 1,9 | 0,34 / 0,35 / 0,37 | 4,1 / 4,1 / 4,1 | 4,6 (1,3) / 4,6 (1,3) / 4,6 (1,3) |
| `base+batched+clips` | 10,6 | 2,10 | 16,3 | 4,5 (1,3) | 9,2 | 1,91 | 14,9 | 4,6 (1,2) |
| `base+batched+clips+join` | 9,4 / 9,0 / 9,0 | 1,86 | 15,1 | 4,5 (1,1) | 8,6 / 8,2 / 8,2 | 1,78 | 13,8 | 4,5 (1,1) |
| `base+batched+clips+join+pad` | 9,3 | 1,84 | 15,2 | 4,5 (1,1) | 8,4 | 1,74 | 13,9 | 4,5 (1,1) |
| `base+batched+clips+join+pad+min` | 5,5 | 1,08 | 9,6 | 4,6 (1,1) | 4,9 | 1,01 | 8,8 | 4,5 (1,1) |
| `base+batched+clips+pack` | 2,4 | 0,46 | 4,9 | 4,5 (1,1) | 2,3 | 0,47 | 4,7 | 4,5 (1,1) |
| `loud+batched+clips` | 10,0 | 1,98 | 16,3 | 4,5 (1,2) | 9,2 | 1,92 | 14,9 | 4,5 (1,1) |
| `loud+batched+clips+join` | 9,1 / 9,0 / 9,0 | 1,80 | 15,1 | 4,4 (1,1) | 8,2 / 8,2 / 8,2 | 1,70 | 13,8 | 4,5 (1,1) |
| `loud+batched+clips+join+pad` | 9,1 | 1,81 | 15,2 | 4,4 (1,1) | 8,2 | 1,71 | 13,9 | 4,5 (1,2) |
| `loud+batched+clips+join+pad+min` | 5,4 | 1,07 | 9,6 | 4,6 (1,1) | 4,9 | 1,01 | 8,8 | 4,5 (1,2) |
| `loud+batched+clips+pack` | 2,4 | 0,46 | 4,9 | 4,5 (1,2) | 2,3 | 0,47 | 4,7 | 4,5 (1,2) |

- **Laufzeit:** Rund 4500 bis 5000 Abschnitte brauchen 8 bis 11 min je Segment, das Fünffache von `base+batched` und mehr als `norm`. Gepackt (rund 900 Abschnitte) sind es 2,3 bis 2,4 min. Kein Lauf kam in die Nähe der Grenze von 60 min aus dem Plan.
- **Speicher:** VRAM wie bei `+batched` (4,4 bis 4,6 GiB). Der Arbeitsspeicher wächst mit der Zahl der Abschnitte auf bis zu 16,3 GiB.
- **Einschränkung:** Der erste Lauf der zweiten Sitzung (`base+batched+clips`) lief rund sechs Minuten lang neben der Auswertung der Pilotsitzung auf der CPU. „–“ heißt, dass `run.json` der Wurzel keine Wall-Zeit trägt.

## Seeds

Abweichung vom Ticket wie im Plan begründet: Drei Seeds liefen nur für `+clips+join`, auf beiden Audios und in beiden Sitzungen.

| Variante | Pilotsitzung: Wörter je Seed | Text und Wortzeiten gleich wie Seed 1 | zweite Sitzung: Wörter je Seed | Text und Wortzeiten gleich wie Seed 1 |
| --- | --- | --- | --- | --- |
| `base+batched+clips+join` | 34398 / 34398 / 34398 | ja / ja | 30611 / 30611 / 30611 | ja / ja |
| `loud+batched+clips+join` | 34464 / 34464 / 34464 | ja / ja | 30973 / 30973 / 30973 | ja / ja |

Die Seeds sind Wort für Wort und Zeit für Zeit gleich. Die übrigen Varianten bleiben deshalb bei Seed 1.

## Regeltabelle

Die fünf Varianten auf `loudnorm`-Audio (`loud+batched+…`) gegen die [Go-Regel](#go-regel). Quellen: [Auslassungen](#auslassungen), [Nach Klassen](#nach-klassen), [WER](#wer), [Längste Folge](#längste-folge-ausgelassener-wörter), [Einfügungen und Wiederholung](#einfügungen-und-wiederholung).

| Punkt | Maßstab | `+clips` | `+clips+join` | `+clips+join+pad` | `+clips+join+pad+min` | `+clips+pack` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 Auslassungen, Summe ohne I | unter 584,3 (`norm`) und unter 628 (`loud+batched`) | 716: nein | 722: nein | 693: nein | 711: nein | 607: nein (unter `loud+batched`, über `norm`) |
| 2 Rate bei 1–3 Wörtern | unter 34,3 % | 34,9 %: nein | 37,7 %: nein | 36,0 %: nein | 46,9 %: nein | 41,7 %: nein |
| 3 WER über dem schlechtesten Lauf von `norm` | an keiner Referenz | an 9 (A bis I): nein | an 9 (A bis I): nein | an 9 (A bis I): nein | an 8 (A bis F, H, I): nein | an 3 (C, G, H): nein |
| 3 längste Folge ausgelassener Wörter | unter 30 | 33 (H): nein | 33 (H): nein | 21: ja | 29: ja | 77 (H): nein |
| 4 Einfügungen, Summe ohne I | höchstens 173,0 | 402: nein | 371: nein | 353: nein | 177: nein | 214: nein |
| 4 Wiederholungsanteil, Pilotsitzung / zweite Sitzung | höchstens 0,6 % / 0,4 % | 2,5 % / 3,3 %: nein | 2,2 % / 3,4 %: nein | 1,7 % / 3,4 %: nein | 1,2 % / 2,0 %: nein | 1,5 % / 2,9 %: nein |
| Ergebnis nach der Regel | alle vier Punkte | No-Go | No-Go | No-Go | No-Go | No-Go |

Gegenprobe auf Rohaudio (`base+batched+…`), ohne eigenes Go:

| | `base` | `base+batched` | `+clips` | `+clips+join` | `+clips+join+pad` | `+clips+join+pad+min` | `+clips+pack` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WER, Mittel A bis K | 37,8 % | 31,6 % | 40,2 % | 39,6 % | 39,1 % | 32,9 % | 30,4 % |
| Auslassungen, Summe ohne I | 871,0 | 705 | 729 | 743 | 731 | 714 | 697 |
| Rate bei 1–3 Wörtern | 40,6 % | 45,7 % | 37,7 % | 38,9 % | 36,6 % | 44,0 % | 42,3 % |
| Einfügungen, Summe ohne I | 261,7 | 187 | 342 | 313 | 335 | 170 | 151 |
| längste Folge ausgelassener Wörter | 66 (J) | 94 (H) | 34 (C) | 34 (C) | 34 (C) | 20 | 77 (H) |

Das Bild ist auf beiden Audios dasselbe. Gegen `base+batched` gewinnt ein Stück je Turn bei den Einwürfen (36,6 bis 38,9 % gegen 45,7 %) und beim größten Blockverlust, verliert aber bei WER und Einfügungen. Die Auslassungen insgesamt bleiben auf dem Stand von `base+batched`.

## Was der Weg nicht erreicht

- **Wörter ohne Turn der Diarisierung.** Über A bis H, J und K (5135 Referenzwörter) verortet `norm` 286 Wörter (5,6 %) an Stellen, an denen kein Turn läuft; 79,7 davon fehlen, das sind 13,6 % seiner Auslassungen. Abschnitte aus der Diarisierung können diese Wörter nur über Polster oder Packen erreichen:
  - Ohne Polster liegen 125 bis 131 Referenzwörter außerhalb aller Abschnitte, 102 bis 111 davon fehlen (14,2 bis 15,4 % der Auslassungen der Variante).
  - Mit Polster oder gepackt verorten die Läufe 289 bis 292 Wörter ohne Turn, 94 bis 117 davon fehlen (15,5 bis 16,5 % der Auslassungen). Die Rate liegt mit 32,2 bis 40,2 % über der von `norm` (27,9 %).
- **Überlappung.** Die Rate bleibt bei 27,5 bis 32,5 % gegen 28,0 % bei `norm`. Exklusive Turns enthalten in der Überlappung nur eine Stimme als Abschnitt, das Audio darin bleibt gemischt.
- **Einwürfe laut Handreferenz.** Der Gewinn in Beiträgen unter 2 s laut Diarisierung kommt bei den Beiträgen mit 1–3 Wörtern der Handreferenz auf `loudnorm`-Audio nicht an (34,9 bis 46,9 % gegen 34,3 %). Die Klasse ist klein: 175 Wörter, davon 43 an H und 38 an D.
- **Blockverlust.** Gepackt fehlen an H 77 Wörter am Stück; nur 20 Referenzwörter liegen dort außerhalb der Abschnitte. Der Block geht also beim Dekodieren verloren, nicht durch fehlende Abdeckung. Die offene Frage aus TOOL-104, ob eine großzügigere VAD der Batched-Pipeline hilft, ist damit beantwortet: `+clips+pack` dekodiert 18 bis 21 min mehr als die VAD der Pipeline und verliert trotzdem Blöcke.
- **Halluzination an kurzen Stücken.** Ein Stück je Turn schreibt 1000 bis 1300 Wörter mehr als `norm` über das Segment und verdoppelt die Einfügungen an den Referenzen. Erst die Mindestlänge von 2 s bringt sie auf den Stand von `norm` (177 gegen 173,0), kostet aber den Gewinn bei kurzen Beiträgen.

## Als Zusatzlauf zum Hauptlauf

Nachfrage der Projektverantwortlichen vom 2026-11-27: Lässt sich der Lauf je Redebeitrag nur dort einsetzen, wo er Vorteile hat? Gemessen ist die Obergrenze mit `seeds.py --variant norm --with loud+batched+clips+join` aus den vorhandenen Läufen, wie das Orakel in [TOOL-104](TOOL-104-recherche-auslassungen.md). Hauptlauf ist `norm` (Mittel der drei Seeds), zweiter Lauf `loud+batched+clips+join`.

| Referenz | Auslassungen von `norm` | der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | Gewinn des Orakels (Punkte WER) | Gewinn der naiven Vereinigung (Punkte WER) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 29,0 | 4,0 | 0,0 | 5,0 | 20,0 | 0,8 | 0,2 |
| B | 42,0 | 0,0 | 0,0 | 14,0 | 28,0 | 0,0 | −3,9 |
| C | 89,3 | 14,7 | 3,0 | 27,7 | 47,0 | 1,6 | −4,9 |
| D | 62,3 | 11,3 | 2,0 | 9,0 | 42,0 | 2,5 | −0,1 |
| E | 30,0 | 4,0 | 0,0 | 8,0 | 18,0 | 1,1 | −7,0 |
| F | 78,7 | 18,7 | 6,7 | 11,0 | 49,0 | 3,2 | −6,0 |
| G | 85,0 | 24,3 | 17,0 | 16,0 | 44,7 | 4,4 | −9,9 |
| H | 67,0 | 8,0 | 3,0 | 17,0 | 42,0 | 1,7 | −10,2 |
| I | 60,0 | 10,0 | 2,0 | 4,0 | 46,0 | 1,7 | −3,9 |
| J | 63,0 | 19,7 | 13,0 | 14,3 | 29,0 | 5,0 | −1,2 |
| K | 38,0 | 7,3 | 4,3 | 12,0 | 18,7 | 1,7 | −3,7 |
| Summe ohne I | 584,3 | 112,0 | 49,0 | 134,0 | 338,3 | | |

- **Obergrenze:** Ein Lauf je Redebeitrag hat 112 der 584,3 Auslassungen von `norm` richtig (19 %). 49 davon liegen in Folgen ab 5 Wörtern, also in Blöcken, die `norm` in einem Seed verliert (G, J); 63 sind verstreute Wörter. 338,3 Auslassungen (58 %) fehlen in beiden Läufen.
- **Ohne Auswahlregel schadet es:** Nimmt man alles dazu, was der zweite Lauf mehr hat, wird die WER an zehn von elf Referenzen schlechter, um bis zu 10,2 Punkte.
- **Was fehlt:** eine Regel ohne Handreferenz, die an einer Lücke die richtigen von den erfundenen Wörtern des zweiten Laufs trennt. Das ist die Frage von TOOL-114 (Blöcke aus einem zweiten Lauf), nur für einzelne Wörter statt für Blöcke; dort hielt sie schon bei Blöcken ab 10 Wörtern nicht mehr ([TOOL-108](TOOL-108-blockverlust.md)).
- **Gepackt als zweiter Lauf** (`loud+batched+clips+pack`, nur gegen Seed 1 von `norm`): 139 von 600 Auslassungen richtig, 69 davon in Folgen ab 5 Wörtern, fast alle an J und F.

## Entscheidung

**No-Go, entschieden von der Projektverantwortlichen am 2026-11-27.** Sie folgt der Empfehlung aus der [Regeltabelle](#regeltabelle).

- **Hauptlauf:** bleibt `norm` wie seit TOOL-109, also das pegelausgeglichene Audio am Stück mit dem nicht gebündelten Decoder. Die Pipeline ändert sich nicht.
- **Kein Umsetzungsticket:** Die Dekodierung je Redebeitrag wird nicht eingebaut, auch nicht als Zusatzlauf für kurze Beiträge.
- **Werkzeug:** `clips.py`, die `+clips`-Varianten in `asr.py` und die Erweiterung von `omissions.py` bleiben als Messwerkzeug unter `scripts/spike/`.
- **Übergaben:**
  - TOOL-113 und TOOL-114 rechnen mit `norm` als Hauptlauf; die Blockverluste an G und J bleiben ihr Thema.
  - TOOL-114 bekommt die Obergrenze aus [Als Zusatzlauf zum Hauptlauf](#als-zusatzlauf-zum-hauptlauf).
  - TOOL-100 bekommt das Ergebnis.
- **Erledigt aus TOOL-104:** die Frage nach einer großzügigeren VAD für die Batched-Pipeline ([Was der Weg nicht erreicht](#was-der-weg-nicht-erreicht)).

## Hinweise für eine Umsetzung

Für den Fall, dass der Weg später aufgegriffen wird, etwa mit einem anderen Modell.

- **Reihenfolge:** Die Pipeline erkennt heute zuerst und diarisiert danach. Abschnitte aus der Diarisierung verlangen die umgekehrte Reihenfolge; `--no-diarize` gäbe es für diesen Weg nicht mehr, und eine neue Diarisierung macht das Transkript veraltet.
- **Abschnitte:** Gemessen ist die Diarisierung auf dem Roh-WAV. Die Regeln (Verbinden, Polster, Mindestlänge, Packen, Teilen über 30 s) stehen in `scripts/spike/clips.py` und müssten mit Tests in das Paket umziehen. Parameter und Hash der Abschnitte gehören in `asr.settings`; ob der Contract (IOA-1214) sie trägt, ist offen.
- **Passagen und Bewertung:** Die Batched-Pipeline liefert ein Segment je Abschnitt, ohne Fallback und ohne Dekodierfenster. Mit einem Stück je Turn entstehen rund 7000 Passagen je Segment statt rund 2000, davon rund 2700 bis 3100 `uncertain`; die Schwellen aus `review.uncertainty` sind dafür nicht kalibriert (TOOL-35).
- **Laufzeit und Speicher:** 8 bis 11 min und bis zu 16,3 GiB Arbeitsspeicher je Segment bei einem Stück je Turn, 2,3 bis 2,4 min und 4,9 GiB gepackt.
- **Blockverlust:** Jede gepackte Variante braucht eine Antwort auf Verluste wie an H, also TOOL-113 oder TOOL-114.
