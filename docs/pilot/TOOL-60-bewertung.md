# TOOL-60 — Bewertung von V0.1 und V0.2-Backlog

Stand 2026-11-21. Grundlage sind die Pilotsitzung aus [TOOL-58](TOOL-58-erste-session.md) im Stand nach [TOOL-96](../spikes/TOOL-96-sprecherwechsel.md) und eine zweite Sitzung derselben Gruppe. Der Bericht enthält nur Kennzahlen: keine Session-Keys, keine Gruppe, keine Namen, keine Labels und keinen Transkripttext (TOOL-66). Handreferenzen und Bögen bleiben unter `work/`. Der Agent hat nur die Zählwerte von `transcript calibrate` gesehen. Plan: [`docs/plans/TOOL-60-pilot-review.md`](../plans/TOOL-60-pilot-review.md).

## Ergebnis in Kürze

- **Die Pipeline trägt, das Transkript ist das Limit.** Von der Aufnahme bis zum Narrata-Import läuft alles lokal, in rund 12 min Rechenzeit und mit 2–4 min Handarbeit pro Abend. Der Wortlaut bleibt mit 21–32 % WER fehlerhaft, und lokal ist nicht mehr drin (TOOL-93). Die Grenze setzt die Aufnahme am Tisch.
- **Die Kernhypothese hält als Rangfolge, nicht als Eingrenzung.** Die Confidence sortiert die Fehler an zwei Sitzungen gleich gut (AUC 0,75–0,78), und Fehlalarme sind selten. Bei dieser Fehlerrate bleiben aber 74–89 % der Hörzeit markiert, und 5–16 % der Fehler liegen in sicheren Passagen. Ein Review, das nur die Markierten prüft, ist weder kurz noch vollständig.
- **Die Sprecher stimmen.** Nach TOOL-96 liegt der Sprecherfehler 3,4–3,6 Punkte über Plaud. Die Diarisierung braucht kein Ticket.
- **Entscheidungen:**
  - Das Review mit Anhören wandert nach Narrata (IOA-1326), die CSV der Pipeline wird eingefroren.
  - IT/OT in Narrata bekommt das Go (IOA-1302).
  - Die Mikrofon-Empfehlung wird nur dokumentiert.
  - Das Remote-Backend (TOOL-14) entfällt.
- **Neu beobachtet:**
  - Archiv-Schreibtreffer sind fast immer Fehlalarm, 2 von 18 (TOOL-99).
  - Der Mundartsprecher hat an zwei Abenden etwa die doppelte Fehlerquote, auch gegen eine Hochdeutsch-Referenz (IOA-1326).

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
- **Ohne Kontext nicht entscheidbar:** Der Vergleich nach Schreibung oder Klang weiß nicht, ob ein Begriff in die Szene passt. Diese Entscheidung gehört zur LLM-Korrektur mit Kontext in Narrata (IOA-1297). Der beurteilte Bogen dient dem Spike IOA-1302 als lokaler Testsatz.

## Bewertung je Bereich

| Bereich | Bewertung | Grundlage |
| --- | --- | --- |
| Referenztranskription | **Begrenzt, lokal ausgereizt.** WER an der Pilotsitzung 21–30 % (Spanne über Seeds 25,6–35,4 % an B), an der zweiten Sitzung 31,5 %. Fast die Hälfte der Fehler sind Auslassungen von Inhaltswörtern. Kein Modell und keine Einstellung bringt mehr als die Seed-Streuung, Entrauschen auch nicht. Plaud ist bei den Wörtern nicht besser. | TOOL-92, TOOL-93, TOOL-96 (Neuwertung), Messungen oben |
| Konfidenz- und Unsicherheitssignale | **Gut als Rangfolge.** AUC 0,75–0,78 an zwei Sitzungen, unter den unsichersten 30 % der Wörter sind 57–68 % falsch. Auslassungen haben keine Confidence und fallen nur über `gap`, `sparse` oder `crosstalk` auf. Halluzinationen am Aufnahmeende wurden richtig `uncertain`. | TOOL-35, TOOL-58, Messungen oben |
| Sprechertrennung und Zuordnung | **Gut.** Sprecherfehler 6,2 % / 3,6 % nach dem Schnitt am Sprecherwechsel, 3,4–3,6 Punkte über Plaud. Die Zuordnung dauert 2–4 min pro Abend, ist nach einem Schnitt neu zu bestätigen und trifft alle Labels. | TOOL-68, TOOL-86, TOOL-96 |
| Segmentüberlappungen | **Entfällt.** Ohne eigene Segmentierung gibt es keine Überlappungen, eine Aufnahme ist ein Segment. | TOOL-62 |
| Review-Kandidaten | **Zu viele für ein vollständiges Review, zu wenige für ein sicheres.** 237–262 Kandidaten pro Stunde Audio, 66 % der Passagen, 79 % der Hörzeit. Fehlalarme: 5 von 50 markierten Passagen an A–C. Übersehen: 5–16 % der Fehler, an der zweiten Sitzung jeder sechste. | TOOL-58, TOOL-96, Messungen oben |
| Domänenwissen und Relevanzregel | **Hilfreich bei `recent`, schädlich beim Archiv.** Schreibtreffer auf `recent` stimmen zu 80 %, auf `archive` zu 11 %, Klang-Treffer zu 28 %. Die Relevanz-Stufen aus TOOL-41 trennen damit genau dort, wo es zählt. Hotwords helfen bei Namen, lassen aber Sprache aus und erhöhen die Seed-Streuung (TOOL-81). | TOOL-35, TOOL-83, Messungen oben |
| CSV-Review | **Nicht alltagstauglich.** 35 Entscheidungen pro Stunde, ein vollständiges Review läge bei rund 25 h pro Abend. Ohne Abspielhilfe musste ein eigenes Skript her. Längerer Hörkontext hilft. | TOOL-58, TOOL-59 |
| JSON-Contract | **Trägt.** Der Export der Pilotsitzung importiert ohne Korrektur, vor und nach dem Schnitt am Sprecherwechsel. Der Re-Import ist idempotent und hat nach dem Schnitt 0 Passagen entfernt, weil die IDs erhalten bleiben. Offen ist, dass Narrata abhängige Links an aktualisierten Passagen nicht prüft. | TOOL-58, TOOL-96, TOOL-98, IOA-1327 |
| TXT- und DOCX-Ausgabe | **Funktioniert, nicht gesondert bewertet.** Offene Passagen sind als `[unklar …]` markiert, und es gibt keinen beobachteten Fehler. Die Lesbarkeit begrenzt der Wortlaut, eine Lesefassung entsteht in Narrata. | TOOL-58, IOA-1318 |
| Resume und Fehlerverhalten | **Gut.** Fertige Schritte werden wiederverwendet, Fehlversuche stehen in `pipeline.log`. Bei Wechsel von Modell oder Snapshot hält `process` an. Die Pilot-Workarounds (CUDA-Bibliotheken, Startskript) sind behoben. | TOOL-57, TOOL-59, TOOL-94, TOOL-95 |
| Laufzeit und Ressourcen | **Gut.** Rund 12 min für 5:26 h Audio (27-fache Echtzeit), bis 13,9 GiB RAM und 2,5 GiB VRAM. Es gibt keine API-Kosten. | TOOL-59 |
| Manuelle Zeit pro Stunde Audio | **Zuordnung vernachlässigbar, Review nicht.** Die Zuordnung braucht 0,4–0,7 min. Ein Review der markierten Passagen hieße allein 47 min Hören pro Stunde Audio (79 % markierte Zeit), dazu Entscheiden und Tippen. Die Hochrechnung aus TOOL-58 von 4,6 h gilt für die längeren Passagen von damals und ist am geteilten Stand nicht neu gemessen. | TOOL-58, TOOL-59, TOOL-96 |

## Bekannte Grenzen von V0.1

- **Der Wortlaut bleibt fehlerhaft.** Rund jedes vierte bis dritte Wort ist falsch oder fehlt, vor allem bei kurzen Einwürfen, bei Übersprechen und bei Mundart. Das Transkript taugt zum Suchen und Wiederfinden, nicht als wörtliches Protokoll.
- **Auslassungen bleiben unsichtbar.** Ein fehlendes Wort hat keine Confidence. In sicheren Passagen bleiben 5–16 % der Fehler unmarkiert, die meisten davon Ersetzungen, an B mehr als die Hälfte Auslassungen.
- **Mundart wird hochdeutsch geschrieben.** Das ist für das Archiv meist richtig, aber kein wörtliches Abbild.
- **Die Sprecher-Labels gelten nur innerhalb einer Sitzung.** Die Zuordnung zu Personen bleibt Handarbeit, es gibt keine Wiedererkennung über Sitzungen hinweg (TOOL-87).
- **Die Bewertung kennt keine Personen.** Schwellen pro Person gibt es nicht.
- **Die Messbasis ist schmal:** zwei Sitzungen derselben Gruppe, drei Handreferenzen, je ein ASR-Lauf. Die WER einer einzelnen Referenz schwankt um mehrere Punkte.
- **Eine Aufnahme ist eine Spur.** Mehrspur-Aufnahmen verarbeitet die Pipeline nicht.

## Entscheidungen

| Entscheidung | Ergebnis | Begründung |
| --- | --- | --- |
| Review-Kanal | **Narrata-UI, die CSV wird eingefroren** (IOA-1326) | Ein Review mit Anhören braucht eine Oberfläche mit Abspielen und Kontext, die CSV ist dafür das falsche Werkzeug. Narrata kennt die Personen hinter den Passagen und die LLM-Korrektur aus IOA-1297 und kann beides in die Reihenfolge einbeziehen. Rohaudio bleibt lokal, IOA-1326 verlangt Abspielen im Browser ohne Upload. Die CSV bleibt lauffähig, bekommt aber keine Erweiterung. |
| Review-Umfang | **Kein Pflicht-Review in der Pipeline** | Die Pipeline exportiert nach der Sprecherzuordnung. Unsichere Stellen bleiben im Transkript markiert und gehen als `confidence_tier` an Narrata. Was geprüft wird, entscheidet die Spielleitung in Narrata. |
| Freigabe IT/OT | **Go für IOA-1302** | Der Wortlaut ist lokal ausgereizt, auf Besseres zu warten bringt nichts. Der Sprecherwechsel liegt unter der Grenze aus TOOL-96. Scheitert IT/OT an Passagen mit mehreren Sprechern, ist das der Anlass, die Diarisierung neu aufzugreifen. |
| Diarisierung | **Kein Ticket** (TOOL-97 geschlossen) | Der Abstand zu Plaud liegt mit 3,4 / 3,6 Punkten unter der 5-Punkte-Grenze aus TOOL-96. |
| Aufnahme am Tisch | **Nur dokumentiert** | Die Empfehlung aus TOOL-93, in absteigender Wirkung: ein Ansteckmikrofon je Person mit getrennten Spuren, 2–3 verteilte Grenzflächenmikrofone auf einer Spur, das vorhandene Mikrofon näher an die leisen Plätze. Sie ist nicht gemessen. Ob eine Änderung wirkt, zeigt eine neue Sitzung mit Handreferenz. |
| Alt-Transkripte | **Bleiben verworfen** | Der Pilot zeigt keinen beobachteten Bedarf. |
| Remote-Backend (TOOL-14) | **Entfällt, TOOL-14 wird geschlossen** | Es gibt kein Qualitätsproblem, das nur remote lösbar wäre. Plaud als Cloud-Dienst ist bei den Wörtern nicht besser, die Grenze setzt die Aufnahme. |
| Guard IOA-1280 | **IOA-Ticket** (IOA-1327) | Mit IT/OT und dem Review in Narrata entstehen bald Links an Passagen, deren Text sich bei einem Re-Import ändern kann. |
| Archiv-Schreibtreffer | **Heben nicht mehr an** (TOOL-99) | 2 von 18 richtig, siehe Messungen. |
| Gewichtung pro Person | **In Narrata, als Teil des Reviews** (IOA-1326) | Beobachtet an zwei Abenden, dieselbe Person bei etwa der doppelten Fehlerquote. Die Pipeline kennt nur Labels pro Segment, Narrata kennt die Person. |
| Parakeet-Zweitlauf (TOOL-82) | **Zurückgestellt** | Er findet Auslassungen, dehnt die Markierung aber auf rund vier Fünftel der Zeit aus (TOOL-35). Solange das Review in Narrata nicht steht, fehlt ein Maß, ob mehr Markierung hilft. Das Ticket bleibt offen. |

**Bewusst nicht weiterverfolgt:**
- **Hörblöcke und ein Review-Dialog in der Pipeline:** Das Review wandert nach Narrata.
- **Ein anderes ASR-Modell oder andere Einstellungen:** TOOL-93 hat sie geprüft, keines bringt mehr als die Seed-Streuung.
- **Entrauschen vor der Erkennung:** No-Go nach TOOL-92.
- **Mehrspur-Aufnahme in der Pipeline:** erst sinnvoll, wenn die Gruppe ein Mehrspur-Setup ausprobieren will.
- **Modellwahl in Narrata, pro Gruppe oder Sprecher:** Es gibt keinen besseren Modellkandidaten, und die Modellwahl gehört zur lokalen Konfiguration (`asr.model`). Neu zu prüfen ist das, wenn das Mundart-Spike unten einen Kandidaten zeigt oder TOOL-85 die Transkription für andere Nutzer öffnet. Ein Hinweis steht an TOOL-85.
- **Ein zweiter ASR-Lauf, wenn die Sprecher bekannt sind:** Whisper hat keine Anpassung an Sprecher. Kurze Ausschnitte erkennt es schlechter, nicht besser. Mundart folgt in dieser Gruppe nicht sauber einer Person.
- **Die 9 veralteten Pilot-Entscheidungen:** Sie werden nicht in der Pipeline nachgeholt, sondern im Review in Narrata neu entschieden.

## V0.2-Backlog

„Beobachtet“ heißt: im Pilot oder an der zweiten Sitzung gemessen. „Idee“ heißt: plausibel, aber ohne Messung.

| Punkt | Art | Ticket | Ort |
| --- | --- | --- | --- |
| Review mit Anhören in der Narrata-UI, mit Gewichtung pro Person | beobachtet: 25 h CSV-Review, Mundartsprecher bei doppelter Fehlerquote | IOA-1326 | Narrata |
| Warnung beim Re-Import, wenn an geänderten Passagen Links oder Provenienz hängen | beobachtet: Struktur in TOOL-96, Wirkung nicht gemessen | IOA-1327 | Narrata |
| IT/OT-Einstufung und LLM-Korrektur mit Kontext, Testsatz aus 18 Archiv-Treffern | Go aus TOOL-60 | IOA-1302 | Narrata |
| Archiv-Schreibtreffer heben keine Passage an | beobachtet: 2 von 18 richtig | TOOL-99 | Pipeline |
| Hotwords: Seed-Streuung und Auslassungen | beobachtet: bis 8 Punkte zwischen Seeds | TOOL-81 | Pipeline |
| Parakeet-Zweitlauf als Signal für Auslassungen | beobachtet: 8 von 9 übersehenen Auslassungen gefunden, aber +15 % Hörzeit | TOOL-82 (zurückgestellt) | Pipeline |
| Review-Korrekturen auf Archivbegriffe an Narrata | Idee | TOOL-88 (besteht) | Pipeline |
| Anwesenheit aus dem Kontext, etwa für die Sprecherzahl der Diarisierung | Idee | TOOL-79 (besteht) | Pipeline |
| Mundart-Spike: bairisch-fähige lokale Modelle an Referenz C | Idee: Gegen die Hochdeutsch-Referenz liegt der Mundartsprecher weiter bei 48 %, an den Auslassungen ändert sich nichts | [kein Ticket: erst, wenn ein lokales bairisch-fähiges Modell bekannt ist] | Pipeline |
| Zweites Fenster an der zweiten Sitzung, für eine Spanne statt eines Einzelwerts | Idee | [kein Ticket: keine Entscheidung hängt am genauen Wert] | Messung |
| Neue Sitzung mit geänderter Aufnahme messen | Idee | [kein Ticket: Mikrofon-Empfehlung nur dokumentiert] | Messung |
| Sprecher über Sitzungen wiedererkennen (Stimmprofile) | Idee, Hauptnutzen wäre die Gewichtung pro Person ohne Handarbeit | TOOL-87 (besteht, M8) | Pipeline |
| Transkription für andere Narrata-Nutzer | Entscheidung | TOOL-85 (besteht, M7) | beide |
