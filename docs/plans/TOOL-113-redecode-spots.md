# TOOL-113 — Spike: auffälliges Stück neu dekodieren statt zweitem vollen Lauf

## Ziel
Der Hauptlauf `norm` verliert in einzelnen Seeds noch Blöcke (G 29 Wörter am Stück, J 38). Nach dem Ticket ist gemessen, ob es reicht, nur die auffälligen Stellen des Hauptlaufs neu zu dekodieren, statt einen zweiten vollen Lauf zu rechnen (TOOL-114). Der Spike läuft gestuft: erst eine Obergrenze aus vorhandenen Läufen, das Neu-Dekodieren nur, wenn sie es lohnt. Ergebnis ist ein Spike-Dokument mit Go/No-Go und, bei Go, ein Umsetzungsticket. Die Messung von Regel A mit `norm` als Hauptlauf beantwortet zugleich die offene Frage von TOOL-114.

## Ist-Stand
- **Der Hintergrund des Tickets ist überholt.** Es geht vom Batched-Lauf ohne Temperatur-Fallback aus. Hauptlauf ist seit TOOL-109 und TOOL-112 `norm`: pegelausgeglichenes Audio, nicht gebündelter Decoder mit Fallback und Zeitstempel-Tokens (`docs/spikes/TOOL-112-redebeitrag.md:454`).
- **Der Vergleichsmaßstab des Tickets liegt bei rund null.** Regel A nimmt mit `loud` als Hauptlauf an A bis I keinen Block an, der in eine Referenz reicht; an J höchstens 2,5 Punkte, an K −0,2 bis 0,1 (`docs/spikes/TOOL-108-blockverlust.md:420`, `:467`–`:471`). `norm` und `loud` haben an jeder Referenz und in jedem Seed dieselben Zahlen (`docs/spikes/TOOL-109-hauptlauf.md:9`). Mit `norm` selbst ist Regel A nicht gemessen.
- **Restfehler von `norm`:** längste Folge ausgelassener Wörter 14 / 29 / 18 an G und 38 / 4 / 16 an J, sonst höchstens 15 (`docs/spikes/TOOL-112-redebeitrag.md:174`). Summe der Auslassungen über A bis H, J, K: 584,3 (`:151`).
- **Auffällige Stellen sind wenig Audio:** `norm` hat 32 bis 61 Stellen ab 2 s, an denen die Diarisierung Sprache hört und der Lauf kein Wort hat, zusammen 1,6 bis 3,9 min je Segment (`:78`).
- **Lehre aus TOOL-112:** Stücke unter 2 s halluzinieren; ein Stück je Turn verdoppelt die Einfügungen (`:350`). Ein anders geschnittener Zusatzlauf hat höchstens 19 % der Auslassungen von `norm` richtig, 58 % fehlen in beiden (`:445`).
- **Werkzeug, das es schon gibt:**
  - *Sprache ohne Wörter:* `omissions.silence` (`scripts/spike/omissions.py:366`), Schwelle `LONG_SILENT_MS` 2 s (`:57`), `Ranges` mit Vereinigung, Schnitt und Differenz (`:98`).
  - *Wortzeit je Referenzwort über alle Seeds:* `omissions.heard` und `omissions.timeline` (`:155`, `:189`).
  - *Orakel:* `seeds.clip_run` und `seeds._fate` (`scripts/spike/seeds.py:348`, `:392`).
  - *Blöcke einsetzen und messen, Regeln A bis C:* `blocks.py` (`offers` `:130`, `rule_tests` `:320`, `filled` `:421`, `print_clip` `:465`). `--main` und `--source` nehmen jede Variante; gleiche Variante heißt „die anderen Seeds“ (`:550`).
  - *Passagenwerte und Dekodierfenster je Lauf:* `Loaded.signals`, `asr.decode_windows` (`blocks.py:64`, `scripts/spike/asr.py:1434`).
- **Der Weg zum Neu-Dekodieren existiert in faster-whisper 1.2.1.** `WhisperModel.transcribe` nimmt `clip_timestamps` als Liste von Sekunden (Start, Ende, …), dekodiert jeden Abschnitt fortlaufend mit Fallback und Zeitstempel-Tokens und ignoriert dann die VAD (`faster_whisper/transcribe.py:786`, `:885`, `:1124`). Die Zeiten bleiben auf der Originalachse.
- **`asr.py` reicht Abschnitte bisher nur an die Batched-Pipeline:** `_cli_with_variant` liest `clips.json` und setzt `_Batched` ein (`scripts/spike/asr.py:774`, `:852`); `NEEDS` verlangt `batched` für `clips` (`:319`). Das Backend ruft `self._model.transcribe(...)` mit `FIXED_SETTINGS` (`src/transcript/asr/whisper.py:237`).
- **Vorhandene Läufe im Hauptcheckout:** `norm`, `loud`, `base` (Seeds 1–3), `loud+batched`, `loud+batched+clips+pack`, `loud+batched+clips+join+pad+min` (Seed 1), beide Sitzungen. Referenzen A, B, D, E, F, G, I an der Pilotsitzung, C, H, J, K an der zweiten.
- **Umgebung:** RTX 3080 Ti. Der Worktree hat weder `.venv` noch `work/`; Läufe mit dem Python des Hauptcheckouts, `PYTHONPATH=src` und einer Config mit absolutem `paths.root` im Scratchpad. Die Spike-Skripte haben keine Unit-Tests, die Qualitätsprüfung ist ruff.

## Entscheidungen
- **Hauptlauf ist `norm`, kein Batched-Lauf** (Projektverantwortliche, 2026-11-27). Das Ticket bekommt dazu einen Kommentar; seine Beschreibung bleibt als Stand vom 24.11. stehen.
- **Gestuft** (Projektverantwortliche, 2026-11-27): Stufe 1 misst ohne neuen Dekodier-Code, Stufe 2 dekodiert nur nach dem Stufentor.
- **Go-Regel wie TOOL-108** (Projektverantwortliche, 2026-11-27), vor der Messung festgelegt. Go, wenn alle drei Punkte gelten:
  1. An mindestens zwei Referenzen sinkt die WER um 3 Punkte gegenüber dem Mittel der drei Hauptläufe. F und I zählen zusammen als eine Referenz.
  2. An keiner Referenz A bis K verliert ein Hauptlauf mehr als 1 Punkt.
  3. Das Mittel über die Referenzen liegt nicht unter dem von Regel A am selben Hauptlauf mit der besten gemessenen Quelle.
- **Auffällige Stelle, vor der Messung festgelegt.** Schwellen sind die festen Zahlen aus TOOL-108, nicht die seit TOOL-109 geänderte Config.
  - *S1:* die Diarisierung hört mindestens 2 s Sprache, und der Hauptlauf hat dort kein Wort (`omissions.silence`, `LONG_SILENT_MS`).
  - *S2:* S1, dazu jede Passage des Hauptlaufs mit `compression_ratio` ab 2,4 oder `avg_logprob` bis −1.
- **Stück:** die Stelle mit 2 s Polster je Seite, überlappende Stücke verbunden, an Segmentanfang und -ende gekappt. Jedes Stück ist damit mindestens 6 s lang und bringt Wörter des Hauptlaufs als Anker mit. Länger als 30 s ist erlaubt, der fortlaufende Decoder rückt im Abschnitt selbst weiter.
- **Stufe 1 misst zwei Obergrenzen** je Referenz und Hauptlauf, an S1 und S2:
  - *harte Obergrenze:* jedes ausgelassene Referenzwort mit Wortzeit in einem Stück käme richtig zurück, kein falsches Wort dazu;
  - *Orakel aus vorhandenen Läufen:* wie viele dieser Auslassungen ein anderer vorhandener Lauf richtig hat (die anderen `norm`-Seeds, `loud+batched`, `loud+batched+clips+pack`, `loud+batched+clips+join+pad+min`).
- **Stufentor, vor der Messung festgelegt:**
  - Harte Obergrenze (S2, Mittel der Hauptläufe) erreicht nicht an zwei Referenzen 3 Punkte: Punkt 1 der Go-Regel ist unerreichbar, No-Go ohne Stufe 2.
  - Orakel erreicht an zwei Referenzen 3 Punkte: Stufe 2 läuft.
  - Dazwischen entscheidet die Projektverantwortliche mit den Zahlen.
- **Stufe 2 dekodiert je Hauptlauf dessen eigene Stücke** als Variante `norm+spots`, Seed n für die Stücke von `norm#n`, mit dem fortlaufenden Decoder der Pipeline (Fallback, Zeitstempel-Tokens, dieselben Hotwords). Gemessen wird S2; S1 ist die Teilmenge der Stücke.
- **Gewertet wird wie in TOOL-108:** Was der neu dekodierte Lauf an einer Stelle ab 20 Wörtern mehr hat, ist ein Angebot. Zeilen: jedes Angebot, Regel A auf den Dekodierwerten des neu dekodierten Stücks. Angebote ab 5 Wörtern stehen daneben und zählen nicht für die Go-Regel.
- **Ein neues Skript `scripts/spike/spots.py`** trägt die Regeln der Stellen und die Stufe 1, damit `asr.py` und `blocks.py` sie ohne Kreisimport nutzen (wie `clips.py` in TOOL-112).
- **Der Pipeline-Code unter `src/` bleibt unverändert.** Kein Aufruf schreibt ein Transkript der Sitzung; neu dekodierter Text wäre eine Alternative an der Stelle.

## Daten-Check
- Läufe, `spots.json`, Kopien von Manifest und Snapshot: *handled* — alles bleibt unter `work/<s>/experiments/asr/` im Hauptcheckout (TOOL-66). Rohaudio verlässt den Rechner nicht.
- `spots.json`: *handled* — nur Zeiten in ms, die Parameter, der Hauptlauf (Variante und Seed) und ein Hash, kein Text und keine Labels.
- Konsole und Logs: *handled* — nur Zähler, Anteile, WER, Zeiten. `SpikeError` nennt Variante, Seed und Clipname.
- Spike-Dokument und README: *handled* — nur Kennzahlen, „Pilotsitzung“ und „zweite Sitzung“, Befehle mit `$S`. Chunk 2 und 5 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Scratch-Config mit absolutem Pfad: *handled* — liegt im Scratchpad der Sitzung, nie im Repo.
- Handreferenzen und Fixtures: *N/A*, weil keine neue entsteht.

## Contract-Check
*N/A*, weil das Ticket keine Contract-JSON liest oder schreibt. Bei Go klärt das Umsetzungsticket zusammen mit TOOL-114, wie eine Alternative an einer Stelle in den Contract kommt (IOA-1214).

## Resume-Check
- Stufe 1: *N/A*, weil sie nur liest und in Sekunden läuft.
- Abbruch beim Neu-Dekodieren: *handled* — die Wiederaufnahme der Pipeline gilt je Wurzel, ein neuer `run` überspringt fertige Wurzeln.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings, `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot ab.
- Gleiche Stücke: *handled* — `asr.settings` trägt Parameter und Hash der Stücke. Ändert sich der Hauptlauf, die Diarisierung oder eine Regel, passt der Hash nicht und die Wurzel läuft neu.
- Gefiltertes Audio: *handled* — `norm+spots` verlinkt die gefilterte Kopie von `norm#1` wie die Seeds 2 und 3 in TOOL-109 (`_share_level`).

## Dependency-Check
*N/A*, weil kein neues Paket und kein neues Modell dazukommt. `clip_timestamps` des fortlaufenden Decoders ist Teil des installierten faster-whisper 1.2.1.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. `spots.json` und die neuen Schlüssel in `asr.settings` entstehen nur in Spike-Wurzeln.

## Chunks
### Chunk 1 — Stufe 1: `spots.py` mit Stellen und Obergrenzen
- Dateien: `scripts/spike/spots.py` (neu), `scripts/spike/README.md` (Abschnitt „Stellen-Spike (TOOL-113)“)
- Änderung:
  - reine Funktionen: Stellen S1 und S2 je Lauf, Stücke mit Polster und Verbinden, Prüfung (sortiert, überschneidungsfrei, im Segment)
  - Aufruf `spots.py $S [--variant norm] [--seeds 3] [--with VARIANTE]… [--clip …]`
  - *Segment:* je Hauptlauf Zahl der Stellen und Stücke, Median und Summe der Stücke in Minuten, für S1 und S2
  - *je Referenz und Hauptlauf:* Auslassungen, davon in einem Stück (harte Obergrenze in Punkten), davon in einem anderen Lauf richtig (Orakel in Punkten), längste Folge ausgelassener Wörter und ihr Anteil in einem Stück; dazu das Mittel der Hauptläufe
  - README: Definitionen, Ablauf, Datenschutz
- Verify: ruff wie in `scripts/check`. Im Hauptcheckout:
  - `asr.py score $S base --seeds 3` ergibt weiter 21,3 % (A) und 29,8 % (B)
  - Zahl der Stellen S1 je `norm`-Seed stimmt mit „Stellen ab 2 s“ aus TOOL-112 überein (32 / 33 / 38 und 52 / 44 / 61)
  - Auslassungen je Lauf und Referenz stimmen mit `asr.py score` überein
- AC: auffällige Stücke mit den Signalen aus TOOL-108 bestimmt.

### Chunk 2 — Stufe 1 messen, Stufentor
- Dateien: `docs/spikes/TOOL-113-stellen.md` (neu)
- Änderung:
  - `spots.py` für `norm` an A bis K, beide Sitzungen
  - `blocks.py --main norm --rules`, ohne Quelle (andere Seeds), mit `--source loud+batched` und mit `--source loud+batched+clips+pack`: Regel A mit dem heutigen Hauptlauf
  - Bericht: Material und Methode mit Go-Regel und Stufentor im Wortlaut, Tabellen zu Stellen, Obergrenzen und Regel A, Stand gegen das Stufentor
  - Halt: Ergebnis der Projektverantwortlichen vorlegen. Bei No-Go weiter mit Chunk 5, Chunk 3 und 4 entfallen.
- Verify: Tabellen 1:1 aus dem Skript. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: Tabellenzeilen „Hauptlauf“ und „Hauptlauf mit Blöcken aus dem zweiten Lauf (Regel A)“ je Referenz; nur Kennzahlen, alles lokal.

### Chunk 3 — Stufe 2: `+spots` in `asr.py`, Paarung in `blocks.py`
- Dateien: `scripts/spike/asr.py`, `scripts/spike/blocks.py`, `scripts/spike/README.md`
- Änderung:
  - `asr.py`: Modifikator `spots`, nur ohne `batched`; `prepare` schreibt `spots.json` aus den Stücken S2 des Hauptlaufs mit demselben Seed und gibt Zahl und Summe aus; ein Stellvertreter um das Modell reicht die Stücke als `clip_timestamps` an den fortlaufenden Decoder; Parameter und Hash in `asr.settings` und in der Prüfung von `transcribed`
  - `blocks.py`: Ist die Quelle eine `+spots`-Variante, bietet nur der Lauf mit dem Seed des Hauptlaufs an; die Zeilen „in einem weiteren Lauf“ entfallen dort
- Verify: ruff. Im Hauptcheckout:
  - `prepare` und `run` für `norm+spots`, Seed 1, Pilotsitzung: Der Lauf endet, `asr.settings` trägt Parameter und Hash, `keywords_used` ist nicht leer, jede Wortzeit liegt in ihrem Stück (Toleranz 1 s), `duration_after_vad` ist die Summe der Stücke
  - Laufzeit und VRAM aus `run.json` notiert
  - `blocks.py --main base --rules` gibt dieselben Zahlen wie in TOOL-108 (C 122/21 · 4,3)
- AC: nur die auffälligen Stücke neu dekodiert, mit Temperatur-Fallback und Zeitstempel-Tokens.

### Chunk 4 — Stufe 2 messen
- Dateien: `docs/spikes/TOOL-113-stellen.md`
- Änderung:
  - `asr.py prepare` und `run` für `norm+spots`, Seeds 1–3, beide Sitzungen, nacheinander im Hintergrund
  - `blocks.py --main norm --source norm+spots`, mit `--least 20` und `--least 5`, an A bis K
  - Bericht: Tabelle je Referenz mit Hauptlauf, Hauptlauf mit neu dekodierten Stücken, Hauptlauf mit Blöcken aus dem zweiten Lauf (Regel A); WER, Auslassungen, Einfügungen; zusätzliche Laufzeit gegen einen zweiten vollen Lauf und gegen einen Batched-Lauf
- Verify: Tabellen 1:1 aus dem Skript, `grep` wie in Chunk 2.
- AC: Tabelle je Referenz mit den drei Zeilen des Tickets; WER, Auslassungen, Einfügungen, zusätzliche Laufzeit.

### Chunk 5 — Auswertung, Go/No-Go, Übergaben
- Dateien: `docs/spikes/TOOL-113-stellen.md`, `docs/plans/TOOL-113-redecode-spots.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung und Regeltabelle: jeder Punkt der Go-Regel mit Zahl, oder das Stufentor mit Zahl
  - Entscheidung der Projektverantwortlichen einholen und mit Datum eintragen; bei Go das Umsetzungsticket im Epic TOOL-100 anlegen
  - Kommentare an TOOL-114 (Regel A mit `norm`) und TOOL-100
- Verify: Jede Aussage der Kurzfassung verweist auf eine Tabelle. Jeder Eintrag unter „Folge-Tickets“ trägt einen Key oder `[kein Ticket: …]`. `grep` wie in Chunk 2.
- AC: Go nur nach der vorab festgelegten Regel, sonst begründetes No-Go; bei Go ein Umsetzungsticket.

## Folge-Tickets
- Umsetzung des Neu-Dekodierens in der Pipeline: [kein Ticket: entsteht nur bei Go, Chunk 5 legt es an und trägt den Key nach]
- TOOL-114 (Blöcke aus einem zweiten Lauf): Kommentar mit Regel A bei `norm` als Hauptlauf aus Chunk 2 und dem Ergebnis des Spikes.
- TOOL-100: Kommentar mit dem Ergebnis.
- Beschreibung von TOOL-113 nennt noch den Batched-Lauf: [kein Ticket: Kommentar vom 2026-11-27 zum neuen Zuschnitt am Ticket selbst]
- Roadmap führt TOOL-113 mit Datum 23.11.2026: [kein Ticket: `/close-ticket` aktualisiert die Roadmap]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Stufe 1: `spots.py`, Stellen und Obergrenzen, README | no |
| 2 | Stufe 1 messen, Regel A mit `norm`, Stufentor | yes |
| 3 | Stufe 2: `+spots` in `asr.py`, Paarung in `blocks.py` | no |
| 4 | Stufe 2 messen | no |
| 5 | Auswertung, Go/No-Go, Übergaben | no |
