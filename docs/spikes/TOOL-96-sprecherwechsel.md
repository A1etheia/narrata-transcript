# TOOL-96 — Passagen am Sprecherwechsel teilen

Stand 2026-11-21. Bericht zu [TOOL-96](../plans/TOOL-96-speaker-turns.md), Werkzeug: [`scripts/spike/turns.py`](../../scripts/spike/turns.py). Alle Messungen liefen lokal auf den gespeicherten Transkripten der Pilotsitzung, ohne Modell. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keine Labels, keinen Session-Schlüssel.

## Ergebnis vorab

- **Das Teilen senkt den Sprecherfehler deutlich.** Mit 500 ms sinkt er an A von 17,4 % auf 6,2 % und an B von 14,0 % auf 3,6 %. Nach dem Schnitt trägt jede Passage im Wesentlichen das Label ihrer Wörter und liegt damit nahe an der Fehlerrate der Wortlabels (A 5,4 %, B 3,4 %). Der größte Teil des heutigen Fehlers kommt also vom Mehrheitslabel pro Whisper-Segment, nicht von der Diarisierung.
- **Abstand zu Plaud unter 5 Punkten.** Plaud liegt bei 2,8 % / 0,0 %, der Abstand beträgt nach der Neuverarbeitung 3,4 bzw. 3,6 Punkte. Ein Folge-Ticket für die Diarisierung entsteht nicht, TOOL-97 wird geschlossen (siehe „Nachher“ und „Folgen“).
- **Strukturell bringt der Schnitt viel.** Mit 500 ms enthalten 8,7 % statt 48,5 % der Passagen Wörter mit mehr als einem Label, und nur 2,8 % statt 26,7 % der beschrifteten Wörter stehen unter einem fremden Label. Review-Kandidaten sinken von 87,3 % auf 65,7 % der Passagen. IT/OT-Einstufung (IOA-1302) und Lesefassung (IOA-1318) bekommen damit den Sprecherwechsel als Grenze.
- **Schwelle: 500 ms.** Bis 1000 ms ist der Fehler an A und B gleich. 500 ms hält die gemischten Passagen unter 10 % und die Zahl der Passagen unter der von Plaud.
- **Neuverarbeitung bestätigt die Messung** (siehe „Nachher“). Die Pilotsitzung hat jetzt 2.166 Passagen. 26 von 35 Review-Entscheidungen gelten weiter. Der Re-Import in Narrata läuft ohne `--replace` und entfernt keine Passage.

## Material und Methode

| | |
| --- | --- |
| Sitzung | Pilotsitzung aus TOOL-58, 5:26 h, zwei Aufnahmen |
| Referenz A | 0:00:00–0:04:06, Handreferenz mit vier Sprechern |
| Referenz B | 1:20:00–1:23:00, Handreferenz mit zwei Sprechern |
| Transkript | gespeicherter Pipeline-Stand: large-v3-turbo mit Hotwords, pyannote community-1, unverändert seit TOOL-58 |

- **Schnitt:** `diarization.turns.split_at_speaker_changes` im Speicher auf jede Passage, danach neu nummeriert. Ein Label-Lauf, der kürzer als die Schwelle dauert (oder weniger Wörter hat), wird zum vorigen Lauf gezogen, am Anfang zum folgenden. Wörter ohne Label bleiben beim Lauf davor.
- **Sprecherfehler:** wie die WDER aus TOOL-20 (`denoise._wder`). Gewertet werden nur Wörter, die Handreferenz und Transkript gleich erkennen. Die Labels werden den Hand-Sprechern 1:1 so zugeordnet, dass die meisten Wörter stimmen.
  - Auf **Passagenebene** trägt jedes Wort das Label seiner Passage, so wie der Export es zeigt.
  - Auf **Wortebene** trägt es das Label, das die Diarisierung ihm selbst gibt. Daran ändert kein Schnitt etwas.
- **Mehrere Sprecher:** Passagen im Ausschnitt, deren gewertete Wörter laut Handreferenz mehr als einer Person gehören.
- **Kandidaten und Hinweise:** Für jede Variante findet das Skript die Hinweise neu und bewertet die Passagen neu (`segment_hints`, `segment_assessment`), mit den Schwellen der Projektkonfiguration.
- **Vergleichbarkeit:** Die Zahlen aus dem Ticket (17,6 % / 14,0 % Pipeline, 2,8 % / 0,0 % Plaud) stammen aus dem Skript der Projektverantwortlichen: Füllwörter entfernt, freie Ausrichtung der Clipgrenzen, ohne 1:1-Zuordnung nach bester Übereinstimmung. Für die gespeicherten Passagen liefert die Repo-Methode fast dieselben Werte (17,4 % / 14,0 %). Gegen Plaud gilt trotzdem die Messung mit jenem Skript am neuen Export (Chunk 6).

### Korrektur des Handreferenz-Parsers

Die erste Fassung dieses Berichts (2026-11-17) beruhte auf einem Parserfehler. `calibration.parse_hand_reference` erkannte eine Sprecherkennung nur als `Name:`, nicht als `Name (Rolle):`. In B steht jede Zeile in dieser Form, in A fünf von 38 Zeilen.

- B hatte damit keinen einzigen Sprecher, A nur drei statt vier. Die Wörter einer nicht erkannten Zeile gingen an die vorige Person, und Name und Rolle zählten als gesprochene Wörter (A 551 statt 531, B 489 statt 441 Wörter).
- Die damaligen Werte (A 16,3 % → 15,1 %, B 6,2 % → 11,3 %) und der Schluss, der Fehler sitze in der Diarisierung, sind damit hinfällig.
- Der Parser erkennt jetzt Kennungen mit beliebig vielen Klammerzusätzen. Die Person bestimmt allein der Name.
- **Auch frühere Spikes sind betroffen:** WER und WDER an A und B in TOOL-92 und TOOL-93 enthalten Kennungs- und Rollenwörter als vermeintlich ausgelassene Wörter, die WDER an A eine falsche Sprecherzuordnung. Die Berichte sind eingefroren und werden nicht geändert. Wer sich auf ihre absoluten Werte stützt, misst neu.

## Sprecherfehler an A und B

Wortebene, gleich für alle Schnitte: A 5,4 % (n = 424), B 3,4 % (n = 320). Die Werte auf Passagenebene zählen einige Wörter mehr, weil auch Wörter ohne eigenes Label über ihre Passage ein Label tragen.

| Schnitt | Passagenebene A | mehrere Sprecher A | Passagenebene B | mehrere Sprecher B |
| --- | --- | --- | --- | --- |
| heute (ungeteilt) | 17,4 % (n = 436) | 4 von 9 | 14,0 % (n = 336) | 3 von 8 |
| 0 | 6,2 % | 11 von 19 | 3,6 % | 2 von 10 |
| 250 ms | 6,2 % | 11 von 19 | 3,6 % | 2 von 10 |
| 500 ms | 6,2 % | 11 von 19 | 3,6 % | 2 von 10 |
| 1000 ms | 6,2 % | 11 von 19 | 3,6 % | 2 von 10 |
| 1500 ms | 7,8 % | 9 von 15 | 3,6 % | 2 von 10 |
| 2000 ms | 8,7 % | 8 von 14 | 3,6 % | 2 von 10 |
| 2 / 3 / 4 Wörter | 6,2 % | 11 von 19 | 3,6 % | 2 von 10 |

- **Obergrenze des Gewinns:** Vor dem Schnitt liegen Passagen- und Wortebene an A 12,0 und an B 10,6 Punkte auseinander. Mit 500 ms holt der Schnitt davon 11,2 bzw. 10,4 Punkte.
- **Mehrere Sprecher bleiben:** An A enthalten auch nach dem Schnitt 11 von 19 Passagen Wörter mehrerer Hand-Sprecher, an B 2 von 10. Die Diarisierung setzt dort keinen Wechsel, also kann auch der Schnitt keinen setzen. Weil die Wortlabels trotzdem zu rund 95 % stimmen, sind das vermutlich meist kurze Einwürfe am Rand einer Passage (nicht gemessen). Wie viel davon an der Diarisierung selbst hängt, misst TOOL-97, falls es nach Chunk 6 nötig bleibt.

## Ganze Sitzung

| Schnitt | Passagen | pro h | Länge P10 / Median / P90 (s) | gemischt | Wörter mit fremdem Label | Kandidaten | markierte Zeit | Hinweise |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| heute (ungeteilt) | 997 | 195 | 0,8 / 13,2 / 40,3 | 484 (48,5 %) | 26,7 % | 870 (87,3 %) | 96,6 % | 403 |
| 0 | 2441 | 478 | 0,5 / 3,6 / 19,3 | 23 (0,9 %) | 1,9 % | 1508 (61,8 %) | 77,5 % | 397 |
| 250 ms | 2327 | 456 | 0,7 / 3,9 / 20,0 | 93 (4,0 %) | 2,2 % | 1476 (63,4 %) | 77,9 % | 397 |
| **500 ms** | **2166** | **424** | **0,8 / 4,4 / 21,6** | **188 (8,7 %)** | **2,8 %** | **1424 (65,7 %)** | **79,0 %** | **397** |
| 1000 ms | 1893 | 371 | 1,1 / 5,7 / 24,2 | 332 (17,5 %) | 4,2 % | 1327 (70,1 %) | 82,0 % | 398 |
| 1500 ms | 1728 | 338 | 1,2 / 6,6 / 27,1 | 398 (23,0 %) | 5,8 % | 1255 (72,6 %) | 83,5 % | 399 |
| 2000 ms | 1615 | 316 | 1,1 / 7,2 / 28,2 | 446 (27,6 %) | 7,3 % | 1209 (74,9 %) | 84,7 % | 399 |
| 2 Wörter | 2114 | 414 | 0,8 / 4,6 / 21,9 | 229 (10,8 %) | 2,6 % | 1399 (66,2 %) | 79,7 % | 398 |
| 3 Wörter | 1975 | 387 | 1,0 / 5,3 / 23,4 | 305 (15,4 %) | 3,2 % | 1345 (68,1 %) | 80,7 % | 398 |
| 4 Wörter | 1877 | 367 | 1,0 / 5,7 / 24,8 | 337 (18,0 %) | 3,8 % | 1312 (69,9 %) | 81,8 % | 398 |

- **gemischt:** Passagen, deren Wörter mehr als ein Label tragen. Bei 0 sind das nur Passagen, deren Wortfolge nicht genau den Text ergibt. Diese teilt die Pipeline nie: 23 von 484 Passagen mit mehr als einem Label.
- **Kandidaten** sinken, weil eine kurze sichere Passage nicht mehr mit einer unsicheren zusammen markiert wird. Die markierte Zeit fällt von 96,6 % auf 79,0 %. Das ist kein Gewinn an Erkennungsqualität, sondern eine feinere Eingrenzung.
- **Hinweise** gehen um 6 zurück (403 → 397), weil ein Glossarbegriff über mehrere Wörter an einem Schnitt in zwei Passagen fallen kann.
- **Plaud** liefert rund 2.600 Abschnitte auf 5 h, also etwa 520 pro Stunde.

## Wahl der Schwelle

**500 ms, gemessen als Dauer der beschrifteten Wörter eines Laufs.** Die Schwelle wird in Millisekunden angegeben, nicht in Wörtern:

- **Fehler:** Von 0 bis 1000 ms ist der Sprecherfehler an A und B gleich. Ab 1500 ms steigt er an A wieder (7,8 %, bei 2000 ms 8,7 %), weil echte kurze Beiträge verschluckt werden.
- **Struktur:** 500 ms hält die gemischten Passagen unter 10 % und die beschrifteten Wörter unter fremdem Label unter 3 %. Bei 1000 ms ist schon jede sechste Passage gemischt.
- **Hören:** Der Median steigt von 3,6 s (0 ms) auf 4,4 s. Lange Passagen sind beim Hören hilfreicher (TOOL-58). Hörblöcke aus mehreren Passagen hängen an der Review-Entscheidung in TOOL-60.
- **Wörter oder Millisekunden:** Die Wortschwellen liegen zwischen den ms-Zeilen und bringen keinen Vorteil. Eine Dauer ist von der Sprechgeschwindigkeit unabhängig.

## Nachher: Neuverarbeitung der Pilotsitzung

Stand 2026-11-21. `transcript process` hat die Pilotsitzung mit 500 ms neu geschnitten. Die Diarisierung lief nicht neu, die gespeicherte Rohdatei wurde wiederverwendet. Danach wurden Hinweise und Bewertung neu berechnet, die Sprecher neu zugeordnet und Arbeitsfassung, Export, TXT, DOCX und Bericht neu geschrieben. Der alte Export ist als Vergleichsstand gesichert.

### Sprecherfehler

| | vorher, Repo-Methode | vorher, Skript der Projektverantwortlichen | nachher, Repo-Methode | Plaud | Abstand nachher |
| --- | --- | --- | --- | --- | --- |
| A | 17,4 % | 17,6 % | **6,2 %** | 2,8 % | **3,4 Punkte** |
| B | 14,0 % | 14,0 % | **3,6 %** | 0,0 % | **3,6 Punkte** |

- **Wie vorhergesagt:** Die Repo-Methode (`turns.py`, Passagenebene) am gespeicherten Stand trifft die Zeile 500 ms der Ausgangsmessung genau, ebenso Passagenzahl, Längen, gemischte Passagen, Kandidaten und Hinweise.
- **Neue Schwellenzeilen nicht aussagekräftig:** `turns.py` schneidet die Schwellenreihe jetzt auf den schon geteilten Passagen noch einmal. Nach dem Schnitt sagen diese Zeilen deshalb nichts Neues.
- **Nachher nur mit der Repo-Methode gemessen:** Das Skript der Projektverantwortlichen stand für die Messung nachher nicht mehr zur Verfügung. Laut Plan sollte nur es gegen Plaud gelten. Am ungeteilten Stand weichen beide Methoden aber höchstens 0,2 Punkte voneinander ab (A 17,4 % gegen 17,6 %, B 14,0 % gegen 14,0 %). Der Abstand zur 5-Punkte-Grenze beträgt 1,4 Punkte, das Siebenfache dieser Abweichung. Die Repo-Methode reicht deshalb für die Entscheidung.

### Ganze Sitzung

| | vorher | nachher |
| --- | --- | --- |
| Passagen | 997 | 2.166 |
| pro Stunde Audio (5:26 h) | 183 | 399 (Plaud rund 520) |
| Länge P10 / Median / P90 (s) | 0,8 / 13,2 / 40,3 | 0,8 / 4,4 / 21,6 |
| Passagen mit mehr als einem Label | 48,5 % | 8,7 % |
| beschriftete Wörter unter fremdem Label | 26,7 % | 2,8 % |
| Review-Kandidaten | 870 (87,3 %) | 1.424 (65,7 %) |
| markierte Zeit | 96,6 % | 79,0 % |
| Hinweise | 403 | 397 |
| im Export `unreviewed` / `open` / `corrected` / `confirmed` | 127 / 835 / 26 / 9 | 742 / 1.398 / 18 / 8 |

- **Mehr Kandidaten, weniger markierte Zeit:** Die Zahl der Kandidaten steigt, weil es mehr Passagen gibt. Ihr Anteil und die markierte Hörzeit sinken.
- **Sichere Passagen:** Im Export sind 742 statt 127 Passagen sicher, vor allem kurze Teile, die vorher mit einer unsicheren Passage zusammen markiert waren.
- **Hinweise:** 6 Glossar-Treffer über mehrere Wörter fallen an einem Schnitt in zwei Passagen (403 → 397).

### Review-Entscheidungen

Aus dem Pilot-Review lagen 35 Entscheidungen vor (23 `corrected`, 9 `confirmed`, 3 `unintelligible`). Nach dem ursprünglichen Plan wären alle veraltet gewesen, die 23 Korrekturen also aus dem Export verschwunden. Seit Chunk 5 folgt eine Entscheidung ihrer Passage (`processing.renumbered`):

| | Entscheidungen | davon `corrected` |
| --- | --- | --- |
| Passage unverändert, Entscheidung gilt unter neuer Nummer | 26 | 15 (dazu 8 `confirmed`, 3 `unintelligible`) |
| Passage geteilt, Entscheidung veraltet, im Sheet beim ersten Teil | 9 | 8 (dazu 1 `confirmed`) |

- **Probelauf und echter Lauf stimmen überein:** Beide ergeben 26 / 9. Der Export enthält 18 `corrected` (15 Korrekturen und 3 unverständliche) und 8 `confirmed`.
- **Die 9 veralteten** kommen beim nächsten Review wieder vor. Ob und wie dieses Review stattfindet, entscheidet TOOL-60. Eine Korrektur auf die Teile zu verteilen hieße, Text zu erfinden.
- **Altes Review-Sheet:** Der erste `process`-Lauf hielt beim Review an. Er las die alte `review.csv` erneut ein, deren IDs nach dem Schnitt keine oder andere Passagen bezeichneten. Behoben: Eine Zeile eines älteren Exports wird an der Entscheidung ihrer eigenen Fassung gemessen. Alle 870 Zeilen gelten jetzt als unberührt.

### Sprecherzuordnung

Die Zuordnung musste neu bestätigt werden, weil sich mit den Passagen der Fingerabdruck der Labels ändert. Der Dialog dauerte rund 2 Minuten. Danach sind alle 7 Labels Personen; vorher war eines als `multiple` markiert.

### Narrata

| Schritt | Ergebnis |
| --- | --- |
| `transcript:validate` | entspricht dem Contract |
| Import des alten Exports (Stand TOOL-58) | 997 angelegt |
| **Import des neuen Exports ohne `--replace`** | **1.169 angelegt, 994 aktualisiert, 3 unverändert, 0 entfernt** |
| derselbe Export noch einmal | nichts geändert |

- **Alle 997 IDs bleiben:** Der erste Teil einer geteilten Passage trägt ihre ID weiter (Chunk 4). Narrata braucht keine Änderung.
- **Lokale Datenbank:** Der Pilot-Import aus TOOL-58 war dort nicht mehr vorhanden. Der Stand vorher wurde deshalb aus dem gesicherten Export wiederhergestellt.
- **Befund für Narrata:** Die Prüfung aus IOA-1280 lehnt einen Import nur ab, wenn Keys fehlen. Ob an einer aktualisierten Passage Links oder Archiv-Provenienz hängen, prüft sie nicht. Eine Passage, deren Text sich durch den Schnitt halbiert, behält ihre Links ungefragt. In der lokalen Datenbank gab es keine solchen Links, gemessen ist es also nicht.

## Folgen

- **Diarisierung (TOOL-97): kein Folge-Ticket, TOOL-97 wird geschlossen.** Es war nach der ersten, fehlerhaften Fassung dieses Berichts angelegt worden.
  - Nach dem Schnitt liegt der Sprecherfehler an A 3,4 und an B 3,6 Punkte über Plaud, also unter der 5-Punkte-Grenze des Tickets. Gemessen ist das mit der Repo-Methode, Begründung unter „Sprecherfehler“ oben.
  - Der verbliebene Fehler liegt nahe an dem der Wortlabels (A 5,4 %, B 3,4 %). Mehr ginge nur über bessere Wortlabels, also über die Diarisierung selbst oder die Aufnahme am Tisch.
  - An A enthalten 11 von 19 Passagen weiter Wörter mehrerer Hand-Sprecher. Das ist kein Grund für ein eigenes Ticket, solange die Fehlerrate unter der Grenze bleibt. Falls IT/OT (IOA-1302) daran scheitert, ist das der Anlass, die Diarisierung neu aufzugreifen.
- **Links an geteilten Passagen (Narrata):** siehe Befund oben. [kein Ticket: Entscheidung in TOOL-60, ob ein IOA-Ticket nötig ist]
- **Frühere Spikes:** Die absoluten WER- und WDER-Werte an A und B aus TOOL-92 und TOOL-93 sind durch den Parserfehler verzerrt (siehe oben). [kein Ticket: Berichte eingefroren, das No-Go aus TOOL-93 hält nach der Neuwertung unten]

### Neuwertung TOOL-93

`asr.py score` auf den gespeicherten Läufen aller 16 Varianten aus TOOL-93, je drei Seeds, mit dem korrigierten Parser. Kein Modelllauf, nur der Vergleich mit den Handreferenzen ist neu.

| Variante | WER A vorher → nachher | WER B vorher → nachher | gegen `base` (A / B) |
| --- | --- | --- | --- |
| `base` | 24,0 % → **21,3 %** | 36,1 % → **29,8 %** (25,6–35,4) | |
| `base+vad-t35` | → 20,5 % | → 35,1 % | −0,8 / +5,3 |
| `base+beam10` | → 21,4 % | → 32,7 % | +0,1 / +2,9 |
| `base+logprob-lax` | → 21,3 % | → 29,6 % | 0 / −0,2 |
| `nohw` | 28,3 % → 26,0 % | 35,0 % → 28,1 % | +4,7 / −1,7 |
| `nohw+de-turbo` | → 25,2 % | → 31,5 % | +3,9 / +1,7 |
| `nohw+large-v3` | → 28,2 % | → 31,1 % | +6,9 / +1,3 |

- **Das No-Go hält.** Keine Variante liegt an A und B mindestens 3 Punkte unter `base`. Die Reihenfolge bleibt: `base` an A vorn, `nohw` an B vorn und an A klar schlechter. `pchw`, `cond-prev` und `crisper` bleiben weit zurück.
- **Absolut** sinkt die WER an A um 2–3 Punkte und an B um rund 6 Punkte, vor allem bei den Auslassungen: An B fallen sie für `base` von 84–92 auf 42–45.
- **Nicht neu gewertet:** Die TOOL-93-Läufe sind nicht diarisiert, eine WDER gibt es dort nicht. Die Fehler je Sprecher hinter der Aufnahme-Empfehlung und die WDER an A aus TOOL-92 (15,3 %) sind nicht neu gemessen. Die Wortebene hier (5,4 %) legt nahe, dass auch diese zu hoch war.
