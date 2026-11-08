# TOOL-68 — Sprecher-Labels manuell Teilnehmer*innen zuordnen

## Ziel
Die Diarisierung (TOOL-76) liefert pro Aufnahme generische Labels (`SPEAKER_00`). Wer sich hinter einem Label verbirgt, kann heute nirgends festgehalten werden. Danach erzeugt `transcript speakers <session>` pro Label eine Hörliste mit den redezeitreichsten Passagen und Zeitangaben. Die Zuordnung Label → Teilnehmer*in steht in einer eigenen, versionierten Datei. Eine geprüfte Lese-Schnittstelle liefert für jede Passage Label und Person. TOOL-49 (Arbeitsfassung) und TOOL-69 (Export) binden diese Schnittstelle ein, TOOL-59 liest den erfassten Aufwand.

## Ist-Stand
- `src/transcript/reference.py:49-71`: `Word.speaker` und `Passage.speaker` (Mehrheitslabel, `majority_speaker` `:209`), `None` ist gültig. `Diarization.labels` (`:136-145`) enthält alle Labels eines Segments. `update_reference` (`:293`) schreibt nach `diarize` nur die Normalform neu. `processing.processed_at` ändert sich dabei **nicht**.
- `docs/referenzformat.md:81-90`: Labels gelten pro Segment. Die Zuordnung zu Personen „kommt nicht in diese Datei“.
- `src/transcript/knowledge.py:65-75,164`: `Snapshot.participants` (eingefroren, mit `snapshot_id`). `src/transcript/narrata.py:63-71`: `Participant(user_id, display_name, role, is_former, characters, present=None)`.
- `src/transcript/session_time.py:40-56`: `segment_of`, `passage_span` → `SessionSpan.timecode()`. `src/transcript/timecode.py:16` `format_ms`.
- `src/transcript/decisions.py`: Vorbild für eine handgemachte, versionierte Datei neben Pipeline-Daten (`format_version`, Session-Prüfung, Meldungen ohne Inhalt, `write_atomic`, veraltet/verwaist statt löschen).
- `src/transcript/candidates.py:126-159`: Muster „alle transkribierten Segmente des Manifests laden“ (`_transcribed`).
- `src/transcript/session.py:102-135`: Pfade unter `work/<s>/`, noch keiner für Sprecher.
- `src/transcript/__main__.py:196-271,737-761`: Subcommand-Muster (`_require`, `_load_config`, Exit 0/2, nur Zähler auf der Konsole).
- Contract (ios-archiv `docs/transcript-contract.md:80-95`): `speakers.<label>` → `{participant_id, display_name}` oder `null`, `passages[].speaker_label` (string, Pflicht), `passages[].participant_id`.

## Entscheidungen
- **Schlüssel ist (Segment, Label).** Labels gelten nur pro Aufnahme (TOOL-76). Zwei Aufnahmen werden „zusammengeführt“, indem ihre Labels derselben Person zugeordnet werden. Ein automatisches Abgleichen über Segmente hinweg gibt es nicht.
- **Kandidaten aus dem Wissens-Snapshot**, nicht direkt aus `read_participants`. Der Snapshot ist eingefroren und gehört ohnehin zum reproduzierbaren Satz von TOOL-49. Inhaltlich sind es dieselben Teilnehmenden wie bei TOOL-38: aktive zuerst, Ehemalige wählbar. `present` wird nicht ausgewertet (bis TOOL-79 `None`).
- **Neue Datei `work/<s>/speakers/assignment.json`** (`format_version: 1`), getrennt von ASR, Diarisierung und Review. Inhalt: `session`, `effort_minutes` (int|null, von Hand, für TOOL-59), `entries: [{segment, label, labels_version, assigned, user_id}]`. Für `assigned` gibt es vier Werte:
  - `person` (mit `user_id`)
  - `unknown`
  - `multiple` (Übersprechen)
  - `open`

  Bei `person` ist `user_id` Pflicht, sonst verboten.
- **Nur die Vorlage schreibt das Werkzeug.** Fehlt die Datei, entsteht sie mit einem `open`-Eintrag pro (Segment, Label). Eine vorhandene Datei wird nie überschrieben oder ergänzt, denn sie ist Handarbeit. Labels ohne Eintrag gelten als `open`.
- **`labels_version` statt `processed_at`**, weil `diarize` `processed_at` nicht ändert. Gemeint ist ein kurzer SHA-256 über `processed_at`, `diarization.labels` und die Labelfolge aller Wörter und Passagen eines Segments. Nach einer Neutranskription oder einer abweichenden Neudiarisierung ist ein Eintrag **veraltet**. Er bleibt in der Datei, wird gemeldet und nicht angewendet. Eine wiederverwendete Diarisierung lässt ihn gültig.
- **Prüfen beim Laden und Anwenden.**
  - Harte Fehler (Exit 2): falsche Version, fremde Session, doppelter (Segment, Label)-Eintrag, ungültiges `assigned` oder `user_id`.
  - Befunde (Exit 1, Eintrag nicht angewendet, Label bleibt Label): unbekanntes Segment, unbekanntes Label, unbekannte Person (nicht im Snapshot), veraltet.
  - Warnung (Exit 0): mehrere Labels **eines** Segments auf dieselbe Person. Das ist gewollt bei einem Diarisierungs-Split und wird zusammengeführt. Dieselbe Person in verschiedenen Segmenten ist normal und bleibt ohne Warnung.
  - Dieser Teil löst auch die Übergabe aus TOOL-42 ein (Referenzen auf unbekannte Sprecher).
- **Schnittstelle für TOOL-49/69:** `SpeakerMap.resolve(segment, label) -> SpeakerRef(segment, label, assigned, user_id)`. `label=None` und alles, was nicht gültig `person` ist, ergibt `user_id=None`. Es wird nie eine Person geraten. Dazu kommt `SpeakerMap.persons()` (user_id → Labels), damit zusammengeführte Labels sichtbar sind.
- **Hörliste `work/<s>/speakers/samples.md`**, bei jedem Lauf neu geschrieben, Markdown zum Lesen und nicht zum Reimport. Pro (Segment, Label) enthält sie:
  - die Redezeit aus der Summe der Wortdauern dieses Labels, ohne Wortzeiten aus Passagendauern
  - den Anteil an der Segment-Redezeit
  - die 5 längsten Passagen mit diesem Mehrheitslabel: Session-Zeit (`passage_span(...).timecode()`), WAV-Datei mit lokaler Zeit, Text
  - einen Vermerk „Kandidat für Zusammenlegung“ unter 3 % Anteil (`MERGE_SHARE`, Konstante)

  Oben stehen die Kandidaten aus dem Snapshot (user_id, Anzeigename, Rolle, aktiv/ehemalig) und der aktuelle Stand der Zuordnung.
- **Ein Befehl `transcript speakers <session>`**: schreibt die Hörliste, legt bei Bedarf die Vorlage an, prüft eine vorhandene Zuordnung und gibt Zähler aus. Voraussetzung sind Manifest, Snapshot und mindestens ein transkribiertes Segment mit `diarization`.
- **Arbeitsfassung und Export** (AC 5) liefert TOOL-68 nur als Schnittstelle. TOOL-49 und TOOL-69 bauen sie ein (Entscheidung mit der Nutzerin).

## Daten-Check
- TOOL-66: handled. `assignment.json` enthält User-IDs, `samples.md` Text und Anzeigenamen, beide nur unter `work/` (gitignored).
- Konsole und Fehler: handled. Sie nennen nur Zähler, Segmentnummern, Eintragsnummern und Felder, nie Labels, Namen, User-IDs oder Text. Labels lässt TOOL-76 auf der Konsole ebenfalls weg.
- Fixtures/Tests: handled. Sie arbeiten mit synthetischen Referenzen und Snapshots wie in `tests/test_candidates.py` und `tests/test_knowledge.py`, mit erfundenen Namen.
- Logs: handled. Das Modul loggt nichts.
- Auswertung pro Person (Opt-in): N/A, weil hier keine Statistik entsteht. Redeanteile pro Person gehören zu TOOL-53/IOA-1216.

## Contract-Check
- TOOL-68 schreibt kein Contract-JSON. Die Schnittstelle passt aber zu IOA-1214 1.x: `participant_id` ist `participants[].user_id` (`transcript-contract.md:82,121`). Zusammengeführte Labels bekommen dieselbe `participant_id`. `unknown`, `multiple` und `open` ergeben `speakers.<label>: null` bzw. `participant_id: null`.
- Für TOOL-69 offen, als Übergabe: Contract-Labels sind sessionweite Keys, unsere gelten pro Segment. TOOL-69 braucht also ein sessionweites Label (z. B. `s01-speaker-00`). Ebenso offen ist, wie Passagen ohne Label (`speaker_label` ist Pflicht-String) und `multiple` (→ Marker `crosstalk`?) abgebildet werden. Narrata braucht für TOOL-68 keine Änderung.

## Resume-Check
- N/A, weil kein Modell und keine lange Laufzeit beteiligt sind. Geschrieben wird atomar (`write_atomic`), die Hörliste lässt sich jederzeit neu erzeugen, und die Zuordnung wird nie vom Werkzeug überschrieben.

## Format-Check
- handled. Neues Format `assignment.json` v1, der Loader lehnt andere Versionen ab. Das Referenzformat bleibt v2 und unverändert. Bestehende Artefakte gibt es keine.

## Chunks
### Chunk 1 — Zuordnungsmodell und Prüfung
- Dateien: `src/transcript/speakers.py`, `src/transcript/session.py` (`speakers_dir`, `speaker_assignment`, `speaker_samples`), `tests/test_speakers.py`
- Änderung: `Assigned`-Literal, `AssignmentEntry`, `SpeakerAssignment` (inkl. `effort_minutes`), `labels_version(reference)`, `load_assignment`/`write_template`, `check(assignment, references, snapshot) -> SpeakerMap` mit Befunden (unbekanntes Segment/Label/Person, veraltet) und Warnungen (Split in einem Segment), `SpeakerMap.resolve`/`persons`.
- Verify: `scripts/check`
- AC:
  - Jedes Label lässt sich `person`/`unknown`/`multiple` zuordnen.
  - Zwei Labels → eine Person liefert dieselbe `user_id` und eine Warnung.
  - Ein unbekanntes Label, eine unbekannte Person oder ein veralteter Eintrag wird gemeldet, nicht angewendet und `resolve` liefert `user_id=None`.
  - `label=None` → `user_id=None`.
  - Die Referenzdateien bleiben byteweise unverändert.
  - Falsche Version oder Session wird abgelehnt.
  - Meldungen enthalten weder Label noch Name noch ID.

### Chunk 2 — Hörliste und CLI
- Dateien: `src/transcript/speaker_samples.py`, `src/transcript/__main__.py` (`speakers`), `tests/test_speaker_samples.py`, `tests/test_cli.py` (bzw. die bestehende CLI-Testdatei)
- Änderung: Redezeit pro (Segment, Label), Top-5-Passagen mit Session- und WAV-Zeit, Zusammenlegungs-Kandidaten, Kandidatenliste aus dem Snapshot (aktive zuerst), Markdown-Ausgabe. `transcript speakers` schreibt `samples.md`, legt die Vorlage nur an, wenn sie fehlt, und prüft eine vorhandene Zuordnung. Exit 0/1/2, auf der Konsole nur Zähler.
- Verify: `scripts/check`
- AC:
  - Pro Label stehen höchstens 5 Passagen in der Liste, absteigend nach Redezeit, mit absoluter Zeit.
  - Ein Label unter 3 % ist markiert.
  - Eine vorhandene `assignment.json` bleibt byteweise unverändert.
  - Fehlt der Snapshot, endet der Befehl mit Exit 2 und dem Hinweis `transcript snapshot`.
  - Die Konsole zeigt weder Text noch Labels.

### Chunk 3 — Dokumentation
- Dateien: `README.md` (Abschnitt „Sprecherzuordnung“ nach „Diarisierung“, Satz `:238` anpassen, Verzeichnisstruktur `speakers/`), `docs/referenzformat.md:87` (Verweis), `docs/transcript-roadmap.py` (Hinweis TOOL-68, `.md` neu generieren)
- Änderung: Ablauf (Hörliste → Zuordnung von Hand → prüfen), Werte von `assigned`, `effort_minutes`, veraltet, Warnungen.
- Verify: `scripts/check`
- AC: Das README beschreibt den Ablauf und alle `assigned`-Werte und sagt, dass nicht zugeordnete Labels Label bleiben.

## Folge-Tickets
- Schnittstelle `SpeakerMap` in die Arbeitsfassung einbauen: TOOL-49 (Übergabekommentar)
- Sessionweite Labels, Passagen ohne Label und `multiple` im Contract abbilden: TOOL-69 (Übergabekommentar)
- `effort_minutes` im Bericht auswerten: TOOL-59 (Übergabekommentar)
- Gewichtung der Unsicherheit pro Person (Mundart 47,5 % gegen 14,0 % falsche Wörter, aus TOOL-36): `[kein Ticket: Übergabe an TOOL-60; ob die Gewichtung nötig ist, zeigt der Pilot]`
- Automatischer Label-Abgleich über Aufnahmen hinweg: `[kein Ticket: nicht V0.1, manuell bei 4–6 Personen billig]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `speakers.py`: Format, Prüfung, Schnittstelle | no |
| 2 | Hörliste, `transcript speakers` | no |
| 3 | README, Referenzformat, Roadmap | no |
