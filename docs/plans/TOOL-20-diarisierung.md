# TOOL-20 — Sprecher-Diarisierung und Label-Stabilität evaluieren

## Ziel
Danach steht anhand der realen TOOL-62-Aufnahme fest, welche Sprechertrennung V0.1 nutzt und wie stabil ihre Labels über eine ganze Sitzung sind, als Zahl: Labels pro realer Person und Fehlzuordnungsrate. Heute liefert das gewählte Backend (Whisper turbo) keine Sprecher. TOOL-68 und alle personenbezogenen Auswertungen (TOOL-65, Redeanteile) warten auf diese Entscheidung.

## Ist-Stand
- `docs/spikes/TOOL-62-asr-vergleich.md` („Sprecherinformation“): Whisper und Parakeet liefern keine Sprecher. Der Sprecher-Modus von Granite Plus ist ungetestet.
- `scripts/spike/common.py:21-155`: `parse_args`, `scratch_dir`, `audio_seconds`, `VramPeak`, `finish`. `finish` schreibt `run.json` mit Segmenten und Wörtern in ein neues Laufverzeichnis.
- `scripts/spike/compare.py:20-38`: `_LABEL` entfernt die Sprecherkennung pro Zeile; `tokens`/`reference_tokens` lassen sich für die Ausrichtung wiederverwenden. `edit_counts` nutzt die `difflib`-Ausrichtung.
- `scripts/spike/cut.sh`: 16-kHz-Mono-WAV aus der Aufnahme, beliebiger Bereich.
- Unter `work/<gruppe>/<ordinal>/spike/` liegen aus TOOL-62: `excerpt.wav` (25 min), die Handreferenz (3 min, Sprecherkennung pro Zeile, 2 Sprecher, 46 Wechsel, keine Zeiten) und Whisper-turbo-Läufe mit Wortzeiten auf Ausschnitt und voller Aufnahme (5:00:00).
- `~/.cache/narrata-spike/parakeet` enthält NeMo 3.0.0 (daraus der Clustering-Diarizer).
- `docs/transcript-roadmap.py:39`, Reflexionspunkte `:181-182`: Für die Integration einer separaten Diarisierung gibt es noch kein Ticket.

## Entscheidungen
- **Kandidaten: pyannote `speaker-diarization-community-1` (pyannote.audio 4.x) und der NeMo-Clustering-Diarizer** (MarbleNet-VAD + TitaNet; Entscheidung der Projektverantwortlichen, 2026-11-04). Lizenzen und Hardwarebedarf werden vor dem Lauf an den Modellkarten geprüft.
- **Granite Plus fällt weg:** Granite läuft nur in 90-Sekunden-Blöcken stabil, und `[Speaker N]` wird pro Block neu vergeben. Stabile Labels pro Sitzung sind damit ausgeschlossen. Es wäre zudem ein zweiter ASR-Lauf nur für Sprecher. Der Bericht vermerkt das in einem Satz.
- **Integrierte Attribution des Favoriten:** Whisper turbo hat keine. Das AC ist mit diesem Befund erfüllt.
- **Sprecher kommen per Zeit-Overlap an die Whisper-Wörter.** Jedes Wort erhält das Label des Turns, der seine Mitte enthält; Wörter ohne Turn bleiben `unassigned`. Auf diese Weise würde auch die Pipeline integrieren, sodass Spike und spätere Umsetzung dasselbe messen.
- **Drei Messungen:**
  1. *Handreferenz (3 min):* Die Referenzwörter werden per `difflib` an die Whisper-Wörter ausgerichtet und erben deren Zeit. Gemessen werden die Wort-Fehlzuordnung (WDER) nach optimaler 1:1-Zuordnung der Labels, der Anteil `unassigned` und erkannte Sprecherwechsel (von 46, Toleranz ±0,5 s).
  2. *Volle Aufnahme:* Anzahl Labels, Sprechzeitanteil pro Label, Labels unter 1 % Anteil, Anzahl Turns, Median-Turnlänge, Overlap-Anteil.
  3. *Stichprobe (30):* aus dem Whisper-Lauf über die volle Aufnahme ein Segment von 2–10 s pro 10-Minuten-Fenster, also unabhängig von beiden Diarisierern und über die ganze Sitzung verteilt. Die CSV enthält nur `id,start,end` und leere Spalten `person`, `nsc`, `mixed`, `note`, damit beide Kandidaten blind bewertet werden. Pro Segment gilt das Label mit dem größten Overlap. Jedes Label wird der Person zugeordnet, die es mehrheitlich trägt. Daraus ergeben sich Fehlzuordnungsrate, Labels pro Person und das Verhalten bei NSC-Stimmen.
- **Bekannte Teilnehmerzahl:** Jeder Kandidat läuft mit und ohne `num_speakers`. Die Zahl gibt die Projektverantwortliche von Hand an; den Narrata-Snapshot gibt es erst mit TOOL-38/41.
- **Ergebnisformat `diar.json`** pro Lauf: `meta` (Modell, Version, Einstellungen, Laufzeit, Spitzen-RAM/VRAM, offline) und `turns` (`start`, `end`, `label`). Es ist ein Wegwerf-Format, kein Vorgriff auf TOOL-16.

## Daten-Check
- Folgt TOOL-66: handled. Audio, `diar.json`, Referenz und ausgefüllte Stichprobe liegen nur unter `work/<gruppe>/<ordinal>/spike/`.
- Transkripttext und Namen an Claude: handled. Der Agent liest weder Referenz noch `run.json`-Text noch die ausgefüllte CSV. Er sieht nur die Kennzahlen von `speakers.py`. Sprecherkennungen der Referenz und Einträge in `person` gibt das Skript nur als `S1`, `S2` bzw. `Person 1…n` (Reihenfolge des Auftretens) aus, nie im Wortlaut. So erscheinen Namen nicht auf der Konsole, falls versehentlich Klarnamen eingetragen werden.
- Konsole und Fehlertexte: handled. Ausgegeben werden nur Zähler, Anteile und Laufzeiten; Exceptions enthalten keine Inhalte.
- Repo: handled. Der Bericht enthält nur Kennzahlen, keinen Session-Schlüssel und keine Namen.
- Modelle lokal: handled. pyannote ist gated: Die Projektverantwortliche akzeptiert die Bedingungen und lädt einmal mit `HF_TOKEN` aus der Umgebung, der Token kommt nie in eine Datei im Repo. Danach laufen alle Läufe mit `HF_HUB_OFFLINE=1`, `diar.json` vermerkt das.

## Contract-Check
N/A, weil kein Contract-JSON und kein Endpoint betroffen sind.

## Resume-Check
- Abbruch: handled. Jeder Lauf schreibt in ein eigenes Verzeichnis mit Zeitstempel, `diar.json` entsteht erst am Ende; ein abgebrochener Lauf startet neu. Das kostet auf 5 h Minuten, nicht Stunden.
- Wiederverwendung: handled. Fertige Läufe werden nie überschrieben; die TOOL-62-Whisper-Läufe werden wiederverwendet, nicht neu erzeugt.
- Gleiches Modell: handled. Modell, Revision und Einstellungen (inkl. `num_speakers`) stehen in `diar.json`.

## Dependency-Check
- Nötig: handled. pyannote.audio kommt in eine neue Spike-venv `~/.cache/narrata-spike/pyannote`, NeMo nutzt die vorhandene Parakeet-venv. `pyproject.toml` bekommt keine Abhängigkeit.
- Lokal und Lizenz: handled. pyannote.audio steht laut Sekundärquellen unter MIT, community-1 unter CC-BY-4.0 (gated), TitaNet und MarbleNet unter CC-BY-4.0. Das wird an den offiziellen Modellkarten geprüft und im Bericht festgehalten.
- Hardware: handled. Der NeMo-Clustering-Diarizer baut eine Affinitätsmatrix über alle Embeddings; auf 5 h kann das die 15 GB RAM sprengen. Falls ja, läuft NeMo nur auf dem Ausschnitt, und der Bericht dokumentiert das als Ergebnis. pyannote auf 5 h ist auf der GPU unkritisch, Spitzenwerte werden gemessen.

## Format-Check
N/A, weil `diar.json` und die Stichproben-CSV Wegwerf-Formate des Spikes ohne Versionsfeld und ohne Leser im Paket sind.

## Chunks
### Chunk 1 — Spike-Werkzeug
- Dateien: `scripts/spike/run_pyannote.py`, `scripts/spike/run_nemo_diar.py`, `scripts/spike/speakers.py`, `scripts/spike/common.py`, `scripts/spike/README.md`
- Änderung: Zwei Runner (`--num-speakers` optional) schreiben `diar.json` über einen neuen Helfer `finish_diarization` in `common.py`, der `audio_seconds`, `VramPeak` und das Laufverzeichnis-Schema von `finish` wiederverwendet. `speakers.py` (nur stdlib, nutzt `tokens` aus `compare.py`) hat die Unterbefehle `reference`, `stats`, `sample` und `score-sample`. Die README bekommt einen Abschnitt für TOOL-20.
- Verify: `scripts/check`; `speakers.py` an synthetischen Dateien im Scratchpad mit bekannter Fehlzuordnung, bekannten Wechseln und bekanntem Overlap; beide Runner einmal auf `excerpt.wav`, danach `git status` ohne Datendateien.
- AC: Beide Runner laufen offline auf der GPU durch; `speakers.py` gibt keinen Text und keine Namen aus.

### Chunk 2 — Ausschnitt und Handreferenz
- Dateien: `docs/spikes/TOOL-20-diarisierung.md`
- Änderung: Beide Kandidaten laufen auf `excerpt.wav`, jeweils mit und ohne `num_speakers`, und werden mit `speakers.py reference` gegen die 3-Minuten-Referenz gewertet. Ins Berichtsgerüst kommen Methode, Kandidaten (Lizenz, Einrichtung), WDER, Wechsel und Laufzeit.
- Verify: `scripts/check`; `git grep` mit der lokalen Namensliste über den Bericht ohne Treffer.
- AC: Sprecherwechsel und Übersprechen auf der Referenz sind dokumentiert.

### Chunk 3 — Volle Aufnahme und Stichprobe
- Dateien: `docs/spikes/TOOL-20-diarisierung.md`
- Änderung: Volle Aufnahme per `cut.sh` als WAV, beide Kandidaten mit und ohne `num_speakers` (NeMo nur, wenn der RAM reicht), `speakers.py stats`. Mit `speakers.py sample` entstehen 30 Segmente als CSV; die Projektverantwortliche hört sie an und trägt Kürzel ein (SL, P1–Pn, `nsc`, `mixed`). Danach wertet `score-sample` die Stichprobe aus.
- Verify: `scripts/check`; die Turns in `diar.json` decken die Aufnahmedauer ab (nur Zähler prüfen).
- AC: Label-Stabilität als Zahl: Labels pro realer Person, Fehlzuordnungsrate in der Stichprobe, Verhalten bei NSC-Stimmen.

### Chunk 4 — Entscheidung und Übergaben
- Dateien: `docs/spikes/TOOL-20-diarisierung.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung: V0.1-Entscheidung und Fallback; Einfluss auf Wortlaut (separate Diarisierung lässt die Whisper-Wörter unverändert) und Zeitstempel; Integrationsaufwand ins Referenzformat (Sprecherfeld pro Wort/Segment, Label-Menge, Diarisierungs-Metadaten). Folgeticket für die Integration anlegen und in die Roadmap einplanen, Reflexionspunkte M1 beantworten, Roadmap neu generieren, Übergaben als Kommentare an TOOL-68, TOOL-16 und TOOL-64.
- Verify: `scripts/check`; `.md` aus `transcript-roadmap.py` neu erzeugt.
- AC: Alle verbleibenden Akzeptanzkriterien sind abgehakt; die Folgearbeiten tragen Ticket-Keys.

## Folge-Tickets
- `TOOL-76`: pyannote community-1 als eigenen Schritt nach der Transkription integrieren; Label der exklusiven Turns an der Wortmitte, Wörter ohne Turn bleiben ohne Label; Modell gated, einmal mit Token laden, danach offline.
- `TOOL-16`: optionales Sprecher-Label pro Wort (fehlt bei 6–14 % der Wörter), Segment-Label aus der Mehrheit, Diarisierungs-Metadaten getrennt von ASR-Metadaten.
- `TOOL-64`: nicht parallel zu pyannote (bis 13,8 GB RAM auf 5 h), Wortzeiten bleiben an; beim Ablösen von `scripts/spike/` auch Diarisierungs-Runner und `speakers.py`.
- `TOOL-68`: 1:1-Zuordnung von 4 Labels zu Personen; NSC-Stimmen ohne eigenes Label, vereinzelt bei einer mitspielenden Person; Wörter ohne Label durchreichen.
- [kein Ticket: NeMo-Clustering-Diarizer verworfen, weil er auf 5 h über 25 GB RAM braucht; kein Fallback für ganze Sitzungen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Spike-Werkzeug | no |
| 2 | Ausschnitt, Handreferenz | no |
| 3 | Volle Aufnahme, Stichprobe | no |
| 4 | Entscheidung, Roadmap, Übergaben | no |
