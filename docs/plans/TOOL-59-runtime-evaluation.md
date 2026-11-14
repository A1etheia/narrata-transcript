# TOOL-59 — Laufzeit, Ressourcenverbrauch und manuellen Review-Aufwand auswerten

## Ziel
Nach TOOL-59 ist dokumentiert, ob die lokale V0.1-Pipeline im Alltag praktikabel ist: Laufzeit je großem Schritt, Segmente und Fehlversuche, Wiederverwendung beim Resume, Peak-RAM/VRAM, Review-Kandidaten und manueller Restaufwand pro Stunde Audio. Zusätzlich trägt `report.json` die Rechenzeiten von ASR und Diarisierung je Segment, damit spätere Sessions (TOOL-92, TOOL-93, TOOL-60) sie maschinenlesbar vergleichen können. Heute steht die ASR-Zeit nur in den Referenzdateien, die Diarisierungszeit wird gar nicht gespeichert, und Peak-RAM/VRAM des erfolgreichen Pilotlaufs fehlen.

## Ist-Stand
- `src/transcript/report.py:49` `REPORT_FORMAT_VERSION = 1`; `SessionReport` (`report.py:158`) hat keine Laufzeit. `compose` (`report.py:403`) lädt Referenzen, Kandidaten, Bewertungen, Zuordnung.
- ASR-Zeit: `Processing.elapsed_ms` (`src/transcript/reference.py:118-121`) = Dauer des erfolgreichen Backend-Aufrufs, im Pilot 377 s (Segment 1) und 28 s (Segment 2).
- Diarisierungszeit: nur in `SegmentSummary.elapsed_ms` (`src/transcript/diarization/__init__.py:160`), nicht in der Rohdatei (`to_json`, `__init__.py:383`; `load_run`, `__init__.py:354`, liest nur bekannte Felder).
- `stats` im Export ist der Bericht unverändert (`src/transcript/export.py:6`, `:140`); das Schema lässt `stats` offen (`contracts/transcript-v1.schema.json:123`).
- `status._report` (`src/transcript/status.py:404`) vergleicht die Bytes von `report.outputs`; ein geänderter Bericht gilt als `stale` und wird von `process`/`report` neu geschrieben.
- `work/<s>/pipeline.log` (`src/transcript/__main__.py:1559`) hält Schrittwechsel, Exit-Codes, `reused`/`ran` und jeden Fehlversuch; laut `session.py:239` nur für Menschen, nie zurückgelesen.
- Pilotzahlen: `docs/pilot/TOOL-58-erste-session.md` (Lauf 6:57 min, Zuordnung 4 min, 870 Kandidaten = 160/h, Review 35/h, RAM/VRAM nur aus dem gescheiterten Versuch).

## Entscheidungen
- **Laufzeit in `report.json`, kein Log-Parser.** `pipeline.log` bleibt Protokoll für Menschen; die Zahlen kommen aus versionierten Artefakten.
- **`runtime`-Sektion:** je Segment `asr_ms` und `diarization_ms` (`null` = nicht erfasst), dazu die Summen. Sie beschreibt die Rechenzeit, mit der die gespeicherte Datei entstand, nicht den letzten Lauf; Wiederverwendung zeigt `pipeline.log`. Fehlt eine Zeit, gibt es die Note `runtime_not_recorded` je Segment. Kein Echtzeitfaktor im Bericht; der steht im Auswertungsbericht.
- **`REPORT_FORMAT_VERSION` 1 → 2**, weil `report.json` eine neue Pflichtsektion bekommt.
- **Diarisierungs-Rohdatei bekommt optional `elapsed_ms`, ohne Versionssprung.** Alte Dateien bleiben lesbar (Feld `null`), wie die Regel in `docs/referenzformat.md:94` verlangt; ein Sprung würde jede gespeicherte Diarisierung neu rechnen (`load_run` verwirft andere Versionen).
- **TOOL-78 entfällt.** TOOL-59 wertet keine Fehlerraten aus; jeder Fehlversuch steht mit Segment und Fehlerklasse in `pipeline.log`, im Pilot gab es nur nicht wiederholbare Konfigurationsfehler.
- **RAM/VRAM jetzt nachmessen**, auf einer Kopie der Pilotsession, damit Review-Entscheidungen und Zuordnung der echten Session nicht `stale` werden. ASR und Diarisierung getrennt (`transcript transcribe --force`, `transcript diarize --force`) unter `/usr/bin/time -v` (Peak-RSS), parallel `nvidia-smi --query-gpu=memory.used --format=csv -lms 500` in den Scratchpad.

## Daten-Check
- TOOL-66: handled — `runtime` enthält nur Segmentnummern und Millisekunden, keinen Text, keine Labels, keine Namen.
- Repo: handled — der Auswertungsbericht übernimmt nur Kennzahlen; Session-Key und Gruppe stehen nicht darin (Konvention aus dem Pilotbericht). Die Messkopie liegt unter `work/`, die Messprotokolle im Scratchpad; beide werden danach gelöscht.
- Logs/Fehlermeldungen: handled — keine neuen Logzeilen; Ladefehler von `elapsed_ms` nennen wie bisher Datei und Feld.
- Fixtures: N/A, weil Tests synthetische Laufzeiten nutzen.

## Contract-Check
- IOA-1214: handled — `stats` ist laut Schema ein offenes Objekt, Narrata wertet es nicht aus; `contract_version` bleibt 1.0/1.1.
- Narrata: N/A, keine Änderung nötig. Ein neu geschriebener Export hat einen anderen Hash; `transcript:import` aktualisiert dann idempotent, kein IOA-Ticket.

## Resume-Check
- Abbruch des Messlaufs: handled — betrifft nur die Kopie; die echte Session bleibt unverändert, die Kopie wird gelöscht.
- Wiederverwendung: handled — eine wiederverwendete Diarisierung behält ihr gespeichertes `elapsed_ms`; `elapsed_ms` wird nur bei erfolgreichem Aufruf geschrieben.
- Modell/Snapshot beim Messlauf: handled — die Kopie übernimmt Snapshot und Konfiguration der Pilotsession; `--force` rechnet mit demselben Modell neu.

## Dependency-Check
- N/A, weil keine neue Abhängigkeit: `/usr/bin/time` (GNU time) und `nvidia-smi` sind nur Messwerkzeuge des einmaligen Laufs, nicht Teil der Pipeline. Fehlt GNU time, wird stattdessen `ps`-Sampling verwendet.

## Format-Check
- `report.json`: handled — `format_version` 2; vorhandene Berichte gelten als `stale` und werden von `transcript report`/`process` neu geschrieben, die Exportdatei ebenso.
- Diarisierungs-Rohdatei: handled — bleibt `format_version` 1, das Feld ist optional und additiv; alte Dateien laden mit `elapsed_ms = null`.
- Referenzformat: N/A, unverändert.

## Chunks
### Chunk 1 — Diarisierungszeit speichern
- Dateien: `src/transcript/diarization/__init__.py`, `tests/test_diarization.py`, `docs/referenzformat.md`
- Änderung: `DiarizationRun` bekommt `elapsed_ms: int | None = None`; `_diarize_segment` setzt es aus `done.elapsed_ms` vor `write_run`; `to_json` schreibt, `load_run` liest es optional. Referenzformat-Doku nennt das Feld.
- Verify: `scripts/check`
- AC: Eine neu gerechnete Diarisierung speichert ihre Zeit; eine alte Datei ohne Feld lädt und wird weiter wiederverwendet.

### Chunk 2 — Laufzeit im Abschlussbericht
- Dateien: `src/transcript/report.py`, `tests/test_report.py`, ggf. `tests/test_export.py`/`tests/test_status.py`, `README.md` („Abschlussbericht“)
- Änderung: `Runtime`/`SegmentRuntime` in `SessionReport`; `compose` liest `asr_ms` aus `reference.processing.elapsed_ms` und `diarization_ms` aus `diarization.load_run(...)`; Note `runtime_not_recorded`; `REPORT_FORMAT_VERSION = 2`; Markdown-Abschnitt „## Laufzeit“ mit Tabelle je Segment und Summen.
- Verify: `scripts/check`
- AC: `report.json` und `report.md` zeigen die Rechenzeit je Segment; fehlende Zeiten sind als Hinweis benannt; gleiche Eingaben geben gleiche Dateien.

### Chunk 3 — Messlauf und Auswertungsbericht
- Dateien: `docs/pilot/TOOL-59-auswertung.md`
- Änderung: Pilotsession unter freiem Ordinal nach `work/` kopieren (Audio, Manifest, Kontext, Snapshot, Konfiguration); `transcribe --force` und `diarize --force` je unter `/usr/bin/time -v` mit `nvidia-smi`-Mitschnitt; `transcript report` auf der echten Session neu schreiben. Bericht mit: Aufnahmedauer, Segmente erzeugt/transkribiert, Fehlversuche, Zeit je Schritt und gesamt (aus `pipeline.log` und `runtime`), Echtzeitfaktor, Peak-RAM/VRAM je Modell, Wiederverwendung beim Resume, Kandidaten pro Stunde, Review- und Zuordnungsaufwand pro Stunde Audio, Engpässe als Beobachtung, keine API-Kosten, Entscheidung TOOL-78. Kopie und Messprotokolle danach löschen.
- Verify: `scripts/check`; `grep -n` auf Session-Key und Gruppennamen im neuen Bericht liefert nichts.
- AC: alle Akzeptanzkriterien des Tickets im Bericht belegt.

## Folge-Tickets
- TOOL-78 (Versuche pro Segment im Referenzformat): entfällt laut Entscheidung; in `/close-ticket` mit Begründung schließen.
- Laufzeit-Vergleich über mehrere Sessions: [kein Ticket: bisher nur eine echte Session, `runtime` in `report.json` reicht als Grundlage]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Diarisierungszeit in der Rohdatei | no |
| 2 | `runtime` in `report.json`/`report.md`, Format 2 | no |
| 3 | Messlauf auf Kopie, `docs/pilot/TOOL-59-auswertung.md` | no |
