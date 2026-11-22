# TOOL-81 — Hotwords und Wortverlust auf langen Aufnahmen

Stand 2026-11-22. Spike-Bericht zu [TOOL-81](../plans/TOOL-81-hotwords.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py). Alle Läufe liefen lokal. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Begriffe, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

**Ursache: Eine kurze Hotword-Liste lässt Whisper turbo systematisch Sprache auslassen. Die Pipeline behält die volle Liste und schaltet die Hotwords unter 110 Tokens ab.**

- **Die Länge des Prompts entscheidet.** Die ersten 9 Begriffe der vollen Liste (`kw9`, 51 Tokens) verlieren genauso viele Wörter wie die 9 `pc`-Hotwords aus TOOL-35 (`pchw`). Beide Varianten sind Lauf für Lauf identisch. Auf der Pilotsitzung haben 16–19 von 61 Abschnitten à 5 min ein Defizit, auf der zweiten Sitzung 25 von 58. Ab 20 Begriffen (110 Tokens) gibt es keinen systematischen Verlust mehr.
- **Der Inhalt wirkt mit, entscheidet aber nicht.** 9 Alltagswörter (`neutral9`, 15 Tokens) verlieren ebenfalls Wörter, nur weniger (9–11 Abschnitte).
- **Fallback und Auslassung gehören zusammen.** Mit kurzer Liste fällt der Decoder in 46–49 % der 30-s-Fenster auf eine höhere Temperatur zurück, mit voller Liste in 9–11 %. In Abschnitten mit Defizit liegt der Anteil bei 58–68 %. Der Fallback ist aber die Rettung, nicht die Ursache: Ohne ihn (`+temp0`) wird es schlimmer, mit 45 Abschnitten Defizit und 28 % Wiederholung.
- **Die Seed-Streuung kommt aus dem Fallback.** Nur beim Fallback wird gesampelt. Mit `+temp0` sind alle Seeds identisch, dafür steigt die WER deutlich.
- **Ohne Hotwords zerfallen die Passagen, weil der Prompt fehlt.** Ohne Hotwords bekommt der Decoder gar keinen Prompt (`condition_on_previous_text: false`). Er schreibt dann 6,8 Segmente pro Fenster statt 1,7, mit einem Median von 2,4 s statt 25 s. Ein voller Prompt aus Alltagswörtern (`neutral`) hält die Passagen lang. Der Inhalt des Prompts ist dafür also nicht nötig, seine Länge schon.
- **VAD ist nicht die Ursache.** `pchw+novad` verliert ebenso viele Wörter wie `pchw`.
- **Auffüllen hilft nicht.** Eine kurze Liste, die mit Alltagswörtern bis zum Budget ergänzt wird (`+fill`), ist schlechter als jede reine Liste.

## Material und Methode

| | |
| --- | --- |
| Aufnahme 1 | Segment 1 der Pilotsitzung, 5:00:00, mit Handreferenz A (0:00:00–0:04:06) und B (1:20:00–1:23:00) |
| Aufnahme 2 | Segment 1 einer zweiten Sitzung derselben Gruppe, 58 Abschnitte à 5 min, ohne Referenz |
| Pipeline | `transcript transcribe --no-diarize`; faster-whisper 1.2.1, large-v3-turbo (Revision `0a363e9161cb`) |
| Wiederholungen | Seeds 1–3 je Variante; auf Aufnahme 2 `nohw`, `kw9` und `neutral` nur Seed 1 |

Das Werkzeug ist dasselbe wie in TOOL-93: eine eigene Wurzel je Variante und Seed, der Seed fest über `ctranslate2.set_random_seed`. Seed und Keyword-Änderung stehen in `asr.settings`, und `score`, `sections` und `decode` prüfen sie gegen die Variante. Neu sind:

- `sections` zählt die Wörter je 5 min nach dem Wortbeginn und vergleicht sie mit `nohw` Seed 1. Ein Abschnitt hat ein **Defizit**, wenn ihm mindestens 20 % und mindestens 30 Wörter fehlen. `nohw` ist dabei keine Wahrheit, sondern der Lauf ohne Prompt, also ohne den untersuchten Effekt.
- `decode` liest die Rohform und zählt pro 30-s-Fenster (`seek`), ob ein Fallback lief (`temperature > 0`), wie viele Segmente es gab und welche Kompressionsrate. Ein Fenster gilt als **dünn**, wenn es weniger als 0,5 Wörter pro Sekunde des Fensters ergibt.
- Die Token-Zahlen der Listen stammen aus dem Whisper-Tokenizer, gezählt wie in `fit_hotwords`.

Die Werte für `base` weichen von TOOL-93 ab (dort 24,0 / 36,1 % WER). Die Transkripte sind dieselben, die Wortzahl ist identisch. Geändert hat sich also die Zählung gegen die Referenzen, nicht die Erkennung. Verglichen wird in diesem Bericht nur innerhalb desselben Stands.

### Varianten

| Variante | Liste | Tokens | prüft |
| --- | --- | --- | --- |
| `base` | volle Snapshot-Liste, 48 Begriffe | 221 von 223 | Bezug, heutiger Default |
| `pchw` | nur die `pc`-Einträge, 9 Begriffe, eigener Snapshot | 51 | Lauf aus TOOL-35 |
| `kw9`, `kw20`, `kw30` | die ersten N der vollen Liste | 51 / 110 / 161 | Länge |
| `neutral9` | 9 feste Alltagswörter | 15 | Inhalt |
| `neutral` | Alltagswörter bis zum Budget, 105 | 191 | Prompt ohne Inhalt |
| `nohw` | keine | 0 | Bezug ohne Prompt |
| `+temp0` | Temperatur nur 0, kein Fallback | – | Fallback, Seed |
| `+novad` | ohne VAD | – | VAD |
| `+fill` | Liste mit Alltagswörtern bis zum Budget ergänzt | ~223 | Auffüllen als Schutz |
| `+guard` | Schutz der Pipeline an: unter 110 Tokens keine Hotwords | – | Abnahme |

## Stufe 1: Wortverlust

### Abschnitte (Aufnahme 1, 61 Abschnitte)

| Variante | Wörter (Mittel) | Abschnitte mit Defizit je Seed | fehlende Wörter darin | größtes Defizit |
| --- | --- | --- | --- | --- |
| `nohw` | 32704 | 0 / 0 / 0 | – | – |
| `base` | 33068 | 0 / 0 / 0 | – | – |
| `kw30` | 32715 | 0 / 0 / 0 | – | – |
| `kw20` | 32224 | 0 / 0 / 0 | – | – |
| `neutral` | 32831 | 1 / 1 / 0 | 105–125 | 20,3 % |
| `neutral9` | 29293 | 9 / 11 / 11 | 1315–1617 | 34,1 % |
| `kw9` = `pchw` | 28000 | 19 / 19 / 16 | 2950–3206 | 51,5 % |
| `pchw+novad` | 27920 | 18 / 13 / 16 | 2408–3384 | 51,7 % |
| `pchw+temp0` | 20585 | 45 (alle Seeds gleich) | 11152 | 77,6 % |
| `base+temp0` | 33189 | 0 (alle Seeds gleich) | – | – |
| `kw9+fill` | 30922 | 8 / 4 / 2 | 283–1057 | 33,9 % |
| `kw20+fill` | 30735 | 5 / 11 / 4 | 557–1366 | 36,3 % |
| `base+fill` | wie `base` | 0 / 0 / 0 | – | – |

`base+fill` ist Lauf für Lauf identisch mit `base`, weil die 48 Begriffe das Budget schon füllen und kein Alltagswort mehr dazukommt.

### Fenster-Diagnose (Aufnahme 1)

| Variante | Fenster mit Fallback | Fallback im Defizit / sonst | Segmente je Fenster | Segmentlänge Median | dünne Fenster | Kompression über 2,4 |
| --- | --- | --- | --- | --- | --- | --- |
| `nohw` | 0 % | – / 0 % | 6,8 | 2,4 s | 0 | 0 |
| `base` | 9,3–10,8 % | – / 9–11 % | 1,7–1,8 | 13–26 s | 6–11 | 0–1 |
| `kw30` | 2,8–5,0 % | – / 3–5 % | 2,9–3,0 | 4,7–5,3 s | 3–5 | 0–2 |
| `kw20` | 7,7–9,4 % | – / 8–9 % | 2,3–2,4 | 6,8–7,3 s | 6 | 0–1 |
| `neutral` | 14,2–15,8 % | 38–44 % / 14–16 % | 2,0–2,2 | 6,3–8,9 s | 7–11 | 1 |
| `neutral9` | 8,2–10,3 % | 10–14 % / 7–9 % | 4,2–4,4 | 3,4–3,7 s | 32–43 | 0–1 |
| `kw9` = `pchw` | 45,8–49,2 % | 58–68 % / 40–41 % | 3,1–3,3 | 4,2–4,5 s | 52–59 | 8–17 |
| `pchw+novad` | 48,8–52,1 % | 62–66 % / 44–49 % | 2,9–3,1 | 3,3–3,6 s | 81–86 | 9–15 |
| `pchw+temp0` | 0 % | – | 1,9 | 10,7 s | 102 | 257 |
| `base+temp0` | 0 % | – | 1,5 | 28,2 s | 7 | 51 |
| `kw9+fill` | 24,3–26,3 % | 21–32 % / 24–27 % | 1,7–1,9 | 10,8–16,8 s | 21–35 | 0–1 |
| `kw20+fill` | 32,1–35,3 % | 28–42 % / 32–34 % | 2,1–2,2 | 5,2–6,1 s | 23–33 | 1–2 |

Mit kurzer Liste kippt fast jedes zweite Fenster in den Fallback, und dort liegen die Defizite. Ohne Fallback (`pchw+temp0`) bleibt der Decoder in Schleifen hängen: 257 Fenster über der Kompressionsschwelle, 102 dünne Fenster. Der Fallback rettet also einen Teil der Fenster, deckt das Problem aber nicht ganz.

### Zwischenbewertung

| Hypothese | Ergebnis |
| --- | --- |
| Länge der Liste | **belegt**: Unter etwa 110 Tokens verliert die Liste systematisch Wörter, ab 110 Tokens nicht mehr |
| Inhalt der Liste | **teilweise**: Bei gleicher Begriffszahl verlieren 9 Alltagswörter weniger als 9 Namen, aber ebenfalls deutlich |
| Temperatur-Fallback als Ursache | **widerlegt**: Der Fallback begleitet den Verlust und mildert ihn, ohne ihn wird es schlimmer |
| VAD | **widerlegt**: `pchw+novad` verliert gleich viel |
| Auffüllen als Schutz | **widerlegt**: gemischte Listen sind schlechter als die reine kurze Liste |

## Stufe 2: Seed-Streuung

Wortlaut an den Referenzen (Aufnahme 1), Mittel und Spanne über drei Seeds, dazu die Fehler, die in `confident`-Passagen liegen („übersehen“):

| Variante | WER A | WER B | übersehen A je Seed | übersehen B je Seed | Wiederholung |
| --- | --- | --- | --- | --- | --- |
| `base` | **21,3 %** (21,3–21,3) | 29,8 % (25,6–35,4) | 0 / 0 / 0 | 0 / 4 / 0 | 0,7 % |
| `kw30` | **21,1 %** (21,1–21,1) | **27,7 %** (27,7–27,7) | 60 / 60 / 60 | 11 / 11 / 11 | 0,4 % |
| `kw20` | 23,7 % (22,6–25,8) | 35,0 % (29,0–39,0) | 13 / 26 / 23 | 12 / 12 / 12 | 0,3 % |
| `neutral` | 24,2 % (23,9–24,7) | 35,4 % (31,1–43,1) | 0 / 0 / 0 | 8 / 0 / 0 | 0,8 % |
| `nohw` | 26,0 % (26,0–26,0) | 28,1 % (28,1–28,1) | 100 | 65 | 0,3 % |
| `base+temp0` | 29,8 % (alle gleich) | 40,8 % | 0 | 4 | 8,9 % |
| `neutral9` | 33,3 % (32,0–33,9) | 46,5 % (44,7–47,8) | 71 / 78 / 71 | 14 / 14 / 14 | 2,1 % |
| `kw9` = `pchw` | 33,3 % (23,5–46,0) | 83,1 % (70,7–89,6) | 38 / 26 / 34 | 2 / 0 / 7 | 3,3 % |
| `pchw+novad` | 34,8 % (30,5–40,3) | 76,8 % (66,9–84,8) | 30 / 26 / 32 | 13 / 0 / 0 | 3,0 % |
| `kw20+fill` | 34,6 % (31,3–40,9) | 58,4 % (43,5–69,6) | 19 / 19 / 19 | 8 / 0 / 0 | 2,0 % |
| `pchw+temp0` | 48,0 % (alle gleich) | 117,5 % | 26 | 0 | 28,1 % |
| `kw9+fill` | 60,9 % (47,8–81,5) | 42,4 % (29,7–54,6) | 34 / 0 / 34 | 0 / 0 / 0 | 1,6 % |

Laufzeit: `kw9`/`pchw` brauchen 2,5–2,7 min ASR pro Stunde Audio, `base` 1,3, `nohw` 1,1. Den doppelten Aufwand verursacht der Fallback.

**Zwischenbewertung:** Die Streuung zwischen den Seeds entsteht im Fallback: Mit `+temp0` verschwindet sie ganz, aber auf Kosten der WER (`base+temp0` +8,5 / +11,0 Punkte) und mit 9 % Wiederholung. Weniger Fallback heißt weniger Streuung. `kw30` hat mit 3–5 % Fallback-Fenstern keine Spanne mehr an A und B. Den Seed abzuschaffen ist deshalb kein Ziel. Die Streuung verschwindet, wenn die Lage nicht mehr kippt.

## Stufe 3: Zerfallen in kurze Passagen

`nohw` schreibt 2600 `confident`-Passagen, `base` 114–142. Pro Fenster entstehen 6,8 Segmente mit 2,4 s Median-Länge. Die Bewertung stuft solche kurzen Passagen oft als sicher ein und übersieht dann 100 / 65 Fehler. Der Grund ist der fehlende Prompt: Ohne Hotwords und ohne `condition_on_previous_text` steht vor dem Decoder gar kein Kontext.

- `neutral`, ein voller Prompt ohne jeden Bezug zur Sitzung, hält die Passagen fast so lang wie `base` und übersieht 0 / 0–8 Fehler. Es kommt also auf die Länge des Prompts an, nicht auf seinen Inhalt.
- Die Zahl der übersehenen Fehler fällt mit der Prompt-Länge: 100 bei 0 Tokens, 60 bei 161 (`kw30`), 0 bei 221 (`base`). `kw20` liegt mit 13–26 aus der Reihe. Die Schwellen der Bewertung sind auf `base` kalibriert, deshalb ist dieser Teil der Folge eine Frage der Kalibrierung (Chunk 4).

**Zwischenbewertung:** belegt. Der Prompt hält die Segmentierung zusammen, schon ein Prompt aus Alltagswörtern genügt. Das betrifft aber nur den Fall ohne Hotwords. Die Pipeline schaltet sie künftig nur unter der Schwelle ab, also bei einer Liste, die ohnehin Wörter verlieren würde.

## Stufe 4: zweite Aufnahme

Aufnahme 2, 58 Abschnitte, Vergleich gegen `nohw` Seed 1 (29100 Wörter):

| Variante | Tokens | Abschnitte mit Defizit je Seed | fehlende Wörter darin | größtes Defizit | Wörter | Fallback im Defizit / sonst |
| --- | --- | --- | --- | --- | --- | --- |
| `base` | 221 | 3 / 3 / 2 | 276–337 | 31,5 % | 28973–29006 | 26–33 % / 12–13 % |
| `kw30` | 161 | 0 / 0 / 1 | 0–92 | 26,8 % | 29192–29328 | 40 % / 7–8 % |
| `kw20` | 110 | 0 / 2 / 1 | 0–263 | 26,6 % | 28382–28687 | 11–25 % / 14–15 % |
| `neutral` | 191 | 3 (Seed 1) | 408 | 23,4 % | 28508 | 30 % / 21 % |
| `kw9` | 51 | 25 (Seed 1) | 4271 | 58,6 % | 23734 | 63 % / 39 % |

Die kurze Liste verliert auch hier systematisch Wörter, 18 % des Segments. Bei voller Liste gibt es je Seed 2–3 einzelne Abschnitte mit 23–31 % Defizit, jedes Mal an anderer Stelle. Die Gesamtwortzahl liegt gleichauf mit `nohw` (−0,4 %). Der Mechanismus ist derselbe, gehäufter Fallback im Abschnitt, aber er wirkt schwach und vereinzelt, und er hängt vom Seed ab. Ob dort wirklich Sprache fehlt oder ob `nohw` mehr schreibt, als gesagt wurde, lässt sich ohne Referenz nicht entscheiden.

## Entscheidung

Die vorab vereinbarte Auswahlregel lässt **keinen Gewinner zu**, wenn man sie streng anwendet. Auf Aufnahme 1 erfüllen nur `base` und `base+temp0` beide Bedingungen: kein Abschnitt mit Defizit und höchstens so viele übersehene Fehler wie `base`. Davon hat `base` die niedrigere WER, 25,6 % im Mittel gegenüber 35,3 %. Auf Aufnahme 2 hat aber auch `base` einzelne Abschnitte über der Schwelle.

Entschieden am 2026-11-22 (Projektverantwortung):

1. **Default bleibt die volle Liste (`base`).** Die vereinzelten, seed-abhängigen Abschnitte gelten als Rauschen. Für AC 2 gilt ein Wortverlust als **systematisch** ab 5 Abschnitten mit Defizit oder ab 5 % weniger Wörtern im Segment. `base` liegt auf beiden Aufnahmen darunter (0 bzw. 2–3 Abschnitte, Wörter +1,1 % bzw. −0,4 %). `kw9` liegt klar darüber (16–25 Abschnitte, −14 % bzw. −18 %).
2. **Schutz: Unter 110 Tokens gehen keine Hotwords an Whisper.** 110 Tokens ist die kürzeste gemessene Länge ohne systematischen Verlust, auf beiden Aufnahmen. Zwischen 51 und 110 Tokens ist nicht gemessen, die Schwelle ist bewusst vorsichtig gewählt. Unter der Schwelle verhält sich die Pipeline wie `nohw`: kein Wortverlust, aber kurze Passagen. Die Abschaltung meldet sie einmal, nur mit Zahlen. Kommen mehr Begriffe dazu, entsteht ein neuer Snapshot, und `transcribe` transkribiert automatisch neu.
3. **`asr.hotwords: true|false`** schaltet das Biasing ganz ab (Default `true`).
4. **Kein `+temp0`, kein neutraler Prompt, kein Auffüllen.** Keine dieser Einstellungen ist an beiden Referenzen besser als `base`.

Narrata soll den Füllstand schon beim Pflegen der Begriffe anzeigen, als Schätzung über die Zeichenzahl ([IOA-1336](https://alethe1a.atlassian.net/browse/IOA-1336)). Gemessen wurden 2,5–3,1 Zeichen pro Token bei Namen und 3,5 bei Alltagswörtern. Ab etwa 350 Zeichen liegt eine Liste sicher über der Schwelle.

## Abnahme

Die Läufe nutzen den Stand der Pipeline mit Schalter und Schutz (Chunk 3) und die Default-Config. Das Spike-Werkzeug setzt dabei nur den Seed. Der neue Modifikator `+guard` lässt den Schutz an, sonst schaltet ihn das Werkzeug für seine Varianten ab. `base+guard` ist also die Pipeline, wie sie ausgeliefert wird. `kw9+guard` gibt ihr eine echte kurze Liste. `transcript keywords` meldet vor den Läufen auf beiden Aufnahmen 48 von 86 Begriffen mit 221 Tokens, also über der Schwelle.

| Lauf | Aufnahme | Wörter | Abschnitte mit Defizit gegen `nohw` | WER A / B | übersehen A / B |
| --- | --- | --- | --- | --- | --- |
| `base+guard` Seed 1 / 2 / 3 | 1 | 33125 / 33100 / 32978 | 0 / 0 / 0 | 21,3 % / 25,6–35,4 % | 0 / 0–4 |
| `kw9+guard` Seed 1 | 1 | 32704 | 0 | 26,0 % / 28,1 % | 100 / 65 |
| `base+guard` Seed 1 | 2 | 29006 | 3 (337 Wörter, größtes 31,5 %) | – | – |
| `kw9+guard` Seed 1 | 2 | 29100 | 0 | – | – |

- **Default:** `base+guard` ist auf beiden Aufnahmen Lauf für Lauf wortgleich mit `base`: dieselben Wortzahlen, dieselben Fehler an A und B, dieselben Abschnitte. Schalter und Schutz ändern bei voller Liste also nichts an der Erkennung, nur die Einstellungen im Transkript. AC 2 ist erfüllt: Aufnahme 1 hat keinen Abschnitt mit Defizit. Aufnahme 2 hat die 3 vereinzelten Abschnitte aus Stufe 4 und bleibt damit unter der Grenze für einen systematischen Verlust.
- **Schutz:** Mit 9 Begriffen (51 Tokens) meldet `transcribe` einmal `hotwords off: 9 of 9 keyword(s) fit, 51 hotword token(s), under the 110 …`, und `keywords_used` bleibt leer. Das Ergebnis ist auf beiden Aufnahmen wortgleich mit `nohw` und hat keinen Abschnitt mit Defizit. Ohne Schutz verliert dieselbe Liste 19 bzw. 25 Abschnitte (`kw9`, 28121 bzw. 23734 Wörter).
- **Kalibrierung:** `transcript calibrate` auf `base+guard` Seed 1 ergibt an A 21,3 % WER mit 0 übersehenen Fehlern und 0 Fehlalarmen, Confidence-AUC 0,78. An B sind es 25,6 % mit 0 übersehenen Fehlern und 0 Fehlalarmen, AUC 0,75. Die Schwellen der Bewertung passen zum Default, eine Nachkalibrierung ist dafür nicht nötig.
- **Unter der Schwelle** verhält sich die Pipeline wie `nohw`, und die Bewertung übersieht dort wie in Stufe 3 100 / 65 Fehler in kurzen `confident`-Passagen. Das ist der bewusste Preis des Schutzes: kein Wortverlust, aber eine Bewertung, die zu oft „sicher“ sagt. Die Meldung weist darauf hin, Begriffe zu ergänzen.
- **Nicht abgedeckt:** Das Werkzeug misst nur Segment 1. Segment 2 ist auf beiden Aufnahmen kurz (26 bzw. 5 min) und wurde nicht eigens gemessen.

## Offen

- Ob die vereinzelten Defizite von `base` auf Aufnahme 2 echte Auslassungen sind, klärt nur eine Handreferenz in einem dieser Abschnitte.
- Bei 110–161 Tokens und unter der Schwelle übersieht die Bewertung mehr Fehler als mit vollem Budget, weil die Passagen kürzer werden. Für den Default ist das nicht so (Abnahme). Schwellen, die für kurze Passagen strenger sind, wären nur nötig, wenn Snapshots oft so kurz sind.
- Zwischen 51 und 110 Tokens gibt es keine Messung. Eine genauere Schwelle wäre nur nötig, wenn Snapshots oft in diesem Bereich liegen.
