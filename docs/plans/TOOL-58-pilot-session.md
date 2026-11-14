# TOOL-58 — Erste reale Session vollständig durch die V0.1-Pipeline

## Ziel
Danach ist belegt, dass eine echte Sitzung ohne Eingriffe in den Code von der Aufnahme bis zum Narrata-Import durchläuft, und es gibt Messwerte für Laufzeit, Review- und Zuordnungsaufwand sowie für erkannte und übersehene Fehler. Bis heute gibt es Läufe nur stückweise. Der Export wurde nur gegen die Schema-Kopie geprüft (TOOL-69, TOOL-89), nie mit Narratas `transcript:validate` oder `transcript:import`. TOOL-59, TOOL-60 und TOOL-70 warten auf dieses Material.

## Ist-Stand
- `transcript process` (`src/transcript/pipeline.py:32-103`) läuft alle Schritte von `doctor` bis `report`, hält bei Review und Zuordnung an (Exit 3) und erzwingt einen Schritt mit `--redo` (`README.md:57-75`).
- Lokal liegt eine Pilotsitzung mit zwei Aufnahmen. Ihr Export wird also Contract 1.1 mit `source.recordings[]` (TOOL-89, `README.md:623`). `transcript status` meldet: Kontext, Snapshot und Manifest `done`, `transcribe` `stale` (Snapshot hat sich nach der ASR geändert), Review `waiting` mit 1371 offenen Kandidaten, Sprecher `done` (8 Labels, `effort_minutes` 8). Der strenge Preflight lässt `process` ohne `--redo transcribe` nicht starten (`README.md:71`).
- Eine neue ASR macht Sprecherentscheidungen über `labels_version` zu `stale` (`src/transcript/speakers.py:10-15`) und Review-Entscheidungen über `reference_processed_at` ebenso (`README.md:466`). Die alte `review.csv` würde beim Import als veraltete Fassung abgelehnt (`README.md:508`).
- Der Bericht liefert `effort_minutes` (Zuordnung) und Kandidaten pro Stunde Audio, aber keine Review-Zeit (`README.md:598-600`). `transcript calibrate` misst erkannte und übersehene Fehler an einer Handreferenz und gibt nur Zahlen aus (`README.md:417-434`).
- Narrata: `scripts/artisan` nimmt `php8.5` oder Sail (`ios-archiv/scripts/artisan`). Lokal fehlt `php8.5`, und die WSL-Integration von Docker Desktop ist aus. `transcript:import` verlangt, dass Gruppe, Ordinal und `play_session_id` der Datei auf eine vorhandene Spielsitzung zeigen (`ios-archiv-backend/app/Support/Transcripts/TranscriptImporter.php:162,246-253`). Personen ohne Mitgliedschaft werden entkoppelt (`:266-283`).

## Entscheidungen
- **Pilotsitzung:** die lokal vorbereitete Sitzung mit zwei Aufnahmen, komplett neu ab `transcribe` (`process --redo transcribe`). Nur so entstehen eine volle Laufzeitmessung für TOOL-59 und ein frisch gemessener Zuordnungsaufwand. Session-Key und Gruppe stehen nie im Repo.
- **Alte Handdateien beiseite:** Vor dem Lauf kommen `speakers/assignment.json`, `review/review.csv` und `review/decisions.json` nach `work/<s>/pre-tool58/`, verschoben und nicht gelöscht. So schreibt `process` frische Vorlagen, und der Aufwand misst nur den Pilot.
- **Snapshot eingefroren:** Ab dem Start von `transcribe` läuft kein `snapshot --refresh` mehr, sonst wird die ASR wieder `stale`.
- **Review mit Timebox:** in der Reihenfolge der Spalte `order` (uncertain und starke Hinweise zuerst), feste Zeit, Vorschlag 2 h. Der Rest bleibt `open` und steht im Bericht als Lücke `open_passages`. Die Review-Zeit stoppt die Projektverantwortliche und trägt sie in den Pilotbericht ein.
- **Fehlerstichprobe über `transcript calibrate`:** Die Projektverantwortliche schreibt eine Handreferenz über einige Minuten mit schnellem Dialog und Übersprechen. Das Werkzeug liefert nur Zahlen.
- **Narrata-Gegenprobe lokal über Sail:** `scripts/artisan transcript:validate` und `transcript:import`, dazu ein zweiter Import für die Idempotenz. Der Import braucht die Gruppe und die Spielsitzung mit denselben IDs in der lokalen DB. Fehlen sie, hält der Chunk an und klärt mit der Projektverantwortlichen, ob ein Abzug der Produktiv-DB her soll oder nur `validate` läuft.
- **„Fixture an IOA-1218“:** Die echte Exportdatei geht in kein Repo (TOOL-66). Übergeben werden das Ergebnis von `validate`/`import` als Kommentar an IOA-1218 und die Datei lokal unter `output/`. Eine anonymisierte Fixture erst, wenn Narrata sie braucht (siehe Folge-Tickets).
- **Pilotbericht:** `docs/pilot/TOOL-58-erste-session.md`, nur Kennzahlen, Codes und nachgestellte Beispiele. Blockierende Fehler werden je Fund als eigener `fix(<scope>): … (TOOL-58)`-Commit im laufenden Chunk behoben, mit Test an synthetischen Daten.

## Daten-Check
- Folgt TOOL-66: handled — Audio, `work/`, `output/`, Handreferenz und die alten Handdateien bleiben lokal. Ins Repo gehen nur Plan und Pilotbericht.
- Transkripttext an Claude: handled — der Agent liest weder `work/`- noch `output/`-Dateien mit Text oder Namen (ASR, Kandidaten, CSV, Zuordnung, Export, TXT, DOCX) und sieht nur Konsolenzeilen mit Zählern, `report.json`/`report.md` (ohne Text und Namen, `README.md:607`) und die Zahlen von `calibrate`. Den interaktiven Dialog `speakers --assign` und das Review führt die Projektverantwortliche selbst.
- Repo und Bericht: handled — kein Session-Key, kein Gruppen-Slug, keine Kampagnennamen. Verify jedes Chunks: `git grep` auf Slug und Ordinal über `docs/`, ohne Treffer; `git status` zeigt keine Datendateien.
- Logs und Fehlermeldungen: handled — `pipeline.log` und die Konsole nennen nur Schlüssel, Zähler und Codes (`README.md:73`). Ein Fix darf daran nichts lockern; `debug` bleibt `false`.
- Narrata lokal: handled — der Import landet in der lokalen Sail-DB, verlässt also den Rechner nicht. Nach der Probe wird das importierte Transkript dort entfernt, außer die Projektverantwortliche will es behalten.
- Jira-Kommentare: handled — nur Zähler, Exit-Codes und Fehlercodes, kein Text und keine Namen.

## Contract-Check
- Version: handled — zwei Aufnahmen ergeben `contract_version` `1.1` mit `source.recordings[]` nach IOA-1287; die Schema-Kopie stammt aus ios-archiv `e8bfb9702` (TOOL-89).
- Gegenprobe: handled — Chunk 4 prüft mit Narratas `transcript:validate` und `transcript:import` statt nur mit `contract.validate`.
- Narrata-Änderung: zunächst N/A. Meldet Narrata einen Verstoß, den `contract.validate` nicht kennt, kommt die Narrata-Seite in ein neues IOA-Ticket und die Pipeline-Seite in einen `fix(export)`-Commit hier. Der Endpoint `transcript context` (IOA-1215) wird nicht neu aufgerufen, der gespeicherte Kontext gilt.

## Resume-Check
- Abbruch: handled — `transcribe` speichert je Segment. Nach Ctrl-C oder Absturz bleibt `process.lock` liegen, `status` meldet `interrupted`, und der nächste `process` ohne `--redo` macht mit dem fehlenden Segment weiter (`README.md:72`). Mit `--redo` würde ein fertiges Segment erneut laufen, deshalb steht `--redo` nur beim ersten Start. Fehlversuche landen in `pipeline.log`.
- Wiederverwendung: handled — nach dem ersten Halt verwendet der zweite `process` Kontext, Snapshot, Manifest und ASR wieder, und alles ab `working` läuft neu.
- Gleiches Modell und Snapshot: handled — der strenge Preflight stoppt bei abweichendem Modell, Snapshot, Keywords oder Sprache (`README.md:71`). Der Snapshot ist eingefroren (siehe Entscheidungen), Modell und Snapshot-Kennung stehen in `report.json` unter `pipeline`.

## Dependency-Check
- Neue Abhängigkeit: N/A, weil die Pipeline keine neue Bibliothek und kein neues Modell bekommt.
- Umgebung: handled — für die Gegenprobe muss die WSL-Integration von Docker Desktop aktiv sein (macht die Projektverantwortliche), und Sail muss laufen. Das ist Umgebung von ios-archiv, keine Abhängigkeit dieses Repos.
- Hardware: handled — die ASR über die volle Aufnahme braucht nach TOOL-62 bis 10,5 GB RAM bei 5 h. Peak-RAM/VRAM und Laufzeit kommen in den Pilotbericht.

## Format-Check
N/A, weil der Pilot kein internes Format ändert. Bräuchte ein Fix eines, gilt dort die Regel aus dem Format-Check (Version erhöhen, Altartefakte benennen) und der Fix bekommt eigene Notizen im Bericht.

## Chunks
### Chunk 1 — Automatischer Lauf bis zum ersten Halt
- Dateien: `docs/pilot/TOOL-58-erste-session.md` (neu), gegebenenfalls Fix-Commits in `src/transcript/…` mit Tests
- Änderung: Alte Handdateien nach `work/<s>/pre-tool58/` verschieben. `transcript doctor <s>`, dann `transcript process <s> --redo transcribe` mit `/usr/bin/time -v` für Laufzeit und Peak-RAM, VRAM per `nvidia-smi`-Stichprobe. Erwartet: Exit 3 an Review und Zuordnung. Der Bericht bekommt Abschnitte zu Aufnahme (Dauer, Segmente), Umgebung, Laufzeit je Schritt aus `pipeline.log`, Kandidaten je Stufe und blockierenden Fehlern mit Workarounds.
- Verify: `scripts/check`; `transcript status <s>` zeigt `transcribe done` und Review `waiting`; `git grep` auf Slug und Ordinal über `docs/` leer.
- AC: Die Sitzung läuft durch alle automatischen Schritte; Unsicherheitsbewertung und Kandidaten sind erzeugt; Laufzeit und Ressourcen sind dokumentiert.

### Chunk 2 — Zuordnung, Review, Export
- Dateien: `docs/pilot/TOOL-58-erste-session.md`
- Änderung: Die Projektverantwortliche ordnet mit `transcript speakers <s> --assign` zu und trägt `effort_minutes` ein, jedes Label einer Person oder `unknown`. Danach Review in der `order`-Reihenfolge mit Timebox und gestoppter Zeit, dann `transcript process <s>` bis zum Bericht. Der Bericht übernimmt die Zahlen aus `report.json` (Review je Status, offene Kandidaten, Marker, Lücken, `open_speakers` = 0) und die Review-Zeit.
- Verify: `scripts/check`; `process` endet mit 0 oder 1 (Lücke nur `open_passages`); `output/<s>/` enthält `transcript.json`, `.txt`, `.docx`, `report.json`, `report.md`.
- AC: Alle Labels sind zugeordnet oder ausdrücklich `unknown`; die Entscheidungen sind in der Arbeitsfassung angewendet; der Export ist schema-gültig; TXT und DOCX sind erzeugt, offene Stellen sichtbar; Review-Menge, Zuordnungsaufwand und grober Gesamtaufwand sind dokumentiert.

### Chunk 3 — Fehlerstichprobe
- Dateien: `docs/pilot/TOOL-58-erste-session.md`
- Änderung: Die Projektverantwortliche schreibt eine Handreferenz für 5–10 min mit schnellem Dialog und Übersprechen nach `work/<s>/review/calibration/`. `transcript calibrate <s> --segment N --reference … --start … --end …` liefert übersehene Fehler in `confident`-Passagen, Fehlalarme, Treffer je Stufe und je Regel. Ins Bericht kommen nur diese Zahlen und eine kurze Einordnung, welche Fehlerarten fehlen. IT/OT-Wechsel notiert die Projektverantwortliche mit Zeitmarke lokal unter `work/<s>/` als Material für TOOL-70.
- Verify: `scripts/check`; `git grep` auf Slug und Ordinal über `docs/` leer.
- AC: Erkannte und übersehene relevante Fehler sind auf der Stichprobe nachvollziehbar.

### Chunk 4 — Narrata-Gegenprobe
- Dateien: `docs/pilot/TOOL-58-erste-session.md`; bei einem Fund gegebenenfalls `fix(export)`-Commit mit Test
- Änderung: WSL-Integration von Docker Desktop aktivieren (Projektverantwortliche), Sail starten. Prüfen, ob Gruppe und Spielsitzung mit den IDs aus dem Manifest lokal existieren. Fehlen sie, hier anhalten und klären. Dann `scripts/artisan transcript:validate <output/…/transcript.json>`, `scripts/artisan transcript:import <datei>` und ein zweiter Import derselben Datei (erwartet: keine Änderung). Ergebnis als Zähler und Codes in den Bericht und als Kommentar an IOA-1218. Danach das lokale Transkript entfernen.
- Verify: `scripts/check`; `validate` meldet keinen Verstoß; der erste Import legt an, der zweite ändert nichts.
- AC: Der Import der Testsession über IOA-1218 gelingt ohne Korrektur (aus TOOL-69/TOOL-89); der Export liegt IOA-1218 vor.

### Chunk 5 — Abschluss
- Dateien: `docs/pilot/TOOL-58-erste-session.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`, gegebenenfalls `README.md`
- Änderung: Auffälligkeiten und Workarounds zusammenfassen, Übergaben an TOOL-59/60/61/70 formulieren, Roadmap-Hinweise ergänzen und `.md` neu erzeugen. README nur, wenn ein Fix Verhalten geändert hat.
- Verify: `scripts/check`; Roadmap-`.md` aus der `.py` neu erzeugt; `git grep` auf Slug und Ordinal leer.
- AC: Blockierende Fehler, Workarounds und Auffälligkeiten sind dokumentiert; alle ACs des Tickets sind abgehakt.

## Folge-Tickets
- `TOOL-59`: Laufzeit (knapp 7 min für 5:26 h), Zuordnungsaufwand (4 min), Review-Tempo (35 Entscheidungen pro Stunde) und Kandidaten pro Stunde (160) aus dem Pilotbericht und `output/<s>/report.json`. Peak-RAM/VRAM des erfolgreichen Laufs fehlen, weil das temporäre Verzeichnis geleert wurde; bei Bedarf in TOOL-93 neu messen.
- `TOOL-60`: Die Kernhypothese hält in der Bewertung (keine Fehlalarme), scheitert aber an der WER von 24–33 %; ein vollständiges Review läge bei rund 25 h pro Abend. Review-Umfang (ohne Review, nur Glossar-Begriffe, vollständig) und Review-Kanal neu entscheiden. Befund der Projektverantwortlichen: Lange Passagen sind beim Hören hilfreicher als kurze.
- `TOOL-61`: In die E2E-Doku gehören das Beiseitelegen alter Handdateien vor einem `--redo transcribe`, `LD_LIBRARY_PATH` bzw. ein Startskript ohne aktivierte venv und das Abspielen einer Kandidaten-ID im Review.
- `TOOL-70`: Die Pilotsitzung steht als Material bereit. IT/OT-Zeitmarken wurden im Pilot nicht notiert und müssen im Spike selbst entstehen.
- `TOOL-91`: Hörproben bei der Sprecherzuordnung entrauscht abspielen (beim Mithören viele Störgeräusche).
- `TOOL-92`: Spike zum Entrauschen vor der Erkennung.
- `TOOL-93`: Spike zur Erkennungsqualität an den beiden Pilot-Handreferenzen, mit Gegenprobe an einer dritten Referenz aus einer anderen Sitzung.
- `TOOL-94`: Der Preflight meldete die ASR als `ok`, obwohl faster-whisper die CUDA-Bibliotheken nicht laden konnte.
- [kein Ticket: anonymisierte Pilot-Fixture für ios-archiv nur, wenn Narrata sie verlangt; die Contract-Fixtures aus IOA-1214/IOA-1287 decken die Form ab]
- [kein Ticket: Review-Dialog mit Abspielen nach dem Vorbild von `speakers --assign`; ob und in welcher Form, hängt an der Review-Entscheidung in TOOL-60]
- [kein Ticket: IPv6 in WSL, Gruppe `docker` und die lokale Narrata-Umgebung sind Einrichtung des Testrechners und im Pilotbericht beschrieben]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Automatischer Lauf bis zum ersten Halt | no |
| 2 | Zuordnung, Review, Export | no |
| 3 | Fehlerstichprobe | no |
| 4 | Narrata-Gegenprobe | no |
| 5 | Abschluss, Roadmap | no |
