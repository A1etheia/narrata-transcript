# TOOL-92 — Spike: Entrauschen vor der Erkennung messen

## Ziel
Gemessen wird, ob ein lokaler Rauschfilter vor ASR und Diarisierung an der Pilotsitzung bessere Ergebnisse liefert als das Roh-WAV: Wortfehler, Halluzinationen, unsichere Passagen, Sprecherfehler und Laufzeit. Heute kennt die Pipeline keinen Filter, und für die Erkennung gibt es nur die Vermutung aus TOOL-91 (2 von 16 Clips für Menschen besser verständlich). Ergebnis: das Spike-Dokument mit Go/No-Go als Eingang für TOOL-60.

## Ist-Stand
- Die Pilotsitzung liegt fertig unter `work/<s>/`: `audio/segment-01.wav` (5:00:00, 16 kHz mono), Manifest, Snapshot `186e030dc24e`, ASR und Diarisierung von TOOL-58.
- Handreferenzen: `review/calibration/reference-1.txt` (A, Segment 1, 0:00:00–0:04:06, 551 Wörter, Sprecher S1–S3) und `reference-2.txt` (B, 1:20:00–1:23:00, 489 Wörter, ohne Sprecher, derselbe Clip wie TOOL-62/35).
- `transcript calibrate` (`src/transcript/calibration.py:301` `measure`, `:322` `evaluate`) liefert WER, Ersetzungen, Auslassungen und Einfügungen, markierte Passagen, übersehene Fehler und AUC aus dem gespeicherten Transkript einer Session.
- `SessionPaths` (`src/transcript/session.py:84`) hängt nur an `paths.root`. Eine zweite Wurzel mit denselben Dateien und einem gefilterten WAV durchläuft `transcribe` (`src/transcript/transcription.py:95`) also unverändert, mit Hinweisen, Bewertung und Diarisierung.
- Das Manifest prüft die Frame-Zahl des WAV (`src/transcript/manifest.py:212` `_checked_frames`), keinen Hash. Ein Filter muss die Länge also exakt halten.
- ffmpeg 4.4.2 hat `highpass`, `afftdn` und `arnndn`. Für `arnndn` fehlt ein RNNoise-Modell, für DeepFilterNet das Werkzeug.
- WDER-Code aus TOOL-20: `scripts/spike/speakers.py` im Stand `2f5b875` (`best_mapping`, `label_at`).

## Entscheidungen
- **Schattenwurzel pro Kandidat statt eigenem Runner.** `work/<s>/experiments/denoise/<kandidat>/` ist eine eigene `paths.root` mit Kopien von Manifest, `audio.json` und `narrata/` sowie dem gefilterten `segment-01.wav`. Gerechnet wird mit `.venv/bin/transcript transcribe <s> --segment 1 --config <kandidat>/config.yaml`. So misst der Spike genau die Pipeline, die später filtern würde, ohne Pipeline-Code zu ändern.
- **Ganzes Segment 1 statt Ausschnitt.** Whisper und pyannote verhalten sich auf 5 h anders als auf einem Clip (Kontext, Clustering). Ein Kandidat kostet rund 10 min Rechenzeit plus den Filter, und das läuft im Hintergrund. Segment 2 hat keine Referenz und bleibt draußen.
- **Kandidaten, gestuft:**
  1. `base` (Roh-WAV, in der Schattenwurzel neu gerechnet)
  2. `hp` (`highpass=f=80`)
  3. `hp-afftdn` (`highpass=f=80,afftdn=nf=-25`, die mittlere Kette aus TOOL-91)
  4. `arnndn` (RNNoise-Modell `lq.rnnn` für Stimme unter allgemeinem Störgeräusch, bei 48 kHz)
  5. `dfn` (DeepFilterNet 3, `deep-filter`, bei 48 kHz)

  Eine `hp`-Variante von `arnndn` oder `dfn` kommt nur dazu, wenn einer der beiden die Basis schlägt.
- **Drei Läufe pro Kandidat (Nachtrag nach den ersten Läufen).** Zwei Läufe von `base` auf demselben WAV lagen an B bei 46,4 % und 33,7 % WER. Vermutete Ursache ist der Temperatur-Fallback von faster-whisper, der ohne festen Seed Stichproben zieht; das Backend setzt `temperature` nicht (`src/transcript/asr/whisper.py:48`). Jeder Kandidat läuft deshalb dreimal in eigenen Wurzeln `<kandidat>.run<n>` mit demselben WAV, verglichen werden Mittelwert und Spanne. Zusätzlich läuft `base-t0` zweimal mit `temperature=0` (nur im Spike, über die festen Whisper-Einstellungen, im Transkript vermerkt). Der Kandidat zeigt, ob der Fallback die Streuung und die Auslassungen verursacht, und ist ein Eingang für TOOL-93.
- **Länge exakt halten:** Nach jedem Filter folgt `aresample=16000,apad,atrim=end_sample=<frames>`, danach prüft das Skript die Frames gegen das Manifest.
- **Kennzahlen:**
  - WER A/B über `calibration.measure` auf den Schattenpfaden. Das Rauschen ergibt sich aus der Spanne der drei `base`-Läufe, nicht aus den 1–2 Punkten von TOOL-62.
  - Halluzination wie in TOOL-62: Wortzahl, Anteil der 5-Wort-Folgen, die mindestens dreimal vorkommen, Anteil verschiedener Wörter, alles über Segment 1.
  - Unsicherheit: Passagen und Zeitanteil je Stufe über Segment 1 (`segment_assessment`).
  - Diarisierung: Zahl der Labels in Segment 1, WDER an A nach der TOOL-20-Methode, Übereinstimmung der Labels mit `base` nach der besten 1:1-Zuordnung.
  - Laufzeit: Filter pro Stunde Audio, ASR und Diarisierung aus `elapsed_ms`.
- **Keine Hörstichprobe** im Spike. Eine blinde Stichprobe wie in TOOL-20 lohnt sich erst, wenn ein Kandidat Go bekommt. Dann gehört sie ins Umsetzungsticket.
- **Go-Regel:** Go nur, wenn ein Kandidat die WER an A und B im Mittel der drei Läufe so weit senkt, dass sich die Spannen von Kandidat und `base` nicht überlappen, ohne dass Halluzinationen oder WDER steigen. Hilft er nur einer Seite, bekommt nur diese Seite die gefilterte Eingabe (Leitplanke im Ticket).

## Daten-Check
- Audio, Schattenwurzeln, Transkripte und Läufe: *handled*. Alles liegt unter `work/<s>/experiments/denoise/`, `work/` ist gitignored.
- Konsole und Skriptausgabe: *handled*. Nur Zähler, Anteile und Laufzeiten, nie Text, Labels von Personen oder der Session-Key (wie `_calibrate`, `src/transcript/__main__.py:865`).
- Spike-Dokument: *handled*. Nur Kennzahlen, kein Transkripttext, keine Namen, kein Session-Key (Muster wie TOOL-62/TOOL-58).
- Fixtures: *N/A*, weil der Spike keine anlegt.
- Rohaudio lokal: *handled*. Alle Filter laufen lokal, nur Werkzeug und Modell werden einmal heruntergeladen.

## Contract-Check
*N/A*: Der Spike liest und schreibt keine Contract-JSON und spricht den Narrata-Endpoint nicht an. Der Snapshot wird kopiert, nicht abgerufen.

## Resume-Check
- Abbruch beim Filtern: *handled*. Das Skript schreibt in eine temporäre Datei und benennt sie erst nach der Frame-Prüfung um. Ein vorhandenes WAV mit passenden Frames und gleicher Filterkette (vermerkt in `<kandidat>/filter.json`) wird wiederverwendet.
- Abbruch in `transcribe`: *handled*. Die Wiederaufnahme der Pipeline greift pro Schattenwurzel (TOOL-17), fertige ASR und Diarisierung werden wiederverwendet.
- Gleiches Modell und gleicher Snapshot: *handled*. Alle Wurzeln nutzen dieselbe Config bis auf `paths.root` und denselben kopierten Snapshot. `score` bricht ab, wenn Modell-Revision oder `knowledge_snapshot_id` zwischen Kandidaten abweichen.

## Dependency-Check
- ffmpeg-Filter `highpass`, `afftdn`, `arnndn`: *handled*. Schon installiert (4.4.2), lokal, CPU.
- RNNoise-Modell `lq.rnnn` (GregorR/rnnoise-models; laut README nicht urheberrechtlich geschützt): *handled*. Wird einmal nach `~/.cache/narrata-spike/denoise/` geladen, nicht ins Repo. Die Lizenz wird beim Download geprüft und im Bericht genannt.
- DeepFilterNet 3: *handled*. Das vorgebaute `deep-filter`-Binary (MIT/Apache-2.0) aus den GitHub-Releases nach `~/.cache/narrata-spike/denoise/`, ohne Python-Abhängigkeit und ohne Konflikt mit torch in der venv. Es läuft auf der CPU. Dauert es über 60 min für 5 h, wird nur gemessen und das im Bericht als Kostenargument vermerkt.
- `pyproject.toml`: *N/A*, weil keine neue Paket-Abhängigkeit dazukommt.

## Format-Check
*N/A*: Kein internes Format ändert sich. Der Spike liest Referenz-, Diarisierungs- und Bewertungsdateien nur.

## Chunks
### Chunk 1 — Spike-Werkzeug
- Dateien: `scripts/spike/denoise.py`, `scripts/spike/README.md`
- Änderung: `prepare <s> <kandidat>` baut die Schattenwurzel und filtert (Ketten als Tabelle im Skript, Frame-Prüfung über `audio.wav_frames`, `filter.json` mit Kette, Werkzeugversion und Filterzeit). `score <s> <kandidat>…` liest pro Wurzel Referenz, Diarisierung und Bewertung und schreibt eine Markdown-Tabelle nur mit Kennzahlen auf stdout. WDER und Label-Abgleich werden nach `2f5b875:scripts/spike/speakers.py` nachgebaut, WER über `calibration.measure`. Das README beschreibt Einrichtung (Downloads), Ablauf und Datenschutz.
- Verify: `scripts/check`; `prepare` für `hp` auf echten Daten, Frames gleich dem Manifest.
- AC: Messskripte unter `scripts/spike/`, keine Ausgabe mit Text oder Namen.

### Chunk 2 — Messläufe und Spike-Bericht
- Dateien: `docs/spikes/TOOL-92-entrauschen.md`
- Änderung: Alle Kandidaten vorbereiten und `transcribe` im Hintergrund nacheinander laufen lassen (nie parallel, RAM). `score` ausführen und den Bericht schreiben: Material und Methode, Kandidaten mit Lizenz, Messtabelle pro Kandidat, Laufzeit, Entscheidung mit Grund, Offen. Bei Go das Umsetzungsticket anlegen (Leitplanken aus TOOL-92: zusätzliche Arbeitsdatei, Filter in `settings`, getrennte Eingaben für ASR und Diarisierung möglich). Bei No-Go steht der Grund im Bericht.
- Verify: `scripts/check`; den Bericht mit `grep` auf Session-Key, Gruppennamen und Personennamen aus dem Snapshot prüfen (kein Treffer).
- AC: Spike-Dokument mit Messtabelle und begründeter Empfehlung; Go → Ticket angelegt, No-Go → Grund im Dokument.

## Folge-Tickets
- TOOL-60: Entscheidung „Entrauschen nein“ (No-Go, `docs/spikes/TOOL-92-entrauschen.md`); die Pilot-WER ist ein Einzellauf, an B liegt das Mittel aus drei Läufen bei 42,3 % statt 32,9 %, die V0.1-Bewertung sollte die Spanne nennen.
- TOOL-93: Whisper streut auf demselben WAV um bis zu 13 Punkte WER (Temperatur-Fallback), 1–2 Punkte Rauschen gelten nur für einen Lauf; jede Variante braucht mehrere Läufe oder einen festen Seed, `temperature=0` scheidet aus (Schleifen, höhere WER); `highpass=f=80` als zusätzliche Variante mitmessen.
- Umsetzung bei Go: [kein Ticket: entfällt mit No-Go]
- Hörstichprobe zur Diarisierung bei Go: [kein Ticket: Teil des Umsetzungstickets]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Spike-Werkzeug `scripts/spike/denoise.py` | no |
| 2 | Messläufe, Bericht, ggf. Umsetzungsticket | no |
