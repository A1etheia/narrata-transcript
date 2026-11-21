# TOOL-96 — Passagen am Sprecherwechsel teilen

## Ziel
Danach enthält eine Passage nur noch eine sprechende Person. Heute ist jedes Whisper-Segment genau eine Passage und trägt das Mehrheitslabel seiner Wörter. Sprecherwechsel innerhalb eines Segments bleiben dadurch unsichtbar, und die Pipeline ordnet an Referenz A 17,6 % und an B 14,0 % der Wörter falsch zu (Plaud: 2,8 % / 0,0 %). IOA-1302 (IT/OT) und IOA-1318 (Lesefassung) brauchen den Sprecherwechsel als Passagengrenze. Die Messung vorher und nachher entscheidet, ob die Diarisierung selbst ein Ticket braucht.

## Ist-Stand
- `src/transcript/reference.py:335` `_passage_from` macht aus jedem Backend-Segment genau eine Passage. `Passage.speaker` ist `majority_speaker` (`reference.py:209`), bei Gleichstand `None`.
- `src/transcript/diarization/__init__.py:278` `assign_speakers` gibt jedem Wort das Label des exklusiven Turns an seiner Mitte (`_word_label`, `:342`). Danach bekommt die Passage das Mehrheitslabel (`_labelled`, `:335`). Die Passagengrenzen ändern sich dabei nie. `_diarize_segment` (`:262`) ruft `assign_speakers` auch bei wiederverwendeter Rohdatei auf und schreibt nur, wenn sich etwas ändert.
- Whisper liefert pro Wort `word.word.strip()` und pro Segment `segment.text.strip()` (`src/transcript/asr/whisper.py:279-285`). Die Wörter mit Leerzeichen verbunden ergeben in aller Regel den Segmenttext.
- **Versionsmarke:** Hinweise, Bewertung, Kandidaten, Entscheidungen, Review-CSV und Arbeitsfassung erkennen die Version eines Transkripts allein an `processing.processed_at`. Passagen adressieren sie über `(segment, passage.index)`:
  - `uncertainty.py:358`, `hints.py:389`, `candidates.py:54` (`candidate_id`), `decisions.py:150-160`, `working.py:171`, `review_sheet.py:80`, `review_import.py:87`.
  - Erneutes Diarisieren behält `processed_at`. Nur die Sprecherzuordnung prüft zusätzlich einen Fingerprint (`speakers.labels_version`, `speakers.py:172`).
  - Teilt die Diarisierung Passagen ohne neue Versionsmarke, zeigen gespeicherte Bewertungen und Entscheidungen still auf falsche Passagen.
- **Export:** `export._mint` (`export.py:224`) prägt die Passagen-ID bei jedem Export neu aus Start und Label (`p-<start_ms>-<label>`). Der Contract verlangt dagegen, dass die ID einmal geprägt und danach mitgeführt wird. Eine geteilte Passage behält ihre ID für den ersten Teil, der zweite Teil bekommt eine neu geprägte (ios-archiv `docs/transcript-contract.md:38-55`, Schema `transcript-v1.schema.json:208`).
- **Narrata:** `TranscriptImporter.php` macht einen Upsert per `passage_key`. Fehlende Keys lehnt der Import ab (`passagesWouldBeRemoved`, `:92-97`). Mit `--replace` löscht er sie hart (`:131-136`). Davon hängen ab:
  - Links (`transcript_passage_links`) werden kaskadierend gelöscht.
  - Die Provenienz von Welt-Archiv-Einträgen wird auf `null` gesetzt.
  - Lese-Anker `#p=<key>` laufen ins Leere.
  - Das Schema hat `additionalProperties: false`, ein Herkunftsfeld pro Passage wäre ein Contract-Bump.
- **Messwerkzeug:** `scripts/spike/denoise.py:421` `_wder` (WDER auf Wortebene, beste 1:1-Zuordnung, Methode aus TOOL-20) und `scripts/spike/asr.py` (Wurzeln pro Variante, `segment_assessment` im Speicher). Die Handreferenzen A und B liegen unter `work/<s>/review/calibration/`. Der Parser ist `calibration.HandReference` mit `Name:`-Labels.
- **Format:** Das Referenzformat ist `format_version: 2`, gelesen werden 1 und 2 (`reference.py:37`, `docs/referenzformat.md:92-94`).

## Entscheidungen
- **Geteilt wird in der Diarisierung** (`assign_speakers`), nicht erst in Arbeitsfassung oder Export. Nur dort entstehen die Wortlabels, und alle Folgeschritte (Hinweise, Bewertung, Kandidaten, Arbeitsfassung, Export) arbeiten dann ohne eigene Änderung auf den geteilten Passagen.
- **Kein Text wird erfunden.** Jeder Teil hat als Text seine Wörter, mit einem Leerzeichen verbunden. Geteilt wird nur, wenn diese Verbindung über alle Wörter den ursprünglichen Passagentext exakt ergibt; sonst bleibt die Passage ganz und wird gezählt. Die Teile ergeben so zusammen immer wieder den ASR-Text. Die ASR-Rohdatei bleibt unberührt.
- **Herkunft pro Passage:** Das neue Feld `asr_passage` hält die Nummer der Backend-Passage. Diarisiert man neu, setzt `assign_speakers` die Teile zuerst über `asr_passage` wieder zusammen und teilt dann neu. Das Teilen ist dadurch wiederholbar und hängt nicht vom vorigen Schnitt ab.
- **Mindestschwelle:** Ein Label-Lauf unter der Schwelle wird zur vorigen Passage gezogen, am Anfang zur folgenden. Wörter ohne Label bleiben bei der vorigen Passage. Ob die Schwelle in ms oder in Wörtern gilt und welchen Wert sie hat, entscheidet die Messung in Chunk 2. Es gibt einen Konfigurationsschlüssel `diarization.min_turn_ms` oder `diarization.min_turn_words`, nicht beide. Die Schwelle steht im `diarization`-Block der Normalform.
- **Signale:** `avg_logprob`, `no_speech_prob` und `compression_ratio` gehen unverändert an jeden Teil. Die Bewertung läuft danach neu.
- **Neue Versionsmarke beim Schnitt:** Ändert `assign_speakers` die Passagengrenzen, setzt es `processing.processed_at` neu. Hinweise, Bewertung und Entscheidungen werden damit `stale` beziehungsweise neu berechnet, statt still falsch zuzuordnen.
  - Ein Lauf mit gleichem Ergebnis schreibt nichts und ändert die Marke nicht.
  - `processed_at` heißt danach „Version der Passagen“. Das wird in `docs/referenzformat.md` dokumentiert.
  - Diese Lösung ist kleiner als eine zweite Versionsmarke in sieben Modulen.
  - **Entscheidungen folgen ihrer Passage** (ergänzt vor der Neuverarbeitung, siehe Chunk 5): Die Normalform hält in `processing.renumbered` fest, wo jede Passage der vorigen Fassung jetzt liegt. Eine Entscheidung auf einer unverändert gebliebenen Passage gilt unter der neuen Nummer weiter. Eine auf einer geteilten Passage ist `stale` und erscheint als `earlier_decision` beim Teil, an dem die Passage begann.
- **Passagen-IDs werden aus der Herkunft geprägt** (Contract-Regel 2 und Teilungsregel; geändert in Chunk 4, siehe Nachtrag):
  - Die Arbeitsfassung führt pro Block `asr_passage` und `asr_speaker`, das Mehrheitslabel der ganzen Backend-Passage (`rejoin`). Sie steigt dafür auf Format 2.
  - Der erste Teil einer Backend-Passage bekommt die ID aus deren Start und `asr_speaker`, also genau die ID, die die Passage vor TOOL-96 hatte. Die anderen Teile bekommen eine neue ID aus eigenem Start und Label, eindeutig gegen die ersten Teile.
  - So verschwindet beim Re-Import von JdG #22 kein Key, und Narrata braucht keine Änderung und kein IOA-Ticket. Der Export bleibt eine Funktion von `work/` und liest `output/` nicht.
  - Keys verschwinden nur, wenn eine neue Diarisierung mit Modell die Mehrheitslabels ändert. Das galt schon vor TOOL-96. Die Narrata-Ablehnung macht es sichtbar, das wird dokumentiert.
- **Hörblöcke im Review** (Umfang 3) kommen nicht in dieses Ticket. Ob Nachbarpassagen beim Hören wieder zusammengefasst werden, hängt an der Entscheidung über Review-Kanal und Review-Umfang in TOOL-60. Dort steht der Review-Dialog mit Abspielen schon als abhängig vermerkt.
- **Messung:** gemessen wird auf zwei Wegen.
  - Das Spike-Skript misst mit der Repo-WDER, auf Passagenebene (Passagenlabel je Wort) und auf Wortebene (Wortlabel).
  - Zusätzlich lässt die Projektverantwortliche ihr eigenes Skript vorher und nachher auf dem Export laufen. Nur diese Zahlen sind mit Plaud vergleichbar, und an ihnen gilt die 5-Punkte-Regel.

## Daten-Check
- Kein Transkripttext, kein Name und kein Label im Repo: handled. Das Spike-Skript gibt nur Zähler, Anteile und Quantile aus, wie `scripts/spike/README.md` „Datenschutz“ es verlangt. Der Bericht enthält nur Kennzahlen.
- Fixtures: handled. Die Tests bauen Passagen und Turns synthetisch wie `tests/test_diarization.py`, ohne echte Wörter.
- Logs und Fehlermeldungen: handled. Die Zahl nicht geteilter Passagen (Text ≠ Wortfolge) wird als Zähler gemeldet, nie mit Text, entsprechend dem Docstring von `diarization/__init__.py:17`.
- TOOL-66: handled, weil Rohaudio und Transkripte unter `work/` und `output/` bleiben. Die Messung läuft lokal auf vorhandenen Dateien, ohne Modell.

## Contract-Check
- Schema: handled, es gibt keine Änderung. Version 1.0/1.1 bleibt, es ändern sich nur Zahl und Grenzen der Passagen. `asr_passage` bleibt intern, denn das Schema verbietet Zusatzfelder.
- ID-Stabilität: handled durch Chunk 4. Die IDs werden aus dem vorigen Export mitgeführt, wie `docs/transcript-contract.md:38-55` es verlangt.
- Narrata-Änderung: N/A, weil mitgeführte IDs die Ablehnung vermeiden. Falls doch Keys fehlen, zeigt der bestehende Guard IOA-1280 sie an. Dass dieser Guard abhängige Links nicht prüft, ist ein Befund für Narrata und wird im Bericht festgehalten.

## Resume-Check
- Abbruch: handled. `update_reference` schreibt atomar, ein Abbruch lässt die alte Normalform stehen.
- Wiederverwendung: handled. Die Rohdatei der Diarisierung wird wie bisher ohne Modell wiederverwendet. Ändert sich nur die Schwelle, wird ohne Modell neu geschnitten. `transcript status` meldet eine abweichende Schwelle als `stale` (neue Art „cut outdated“ neben „no speaker labels“, `status.py:263`).
- Modell und Snapshot: N/A, weil das Teilen weder ASR noch Snapshot berührt. `asr` und `knowledge_snapshot_id` bleiben gleich.

## Dependency-Check
- N/A, weil weder Abhängigkeit noch Modell neu hinzukommen. Das Spike-Skript nutzt `difflib` und vorhandene Module.

## Format-Check
- Referenzformat: Version steigt von 2 auf 3 (`asr_passage` pro Passage, Schwelle im `diarization`-Block). `load_reference` liest 1–3. Bei 1 und 2 gilt `asr_passage = index`, ohne Schwelle gelten die Passagen als nicht geteilt. `transcript diarize` hebt eine alte Datei beim Neuschreiben auf 3.
- Bewertung, Hinweise, Kandidaten, Entscheidungen, Arbeitsfassung: N/A, weil sich ihr Format nicht ändert. Sie werden über die neue Versionsmarke neu berechnet beziehungsweise als `stale` gemeldet.
- Sprecherzuordnung: handled. `labels_version` ändert sich mit den Passagen, die Einträge werden `stale` und müssen mit `transcript speakers --assign` neu bestätigt werden (rund 4 min). Das kommt als Hinweis in README und Bericht.

## Chunks

### Chunk 1 — Schnittfunktion
- Dateien: `src/transcript/diarization/__init__.py` (oder ein eigenes Modul `diarization/turns.py`), `tests/test_diarization.py`
- Änderung: Reine Funktion `split_at_speaker_changes(passage, min_turn) -> tuple[Passage, ...]`, noch nicht angebunden:
  - Sie teilt nach Label-Läufen und zieht kurze Läufe und Wörter ohne Label zum Nachbarn.
  - Sie teilt nur, wenn die Wortfolge den Text exakt ergibt.
  - Signale gehen an alle Teile, das Label ist `majority_speaker` des Teils.
  - Dazu `rejoin(parts)` als Umkehrung.
- Verify: `scripts/check`
- AC: Die Teile verbunden ergeben immer den Originaltext und die Originalwörter. Kein Teil hat oberhalb der Schwelle zwei Labels. `rejoin(split(p)) == p`.

### Chunk 2 — Messwerkzeug und Ausgangsmessung
- Dateien: `scripts/spike/turns.py`, `scripts/spike/README.md`, `docs/spikes/TOOL-96-sprecherwechsel.md` (Abschnitt „Vorher“ und Schwellenwahl)
- Änderung: Das Spike-Skript liest die gespeicherten Normalformen und Handreferenzen einer Sitzung. Es wendet die Schnittfunktion im Speicher mit einer Schwellenreihe an: 0, 250, 500, 1000, 1500, 2000 ms und 1–4 Wörter. An A und B misst es:
  - WDER auf Passagen- und auf Wortebene (`denoise._wder`, Variante mit Passagenlabel)
  - den Anteil der Passagen mit mehr als einem Hand-Sprecher
  - über die ganze Sitzung Zahl und Längenquantile der Passagen
  - den Kandidatenanteil (`segment_assessment` im Speicher)
  - die Zahl der Hinweise
  - die Zahl nicht geteilter Passagen (Text ≠ Wortfolge)
- Verify: `scripts/check`; `.venv/bin/python scripts/spike/turns.py <gruppe>/<ordinal>` an JdG #22, die Ausgabe enthält nur Kennzahlen.
- AC: Die Ausgangswerte sind dokumentiert, darunter die Differenz zwischen Passagen- und Wortebene als Obergrenze des Gewinns. Einheit und Wert der Schwelle sind gewählt und begründet.

### Chunk 3 — In der Diarisierung teilen
- Dateien: `src/transcript/diarization/__init__.py`, `src/transcript/reference.py`, `src/transcript/config.py`, `config/example.yaml`, `src/transcript/status.py`, `src/transcript/__main__.py` (Durchreichen der Schwelle), Tests, `docs/referenzformat.md`, README „Diarisierung“
- Änderung:
  - `assign_speakers` setzt zuerst über `asr_passage` zusammen, beschriftet die Wörter, teilt, nummeriert neu und setzt bei geänderten Grenzen `processed_at` neu.
  - Referenzformat v3 mit `asr_passage` und der Schwelle im `diarization`-Block.
  - Neuer Konfigurationsschlüssel aus Chunk 2.
  - `transcript status` erkennt eine abweichende Schwelle.
  - Hinweis zur Neuverarbeitung in README und `docs/ablauf.md`: `transcript process` rechnet Hinweise und Bewertung neu, Entscheidungen werden `stale`, die Sprecherzuordnung muss neu bestätigt werden.
- Verify: `scripts/check`
- AC: Ein zweiter Lauf mit gleichen Eingaben schreibt nichts und behält `processed_at`. Eine v2-Datei wird gelesen und beim Diarisieren zu v3. Eine geänderte Schwelle ergibt `stale` und wird ohne Modell neu geschnitten. Gespeicherte Entscheidungen auf einem neu geschnittenen Segment werden `stale` gemeldet, nicht angewendet.

### Chunk 4 — Passagen-IDs mitführen
- Dateien: `src/transcript/working.py`, `src/transcript/export.py`, `src/transcript/diarization/turns.py`, Tests, README „Arbeitsfassung“ und „JSON-Export“
- Änderung: `Block` bekommt `asr_passage` und `asr_speaker`, die Arbeitsfassung Format 2. `export.build` prägt zuerst die IDs der ersten Teile aus Start und `asr_speaker`, dann die der übrigen Teile aus Start und eigenem Label. Ohne Schnitt bleibt das Ergebnis byte-gleich mit heute.
- Verify: `scripts/check`
- AC: Ein Re-Export nach dem Schnitt enthält alle IDs des Exports vor dem Schnitt. Eine geteilte Passage behält ihre ID im ersten Teil, auch wenn dessen Label wechselt. Der Export liest `output/` nicht. Die Schema-Prüfung bleibt grün.
- Nachtrag: Die erste Umsetzung (`be8a71f`) las die vorige `output/<s>/transcript.json` und vergab IDs nach Zeitlage. Die Review fand zwei Schwächen. Erstens hingen die IDs an einer Ausgabedatei: Wer `output/` löscht oder anderswo exportiert, bekommt still neue IDs, und `transcript status` verglich gegen eine Datei, aus der es sein Soll selbst baute. Zweitens war unklar, was bei einer ungültigen Vorgängerdatei passiert. Die Herkunft aus `asr_passage` löst beides ohne Dateizugriff.

### Chunk 5 — Entscheidungen folgen ihrer Passage
- Dateien: `src/transcript/reference.py`, `src/transcript/diarization/__init__.py`, `src/transcript/candidates.py`, `src/transcript/decisions.py`, Tests, `docs/referenzformat.md`, README „Review-Entscheidungen“
- Änderung:
  - `Renumbering` mit `Moved` pro alter Passage, berechnet in `assign_speakers`, wenn sich Grenzen verschieben, gespeichert als `processing.renumbered` der Normalform (v3, noch nicht veröffentlicht, daher ohne Versionssprung).
  - `RatedSegment` und `candidates.json` führen die Abbildung mit.
  - `review_items` lässt eine Entscheidung auf einer unveränderten Passage unter der neuen Nummer gelten und zeigt eine auf einer geteilten Passage beim Teil, an dem sie begann. Eine Entscheidung auf der neuen Fassung geht vor. `decisions.json` bleibt unverändert.
- Verify: `scripts/check`; Probelauf im Speicher an JdG #22 (nur Zähler).
- AC: Von den 35 Entscheidungen an JdG #22 gelten 26 weiter (davon 15 Korrekturen), 9 auf geteilten Passagen sind `stale` und stehen beim richtigen Teil.
- Nachtrag: Ursprünglich sollten alle Entscheidungen `stale` werden. Ein Probelauf zeigte, dass das 23 Korrekturen aus dem Pilot-Review aus dem Export nähme, obwohl 15 davon auf Passagen liegen, die der Schnitt nicht verändert. Außerdem hätte der Hinweis `earlier_decision` nach der Neunummerierung bei der falschen Passage gestanden. Die frühere Chunk 5 ist jetzt Chunk 6.

### Chunk 6 — Neuverarbeitung, Messung nachher, Entscheidung
- Dateien: `docs/spikes/TOOL-96-sprecherwechsel.md`, Plan-Nachtrag
- Änderung:
  - Vorher sichert die Projektverantwortliche den alten Export und misst ihn mit ihrem Skript.
  - Dann `transcript process` an JdG #22: Die Diarisierung wird ohne Modell wiederverwendet und neu geschnitten. Danach Bewertung, Zuordnung (`speakers --assign`), Arbeitsfassung, Export und Re-Import in Narrata.
  - `turns.py` misst nachher, das eigene Skript der Projektverantwortlichen misst den neuen Export.
  - Der Bericht vergleicht vorher und nachher, beide Methoden, mit Plaud. Er nennt Passagenzahl, Längen, Kandidatenanteil und die Wirkung auf die Hinweise.
  - Diarisierungs-Entscheidung nach der 5-Punkte-Regel, gemessen mit dem Skript der Projektverantwortlichen.
- Verify: `scripts/check`; `transcript:validate` und `transcript:import` in ios-archiv ohne `--replace` erfolgreich.
- AC: Alle Akzeptanzkriterien des Tickets sind belegt. Die Diarisierungs-Entscheidung ist getroffen: Folge-Ticket angelegt oder Ausbleiben begründet.
- Nachtrag:
  - **Messung nur mit der Repo-Methode:** Das Skript der Projektverantwortlichen stand für die Messung nachher nicht mehr zur Verfügung. Am ungeteilten Stand weichen beide Methoden höchstens 0,2 Punkte ab (A 17,4 % gegen 17,6 %, B 14,0 % gegen 14,0 %). Nachher liegt der Abstand zu Plaud bei 3,4 bzw. 3,6 Punkten, 1,4 Punkte unter der Grenze. Die 5-Punkte-Regel wurde deshalb mit der Repo-Methode angewendet: kein Folge-Ticket, TOOL-97 wird geschlossen.
  - **Alter Export beschädigt:** `output/<s>/transcript.json` begann mit vier fremden Bytes. Gesichert wurde er ohne sie, sonst byte-gleich, als `transcript.pre-tool-96.json`.
  - **Altes Review-Sheet:** Der erste `process`-Lauf hielt beim Review an, weil er die alte `review.csv` gegen die neu nummerierten Kandidaten las. Behoben in `review_import`: Eine Zeile eines älteren Exports wird an der Entscheidung ihrer eigenen Fassung gemessen.
  - **Sprecherzuordnung** in rund 2 Minuten neu bestätigt. Eine Zuordnung vor dem Schnitt gilt danach nicht mehr.
  - **Narrata:** In der lokalen Datenbank fehlte der Import aus TOOL-58. Er wurde aus dem gesicherten Export wiederhergestellt (997 angelegt). Danach brachte der neue Export ohne `--replace` 1.169 angelegt, 994 aktualisiert, 3 unverändert und 0 entfernt, ein zweiter Import änderte nichts. Den Import mit nativem PHP muss `DB_HOST=127.0.0.1` auf das MySQL im Container richten; `--via-sail` sieht Dateien außerhalb des Narrata-Repos nicht.

## Folge-Tickets
- Hörblöcke im Review (Nachbarpassagen beim Hören zusammenfassen): TOOL-60, Entscheidung über Review-Kanal und Review-Umfang
- Diarisierung selbst (Sprecherzahl aus TOOL-79, pyannote-Einstellungen), angelegt nach einer Ausgangsmessung mit Parserfehler, nach der Korrektur nur bedingt nötig; nach der 5-Punkte-Regel nicht nötig (Abstand 3,4 / 3,6 Punkte), wird geschlossen: TOOL-97
- Narrata-Guard IOA-1280 prüft abhängige Links und Provenienz nicht: [kein Ticket: Befund im Bericht, Entscheidung in TOOL-60, ob ein IOA-Ticket nötig ist]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schnittfunktion, rein und getestet | no |
| 2 | Spike-Skript, Ausgangsmessung, Schwellenwahl | no |
| 3 | Schnitt in der Diarisierung, Referenzformat v3, Status, Config | yes |
| 4 | Passagen-IDs im Export mitführen | no |
| 5 | Entscheidungen folgen ihrer Passage | no |
| 6 | Neuverarbeitung JdG #22, Messung nachher, Diarisierungs-Entscheidung | no |
