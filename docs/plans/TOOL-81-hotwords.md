# TOOL-81 — Hotwords lassen Whisper turbo auf langen Aufnahmen Sprache auslassen

## Ziel
Ursache der drei Hotword-Effekte an realen Aufnahmen belegen: Wortverlust bei kurzer Liste, Seed-Streuung mit Hotwords, Zerfallen in kurze Passagen ohne Hotwords. Danach wählt die Pipeline nach einer vorab festgelegten Regel die beste Einstellung, verhindert die schädliche Lage selbst, und `asr.hotwords` schaltet das Biasing ab. Heute verliert ein Snapshot mit wenigen Begriffen unbemerkt rund 15 % der Wörter, und es gibt keinen Schalter.

## Ist-Stand
- `src/transcript/asr/whisper.py:200-213`: Bei `keyword_biasing` gehen die vorderen Keywords, die ins Budget passen (`fit_hotwords`, `:259`, `HOTWORD_TOKENS = 223`, `:47`), als `hotwords=` an `WhisperModel.transcribe`. `takes_hotwords` (`:250`) schaltet nur nach dem Modellnamen. Kein Konfigurationsschalter.
- faster-whisper 1.2.1 `get_prompt`: Hotwords werden in jedem 30-s-Fenster als `<|startofprev|> + hotwords` vor den Decoder gesetzt. Wegen `condition_on_previous_text: false` (`FIXED_SETTINGS`, `whisper.py:48`) ist das der einzige Prompt. Ohne Hotwords bekommt der Decoder gar keinen Prompt.
- `src/transcript/__main__.py:740-756`: `transcribe` liest die Keywords aus dem Snapshot und meldet Zahl und Kennung.
- Wiederaufnahme: `src/transcript/transcription.py:275-297` vergleicht Identität plus `settings`, Snapshot-Kennung und `keywords_used`. Ein Backend ohne `keyword_biasing` ignoriert die Keywords (`keywords=None`).
- Spike-Werkzeug `scripts/spike/asr.py` (TOOL-93): Varianten `base`/`pchw`/`nohw`/`nohw-hp` plus Modifikatoren, eine Wurzel pro Seed, `prepare`/`run`/`score`/`windows`. `run` setzt Seed und Hotword-Schalter über einen CLI-Wrapper (`:328-345`).
- Befund TOOL-93 (`docs/spikes/TOOL-93-erkennungsqualitaet.md`, Stufe 1):
  - `base` (48 Hotwords): keine Wortverluste, aber B streut 32,9–41,1 %.
  - `pchw` (9 Hotwords): −15 % Wörter, 3 % Wiederholung, doppelte Laufzeit. Das reproduziert den TOOL-35-Lauf.
  - `nohw`: Seeds identisch, aber 3703 statt rund 870 Passagen. Die Bewertung übersieht dann 114 bzw. 89 Fehler.
- Downstream: TOOL-90 (`session_terms` ins Biasing, To Do) wartet auf dieses Ticket.

## Entscheidungen
- **Umfang: alle drei Effekte** (Entscheidung der Projektverantwortlichen). Wortverlust, Seed-Streuung und Zerfallen ohne Hotwords hängen alle am Prompt pro Fenster und werden zusammen untersucht.
- **Werkzeug:** `scripts/spike/asr.py` wird erweitert, kein neues Skript. Wurzeln, Seeds und Provenienzprüfung sind dort schon gelöst.
- **Hypothesen und Varianten:**

  | Effekt | Hypothese | Variante |
  | --- | --- | --- |
  | Wortverlust | Länge der Liste | `kw9`, `kw20`, `kw30`: die vorderen N der vollen Liste |
  | Wortverlust | Inhalt der Liste | `neutral9`: 9 feste, neutrale deutsche Wörter, nicht aus dem Snapshot, gegen `pchw` |
  | Wortverlust, Seed-Streuung | Temperatur-Fallback | Modifikator `+temp0`: nur Temperatur 0. Beim Fallback wirkt der Seed, und `pchw` braucht doppelt so lange |
  | Wortverlust | VAD | `pchw+novad` |
  | Zerfallen ohne Hotwords | Ein beliebiger Prompt hält die Passagen lang | `neutral`: fester neutraler Prompt in voller Länge, ohne Snapshot-Begriffe |

- **Diagnose aus der Rohform:** Pro 30-s-Fenster werden Temperatur, Kompressionsrate, `avg_logprob`, Segmentzahl und Lücken zwischen VAD-Sprache und erkannten Segmenten aus `segment-NN.raw.json` gezählt. So lässt sich zeigen, ob verlorene Wörter in Fallback-Fenstern oder in übersprungenen Bereichen liegen.
- **Prüfstand:**
  - Pilotsitzung: Segment 1 mit Referenz A und B, je 3 Seeds.
  - Ganze Aufnahme: Segment 1 der Pilotsitzung über die vollen 5:00:00, das sind die 60 Abschnitte aus dem Befund, und Segment 1 der zweiten Sitzung, beide ohne Referenz, Vergleich pro 5 min. Das deckt AC 2 ab. Die übrigen Segmente prüft der Abnahmelauf in Chunk 4.
- **Auswahlregel (vorab vereinbart):** Unter den Varianten, die in keinem 5-min-Abschnitt deutlich weniger Wörter haben als `nohw` (Schwelle: 20 % und mindestens 30 Wörter weniger) und an A und B höchstens so viele Fehler übersehen wie `base` (0 / 7), gewinnt die mit der niedrigsten mittleren WER an A und B. Unterschiede unter 3 Punkten gelten wie in TOOL-93 als Rauschen. Bei Gleichstand gewinnt die geringere Seed-Spanne an B, dann die einfachere Einstellung.
- **Pipeline danach:**
  - `asr.hotwords: true|false` kommt immer dazu (Default `true`). Bei `false` gilt `keyword_biasing: false` wie bei einem Modell ohne Hotwords.
  - Dazu der Schutz, den die Messung festlegt, z. B. eine Mindestlänge der Liste oder Auffüllen auf eine stabile Länge.
  - Gewinnt `neutral` oder `+temp0`, wird das die feste Einstellung in `FIXED_SETTINGS` bzw. im Prompt.
- **Wo die Läufe laufen:** `work/` und `.venv` liegen im Haupt-Checkout, nicht in diesem Worktree. Die Läufe brauchen deshalb dort Lesezugriff, gegebenenfalls per `/add-dir`.

## Daten-Check
- Aufnahmen, Läufe, Rohformen: *handled* — alles bleibt unter `work/<s>/experiments/asr/`, wie in TOOL-93 (TOOL-66).
- Konsole und Bericht: *handled* — `sections` und `decode` geben nur Zählwerte, Zeiten und Anteile aus, keinen Text, keine Begriffe, keinen Session-Schlüssel im Bericht.
- Hotwords in Meldungen: *handled* — die Pipeline nennt weiter nur Zahlen (`whisper.py:7`). Ein Schutz, der Begriffe weglässt, meldet nur die Zahl.
- Neutrale Wortliste: *handled* — feste, erfundene bzw. allgemeine Wörter im Code, keine Namen aus einem Snapshot.
- Fixtures: *handled* — neue Tests verwenden nur erfundene Begriffe wie die bestehenden (`Drachenhort`, `Beispielfigur`).

## Contract-Check
- *N/A, weil* kein Contract-JSON und kein Narrata-Endpoint berührt werden. `asr.settings` gehört zum internen Referenzformat. TOOL-90 (Contract 1.4) baut später auf dem Ergebnis auf.

## Resume-Check
- Abbruch eines Spike-Laufs: *handled* — jede Variante pro Seed hat eine eigene Wurzel, `transcribe` nimmt fertige Segmente wieder auf (`transcription.py:275`).
- Gleiches Modell und gleicher Snapshot: *handled* — `score` prüft Modell-Revision und Snapshot pro Variante (`check_provenance`). `sections` und `decode` tun das auch.
- Pipeline: *handled* — `hotwords` und ein eventueller Schutzparameter stehen in `asr.settings`. Ein Ergebnis mit Hotwords wird also nicht wiederverwendet, wenn sie abgeschaltet sind, und umgekehrt. Vorhandene Transkripte passen danach nicht mehr und werden einmal neu transkribiert, rund 7 min pro Sitzung. Das README nennt es.

## Dependency-Check
- *N/A, weil* keine neue Abhängigkeit und kein neues Modell dazukommt. Alle Varianten laufen mit faster-whisper 1.2.1 und large-v3-turbo aus dem Cache, lokal auf der vorhandenen GPU.

## Format-Check
- Referenztranskript `format_version: 1`: *handled* — `settings` ist laut `docs/referenzformat.md:44` eine freie Abbildung der Inferenzparameter. Ein neuer Schlüssel braucht keinen Versionssprung, alte Dateien bleiben lesbar und werden nur nicht wiederverwendet (siehe Resume-Check).
- Spike-Dateien (`run.json`): *N/A, weil* sie keine Versionsnummer haben und nur unter `work/` liegen.

## Chunks
### Chunk 1 — Spike-Werkzeug für Hotword-Ursachen
- Dateien: `scripts/spike/asr.py`
- Änderung:
  - neue Basen `kw<N>` (vordere N der vollen Liste), `neutral9`, `neutral`
  - Modifikator `+temp0` (`temperature: 0`)
  - Unterbefehl `sections <session> <variant>... --against <variant>`: Wörter pro 5 min, Abschnitte über der Schwelle der Auswahlregel
  - Unterbefehl `decode <session> <variant>`: Fenster-Diagnose aus der Rohform, Zählwerte je Seed
  - Docstring nachziehen
- Verify: `scripts/check`, dazu `asr.py prepare` mit einer neuen Variante an der Pilotsitzung (Wurzel entsteht, Config und Hotword-Zahl stimmen)
- AC: Alle Varianten der Hypothesentabelle lassen sich vorbereiten, laufen und auswerten. Die Ausgabe enthält keinen Text.

### Chunk 2 — Läufe und Spike-Bericht
- Dateien: `docs/spikes/TOOL-81-hotwords.md`
- Änderung:
  - Läufe: Hypothesentabelle × 3 Seeds an Segment 1 der Pilotsitzung, dazu `base`, `pchw`, `nohw` als Bezug (aus TOOL-93 wiederverwendet, wenn die Provenienz passt)
  - danach die Spitzenkandidaten über die ganze Aufnahme und an der zweiten Sitzung
  - Bericht mit den Stufen Wortverlust, Seed-Streuung und Zerfallen, je Messtabelle, Fenster-Diagnose und Zwischenbewertung
  - Entscheidung nach der Auswahlregel, mit der Form des Schutzes
- Verify: `scripts/check`. Der Bericht nennt für jede Hypothese belegt / widerlegt / offen.
- AC: Die Ursache ist an mindestens einer realen Aufnahme belegt (AC 1). Die gewählte Einstellung hat auf der ganzen Aufnahme keinen 5-min-Abschnitt über der Schwelle (AC 2).
- Nachtrag nach den Läufen:
  - Dazugekommen ist der Modifikator `+fill` in `scripts/spike/asr.py`. Er prüft das Auffüllen als Schutz, mit dem Ergebnis: widerlegt.
  - AC 2 ist präzisiert (Entscheidung der Projektverantwortung). Ein Wortverlust gilt als systematisch ab 5 Abschnitten mit Defizit oder ab 5 % weniger Wörtern im Segment. Vereinzelte, seed-abhängige Abschnitte bei voller Liste nennt der Bericht als Rest.

### Chunk 3 — Schalter und Schutz in der Pipeline
- Dateien: `src/transcript/config.py`, `src/transcript/asr/whisper.py`, `src/transcript/__main__.py`, `config/example.yaml`, `tests/test_asr_whisper.py`, `tests/test_config.py`
- Änderung:
  - `asr.hotwords` (bool, Default `true`) in Config und Beispiel-YAML
  - `WhisperBackend` setzt `keyword_biasing` aus Modell und Schalter und schreibt `hotwords` in die Settings
  - Schutz aus Chunk 2 (`docs/spikes/TOOL-81-hotwords.md`, Entscheidung): Eine Liste unter 110 Hotword-Tokens geht nicht an Whisper. `keywords_used` bleibt dann leer, und `asr.settings` vermerkt den Grund.
  - `transcribe` meldet abgeschaltete Hotwords einmal, nur mit Zahlen: Begriffe, Tokens, Schwelle, dazu der Hinweis, Begriffe im Snapshot zu ergänzen und neu zu transkribieren.
  - Ein schneller Vorab-Check ohne Modell (z. B. `transcript keywords <session>`) zeigt dieselben Zahlen, bevor ein Lauf startet.
- Verify: `scripts/check`
- AC: Hotwords sind abschaltbar. Eine Liste unter der Schwelle erreicht Whisper mit Default-Config nicht (Test mit erfundenen Begriffen). Die Wiederaufnahme unterscheidet an und aus, und ein neuer Snapshot mit mehr Begriffen löst die Neutranskription aus.
- Nachtrag nach der Umsetzung:
  - Der Grund für ein leeres `keywords_used` steht nicht als eigener Vermerk im Ergebnis, sondern als Schwelle `hotword_min_tokens` in `asr.settings`. Ein Schlüssel nur im Ergebnis würde die Identität beim nächsten Lauf nicht mehr treffen.
  - Die Wiederaufnahme verlangt nur noch, dass `keywords_used` eine geordnete Teilfolge der Keywords ist. Neue Begriffe kommen mit einem neuen Snapshot. Damit fällt die Regel weg, nach der ein Ergebnis ohne Hinweise bei gleichem Snapshot neu transkribiert wird (Ergebnis von `/simplify`).
  - Zusätzlich geändert: `transcription.py`, `asr/backend.py` (`HotwordCheck`), `asr/fake.py`, `scripts/spike/asr.py` (Schutz für die Varianten aus), `docs/asr-backends.md`, `tests/test_smoke.py`, `tests/test_transcription.py`.

### Chunk 4 — Abnahmelauf, Kalibrierung, README
- Dateien: `README.md` (Spracherkennung, Konfiguration), `docs/spikes/TOOL-81-hotwords.md` (Abschnitt Abnahme)
- Änderung:
  - Pipeline-Lauf mit der Default-Config über die ganze Pilotaufnahme, `sections` gegen `nohw`
  - `transcript calibrate` an A und B wiederholen (Ticketkommentar aus TOOL-35)
  - README beschreibt Entscheidung, Schalter, Schutz und die einmalige Neutranskription
- Verify: `scripts/check`
- AC: README „Spracherkennung“ beschreibt die Entscheidung (AC 3). Abnahme- und Kalibrierungswerte stehen im Bericht.
- Nachtrag nach dem Lauf:
  - Der Abnahmelauf läuft über das Spike-Werkzeug mit dem neuen Modifikator `+guard`, also in eigenen Wurzeln unter `experiments/`. Die echten Transkripte unter `work/<s>/asr/` bleiben so unberührt.
  - Gemessen ist Segment 1 beider Aufnahmen. Segment 2 (26 bzw. 5 min) ist nicht eigens gemessen.
  - Die Kalibrierung ergibt 0 übersehene Fehler an A und B. Das Folge-Ticket für neue Schwellen entfällt.

## Folge-Tickets
- Schwellen der Bewertung neu setzen, falls die Kalibrierung in Chunk 4 zeigt, dass die Defaults zur gewählten Einstellung nicht mehr passen: [kein Ticket: Kalibrierung in Chunk 4 ergab 0 übersehene Fehler an A und B, die Defaults passen]
- TOOL-90 (`session_terms` ins Biasing) kann danach starten; der Schutz aus Chunk 3 gilt auch für die neuen Begriffe: TOOL-90
- Narrata zeigt den geschätzten Füllstand der Hotword-Liste schon beim Pflegen der Begriffe: IOA-1336
- Handreferenz in einem Abschnitt, in dem `base` auf der zweiten Aufnahme ein Defizit hat, um zu klären, ob dort wirklich Sprache fehlt: [kein Ticket: nur nötig, falls die Abnahme in Chunk 4 wieder Defizite zeigt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Spike-Werkzeug: Varianten, `sections`, `decode` | no |
| 2 | Läufe und Spike-Bericht mit Entscheidung | yes |
| 3 | `asr.hotwords` und Schutz in der Pipeline | no |
| 4 | Abnahmelauf, Kalibrierung, README | no |
