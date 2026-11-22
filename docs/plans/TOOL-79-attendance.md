# TOOL-79 — Anwesenheit der Teilnehmenden aus dem Transkriptionskontext lesen

## Ziel
Die Pipeline übernimmt aus dem Narrata-Kontext ab `1.3`, wer an einer Sitzung anwesend war (`participants[].present`: `true`, `false`, `null`). Die Sprecherzuordnung nennt Anwesende zuerst und fragt nach, bevor ein Label an eine abwesende Person geht. Die Diarisierung bekommt die Zahl der Anwesenden als Obergrenze `max_speakers`. Heute ist `present` immer `None`, und pyannote sucht die Sprecherzahl ohne jede Vorgabe.

## Ist-Stand
- `src/transcript/narrata.py:62-71`: `Participant.present` existiert, Default `None`. `_participant` (`:260-284`) liest das Feld nicht.
- `src/transcript/narrata.py:32-34`: Jede `1.x` wird gelesen, `1.3`/`1.4` laufen schon durch. Zusätzliche Felder werden ignoriert.
- `src/transcript/knowledge.py:250-264`: `_participant_json` schreibt kein `present` in den Snapshot, also geht die Anwesenheit dort verloren. `load_snapshot` (`:197`) liest die Teilnehmenden über `narrata.parse_participants`.
- `src/transcript/__main__.py:532-537`: Der Konsolen-Zähler von `transcript context` zeigt Teilnehmende, Spielleitung und Ehemalige.
- `src/transcript/speaker_samples.py:144-174`: `ordered` sortiert `present is True` schon nach vorn. Die Hörliste zeigt die Spalte `membership` (`active`/`former`).
- `src/transcript/speaker_assign.py:95-103, 171-193`: Der Dialog nummeriert alle aus `ordered`. `_confirm_merge` ist das Muster für eine Rückfrage.
- `src/transcript/diarization/__init__.py:95-145`: `DiarizationRun.num_speakers` ist Teil von `matches` und damit der Wiederverwendung. Rohdatei mit `DIARIZATION_FORMAT_VERSION = 1` (`:67`), `load_run`/`to_json` bei `:425-470`.
- `src/transcript/diarization/pyannote.py:93-119`: `diarize(..., num_speakers)` reicht nur `num_speakers` an die Pipeline weiter.
- `src/transcript/reference.py:234-253, 550-560, 663-670`: `Diarization.num_speakers` in der Normalform v3.
- `src/transcript/report.py:364`: `num_speakers` fließt in die Pipeline-Angaben des Berichts und damit in den `config_hash` des Exports (`export.py:340-350`).
- `src/transcript/__main__.py:167, 182, 392, 395, 733, 798, 1328, 1574-1591`: `--num-speakers` bei `transcribe`, `diarize` und `process`. `_domain` (`:1547`) lädt den Snapshot, wenn es einen gibt.
- Narrata-Spezifikation: `ios-archiv/docs/transcripts.md:393, 412-415`. `null` heißt „unbekannt“, nie „abwesend“. Ehemalige können `true` tragen.

## Entscheidungen
- **`present` lesen:** bool oder `null`. Fehlt das Feld, gilt `None`. Jeder andere Wert ist `participants[i].present missing or invalid` (Index und Feld, kein Wert), über den bestehenden `_invalid`.
- **Snapshot:** `present` wird nur geschrieben, wenn es nicht `None` ist. Ein Snapshot aus einem Kontext ohne Anwesenheit bekommt so dieselbe `snapshot_id` wie heute, und `transcribe` wiederholt nichts. `false` und `true` bleiben unterscheidbar.
- **Sprecherzuordnung (mit Nutzerin entschieden):** Alle bleiben wählbar. Reihenfolge: anwesend, unbekannt, abwesend, innerhalb davon aktiv vor ehemalig, dann nach Name. Abwesende tragen den Zusatz `absent` (Hörliste, Dialog). Die Wahl einer abwesenden Person fragt nach (`[y/N]`, wie `_confirm_merge`). `speakers.check` bleibt unverändert, eine gespeicherte Zuordnung zu einer abwesenden Person gilt weiter.
- **Sprecherzahl (mit Nutzerin entschieden):** Als Obergrenze `max_speakers`, nicht als exakte Zahl. Ohne `--num-speakers` gilt: Ist im Snapshot jede aktive Mitgliedschaft `true` oder `false` und mindestens eine `true`, geht die Zahl der `true` (Ehemalige eingeschlossen) als `max_speakers` an pyannote. Ehemalige mit `null` zählen als nicht anwesend. Sonst bleibt `max_speakers` bei `None`. `--num-speakers` übersteuert und setzt `max_speakers` auf `None`.
- **Quelle der Obergrenze ist der Snapshot**, nicht der rohe Kontext: Er ist reproduzierbar, und `transcribe` liest ihn ohnehin (`_domain`). Ohne Snapshot keine Obergrenze.
- **Konsole:** `transcript context` ergänzt „N present, M absent“. `transcribe`/`diarize` melden `speaker limit N from attendance`, wenn eine Obergrenze greift. Beides nur als Zahlen.

## Daten-Check
- Konsole und Logs: *handled* — nur Zähler (`present`, `absent`, Obergrenze), keine Namen (TOOL-66).
- Fehlermeldungen: *handled* — ein ungültiges `present` nennt Datei, Index und Feld, nie den Wert.
- Hörliste `samples.md` und Dialog: *handled* — sie zeigen schon heute Namen, nur lokal unter `work/` bzw. im interaktiven Terminal. Neu ist nur der Zusatz `absent`.
- Fixtures: *handled* — die neuen Tests nutzen die vorhandenen erfundenen Teilnehmenden, mit `present` ergänzt.
- Repo: *N/A* — es kommen keine Sitzungsdaten hinzu.

## Contract-Check
- Kontext-Contract: *handled* — `present` laut `ios-archiv/docs/transcripts.md` seit `1.3` (IOA-1271). Der Leser akzeptiert weiter jede `1.x`, `1.0` bis `1.2` laufen ohne Feld unverändert.
- Transkript-Contract (IOA-1214): *N/A* — der Export bekommt kein neues Feld. Nur der `config_hash` ändert sich, wenn eine Obergrenze greift, weil `max_speakers` in den Pipeline-Angaben steht (`report.py:364`). Das ist gewollt: andere Einstellung, anderer Hash.
- Narrata-Änderung: *N/A* — keine, IOA-1271 ist erledigt.

## Resume-Check
- Abbruch: *handled* — unverändert. Fertige Segmente behalten ihre Rohdatei, `diarize_session` macht beim nächsten Lauf weiter.
- Wiederverwendung: *handled* — `max_speakers` kommt in `DiarizationRun.matches`. Eine Rohdatei ohne das Feld lädt mit `None` und passt weiter, solange keine Obergrenze greift. Kommt erstmals eine Anwesenheit über einen neuen Snapshot, wird jedes Segment einmal neu diarisiert (etwa 4 min auf 5 h). Danach gilt die Passagen-Neunummerierung aus TOOL-96, und Review-Entscheidungen folgen ihrer Passage.
- Gleiches Modell und gleicher Snapshot: *handled* — die Obergrenze stammt aus dem Snapshot. `transcript context` warnt schon heute, wenn der Kontext vom Snapshot abweicht (`_warn_if_snapshot_differs`).

## Dependency-Check
- *N/A* — keine neue Abhängigkeit, kein neues Modell. `max_speakers` ist ein vorhandener Parameter der pyannote-Pipeline.

## Format-Check
- Wissens-Snapshot (`SNAPSHOT_FORMAT_VERSION = 1`): *handled* — kein Bump, `present` ist optional und additiv. Alte Snapshots laden mit `None`, ihre `snapshot_id` bleibt gleich.
- Diarisierungs-Rohdatei (`DIARIZATION_FORMAT_VERSION = 1`): *handled* — kein Bump, `max_speakers` ist optional. Alte Dateien laden mit `None`.
- Normalform (`REFERENCE_FORMAT_VERSION = 3`): *handled* — kein Bump, `diarization.max_speakers` ist optional (`_optional`). Alte Dateien laden mit `None`, `docs/referenzformat.md` beschreibt das Feld.

## Chunks
### Chunk 1 — `present` lesen und im Snapshot halten
- Dateien: `src/transcript/narrata.py`, `src/transcript/knowledge.py`, `src/transcript/__main__.py` (`_context`), `tests/test_narrata.py`, `tests/test_knowledge.py`, `README.md` („Teilnehmende“)
- Änderung: `_participant` liest `present` (bool/`null`/fehlt). `_participant_json` schreibt `present`, wenn nicht `None`. Der Konsolen-Zähler bekommt „N present, M absent“. Im README entfällt „Narrata führt noch nicht“.
- Verify: `scripts/check`
- AC: Ein `1.3`-Kontext mit `true`/`false`/`null` gibt drei unterscheidbare Werte, auch nach Snapshot und `load_snapshot`. Ein `1.2`-Kontext ohne Feld gibt nur `None` und dieselbe `snapshot_id` wie vorher. `"present": "yes"` meldet `participants[0].present missing or invalid` ohne den Wert.

### Chunk 2 — Anwesenheit in Hörliste und Zuordnungsdialog
- Dateien: `src/transcript/speaker_samples.py`, `src/transcript/speaker_assign.py`, `tests/test_speaker_samples.py`, `tests/test_speaker_assign.py`, `README.md` („Sprecherzuordnung“)
- Änderung: `ordered` sortiert anwesend → unbekannt → abwesend, dann aktiv vor ehemalig, dann Name. Die Spalte `membership` und die Dialog-Hilfe ergänzen `absent`. Die Wahl einer abwesenden Person fragt nach, `N` fragt erneut nach dem Label.
- Verify: `scripts/check`
- AC: Abwesende stehen zuletzt und sind wählbar. Eine Zuordnung zu einer abwesenden Person braucht `y`. Ohne Anwesenheitsangaben bleiben Reihenfolge und Ausgabe wie heute.

### Chunk 3 — `max_speakers` aus der Anwesenheit
- Dateien: `src/transcript/diarization/__init__.py`, `src/transcript/diarization/pyannote.py`, `src/transcript/reference.py`, `src/transcript/report.py`, `src/transcript/domain.py` oder `src/transcript/knowledge.py` (Ableitung `attendance_limit(participants) -> int | None`), `src/transcript/__main__.py` (`_transcribe`, `_diarize`, `process`), `tests/test_diarization.py`, `tests/test_diarization_pyannote.py`, `tests/test_reference.py`, `tests/test_knowledge.py` bzw. `tests/test_domain.py`, `docs/referenzformat.md`, `README.md` („Diarisierung“)
- Änderung: `max_speakers` in `DiarizationRun` (Feld, `matches`, `load_run`/`to_json`), in `Diarization` der Normalform und in den Berichtsangaben. `PyannoteDiarizer.diarize` reicht es weiter. Die CLI leitet es nach der Regel aus „Entscheidungen“ ab, wenn `--num-speakers` fehlt, und meldet die Obergrenze als Zahl.
- Verify: `scripts/check`
- AC: Ein Snapshot mit vollständiger Anwesenheit (3 × `true`) ergibt `max_speakers=3` beim Diarisierer. Ein aktives `null` oder kein Snapshot ergibt `None`. `--num-speakers 4` ergibt `num_speakers=4, max_speakers=None`. Eine alte Rohdatei ohne `max_speakers` wird ohne Obergrenze wiederverwendet und mit Obergrenze neu gerechnet. Tests laufen ohne Modell.

## Folge-Tickets
- Gäste ohne Mitgliedschaft (Person-Fallback-Spieler*innen) fehlen in `participants`, die Obergrenze kann dann zu niedrig sein. [kein Ticket: `--num-speakers` übersteuert; erst anlegen, wenn es an einem echten Abend auftritt]
- Eine von Hand in `assignment.json` eingetragene Zuordnung zu einer abwesenden Person gilt ohne Warnung. [kein Ticket: Der Dialog fragt nach, die Handdatei ist die Ausnahme]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `present` lesen, Snapshot, Konsolen-Zähler | no |
| 2 | Hörliste und Zuordnungsdialog | yes |
| 3 | `max_speakers` aus der Anwesenheit | no |
