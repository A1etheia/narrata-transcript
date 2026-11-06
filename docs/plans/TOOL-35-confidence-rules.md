# TOOL-35 — Konfidenz und Unsicherheit von Transkriptpassagen bewerten

## Ziel
Jede Passage eines Referenztranskripts bekommt eine maschinenlesbare Stufe `confident` / `needs_review` / `uncertain`, dazu die Signale, die sie ausgelöst haben. Die Regeln sind klein, deterministisch und über die Konfiguration einstellbar. Heute gibt es nur die Domänen-Hinweise aus TOOL-44. Confidence, Segmentsignale, Zeiten und Sprecher liegen im Referenzformat, werden aber nicht ausgewertet. Nach dem Ticket ist an der Handreferenz aus TOOL-62 gemessen, wie viele Fehler die Regeln finden, wie viele Fehlalarme sie bringen und ob ein Parakeet-Abgleich als zusätzliches Signal lohnt.

## Ist-Stand
- Referenzformat v2: `Word.confidence` (`src/transcript/reference.py:51`), `Passage.signals` mit `avg_logprob`, `no_speech_prob`, `compression_ratio` (`reference.py:70`, gefüllt in `src/transcript/asr/whisper.py:241`), `Passage.speaker` nach `majority_speaker` (`reference.py:202`), `Diarization.overlaps` (`reference.py:138`), Capabilities im `AsrInfo` (`reference.py:95`, Flags `word_confidence`/`segment_signals` in `src/transcript/asr/backend.py:73`).
- Hinweise: `hints.review_session` schreibt `review/segment-NN.hints.json` (`src/transcript/hints.py:399`). Die `similar`-Schwellen sind Modulkonstanten (`hints.py:53-57`). Aufgerufen wird es in `_transcribe` vor der Diarisierung (`src/transcript/__main__.py:526`, Diarisierung ab `:537`). `transcript diarize` schreibt danach nur die Normalform neu (`__main__.py:582`).
- Konfiguration: feste Abschnitte und Schlüssel mit Prüfung nach Datei und Schlüssel (`src/transcript/config.py:16`, Muster `_bounded_int`, `_keyword_budget`). Ein `review`-Abschnitt existiert noch nicht.
- Pfade: `SessionPaths.review_dir`/`review_hints` (`src/transcript/session.py:111-116`). Atomares Schreiben über `jsonfile.write_atomic`.
- Contract (ios-archiv `docs/transcript-contract.md:98-117`): `passages[].confidence_tier` ∈ `confident`·`needs_review`·`uncertain`, `markers[].type` ∈ `unintelligible`·`speaker_unclear`·`crosstalk`·`gap`. Eine Stufe „unbewertet“ gibt es dort nicht.
- Stichprobe (nur lokal, `work/<key>/spike/`): Handreferenz über einen 180-s-Clip (358 Wörter, 2 Sprecher, `???` für Unverständliches, Sprecherkennung pro Zeile) und Läufe von Whisper turbo und Parakeet genau auf diesem Clip (`runs-clip/*/run.json`). Die Konvention der Handreferenz und die difflib-Ausrichtung stehen in `scripts/spike/compare.py` im Stand `2f5b875`. Der Clip stammt aus Segment 1 der Session `jahr-des-greifen/022`. Für 022 gibt es Audio und Manifest, aber noch keine ASR, keine Diarisierung und keinen Snapshot.

## Entscheidungen
Mit der Nutzerin am 06.11.2026 entschieden:
- **Stichprobe:** Confidence-, Lücken-, Sprecher- und Parakeet-Signale werden an der 3-min-Handreferenz kalibriert. Für `similar` hört und bewertet die Nutzerin 30–50 `similar`-Hinweise aus Session 022. Daraus ergibt sich nur die Präzision, keine Trefferquote. Diese Grenze wird dokumentiert.
- **Snapshot für 022:** `transcript context` und `transcript snapshot` laufen gegen Narrata. Danach wird 022 mit der echten Pipeline transkribiert und diarisiert. Kalibriert wird auf dem Zeitbereich des Clips innerhalb des 5-h-Laufs, weil der Produktivlauf ebenfalls auf der ganzen Aufnahme läuft.

Eigene Wahl:
- **Stufen heißen wie im Contract:** `confident`, `needs_review`, `uncertain`. TOOL-69 bildet sie dann ohne Übersetzung ab. Eine Passage ohne ein einziges auswertbares Signal bekommt `needs_review` mit Grund `no_signals`. Sicherheit wird nie aus fehlenden Daten abgeleitet.
- **Einheit ist die Passage.** Wort-Signale stehen mit Wortindex dabei. Die Stufe einer Passage ist das Maximum ihrer ausgelösten Regeln.
- **Regeln (Startwerte, kalibriert in Chunk 5):**
  - `low_confidence`: Anteil der Wörter mit Confidence unter `word_low` → `needs_review` ab `low_share_review`, `uncertain` ab `low_share_uncertain`. Ein Wort unter `word_very_low` macht die Passage mindestens `needs_review`.
  - `segment_signal`: `no_speech_prob` ≥ Schwelle, `avg_logprob` ≤ Schwelle, `compression_ratio` ≥ Schwelle (Whisper-Default 2,4 für Schleifen).
  - `gap` (für Auslassungen): größte Lücke zwischen Wörtern einer Passage ≥ `gap_ms`, oder Sprechdichte unter `min_words_per_second`.
  - `missing_times`: Passage oder Wörter ohne Zeiten, obwohl das Backend Zeiten kann.
  - `speaker_unclear`: Diarisierung vorhanden, Passage ohne Mehrheitslabel. `crosstalk`: Passage überschneidet `diarization.overlaps`.
  - `known_variant` → `needs_review`, `ambiguous` → `uncertain`, `similar` → Stufe je nach Kalibrierung (Startwert `needs_review`).
  - Ist eine Capability nicht vorhanden (keine Confidence, keine Signale, keine Diarisierung, kein Snapshot), feuert die Regel nicht. Sie steht dann unter `missing` und bekommt keinen Ersatzwert.
- **Mundart/Sprecher:** Die Labels gelten pro Segment und sind bis TOOL-68 keiner Person zugeordnet. Schwellen pro Person gibt es deshalb nicht. Die Kalibrierung misst die Fehlerquote pro Label der Stichprobe und gibt das Ergebnis an TOOL-36/TOOL-68 weiter.
- **Konfiguration:** neuer Abschnitt `review:` mit `uncertainty:` (alle Schwellen und Stufen oben) und `similar:` (`min_ratio`, `min_length`, `max_length_deviation`). `hints._Matcher` bekommt die `similar`-Werte übergeben, die Defaults entsprechen den heutigen Konstanten. Damit lassen sich alle Schwellen ohne Codeänderung anpassen.
- **Eigene Datei:** `review/segment-NN.uncertainty.json`, `format_version: 1`, **ohne Transkripttext**. Sie enthält nur Passagenindex, Stufe, Gründe (`rule`, `value`, `threshold`, `level`, Wortindizes), `missing`, Zählwerte, die verwendeten Schwellen und die Herkunft (`reference.processed_at`, `hints.created_at` oder `null`, `knowledge_snapshot_id`). Das Referenzformat und die Hinweisdatei bleiben unverändert.
- **Ablauf:** `transcript assess <session>` bewertet eigenständig, ideal zum Nachjustieren der Schwellen. Dieselbe Bewertung läuft automatisch am Ende von `transcribe` (nach der Diarisierung bzw. nach der ASR bei `--no-diarize`) und am Ende von `diarize`. Die Konsole zeigt nur Zählwerte pro Stufe.
- **Kalibrierung als bleibendes Werkzeug:** `transcript calibrate <session> --segment N --reference <txt> --offset-ms X`. Die Handreferenz wird nach der Konvention von `compare.py` gelesen (Labels, `[Notizen]`, `???` als Lücke). Die difflib-Ausrichtung wird übernommen. Jede Ersetzung oder Einfügung zeigt auf ein Wort, jede Auslassung auf die Lücke zwischen zwei Wörtern und damit auf Passage und Lücke. Ausgegeben werden nur Zahlen: Fehler gesamt und pro Label, pro Regel und Stufe gefundene Fehler und Fehlalarme, übersehene Fehler (Auslassungen getrennt), Review-Anteil an Passagen und Audiozeit, AUC der Word-Confidence. TOOL-58/60 nutzen das Werkzeug wieder.
- **`similar`-Stichprobe:** `transcript calibrate … --similar-sheet <csv>` schreibt eine deterministisch gestreute Auswahl von bis zu 50 `similar`-Hinweisen unter `work/<key>/review/calibration/` (Timecode, gehört, Kandidat, Methode, Score, leere Spalte `richtig`). Mit `--similar-judged <csv>` werden die ausgefüllten Antworten gelesen und Präzision pro Methode und Score-Band ausgegeben.
- **Parakeet-Entscheidung:** Es braucht keinen neuen Lauf, die Clip-Läufe beider Modelle liegen vor. Ein Wegwerf-Skript im Scratchpad nutzt `transcript.calibration` für die Ausrichtung beider Läufe gegen die Handreferenz. Es zählt, wie viele Whisper-Fehler (vor allem Auslassungen) an Stellen liegen, an denen Parakeet abweicht, die Confidence-Regeln aber nicht anschlagen, und wie viele Abweichungen Fehlalarme sind. Ergebnis: aufnehmen (dann Folge-Ticket), verwerfen oder an TOOL-60 übergeben.
- **Der Agent liest keinen Transkripttext** (wie in TOOL-62): weder Handreferenz noch Läufe, Hinweise oder CSV. Er sieht nur die Zählwerte von `calibrate` und dem Skript. Fehlerbeispiele und das Anhören übernimmt die Nutzerin.

## Daten-Check
- Folgt TOOL-66? *handled*: Handreferenz, `similar`-Bogen und Läufe bleiben unter `work/` (per `.gitignore` ausgeschlossen). Die Unsicherheitsdatei enthält keinen Text. Die Konsole zeigt nur Zählwerte.
- Kann Echtes ins Repo? *handled*: Tests nutzen erfundene Passagen und eine erfundene Handreferenz inline, `tests/fixtures/` bekommt nichts. Der Kalibrierungsbericht `docs/spikes/TOOL-35-kalibrierung.md` enthält nur Kennzahlen, keinen Session-Schlüssel, keine Namen, keine Labels.
- Logs/Fehlermeldungen? *handled*: `uncertainty.py` und `calibration.py` loggen nichts. Fehler nennen Datei, Feld, Zeile oder Passagennummer, nie einen Wert. Ein Smoke-Test prüft stdout/stderr von `assess` und `calibrate` auf Fixture-Text. Das Parakeet-Skript liegt nur im Scratchpad, gibt nur Zahlen aus und wird nicht committet.

## Contract-Check
- Passt zu IOA-1214 (Contract 1.1)? *handled*: Stufennamen und Gründe `gap`/`speaker_unclear`/`crosstalk` entsprechen `confidence_tier` und `markers[].type`. Geschrieben wird hier kein Contract-JSON, die Abbildung macht TOOL-69.
- Braucht Narrata eine Änderung? N/A, weil der Contract die drei Stufen schon trägt und nichts Neues exportiert wird.

## Resume-Check
- Abbruch? *handled*: `assess` und `calibrate` laufen ohne Modell, deterministisch, in Sekunden und schreiben atomar. Ein Abbruch hinterlässt alte Dateien, der nächste Lauf ersetzt sie. Wird ein Segment `failed`, entfernt `assess` dessen Unsicherheitsdatei.
- Wiederverwendung? *handled*: Die Bewertung läuft immer neu, so passt sie stets zu Referenz, Hinweisen und Konfiguration. Der lange ASR-Lauf auf 022 nutzt die bestehende Wiederverwendung (`transcription._reusable`).
- Gleiches Modell/Snapshot? *handled*: Die Datei hält die Schwellen, `knowledge_snapshot_id` und `reference.processed_at` fest. Der Kalibrierungsbericht nennt Modell, Snapshot-ID-Präfix und Schwellen.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt: difflib, csv und eine AUC per Rangzählung, alles stdlib. Parakeet wird nicht neu ausgeführt.

## Format-Check
- Neue Unsicherheitsdatei: *handled*: `format_version: 1`. Der Leser lehnt andere Versionen ab und verweist auf `transcript assess`.
- Hinweisdatei, Referenzformat, Snapshot: N/A, weil unverändert (`HINTS_FORMAT_VERSION` 1, `REFERENCE_FORMAT_VERSION` 2).
- Konfiguration: *handled*: neuer optionaler Abschnitt `review`. Fehlt er, gelten die Defaults, alte Konfigurationen bleiben gültig.

## Chunks
### Chunk 1 — Schwellen in die Konfiguration
- Dateien: `src/transcript/config.py`, `config/example.yaml`, `src/transcript/hints.py`, `src/transcript/__main__.py`, `tests/test_config.py`, `tests/test_hints.py`
- Änderung: `SimilarThresholds` und `UncertaintyThresholds` (frozen, Defaults = Startwerte) als `Config.review_similar`/`review_uncertainty`. `load_config` prüft `review.similar.*` und `review.uncertainty.*` mit Bereichen, `format_config` gibt sie aus. `find_hints`/`review_session` nehmen `SimilarThresholds`, die Modulkonstanten entfallen.
- Verify: `scripts/check`
- AC: Ohne `review`-Abschnitt sind die Hinweise byte-gleich zu heute. Ein geänderter `min_ratio` ändert einen Testfall von „kein Hinweis“ zu `similar`. Unbekannte Schlüssel und Werte außerhalb des Bereichs werden mit Datei und Schlüssel abgelehnt.

### Chunk 2 — Regeln
- Dateien: `src/transcript/uncertainty.py` (neu), `tests/test_uncertainty.py` (neu)
- Änderung: `Reason(rule, level, value, threshold, words)`, `PassageRating(passage, level, reasons, missing)`, `assess(reference, hints: SegmentHints | None, thresholds) -> tuple[PassageRating, ...]` mit den Regeln aus „Entscheidungen“. `missing` wird aus Capabilities und den tatsächlich vorhandenen Daten abgeleitet.
- Verify: `scripts/check`
- AC: Jede Regel hat einen auslösenden und einen nicht auslösenden Fall. Ohne Confidence, Signale oder Diarisierung feuert die jeweilige Regel nicht und steht in `missing`. Eine Passage ganz ohne Signale ist `needs_review`/`no_signals`. `ambiguous` ergibt `uncertain`. Gleiche Eingabe ergibt die gleiche Ausgabe. Die Referenz bleibt unverändert.

### Chunk 3 — Unsicherheitsdatei, `assess` und Doku
- Dateien: `src/transcript/uncertainty.py`, `src/transcript/session.py`, `src/transcript/__main__.py`, `tests/test_uncertainty.py`, `tests/test_smoke.py`, `README.md` (neuer Abschnitt „Unsicherheitsbewertung“, „Konfiguration“)
- Änderung: `SessionPaths.review_uncertainty(index)`, `write_assessment`/`load_assessment` (v1), `assess_session(paths, indices, thresholds)`. Neues Kommando `transcript assess`. Aufruf am Ende von `_transcribe` und `_diarize`. Konsole: `N confident, N needs_review, N uncertain`.
- Verify: `scripts/check`
- AC: Ein Rundlauf erhält alle Felder. Eine fremde Version wird abgelehnt. Smoke-Test mit Fake-Backend: Die Datei entsteht, enthält keinen Passagentext, und stdout/stderr enthalten keinen Fixture-Text. Ein `failed`-Segment hat keine Datei. Die README beschreibt Stufen, Regeln, Schwellen und `missing`.

### Chunk 4 — Kalibrierungswerkzeug
- Dateien: `src/transcript/calibration.py` (neu), `src/transcript/__main__.py`, `tests/test_calibration.py` (neu), `tests/test_smoke.py`, `README.md` („Kalibrierung“)
- Änderung: Handreferenz parsen (Port aus `compare.py`), ausrichten, Fehler den Wörtern und Lücken zuordnen, Kennzahlen pro Regel, Stufe und Label, AUC. `transcript calibrate` mit `--segment`, `--reference`, `--offset-ms`, `--similar-sheet`, `--similar-judged`.
- Verify: `scripts/check`
- AC: An einer erfundenen Referenz mit bekannter Ersetzung, Auslassung und Einfügung zeigen die Zählwerte genau diese. `???` absorbiert Wörter wie in TOOL-62. Der Bogen enthält höchstens 50 Zeilen, deterministisch ausgewählt. Die Präzision aus einem ausgefüllten Bogen stimmt. Die Ausgabe enthält keinen Fixture-Text.

### Chunk 5 — Kalibrierung an der Stichprobe und Entscheidung
- Dateien: `src/transcript/config.py` (Defaults), `config/example.yaml`, `docs/spikes/TOOL-35-kalibrierung.md` (neu), `README.md` (Verweis), ggf. Tests, die Defaults prüfen
- Änderung (mit Nutzerin): Clip-Offset in Segment 1 bestimmen (PCM-Abgleich per Scratchpad-Skript), dann `context`/`snapshot`/`transcribe`/`diarize` für 022. `calibrate` laufen lassen und Schwellen nachziehen. Parakeet-Messung per Scratchpad-Skript. `similar`-Bogen erzeugen, die Nutzerin bewertet, Präzision lesen. Bericht nur mit Kennzahlen: Fehlalarme, übersehene Fehler, Review-Anteil gegen gefundenen Fehleranteil, Mundart-Effekt pro Label, `similar`-Präzision, Parakeet-Entscheidung mit Messwerten und das Urteil, ob die Signale für eine sinnvolle Review-Eingrenzung reichen.
- Verify: `scripts/check`, dazu `transcript assess` auf 022 (nur Zählwerte)
- AC: Alle Akzeptanzkriterien des Tickets zur Messung sind im Bericht belegt. Die Defaults entsprechen den kalibrierten Werten. Wird Parakeet aufgenommen, existiert ein Folge-Ticket.

## Verifikation gesamt
`scripts/check` nach jedem Chunk. Am Ende `transcript assess jahr-des-greifen/022` und `transcript calibrate …` auf dem Clip. Die Konsole zeigt nur Zahlen, die Nutzerin prüft einige `uncertain`-Passagen gegen das Audio.

## Folge-Tickets
- TOOL-36: Review-Kandidaten lesen `review/segment-NN.uncertainty.json` und die Hinweise, `uncertain` vor `needs_review`; Gewichtung pro Sprecher, sobald TOOL-68 Labels Personen zuordnet (Kommentar am Ticket).
- TOOL-69: Stufe → `confidence_tier`, Gründe `gap`/`speaker_unclear`/`crosstalk` → `markers` (Kommentar am Ticket).
- TOOL-60: Prüft am vollen Pilotlauf, ob die Eingrenzung aus dem Bericht hält (Kommentar am Ticket).
- Parakeet-Zweitlauf: [kein Ticket: entscheidet Chunk 5; bei Aufnahme wird das Ticket vor `/close-ticket` angelegt und hier eingetragen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schwellen in `config.py`, `hints.py` liest sie | no |
| 2 | `uncertainty.py`: Regeln | no |
| 3 | Unsicherheitsdatei, `transcript assess`, README | no |
| 4 | `calibration.py`, `transcript calibrate` | no |
| 5 | Kalibrierung an 022, Parakeet-Entscheidung, Bericht | no |
