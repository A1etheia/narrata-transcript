# TOOL-104 — Recherche: sprecherbedingte Dekodierung, neue lokale Modelle und Batched-Pipeline gegen Auslassungen

## Ziel
TOOL-62 und TOOL-93 haben sechs lokale Modelle verglichen, aber weder die Batched-Pipeline von faster-whisper noch sprecherbedingte Erkennung, Sprachtrennung oder Modelle, die seitdem erschienen sind. Nach dem Ticket steht unter `docs/spikes/` ein Dokument mit einer Zeile je Kandidat und höchstens drei Kandidaten für eine Messung, jeder mit Folge-Ticket oder `[kein Ticket: <Grund>]`. Die Batched-Pipeline ist an allen Handreferenzen gemessen. Für Punkt 1, 2 und 5 (Überlappung, kurze Beiträge) gibt es zwei oder drei neue Handreferenz-Fenster an unruhigen Stellen und damit eine Entscheidung, die nicht mehr auf 16–52 Wörtern steht.

## Ist-Stand
- **Punkt 4 ist aus dem Code beantwortbar: Die Batched-Pipeline trägt Hotwords und Wortzeiten.** Installiert ist faster-whisper 1.2.1 (`pyproject.toml:16`). `BatchedInferencePipeline.transcribe` nimmt `hotwords` und `word_timestamps` an und reicht beide durch (`faster_whisper/transcribe.py:296`, `:544`, `:161`, `:190`). Die Messung an A und B ist damit Pflicht (Akzeptanzkriterium 3).
- **Die Batched-Pipeline dekodiert anders als die Pipeline, über den Zuschnitt hinaus:**
  - *Kein Temperatur-Fallback.* Sie nutzt nur die erste Temperatur (`:528`, `:233`), also 0. `log_prob_threshold`, `no_speech_threshold` und `compression_ratio_threshold` wirken nicht. Der Seed dürfte nichts ändern.
  - *Eigene VAD-Vorgaben.* Ohne `vad_parameters` gelten `max_speech_duration_s=30` und `min_silence_duration_ms=160` (`:399`), die Pipeline schneidet erst ab 2000 ms Stille.
  - *`without_timestamps=True` als Vorgabe* (`:283`): ein Segment je Abschnitt, Wortzeiten kommen trotzdem aus der Ausrichtung.
  - *`seek` ist der Beginn des Abschnitts auf der Originalzeit* (`:154`), nicht die Position im VAD-Audio.
  - *`clip_timestamps` nimmt eine Liste von Abschnitten* (`:426`). Das ist der Weg für Punkt 5: die Turns der Diarisierung als Abschnitte, ohne neues Modell.
- **Das Backend ruft `WhisperModel.transcribe` direkt** (`src/transcript/asr/whisper.py:237`) mit `FIXED_SETTINGS` (`:54`). Der Spike-Wrapper `_cli_with_variant` (`scripts/spike/asr.py:651`) ersetzt `WhisperBackend._prepare` und `transcribe` und schreibt Abweichungen in `asr.settings`; `transcribed` (`:866`) prüft sie beim Lesen.
- **Varianten** sind `<basis>[+<modifikator>…]` (`scripts/spike/asr.py:302`, `MODIFIERS` `:270`). `loud` (TOOL-103, Go mit Vorbehalt, Umsetzung TOOL-109) ist eine Basis (`:241`).
- **`omissions.py` passt nicht auf Batched-Läufe.** `vad_speech` (`scripts/spike/omissions.py:274`) rechnet mit den VAD-Optionen der Pipeline (`:56`), und `measure` bricht ab, wenn die Summe von `duration_after_vad` abweicht (`:640`). `asr.decode_windows` (`scripts/spike/asr.py:1269`) leitet Fenster und Fallback aus `seek` im VAD-Audio ab.
- **Fenstervorschläge gibt es nur für ruhige Stellen** (`asr.py windows`, `:1078`) und für Seed-Abweichung (`seeds.py --suggest`, `scripts/spike/seeds.py:221`). Überlappung und verbundene Turns liegen in `omissions.py` schon vor (`diarization.overlaps`, `Turns.joined`, `:215`, `:619`).
- **Läufe und Referenzen im Hauptcheckout:** `base.seed1..3` und `loud.seed1..3` für beide Sitzungen, `base+temp0.seed1..3` für die Pilotsitzung. Handreferenzen A, B, D, E (Pilotsitzung) und C (zweite Sitzung, Fassung Hochdeutsch); Clips laut `docs/spikes/TOOL-103-pegelausgleich.md:26`.
- **Vergleichswerte** (Mittel über drei Seeds, Kommentar an TOOL-100 vom 2026-11-23): WER `base` / `loud` 21,3 / 20,2 % (A), 29,8 / 26,5 % (B), 30,8 / 23,9 % (C), 61,2 / 36,7 % (D), 34,0 / 29,6 % (E).
- **Stand der Aussage zu Punkt 1, 2 und 5** (`docs/spikes/TOOL-101-auslassungen-verorten.md:144`, `:150`, `:254`, `:260`): 17 und 52 Referenzwörter in Überlappung, 16 und 23 in Beiträgen mit 1–3 Wörtern.
- **Umgebung:** RTX 3080 Ti mit 12 GB. Der Worktree hat weder `.venv` noch `work/`. Die Spike-Skripte haben keine Unit-Tests, `scripts/check` prüft sie mit ruff.

## Entscheidungen
- **Die Batched-Pipeline wird ein Modifikator `+batched`, kein eigenes Skript.** Der Wrapper legt für die Dauer von `transcribe` einen Stellvertreter um das Modell, der an `BatchedInferencePipeline(model).transcribe` weiterreicht. `batched`, `batch_size` (8, Vorgabe der Bibliothek) und `without_timestamps` stehen in `asr.settings`, nur bei Batched-Läufen, damit alle gespeicherten Wurzeln wiederverwendbar bleiben. Der Pipeline-Code unter `src/` bleibt unverändert.
- **Drei Varianten, vorab festgelegt:**

  | Variante | Frage |
  | --- | --- |
  | `base+batched` | Batched-Pipeline mit ihren Vorgaben, Hotwords und Wortzeiten |
  | `base+batched+ts` | dasselbe mit `without_timestamps=False`: Ändern Zeitstempel-Tokens Auslassungen oder Passagenzuschnitt? |
  | `loud+batched` | auf dem Audio, das die Pipeline nach TOOL-109 bekommt |

- **Vergleich gegen `base`, `base+temp0` und `loud`.** `base+temp0` trennt die Wirkung des fehlenden Fallbacks vom Zuschnitt je VAD-Abschnitt. Für die zweite Sitzung läuft `base+temp0` neu (drei Seeds).
- **Drei Seeds wie im Ticket, auch wenn sie gleich ausfallen dürften.** Sind die Läufe identisch, steht das als Befund im Bericht: Die Streuung zwischen den Seeds, die TOOL-102 und TOOL-103 beschäftigt hat, wäre dann weg.
- **Gemessen wird an A, B, C, D und E**, nicht nur an A und B. Die Ergänzung im Ticket verlangt alle Referenzen, und die Blockverluste sitzen an C, D und E.
- **Blockverluste über zwei Zahlen:** „Sprache ohne Wörter" aus `omissions.py` (Segment und Referenz C) und `asr.py sections --against base`. `omissions.py` rechnet die VAD für `+batched` mit deren Optionen. Die Merkmale „Fallback-Fenster" und „dünnes Fenster" entfallen für Batched-Läufe und erscheinen in der Tabelle als „entfällt".
- **Regel für ein Umsetzungsticket, wie TOOL-92 und TOOL-103:** An A und an B liegt die höchste WER der drei Seeds unter der niedrigsten des Vergleichs (`base+batched` gegen `base`, `loud+batched` gegen `loud`), und Einfügungen und Wiederholungsanteil liegen im Mittel nicht darüber. C, D und E sind Gegenprobe. Erfüllt eine Variante die Regel, zählt sie als einer der höchstens drei Kandidaten.
- **Neue Handreferenz: Vorschlag aus der Diarisierung, als `omissions.py --suggest`.** 3-min-Fenster im 1-min-Raster, außerhalb der bestehenden Clips und überschneidungsfrei, Rang nach Überlappungszeit plus Zahl der verbundenen Turns unter 2 s. Zwei Fenster an der Pilotsitzung, eines an der zweiten Sitzung. Ausgegeben werden nur Zeiten und Zähler. Sitzung und Zeitfenster gehen im Chat an die Projektverantwortliche, nicht ins Repo.
- **Die Entscheidung zu Punkt 1, 2 und 5 wartet auf die neuen Fenster**, wie im Ticket festgelegt. Ziel sind rund 100 Referenzwörter je Klasse (Überlappung, Beitrag mit 1–3 Wörtern). Chunk 4 beginnt erst, wenn die Dateien unter `review/calibration/` liegen.
- **Punkt 5 wird nur recherchiert, nicht gemessen.** Der Weg über `clip_timestamps` steht als Aufwandsangabe im Dokument; ob er einen der drei Plätze bekommt, entscheidet Chunk 4.
- **Auswahl der Kandidaten, vorab festgelegt:** Pflicht sind lokaler Betrieb ohne Netz, höchstens 12 GB VRAM, Deutsch und eine Lizenz, die den privaten Einsatz erlaubt. Danach zählt belegte Qualität auf deutschen Meeting- oder Fernfelddaten vor Benchmark-Werten auf gelesener Sprache. Fehlende Wortzeiten schließen nicht aus, wenn eine Zwangsausrichtung möglich ist; sie stehen dann im Aufwand.
- **Recherche über Websuche, Primärquellen zuerst** (Modellkarten, Repos, Paper). Jede Tabellenzeile nennt ihre Quelle. Was nicht belegt ist, steht als „nicht belegt" in der Zelle. Kein Modell wird in diesem Ticket heruntergeladen oder installiert.
- **Läufe aus dem Worktree** wie in TOOL-101 bis TOOL-103: Python aus der `.venv` des Hauptcheckouts, `--config` auf dessen `config/config.yaml`, als Hintergrundbefehl nacheinander, nie parallel.
- **Laufzeit:** 9 Batched-Läufe je Sitzung plus 3 Läufe `base+temp0` an der zweiten Sitzung. Die Batched-Läufe sollten deutlich unter den 7 min eines `base`-Laufs liegen, zusammen höchstens 1,5 h GPU.

## Daten-Check
- Läufe, Kopien von Manifest und Snapshot, VAD-Zwischenspeicher: *handled* — alles bleibt unter `work/<s>/experiments/asr/` im Hauptcheckout (TOOL-66). Rohaudio verlässt den Rechner nicht.
- Websuche: *handled* — die Anfragen nennen nur Modell- und Verfahrensnamen. Kein Audio, kein Transkripttext, kein Name, kein Session-Schlüssel geht nach außen. Cloud-Dienste werden höchstens mit veröffentlichten Werten zitiert.
- Konsole: *handled* — nur Zähler, Anteile, WER und Zeiten. `--suggest` gibt Fenstergrenzen und Zähler aus, keine Labels.
- Neue Handreferenzen: *handled* — sie liegen unter `review/calibration/` im Hauptcheckout und kommen nie ins Repo. Der Bericht nennt Fenster und Wortzahl, die Sitzungen heißen „Pilotsitzung" und „zweite Sitzung".
- Spike-Dokument und README: *handled* — nur Kennzahlen und öffentliche Quellen, Befehle nutzen `$S`. Chunk 2 bis 5 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Fehlermeldungen: *handled* — `SpikeError` nennt Variante, Seed und Clipname.
- Fixtures: *N/A*, weil keine angelegt werden.

## Contract-Check
*N/A*, weil das Ticket keine Contract-JSON liest oder schreibt. Bekommt die Batched-Pipeline ein Umsetzungsticket, stehen `batched` und `batch_size` in `asr.settings` des internen Referenzformats; ob der Contract (IOA-1214) sie trägt, klärt jenes Ticket.

## Resume-Check
- Abbruch beim Transkribieren: *handled* — die Wiederaufnahme der Pipeline gilt je Wurzel, ein neuer `run` überspringt fertige Wurzeln.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings, neu auch `batched`, `batch_size` und `without_timestamps`. `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot ab. Weicht eine Batched-Variante von den gespeicherten Vergleichsläufen ab, laufen diese neu und der Bericht nennt es.
- VAD-Zwischenspeicher: *handled* — `vad.json` hält die Optionen; andere Optionen rechnen neu. Die Batched-VAD bekommt eine eigene Datei, damit der Speicher der Pipeline-VAD bleibt.
- Abbruch der Recherche: *handled* — die Tabelle im Dokument wächst zeilenweise, jede Zeile mit Quelle; ein neuer Anlauf setzt dort fort.

## Dependency-Check
- Batched-Pipeline: *handled* — Teil des installierten faster-whisper 1.2.1, kein neues Paket, kein neues Modell, läuft lokal auf der GPU. VRAM bei `batch_size=8` misst `run.json`.
- Recherchierte Modelle und Verfahren: *N/A*, weil dieses Ticket keines installiert. Lizenz, VRAM und Laufzeit je Kandidat sind Spalten des Dokuments; Installation und Messung gehören in die Folge-Tickets.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. Die neuen Schlüssel in `asr.settings` entstehen nur in Spike-Wurzeln.

## Chunks
### Chunk 1 — Werkzeug: `+batched`, `omissions.py` für Batched-Läufe, Fenstervorschlag
- Dateien: `scripts/spike/asr.py`, `scripts/spike/omissions.py`, `scripts/spike/README.md` (Abschnitt „Batched-Spike (TOOL-104)")
- Änderung:
  - Modifikatoren `batched` und `ts` in `asr.py`; Stellvertreter um das Modell in `_cli_with_variant`; Settings in `asr.settings` und in der Prüfung von `transcribed`; `ts` ohne `batched` ist ein Fehler
  - `omissions.py`: VAD-Optionen der Batched-Pipeline für `+batched`, eigener Zwischenspeicher; „Fallback-Fenster" und „dünnes Fenster" entfallen dort
  - `omissions.py --suggest`: unruhige 3-min-Fenster aus der Diarisierung der Sitzung, außerhalb der angegebenen Clips
- Verify: `scripts/check`. Im Hauptcheckout:
  - `asr.py score $S base --seeds 3` ergibt weiter 21,3 % (A) und 29,8 % (B)
  - `omissions.py $S` für `base` ergibt weiter 31/31/36 Auslassungen an A
  - `asr.py prepare` und `run` für `base+batched`, Seed 1, Pilotsitzung: Der Lauf endet, `asr.settings` trägt `batched`, die Wörter haben Zeiten, `keywords_used` ist nicht leer
  - `omissions.py $S --suggest` an beiden Sitzungen gibt Fenster außerhalb von A–E aus
- AC: Punkt 4 ist am Lauf belegt (Hotwords und Wortzeiten). Die Projektverantwortliche bekommt Sitzung und Zeitfenster im Chat.

### Chunk 2 — Messung der Batched-Pipeline an A bis E
- Dateien: `docs/spikes/TOOL-104-recherche-auslassungen.md` (neu)
- Änderung:
  - `asr.py run` für `base+batched`, `base+batched+ts`, `loud+batched` mit drei Seeds an beiden Sitzungen, `base+temp0` an der zweiten Sitzung
  - `asr.py score` mit `base`, `base+temp0`, `loud` an A, B, D, E und an C
  - `omissions.py --variant base+batched` und `asr.py sections --against base` für die Blockverluste
  - Bericht: Material und Methode, Antwort auf Punkt 4 (was die Batched-Pipeline trägt und was sie anders macht), Messtabellen, Ergebnis nach der Regel oben, Laufzeit und VRAM
- Verify: `scripts/check`. Tabellen 1:1 aus dem Skript, je Variante drei Seeds an fünf Referenzen. Die Auslassungen je Seed aus `omissions.py` stimmen mit `asr.py score` überein. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: Punkt 4 beantwortet; Batched-Pipeline mit Hotwords an A und B mit drei Seeds gemessen.

### Chunk 3 — Recherche zu Punkt 3, 1, 2 und 5
- Dateien: `docs/spikes/TOOL-104-recherche-auslassungen.md`
- Änderung:
  - Punkt 3 zuerst: lokale ASR-Modelle seit TOOL-62 (Voxtral, Canary v2 und was die Suche sonst ergibt), dazu der Stand bairisch-fähiger lokaler Modelle (offener Punkt aus TOOL-60)
  - danach Punkt 1 (DiCoW und andere Target-Speaker-ASR, Zusammenspiel mit pyannote community-1), Punkt 2 (Trennmodelle für Mono-Fernfeld, Artefakte, Wirkung auf die WER), Punkt 5 (Dekodierung je Redebeitrag, mit dem Weg über `clip_timestamps`)
  - eine Tabellenzeile je Kandidat: Quelle, Lizenz, Hardware, Deutsch, Wortzeiten, Biasing, erwarteter Aufwand für ein Backend; darunter je Punkt zwei bis vier Sätze Einordnung
  - ausgeschiedene Ansätze mit dem Grund in einer Zeile (Lizenz, VRAM, kein Deutsch, nur Cloud)
- Verify: `scripts/check`. Jede Zeile hat eine Quelle und alle sieben Spalten gefüllt oder „nicht belegt". Kein Cloud-Dienst steht als Kandidat. `grep` wie in Chunk 2.
- AC: Dokument unter `docs/spikes/` mit einer Zeile je Kandidat; nur lokal lauffähige Ansätze.

### Chunk 4 — Neue Handreferenz: Verortung wiederholen, Punkt 1, 2 und 5 entscheiden
- Dateien: `docs/spikes/TOOL-104-recherche-auslassungen.md`
- Voraussetzung: Die neuen Fenster liegen unter `review/calibration/`.
- Änderung:
  - `omissions.py` für `base` mit allen Clips, alten und neuen: Wortzahl und Auslassungsrate je Klasse (Überlappung, Beitrag unter 2 s, Beitrag mit 1–3 Wörtern), Anteil an allen Auslassungen
  - `asr.py score` der Batched-Varianten und der Vergleichsläufe an den neuen Fenstern
  - Abschnitt „Überlappung und kurze Beiträge an unruhigen Stellen": Wie viel der Auslassungen könnten Punkt 1, 2 und 5 höchstens erreichen, und bekommt einer davon einen Messkandidaten?
- Verify: `scripts/check`. Die Klassen Überlappung und kurze Einwürfe tragen zusammen über die Referenzen rund 100 Wörter oder mehr; liegt eine darunter, nennt der Bericht die Zahl und die Aussage bleibt als vorläufig markiert. `grep` wie in Chunk 2.
- AC: `omissions.py` mit den neuen Fenstern erneut gelaufen; Kandidaten aus Punkt 3 und 4 an alten und neuen Referenzen gemessen, soweit sie in diesem Ticket laufen (Batched-Pipeline).

### Chunk 5 — Auswertung, Kandidaten, Übergaben
- Dateien: `docs/spikes/TOOL-104-recherche-auslassungen.md`, `docs/plans/TOOL-104-asr-research.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung: höchstens drei Kandidaten für eine Messung an A, B und C, oder die begründete Aussage, dass es keinen gibt
  - je Kandidat ein Folge-Ticket im Epic TOOL-100 oder `[kein Ticket: <Grund>]`
  - Kommentar an TOOL-100 mit dem Ergebnis für M9
- Verify: `scripts/check`. Jede Aussage der Kurzfassung verweist auf eine Tabelle oder Quelle, jeder Eintrag unter „Folge-Tickets" trägt einen Key oder `[kein Ticket: …]`.
- AC: höchstens drei Kandidaten, jeweils als Folge-Ticket oder mit `[kein Ticket: <Grund>]`.

## Folge-Tickets
- Messung je Kandidat (höchstens drei): [kein Ticket: die Kandidaten stehen erst nach Chunk 5 fest; die Keys werden dort nachgetragen]
- Umsetzung der Batched-Pipeline im Backend, falls sie die Regel erfüllt: [kein Ticket: hängt am Ergebnis von Chunk 2 und 4; wird in Chunk 5 angelegt oder mit Grund verworfen]
- Zusätzliche Handreferenz an unruhigen Stellen: [kein Ticket: Teil dieses Tickets, Rahmen im Epic TOOL-100]
- TOOL-100: Kommentar mit dem Ergebnis für den Reflexionspunkt M9, in Chunk 5.
- TOOL-109 (`loudnorm` in der Pipeline): bekommt in Chunk 5 einen Hinweis, falls `loud+batched` anders ausfällt als `base+batched`.
- TOOL-82 (Parakeet-Zweitlauf): bekommt in Chunk 5 einen Hinweis, falls die Recherche ein Modell findet, das den Zweitlauf besser trägt.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug: `+batched` in `asr.py`, `omissions.py` für Batched-Läufe, `--suggest` | no |
| 2 | Messung der Batched-Pipeline an A bis E, Antwort auf Punkt 4 | yes |
| 3 | Recherche zu Punkt 3, 1, 2 und 5, Kandidatentabelle | no |
| 4 | Neue Handreferenz, Verortung wiederholt, Entscheidung zu Punkt 1, 2 und 5 | no |
| 5 | Auswertung, Kandidaten, Übergaben | no |
