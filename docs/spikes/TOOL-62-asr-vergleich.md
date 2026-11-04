# TOOL-62 — Lokale ASR-Modelle im Vergleich

Stand 2026-11-04. Spike-Bericht zu [TOOL-62](../plans/TOOL-62-asr-spike.md), Werkzeug unter [`scripts/spike/`](../../scripts/spike/README.md). Alle Läufe liefen lokal und offline. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

- **Empfehlung V0.1: Whisper large-v3-turbo über faster-whisper.** Die Fehlerquote ist so gut wie die der anderen Kandidaten. Als einziges Modell verarbeitet es fünf Stunden am Stück, liefert Wortzeiten und eine brauchbare Confidence und hat ein funktionierendes Biasing.
- **Fallback: Parakeet TDT 0.6B v3.** Genauso genau und siebenmal schneller, aber nur in Blöcken lauffähig und ohne Biasing.
- **Nicht tragfähig: Granite Speech 4.1 2B Plus.** Fehlerquote fast doppelt so hoch, Schleifen bei jeder Einstellung außer einer.
- **Segmentierung:** Mit Whisper turbo braucht die Pipeline keine eigene Segmentierung. `TOOL-11` und `TOOL-33` entfallen dann.
- **Größter Fehlerfaktor ist nicht das Modell, sondern die Mundart.** Beim Mundartsprecher ist die Fehlerquote mehr als dreimal so hoch wie beim anderen Sprecher, bei allen Modellen ähnlich.

## Material und Methode

| | |
| --- | --- |
| Testaufnahme | 5:00:00 einer Sitzung, 16 kHz mono, MP3 32 kbit/s |
| Ausschnitt | 25:00 aus der Mitte, ausgewählt über Sprechdichte, Tempowechsel und unsichere Wörter |
| Handreferenz | 3:00 aus dem Ausschnitt, dort wo Whisper und Parakeet am stärksten voneinander abweichen; 358 gewertete Wörter, 2 Sprecher, 5 unverständliche Stellen |
| Begriffsliste | 122 Kampagnenbegriffe, 28 davon mehrteilig |
| Hardware | RTX 3080 Ti (12 GB VRAM), 20 Threads, 15 GB RAM in WSL2 |
| Versionen | faster-whisper 1.2.1 (CTranslate2 4.8.4), NeMo 3.0.0, transformers 5.20.2, torch 2.14.1 |

Die Wortfehlerrate (WER) beruht auf einer `difflib`-Ausrichtung und liegt nahe an der minimalen WER. Jeder Lauf wird auf denselben 358 Wörtern gewertet; was ein Modell an einer unverständlichen Stelle ausgibt, zählt weder als richtig noch als Einfügung. Ein Prozentpunkt entspricht knapp vier Wörtern; Unterschiede von ein bis zwei Punkten sind Rauschen. Der Mundartsprecher ist in der Referenz teils wörtlich, teils hochdeutsch geschrieben. Seine WER ist deshalb um einen unbekannten Anteil nach oben verzerrt; der Vergleich der Modelle untereinander bleibt fair, weil alle gegen dieselbe Referenz laufen.

Der Agent, der die Läufe ausgewertet hat, hat keinen Transkripttext gelesen. Ausgewertet sind Zählwerte, Wiederholungsstatistiken und Ausrichtungen. Lesbarkeit und Interpunktion sind deshalb nicht beurteilt (siehe [Offen](#offen)).

## Kandidaten

| Kandidat | Lizenz | Deutsch | Lauffähig | Einrichtung |
| --- | --- | --- | --- | --- |
| Whisper large-v3-turbo (faster-whisper) | MIT (Runtime); Lizenz der CTranslate2-Konvertierung nicht geprüft | ja | ja, am Stück | 2,6 GB venv, `LD_LIBRARY_PATH` für cuBLAS/cuDNN aus pip |
| Whisper large-v3 (faster-whisper) | wie oben | ja | ja, am Stück | dieselbe venv |
| Parakeet TDT 0.6B v3 (NeMo) | CC-BY-4.0 | ja, 25 Sprachen | nur in Blöcken à 300 s | 6,4 GB venv |
| Granite Speech 4.1 2B Plus (transformers) | Apache 2.0 | ja | nur in Blöcken à 90 s mit Penalty 1,2 | 5,5 GB venv, `transformers>=5.8` |

## Ergebnisse

### Wortlaut

WER auf der Handreferenz, jeweils als Lauf nur auf den drei Minuten. In Klammern derselbe Abschnitt aus dem Lauf über den ganzen Ausschnitt; Granite fehlt dort, weil seine 90-s-Blöcke nicht auf die Grenzen fallen.

| Kandidat | WER | Ersetzungen | Auslassungen | Einfügungen |
| --- | --- | --- | --- | --- |
| Whisper large-v3-turbo | 33,5 % (33,0 %) | 57 | 54 | 9 |
| Parakeet TDT 0.6B v3 | 33,5 % (34,9 %) | 63 | 52 | 5 |
| Whisper large-v3 | 35,8 % (34,9 %) | 57 | 66 | 5 |
| Granite 2B Plus | 60,6 % | 130 | 80 | 7 |

Nach Sprecher (Fehlerquote ohne Einfügungen):

| | Wörter | Whisper turbo | Parakeet | Whisper large-v3 | Granite |
| --- | --- | --- | --- | --- | --- |
| Sprecher ohne Mundart | 179 | 13 % | 15 % | 16 % | 36 % |
| Mundartsprecher | 179 | 49 % | 50 % | 53 % | 81 % |

Füllwörter erklären den Abstand nicht: Von 46 Auslassungen bei Whisper turbo beim Mundartsprecher sind 12 Wörter wie „ja“ oder „äh“, beim anderen Sprecher keine.

### Auslassungen und Halluzinationen

Gemessen über Wiederholungen: Anteil des Texts in 5-Wort-Folgen, die mindestens dreimal vorkommen, und Anteil verschiedener Wörter. Natürlicher deutscher Text liegt auf diesem Material bei 0–1 % Wiederholung und 24 % verschiedenen Wörtern.

| Kandidat und Einstellung | Wörter (Ausschnitt) | Wiederholung | verschiedene Wörter |
| --- | --- | --- | --- |
| Whisper large-v3-turbo | 3.612 | 0,7 % | 24 % |
| Whisper large-v3 | 3.597 | 0,1 % | 24 % |
| Parakeet | 3.523 | 0,5 % | 25 % |
| Granite, Penalty 2,0 (Modellkarte), 480-s-Blöcke | ca. 10.800 auf 26 min | 0 % | 99,6 % je Block |
| Granite, Penalty 1,0, 90-s-Blöcke | 6.435 | 58 % | 13 % |
| Granite, Penalty 1,2, 90-s-Blöcke | 3.297 | 0 % | 40 % |

Granite erzeugt mit der Einstellung der Modellkarte Text ohne jede Wiederholung, also keinen Sprachtext, und mit 1,0 Schleifen. Mit 1,2 bleibt es stabil, liegt aber 9 % unter den anderen Wortzahlen und hat auffällig viele verschiedene Wörter; vermutlich unterdrückt die Penalty häufige Wörter.

### Eigennamen und Biasing

Ohne Biasing finden alle Modelle auf dem Ausschnitt dieselben 6 der 122 Begriffe. In der Handreferenz kommen nur 2 Begriffe aus der Liste vor; eine Trefferquote für Eigennamen lässt sich daraus nicht ablesen.

Biasing mit der Begriffsliste auf dem Ausschnitt:

| Kandidat | Wörter | Begriffstreffer | verschiedene Begriffe | Wiederholung |
| --- | --- | --- | --- | --- |
| Whisper large-v3-turbo | 3.612 → 3.683 | 18 → 26 | 6 → 12 | 0,7 % → 1,1 % |
| Whisper large-v3 | 3.592 → 1.703 | 17 → 260 | 6 → 18 | 0,1 % → 24 % |
| Granite (Penalty 1,2) | 3.284 → 3.963 | 11 → 16 | 6 → 5 | 0 % → 21 % |

- **Whisper turbo** nimmt die Liste auf, ohne dass die Ausgabe leidet. Der Zuwachs liegt ausschließlich bei den ersten 63 Begriffen; mehr passen nicht in die 223 Tokens, die faster-whisper für Hotwords zulässt. Ob die zusätzlichen Treffer stimmen, zeigt die Referenz nicht: Die WER mit Liste ist auf der Probe 32,4 % gegen 33,5 % ohne, im Ausschnittslauf 36,3 % gegen 33,0 %, also kein belastbarer Effekt.
- **Whisper large-v3** gibt mit Liste vermutlich die Begriffe selbst aus statt zu transkribieren.
- **Granite** kippt mit Liste wieder in Schleifen.
- **Parakeet** hat kein dokumentiertes Biasing.

### Zeitstempel

Whisper und Parakeet liefern Wort- und Segmentzeiten, Granite im reinen ASR-Modus keine; sein Zeitstempel-Modus ist laut Modellkarte auf 3,5 Minuten ausgelegt und nicht getestet. Die Genauigkeit der Zeiten ist nicht gemessen, weil die Referenz keine Zeiten enthält. Über fünf Stunden verlaufen die Wörter pro 5 Minuten bei Whisper und Parakeet fast deckungsgleich (z. B. 885/779 und 893/879 im dichtesten, 285/286 im leisesten Abschnitt); keines der beiden Modelle driftet.

### Confidence

Beide Whisper-Varianten und Parakeet geben pro Wort einen Wert aus, auf verschiedenen Skalen (Mittel 0,86 gegen 0,22). Für die Rangfolge spielt das keine Rolle:

| Kandidat | falsche Wörter in der Ausgabe | AUC | unsicherste 10 % | 20 % | 30 % |
| --- | --- | --- | --- | --- | --- |
| Whisper large-v3-turbo | 21 % | 0,82 | 27 % | 47 % | 71 % |
| Whisper large-v3 | 21 % | 0,81 | 27 % | 50 % | 68 % |
| Parakeet | 22 % | 0,79 | 29 % | 50 % | 62 % |

Die letzten Spalten nennen den Anteil der falschen Wörter, der unter den unsichersten 10, 20 oder 30 % der Wörter liegt. Die AUC ist die Wahrscheinlichkeit, dass ein falsches Wort einen niedrigeren Wert hat als ein richtiges. Wer die unsichersten 30 % prüft, findet also zwei Drittel der falschen Wörter. Ausgelassene Wörter haben keinen Wert und bleiben unsichtbar; bei Whisper turbo sind das 54 von 120 Fehlern auf der Probe.

Whisper liefert zusätzlich pro Segment `avg_logprob`, `no_speech_prob` und `compression_ratio`, Granite keine Signale.

### Sprecherinformation

Whisper und Parakeet liefern keine Sprecher. Granite Plus hat einen Modus mit Sprecherzuordnung (`[Speaker N]:`), getestet ist er nicht.

### Lange Aufnahmen

| Kandidat | volle Aufnahme (5:00:00) | Laufzeit | Spitzen-RAM | Spitzen-VRAM |
| --- | --- | --- | --- | --- |
| Whisper large-v3-turbo | am Stück, längste Lücke zwischen Segmenten 34 s, keine Schleifen | 6 min (50×) | 10,5 GB | 6,3 GB |
| Parakeet | nur in Blöcken à 300 s; am Stück Absturz schon bei 26 min | 46 s (389×) | 3,6 GB | 8,9 GB |
| Granite | nicht versucht | (auf 25 min: 2,6 min) | 4,9 GB | 8,4 GB |

Parakeets Absturz (`CUDA driver error: device not ready` im Subsampling des Encoders) tritt trotz Local Attention und Conv-Chunking auf; die Ursache ist nicht geklärt. Der RAM-Bedarf von Whisper wächst mit der Länge (1,7 GB auf 25 Minuten); bei fünf Stunden bleiben in WSL weniger als 5 GB Reserve. Die VRAM-Werte messen die ganze Karte und schwankten zwischen Läufen um mehrere GB; sie zeigen nur, dass alles unter 12 GB bleibt.

### Laufzeit auf dem Ausschnitt (25 min)

| Kandidat | Transkription | Faktor |
| --- | --- | --- |
| Parakeet | 5 s | 297× |
| Whisper large-v3-turbo | 29 s | 52× |
| Whisper large-v3 | 81 s | 18× |
| Granite | 155 s | 10× |

Für einen nächtlichen Lauf ist jeder Kandidat schnell genug.

## Entscheidung

**V0.1-Backend: Whisper large-v3-turbo über faster-whisper**, mit VAD, Wortzeiten und `beam_size 5`, ohne `condition_on_previous_text`.

- Gleichauf mit den anderen bei der Fehlerquote, auch beim Mundartsprecher.
- Verarbeitet fünf Stunden am Stück ohne Lücken, Schleifen oder Drift.
- Confidence auf einer intuitiven Skala, mit derselben Trennschärfe wie die anderen.
- Einziges Biasing, das die Ausgabe nicht beschädigt.
- Kleinste Einrichtung, keine Blocklogik.

large-v3 bringt keine bessere Fehlerquote, braucht die dreifache Zeit und zerfällt mit Hotwords.

**Fallback: Parakeet TDT 0.6B v3.** Gleich genau und am schnellsten. Ein Wechsel zu Parakeet braucht eigene Segmentierung (dann `TOOL-11`, Startwert 300 s) und eine Kalibrierung der Confidence-Skala. Für die Überlappungs-Deduplizierung (`TOOL-33`) muss dann zuerst eine Blocküberlappung eingeführt werden; ohne Überlappung zerschneiden Blockgrenzen einzelne Wörter.

**Segmentierung:** Mit Whisper turbo sind `TOOL-11` und `TOOL-33` nicht nötig. Die Segmentwerte in der Konfiguration bleiben `null`.

## Weitergabe

- **`TOOL-20`:** Die Handreferenz hat Sprecherkennungen pro Zeile (46 Wechsel in drei Minuten) und taugt damit als erste Referenz für die Diarisierung. Granite Plus mit Sprecherzuordnung ist ungetestet und könnte dort betrachtet werden.
- **`TOOL-35`:** Confidence trennt mit einer AUC von 0,79–0,82; die unsichersten 30 % enthalten 62–71 % der falschen Wörter. Auslassungen bleiben für die Confidence unsichtbar und brauchen ein anderes Signal, etwa Lücken in der Sprechdichte oder `no_speech_prob`. Die Mundart verdreifacht die Fehlerquote; die Review-Auswahl sollte den Sprecher berücksichtigen.
- **`TOOL-64`:** RAM-Bedarf von 10,5 GB auf fünf Stunden einplanen; Hotwords auf die ersten 223 Tokens begrenzen und die wichtigsten Begriffe nach vorne stellen; Lizenz der CTranslate2-Konvertierung prüfen.
- **`TOOL-44`:** Biasing nur mit turbo, nie mit large-v3. Die Wirkung auf die WER ist unbelegt.

## Offen

- **Lesbarkeit und Interpunktion** sind nicht beurteilt. Granite Plus setzt laut Modellkarte keine Satzzeichen, Whisper und Parakeet setzen welche.
- **Fehlerbeispiele** fehlen; sie müssten pseudonymisiert von Hand aus den Läufen übernommen werden.
- **Eigennamen:** Die Probe enthält zu wenige Listenbegriffe. Eine zweite Referenz an einer namensreichen Stelle würde Trefferquote und Biasing-Effekt messbar machen.
- **Mundart:** Wie viel die Mundart wirklich kostet, zeigt erst eine Referenz, die sie durchgängig hochdeutsch oder durchgängig wörtlich schreibt.
- **Aufnahmelänge:** Die Testaufnahme endet bei genau 5:00:00, ebenso weitere Dateien gleicher Größe. Das deutet auf eine Längenbegrenzung des Aufnahmegeräts, die Sitzungen abschneiden kann.
