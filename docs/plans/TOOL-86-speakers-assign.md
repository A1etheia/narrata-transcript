# TOOL-86 — Sprecher-Labels interaktiv zuordnen (`transcript speakers --assign`)

## Ziel
Danach ordnet `transcript speakers <session> --assign` alle offenen Labels einer Session im Terminal zu: Kennzahlen und Passagen ansehen, Hörprobe lokal abspielen, Person aus dem Snapshot oder `unknown`/`multiple` wählen. Jede Wahl wird sofort atomar gespeichert. Heute muss man Zeiten aus `samples.md` in einem Player suchen und `user_id`s von Hand in `assignment.json` tippen.

## Ist-Stand
- CLI: `_speakers` in `src/transcript/__main__.py:958-1004` schreibt die Vorlage, prüft (`speakers.check`) und rendert `samples.md`. Parser `__main__.py:238-243` hat nur `session`. Exit 0/1/2.
- Format: `speakers.py:37` `ASSIGNMENT_FORMAT_VERSION = 1`, `Assigned` = `open|person|unknown|multiple` (`:39-44`), `AssignmentEntry` (`:56-73`), `SpeakerAssignment` mit `effort_minutes` (`:76-86`). `write_template` schreibt nie über eine vorhandene Datei (`:276-283`); `write_assignment` ersetzt sie komplett (`:286-296`); `_entry_from` verwirft Zusatzfelder (`:319-331`).
- Prüfung: `check`/`_finding` (`speakers.py:210-249`) mit `unknown_segment`, `unknown_label`, `stale`, `unknown_person`; Splits (`:252`).
- Hörliste: `speaker_samples.label_samples` (`speaker_samples.py:82-120`) liefert pro Label Redezeit, Anteil, `merge_candidate` (`:55`) und die 5 längsten Passagen mit `local_start_ms` (WAV-lokal) und Sessionzeit; ein lokales Ende fehlt.
- Teilnehmende: `knowledge.load_snapshot` (`knowledge.py:173`), `Participant` mit `is_former`, `present` (`narrata.py:63-71`).
- WAV: `SessionPaths.segment_wav(i)` (`session.py:106-108`).
- Atomar: `jsonfile.write_atomic` (`jsonfile.py:140-153`, `indent=2`).
- Werkzeuge: `audio_tools._TOOLS = ("ffmpeg", "ffprobe")` (`audio_tools.py:10`); Preflight kennt `warning` (`preflight.py:30`). `ffplay` und `isatty` kommen im Code nicht vor.
- Haltanweisung: `_print_halt` (`__main__.py:1322-1337`) verweist auf Handbearbeitung; Test `tests/test_process.py:86`.
- Datenschutz: `docs/datenschutz.md:37` (Logs/Meldungen nur Session-Keys, Passage-IDs, Zeiten, Zähler).
- Tests: `tests/test_speakers.py`, `tests/test_speaker_samples.py`, CLI in `tests/test_smoke.py` (~1661-1780).
- Narrata (ios-archiv): Kandidaten kommen aus `participants[]` des Transkriptionskontexts inkl. `is_former` (`docs/transcripts.md:251-270`); der Import akzeptiert Ehemalige und lehnt IDs ohne Mitgliedschaft ab (`TranscriptImporter.php:224-258`).

## Entscheidungen
- **Reihenfolge:** Segmente aufsteigend, darin Labels nach Redezeit absteigend. Standardmäßig nur Labels ohne angewendeten Eintrag (fehlend, `open`, `stale`); `--all` nimmt auch zugeordnete dazu.
- **Kandidaten:** Anwesende (`present is True`) zuerst, dann aktive, dann ehemalige Mitglieder, je nach Anzeigename; nummeriert. Dazu `u` = `unknown`, `m` = `multiple`, `s` = überspringen (bleibt `open`), `q` = beenden. Ehemalige bleiben wählbar, weil der Narrata-Import sie akzeptiert.
- **Hörprobe:** `p` = nächste Probe, `r` = wiederholen. Gespielt wird `ffplay -nodisp -autoexit -loglevel error -ss <lokal> -t <dauer> <segment-wav>` mit Dauer = Passagenlänge, höchstens 12 s. `Sample` bekommt dafür `local_end_ms`. Fehlt `ffplay` oder schlägt es fehl (z. B. WSL ohne Audio), nennt der Befehl WAV und lokale Zeit und läuft weiter. Grund: ffmpeg ist schon Abhängigkeit, eine Python-Audiobibliothek brächte nichts.
- **Schreibregel (TOOL-68):** `--assign` ist ein ausdrücklicher Schreibweg. Geändert werden nur Einträge, die in diesem Lauf gewählt wurden; neue Labels werden angehängt. Alle übrigen Einträge werden inhaltlich so zurückgeschrieben, wie sie gelesen wurden, mit Schlüsselreihenfolge und Zusatzfeldern; die Datei bekommt die Standardformatierung von `write_atomic`. Byteweise bleibt sie nur, wenn der Lauf nichts wählt, denn dann wird sie gar nicht geschrieben. Grund: byteweises Erhalten handformatierter Dateien bräuchte Textchirurgie am JSON, ohne inhaltlichen Gewinn.
- **Veraltete Einträge:** Ein `stale`-Eintrag eines aktuellen Labels wird mit seiner alten Wahl angezeigt („stale, earlier: person 3“) und erst durch eine neue Wahl ersetzt. Bei Überspringen bleibt er stehen und wird wie bisher gemeldet. Einträge zu unbekannten Segmenten oder Labels fasst `--assign` nie an.
- **Split-Hinweis:** Wählt man eine Person, die im selben Segment schon ein Label hat, kommt ein Hinweis mit Rückfrage, weil die Anwendung beide Labels zusammenführt.
- **`effort_minutes`:** Die Laufzeit der interaktiven Sitzung wird gemessen. Am Ende schlägt der Befehl bisherigen Wert plus aufgerundete Minuten vor und schreibt erst nach `y`. Bei Strg+C entfällt der Vorschlag.
- **Abbruch:** Strg+C (auch während einer Probe) beendet mit Exit 130 und meldet die Zahl der gespeicherten Labels. Die Datei ist gültig, weil nach jeder Wahl atomar geschrieben wird.
- **TTY:** `--assign` verlangt `stdin` und `stdout` als TTY, sonst `error: … needs an interactive terminal` und Exit 2. Danach dieselbe Prüfung und Ausgabe wie ohne `--assign`, inklusive Neuschreiben von `samples.md`.
- **Testbarkeit:** Ablauf in `src/transcript/speaker_assign.py` mit injizierten `ask`/`say`/`play`, damit Tests skriptbare Eingaben nutzen. Der CLI-Teil verdrahtet nur `input`/`print`/ffplay.

## Daten-Check
- Namen und Passagentext in der Konsole: *handled — nur im interaktiven Lauf (`stdin` und `stdout` TTY); ohne TTY Exit 2, bevor etwas gezeigt wird.*
- Logs: *handled — die neuen Module loggen nichts; `--assign` ist kein Pipeline-Schritt und schreibt nicht in `pipeline.log`.*
- Zähler-Output und Fehlermeldungen: *handled — Abschluss wie `_speakers` (Zähler, Segment- und Eintragsnummern); Ausgaben von ffplay werden nicht weitergereicht, nur „playback failed“ mit WAV-Pfad (enthält nur den Session-Key).*
- Fixtures/Tests: *handled — bestehende anonyme Helfer (`tests/test_speakers.py:38` `participant()`, `NAME`); keine echten Daten.*
- Wohin geschrieben wird: *handled — nur `work/<s>/speakers/assignment.json` und `samples.md` (beide unter `work/`, TOOL-66).*

## Contract-Check
- JSON-Contract IOA-1214: *N/A because `--assign` schreibt nur die interne `assignment.json`; der Export (`export.py:207`) bildet `person` → `participant_id` unverändert ab, `transcript-v1` 1.0 bleibt.*
- Narrata-Änderung: *N/A because die Kandidaten kommen aus dem Transkriptionskontext und der Import akzeptiert genau diese IDs.*
- Abweichung in ios-archiv: *handled — `docs/transcript-contract.md:122` sagt „fremde ID wird zu null“, der Importer lehnt ab; Doku-Angleichung in IOA-1294.*

## Resume-Check
- Abbruch: *handled — Schreiben nach jeder Wahl, Strg+C → Exit 130 mit gültiger Datei.*
- Wiederverwendung: *handled — ein neuer Lauf fragt nur Labels ohne angewendeten Eintrag ab.*
- Modell/Snapshot: *N/A because kein Modell; ein Snapshot-Wechsel zeigt sich über `unknown_person` in der Abschlussprüfung, `--all` erlaubt Nachziehen.*

## Dependency-Check
- `ffplay`: *handled — gehört unter Ubuntu/Debian zum Paket `ffmpeg`, läuft lokal, Lizenz wie ffmpeg (LGPL/GPL); optional: fehlt es, gibt es keine Wiedergabe, sondern WAV und Zeit. `transcript doctor` meldet ein fehlendes `ffplay` als `warning`, nicht als Fehler.*
- Python-Pakete: *N/A because keine neuen.*

## Format-Check
- `assignment.json`: *N/A because das Format bleibt `format_version: 1`; `--assign` schreibt nur Felder, die es schon gibt. Bestehende Dateien bleiben gültig.*

## Chunks
### Chunk 1 — Schreiblogik für einzelne Einträge
- Dateien: `src/transcript/speakers.py`, `tests/test_speakers.py`
- Änderung: `set_entry(paths, entry)` liest die Rohdaten, ersetzt bzw. hängt den Eintrag für (segment, label) an, lässt alle anderen Rohobjekte unverändert und schreibt atomar. `set_effort(paths, minutes)` entsprechend. Beides validiert das Ergebnis mit der Logik von `load_assignment`, bevor geschrieben wird.
- Verify: `scripts/check`
- AC: Zusatzfelder und Reihenfolge fremder Einträge bleiben erhalten; ungültige Datei → `AssignmentError`, nichts geschrieben.

### Chunk 2 — Hörprobe und Werkzeugprüfung
- Dateien: `src/transcript/speaker_samples.py` (`Sample.local_end_ms`), neu `src/transcript/speaker_player.py`, `src/transcript/preflight.py`, Tests
- Änderung: `play(wav, start_ms, end_ms)` über `ffplay` (Dauer ≤ 12 s, Ausgabe geschluckt), Ergebnis `played | missing | failed`; Doctor-Warnung bei fehlendem `ffplay`.
- Verify: `scripts/check`
- AC: korrekte `-ss`/`-t` aus der lokalen Zeit (Test mit gemocktem `subprocess.run`); fehlendes ffplay ist kein Fehler.

### Chunk 3 — Interaktiver Ablauf und CLI
- Dateien: neu `src/transcript/speaker_assign.py`, `src/transcript/__main__.py` (`--assign`, `--all`), `tests/test_speaker_assign.py`, `tests/test_smoke.py`
- Änderung: Warteschlange, Kandidatenliste, Befehle `p/r/<n>/u/m/s/q`, Split-Rückfrage, Stale-Anzeige, Effort-Vorschlag, Strg+C → 130, TTY-Prüfung → 2, danach die bestehende Prüfung aus `_speakers`.
- Verify: `scripts/check`
- AC: alle Ticket-AK mit skriptbaren Eingaben abgedeckt (Zuordnung ohne Editor, Probe mit Zeitposition, Abbruch hinterlässt gültige Datei, Unberührtes bleibt, ohne TTY Exit 2).

### Chunk 4 — Haltanweisung und Doku
- Dateien: `src/transcript/__main__.py` (`_print_halt`), `tests/test_process.py`, `README.md` („Sprecherzuordnung“), `src/transcript/speaker_samples.py` (`_INTRO` nennt `--assign`), `docs/datenschutz.md` (Namen nur im interaktiven TTY)
- Änderung: Halt nennt `transcript speakers <s> --assign`; README beschreibt Ablauf, Tasten, ffplay/WSL-Hinweis, Schreibregel.
- Verify: `scripts/check`
- AC: Haltanweisung und Doku nennen `--assign`; Übergabe aus TOOL-55 erledigt.

## Folge-Tickets
- IOA-1294: `docs/transcript-contract.md:122` an `TranscriptImporter` angleichen (fremde `participant_id` → Import abgelehnt).
- TOOL-87: automatische Vorschläge über Stimmprofile.
- TOOL-79: Kandidaten auf Anwesende eingrenzen, sobald Narrata Anwesenheit liefert.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schreiblogik `set_entry`/`set_effort` | no |
| 2 | Hörprobe (`ffplay`) + Doctor-Warnung | no |
| 3 | Interaktiver Ablauf + CLI `--assign` | no |
| 4 | Haltanweisung, README, Datenschutz-Doku | no |
