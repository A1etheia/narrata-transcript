# TOOL-108 — Spike: Blockverlust ohne Referenz von Halluzination trennen

## Ziel

Ein zweiter Lauf hat oft einen Block von 20 und mehr Wörtern, den der Hauptlauf nicht hat. Heute lässt sich ohne Handreferenz nicht sagen, ob der Hauptlauf ihn verloren oder der zweite Lauf ihn erfunden hat; daran sind R1 bis R3 in TOOL-102 gescheitert, und die naive Vereinigung kostet an D bis zu 22 Punkte. Nach dem Spike steht je Signal fest, wie gut es die beiden Fälle trennt, und es gibt ein Go oder ein begründetes No-Go für eine Regel „Block aus dem zweiten Lauf als Alternative anbieten“. Ergebnis ist `docs/spikes/TOOL-108-blockverlust.md`, bei Go mit Umsetzungsticket.

## Ist-Stand

- **`scripts/spike/seeds.py`** richtet Läufe einer Variante paarweise in 5-Minuten-Abschnitten aus (`aligned`, `:143`) und kennt die Blockschwelle `BLOCK_TOKENS = 20` (`:48`). `view` (`:642`) liefert je Basis die `Alternative`n der anderen Seeds (`:570`), `print_rules_clip` (`:767`) zählt je Alternative „füllt eine Auslassung / sonst richtig / falsch / unverständlich“ (`:816-830`). `Run.seed` ist eine Zahl, die Regeln laufen deshalb nur innerhalb einer Variante.
- **`--with`** (`measure_cross`, `:937`) misst über zwei Varianten nur Orakel und naive Vereinigung, mit Blöcken als Folgen ab 5 Referenzwörtern (`CROSS_BLOCK_TOKENS`, `:55`), also mit Referenz. Eine Regel ohne Referenz über zwei Varianten gibt es nicht.
- **Signale liegen in den gespeicherten Läufen vor.** Normalisiert je Passage `signals` mit `avg_logprob`, `no_speech_prob`, `compression_ratio` und je Wort `confidence` (`src/transcript/asr/whisper.py:334-342`); `temperature` nur in `segment-01.raw.json`, gelesen von `decode_windows` (`scripts/spike/asr.py:1309-1338`). Bei `+batched` ist die Temperatur immer 0, `avg_logprob` und `no_speech_prob` gelten je Stück von bis zu 30 s, nur `compression_ratio` je Passage.
- **„Sprache ohne Wörter“** rechnet `omissions.silence(reference, context)` (`scripts/spike/omissions.py:357-367`) aus der Diarisierung der Sitzung (`diarized`, `:702`; `heard_speech`, `:709`), Brücke 1 s, Stellen ab 1 s, Segmenttabelle ab 2 s (`:54`). `Ranges` (`:94-146`) trägt die Zeitrechnung.
- **Läufe:** `work/<s>/experiments/asr/<variante>.seed<n>/` im Hauptcheckout. Für beide Sitzungen liegen `base`, `base+batched`, `loud`, `loud+batched` mit Seeds 1 bis 3 vor. Die drei Batched-Seeds sind Wort für Wort gleich. `asr.py run --seeds N` baut immer 1..N (`asr.py:1422`) und bereitet dabei alte Wurzeln neu vor (`:408-423`).
- **Referenzen** A bis I: Pilotsitzung A, B, D, E, F, G, I; zweite Sitzung C und H. Im Code stehen nur A und B (`scripts/spike/denoise.py:71-74`), die übrigen kommen über `--clip`. Die Dateinamen tragen nicht überall den Buchstaben des Dokuments; die Zahl der Referenzwörter in der Ausgabe (H 470, I 597) belegt die Zuordnung.
- **Ausgangszahlen:** Orakel `base`-Seeds untereinander C 6,3 / D 12,3 / E 5,2 Punkte, A und B unter 2 (`docs/spikes/TOOL-102-seed-vereinigung.md:79`). Hauptlauf `base+batched` mit Blöcken aus `base`: H 15, I 8, sonst höchstens 2 (`docs/spikes/TOOL-104-recherche-auslassungen.md:333-349`).
- **Tests:** keine für `scripts/spike/`; `scripts/check` prüft dort Lint und Format.

## Entscheidungen

- **Neues Skript `scripts/spike/blocks.py`** statt Ausbau von `seeds.py`. Es importiert Ausrichtung und Bewertung aus `seeds.py`, `omissions.py` und `asr.py`; `seeds.py` hat schon 1043 Zeilen und bleibt in seinen Zahlen unverändert.
- **Ein Angebot** ist ein Block ab 20 Wörtern, den ein Quelllauf an einer Stelle mehr hat als der Hauptlauf (Ausrichtung wie `seeds.aligned`). Zusätzlich eine Zeile ab 10 Wörtern, die nicht in die Go-Regel eingeht.
- **Paarungen:** (a) `base`-Seed als Hauptlauf, andere `base`-Seeds als Quelle, mit 3 und mit 5 Seeds; (b) `base+batched` als Hauptlauf, ein `base`-Seed als Quelle; (c) `base`-Seed als Hauptlauf, `base+batched` als Quelle; (d) dieselben drei mit `loud` und `loud+batched`, nur Seeds 1 bis 3. Die Go-Regel gilt für (a) bis (c); (d) zeigt, ob das Ergebnis nach TOOL-109 hält (Entscheidung der Projektverantwortlichen vom 24.11.2026).
- **Signale**, je Angebot, alle ohne Referenz:
  - Quelllauf: höchste `compression_ratio`, niedrigster `avg_logprob`, höchste `no_speech_prob` der berührten Passagen; Temperatur über 0; mittlere Wort-Confidence; Wiederholungsanteil des Blocks (`denoise._repetition`).
  - Hauptlauf: Lücke zwischen den Wörtern um die Einfügestelle; Dauer des Worts vor der Lücke; dünnes Dekodierfenster.
  - Diarisierung: Anteil der Blockzeit, der im Hauptlauf „Sprache ohne Wörter“ ist, und deren Länge.
  - Übereinstimmung: wie viele andere Läufe an der Stelle einen Block anbieten und welcher Anteil der Blockwörter dort wörtlich wiederkehrt.
  - Bei Batched-Läufen stehen Temperatur und dünnes Fenster als „entfällt“ in der Tabelle.
- **Schwellen vor der Messung:** je Signal die Schwelle, die die Pipeline schon hat (`review_uncertainty` aus der Konfiguration, 2 s aus `LONG_SILENT_MS`), sonst der Median über alle Angebote des Segments, also ohne Referenz bestimmt. Übereinstimmung: mindestens ein weiterer Lauf mit der Hälfte der Wörter.
- **Regeln:** höchstens drei, aus den Signalen von Chunk 2 gebildet, in Chunk 3 im Dokument und als Konstanten festgeschrieben, bevor die neuen Fenster abgetippt sind. Pflichtkandidat aus TOOL-104: „Sprache ohne Wörter über mindestens 2 s im Hauptlauf, der zweite Lauf hat dort Text“.
- **Wirkung einer Regel:** die angenommenen Blöcke an ihrer Stelle in den Hauptlauf eingesetzt, bewertet wie `calibration.measure`. Gewinn je Referenz als Mittel über die Hauptläufe der Paarung.
- **Go-Regel** wie im Ticket: mindestens 3 Punkte an zwei Referenzen, an keiner mehr als 1 Punkt Verlust. Festlegung dazu: I zählt als Referenz mit, F und I gelten wegen der gemeinsamen Minute zusammen als eine. Ohne I könnte Paarung (b) das Go rechnerisch nicht erreichen, weil das Orakel dort nur an H und I über 3 Punkten liegt.
- **Seeds 4 und 5** nur für `base`, beide Sitzungen (vier Läufe, je rund 7 min). `asr.py` bekommt `--first-seed`, damit die Wurzeln 1 bis 3 nicht neu vorbereitet und bei geändertem Snapshot nicht neu transkribiert werden.
- **Zwei neue Handreferenzen**, beide zweite Sitzung, je 3 min: eine an einem Blockverlust (Vorschlag aus TOOL-102: 1:23:00–1:26:00), eine an der Stelle, an der die meisten Läufe denselben Block mehr haben (`blocks.py --suggest`). Sie prüfen die festgeschriebenen Regeln und gehen in keine Schwelle ein. Sitzung und Fenster gehen im Chat an die Projektverantwortliche, nicht ins Repo.
- **Neu-Dekodieren des auffälligen Stücks** ist nicht Teil dieses Spikes und bekommt ein eigenes Ticket, TOOL-113 (Entscheidung vom 24.11.2026).
- **Aufruf** wie in TOOL-104: aus dem Worktree mit `.venv` und `config/config.yaml` des Hauptcheckouts, Läufe als Hintergrundbefehle nacheinander, nie parallel.

## Daten-Check

- Läufe und Diarisierung: *handled* — bleiben unter `work/` im Hauptcheckout, das Skript liest nur.
- Konsole: *handled* — `blocks.py` gibt Zahlen, Anteile, Fehlerquoten und Zeiten aus, keinen Text, kein Token, keine Namen und keine Sprecherlabels; `--suggest` nennt nur Zeitfenster.
- Neue Handreferenzen: *handled* — liegen unter `review/calibration/` im Hauptcheckout; Sitzung und Fenster nur im Chat.
- Spike-Dokument und README: *handled* — nur Kennzahlen, Sitzungen heißen „Pilotsitzung“ und „zweite Sitzung“, Beispiele mit `$S`; vor jedem Commit `grep` auf Sitzungsschlüssel, Gruppenname und Personennamen.
- Fehlermeldungen: *handled* — nennen Variante, Seed und Referenzbuchstaben, keine Inhalte (wie `SpikeError` in `seeds.py:353`).
- Fixtures: *N/A*, weil das Skript keine Tests und keine Fixtures bekommt.

## Contract-Check

*N/A*, weil der Spike weder Contract-JSON noch den Narrata-Endpunkt liest oder schreibt. Wie das Format Alternativen trägt, ist die Frage des Umsetzungstickets.

## Resume-Check

- Abbruch eines Laufs (Seed 4 oder 5): *handled* — der Kindprozess `transcript transcribe` schreibt das Ergebnis erst am Ende; ein neuer Start mit `--first-seed 4` verwendet fertige Läufe wieder (`reusable`, `src/transcript/transcription.py:134-151`).
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.check_provenance` bricht ab, wenn Modell, Revision oder Snapshot zwischen den Läufen einer Messung abweichen; die Wurzeln 1 bis 3 bleiben unberührt.
- Messung selbst: *N/A*, weil `blocks.py` nichts schreibt und in Sekunden neu läuft.

## Dependency-Check

*N/A*, weil kein neues Paket und kein neues Modell dazukommt; die Seeds 4 und 5 laufen mit der vorhandenen `base`-Variante lokal.

## Format-Check

*N/A*, weil kein internes Format geändert wird. Referenzformat 3 und Arbeitsformat 2 bleiben, wie sie sind.

## Chunks

### Chunk 1 — Werkzeug `blocks.py` und `--first-seed`

- Dateien: `scripts/spike/blocks.py` (neu), `scripts/spike/asr.py`, `scripts/spike/README.md`
- Änderung:
  - `asr.py`: Option `--first-seed N` (Standard 1) für `prepare` und `run`.
  - `blocks.py $S [--main base] [--source base] [--seeds 3] [--clip …] [--suggest]`: Läufe beider Varianten laden (`asr.transcribed`, `seeds.timed`), ausrichten (`seeds.aligned`), Angebote ab 20 und ab 10 Wörtern bilden, je Angebot die Signale rechnen (`omissions.silence`, `decode_windows`, Passagen-`signals`, Wort-Confidence).
  - Ausgabe über das Segment: Angebote je Hauptlauf, Zeit, Verteilung je Signal.
  - Ausgabe je Referenz und Signal: angenommene Blöcke, darin Wörter „füllt eine Auslassung / sonst richtig / falsch / unverständlich“, WER mit eingesetzten Blöcken, Gewinn gegen den Hauptlauf und gegen das Mittel.
  - `--suggest`: Fenster à 3 min abseits der Referenzen, an denen die meisten Läufe denselben Block anbieten.
  - README: Abschnitt „Block-Spike (TOOL-108)“ mit Datenschutz und Ablauf.
- Verify: `scripts/check`; im Hauptcheckout gibt `asr.py score $S base --seeds 3` weiter 21,3 % (A) und 29,8 % (B); `seeds.py $S` unverändert; in `blocks.py` stimmt die Zahl der Angebote ab 20 Wörtern je Seed-Paar mit der Spalte „Blöcke ab 20 Wörtern“ aus `seeds.py` überein, und ohne angenommenen Block ist die WER die des Hauptlaufs.
- AC: Das Skript läuft für alle vier Paarungen an beiden Sitzungen und schreibt nichts.

### Chunk 2 — Seeds 4 und 5, Messung je Signal

- Dateien: `docs/spikes/TOOL-108-blockverlust.md` (neu)
- Änderung: `asr.py run $S base --seeds 5 --first-seed 4` für beide Sitzungen. `blocks.py` für die Paarungen (a) bis (d) an A bis I. Dokument mit Methode, Definitionen, vorab festgelegten Schwellen und der Tabelle je Signal (angenommene Blöcke, richtige und falsche Wörter, je Hauptlauf), dazu die Segmentzahlen.
- Verify: `scripts/check`; `grep` im Dokument auf Sitzungsschlüssel, Gruppenname und Personennamen ohne Treffer; Referenzwörter je Fenster wie in TOOL-104 (H 470, I 597).
- AC: Tabelle je Signal an A bis I für jede Paarung; Aussage, ob 5 Seeds die Übereinstimmung tragfähiger machen als 3.

### Chunk 3 — Regeln festschreiben, Fenster vorschlagen

- Dateien: `scripts/spike/blocks.py`, `scripts/spike/README.md`, `docs/spikes/TOOL-108-blockverlust.md`
- Änderung: höchstens drei Regeln als Konstanten und `--rule`; je Regel WER-Wirkung an A bis I je Paarung, angenommene Blöcke und Zeit über das Segment, Laufzeit der nötigen Läufe. Vorläufiger Stand gegen die Go-Regel. Die zwei Fenster der zweiten Sitzung im Chat nennen.
- Verify: `scripts/check`; `grep` wie in Chunk 2; die Regeln stehen mit Schwellen im Dokument, bevor eine neue Referenz vorliegt.
- AC: Regeln und Schwellen sind committet; die Projektverantwortliche hat die beiden Fenster.

### Chunk 4 — Neue Fenster, Entscheidung, Übergaben

- Voraussetzung: beide neuen Handreferenzen liegen unter `review/calibration/`.
- Dateien: `docs/spikes/TOOL-108-blockverlust.md`
- Änderung: die festgeschriebenen Regeln an den neuen Fenstern J und K messen, Schwellen bleiben. Go oder begründetes No-Go, getrennt für die `base`-Familie und für `loud`. Bei Go Umsetzungsticket mit der Frage, wie das Referenzformat mehrere Läufe und Alternativen trägt. Kommentare an TOOL-107, TOOL-82, TOOL-109 und TOOL-100.
- Verify: `scripts/check`; `grep` wie in Chunk 2; jeder Eintrag unter „Übergaben“ trägt einen Key oder `[kein Ticket: …]`.
- AC: die Akzeptanzkriterien des Tickets sind erfüllt; die Leitplanke steht im Dokument: Wörter aus einem anderen Lauf sind Alternativen, das ASR-Ergebnis bleibt unverändert.

## Folge-Tickets

- Spike: nur das auffällige Stück (Sprache ohne Wörter über mehrere Sekunden) mit Fallback neu dekodieren — TOOL-113.
- Umsetzung der Regel samt Formatfrage — [kein Ticket: entsteht nur bei Go, in Chunk 4].
- Großzügigere VAD und `loud+batched` an E — [kein Ticket: nur von Belang, wenn das Ergebnis die Batched-Pipeline weiterträgt; Chunk 4 entscheidet].
- Messwerte zu „Sprache ohne Wörter“ für TOOL-107 — TOOL-107, als Kommentar in Chunk 4.
- Verhältnis zum Parakeet-Zweitlauf — TOOL-82, als Kommentar in Chunk 4.
- Ergebnis an `loud` — TOOL-109, als Kommentar in Chunk 4.
- Zeile für TOOL-108 in `docs/transcript-roadmap.py` (fehlt heute) — [kein Ticket: kommt mit `/close-ticket`].

## Chunk-Tabelle

| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug: `blocks.py`, `--first-seed` in `asr.py`, README | no |
| 2 | Seeds 4 und 5, Messung je Signal an A bis I, Spike-Dokument | no |
| 3 | Regeln festschreiben, Wirkung an A bis I, Fenster für die neue Handreferenz | yes |
| 4 | Neue Fenster messen, Go/No-Go, Übergaben | no |
