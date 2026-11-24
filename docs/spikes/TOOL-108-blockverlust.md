# TOOL-108 — Blockverlust ohne Referenz von Halluzination trennen

Stand 2026-11-24, Messung je Signal und drei festgeschriebene Regeln. Die Prüfung an zwei neuen Fenstern und die Entscheidung folgen. Spike-Bericht zu [TOOL-108](../plans/TOOL-108-block-loss.md), Werkzeug: [`scripts/spike/blocks.py`](../../scripts/spike/blocks.py). Neu transkribiert wurden nur die Seeds 4 und 5 von `base`, alles lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Zwischenstand

**Der `avg_logprob` des Quelllaufs trennt an den Handreferenzen den verlorenen Block vom erfundenen. „Sprache ohne Wörter“ trennt nur zwischen zwei verschiedenen Pipelines.** Eine Entscheidung ist das noch nicht: Je Paarung reichen nur wenige Blöcke in eine Referenz.

- **`base` mit den anderen `base`-Seeds als Quelle:** Jeder Block ab 20 Wörtern kostet an D im Mittel 8,2 Punkte WER, für einen Hauptlauf 21,2. Nur Blöcke mit `avg_logprob` über −1 bringen an C 4,3, an D 3,4 und an E 2,5 Punkte, und kein Hauptlauf verliert an einer Referenz ([`base` untereinander](#base-mit-anderen-base-seeds)).
- **Mit fünf Seeds** sind es 3,2 an C, 7,2 an D und 3,8 an E. „In einem weiteren Lauf“ nimmt dann dieselben Blöcke an wie `avg_logprob`; mit drei Seeds verlor es an C einen richtigen Block ([Fünf Seeds](#fünf-seeds)).
- **`base+batched` mit `base` als Quelle:** 11,9 Punkte an H und 6,0 an I, sonst kein Block. Ohne Signal kommen 12,5 Punkte Verlust an D dazu; `avg_logprob`, Wort-Confidence, „kein Fallback“ und „Sprache ohne Wörter“ nehmen diesen Block nicht an, Übereinstimmung der `base`-Seeds schon ([`base+batched` als Hauptlauf](#basebatched-mit-base-als-quelle)).
- **`base` mit `base+batched` als Quelle:** „Sprache ohne Wörter ab 2 s“ bringt 4,2 an C, 6,2 an D und 2,0 an E ohne Verlust. `avg_logprob` nimmt hier jeden Block an, auch einen an G mit 7,1 Punkten Verlust für einen Hauptlauf ([`base` mit `base+batched`](#base-mit-basebatched-als-quelle)).
- **`loud`:** Unter den `loud`-Seeds reicht kein Block ab 20 Wörtern in eine Referenz. `loud+batched` als Quelle fügt an E 288 falsche Wörter ein; „keine Wiederholung“, Kompression und „Sprache ohne Wörter“ halten sie fern ([`loud`](#loud)).
- **Drei Regeln sind festgeschrieben.** Regel A (Dekodierwerte der Quelle) erfüllt an A bis I die Go-Regel in allen drei `base`-Paarungen, Regel B (Sprache ohne Wörter) nur über zwei Pipelines hinweg ([Regeln](#regeln)).
- **Blöcke ab 10 Wörtern** verschlechtern das Bild: An B und G kommen Verluste dazu, und an G hält `avg_logprob` sie nicht mehr fern ([Blöcke ab 10 Wörtern](#blöcke-ab-10-wörtern)).

## Material und Methode

| | |
| --- | --- |
| Läufe | `base`, `loud` (Seeds 1–3), `base+batched`, `loud+batched` (Seed 1, die Seeds sind Wort für Wort gleich) aus TOOL-93, TOOL-103 und TOOL-104; neu `base` Seeds 4 und 5, je rund 6,5 min je Segment |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |
| Referenz D | Pilotsitzung, 0:43:00–0:46:00, 449 Wörter |
| Referenz E | Pilotsitzung, 1:23:00–1:26:00, 369 Wörter |
| Referenz F | Pilotsitzung, 1:40:00–1:43:00, 584 Wörter |
| Referenz G | Pilotsitzung, 1:31:00–1:34:00, 551 Wörter |
| Referenz H | zweite Sitzung, 1:38:00–1:41:00, 470 Wörter |
| Referenz I | Pilotsitzung, 1:38:00–1:41:00, 597 Wörter; überschneidet sich eine Minute mit F |

- **Paarung:** Jeder Lauf der Hauptvariante ist einmal Hauptlauf. Quelle sind die anderen Seeds derselben Variante oder die Läufe einer zweiten Variante.
- **Angebot:** ein Block ab 20 Wörtern in Folge, den die Quelle an einer Stelle mehr hat als der Hauptlauf. Ausrichtung wie in `seeds.py` (TOOL-102), abschnittsweise je 5 Minuten; die Zahl der Angebote je Seed-Paar stimmt mit der Spalte „Blöcke ab 20 Wörtern“ dort überein. Die Schwelle stand vor der Messung fest.
- **Signale je Angebot**, alle ohne Handreferenz:
  - *Quelle:* höchste `compression_ratio`, niedrigster `avg_logprob` und höchste `no_speech_prob` der Passagen des Blocks; kein Wort des Blocks in einem Dekodierfenster mit Temperatur-Fallback; mittlere Wort-Confidence; Wiederholungsanteil 0.
  - *Hauptlauf:* Lücke zwischen den Wörtern um die Stelle; Länge des Worts vor der Lücke; dünnes Dekodierfenster.
  - *Sprache ohne Wörter:* Zeit im Block, in der die Diarisierung Sprache hört und der Hauptlauf kein Wort hat (Definition aus TOOL-101).
  - *In einem weiteren Lauf:* Ein Lauf außer Hauptlauf und Quelle hat mindestens die Hälfte der Blockwörter in derselben Reihenfolge, höchstens 5 s neben dem Block.
- **Schwellen**, vor der Messung festgelegt: die der Pipeline aus `review.uncertainty` (Kompression 2,4, `avg_logprob` −1, `no_speech_prob` 0,6, Wort-Confidence 0,5, Lücke 2,5 s), 1 s für das Wort vor der Lücke, 2 s für Sprache ohne Wörter. Für die vier Dekodierwerte steht daneben der Median über alle Angebote des Aufrufs.
- **Angenommene Blöcke:** Bieten mehrere Quellen an derselben Stelle an, zählt der größte Block, den das Signal annimmt.
- **Wirkung:** Die angenommenen Blöcke werden an ihrer Stelle in den Hauptlauf eingesetzt, die Folge wird wie in `calibration.measure` gegen die Handreferenz gemessen. Gewinn in Punkten WER gegenüber dem Hauptlauf, negativ heißt schlechter.
- **Bei Batched-Läufen** gibt es weder Fallback noch Dekodierfenster. Die Zeile heißt dann „entfällt“. `avg_logprob` und `no_speech_prob` gelten dort je Stück von bis zu 30 s.
- **Leitplanke:** Kein Aufruf schreibt ein Transkript. Ein angenommener Block wäre in der Pipeline eine Alternative an der Stelle, das ASR-Ergebnis bliebe unverändert.

**Lesart der Tabellen:** Eine Zelle nennt die richtigen und falschen Wörter der angenommenen Blöcke an der Referenz, summiert über die Hauptläufe, dann den Gewinn im Mittel der Hauptläufe und in Klammern den kleinsten Gewinn eines Hauptlaufs. „–“ heißt: kein angenommener Block reicht in die Referenz.

## Über das Segment

Blöcke ab 20 Wörtern, der größte je Stelle, je Hauptlauf. Spanne über die Hauptläufe.

| Paarung | Sitzung | Blöcke | Wörter | Zeit (min) |
| --- | --- | --- | --- | --- |
| `base` ← `base`, 3 Seeds | Pilot | 14–18 | 611–745 | 4,6–6,2 |
| | zweite | 33–36 | 1418–1545 | 11,1–14,4 |
| `base` ← `base`, 5 Seeds | Pilot | 28–34 | 1205–1449 | 8,4–11,4 |
| | zweite | 42–51 | 1745–2270 | 11,7–19,0 |
| `base+batched` ← `base` | Pilot | 21 | 1062 | 8,0 |
| | zweite | 23 | 994 | 6,8 |
| `base` ← `base+batched` | Pilot | 17–20 | 687–863 | 5,4–6,6 |
| | zweite | 27–30 | 1182–1272 | 9,1–11,2 |
| `loud` ← `loud` | Pilot | 7–15 | 286–575 | 1,5–3,7 |
| | zweite | 7–14 | 315–597 | 2,1–5,4 |
| `loud+batched` ← `loud` | Pilot | 23 | 1066 | 7,5 |
| | zweite | 11 | 410 | 2,9 |
| `loud` ← `loud+batched` | Pilot | 9–16 | 478–752 | 3,4–4,9 |
| | zweite | 9–15 | 483–744 | 3,2–6,3 |

- **`loud` verliert unter seinen Seeds etwa halb so viele Blöcke wie `base`.** Das passt zu TOOL-103: Der Pegelausgleich macht die Läufe stabiler.
- **Was die Signale über das Segment annehmen**, `base` ← `base` mit 3 Seeds:
  - `avg_logprob` über −1: an der Pilotsitzung 6–11 Blöcke mit 281–445 Wörtern in 2,0–4,1 min, an der zweiten Sitzung 22–26 Blöcke mit 915–1165 Wörtern in 7,4–11,1 min.
  - Sprache ohne Wörter ab 2 s: 6–10 und 20–22 Blöcke.
  - Mit 5 Seeds nimmt `avg_logprob` 18–22 und 28–35 Blöcke an, in 4,9–8,6 und 9,7–13,1 min.

## `base` mit anderen `base`-Seeds

Seeds 1–3.

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | 122/21 · 4,3 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: Kompression unter 2,4 | – | – | 122/21 · 4,3 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: Kompression höchstens Median | – | – | 122/21 · 4,3 (0,0) | 10/156 · −11,6 (−21,2) | – | – | – | – | – |
| Quelle: avg_logprob über −1 | – | – | 122/21 · 4,3 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: avg_logprob mindestens Median | – | – | 122/21 · 4,3 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: no_speech_prob unter 0,6 | – | – | 122/21 · 4,3 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: no_speech_prob höchstens Median | – | – | 122/21 · 4,3 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: Wort-Confidence ab 0,5 | – | – | 122/21 · 4,3 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: Wort-Confidence mindestens Median | – | – | 94/10 · 3,4 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Quelle: kein Fallback | – | – | 122/21 · 4,3 (0,0) | 28/3 · 2,0 (0,0) | – | – | – | – | – |
| Quelle: keine Wiederholung | – | – | 122/21 · 4,3 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Hauptlauf: Lücke ab 2,5 s | – | – | 96/32 · 2,5 (0,0) | 61/170 · −8,2 (−21,2) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | 3/22 · −1,9 (−5,6) | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | – | – | – | 3/22 · −1,9 (−5,6) | – | – | – | – | – |
| Sprache ohne Wörter ab 2 s | – | – | 122/21 · 4,3 (0,0) | 10/74 · −5,5 (−11,1) | 28/3 · 2,5 (0,0) | – | – | – | – |
| in einem weiteren Lauf | – | – | 28/11 · 0,9 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |

- **`avg_logprob` und Wort-Confidence der Quelle trennen an D.** Die erfundenen Blöcke stammen dort aus Passagen, die der Decoder selbst schlecht bewertet hat. Beide Signale nehmen an C, D und E dieselben Blöcke an.
- **„Sprache ohne Wörter“ trennt hier nicht.** Es nimmt an D Blöcke mit 74 falschen und 10 richtigen Wörtern an. Wo ein Seed erfindet, hört die Diarisierung oft trotzdem Sprache, die der Hauptlauf nicht hat.
- **Die Lücke im Hauptlauf trennt auch nicht:** An D haben alle angebotenen Blöcke eine Lücke ab 2,5 s.
- **`no_speech_prob`, Kompression und Wiederholung sagen in dieser Paarung nichts.** Sie nehmen fast jeden Block an.
- **„Kein Fallback“ ist zu streng:** Es hält die erfundenen Blöcke an D fern, aber auch den richtigen an E.
- **Übereinstimmung mit drei Seeds** nimmt an C einen richtigen Block nicht an (0,9 statt 4,3 Punkte), wie in TOOL-102.

## Fünf Seeds

`base`, Seeds 1–5. Jeder Hauptlauf hat vier Quellen, „in einem weiteren Lauf“ heißt einer von drei übrigen.

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | 187/56 · 3,2 (0,0) | 170/294 · −4,8 (−16,5) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: Kompression unter 2,4 | – | – | 187/56 · 3,2 (0,0) | 170/294 · −4,8 (−16,5) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: Kompression höchstens Median | – | – | 187/56 · 3,2 (0,0) | 14/243 · −10,6 (−21,2) | 77/20 · 3,8 (0,0) | – | – | – | – |
| Quelle: avg_logprob über −1 | – | – | 187/56 · 3,2 (0,0) | 192/65 · 7,2 (0,0) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: avg_logprob mindestens Median | – | – | 187/56 · 3,2 (0,0) | 192/65 · 7,2 (0,0) | 76/17 · 4,0 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: no_speech_prob unter 0,6 | – | – | 187/56 · 3,2 (0,0) | 170/294 · −4,8 (−16,5) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: no_speech_prob höchstens Median | – | – | 187/56 · 3,2 (0,0) | 170/294 · −4,8 (−16,5) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: Wort-Confidence ab 0,5 | – | – | 187/56 · 3,2 (0,0) | 192/65 · 7,2 (0,0) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Quelle: Wort-Confidence mindestens Median | – | – | 159/45 · 2,6 (0,0) | 138/46 · 5,1 (0,0) | 50/5 · 2,7 (0,0) | 13/7 · 0,4 (0,0) | – | 45/26 · 0,9 (0,0) | – |
| Quelle: kein Fallback | – | – | 187/56 · 3,2 (0,0) | 165/56 · 6,2 (0,0) | 22/15 · 1,0 (0,0) | 13/7 · 0,4 (0,0) | – | 45/26 · 0,9 (0,0) | – |
| Quelle: keine Wiederholung | – | – | 187/56 · 3,2 (0,0) | 170/294 · −4,8 (−16,5) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Hauptlauf: Lücke ab 2,5 s | – | – | 174/59 · 3,1 (0,0) | 96/217 · −5,2 (−21,2) | 77/20 · 3,8 (0,0) | – | – | 45/26 · 0,9 (0,0) | – |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | 8/14 · −0,3 (−1,3) | 3/22 · −1,1 (−5,6) | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | – | – | 9/15 · −0,0 (−0,2) | 3/22 · −1,1 (−5,6) | – | – | – | – | – |
| Sprache ohne Wörter ab 2 s | – | – | 178/41 · 3,5 (0,0) | 110/91 · 1,8 (−10,0) | 77/20 · 3,8 (0,0) | – | – | – | – |
| in einem weiteren Lauf | – | – | 187/56 · 3,2 (0,0) | 192/65 · 7,2 (0,0) | 77/20 · 3,8 (0,0) | – | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| in zwei weiteren Läufen | – | – | 46/41 · 0,1 (−1,8) | 84/25 · 3,4 (0,0) | 77/20 · 3,8 (0,0) | – | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |

Je Hauptlauf an C, D und E:

| Referenz | Signal | Hauptlauf | Blöcke am Clip | Wörter | füllen eine Auslassung | sonst richtig | falsch | an unverständlicher Stelle | WER Hauptlauf | WER mit Blöcken | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C | alle Blöcke | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 27,3% | 27,3% | 0,0 |
| C | alle Blöcke | base#2 | 2 | 76 | 56 | 0 | 20 | 0 | 31,9% | 27,1% | 4,8 |
| C | alle Blöcke | base#3 | 2 | 91 | 66 | 9 | 16 | 0 | 33,3% | 25,6% | 7,7 |
| C | alle Blöcke | base#4 | 2 | 76 | 47 | 9 | 20 | 0 | 31,7% | 28,4% | 3,3 |
| C | alle Blöcke | base#5 | 0 | 0 | 0 | 0 | 0 | 0 | 25,5% | 25,5% | 0,0 |
| C | Quelle: avg_logprob über −1 | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 27,3% | 27,3% | 0,0 |
| C | Quelle: avg_logprob über −1 | base#2 | 2 | 76 | 56 | 0 | 20 | 0 | 31,9% | 27,1% | 4,8 |
| C | Quelle: avg_logprob über −1 | base#3 | 2 | 91 | 66 | 9 | 16 | 0 | 33,3% | 25,6% | 7,7 |
| C | Quelle: avg_logprob über −1 | base#4 | 2 | 76 | 47 | 9 | 20 | 0 | 31,7% | 28,4% | 3,3 |
| C | Quelle: avg_logprob über −1 | base#5 | 0 | 0 | 0 | 0 | 0 | 0 | 25,5% | 25,5% | 0,0 |
| C | Sprache ohne Wörter ab 2 s | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 27,3% | 27,3% | 0,0 |
| C | Sprache ohne Wörter ab 2 s | base#2 | 2 | 76 | 56 | 0 | 20 | 0 | 31,9% | 27,1% | 4,8 |
| C | Sprache ohne Wörter ab 2 s | base#3 | 2 | 91 | 66 | 9 | 16 | 0 | 33,3% | 25,6% | 7,7 |
| C | Sprache ohne Wörter ab 2 s | base#4 | 1 | 52 | 47 | 0 | 5 | 0 | 31,7% | 26,6% | 5,1 |
| C | Sprache ohne Wörter ab 2 s | base#5 | 0 | 0 | 0 | 0 | 0 | 0 | 25,5% | 25,5% | 0,0 |
| D | alle Blöcke | base#1 | 2 | 145 | 50 | 7 | 87 | 1 | 49,4% | 53,7% | −4,2 |
| D | alle Blöcke | base#2 | 2 | 112 | 39 | 15 | 57 | 1 | 52,6% | 53,0% | −0,4 |
| D | alle Blöcke | base#3 | 2 | 67 | 51 | 0 | 14 | 2 | 81,5% | 71,3% | 10,2 |
| D | alle Blöcke | base#4 | 2 | 60 | 1 | 3 | 56 | 0 | 38,1% | 51,0% | −12,9 |
| D | alle Blöcke | base#5 | 2 | 84 | 3 | 1 | 80 | 0 | 49,7% | 66,1% | −16,5 |
| D | Quelle: avg_logprob über −1 | base#1 | 1 | 75 | 50 | 4 | 20 | 1 | 49,4% | 38,1% | 11,4 |
| D | Quelle: avg_logprob über −1 | base#2 | 1 | 75 | 39 | 15 | 20 | 1 | 52,6% | 44,8% | 7,8 |
| D | Quelle: avg_logprob über −1 | base#3 | 2 | 67 | 51 | 0 | 14 | 2 | 81,5% | 71,3% | 10,2 |
| D | Quelle: avg_logprob über −1 | base#4 | 0 | 0 | 0 | 0 | 0 | 0 | 38,1% | 38,1% | 0,0 |
| D | Quelle: avg_logprob über −1 | base#5 | 1 | 46 | 33 | 0 | 11 | 2 | 49,7% | 43,0% | 6,7 |
| D | Sprache ohne Wörter ab 2 s | base#1 | 1 | 75 | 50 | 4 | 20 | 1 | 49,4% | 38,1% | 11,4 |
| D | Sprache ohne Wörter ab 2 s | base#2 | 1 | 75 | 39 | 15 | 20 | 1 | 52,6% | 44,8% | 7,8 |
| D | Sprache ohne Wörter ab 2 s | base#3 | 0 | 0 | 0 | 0 | 0 | 0 | 81,5% | 81,5% | 0,0 |
| D | Sprache ohne Wörter ab 2 s | base#4 | 0 | 0 | 0 | 0 | 0 | 0 | 38,1% | 38,1% | 0,0 |
| D | Sprache ohne Wörter ab 2 s | base#5 | 1 | 53 | 2 | 0 | 51 | 0 | 49,7% | 59,7% | −10,0 |
| E | alle Blöcke | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 29,8% | 29,8% | 0,0 |
| E | alle Blöcke | base#2 | 0 | 0 | 0 | 0 | 0 | 0 | 31,4% | 31,4% | 0,0 |
| E | alle Blöcke | base#3 | 1 | 36 | 32 | 0 | 4 | 0 | 40,7% | 32,2% | 8,4 |
| E | alle Blöcke | base#4 | 0 | 0 | 0 | 0 | 0 | 0 | 34,1% | 34,1% | 0,0 |
| E | alle Blöcke | base#5 | 1 | 61 | 44 | 1 | 16 | 0 | 43,6% | 32,8% | 10,8 |
| E | Quelle: avg_logprob über −1 | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 29,8% | 29,8% | 0,0 |
| E | Quelle: avg_logprob über −1 | base#2 | 0 | 0 | 0 | 0 | 0 | 0 | 31,4% | 31,4% | 0,0 |
| E | Quelle: avg_logprob über −1 | base#3 | 1 | 36 | 32 | 0 | 4 | 0 | 40,7% | 32,2% | 8,4 |
| E | Quelle: avg_logprob über −1 | base#4 | 0 | 0 | 0 | 0 | 0 | 0 | 34,1% | 34,1% | 0,0 |
| E | Quelle: avg_logprob über −1 | base#5 | 1 | 61 | 44 | 1 | 16 | 0 | 43,6% | 32,8% | 10,8 |
| E | Sprache ohne Wörter ab 2 s | base#1 | 0 | 0 | 0 | 0 | 0 | 0 | 29,8% | 29,8% | 0,0 |
| E | Sprache ohne Wörter ab 2 s | base#2 | 0 | 0 | 0 | 0 | 0 | 0 | 31,4% | 31,4% | 0,0 |
| E | Sprache ohne Wörter ab 2 s | base#3 | 1 | 36 | 32 | 0 | 4 | 0 | 40,7% | 32,2% | 8,4 |
| E | Sprache ohne Wörter ab 2 s | base#4 | 0 | 0 | 0 | 0 | 0 | 0 | 34,1% | 34,1% | 0,0 |
| E | Sprache ohne Wörter ab 2 s | base#5 | 1 | 61 | 44 | 1 | 16 | 0 | 43,6% | 32,8% | 10,8 |

- **Mehr Seeds finden mehr Verluste:** An D bekommen vier von fünf Hauptläufen einen richtigen Block, im Mittel 7,2 Punkte.
- **Mehr Seeds bringen auch mehr Erfundenes:** Ohne Signal sind an D 294 der 464 angebotenen Wörter falsch.
- **Übereinstimmung trägt mit fünf Seeds.** „In einem weiteren Lauf“ nimmt an allen Referenzen dieselben Blöcke an wie `avg_logprob`. „In zwei weiteren Läufen“ ist zu streng und verliert an C fast den ganzen Gewinn.
- **Kosten:** vier zusätzliche volle Läufe je Segment, rund 26 min, für im Mittel 3 bis 7 Punkte an den Stellen mit Blockverlust.

## `base+batched` mit `base` als Quelle

Quelle sind die `base`-Seeds 1–3.

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Kompression unter 2,4 | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Kompression höchstens Median | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 58/9 · 11,9 (11,9) | – |
| Quelle: avg_logprob über −1 | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: avg_logprob mindestens Median | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: no_speech_prob unter 0,6 | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: no_speech_prob höchstens Median | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Wort-Confidence ab 0,5 | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Wort-Confidence mindestens Median | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 42/6 · 7,0 (7,0) |
| Quelle: kein Fallback | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: keine Wiederholung | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Hauptlauf: Lücke ab 2,5 s | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 41/4 · 8,7 (8,7) | 38/20 · 6,0 (6,0) |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | – | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Sprache ohne Wörter ab 2 s | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| in einem weiteren Lauf | – | – | – | 1/20 · −3,8 (−3,8) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| in zwei weiteren Läufen | – | – | – | 1/20 · −3,8 (−3,8) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |

Mit fünf `base`-Seeds als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: Kompression unter 2,4 | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: Kompression höchstens Median | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 64/18 · 12,8 (12,8) | – |
| Quelle: avg_logprob über −1 | – | – | – | – | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: avg_logprob mindestens Median | – | – | – | – | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: no_speech_prob unter 0,6 | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: no_speech_prob höchstens Median | – | – | – | 1/59 · −12,5 (−12,5) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: Wort-Confidence ab 0,5 | – | – | – | – | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: Wort-Confidence mindestens Median | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 41/16 · 6,7 (6,7) |
| Quelle: kein Fallback | – | – | – | – | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Quelle: keine Wiederholung | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| Hauptlauf: Lücke ab 2,5 s | – | – | – | 0/22 · −4,9 (−4,9) | – | – | – | 41/4 · 8,7 (8,7) | 38/20 · 6,0 (6,0) |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | – | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Sprache ohne Wörter ab 2 s | – | – | – | – | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| in einem weiteren Lauf | – | – | – | 1/20 · −3,8 (−3,8) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |
| in zwei weiteren Läufen | – | – | – | 1/20 · −3,8 (−3,8) | – | – | – | 64/18 · 12,8 (12,8) | 38/20 · 6,0 (6,0) |

- **Der Gewinn liegt an H und I**, den Fenstern, an denen `base+batched` ein Stück verliert (TOOL-104). Das Orakel dort lag bei 15 und 8 Punkten.
- **An D bietet `base` einen erfundenen Block an.** Vier Signale nehmen ihn nicht an: `avg_logprob`, Wort-Confidence, „kein Fallback“ und „Sprache ohne Wörter“.
- **Übereinstimmung der `base`-Seeds hilft hier nicht:** Ein Block mit 20 falschen Wörtern steht an D in zwei weiteren Läufen.
- **An I sind 20 der 58 eingesetzten Wörter falsch.** Der Block füllt die Lücke, bringt aber Fehler mit.

## `base` mit `base+batched` als Quelle

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Quelle: Kompression unter 2,4 | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | – | – |
| Quelle: Kompression höchstens Median | – | – | 115/17 · 4,2 (0,0) | – | 21/1 · 2,0 (0,0) | – | – | – | – |
| Quelle: avg_logprob über −1 | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Quelle: avg_logprob mindestens Median | – | – | 90/6 · 3,3 (0,0) | 112/34 · 6,2 (0,0) | – | – | – | – | – |
| Quelle: no_speech_prob unter 0,6 | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Quelle: no_speech_prob höchstens Median | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Quelle: Wort-Confidence ab 0,5 | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Quelle: Wort-Confidence mindestens Median | – | – | 90/6 · 3,3 (0,0) | 112/34 · 6,2 (0,0) | – | – | – | – | – |
| Quelle: kein Fallback | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Quelle: keine Wiederholung | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | 24/4 · −2,4 (−7,1) | – | – |
| Hauptlauf: Lücke ab 2,5 s | – | – | 115/17 · 4,2 (0,0) | – | – | – | – | – | – |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | – | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | – | – | – | – | – | – | – | – | – |
| Sprache ohne Wörter ab 2 s | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | – | – |

- **„Sprache ohne Wörter“ trägt in dieser Richtung.** Es nimmt die Blöcke an C, D und E an und den an G nicht.
- **`avg_logprob` und Wort-Confidence der Batched-Quelle sagen nichts.** Sie gelten je Stück von bis zu 30 s und liegen bei jedem Angebot über der Schwelle.
- **Kompression unter 2,4 trennt hier**, anders als unter den `base`-Seeds: Der Block an G stammt aus einem Stück mit hoher Kompression.
- **Diese Richtung braucht nur einen zusätzlichen Lauf von unter 2 min.**

## `loud`

`loud` mit den anderen `loud`-Seeds: An keiner Referenz reicht ein Block ab 20 Wörtern in den Clip, die Tabelle wäre leer.

`loud+batched` mit `loud` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: Kompression unter 2,4 | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: Kompression höchstens Median | – | – | – | – | – | – | – | – | – |
| Quelle: avg_logprob über −1 | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: avg_logprob mindestens Median | – | – | – | – | – | – | – | – | – |
| Quelle: no_speech_prob unter 0,6 | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: no_speech_prob höchstens Median | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: Wort-Confidence ab 0,5 | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: Wort-Confidence mindestens Median | – | – | – | – | – | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: kein Fallback | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Quelle: keine Wiederholung | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Hauptlauf: Lücke ab 2,5 s | – | – | – | – | – | – | – | – | 43/48 · 1,3 (1,3) |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | – | – | – | – | – | – |
| Hauptlauf: dünnes Fenster | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Sprache ohne Wörter ab 2 s | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| in einem weiteren Lauf | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| in zwei weiteren Läufen | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |

`loud` mit `loud+batched` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | – | – | – | 0/288 · −26,3 (−26,3) | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: Kompression unter 2,4 | – | – | – | – | – | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: Kompression höchstens Median | – | – | – | – | – | – | – | – | – |
| Quelle: avg_logprob über −1 | – | – | – | – | 0/288 · −26,3 (−26,3) | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: avg_logprob mindestens Median | – | – | – | – | 0/288 · −26,3 (−26,3) | – | – | – | – |
| Quelle: no_speech_prob unter 0,6 | – | – | – | – | 0/288 · −26,3 (−26,3) | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: no_speech_prob höchstens Median | – | – | – | – | 0/288 · −26,3 (−26,3) | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: Wort-Confidence ab 0,5 | – | – | – | – | 0/288 · −26,3 (−26,3) | – | 18/40 · −0,7 (−1,1) | – | – |
| Quelle: Wort-Confidence mindestens Median | – | – | – | – | 0/288 · −26,3 (−26,3) | – | – | – | – |
| Quelle: kein Fallback | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Quelle: keine Wiederholung | – | – | – | – | – | – | – | – | – |
| Hauptlauf: Lücke ab 2,5 s | – | – | – | – | 0/288 · −26,3 (−26,3) | – | – | – | – |
| Hauptlauf: Wort vor der Lücke ab 1 s | – | – | – | – | – | – | 9/22 · −0,4 (−1,1) | – | – |
| Hauptlauf: dünnes Fenster | – | – | – | – | – | – | – | – | – |
| Sprache ohne Wörter ab 2 s | – | – | – | – | – | – | – | – | – |

- **Mit Pegelausgleich bleibt unter den Seeds an den Referenzen nichts zu holen.** Ob das am Pegelausgleich liegt oder daran, dass die Referenzen an `base`-Abweichungen ausgesucht sind, zeigt diese Messung nicht.
- **`loud+batched` entgleist an E** (TOOL-104). Als Hauptlauf bekommt es dort 11,4 Punkte aus `loud` zurück, als Quelle fügt es 288 falsche Wörter ein.
- **Als Quelle ist `loud+batched` nur mit einem Signal gegen Wiederholung brauchbar.** „Sprache ohne Wörter“ hält den Block an E ebenfalls fern.

## Blöcke ab 10 Wörtern

Nicht Teil der Go-Regel. Ohne die Zeilen mit Median und die Signale, die nichts annehmen.

`base` mit anderen `base`-Seeds, Seeds 1–3:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | 6/1 · 0,4 (0,0) | 0/34 · −2,6 (−3,9) | 136/60 · 2,4 (0,0) | 86/187 · −9,2 (−18,9) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 25/16 · −1,6 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Quelle: Kompression unter 2,4 | 6/1 · 0,4 (0,0) | 0/34 · −2,6 (−3,9) | 136/60 · 2,4 (0,0) | 86/187 · −9,2 (−18,9) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 25/16 · −1,6 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Quelle: avg_logprob über −1 | 6/1 · 0,4 (0,0) | – | 136/60 · 2,4 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 25/16 · −1,6 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Quelle: Wort-Confidence ab 0,5 | 6/1 · 0,4 (0,0) | – | 136/60 · 2,4 (0,0) | 76/14 · 5,0 (2,2) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 25/16 · −1,6 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Quelle: kein Fallback | 6/1 · 0,4 (0,0) | – | 134/38 · 3,2 (0,0) | 28/3 · 2,0 (0,0) | – | 11/7 · 0,6 (0,0) | 15/13 · −1,5 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Quelle: keine Wiederholung | 6/1 · 0,4 (0,0) | 0/34 · −2,6 (−3,9) | 134/38 · 3,2 (0,0) | 86/187 · −9,2 (−18,9) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 24/5 · −0,8 (−2,4) | 10/1 · 0,7 (0,0) | – |
| Hauptlauf: Lücke ab 2,5 s | 6/1 · 0,4 (0,0) | – | 106/57 · 2,3 (0,0) | 72/170 · −6,7 (−21,2) | 28/3 · 2,5 (0,0) | – | – | 10/1 · 0,7 (0,0) | – |
| Sprache ohne Wörter ab 2 s | 6/1 · 0,4 (0,0) | – | 132/31 · 3,9 (0,0) | 21/74 · −4,0 (−11,1) | 28/3 · 2,5 (0,0) | – | – | 10/1 · 0,7 (0,0) | – |
| in einem weiteren Lauf | 6/1 · 0,4 (0,0) | – | 35/23 · −0,0 (−2,8) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | 11/7 · 0,6 (0,0) | 24/5 · −0,8 (−2,4) | 10/1 · 0,7 (0,0) | – |

`base+batched` mit `base` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | – | 0/17 · −3,9 (−3,9) | 1/11 · −1,1 (−1,1) | 1/78 · −16,7 (−16,7) | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Kompression unter 2,4 | – | 0/17 · −3,9 (−3,9) | 1/11 · −1,1 (−1,1) | 1/78 · −16,7 (−16,7) | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: avg_logprob über −1 | – | – | 1/11 · −1,1 (−1,1) | – | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: Wort-Confidence ab 0,5 | – | – | 1/11 · −1,1 (−1,1) | – | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: kein Fallback | – | – | – | – | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Quelle: keine Wiederholung | – | 0/17 · −3,9 (−3,9) | – | 0/41 · −9,1 (−9,1) | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Hauptlauf: Lücke ab 2,5 s | – | 0/17 · −3,9 (−3,9) | – | 0/41 · −9,1 (−9,1) | – | – | – | 41/4 · 8,7 (8,7) | 38/20 · 6,0 (6,0) |
| Sprache ohne Wörter ab 2 s | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| in einem weiteren Lauf | – | – | – | 1/20 · −3,8 (−3,8) | – | 6/4 · 0,9 (0,9) | 3/15 · 0,2 (0,2) | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| in zwei weiteren Läufen | – | – | – | 1/20 · −3,8 (−3,8) | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |

`base` mit `base+batched` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alle Blöcke | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 125/37 · 7,5 (3,8) | 26/3 · 2,4 (0,0) | – | 39/16 · −3,9 (−7,1) | 13/2 · 0,9 (0,0) | – |
| Quelle: Kompression unter 2,4 | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 125/37 · 7,5 (3,8) | 26/3 · 2,4 (0,0) | – | – | 13/2 · 0,9 (0,0) | – |
| Quelle: avg_logprob über −1 | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 125/37 · 7,5 (3,8) | 26/3 · 2,4 (0,0) | – | 39/16 · −3,9 (−7,1) | 13/2 · 0,9 (0,0) | – |
| Quelle: Wort-Confidence ab 0,5 | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 125/37 · 7,5 (3,8) | 26/3 · 2,4 (0,0) | – | 39/16 · −3,9 (−7,1) | 13/2 · 0,9 (0,0) | – |
| Quelle: kein Fallback | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt | entfällt |
| Quelle: keine Wiederholung | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 125/37 · 7,5 (3,8) | 26/3 · 2,4 (0,0) | – | 39/16 · −3,9 (−7,1) | 13/2 · 0,9 (0,0) | – |
| Hauptlauf: Lücke ab 2,5 s | 6/2 · 0,4 (0,0) | – | 115/17 · 4,2 (0,0) | 13/3 · 1,3 (0,0) | 5/2 · 0,5 (0,0) | – | – | 13/2 · 0,9 (0,0) | – |
| Sprache ohne Wörter ab 2 s | 6/2 · 0,4 (0,0) | – | 119/30 · 4,1 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | 13/2 · 0,9 (0,0) | – |

- **Kleinere Blöcke sind öfter falsch.** An B sind unter den `base`-Seeds alle 34 Wörter falsch, an G kommen Verluste bis 2,4 Punkte dazu.
- **`avg_logprob` hält an B und D weiter stand, an G nicht mehr.**
- **Die Schwelle von 20 Wörtern bleibt.**

## Regeln

Drei Regeln, festgeschrieben nach der Messung je Signal an A bis I und bevor die zwei neuen Fenster abgetippt sind. Die Schwellen sind die der Pipeline. In `blocks.py` stehen sie als `rule_tests`, der Aufruf mit `--rules` zählt nur sie.

| Regel | nimmt einen Block ab 20 Wörtern an, wenn |
| --- | --- |
| A, Dekodierwerte der Quelle | der niedrigste `avg_logprob` seiner Passagen über −1 liegt, die höchste `compression_ratio` unter 2,4 und sein Wiederholungsanteil 0 ist |
| B, Sprache ohne Wörter | die Diarisierung im Block mindestens 2 s Sprache hört, an der der Hauptlauf kein Wort hat (Kandidat aus TOOL-104) |
| C | A und B zugleich gelten |

- **Warum A drei Signale verbindet:** `avg_logprob` trennt, wenn die Quelle ein `base`- oder `loud`-Lauf ist. Kompression und Wiederholung trennen, wenn die Quelle ein Batched-Lauf ist, dessen `avg_logprob` nichts sagt.
- **Übereinstimmung mit weiteren Läufen ist keine Regel geworden.** Sie trägt erst mit fünf Seeds und nimmt mit `base+batched` als Hauptlauf an D einen erfundenen Block an.

`base` mit anderen `base`-Seeds, Seeds 1–3:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regel A: Dekodierwerte der Quelle | – | – | 122/21 · 4,3 (0,0) | 51/14 · 3,4 (0,0) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Regel B: Sprache ohne Wörter | – | – | 122/21 · 4,3 (0,0) | 10/74 · −5,5 (−11,1) | 28/3 · 2,5 (0,0) | – | – | – | – |
| Regel C: A und B | – | – | 122/21 · 4,3 (0,0) | – | 28/3 · 2,5 (0,0) | – | – | – | – |

`base` mit anderen `base`-Seeds, Seeds 1–5:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regel A: Dekodierwerte der Quelle | – | – | 187/56 · 3,2 (0,0) | 192/65 · 7,2 (0,0) | 77/20 · 3,8 (0,0) | 13/7 · 0,4 (0,0) | 21/1 · 0,8 (0,0) | 45/26 · 0,9 (0,0) | – |
| Regel B: Sprache ohne Wörter | – | – | 178/41 · 3,5 (0,0) | 110/91 · 1,8 (−10,0) | 77/20 · 3,8 (0,0) | – | – | – | – |
| Regel C: A und B | – | – | 178/41 · 3,5 (0,0) | 141/51 · 5,2 (0,0) | 77/20 · 3,8 (0,0) | – | – | – | – |

`base+batched` mit `base` als Quelle, Seeds 1–3:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regel A: Dekodierwerte der Quelle | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Regel B: Sprache ohne Wörter | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |
| Regel C: A und B | – | – | – | – | – | – | – | 58/9 · 11,9 (11,9) | 38/20 · 6,0 (6,0) |

`base` mit `base+batched` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regel A: Dekodierwerte der Quelle | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | – | – |
| Regel B: Sprache ohne Wörter | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | – | – |
| Regel C: A und B | – | – | 115/17 · 4,2 (0,0) | 112/34 · 6,2 (0,0) | 21/1 · 2,0 (0,0) | – | – | – | – |

`loud+batched` mit `loud` als Quelle:

| Signal | A | B | C | D | E | F | G | H | I |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Regel A: Dekodierwerte der Quelle | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Regel B: Sprache ohne Wörter | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |
| Regel C: A und B | – | – | – | – | 57/21 · 11,4 (11,4) | – | – | – | 43/48 · 1,3 (1,3) |

Unter den `loud`-Seeds und mit `loud+batched` als Quelle nimmt keine Regel einen Block an, der in eine Referenz reicht. Die 288 falschen Wörter an E bleiben draußen.

Über das Segment nimmt Regel A an (Blöcke / Wörter / Zeit in min, Spanne über die Hauptläufe):

| Paarung | Pilotsitzung | zweite Sitzung | zusätzliche Läufe |
| --- | --- | --- | --- |
| `base` ← `base`, 3 Seeds | 6–10 / 281–410 / 2,0–3,4 | 21–26 / 881–1165 / 7,2–11,1 | zwei volle Läufe, rund 13 min je Segment |
| `base` ← `base`, 5 Seeds | 16–21 / 627–1064 / 4,7–8,5 | 26–33 / 1132–1490 / 9,3–12,9 | vier volle Läufe, rund 26 min |
| `base+batched` ← `base` | 15 / 749 / 6,2 | 10 / 429 / 2,9 | ein voller Lauf, rund 6,5 min |
| `base` ← `base+batched` | 14–16 / 548–642 / 5,1–5,6 | 25–28 / 1100–1199 / 8,8–10,9 | ein Batched-Lauf, unter 2 min |

### Vorläufiger Stand gegen die Go-Regel

Go nur, wenn eine Regel an mindestens zwei Referenzen 3 Punkte WER gegenüber dem Mittel der Hauptläufe bringt und an keiner mehr als 1 Punkt verliert. F und I zählen zusammen als eine Referenz. Die Regel gilt für die `base`-Paarungen.

| Paarung | Regel A | Regel B | Regel C |
| --- | --- | --- | --- |
| `base` ← `base`, 3 Seeds | erfüllt: C 4,3 und D 3,4, kein Verlust | verfehlt: D −5,5 | verfehlt: nur C mit 4,3, E 2,5, an D kein Block |
| `base` ← `base`, 5 Seeds | erfüllt: C 3,2, D 7,2, E 3,8, kein Verlust | im Mittel erfüllt (C 3,5, E 3,8, D 1,8), aber ein Hauptlauf verliert an D 10,0 Punkte | erfüllt: C 3,5, D 5,2, E 3,8, kein Verlust |
| `base+batched` ← `base` | erfüllt: H 11,9 und I 6,0 | erfüllt, dieselben Blöcke | erfüllt, dieselben Blöcke |
| `base` ← `base+batched` | erfüllt: C 4,2 und D 6,2 | erfüllt, dieselben Blöcke | erfüllt, dieselben Blöcke |

- **Regel A erfüllt die Go-Regel in allen drei `base`-Paarungen**, Regel B nur über zwei Pipelines hinweg.
- **An `loud` ist die Go-Regel nicht erreicht:** Unter den Seeds gibt es an den Referenzen nichts zu gewinnen und nichts zu verlieren. `loud+batched` mit `loud` als Quelle gewinnt nur an E 11,4 Punkte und an I 1,3.
- **Das ist ein Stand an den Fenstern, an denen die Regeln gebildet wurden.** Die Entscheidung fällt nach der Messung an den zwei neuen Fenstern der zweiten Sitzung.

## Einschränkungen

- **Wenige Blöcke je Referenz.** Mit fünf Seeds reichen unter `avg_logprob` 6 angenommene Blöcke in C, 5 in D und 2 in E, über alle fünf Hauptläufe. Ein einzelner Block entscheidet über mehrere Punkte.
- **Die Schwellen sind die der Pipeline und nicht an diesen Fenstern gewählt.** Welche Signale in eine Regel kommen, wird aber an diesen Fenstern entschieden. Die zwei neuen Fenster der zweiten Sitzung prüfen die Regeln unabhängig.
- **D ist nach der Abweichung der Seeds 1–3 ausgesucht.** Dort treffen Verlust und Erfindung zusammen, das Fenster ist kein Durchschnitt.
- **F und I teilen eine Minute** und zählen für die Go-Regel zusammen als eine Referenz.
- **Die gespeicherten Läufe sind ohne Diarisierung transkribiert.** „Sprache ohne Wörter“ nutzt die Diarisierung der Sitzung auf dem Roh-WAV, auch für `loud`.
