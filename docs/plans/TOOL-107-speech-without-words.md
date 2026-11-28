# TOOL-107 — Spike: Hinweis „Sprache ohne Wörter“ gegen `gap` und `sparse` messen

## Ziel
Nach dem Ticket ist gemessen, ob der Hinweis „die Diarisierung hört Sprache, der Lauf hat dort kein Wort“ Auslassungen zeigt, die `gap` und `sparse` heute nicht zeigen, und was er an markierter Zeit kostet. Heute ist nur bekannt, wie viele Auslassungen in solchen Stellen liegen, nicht, wie viele davon die Bewertung schon abdeckt und ob an den Stellen außerhalb der Handreferenzen wirklich Sprache fehlt. Ergebnis ist ein Spike-Dokument mit Go/No-Go nach einer vorab festgelegten Regel und, bei Go, ein Umsetzungsticket. An den Bewertungsregeln ändert das Ticket nichts.

## Ist-Stand
- **Die Messgrundlage des Tickets ist überholt.** Es nennt `base`, Seeds 1–3, an A, B, C. Hauptlauf ist seit TOOL-109 `norm`, Referenzen gibt es elf, A bis K (`docs/spikes/TOOL-109-hauptlauf.md:184`, `:25`).
- **`norm` verliert an C keine Blöcke mehr:** 88 / 92 / 88 Auslassungen (`docs/spikes/TOOL-109-hauptlauf.md:68`) gegen 80–177 bei `base` (`docs/spikes/TOOL-101-auslassungen-verorten.md:90`). Das Kriterium „an C deutlich mehr“ trägt mit `norm` nicht mehr.
- **Was über das Signal bei `norm` bekannt ist:**
  - 32 / 33 / 38 Stellen ab 2 s an der Pilotsitzung und 52 / 44 / 61 an der zweiten, zusammen 1,6 bis 3,9 min je Segment (`docs/spikes/TOOL-113-stellen.md:58`–`:71`).
  - Im Mittel liegen 30,3 der 584,3 Auslassungen in einer Stelle mit 2 s Polster (`:10`), fast nur an J (36 / 0 / 16) und C (11) (`:122`, `:155`).
  - Den Block an J sieht das Signal zur Hälfte (20 von 38 Wörtern), den an G gar nicht (`:164`).
- **Die markierte Zeit ist schon hoch:** 87,7 % und 90,3 % mit den Schwellen seit TOOL-109 (`docs/spikes/TOOL-109-hauptlauf.md:133`). Neu markierte Passagen können höchstens rund 10 Punkte ausmachen. Der Kommentar aus TOOL-102 am Ticket verlangt deshalb, auch die Stelle in der Passage zu zählen.
- **Was die Bewertung heute zeigt** (`src/transcript/uncertainty.py:224`):
  - `gap`: nur die größte Pause zwischen zwei Wörtern *derselben* Passage, ab `gap_ms` 2,5 s; der Grund nennt das Wort nach der Pause (`:237`–`:247`).
  - `sparse`: Passage ab 1 s mit weniger als 1 Wort je Sekunde, ohne Stelle (`:248`–`:253`).
  - Pausen *zwischen* zwei Passagen prüft keine Regel. Seit dem Teilen am Sprecherwechsel (TOOL-96) sind das viele.
- **Werkzeug, das es schon gibt:**
  - *Sprache ohne Wörter:* `omissions.silence` (`scripts/spike/omissions.py:366`) mit festen Konstanten `BRIDGE_WORDS_MS` 1 s und `LONG_SILENT_MS` 2 s (`:56`–`:57`); `Ranges` mit Vereinigung, Differenz, Schnitt (`:98`).
  - *Wortzeit je Referenzwort:* `omissions.heard`, `omissions.timeline` (`:155`, `:189`).
  - *Läufe laden, Auslassungen je Lauf, längste Folge:* `spots.load` (`scripts/spike/spots.py:115`), `seeds.clip_run`, `spots._longest` (`:187`).
  - *Bewertung im Speicher:* `uncertainty.assess` (`src/transcript/uncertainty.py:91`), Gründe mit Regel und Wortposition (`Reason`, `:73`).
  - *Passagen am Sprecherwechsel im Speicher:* `diarization.assign_speakers(reference, run, min_turn_ms)` (`src/transcript/diarization/__init__.py:321`), schreibt nichts.
- **Zwei Fallen aus dem Recon:**
  - Die Seeds 2 und 3 von `norm` sind ohne Diarisierung gespeichert und markieren 95–97 % der Zeit (`docs/spikes/TOOL-109-hauptlauf.md:107`). Ihre Passagen sind mit Seed 1 nicht vergleichbar.
  - Die Spike-Skripte lesen die Schwellen aus der `config.yaml` der Schattenwurzel (`scripts/spike/asr.py:958`). Das ist eine Kopie vom Tag des `prepare` und kann die alten Schwellen tragen.
- **Whisper dehnt das Wort vor übersprungener Sprache über die Lücke** (`scripts/spike/omissions.py:161`). `silence` rechnet mit den rohen Wortzeiten, ein gedehntes Wort verdeckt die Stelle. Das kann erklären, warum der Block an G unsichtbar bleibt.
- **Vorhandene Läufe im Hauptcheckout:** `norm` und `base`, Seeds 1–3, beide Sitzungen; Handreferenzen A, B, D, E, F, G, I an der Pilotsitzung, C, H, J, K an der zweiten.
- **Umgebung:** Der Worktree hat weder `.venv` noch `work/`. Läufe mit dem Python des Hauptcheckouts, `PYTHONPATH=src` und einer Config mit absolutem `paths.root` im Scratchpad. Die Spike-Skripte haben keine Unit-Tests, die Qualitätsprüfung ist ruff.

## Entscheidungen
- **`norm` entscheidet, `base` läuft als Vergleichszeile mit** (Projektverantwortliche, 2026-11-27). Go/No-Go an `norm`, Seeds 1–3, A bis K. `base` schließt an die Zahlen aus TOOL-101 an und zeigt, was der Hinweis bei einem Lauf mit Blockverlusten leistet. Kein neuer ASR-Lauf.
- **Go-Regel, vor der Messung festgelegt** (Projektverantwortliche, 2026-11-27). Sie gilt an der heutigen Definition: Stelle ab 2 s, Brücke 1 s, rohe Wortzeiten. Go, wenn alle drei Punkte gelten:
  1. *Zusatznutzen:* Über A bis K, Mittel der drei `norm`-Seeds, liegen mit dem Hinweis mindestens 50 % mehr Auslassungen an einer gezeigten Stelle als mit `gap` und `sparse` allein, und mindestens 20 Auslassungen mehr.
  2. *Treffsicherheit:* In der Hörstichprobe fehlt an mindestens der Hälfte der beantworteten Stellen wirklich Sprache.
  3. *Kosten:* Bisher `confident`-Passagen, die der Hinweis neu markiert, erhöhen die markierte Zeit je Sitzung um höchstens 2 Punkte (Mittel der `norm`-Seeds).
- **Gezeigte Stelle:**
  - `gap`: die Pause vor dem Wort, das der Grund nennt.
  - `sparse`: die ganze Spanne der Passage.
  - Hinweis: die Stelle selbst.
  - Eine Auslassung zählt, wenn ihre Wortzeit (`omissions.timeline`, Median über die Läufe der Variante) in der Stelle liegt.
- **Passage zur Stelle:** jede Passage, deren Spanne die Stelle schneidet; liegt die Stelle ganz zwischen zwei Passagen, die davor und die danach. „Neu markiert“ sind die `confident`-Passagen darunter.
- **Alle Läufe bekommen die Passagen im Speicher:** `assign_speakers` mit der Diarisierung der Sitzung und `diarization.min_turn_ms` aus der Config, bewertet mit `assess` ohne Hinweise und mit den Schwellen aus `--config` (heutige Defaults), nicht aus der Schattenwurzel. Kontrolle: Für `norm#1` steht daneben die markierte Zeit der gespeicherten Fassung mit Hinweisen (87,7 % / 90,3 %).
- **Variation wie im Ticket, dazu eine Zeile:** Schwelle 1 / 2 / 3 s mal Brücke 0,5 / 1 / 2 s. Zusätzlich an 2 s / 1 s die Zeile „Wortlänge auf 1 s gekappt“ (`MAX_WORD_MS`), weil gedehnte Wörter Stellen verdecken. Die Variation zählt nicht für die Go-Regel, sie geht bei Go ins Umsetzungsticket.
- **Hörstichprobe:** 20 Stellen ab 2 s aus `norm#1`, 10 je Sitzung, mit festem Zufallswert gezogen, außerhalb der Fenster A bis K. Das Skript nennt nur Zeitfenster mit 3 s Rand je Seite. Die Projektverantwortliche tippt je Fenster ab, was gesagt wird, oder vermerkt „keine Sprache“. „Sprache fehlt“ heißt: Gegen die Wörter des Laufs im Fenster sind mindestens 2 getippte Wörter ausgelassen (ein einzelnes kann vom Rand stammen). Ohne Stichprobe ist Punkt 2 offen und es gibt kein Go.
- **Ein neues Skript `scripts/spike/hint.py`.** `omissions.silence` bekommt Brücke und Kappung als Parameter mit den heutigen Werten als Default; `omissions.py` und `spots.py` rechnen unverändert.
- **Der Pipeline-Code unter `src/` bleibt unverändert.**

## Daten-Check
- Läufe, Diarisierung, Handreferenzen: *handled* — nur gelesen, alles bleibt unter `work/` im Hauptcheckout (TOOL-66).
- Stichprobendatei: *handled* — liegt unter `review/calibration/` der jeweiligen Sitzung im Hauptcheckout, nie im Repo. Das Skript schreibt sie nur, wenn sie fehlt (Zeitfenster und leere Zeilen), und überschreibt Getipptes nie.
- Konsole: *handled* — nur Zähler, Anteile, Zeiten. Für die Stichprobe Zeitfenster, kein Text, keine Labels. `SpikeError` nennt Variante, Seed, Clipname.
- Spike-Dokument und README: *handled* — nur Kennzahlen, „Pilotsitzung“ und „zweite Sitzung“, Befehle mit `$S`, keine Zeitfenster der Stichprobe. Chunk 2 und 3 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Scratch-Config mit absolutem Pfad: *handled* — im Scratchpad der Sitzung, nie im Repo.
- Fixtures: *N/A*, weil keine entsteht.

## Contract-Check
*N/A*, weil das Ticket keine Contract-JSON liest oder schreibt. Bei Go klärt das Umsetzungsticket, ob der Hinweis den vorhandenen Marker `gap` des Contracts nutzt (`src/transcript/markers.py:51`) oder nur als Grund in der Bewertung steht (IOA-1214).

## Resume-Check
*N/A*, weil kein Modell läuft: Das Skript liest gespeicherte Läufe und rechnet in Sekunden. Gleiches Modell und gleicher Snapshot über die Seeds: *handled* über `asr.check_provenance`.

## Dependency-Check
*N/A*, weil kein neues Paket und kein neues Modell dazukommt.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. Die Stichprobendatei ist eine Arbeitsdatei des Spikes.

## Chunks
### Chunk 1 — `hint.py`: Stellen gegen die Bewertung
- Dateien: `scripts/spike/hint.py` (neu), `scripts/spike/omissions.py` (`silence` mit `bridge_ms` und `cap_ms`), `scripts/spike/README.md` (Abschnitt „Hinweis-Spike (TOOL-107)“)
- Änderung:
  - Aufruf `hint.py $S [--variant norm] [--seeds 3] [--clip …] [--config PATH]`
  - je Lauf: Passagen im Speicher teilen, bewerten, Stellen je Schwelle und Brücke bestimmen
  - *Segment*, je Schwelle, Brücke und Lauf: Stellen und Zeit darin; davon in einer `gap`-Pause, in einer `sparse`-Passage, in einer aus anderem Grund markierten Passage, in einer `confident`-Passage, zwischen zwei Passagen; neu markierte Passagen, ihre Zeit, markierte Zeit vorher und nachher in Punkten
  - *je Referenz und Lauf*: Auslassungen, davon an einer `gap`-Pause, in einer `sparse`-Passage, beides zusammen, in einer Stelle des Hinweises, alles zusammen, Zuwachs; längste Folge ausgelassener Wörter und ihr Anteil in einer Stelle; Referenzwörter in den Stellen und der Anteil, der fehlt
  - *Regelzeile*: Summe über die Referenzen im Mittel der Seeds, Zuwachs absolut und in Prozent
  - `--sample N` zieht die Stichprobe und legt die Datei an, `--sampled` zählt sie aus: Stellen mit fehlender Sprache, ohne Sprache, unbeantwortet, getrennt nach schon markiert und neu
  - README: Definitionen, Ablauf, Datenschutz
- Verify: ruff mit dem venv des Hauptcheckouts (`ruff check .`, `ruff format --check .`), `PYTHONPATH=src … python -m unittest discover -s tests`. Im Hauptcheckout:
  - `asr.py score $S base --seeds 3` ergibt weiter 21,3 % (A) und 29,8 % (B)
  - Stellen ab 2 s bei Brücke 1 s je `norm`-Seed: 32 / 33 / 38 und 52 / 44 / 61 wie in TOOL-113
  - Auslassungen je Lauf und Referenz wie in `docs/spikes/TOOL-109-hauptlauf.md:66`
  - `omissions.py` und `spots.py` geben für `norm` dieselben Segmenttabellen wie vor der Änderung
- AC: je Stelle ab 1 s und ab 2 s geprüft, ob die Passage dort schon `needs_review` oder `uncertain` ist und mit welchem Grund.

### Chunk 2 — Messen, Stichprobe ziehen
- Dateien: `docs/spikes/TOOL-107-sprache-ohne-woerter.md` (neu)
- Änderung:
  - `hint.py` für `norm` und `base` an A bis K, beide Sitzungen
  - Bericht: Material und Methode mit Go-Regel im Wortlaut, Tabelle je Schwelle und Brücke, Tabellen je Referenz, Stand gegen Punkt 1 und 3 der Regel
  - `hint.py --sample 10` je Sitzung
  - Halt: Zeitfenster der Projektverantwortlichen zum Abtippen übergeben. Steht Punkt 1 oder 3 schon auf No-Go, sagt die Übergabe das dazu; die Stichprobe ist dann freiwillig.
- Verify: Tabellen 1:1 aus dem Skript. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: Tabelle je Schwelle mit neu markierten Passagen und Zeit und den darin gefundenen Auslassungen; über beide Sitzungen Zahl der neu markierten Passagen und Anteil der Sitzungszeit; nur Kennzahlen, alles lokal.

### Chunk 3 — Stichprobe auswerten, Go/No-Go, Übergaben
- Dateien: `docs/spikes/TOOL-107-sprache-ohne-woerter.md`, `docs/plans/TOOL-107-speech-without-words.md` (Folge-Tickets nachtragen)
- Änderung:
  - `hint.py --sampled` je Sitzung, Spalte „Stellen mit fehlender Sprache“ über das Segment
  - Kurzfassung und Regeltabelle: jeder Punkt der Go-Regel mit Zahl
  - Entscheidung der Projektverantwortlichen einholen und mit Datum eintragen
  - bei Go: Umsetzungsticket im Epic TOOL-100 mit der Frage, wie der Hinweis ohne Diarisierung unter `missing` steht, mit der gewählten Schwelle und Brücke und der Frage nach dem Contract-Marker
  - Kommentar an TOOL-100 mit dem Ergebnis
- Verify: Jede Aussage der Kurzfassung verweist auf eine Tabelle. Jeder Eintrag unter „Folge-Tickets“ trägt einen Key oder `[kein Ticket: …]`. `grep` wie in Chunk 2.
- AC: Go nur nach der vorab festgelegten Regel, sonst begründetes No-Go; bei Go ein Umsetzungsticket; ohne Stichprobe sagt der Bericht, dass die Treffsicherheit außerhalb der Referenzen offen ist.

## Folge-Tickets
- Umsetzung des Hinweises in der Bewertung: TOOL-116, angelegt am 2026-11-27 im Epic TOOL-100 nach dem Go mit bewusster Abweichung. Es trägt die Fragen nach `missing` ohne Diarisierung, nach Stellen zwischen zwei Passagen, nach den Sprachbereichen im Referenzformat und nach dem Contract-Marker.
- Gekappte Wortlänge als Variante: TOOL-116, als Prüfpunkt mit eigener Stichprobe.
- TOOL-100: Kommentar vom 2026-11-27 mit dem Ergebnis.
- Beschreibung von TOOL-107 nennt noch `base` an A, B, C: [kein Ticket: Kommentar vom 2026-11-27 zum neuen Zuschnitt am Ticket selbst]
- Schattenwurzeln tragen eine alte Kopie der Schwellen: [kein Ticket: betrifft nur Spike-Skripte, `hint.py` liest die Schwellen aus `--config`; im Bericht unter „Grenzen“ vermerkt]
- Roadmap führt TOOL-107 mit Datum 23.11.2026: [kein Ticket: `/close-ticket` aktualisiert die Roadmap]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `hint.py`, `silence` mit Parametern, README | no |
| 2 | Messen an `norm` und `base`, Bericht, Stichprobe ziehen, Halt | yes |
| 3 | Stichprobe auswerten, Go/No-Go, Übergaben | no |
