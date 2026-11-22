# TOOL-101 — Spike: Auslassungen an den Handreferenzen verorten

## Ziel
Bekannt ist, dass Whisper an den Handreferenzen 30–131 Wörter je Clip auslässt und dass es fast nur Inhaltswörter sind (TOOL-93, TOOL-60). Unbekannt ist, *wo* sie liegen: TOOL-93 vermutet kurze, leise Einwürfe in Überlappung, gemessen ist nur die Fehlerquote je Sprecher. Nach dem Spike steht für jedes Merkmal (Überlappung, Beitragslänge, Sprecher und Pegel, Fallback-Fenster, VAD, Stabilität über die Seeds, Sprache ohne Wörter) der Anteil der Auslassungen neben dem Vergleichswert über alle Referenzwörter. Daraus folgen die Reihenfolge von TOOL-102 bis TOOL-105 und der Zuschnitt von TOOL-82. Pipeline und Bewertungsregeln bleiben unverändert.

## Ist-Stand
- **Läufe liegen vor, es muss nichts neu transkribiert werden.** Im Hauptcheckout gibt es unter `work/` für beide Sitzungen `experiments/asr/base.seed1..3` mit Transkript und Rohform von Segment 1. Die Diarisierung von Segment 1 liegt je Sitzung unter `work/<s>/diarization/segment-01.json`.
- **Handreferenzen** (lokal, nie im Repo), Stand TOOL-60 (`docs/pilot/TOOL-60-bewertung.md:29`):
  - A: Pilotsitzung, 0:00:00–0:04:06, 531 Wörter, 4 Sprecher
  - B: Pilotsitzung, 1:20:00–1:23:00, 441 Wörter, **2 Sprecher**. Das Ticket schreibt noch „B hat keine Sprecher", die Datei trägt seit TOOL-60 Labels.
  - C: zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch mit 909 Wörtern, 4 Sprecher, 3 unverständliche Stellen
- **Ausrichtung:** `calibration.align` (`src/transcript/calibration.py:126`) liefert je Auslassung nur die Referenzposition und das benachbarte erkannte Token, aber keine Zuordnung der Treffer. `_clip_tokens` (`:175`) liefert die erkannten Tokens eines Clips mit Passage und Wortindex. `denoise._wder` (`scripts/spike/denoise.py:430`) geht denselben `SequenceMatcher` für die Treffer durch.
- **Spike-Werkzeug `scripts/spike/asr.py`:**
  - `transcribed` (`:726`) lädt das Transkript einer Wurzel und prüft Seed, Modell und Settings.
  - `decode_windows` (`:1129`) liest die 30-s-Fenster aus der Rohform mit Temperatur, Wortzahl und Startzeit.
  - `parse_clip` (`:635`) und `denoise.CLIPS` (`scripts/spike/denoise.py:71`, A und B) beschreiben die Clips, `check_provenance` (`:761`) prüft Revision und Snapshot.
  - `count_fillers` (`:610`) trennt Auslassungen schon nach Füllwörtern.
- **Diarisierung:** `DiarizationRun.turns` dürfen sich überlappen, `exclusive_turns` nicht (`src/transcript/diarization/__init__.py:93`). `overlaps(turns)` (`:388`) liefert die Bereiche mit zwei Stimmen. `denoise.best_mapping` (`scripts/spike/denoise.py:464`) ordnet Labels 1:1 den Handsprechern zu.
- **VAD:** Die Rohform hält nur `duration_after_vad` (`src/transcript/asr/whisper.py:353`), nicht die Sprachabschnitte. faster-whisper 1.2.1 bringt `faster_whisper.vad.get_speech_timestamps` und `VadOptions` mit (Defaults `threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`, wie die Pipeline).
- **Umgebung:** Dieser Worktree hat weder `.venv` noch `work/`. Die Spike-Skripte haben keine Unit-Tests, `scripts/check` prüft sie mit ruff.
- **Roadmap:** `docs/transcript-roadmap.md` auf `main` kennt TOOL-100 und TOOL-101 nicht. Der Eintrag (Phase 9, M9) liegt als Commit `dc986c2` auf dem lokalen Branch `tool-100-roadmap-omissions` im Hauptcheckout, ohne PR.

## Entscheidungen
- **Eigenes Skript `scripts/spike/omissions.py`, das `asr.py` und `denoise.py` importiert.** `asr.py` hat 1277 Zeilen, `turns.py` geht denselben Weg. Das Ticket nennt „Erweiterung von `asr.py`"; gemeint ist dasselbe Werkzeug, und alle Bausteine kommen von dort.
- **Jedes Referenzwort bekommt eine Zeit, nicht nur die Auslassungen.** Nur so gibt es den Vergleichswert über alle Referenzwörter.
  - Treffer und Ersetzungen bekommen die Mitte ihres erkannten Wortes.
  - Eine Folge ausgelassener Wörter wird gleichmäßig zwischen dem Ende des linken und dem Anfang des rechten Nachbarwortes verteilt, am Cliprand bis zur Clipgrenze.
  - Der Bericht nennt die Breite dieser Lücken (Median, Anteil über 5 s), weil ein verlorener Block von 70–100 Wörtern nur grob verortet ist.
- **Gleiche Ausrichtung wie `calibration.measure`:** derselbe `SequenceMatcher`-Aufruf über dieselben Clip-Tokens. Das Skript bricht ab, wenn seine Auslassungen nicht mit `calibration.align(...).deletions` übereinstimmen.
- **Schwellen stehen vorab fest**, damit bei 30–131 Auslassungen je Clip nichts an die Daten angepasst wird:

  | Merkmal | Regel |
  | --- | --- |
  | Überlappung | Wortzeit liegt in einem Bereich aus `overlaps(run.turns)` |
  | Beitragslänge | exklusiver Turn an der Wortzeit, gleiche Labels mit höchstens 500 ms Abstand verbunden (Schwelle aus TOOL-96); Klassen unter 2 s, 2–10 s, über 10 s, kein Turn |
  | Beitragslänge, zweite Sicht | Wörter im Beitrag laut Handreferenz: 1–3, 4–10, über 10 |
  | Sprecher | Label der Handreferenz, ausgegeben als Rang nach Wortzahl |
  | Pegel je Sprecher | RMS in dBFS über die exklusiven Turns des zugeordneten Labels im Clip, relativ zum lautesten Sprecher |
  | leise | Turn an der Wortzeit liegt mindestens 6 dB unter dem lautesten Sprecher |
  | Fallback | 30-s-Fenster des Seeds an der Wortzeit hat `temperature > 0`; dazu „dünnes Fenster" wie in TOOL-81 |
  | VAD | Wortzeit liegt außerhalb aller Silero-Sprachabschnitte |
  | Stabilität | Referenzwort fehlt in 3, 2 oder 1 der Seeds |
  | Sprache ohne Wörter | Zeit in einem Turn, in der Whisper kein Wort hat; Lücken zwischen Wörtern bis 1 s gelten als gedeckt |

- **Handsprecher an A, B und C.** B hat inzwischen Labels, die Ausnahme aus dem Ticket entfällt. Beitragslänge und Pegel hängen an allen drei Clips an den Turns der Diarisierung.
- **Referenz C in der Hochdeutsch-Fassung**, wie TOOL-60 festgelegt hat. Die Auslassungen sind in beiden Fassungen gleich (131).
- **VAD nachrechnen statt speichern.** Das Skript ruft Silero mit den Pipeline-Defaults auf dem WAV von Segment 1 auf und prüft die Summe gegen `duration_after_vad` der Rohform (Toleranz 1 s). Die Abschnitte liegen danach als Zahlen unter `work/<s>/experiments/asr/vad.json`. Die Pipeline bleibt unverändert.
- **„Erklärt" heißt mindestens eines von Überlappung, Beitrag unter 2 s, leise, Fallback-Fenster.** Die Tabelle zeigt je Merkmal und für die Vereinigung den Anteil unter den Auslassungen, den Anteil unter allen Referenzwörtern und die Auslassungen je Wort innerhalb und außerhalb. Der Rest ist „unerklärt". Absolute Zahlen stehen immer dabei.
- **Sprache ohne Wörter als Hinweis:** über das ganze Segment Zeit und Zahl der Stellen ab 2 s, an den Clips der Anteil der Auslassungen und aller Referenzwörter darin und der Anteil der Clip-Zeit. Das zeigt Trefferquote und Kosten eines möglichen Hinweises, ohne eine Regel zu bauen.
- **Läufe aus dem Worktree:** Python aus der `.venv` des Hauptcheckouts, `--config` auf dessen `config/config.yaml`. Das Skript liegt im Worktree, alle Daten bleiben im Hauptcheckout unter `work/`.

## Daten-Check
- Audio, Transkripte, Diarisierung, Handreferenzen, `vad.json`: *handled* — alles bleibt unter `work/` im Hauptcheckout (gitignored), das Skript schreibt nur `vad.json` dorthin.
- Konsole: *handled* — nur Zähler, Anteile, dB-Werte und Zeiten. Sprecher erscheinen als Rang nach Wortzahl, nie als Label oder Name. Kein Text, kein Session-Schlüssel.
- Spike-Dokument: *handled* — nur Kennzahlen, Sitzungen heißen „Pilotsitzung" und „zweite Sitzung". Chunk 2 prüft mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Fehlermeldungen: *handled* — `SpikeError` nennt Variante, Seed und Clipname, nie Inhalt.
- Fixtures: *N/A*, weil keine angelegt werden.

## Contract-Check
*N/A*, weil der Spike keine Contract-JSON liest oder schreibt und den Narrata-Endpoint nicht anspricht.

## Resume-Check
- Abbruch: *handled* — das Skript liest nur und rechnet in Sekunden neu. Der einzige längere Schritt ist die VAD über 5 h Audio auf der CPU; `vad.json` wird wiederverwendet, wenn Frame-Zahl und VAD-Optionen passen.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings je Wurzel, `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot zwischen den Seeds ab.
- Fehlt oder veraltet eine `base`-Wurzel: *handled* — `asr.py prepare` und `run` rechnen sie mit der Wiederaufnahme der Pipeline nach (rund 7 min je Seed). Das stünde dann im Bericht.

## Dependency-Check
- Neue Pakete: *N/A*, weil keines dazukommt. `numpy` und `faster_whisper.vad` samt Silero-Modell sind mit dem Extra `whisper` installiert, das WAV liest `wave` aus der stdlib.
- Neues Modell: *N/A*, weil Silero-VAD schon in jedem Pipeline-Lauf mitläuft. Es läuft lokal auf der CPU.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. `vad.json` ist eine Arbeitsdatei des Spikes.

## Chunks
### Chunk 1 — Werkzeug `omissions.py`
- Dateien: `scripts/spike/omissions.py` (neu), `scripts/spike/README.md` (Abschnitt „Auslassungs-Spike (TOOL-101)")
- Änderung:
  - Aufruf `omissions.py <gruppe>/<ordinal> [--variant base] [--seeds 3] [--clip NAME=DATEI@H:MM:SS-H:MM:SS]… [--config PATH]`, Clips wie in `asr.py score`
  - Wortzeiten für alle Referenzwörter, Abgleich mit `calibration.align`
  - Merkmale nach der Tabelle oben, VAD mit Cache und Summenprüfung
  - Markdown-Tabellen je Clip: Merkmale (Auslassungen gegen alle Referenzwörter, Mittel und Spanne über die Seeds, absolute Zahlen), Sprecher mit Pegel, Stabilität, erklärt und unerklärt, Lückenbreite, Sprache ohne Wörter
- Verify: `scripts/check`. Lauf an A und B:
  - Auslassungen je Seed gleich denen aus `asr.py score` für `base`
  - VAD-Summe innerhalb 1 s von `duration_after_vad`
  - die Klassen jedes Merkmals summieren sich zu den Auslassungen bzw. Referenzwörtern
  - die Ausgabe enthält keinen Text und kein Label
- AC: Messskript unter `scripts/spike/`, nur Kennzahlen in der Ausgabe.

### Chunk 2 — Messung und Tabellen
- Dateien: `docs/spikes/TOOL-101-auslassungen-verorten.md` (neu)
- Änderung: Lauf an der Pilotsitzung (A, B) und an der zweiten Sitzung (C, Hochdeutsch), je `base` mit den Seeds 1–3. Der Bericht bekommt Material und Methode (Wortzeiten, Schwellen, Grenzen der Verortung) und je Merkmal eine Tabelle mit A, B und C.
- Verify: `scripts/check`. Die Tabellen kommen 1:1 aus dem Skript. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots ergibt keinen Treffer.
- AC: Anteil der Auslassungen je Merkmal an A, B und C mit Vergleichswert und absoluten Zahlen.

### Chunk 3 — Auswertung, Empfehlung, Übergaben
- Dateien: `docs/spikes/TOOL-101-auslassungen-verorten.md`, `docs/plans/TOOL-101-omission-location.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung und Abschnitt „Erklärt und unerklärt": welcher Anteil auf Überlappung, kurze Beiträge, Pegel und Fallback fällt, mit dem Hinweis, wo die Zahlen zu klein für eine Aussage sind
  - Reihenfolge für TOOL-102 bis TOOL-105 mit Begründung aus den Tabellen, bei TOOL-104 die Vorrangregel aus dessen Ticket (Punkte 1, 2, 5 oder 3, 4)
  - Zuschnitt von TOOL-82
  - Aussage zu „Sprache ohne Wörter" als Hinweis: Trefferquote gegen zusätzlich markierte Zeit; bei brauchbarem Verhältnis ein Folge-Ticket anlegen
  - Kommentare an TOOL-100 (Reihenfolge), TOOL-82 (Zuschnitt) und TOOL-102 (Stabilität über die Seeds)
- Verify: `scripts/check`. Jede Aussage der Kurzfassung verweist auf eine Tabelle, jeder Eintrag unter „Folge-Tickets" trägt einen Key oder `[kein Ticket: …]`.
- AC: Aussage zum erklärten und unerklärten Anteil, Empfehlung zur Reihenfolge in TOOL-100 und zum Zuschnitt von TOOL-82.

## Folge-Tickets
- TOOL-100: Kommentar mit der empfohlenen Reihenfolge der übrigen Tickets.
- TOOL-82: Kommentar mit dem empfohlenen Zuschnitt; das Ticket bleibt zurückgestellt, bis die Projektverantwortliche entscheidet.
- TOOL-102: Kommentar mit der Stabilität der Auslassungen über die Seeds als Vorarbeit für das Orakel.
- TOOL-103, TOOL-104, TOOL-105: Reihenfolge und Begründung stehen im Kommentar an TOOL-100, die Tickets selbst bleiben unverändert.
- Neuer Hinweis „Sprache ohne Wörter" in der Bewertung: [kein Ticket: entsteht erst in Chunk 3, falls Trefferquote und markierte Zeit dafür sprechen]
- Roadmap-Eintrag für Phase 9: [kein Ticket: liegt als `dc986c2` auf dem lokalen Branch `tool-100-roadmap-omissions` und muss vor `/close-ticket` auf `main` sein]
- Ticketbeschreibung TOOL-101 „B hat keine Sprecher": [kein Ticket: überholt seit TOOL-60, im Bericht unter Material vermerkt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug `scripts/spike/omissions.py` | no |
| 2 | Messung an A, B, C und Tabellen im Bericht | no |
| 3 | Auswertung, Empfehlung, Übergaben | no |
