# TOOL-103 — Spike: Pegelausgleich vor der Erkennung messen

## Ziel
TOOL-92 hat nur Rauschfilter gemessen, keinen Pegelausgleich. TOOL-101 hat inzwischen gezeigt, dass der Pegel die Auslassungen nicht erklärt, und empfiehlt, TOOL-103 zuletzt zu machen; die Projektverantwortliche hat am 2026-11-22 entschieden, trotzdem voll wie im Ticket zu messen, damit der Hebel belegt abgeschlossen ist.

Nach dem Spike steht je Kandidat (`dynaudnorm` mild und stark, `acompressor`, `loudnorm` zweistufig, `speechnorm`, der beste mit `highpass=f=80`) eine Messtabelle an A, B und C mit drei Seeds, dazu die Auslassungen je Sprecher an A und C und für den besten Kandidaten der Sprecherfehler. Daraus folgt Go oder No-Go nach der Regel aus TOOL-92. Pipeline, Referenzformat und Bewertungsregeln bleiben unverändert.

## Ist-Stand
- **Das Ticket nennt `denoise.py` als Prüfstand, die Methode liegt aber in `asr.py`.** `scripts/spike/denoise.py` kennt nur unbeseedete Wiederholungen (`--runs`, `:635`) und die festen Clips A und B (`:71`). Seeds, frei wählbare Clips (`--clip`, `scripts/spike/asr.py:635`) und damit Referenz C gibt es nur in `asr.py`.
- **`asr.py` kann Filterketten schon.** `Variant.chain` (`scripts/spike/asr.py:98`) trägt eine `denoise.Chain`, `nohw-hp` nutzt sie (`:220`). `_link_audio` (`:377`) filtert einmal je Kette nach `experiments/asr/audio/<kette>/` über `denoise._filter` (`scripts/spike/denoise.py:206`), das auf die Frame-Zahl des Manifests auffüllt und kürzt. Jede Wurzel verlinkt das WAV.
- **Zweistufiges `loudnorm` passt nicht in `Chain`.** Die Kette ist eine feste Filterzeichenkette, und `denoise._call` (`:263`) verwirft die Ausgabe, aus der die Messwerte des ersten Durchgangs kämen.
- **Kennzahlen:** `asr.py score` (`:655`, Tabellen `:789`) liefert WER als Mittel und Spanne, E/A/Ei je Lauf, Wortzahl, Wiederholungsanteil, Passagen je Stufe, markierte Zeit und für diarisierte Wurzeln WDER und Übereinstimmung mit `--baseline`.
- **Auslassungen je Sprecher:** `omissions.py --variant` (`scripts/spike/omissions.py:680`) gibt die Sprechertabelle mit Pegel aus. Für eine gefilterte Variante bricht es heute ab: `vad_speech` (`:283`) rechnet die VAD auf dem Roh-WAV, `measure` (`:643`) vergleicht sie mit `duration_after_vad` des Laufs. Auch der Pegel kommt aus dem Roh-WAV (`:649`).
- **Läufe und Referenzen im Hauptcheckout:** `base.seed1..3` für beide Sitzungen, das Hochpass-WAV der Pilotsitzung, die Handreferenzen A, B, D, E (Pilotsitzung) und C (zweite Sitzung, Fassung Hochdeutsch). Clips laut `docs/spikes/TOOL-102-seed-vereinigung.md:23`: C 1:10:00–1:18:08, D 0:43:00–0:46:00, E 1:23:00–1:26:00.
- **Vergleichswerte `base`** nach der Parserkorrektur aus TOOL-96: 21,3 % an A, 29,8 % an B. Auslassungen je Seed 31/31/36 (A), 44/42/45 (B), 80/156/177 (C) (`docs/spikes/TOOL-101-auslassungen-verorten.md:59`).
- **Pegel laut TOOL-101** (`:79`): Sprecher an A innerhalb von 0,9 dB, an C höchstens 4,6 dB auseinander; die leiseren Sprecher an C haben die wenigsten Auslassungen.
- **Umgebung:** ffmpeg 4.4.2 hat alle fünf Filter und `alimiter`. Der Worktree hat weder `.venv` noch `work/`. Die Spike-Skripte haben keine Unit-Tests, `scripts/check` prüft sie mit ruff.

## Entscheidungen
- **Prüfstand ist `asr.py`, nicht `denoise.py`.** Nur dort gibt es Seeds und Referenz C; `denoise.py` bleibt unverändert und liefert weiter Kette und Filter. Die `base`-Läufe werden wiederverwendet.
- **Kandidaten als Basen mit Hotwords**, also die Pipeline wie sie ist plus Filter. Parameter stehen vor der Messung fest:

  | Name | Kette |
  | --- | --- |
  | `dyn` | `dynaudnorm=f=500:g=31:m=5` (mild: langsame Regelung, höchstens 14 dB) |
  | `dynx` | `dynaudnorm=f=200:g=11:m=30` (stark: schnelle Regelung, bis 30 dB) |
  | `comp` | `acompressor=threshold=0.05:ratio=4:attack=5:release=200:makeup=4,alimiter=limit=0.95:level=false` |
  | `loud` | `loudnorm=I=-16:TP=-1.5:LRA=11`, zweistufig mit den Messwerten des ersten Durchgangs |
  | `spn` | `speechnorm=e=12.5:r=0.0001:l=1` („stark und schnell“ aus der ffmpeg-Doku) |
  | `<bester>-hp` | `highpass=f=80` vor der Kette des besten Kandidaten |

- **`loud` ist auch die Kontrolle.** Zweistufig und linear ist `loudnorm` eine feste Verstärkung ohne Ausgleich zwischen laut und leise. Der Bericht nennt, ob ffmpeg linear oder dynamisch normalisiert hat (`normalization_type`).
- **Zweistufiges `loudnorm` in `asr.py`:** `Variant` bekommt ein Feld für die Zielwerte. `_link_audio` misst im ersten Durchgang mit eigenem ffmpeg-Aufruf (`print_format=json`), setzt die Messwerte in die Kette ein und legt sie in `filter.json` ab. Die Messung wird je Sitzung zwischengespeichert.
- **Zeitachse und Übersteuerung prüfen.** `prepare` schreibt je Kette in `filter.json`: den Versatz der Hüllkurve gegen das Roh-WAV an drei Stellen und den Anteil der Samples am Vollausschlag. Ein Versatz über 10 ms bricht ab, weil Wortzeiten und Diarisierung sonst nicht mehr passen.
- **Bester Kandidat, vorab festgelegt:** kleinstes Mittel der WER über A und B unter den Kandidaten, deren Einfügungen und Wiederholungsanteil im Mittel nicht über `base` liegen. Erfüllt das keiner, der mit dem kleinsten Mittel; `<bester>-hp` wird in jedem Fall gemessen, weil das Ticket es verlangt.
- **Go-Regel wie TOOL-92, konkretisiert:** An A und an B liegt die höchste WER der drei Seeds des Kandidaten unter der niedrigsten von `base`, und Einfügungen und Wiederholungsanteil liegen im Mittel nicht über `base`. C, D und E sind Gegenprobe: Ist der Kandidat an C im Mittel schlechter als `base`, wird aus dem Go ein „Go mit Vorbehalt“ und das Umsetzungsticket nennt ihn.
- **Auslassungen je Sprecher an A und C für alle Kandidaten**, über `omissions.py --variant`. Dafür rechnet `vad_speech` die VAD auf dem WAV der Variante und speichert sie je Kette. Der Pegel je Sprecher kommt ebenfalls aus dem gefilterten WAV: So zeigt die Tabelle, ob der Filter den Abstand der Sprecher überhaupt verkleinert. Die Diarisierung bleibt die der Sitzung.
- **Sprecherfehler für den besten Kandidaten:** Seed 1 läuft je Sitzung zusätzlich mit `--diarize`, die Diarisierung bekommt also das gefilterte WAV. Verglichen wird mit einer diarisierten `base`-Wurzel (WDER an A und C, Wörter ohne Label, Übereinstimmung der Labels). Die Diarisierung ist deterministisch, ein Seed reicht.
- **Läufe aus dem Worktree** wie in TOOL-101 und TOOL-102: Python aus der `.venv` des Hauptcheckouts, `--config` auf dessen `config/config.yaml`. Alle Daten bleiben dort unter `work/`.
- **Laufzeit:** 6 Kandidaten × 3 Seeds × 2 Sitzungen sind 36 Läufe zu rund 7 min, dazu 4 Läufe mit Diarisierung, zusammen gut 4,5 h GPU. Sie laufen als Hintergrundbefehl je Sitzung nacheinander, nie parallel. Die Wartezeit kostet keine Modell-Tokens.

## Daten-Check
- Gefiltertes Audio, Läufe, Kopien von Manifest und Snapshot: *handled* — alles bleibt unter `work/<s>/experiments/asr/` im Hauptcheckout (TOOL-66). Rohaudio verlässt den Rechner nicht, alle Filter sind lokales ffmpeg.
- Konsole: *handled* — nur Zähler, Anteile, WER, Pegel und Zeiten. Kein Text, kein Name, kein Label, kein Session-Schlüssel. Sprecher erscheinen als Rang nach Wortzahl.
- Spike-Dokument und README: *handled* — nur Kennzahlen, Sitzungen heißen „Pilotsitzung“ und „zweite Sitzung“, Befehle nutzen `$S`. Chunk 2 bis 4 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Fehlermeldungen: *handled* — `SpikeError` nennt Variante, Seed und Clipname; von ffmpeg nur die letzte Zeile wie bisher (`denoise._call`).
- Fixtures: *N/A*, weil keine angelegt werden.

## Contract-Check
*N/A*, weil der Spike keine Contract-JSON liest oder schreibt. Bei Go stehen Filter und Version in `asr.settings` des internen Referenzformats; ob der Contract (IOA-1214) sie trägt, klärt das Umsetzungsticket.

## Resume-Check
- Abbruch beim Filtern: *handled* — `denoise._filter` schreibt in eine temporäre Datei und verschiebt erst nach der Längenprüfung; ein fertiges WAV mit derselben Kette wird wiederverwendet (`denoise._reusable`).
- Abbruch beim Transkribieren: *handled* — die Wiederaufnahme der Pipeline gilt je Wurzel, ein neuer `run` überspringt fertige Wurzeln.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings, `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot zwischen den Seeds ab. Weicht ein Kandidat von den gespeicherten `base`-Läufen ab, läuft `base` neu (3 Läufe je Sitzung) und der Bericht nennt es.
- Gleiche Kette: *handled* — `filter.json` hält Kette, Messwerte von `loudnorm` und ffmpeg-Version.

## Dependency-Check
- Neues Paket oder Modell: *N/A*, weil keins dazukommt.
- ffmpeg-Filter: *handled* — `dynaudnorm`, `acompressor`, `alimiter`, `loudnorm`, `speechnorm` sind im installierten ffmpeg 4.4.2 enthalten, laufen lokal auf der CPU und brauchen keine GPU. Ein Umsetzungsticket müsste `speechnorm` (ab ffmpeg 4.4) im Preflight prüfen.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. `filter.json` und der VAD-Zwischenspeicher sind Arbeitsdateien des Spikes ohne Versionsfeld.

## Chunks
### Chunk 1 — Werkzeug: Kandidaten, zweistufiges `loudnorm`, Sprechertabelle für gefilterte Varianten
- Dateien: `scripts/spike/asr.py`, `scripts/spike/omissions.py`, `scripts/spike/README.md` (Abschnitt „Pegel-Spike (TOOL-103)“)
- Änderung:
  - Basen `dyn`, `dynx`, `comp`, `loud`, `spn` und je eine `-hp`-Fassung in `BASES`
  - Messdurchgang für `loudnorm`, Messwerte in Kette und `filter.json`
  - Versatz und Anteil am Vollausschlag in `filter.json`, Abbruch über 10 ms
  - `omissions.py`: VAD und Pegel aus dem WAV der Variante, Zwischenspeicher je Kette; für `base` unverändert
- Verify: `scripts/check`. Im Hauptcheckout:
  - `asr.py prepare $S dyn dynx comp loud spn --seeds 3` an beiden Sitzungen: jedes WAV hat die Frame-Zahl des Manifests, Versatz höchstens 10 ms
  - `asr.py score $S base --seeds 3` ergibt weiter 21,3 % (A) und 29,8 % (B)
  - `omissions.py $S` für `base` ergibt weiter 31/31/36 Auslassungen an A
- AC: Messskripte unter `scripts/spike/`, nur Kennzahlen in der Ausgabe.

### Chunk 2 — Messung der fünf Kandidaten an A, B und C
- Dateien: `docs/spikes/TOOL-103-pegelausgleich.md` (neu)
- Änderung: `asr.py run` für fünf Kandidaten × drei Seeds an beiden Sitzungen (30 Läufe, rund 3,5 h im Hintergrund). `asr.py score` mit `base` an A, B, D, E und an C. Der Bericht bekommt Material und Methode, die Kandidatentabelle mit Filterwerten aus `filter.json` und die Messtabellen. Danach steht der beste Kandidat nach der Regel oben fest.
- Verify: `scripts/check`. Tabellen 1:1 aus dem Skript, je Kandidat drei Seeds an fünf Referenzen. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: Messtabelle je Kandidat mit WER, E/A/Ei, Wortzahl, Wiederholungsanteil und Passagen je Stufe.

### Chunk 3 — Bester mit Hochpass, Sprecherfehler, Auslassungen je Sprecher
- Dateien: `docs/spikes/TOOL-103-pegelausgleich.md`
- Änderung:
  - `<bester>-hp` mit drei Seeds an beiden Sitzungen (6 Läufe)
  - Seed 1 des besten Kandidaten und von `base` mit `--diarize` an beiden Sitzungen, WDER an A und C
  - `omissions.py --variant` für `base` und alle Kandidaten: Sprechertabelle an A und C mit Auslassungen je Wort und Pegel zum lautesten Sprecher
- Verify: `scripts/check`. Die Auslassungen je Seed aus `omissions.py` stimmen mit `asr.py score` überein. `grep` wie in Chunk 2.
- AC: Auslassungen je Sprecher an A und C; WDER für den besten Kandidaten mit gefilterter Diarisierung.

### Chunk 4 — Auswertung, Go/No-Go, Übergaben
- Dateien: `docs/spikes/TOOL-103-pegelausgleich.md`, `docs/plans/TOOL-103-level-normalization.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung mit Go, Go mit Vorbehalt oder begründetem No-Go nach der Regel oben
  - bei Go: Umsetzungsticket im Epic TOOL-100 (gefilterte Fassung als zusätzliche Arbeitsdatei, Filter und Version in `asr.settings`, gespeicherte Transkripte werden `stale`, Bewertung auf gefiltertem Audio neu kalibrieren)
  - Kommentar an TOOL-100 mit dem Ergebnis für M9
- Verify: `scripts/check`. Jede Aussage der Kurzfassung verweist auf eine Tabelle, jeder Eintrag unter „Folge-Tickets“ trägt einen Key oder `[kein Ticket: …]`.
- AC: Go/No-Go nach der Regel aus TOOL-92; bei Go ein Umsetzungsticket; nur Kennzahlen im Dokument.

## Folge-Tickets
- Umsetzung von `loudnorm` vor der Erkennung: TOOL-109, angelegt nach dem „Go mit Vorbehalt“ vom 2026-11-23. Die Go-Regel ist an B verfehlt, die Projektverantwortliche hat trotzdem für die Umsetzung entschieden.
- Bewertung auf gefiltertem Audio neu kalibrieren (offener Punkt aus TOOL-92): TOOL-109, als Akzeptanzkriterium.
- Diarisierung auf Roh-WAV oder gefiltertem WAV: TOOL-109, als Punkt im Vorgehen.
- Kontrolle `gain` mit fester Verstärkung, im Plan nicht vorgesehen: [kein Ticket: in Chunk 3 mitgemessen, weil `loudnorm` dynamisch regelt und als Kontrolle ausfiel]
- TOOL-100: Kommentar mit dem Ergebnis für den Reflexionspunkt M9, in Chunk 4.
- Reihenfolge aus TOOL-101 (TOOL-103 zuletzt): [kein Ticket: am 2026-11-22 von der Projektverantwortlichen entschieden, voll wie im Ticket zu messen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug: Kandidaten in `asr.py`, zweistufiges `loudnorm`, `omissions.py` für gefilterte Varianten | no |
| 2 | Messung der fünf Kandidaten an A, B, C (dazu D, E), Messtabellen | no |
| 3 | Bester mit Hochpass, WDER, Auslassungen je Sprecher | no |
| 4 | Auswertung, Go/No-Go, Übergaben | no |
