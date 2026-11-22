# TOOL-102 — Spike: Vereinigung mehrerer Seeds gegen Auslassungen messen

## Ziel
TOOL-101 hat gezeigt, dass 32–72 % der betroffenen Wörter nur in einzelnen Seeds fehlen. Offen ist, was davon nutzbar ist: Die Obergrenze dort zählt ersetzte Wörter als erkannt und kennt die falschen Wörter nicht, die eine Vereinigung mitbringt. Nach dem Spike steht an A, B und C das Orakel mit beiden Richtungen, über das ganze Segment die Abweichung der Seeds samt Blockverlusten, und, falls das Orakel trägt, je Regel ohne Referenz eine Tabelle. Daraus folgt Go oder No-Go. Pipeline, Referenzformat und Bewertungsregeln bleiben unverändert.

## Ist-Stand
- **Läufe liegen vor.** Im Hauptcheckout gibt es für beide Sitzungen `experiments/asr/base.seed1..3` (Segment 1, Transkript und Rohform), dazu die Diarisierung und `vad.json`. Es muss nichts neu transkribiert werden.
- **Handreferenzen** (lokal, nie im Repo): A 531 Wörter und B 441 Wörter an der Pilotsitzung, C 909 Wörter (Fassung Hochdeutsch) an der zweiten Sitzung (`docs/spikes/TOOL-101-auslassungen-verorten.md:20`).
- **Vorarbeit aus TOOL-101** (`docs/spikes/TOOL-101-auslassungen-verorten.md:83`): Auslassungen je Seed 31/31/36 (A), 44/42/45 (B), 80/156/177 (C); in allen drei Seeds fehlen 28 / 28 / 59. An C verlieren Seed 2 und 3 je eine Folge von 54 Wörtern.
- **Was die Obergrenze höchstens hergibt:** an A 0,6–1,5 Punkte WER (3–8 Wörter auf 531), an B 3,2–3,9 Punkte, an C 2,3–13 Punkte. A kann die 3 Punkte nicht erreichen, die Entscheidung fällt also an B und C.
- **Werkzeug `scripts/spike/omissions.py`:**
  - `heard` (`:143`) liefert je Referenztoken die Zeit, zu der ein Lauf es erkannt hat, und prüft die Auslassungen gegen `calibration.align`. Treffer und Ersetzungen unterscheidet es nicht.
  - `timeline` (`:177`) gibt jedem Referenzwort eine Zeit über alle Seeds.
  - `Ranges` (`:86`) rechnet mit Zeitbereichen, `silence` (`:345`) findet Sprache ohne Wörter.
  - `measure` (`:614`) lädt Läufe, Diarisierung und VAD und prüft die Herkunft.
- **Werkzeug `scripts/spike/asr.py`:**
  - `transcribed` (`:726`) lädt das Transkript einer Wurzel und prüft Seed, Modell und Settings, `check_provenance` (`:761`) Revision und Snapshot.
  - `decode_windows` (`:1129`) liest je 30-s-Fenster Temperatur, Wortzahl und `compression` aus der Rohform. Die Fenster liegen je Seed an anderen Stellen.
  - `sections` und `deficits` (`:1021`, `:1052`) zählen Wörter je 5 Minuten und finden Defizite ab 30 Wörtern und 20 %.
  - `score` (`:655`) liefert Wortzahl, Wiederholungsanteil (`denoise._repetition`, `scripts/spike/denoise.py:416`), Passagen je Stufe und markierte Zeit über das Segment.
  - `parse_clip` (`:635`) beschreibt Clips, `denoise.CLIPS` (`scripts/spike/denoise.py:71`) hält A und B.
- **Ausrichtung:** `calibration.align` (`src/transcript/calibration.py:126`) liefert Treffer, Ersetzungen (`substituted`), Auslassungen und Einfügungen gegen die Handreferenz. `_clip_tokens` (`:175`) liefert die erkannten Tokens eines Clips, `evaluate` (`:323`) Fehler je Stufe.
- **Vergleichswerte Parakeet** (TOOL-35, im Ticket TOOL-82): am Clip 16 von 17 Fehlern in `confident`-Passagen bei 15 % mehr Clip-Zeit, über die Sitzung 32 Punkte mehr markierte Zeit.
- **Umgebung:** Der Worktree hat weder `.venv` noch `work/`. Die Spike-Skripte haben keine Unit-Tests, `scripts/check` prüft sie mit ruff.

## Entscheidungen
- **Eigenes Skript `scripts/spike/seeds.py`**, das `omissions.py`, `asr.py` und `denoise.py` importiert. `omissions.py` hat 700 Zeilen und eine andere Frage.
- **Reihenfolge nach dem Ticket-Nachtrag:** zuerst der Segmentvergleich ohne Referenz, dann das Orakel, dann erst die Regeln.
- **Segmentvergleich.** Die Tokenfolgen der Seeds werden paarweise ausgerichtet, abschnittsweise je 5 Minuten (`asr.SECTION_MS`), damit die Ausrichtung über 5 h schnell bleibt.
  - *Abweichung:* Tokens, die ein Lauf hat und ein anderer an derselben Stelle nicht.
  - *Blockverlust:* eine Folge von mindestens 20 Tokens, die einem Seed fehlt und in einem anderen steht. Die Schwelle steht vorab fest; an C waren es 54, an A und B höchstens 9.
  - Ausgabe je Sitzung: Wörter je Seed, Anteil der Tokens in Abweichung, Zahl und Größe der Blockverluste je Seed, Anteil der 30-s-Raster-Fenster mit Abweichung ab 5 Tokens.
- **Orakel, je Seed als Basis** (nicht nur Seed 1, weil C von 80 bis 177 streut):
  - *Rückgewinn:* Für jede Auslassung der Basis zählen, ob ein anderer Seed das Wort als Treffer hat, nur als Ersetzung, oder ob es in allen fehlt. Nur Treffer senken die WER.
  - *Gegenrichtung:* Die anderen Läufe werden gegen die Basis ausgerichtet. Was nur sie haben, wird in die Basis eingefügt, und die vereinigte Tokenfolge wird mit `calibration.align` gegen die Handreferenz gemessen. Das ergibt die WER der naiven Vereinigung und die zusätzlichen Einfügungen.
  - *Tabelle:* WER der Basis, WER des Orakels (alle Treffer eingesetzt, nichts Falsches), WER der naiven Vereinigung, jeweils mit E/A/Ei.
- **Schwelle für Schritt 2:** Die Regeln werden nur gemessen, wenn das Orakel im Mittel über die Basis-Seeds an mindestens zwei Referenzen 3 Punkte WER bringt. Das Ticket nennt 3 Punkte, die zwei Referenzen kommen aus seiner Go-Regel.
- **Zusätzliche Handreferenz nur, wenn die Entscheidung daran hängt:** Das Orakel liegt an B oder C zwischen 2 und 4 Punkten, oder B und C liegen auf verschiedenen Seiten der Schwelle. Dann schlägt das Skript ein 3-min-Fenster mit der größten Abweichung zwischen den Seeds vor (nur Zeiten), aus der Sitzung, deren Ergebnis unklar ist. Chunk 2 hält dafür an.
- **Regeln ohne Referenz**, Schwellen vorab fest:
  - *R1, Fensterwahl:* Raster von 30 s auf der Zeitachse des Segments, weil die Dekodierfenster je Seed woanders liegen. Je Fenster gewinnt der Lauf mit den meisten Wörtern. Ein Lauf scheidet aus, wenn ein Rohsegment im Fenster die `compression_ratio`-Schwelle aus `review.uncertainty` erreicht oder der Wiederholungsanteil der Fenster-Tokens über 0 liegt. Bei Gleichstand gewinnt der niedrigste Seed. Wörter werden nach ihrem Startzeitpunkt zugeordnet. Gemessen wird die WER an den Referenzen.
  - *R2, Alternative an der Lücke:* Die Basis bleibt, Tokens, die nur ein anderer Seed hat, gelten als Alternative an der Stelle. Gemessen: wie viele Auslassungen der Basis eine richtige Alternative bekommen, wie viele Alternativen falsch sind und wie viel Zeit die Stellen einnehmen.
  - *R3, Abweichung als Review-Hinweis:* Eine Passage der Basis mit einer Abweichung ab 1, 2 oder 3 Tokens gilt als markiert. Gemessen wie in TOOL-35: gefundene Fehler und Auslassungen in `confident`-Passagen, Fehlalarme, zusätzlich markierte Zeit am Clip und über das Segment.
  - *Über das Segment* je Regel: Wortzahl, Wiederholungsanteil, Passagen je Stufe, markierte Zeit. Bei R1 trägt jede Passage die Stufe aus dem Lauf, aus dem sie stammt.
- **Go-Regel, konkretisiert.** Das Ticket sagt „deutlich mehr Auslassungen markiert, ohne die markierte Zeit stark auszudehnen". Vor der Messung festgelegt:
  - R1: 3 Punkte WER an mindestens zwei Referenzen.
  - R2 und R3: an mindestens zwei Referenzen bekommt die Hälfte der Auslassungen in `confident`-Passagen eine Markierung bzw. richtige Alternative, bei höchstens 10 Punkten mehr markierter Zeit über das Segment. Parakeet lag bei 32 Punkten.
- **Leitplanke:** Keine Regel schreibt ein Transkript. R1 ist eine Auswahl unter ASR-Ergebnissen, R2 und R3 lassen die Basis stehen. Wie das Referenzformat das trägt, ist Frage des Umsetzungstickets.
- **Läufe aus dem Worktree** wie in TOOL-101: Python aus der `.venv` des Hauptcheckouts, `--config` auf dessen `config/config.yaml`. Alle Daten bleiben dort unter `work/`.

## Daten-Check
- Audio, Transkripte, Rohform, Handreferenzen: *handled* — alles bleibt unter `work/` im Hauptcheckout. `seeds.py` schreibt nichts.
- Konsole: *handled* — nur Zähler, Anteile, WER und Zeiten. Kein Text, kein Token, kein Name, kein Label, kein Session-Schlüssel. Der Fenstervorschlag nennt nur Zeiten.
- Spike-Dokument: *handled* — nur Kennzahlen, Sitzungen heißen „Pilotsitzung" und „zweite Sitzung". Chunk 2 und 4 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Fehlermeldungen: *handled* — `SpikeError` nennt Variante, Seed und Clipname, nie Inhalt.
- Zusätzliche Handreferenz: *handled* — sie liegt wie A bis C nur unter `review/calibration/` der Sitzung.
- Fixtures: *N/A*, weil keine angelegt werden.

## Contract-Check
*N/A*, weil der Spike keine Contract-JSON liest oder schreibt. Bei Go betrifft die Frage nach mehreren Läufen und Alternativen zuerst das interne Referenzformat; ob der Contract (IOA-1214) folgt, klärt das Umsetzungsticket.

## Resume-Check
- Abbruch: *handled* — das Skript liest nur und rechnet in Sekunden bis wenigen Minuten neu.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings je Wurzel, `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot ab.
- Fehlt eine `base`-Wurzel: *handled* — `asr.py prepare` und `run` rechnen sie nach (rund 7 min je Seed). Das stünde dann im Bericht.

## Dependency-Check
*N/A*, weil weder ein Paket noch ein Modell dazukommt.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert.

## Chunks
### Chunk 1 — Werkzeug `seeds.py`: Segmentvergleich und Orakel
- Dateien: `scripts/spike/seeds.py` (neu), `scripts/spike/README.md` (Abschnitt „Seed-Spike (TOOL-102)")
- Änderung:
  - Aufruf `seeds.py <gruppe>/<ordinal> [--variant base] [--seeds 3] [--clip NAME=DATEI@H:MM:SS-H:MM:SS]… [--config PATH]`, Clips wie in `omissions.py`
  - Segmentvergleich: Abweichung, Blockverluste, Raster-Fenster
  - Orakel je Basis-Seed: Rückgewinn (Treffer, Ersetzung, fehlt überall), naive Vereinigung gegen `calibration.align`
  - `--suggest`: drei sich nicht überlappende 3-min-Fenster mit der größten Abweichung, nur Zeiten
- Verify: `scripts/check`. Lauf an beiden Sitzungen:
  - Auslassungen je Seed wie in TOOL-101 (31/31/36, 44/42/45, 80/156/177)
  - „fehlt überall" ergibt 28 / 28 / 59
  - Treffer + Ersetzung + fehlt überall = Auslassungen der Basis
  - WER der Basis gleich `asr.py score`
  - die Ausgabe enthält keinen Text und kein Label
- AC: Messskript unter `scripts/spike/`, nur Kennzahlen in der Ausgabe.

### Chunk 2 — Messung: Segmentvergleich und Orakel, Entscheidung über Schritt 2
- Dateien: `docs/spikes/TOOL-102-seed-vereinigung.md` (neu)
- Änderung: Lauf an der Pilotsitzung (A, B) und der zweiten Sitzung (C). Der Bericht bekommt Material und Methode, den Segmentvergleich je Sitzung, die Orakel-Tabelle an A, B und C und die Entscheidung nach der Schwelle oben: Regeln messen, nicht messen, oder zusätzliches Fenster anfragen.
- Verify: `scripts/check`. Tabellen 1:1 aus dem Skript. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: Orakel-Tabelle an A, B und C; Aussage, ob die Blockverluste an C Regel oder Ausreißer sind.
- **Halt nur, wenn ein zusätzliches Fenster nötig ist:** Dann bekommt die Projektverantwortliche die Zeiten des Fensters. Nach dem Abtippen läuft das Orakel dort als Referenz D, und der Bericht wird ergänzt.

### Chunk 3 — Regeln ohne Referenz (entfällt, wenn das Orakel die Schwelle verfehlt)
- Dateien: `scripts/spike/seeds.py`, `scripts/spike/README.md`, `docs/spikes/TOOL-102-seed-vereinigung.md`
- Änderung: R1, R2 und R3 nach den Entscheidungen oben, je Regel eine Tabelle an den Referenzen und eine über das Segment. Bei R3 der Vergleich mit Parakeet aus TOOL-35.
- Verify: `scripts/check`. Die WER von R1 mit nur einem Seed ist gleich der WER dieses Seeds. R2 und R3 ändern die WER der Basis nicht. `grep` wie in Chunk 2.
- AC: eine Tabelle je Regel; über das Segment Wortzahl, Wiederholungsanteil, Passagen je Stufe und markierte Zeit.
- Entfällt der Chunk, steht der Grund mit den Orakel-Zahlen im Bericht.

### Chunk 4 — Auswertung, Go/No-Go, Übergaben
- Dateien: `docs/spikes/TOOL-102-seed-vereinigung.md`, `docs/plans/TOOL-102-seed-union.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung mit Go oder begründetem No-Go nach der Go-Regel oben
  - bei Go: Umsetzungsticket im Epic TOOL-100 anlegen, mit der Frage, wie das Referenzformat mehrere Läufe und Alternativen trägt
  - Kommentar an TOOL-82 (was ein zweiter Seed schon leistet, was für Parakeet bleibt) und an TOOL-107 (Blockverluste über das Segment)
- Verify: `scripts/check`. Jede Aussage der Kurzfassung verweist auf eine Tabelle, jeder Eintrag unter „Folge-Tickets" trägt einen Key oder `[kein Ticket: …]`.
- AC: Go/No-Go nach der Regel im Ticket; bei Go ein Umsetzungsticket.

## Folge-Tickets
- Umsetzungsticket bei Go: [kein Ticket: Ergebnis ist No-Go, entschieden am 2026-11-22]
- TOOL-108: Folge-Spike, angelegt am 2026-11-22. Misst, ob sich ein Blockverlust ohne Referenz von einer Halluzination trennen lässt.
- TOOL-82: Kommentar vom 2026-11-22 mit dem Vergleich Seed gegen Parakeet und dem, was für die Wörter bleibt, die in allen Seeds fehlen.
- TOOL-107: Kommentar vom 2026-11-22 mit Zahl und Größe der Blockverluste über das Segment, weil derselbe Hinweis sie sichtbar machen soll.
- TOOL-100: Kommentar vom 2026-11-22 mit dem Ergebnis für den Reflexionspunkt M9.
- Referenzen D und E (Pilotsitzung): [kein Ticket: für diesen Spike getippt, liegen lokal unter `review/calibration/`; das vorgeschlagene Fenster der zweiten Sitzung steht in TOOL-108]
- Go-Regel für R2 und R3 (Hälfte der Auslassungen, höchstens 10 Punkte Zeit): [kein Ticket: in diesem Plan festgelegt, weil das Ticket nur „deutlich" und „stark" sagt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug `scripts/spike/seeds.py`: Segmentvergleich und Orakel | no |
| 2 | Messung an A, B, C, Orakel-Tabelle, Entscheidung über Schritt 2 | no |
| 3 | Regeln R1 bis R3, nur wenn das Orakel trägt | no |
| 4 | Auswertung, Go/No-Go, Übergaben | no |
