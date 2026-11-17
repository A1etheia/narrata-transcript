# TOOL-93 — Spike: Erkennungsqualität an den Pilot-Handreferenzen verbessern

## Ziel
Gemessen wird, welche lokalen Einstellungen und Modelle die WER an den beiden Pilot-Handreferenzen A und B senken, vor allem die Auslassungen. Heute läuft die Pipeline fest mit large-v3-turbo, VAD, `beam_size 5` und Hotwords. Eine andere Einstellung lässt sich nur durch einen Eingriff in den Code ausprobieren, und Läufe sind ohne Seed nicht reproduzierbar (TOOL-92). Ergebnis ist ein Spike-Dokument mit Messtabelle je Variante, einer Gegenprobe an einer dritten Referenz aus der zweiten Sitzung und einer Empfehlung für V0.2 als Eingang für TOOL-60.

## Ist-Stand
- Pilotsitzung unter `work/<s>/`: Segment 1 (5:00:00), Referenzen `review/calibration/reference-1.txt` (A, 0:00:00–0:04:06, 551 Wörter, 3 Sprecher) und `reference-2.txt` (B, 1:20:00–1:23:00, 489 Wörter). Die zweite Sitzung unter `work/` ist extrahiert (Manifest, Audio, Snapshot), aber noch nicht transkribiert.
- Der Pilotlauf hat **48 Hotwords** genommen (`asr.keywords_used`). Laut TOOL-81 fehlen mit Hotwords auf langen Aufnahmen rund 16 % der Wörter. Hotwords bekommt nur ein Modell mit `turbo` im Namen (`src/transcript/asr/whisper.py:250` `takes_hotwords`).
- Feste Whisper-Einstellungen: `src/transcript/asr/whisper.py:48` `FIXED_SETTINGS` (VAD an, Wortzeiten, `condition_on_previous_text: false`). Konfigurierbar sind nur `model`, `device`, `compute_type`, `beam_size` und `retries` (`src/transcript/config.py:43`). Die VAD-Defaults von faster-whisper 1.2.1 sind `threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`. `temperature`, `no_speech_threshold`, `log_prob_threshold` und `compression_ratio_threshold` stehen auf den Defaults der Bibliothek.
- Settings fließen in die Identität des Ergebnisses (`src/transcript/asr/backend.py:131` `matches`). Eine Wurzel mit anderen Settings rechnet also neu, und eine Wurzel mit denselben Settings nimmt das gespeicherte Ergebnis wieder auf (`src/transcript/transcription.py:276` `reusable`).
- `scripts/spike/denoise.py` aus TOOL-92 hat schon fast alles, was hier gebraucht wird:
  - Schattenwurzel pro Kandidat und Lauf (`prepare`, `:123`)
  - CLI-Aufruf mit zusätzlichen Whisper-Settings (`_cli_with_asr`, `:301`)
  - WER über `calibration.measure` je Clip, Wiederholung, Stufen, Mittel und Spanne (`score`, `print_summary`, `:336`/`:506`)
- `transcript transcribe --no-diarize` (`src/transcript/__main__.py:161`) überspringt die Diarisierung. Sie ist deterministisch (TOOL-92) und für die WER unerheblich.
- CTranslate2 4.8.5 hat `set_random_seed`. faster-whisper hat keinen eigenen Seed-Parameter.
- Hardware: RTX 3080 Ti mit 12 GB, WSL jetzt mit 25 GB RAM. Im HF-Cache liegen large-v3-turbo, large-v3, Parakeet und Granite. In der venv fehlt `transformers`.

### Stand nach Chunk 4 (2026-11-17)
- **Stufen 1–3 ohne Gewinner** (Bericht, Commits bis `de1c426`). `base` bleibt bei A 24,0 % und B 36,1 % (32,9–41,1). Keine Einstellung und kein Modell bringt an A und B 3 Punkte. Stufe 4 hat damit keinen Finalisten, die Go-Regel ergibt No-Go.
- Die zweite Sitzung ist mit `base`, Seed 1 und Diarisierung transkribiert. `windows` hat drei Fenster für Referenz C vorgeschlagen, sie stehen im Bericht.
- **Vergleich mit Plaud** (Kommentar am Ticket, 2026-11-17): Die Projektverantwortliche hat die Pilotaufnahme außerhalb der Pipeline in Plaud transkribiert und mit eigenem Skript gegen A und B gemessen, mit entfernten Füllwörtern. Plaud liegt dabei an A und B 8–13 Punkte über der Pipeline. Plauds zusätzliche Auslassungen sind vor allem Füll- und Mundartwörter, dazu falsch oder gar nicht erkannte Figurennamen. Auch ein kommerzielles System erkennt dasselbe Audio also nicht wörtlicher. Das ist ein Hinweis, dass die Aufnahme (ein Mikrofon in der Tischmitte, Mundart, Übersprechen) die Grenze setzt, und stützt die Empfehlung zur Aufnahme am Tisch, ohne sie zu beweisen.
- Neue Verknüpfungen am Ticket: TOOL-96 (Passagen am Sprecherwechsel teilen) verfolgt den Vorsprung von Plaud bei der Sprecherzuordnung. IOA-1302 (IT/OT-Klassifikation und LLM-Korrektur an der Pilotsitzung) wartet auf das Ergebnis dieses Spikes.

## Entscheidungen
- **Eigenes Skript `scripts/spike/asr.py`, das `denoise.py` importiert.** Schattenwurzeln, Hochpass-Kette, Score-Tabellen und der CLI-Wrapper kommen aus `denoise.py` (gleicher Ordner, also importierbar). `denoise.py` bleibt so, wie TOOL-92 es beschreibt. Wurzeln liegen unter `work/<s>/experiments/asr/<variante>.seed<n>/`.
- **Eine Variante besteht aus Modell, Hotwords an oder aus, Whisper-Overrides und optional `hp`-Kette.** Overrides gehen wie bei `base-t0` in `FIXED_SETTINGS` und landen damit in `asr.settings`. Hotwords aus heißt `takes_hotwords` liefert im Wrapper `False`, das Transkript zeigt dann `keywords_used: []`. Das Modell kommt über `asr.model` in der Config der Wurzel.
- **Fester Seed statt bloßer Wiederholung.** Der Wrapper setzt `ctranslate2.set_random_seed(n)` und schreibt `seed` in die Settings. Ein Lauf ist damit reproduzierbar und die Wiederaufnahme sauber. Die Streuung bleibt trotzdem: Jede Variante läuft mit den Seeds 1–3, verglichen werden Mittel und Spanne. Chunk 1 prüft, dass derselbe Seed zweimal dieselbe Zählung gibt. Schlägt das fehl (GPU nicht deterministisch), bleibt es bei 3 Läufen wie in TOOL-92, und der Bericht nennt das.
- **Ganzes Segment 1, Diarisierung nur für Finalisten.** Der Hotword-Effekt zeigt sich erst auf langen Aufnahmen (TOOL-81), Ausschnitte würden ihn verstecken. Gerechnet wird mit `--no-diarize`. WDER und Label-Abgleich kommen erst in Stufe 4 dazu.
- **Gestuft, jeweils ein Faktor auf dem bisher besten Stand:**
  1. **Hotwords** (Turbo):
     - `base`: wie die Pipeline, mit allen Hotwords (Pilot: 48)
     - `pchw`: nur die `pc`-Einträge als Hotwords. Die Schattenwurzel setzt dafür in ihrer Config jedes Budget in `knowledge.keyword_budget` auf 0 und baut den Snapshot mit `transcript snapshot --refresh` neu (`src/transcript/knowledge.py:99`). Die Variante zeigt, ob eine kurze Liste ohne Schaden hilft oder ob Hotwords ganz wegfallen sollten. Die Ursache bleibt bei TOOL-81.
     - `nohw`: keine Hotwords
     - `nohw-hp`: keine Hotwords, mit Hochpass

     Der Gewinner wird die Basis für Stufe 2.
  2. **VAD und Dekodierung** (Turbo):
     - `novad`
     - `vad-t35` (`threshold 0.35`), `vad-pad800` (`speech_pad_ms 800`), `vad-sil500` (`min_silence_duration_ms 500`)
     - `beam10`
     - `nospeech-off` (`no_speech_threshold: None`, Whisper verwirft dann keine Fenster als stumm)
     - `logprob-lax` (`log_prob_threshold -1.5`, seltenerer Fallback)
     - `cond-prev` (`condition_on_previous_text: true`)
     - `temperature=0` scheidet nach TOOL-92 aus (Schleifen, höhere WER).
  3. **Modelle**, ohne Hotwords und mit den Einstellungen des Gewinners aus Stufe 2:
     - `large-v3`
     - eine auf Deutsch nachtrainierte Whisper-Variante (Kandidat: `primeline/whisper-large-v3-turbo-german`)
     - ein wortgetreues Modell (Kandidat: CrisperWhisper, schreibt Füllwörter und Wiederholungen)

     Welche dieser Kandidaten es tatsächlich als CTranslate2-Modell gibt oder ob sie konvertiert werden müssen, klärt Chunk 3, ebenso die Lizenz. Parakeet bleibt draußen (TOOL-82, TOOL-62: kein Vorsprung, nur in Blöcken).
  4. **Kombination und Finalisten:** Das beste Modell mit allen Einstellungen aus Stufe 2, die einzeln mindestens 3 Punkte gebracht haben. Das läuft gegen `base` und gegen den besten Einzelstand, mit Diarisierung.
- **Go-Regel:** Ein Gewinner muss an A **und** B im Mittel mindestens 3 Punkte unter `base` liegen, ohne dass sich die Spannen überlappen. Wiederholungsanteil und Wortzahl dürfen dabei nicht über die Spanne von `base` hinaus kippen, und WDER sowie die übersehenen Fehler dürfen nicht steigen. Hilft eine Variante nur an einem Clip, ist sie ein Hinweis, kein Gewinner.
- **Gegenprobe C:** Die zweite Sitzung wird mit `base` und dem Gewinner (je 3 Seeds) transkribiert. Aus Zählwerten (Wörter pro Minute, Labels) schlägt das Skript zwei oder drei ruhige 3-min-Fenster vor, ohne Text. Die Projektverantwortliche wählt eins und tippt es als `review/calibration/reference-1.txt` dieser Sitzung ab. An C wird nicht mehr optimiert.
  - *Nach Chunk 4:* Es gibt keinen Gewinner. Laut Ticket wird C erst abgetippt, wenn ein Gewinner feststeht, sie ist also nicht mehr Pflicht. Liegt C trotzdem vor, misst Chunk 5 `base` daran (3 Seeds), um zu prüfen, ob die Werte der Pilotsitzung auf eine zweite Sitzung übertragbar sind. Sonst bleiben die Fenster im Bericht für ein späteres Ticket, etwa nach einer geänderten Aufnahme.
- **Auslassungen aufschlüsseln (nach dem Plaud-Vergleich):** Chunk 5 zählt die Auslassungen von `base` an A und B getrennt nach Füllwörtern und übrigen Wörtern und gibt die WER zusätzlich ohne Füllwörter aus. Die Füllwortliste steht fest in `asr.py` (z. B. „ja“, „also“, „halt“, „dann“, „äh“, „ähm“, Mundartformen wie „des“) und wird im Bericht genannt. Die Ausgabe enthält nur Zähler. So wird sichtbar, wie viel der Auslassungen auf Füll- und Mundartwörter fällt, und die Pipeline-Werte lassen sich neben die Plaud-Werte stellen. Die Plaud-Werte selbst werden nur zitiert und nicht nachgerechnet: Plaud ist ein Cloud-Dienst, die Pipeline schickt kein Audio dorthin.
- **Kennzahlen** wie in TOOL-92, dazu:
  - Peak-RAM über `resource.getrusage(RUSAGE_CHILDREN)` nach jedem Lauf
  - Peak-VRAM über `nvidia-smi`-Abfrage im Sekundentakt während des Laufs
  - Laufzeit pro Stunde Audio

## Daten-Check
- Audio, Schattenwurzeln, Transkripte und die Referenz C: *handled*. Alles liegt unter `work/`, das gitignored ist. Referenz C liegt unter `work/<s2>/review/calibration/`.
- Konsole und Skriptausgabe: *handled*. Nur Zähler, Anteile, Zeiten und Fenstergrenzen, nie Text, Namen, Sprecher-Labels oder der Session-Key.
- Spike-Dokument: *handled*. Nur Kennzahlen. Sitzungen heißen dort „Pilotsitzung“ und „zweite Sitzung“, ohne Schlüssel oder Gruppenname. Chunk 5 prüft das mit `grep` gegen Session-Keys, Gruppennamen und Personennamen aus beiden Snapshots.
- Fixtures: *N/A*, weil keine angelegt werden.
- Rohaudio lokal: *handled*. Heruntergeladen werden nur Modelle, und zwar einmal, in den HF-Cache bzw. nach `~/.cache/narrata-spike/asr/`.

## Contract-Check
*N/A*: Der Spike liest und schreibt keine Contract-JSON und spricht den Narrata-Endpoint nicht an. Snapshots werden nur in die Schattenwurzeln kopiert.

## Resume-Check
- Abbruch in einem Lauf: *handled*. Jede Wurzel nutzt die Wiederaufnahme der Pipeline (TOOL-17). Ein fertiges Transkript mit gleichem Modell, gleicher Revision, gleichen Settings samt `seed` und gleichem Snapshot wird wiederverwendet. `run` überspringt damit fertige Wurzeln und lässt sich über Nacht einfach neu starten.
- Gleiches Modell und gleicher Snapshot: *handled*. `score` bricht ab, wenn innerhalb einer Variante Revision oder Snapshot abweichen, und gibt die Revision je Modell aus. Alle Wurzeln einer Sitzung nutzen denselben kopierten Snapshot. Die einzige Ausnahme ist `pchw` mit seinem neu gebauten Snapshot: Er hat dasselbe Glossar und nur ein anderes Budget, und der Bericht nennt beide Kennungen.
- Reproduzierbarkeit: *handled* über den Seed (siehe Entscheidungen). Die Seed-Prüfung in Chunk 1 hält fest, ob das auf der GPU trägt.

## Dependency-Check
- large-v3: *handled*. Liegt schon im Cache, MIT-Lizenz, lokal, VRAM in TOOL-62 unter 12 GB.
- Deutsche Whisper-Variante und wortgetreues Modell: *handled* in Chunk 3. Die Lizenz wird beim Download geprüft und im Bericht genannt. Eine nicht-kommerzielle Lizenz (z. B. CC-BY-NC) wird für die private Gruppe bewertet, nicht pauschal ausgeschlossen. Braucht ein Modell eine Konvertierung nach CTranslate2, läuft `ct2-transformers-converter` in einer Wegwerf-venv unter `~/.cache/narrata-spike/asr/convert-venv`, nicht in der Projekt-venv. Modelle über 12 GB VRAM laufen nur mit `compute_type int8_float16` oder auf der CPU, mit gemessener Laufzeit.
- `pyproject.toml`: *N/A*, weil keine Paket-Abhängigkeit dazukommt. Peak-RAM und Peak-VRAM kommen aus der stdlib und `nvidia-smi`.

## Format-Check
*N/A*: Kein internes Format und keine Versionsnummer ändern sich. `seed` und die Overrides stehen nur in `asr.settings` der Schattenwurzeln. Das Feld ist ein offenes Mapping, das es schon gibt. Dass ein späterer Modell- oder Settingswechsel gespeicherte Transkripte `stale` macht, gehört ins Umsetzungsticket (Folge-Tickets).

## Chunks
### Chunk 1 — Spike-Werkzeug
- Dateien: `scripts/spike/asr.py`, `scripts/spike/README.md`
- Änderung:
  - Variantentabelle (Modell, Hotwords, Overrides, Kette)
  - `prepare <s> <variante>… --seeds N`: Wurzeln über `denoise.prepare`-Bausteine, Config mit `asr.model`; bei `pchw` Budget 0 je Typ und Snapshot-Neubau in der Wurzel
  - `run`: Wrapper mit Seed, Hotword-Schalter und Overrides, `--no-diarize` außer mit `--diarize`, Peak-RAM und Peak-VRAM nach `<wurzel>/run.json`
  - `score`: Tabellen aus `denoise` plus Modell und Revision, RAM, VRAM und Laufzeit pro Stunde, Clips konfigurierbar für Referenz C
  - `windows <s>`: Vorschläge für ruhige 3-min-Fenster aus Wortdichte und Labelzahl, nur Zeiten und Zähler
  - README-Abschnitt „ASR-Spike (TOOL-93)“
- Verify: `scripts/check`. `base` mit Seed 1 zweimal in getrennten Wurzeln rechnen, `score` zeigt identische Zählung. `nohw.seed1` hat `keywords_used: []`, `pchw.seed1` nur so viele Begriffe, wie die `pc`-Einträge Namen und Aliase haben.
- AC: Messskripte unter `scripts/spike/`, keine Ausgabe mit Text oder Namen.

### Chunk 2 — Stufen 1 und 2 (Hotwords, VAD, Dekodierung)
- Dateien: `docs/spikes/TOOL-93-erkennungsqualitaet.md`
- Änderung: Stufe 1 rechnen und auswerten, Basis für Stufe 2 festlegen, dann Stufe 2 rechnen, immer nacheinander und im Hintergrund. Der Bericht bekommt Material und Methode, die Tabellen beider Stufen und eine Zwischenbewertung je Variante. Den Hotword-Befund als Kommentar an TOOL-81.
- Verify: `scripts/check`. Die Tabellen kommen 1:1 aus `score`. Der `base`-Mittelwert liegt in der Größenordnung von TOOL-92 (A ≈ 24 %, B 34–47 %), sonst wird die Abweichung im Bericht erklärt.
- AC: Messtabelle je Variante auf A und B.

### Chunk 3 — Stufe 3 (Modelle)
- Dateien: `scripts/spike/asr.py` (Modellvarianten), `scripts/spike/README.md` (Einrichtung), `docs/spikes/TOOL-93-erkennungsqualitaet.md`
- Änderung: Modellkandidaten recherchieren, laden und, falls nötig, konvertieren. Lizenz und Hardwarebedarf festhalten, rechnen, den Abschnitt „Modelle“ schreiben. Fällt ein Kandidat aus (kein Download, nur über 12 GB VRAM, Absturz), steht der Grund in der Tabelle.
- Verify: `scripts/check`. Jede Modellvariante hat ihre Revision in der `score`-Ausgabe.
- AC: Lizenz und Hardwarebedarf je Modell im Bericht.

### Chunk 4 — Stufe 4 (Kombination und Finalisten)
- Dateien: `docs/spikes/TOOL-93-erkennungsqualitaet.md`
- Änderung: Kombination rechnen, Finalisten mit Diarisierung, Go-Regel anwenden, Gewinner festlegen. Danach die zweite Sitzung mit `base` und Gewinner transkribieren, `windows` ausführen und der Projektverantwortlichen Fenster und Zeitpunkt für Referenz C nennen.
- Verify: `scripts/check`. Die Finalistentabelle enthält WDER und übersehene Fehler.
- AC: Gewinner (oder kein Gewinner) mit Begründung im Bericht.
- *Erledigt* (`de1c426`): kein Finalist, No-Go, Fenster für C im Bericht. Die Finalistentabelle mit WDER entfällt mangels Finalist.

### Chunk 5 — Auslassungen, Entscheidung, Übergaben
- Dateien: `scripts/spike/asr.py` (Füllwort-Aufschlüsselung), `scripts/spike/README.md`, `docs/spikes/TOOL-93-erkennungsqualitaet.md`, `docs/plans/TOOL-93-asr-quality.md` (Folge-Tickets)
- Änderung:
  - `score`: Auslassungen je Clip getrennt nach Füllwörtern und übrigen Wörtern, dazu die WER ohne Füllwörter; für `base` an A und B (3 Seeds)
  - Falls Referenz C vorliegt: `score` an C für `base`; sonst steht im Bericht, dass C mangels Gewinner entfällt
  - Abschnitte Auslassungen (mit den Plaud-Werten aus dem Ticketkommentar als Vergleich, ausdrücklich mit anderer Methode und Einzellauf), Entscheidung, Empfehlung zur Aufnahme am Tisch (aus Auslassungen bei Übersprechen, Fehlern je Sprecher und dem Plaud-Befund, ohne Messung) und Offen
  - Kurzfassung des Berichts ausfüllen: No-Go, „bei dieser Aufnahme ist lokal nicht viel mehr drin“ als gültiges Ergebnis laut Ticket, mit Empfehlung zur Aufnahme
  - Bei Go: Umsetzungsticket mit Leitplanken (neue Settings in der Config, `stale` für gespeicherte Transkripte samt Hinweis zur Neuverarbeitung, Bewertung bei Modellwechsel neu kalibrieren, TOOL-35)
  - Übergaben an TOOL-60, TOOL-81 und IOA-1302
- Verify: `scripts/check`. Die Summe aus Füllwort- und übrigen Auslassungen ergibt die Auslassungen aus der WER-Tabelle. `grep` im Bericht gegen Session-Keys, Gruppenname und Personennamen aus beiden Snapshots ergibt keinen Treffer.
- AC: Auslassungen aufgeschlüsselt, Gegenprobe im Dokument oder ihr Wegfall begründet, Empfehlung oder begründetes No-Go mit Empfehlung zur Aufnahme, bei Go ein Umsetzungsticket.

## Folge-Tickets
- TOOL-81: Messbefund Hotwords an/aus an A und B (Stufe 1) als Kommentar. Ursache, Schalter und README bleiben dort.
- TOOL-60: Modell und Einstellungen für V0.2 (oder No-Go) mit Spanne statt Einzelwert, Ergebnis der Gegenprobe C oder ihr Wegfall, Empfehlung zur Aufnahme.
- IOA-1302: Kommentar mit dem Ergebnis. Die Pipeline bleibt bei `base`, das Pilot-Transkript ist damit der Stand, an dem IT/OT und LLM-Korrektur gemessen werden. Dazu die WER-Spanne und der Anteil der Füllwörter an den Auslassungen.
- TOOL-96: nur Verweis im Bericht. Die Sprecherzuordnung aus dem Plaud-Vergleich ist dort schon erfasst, eine Übergabe braucht es nicht.
- Umsetzung bei Go: [kein Ticket: entsteht erst in Chunk 5, falls die Go-Regel greift]
- Neukalibrierung der Bewertung bei Modellwechsel: [kein Ticket: Leitplanke im Umsetzungsticket]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Spike-Werkzeug `scripts/spike/asr.py` | no |
| 2 | Stufen 1–2: Hotwords, VAD, Dekodierung | no |
| 3 | Stufe 3: Modelle | no |
| 4 | Stufe 4: Kombination, Finalisten, Fenster für Referenz C | yes |
| 5 | Auslassungen, Gegenprobe C (falls vorhanden), Entscheidung, Übergaben | no |
