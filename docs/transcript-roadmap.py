#!/usr/bin/env python3
"""Recompute docs/transcript-roadmap.md and the Jira date list.

Single source for the transcript project's schedule (Jira TOOL + IOA-1213).
Edit START, WORKDAYS, PAUSES or the task list P, then run:

    python3 docs/transcript-roadmap.py

Writes transcript-roadmap.md next to this file and prints one JSON line per
ticket (key, start, end) for mirroring into Jira (customfield_10015 / duedate).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib

START = dt.date(2026, 11, 23)  # a Monday: the week the open work is planned from
FROM = dt.date(2026, 11, 23)  # first day counted; working days before it are skipped
WORKDAYS = [0, 1, 3]  # Mon, Tue, Thu -> 3 dev-days per week
PAUSES = [(dt.date(2026, 12, 21), dt.date(2027, 1, 3))]  # inclusive ranges, no work
GENERATED = "2026-11-22"

# (phase title, milestone sentence, [(key, title, dev-days, note)])
P = [
    ("Phase 0 — Fundament und Entscheidungen",
     "M0 — Repo steht, Datenschutz entschieden, Contract v1 eingefroren. Nichts auf beiden Seiten schreibt JSON, bevor IOA-1214 steht.", [
        ("TOOL-66", "Datenschutz-/Einwilligungs-/Sichtbarkeitsentscheidungen", 0.5, "erledigt: `docs/datenschutz.md`"),
        ("TOOL-2", "Repo, Python-Projekt, README", 0.5, "erledigt"),
        ("TOOL-4", "Verzeichnis-/Sessionstruktur (Narrata-Schlüssel)", 0.5, "erledigt: `src/transcript/session.py`, Layout im README"),
        ("TOOL-5", "Dateiregeln, Rohaudio bleibt lokal", 0.5, "erledigt: `.gitignore`, `tests/fixtures/`, Dateiregeln im README"),
        ("TOOL-6", "Basiskonfiguration", 0.5, "erledigt: `src/transcript/config.py`, `config/example.yaml`"),
        ("IOA-1216", "Privacy-/Sichtbarkeitsmodell, Opt-in-Flag", 1.5, "erledigt: ios-archiv PR #1121; Narrata-Seite von TOOL-66; Anforderungen in `docs/datenschutz.md`"),
        ("IOA-1214", "Contract v1: Schema, Fixture, Validator", 1.0, "erledigt: ios-archiv PR #1128, `transcript:validate`; Fixture dient IOA-1218, bis TOOL-58 liefert; aus TOOL-5: die Kopie der Contract-Fixture liegt im Pipeline-Repo unter `tests/fixtures/`"),
    ]),
    ("Phase 1 — ASR-Spike und Backend-Entscheidung",
     "M1 — Backend gewählt, Diarisierung entschieden, TOOL-11/33 entschieden, Export-Endpoint live. Reflexionspunkt: Epic TOOL-8 wird hier dimensioniert.", [
        ("TOOL-62", "ASR-Kandidaten an realer Session (inkl. Hand-Check, Long-Audio-Frage)", 3.0, "erledigt: `docs/spikes/TOOL-62-asr-vergleich.md`; Whisper large-v3-turbo, Fallback Parakeet, keine eigene Segmentierung; vor IOA-1216/IOA-1214 vorgezogen (02.–04.11.2026)"),
        ("TOOL-20", "Diarisierung / Label-Stabilität", 2.0, "erledigt: `docs/spikes/TOOL-20-diarisierung.md`; separate Diarisierung mit pyannote community-1, 4 stabile Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; NeMo braucht auf 5 h über 25 GB RAM; Integration in TOOL-76"),
        ("IOA-1215", "Transcription-context Export-Endpoint", 2.0, "erledigt: ios-archiv PR #1124; gelesen von `transcript context` (TOOL-67)"),
        ("IOA-1217", "asr_variants-Alias-Kategorie", 1.5, "erledigt: ios-archiv PR #1129; `asr_variants` und `asr_ambiguities` ab Contract 1.1, keine Hörfehler an Ereignissen; Import-Command für Vorschlagsdateien (Format aus TOOL-80) an IOA-1285"),
    ]),
    ("Phase 2 — Pipeline-Kern bis Referenztranskription",
     "M2 — Eine Session läuft vom MP4 bis zur Referenztranskription mit Sprecher-Labels und Wissens-Snapshot.", [
        ("TOOL-9", "ffmpeg/ffprobe-Preflight", 0.5, "erledigt: `src/transcript/audio_tools.py`, `transcript doctor`"),
        ("TOOL-10", "Formate erkennen, Audiospur extrahieren", 1.0, "erledigt: `src/transcript/audio.py`, `transcript extract`"),
        ("TOOL-12", "Session-Manifest, absolute Zeiten", 1.0, "erledigt: `src/transcript/manifest.py`, `transcript manifest`; Teilaufnahmen einer Sitzung sind die Segmente"),
        ("TOOL-63", "Backend-Schnittstelle, Capabilities, Fake-Backend", 1.0, "erledigt: `src/transcript/asr/`, `docs/asr-backends.md`; AK „V0.1-Backend implementiert die Schnittstelle“ an TOOL-64 übergeben"),
        ("TOOL-16", "Internes Referenztranskript-Format", 1.0, "erledigt: `src/transcript/reference.py`, `docs/referenzformat.md`; eine Datei pro Segment unter `work/<session>/asr/`, Rohform getrennt"),
        ("TOOL-64", "Lokales V0.1-Backend", 2.0, "erledigt: `src/transcript/asr/whisper.py`, README „Spracherkennung“; `scripts/spike/` entfernt, Runner im Stand `2f5b875`"),
        ("TOOL-76", "Diarisierung mit pyannote integrieren", 1.5, "erledigt: `src/transcript/diarization/`, `transcript diarize`, README „Diarisierung“; Labels pro Segment, Rohform unter `work/<session>/diarization/`; pyannote-Telemetrie per `transcript/__init__.py` abgeschaltet"),
        ("TOOL-15", "Einzelsegment transkribieren", 0.5, "erledigt: `src/transcript/transcription.py`, `transcript transcribe --segment N`, README „Spracherkennung“; ein Fehlschlag ersetzt nie ein erfolgreiches Ergebnis"),
        ("TOOL-17", "Ganze Session, Resume", 1.0, "erledigt: `transcription.transcribe_session`, `transcript transcribe <session>` mit Wiederaufnahme und Diarisierung, README „Lauf“"),
        ("TOOL-18", "Fehlerkategorien, Retry, Force", 1.0, "erledigt: `src/transcript/retry.py`, `asr.retries`/`diarization.retries`, README „Lauf“; Diarisierung markiert Segmente `failed` statt abzubrechen"),
        ("TOOL-19", "Absolute Zeitstempel im Format", 0.5, "erledigt: `src/transcript/session_time.py`, `docs/referenzformat.md` „Session-Zeit“; Spannen mit Granularität, Zeiten bis 1 s hinter dem WAV-Ende als `clamped` begrenzt"),
        ("TOOL-67", "Narrata-Kanal + Datei-Fallback", 1.0, "erledigt: `transcript context` (`src/transcript/narrata.py`, `src/transcript/narrata_client.py`), README „Narrata-Kontext“; Contract 1.x, Token aus `.env`, `--from-file` als Datei-Fallback"),
        ("TOOL-38", "Teilnehmerwissen", 0.5, "erledigt: `narrata.read_participants`, README „Narrata-Kontext“; `store_context` prüft `participants`; Anwesenheit unbekannt bis IOA-1271/TOOL-79"),
        ("TOOL-39", "Glossarbegriffe", 0.5, "erledigt: `narrata.read_glossary`, `src/transcript/glossary.py` (`GlossaryIndex`, `keyword_terms`), README „Narrata-Kontext“ / „Glossar“; `store_context` prüft Glossar, Archiv-Kappung und `asr_ambiguities`; Mehrdeutigkeiten werden ausgewiesen, nie aufgelöst"),
        ("TOOL-41", "Relevanzregel + Snapshot", 1.0, "erledigt: `src/transcript/knowledge.py`, `transcript snapshot`, README „Wissens-Snapshot“; Relevanzstufe kommt aus Narrata, lokal nur Keyword-Auswahl und `knowledge.keyword_budget`; `asr.knowledge_snapshot_id` im Referenzformat v2 und in der Wiederverwendungsregel; `n`/`archive_limit` konfigurierbar; `num_speakers` an TOOL-79"),
        ("TOOL-42", "Validator + Diagnose", 0.5, "erledigt: `src/transcript/diagnosis.py`, `transcript snapshot` schreibt `narrata/diagnosis.json`, README „Diagnose“; technische Fehler bleiben in den Parsern, Querbezüge (geteilte Begriffe, Hörfehler, Spielfiguren gegen `pc`) sind Warnungen ohne Namen"),
        ("TOOL-43", "Wissensschnittstelle", 1.0, "erledigt: `src/transcript/domain.py` (`DomainContext`), README „Wissensschnittstelle“; `transcribe` übergibt die Snapshot-Keywords, die Wiederverwendungsregel prüft `keywords_used` als geordnete Teilfolge der aktuellen Keywords"),
        ("TOOL-44", "Keyword-Biasing + Review-Signal", 1.0, "erledigt: `src/transcript/hints.py`, README „Review-Hinweise“; Hotwords nur für Turbo-Modelle, `transcribe` meldet die Zahl der übergebenen Keywords; pro Segment `review/segment-NN.hints.json` mit `known_variant` (stark) und `similar` (schwach), Mehrdeutiges als `ambiguous`, ASR-Text unverändert"),
        ("TOOL-40", "Fehlvarianten (leer-lauffähig) + Vorschlagsliste", 0.5, "erledigt: Tests in `tests/test_hints.py`, README „Review-Hinweise“ / „Hörfehler aus Narrata“; ein Hörfehler gilt für seinen Eintrag, Contract 1.1 liefert keinen Kontext pro Variante; Vorschlagsliste an TOOL-80"),
    ]),
    ("Phase 3 — Review, Sprecherzuordnung, Export",
     "M3 — JSON-Export (Contract v1) einer Session importiert lokal in Narrata und rendert dort als Rohliste.", [
        ("TOOL-35", "Konfidenz-/Unsicherheitsregeln kalibrieren", 1.5, "erledigt: `transcript assess`/`calibrate`, Bericht `docs/spikes/TOOL-35-kalibrierung.md` (85 % der Fehler in 46 % der Session-Zeit); Folge-Tickets außerhalb der Roadmap: TOOL-81 (Hotwords verschlucken Wörter), TOOL-82 (Parakeet-Zweitlauf), TOOL-83 (`similar` nach Relevanz-Stufe, erledigt: keine Archiv-Regel, Abschnitt im Bericht)"),
        ("TOOL-36", "Review-Kandidaten", 1.0, "erledigt: `src/transcript/candidates.py`, `review/candidates.json`, README „Review-Kandidaten“; Kandidat = Stufe `needs_review`/`uncertain`, `uncertain` und starke Hinweise zuerst; Signal „überlappende Segmenttranskriptionen“ gestrichen (keine Segmentierung seit TOOL-62); erster Lauf an einer realen Session: 252 Kandidaten pro Stunde Audio"),
        ("TOOL-46", "Review-Datenmodell", 0.5, "erledigt: `src/transcript/decisions.py`, `review/decisions.json`, README „Review-Entscheidungen“; Entscheidungen getrennt von den Kandidaten, sechs Status, Zieltext nur bei `corrected`, veraltete und verwaiste Entscheidungen werden gemeldet, nie angewendet; Hinweise aus TOOL-44 kommen über `candidates.json`"),
        ("TOOL-47", "Review-CSV", 0.5, "erledigt: `transcript review-export`, `src/transcript/review_sheet.py`, `review/review.csv`, README „Review-CSV“; `;`, UTF-8 mit BOM für deutsches Excel; Standard `open`/`deferred`, `--all` alle; chronologisch, Spalte `order` für die Review-Reihenfolge; veraltete Entscheidungen in `earlier_decision`, verwaiste per ID auf der Konsole; vorhandene CSV nur mit `--force` ersetzt"),
        ("TOOL-48", "CSV-Reimport", 0.5, "erledigt: `transcript review-import`, `src/transcript/review_import.py`, README „Review-Import“; gültige Zeilen übernommen, fehlerhafte mit Zeile/ID/Feld gemeldet (Exit 2); fehlende Spalte oder doppelte ID lehnt die Tabelle ab; unveränderte Zeilen sind keine Entscheidung, Reimport idempotent; `version` nur bei geänderten Zeilen geprüft; CSV-Leser geteilt in `src/transcript/sheetfile.py`"),
        ("TOOL-80", "Vorschlagsdatei neuer Hörfehler", 0.5, "erledigt: `src/transcript/variant_suggestions.py`, README „Hörfehler-Vorschläge“; `transcript review-import` schreibt `review/asr-variant-suggestions.json` (`format_version: 1`) aus geltenden `corrected`-Entscheidungen, Ersetzungen bis 4 Wörter auf Glossar-Begriffe, Mehrdeutiges nie aufgelöst, ohne Zeitstempel reproduzierbar; Import-Command in Narrata an IOA-1285"),
        ("TOOL-68", "Sprecherzuordnung manuell", 1.0, "erledigt: `src/transcript/speakers.py`, `transcript speakers`, README „Sprecherzuordnung“; Zuordnung von Hand in `speakers/assignment.json` (`format_version: 1`) pro Segment und Label, Kandidaten aus dem Snapshot, Hörliste `speakers/samples.md`; unbekannte Segmente, Labels und Personen sowie veraltete Einträge werden gemeldet, nie angewendet"),
        ("TOOL-49", "Arbeitsfassung", 1.0, "erledigt: `src/transcript/working.py`, `transcript working`, README „Arbeitsfassung“; `work/<s>/working/transcript.json` (`format_version: 1`), ein Block pro Passage mit `origin` (`automatic`/`decided`/`open`), unverändertem `asr_text`, Ergebnistext (`null` bei `unintelligible`) und Label plus Person; veraltete und verwaiste Entscheidungen, nicht anwendbare Sprecher-Einträge und fehlende Segmente als `findings` (Exit 1), nie angewendet; ohne Zeitstempel, `inputs` mit Versionen und Datei-Hashes, gleiche Eingaben byte-gleich"),
        ("TOOL-50", "Markierungskonvention", 0.5, "erledigt: `src/transcript/markers.py`, README „Markierungen“; aus jedem Block der Arbeitsfassung abgeleitet, nicht gespeichert: `unintelligible` (`[unverständlich HH:MM:SS]`, ohne Text), `unresolved` (Text plus `[unklar …]`), `speaker_unclear` (`unknown`), `crosstalk` (`multiple`); Zeit = Sitzungszeit des Blockanfangs, auf Sekunden abgerundet, ohne Startzeit keine Zeit; Sprecher `open` und `label: null` unmarkiert"),
        ("TOOL-53", "Abschlussbericht", 0.5, "erledigt: `src/transcript/report.py`, `transcript report`, README „Abschlussbericht“; `output/<s>/report.json` (`format_version: 1`) und `report.md` aus der gespeicherten Arbeitsfassung, die aktuell sein muss (`working.load_current`); Passagen je `origin`, Kandidaten je Stufe und Status, Kandidaten pro Stunde, Markierungen, Labels pro Segment mit Redezeit, Personen nur als Anzahl, `effort_minutes`; ASR, Diarisierung, Schwellenwerte und Snapshot mit ihren Segmenten; `gaps` (Exit 1) und `notes`; keine Genauigkeitsangabe, kein Text, keine Namen oder User-IDs"),
        ("TOOL-69", "JSON-Export Contract v1", 1.0, "erledigt: `src/transcript/export.py`, `src/transcript/contract.py`, `transcript export`, README „JSON-Export“; `output/<s>/transcript.json` nach Contract 1.0, vor dem Schreiben gegen die Schema-Kopie (`jsonschema`) und die Regeln jenseits des Schemas geprüft; Labels sessionweit `s01-SPEAKER_00`, ohne Label `unlabelled`; Passagen-ID aus Sitzungsstart und Label, über Review stabil; verweigert Passagen ohne Zeit, mehrere Aufnahmen (Contract 1.1 aus IOA-1287, Export in TOOL-89) und nicht ganzzahlige IDs; `review_note` `null`, `knowledge_hints` `[]`; Gegenprobe mit `transcript:validate`/`transcript:import` steht aus (lokale Narrata-Umgebung fehlte)"),
        ("TOOL-51", "TXT-Rendering", 0.5, "erledigt: `src/transcript/rendering.py`, `transcript txt`, README „TXT-Ausgabe“; `output/<s>/transcript.txt` nur aus `transcript.json` (vorher gegen die Schema-Kopie geprüft), ein Absatz je Sprecherwechsel, `render.timestamps` `turn`/`passage`, Marker aus dem Contract inkl. `gap` (`markers.contract_marker_label`), byte-gleich bei erneutem Lauf"),
        ("TOOL-52", "DOCX-Rendering", 0.5, "erledigt: `src/transcript/docx_render.py`, `transcript docx`, README „DOCX-Ausgabe“; `output/<s>/transcript.docx` nur aus `transcript.json`, Marker aus dem Contract, gleiche Regel `render.timestamps` wie TXT"),
        ("IOA-1218", "Storage + idempotenter Import", 2.0, "erledigt: `transcript:import` und Upload-Endpoint in Narrata (ios-archiv PR #1138), gegen die IOA-1214-Fixture; die Probe gegen einen echten TOOL-69-Export folgt mit TOOL-58"),
        ("IOA-1287", "Contract 1.1: mehrere Aufnahmen in `source`", 1.0, "erledigt: optionales `source.recordings[]` (`file_name`, `duration_seconds`, `audio_sha256`, `starts_at`) in Sitzungsreihenfolge, `recordings[0]` gleich den Top-Level-Feldern; 1.0-Dateien bleiben gültig, Referenz-Fixture `session-v1-multi.json`; Pipeline-Seite in TOOL-89"),
    ]),
    ("Phase 4 — End-to-End-Pilot",
     "M4 — Pilot-Review (TOOL-60): Kernhypothese geprüft; Entscheidungen Review-Kanal, Remote-Backend, Freigabe IT/OT. Zweiter großer Reflexionspunkt. Danach die Pipeline-Nacharbeit aus dem V0.2-Backlog von TOOL-60, vor den Reflexionspunkten M7 und M8.", [
        ("TOOL-56", "Preflight", 0.5, "erledigt: `src/transcript/preflight.py`, `transcript doctor`; prüft Werkzeuge, Konfiguration, Modelle sowie Eingabe, Wissen und Artefakte einer Sitzung; aus TOOL-9: `transcript doctor` war der Ausgangspunkt"),
        ("TOOL-55", "E2E-CLI mit Halt an manuellen Schritten", 1.0, "erledigt: `transcript process` (`src/transcript/pipeline.py`), Halt an manuellen Schritten, Exit-Codes 0/1/2/3; aus TOOL-10: `transcript extract` ist der erste Schritt des E2E-Befehls; aus TOOL-56: der E2E-Befehl ruft `preflight.run` vor dem ersten Schritt auf und bricht bei Fehlern ab"),
        ("TOOL-57", "Pipeline-Status + Resume, Fehlversuche dauerhaft protokollieren", 1.5, "erledigt: `transcript status` (`src/transcript/status.py`) leitet Gesamt- und Schrittstatus nur aus den Dateien ab, ohne Statusdatei; `process` stoppt bei Modell-, Snapshot-, Keyword- oder Sprachwechsel bis `--redo`, Lock `work/<s>/process.lock` gegen parallele Läufe (`src/transcript/lock.py`); TOOL-77 aufgenommen: Schrittwechsel und Fehlversuche in `work/<s>/pipeline.log`; aus TOOL-56: baut auf dem `resume`-Check auf; aus TOOL-55: baut auf `pipeline.STEPS` und `StepResult` auf"),
        ("TOOL-86", "Sprecherzuordnung interaktiv (`transcript speakers --assign`)", 1.0, "erledigt: `src/transcript/speaker_assign.py`; vor TOOL-58, damit der Pilot den Zuordnungsaufwand mit dem Alltagsweg misst; offen: Namen nur im interaktiven TTY (TOOL-66), Schreibregel für die handgemachte `assignment.json` (TOOL-68)"),
        ("TOOL-89", "Sitzungen mit mehreren Aufnahmen gegen Contract 1.1 exportieren", 0.5, "erledigt: `export._source`, README „JSON-Export“; mehrere Aufnahmen → `contract_version` `1.1` mit `source.recordings[]` (aufeinanderfolgende Segmente derselben Datei, `starts_at` auf der Session-Zeitachse), eine Aufnahme bleibt 1.0 und byte-gleich; Schema-Kopie aus ios-archiv `e8bfb9702`, Fixture `session-v1-multi.json`, die vier Recording-Regeln in `contract.validate`; Preflight-Warnung entfällt, `process` hält nicht mehr an `export`; Gegenprobe mit `transcript:validate` in TOOL-58"),
        ("TOOL-58", "Erste reale Session komplett (inkl. Review- und Zuordnungszeit)", 2.0, "erledigt: `docs/pilot/TOOL-58-erste-session.md`; 5:26 h in knapp 7 min, Zuordnung 4 min; Export (Contract 1.1, zwei Aufnahmen) besteht `transcript:validate` und wird ohne Korrektur und idempotent importiert; WER 24–33 %, 87 % der Passagen Kandidaten ohne Fehlalarm, ein vollständiges Review läge bei rund 25 h pro Abend"),
        ("TOOL-94", "Preflight prüft das Laden der CUDA-Bibliotheken für faster-whisper", 0.5, "erledigt: `whisper.missing_cuda_library`, `transcript doctor` meldet ein nicht ladbares `libcublas.so.12` auf `cuda` als Fehler, auch bei `auto`; `WhisperBackend.load` bricht vor dem Modell ab; aus TOOL-58: der Preflight meldete die ASR als `ok`, die Segmente scheiterten erst nach rund 6 min an fehlendem `LD_LIBRARY_PATH`"),
        ("TOOL-91", "Hörproben bei der Sprecherzuordnung entrauscht abspielen", 0.5, "erledigt: `playback.filter`, Standard `false`, weil die Proben roh am besten klangen (Pausenpegel rund −55 dBFS); `highpass=f=80,afftdn=nf=-25` als Vorschlag für verrauschte Aufnahmen; ffmpeg prüft die Kette einmal pro Lauf, da ffplay bei einem kaputten Filter mit Exit 0 stumm bleibt; Hörprobe im Pilotbericht TOOL-58"),
        ("TOOL-59", "Laufzeit/Ressourcen/Aufwand auswerten", 0.5, "erledigt: `docs/pilot/TOOL-59-auswertung.md`; voller Neulauf ASR + Diarisierung rund 12 min für 5:26 h (27-fache Echtzeit), Peak-RAM 13,9 GiB (ASR) / 12,0 GiB (Diarisierung), Peak-VRAM rund 2,5 GiB; pro Stunde Audio rund 2 min Rechenzeit, 0,7 min Zuordnung, 4,6 h vollständiges Review; `report.json` `format_version: 2` mit `runtime` (ASR- und Diarisierungszeit je Segment), Diarisierungs-Rohdatei mit `elapsed_ms`; TOOL-78 verworfen"),
        ("TOOL-61", "E2E-Workflow dokumentieren", 0.5, "erledigt: `docs/ablauf.md` (Ablauf von Setup bis Narrata-Import, manuelle Schritte, Resume, Snapshot, Artefakte, Pilot-Fehler); Startskript `scripts/transcript` setzt `LD_LIBRARY_PATH` für cuBLAS und läuft ohne aktivierte venv; `nvidia-cudnn-cu12` aus dem Whisper-Extra entfernt (Smoke-Tests auf `cuda` nur mit cuBLAS grün); Abspielen im Review über `ffplay` und `segment_start` dokumentiert; Folge: TOOL-95 (CLI ohne Startskript)"),
        ("TOOL-92", "Spike: Entrauschen vor der Erkennung messen", 1.0, "erledigt: `docs/spikes/TOOL-92-entrauschen.md`; No-Go, `afftdn`, RNNoise und DeepFilterNet verschlechtern die WER an A um 2–9 Punkte und lassen mehr Wörter ohne Label; nur `highpass=f=80` schadet nirgends, überlappt aber mit der Streuung; Whisper streut auf demselben WAV um bis zu 13 Punkte (Temperatur-Fallback), deshalb 3 Läufe pro Kandidat"),
        ("TOOL-93", "Spike: Erkennungsqualität an den Pilot-Handreferenzen verbessern", 1.5, "erledigt: `docs/spikes/TOOL-93-erkennungsqualitaet.md`; No-Go, large-v3-turbo mit Hotwords bleibt; keine VAD-/Dekodier-Einstellung und kein lokales Modell bringt ≥ 3 Punkte; Auslassungen sind zu 85–90 % Inhaltswörter; Empfehlung: Aufnahme am Tisch verbessern"),
        ("TOOL-96", "Passagen am Sprecherwechsel teilen", 1.5, "erledigt: `src/transcript/diarization/turns.py`, `docs/spikes/TOOL-96-sprecherwechsel.md`; `transcript diarize` teilt Passagen am Sprecherwechsel (`diarization.min_turn_ms`, 500 ms), Referenzformat v3 mit `asr_passage` und `processing.renumbered`; Sprecherfehler an der Pilotsitzung 17,4 % → 6,2 % (A) und 14,0 % → 3,6 % (B), 3,4 / 3,6 Punkte über Plaud, daher kein Diarisierungs-Ticket (TOOL-97 geschlossen); 2.166 statt 997 Passagen, Kandidaten 65,7 % statt 87,3 %; Passagen-IDs aus der Backend-Passage, Re-Import in Narrata ohne `--replace` (0 entfernt); Review-Entscheidungen folgen ihrer Passage (26 von 35 gelten weiter); Arbeitsfassung `format_version: 2`"),
        ("TOOL-95", "CLI ohne Startskript: cuBLAS vorladen, `paths.root` verankern", 0.5, "erledigt: `whisper.preload_cuda_libraries` lädt `libcublas.so.12` aus `nvidia-cublas-cu12` per absolutem Pfad mit `RTLD_GLOBAL` vor (Fallback: System-Bibliothek), `doctor` und Whisper-Smoke-Test auf `cuda` grün ohne `LD_LIBRARY_PATH`; relativer `paths.root`, Default-Config und `.env` gelten ab dem Projektordner, Argumente wie `--config` weiter ab dem aktuellen Verzeichnis; `scripts/transcript` entfernt, Aufruf direkt über `.venv/bin/transcript`"),
        ("TOOL-60", "V0.1 bewerten, Entscheidungen, V0.2-Backlog", 1.0, "erledigt: `docs/pilot/TOOL-60-bewertung.md`; Kernhypothese hält als Rangfolge (AUC 0,75–0,78 an zwei Sitzungen), nicht als Eingrenzung (74–89 % der Hörzeit markiert, 5–16 % der Fehler in sicheren Passagen); WER Pilot 21–26 %, zweite Sitzung 31,5 % gegen eine Hochdeutsch-Referenz; Review mit Anhören wandert nach Narrata (IOA-1326), CSV eingefroren, kein Pflicht-Review in der Pipeline; Go für IT/OT (IOA-1302); Mikrofon-Empfehlung nur dokumentiert; TOOL-14 verworfen; Archiv-Schreibtreffer 2 von 18 richtig (TOOL-99); Mundartsprecher an zwei Abenden etwa doppelte Fehlerquote, Gewichtung pro Person in IOA-1326; Re-Import-Warnung bei abhängigen Links (IOA-1327); TOOL-82 zurückgestellt"),
        ("TOOL-81", "Hotwords: Auslassungen und Seed-Streuung auf langen Aufnahmen", 1.0, "erledigt: `docs/spikes/TOOL-81-hotwords.md`; Ursache: zu kurze Hotword-Liste (9 Begriffe, 51 Tokens: 14 % fehlende Wörter); unter 110 Hotword-Tokens gehen keine Hotwords an Whisper, volle Liste bleibt Default; Schalter `asr.hotwords`, Vorab-Check `transcript keywords`; Biasing bleibt, TOOL-90 kann starten"),
        ("TOOL-99", "Archiv-Schreibtreffer heben keine Passage an", 0.5, "erledigt: `docs/plans/TOOL-99-archive-similar.md`; aus TOOL-60: 2 von 18 Archiv-Schreibtreffern richtig; eigene Schwelle `similar_archive_level`, Hinweis bleibt sichtbar"),
        ("TOOL-90", "Kontext 1.4: `session_terms` ins Biasing und in die Review-Zuordnung", 0.5, "erledigt: `docs/plans/TOOL-90-session-terms.md`; `session_terms` im Snapshot, im Biasing und als Review-Hinweis"),
        ("TOOL-84", "Kontext mit dem Pipeline-Token statt dem Login-Token abrufen", 0.5, "erledigt: `docs/plans/TOOL-84-pipeline-token.md`; IOA-1251 erledigt; ein Token pro Runde (`NARRATA_TOKEN_<SLUG>`), 90 Tage, nur dieser Endpoint; Import bleibt beim Login-Token"),
        ("TOOL-79", "Anwesenheit aus dem Transkriptionskontext lesen", 0.5, "erledigt: `docs/plans/TOOL-79-attendance.md`; IOA-1271 erledigt (Kontext 1.3); Anwesende zuerst in der Sprecherzuordnung (Abwesende fragen nach), `max_speakers` aus dem Snapshot für die Diarisierung; vor TOOL-87"),
    ]),
    ("Phase 5 — Narrata-Oberflächen",
     "M5 — Transkript per Chat/MCP befragbar, in Narrata durchsuchbar, lesbar, verlinkt.", [
        ("IOA-1220", "Volltextsuche", 1.5, "erledigt, vor Phase 4 vorgezogen; Voraussetzung für IOA-1223"),
        ("IOA-1223", "Chat + MCP", 1.5, "erledigt, vor Phase 4 vorgezogen; Kernziel: der KI-Assistent antwortet der Spielleitung aus dem Transkript"),
        ("IOA-1219", "Lese-UI am Session-Detail", 3.0, "erledigt, vor Phase 4 vorgezogen"),
        ("IOA-1221", "Passage-Links", 2.0, "erledigt, vor Phase 4 vorgezogen"),
    ]),
    ("Phase 6 — Extraktion und Analytik in Narrata",
     "M6 — Erste Welt-Archiv-Einträge mit Transkript-Provenienz; IT/OT-Statistik und Abendvergleich sichtbar.", [
        ("IOA-1222", "Transkript als Extraktionsquelle, polymorphe Provenienz", 3.0, "erledigt, vor Phase 4 vorgezogen; größte Migration des Epics"),
        ("IOA-1224", "IT/OT-Flächen + Statistik", 2.0, "erledigt, vor Phase 4 vorgezogen (Anzeige; die Einstufung selbst kommt aus Epic IOA-1297)"),
    ]),
    ("Phase 7 — Öffnung für andere Nutzer",
     "M7 — Entscheidung, ob und wie andere Narrata-Nutzer ihre Aufnahmen transkribieren können. Reflexionspunkt, kein Umsetzungsblock.", [
        ("TOOL-85", "Entscheidung: Transkription für andere Narrata-Nutzer öffnen?", 0.5, "erledigt: `docs/pilot/TOOL-85-oeffnung.md`; nichts tun, die Pipeline bleibt das Werkzeug der eigenen Gruppe; keine Nachfrage, andere Gruppen nutzen den Fremdformat-Upload (IOA-1304, IOA-1306); lokal rechnen (Weg 1) bleibt erste Wahl bei einer konkreten Anfrage; eigener Worker und externer ASR-Dienst verworfen; Modellwahl auf Gruppenebene entfällt; keine Folge-Tickets"),
    ]),
    ("Phase 8 — Sprecher-Wiedererkennung",
     "M8 — Konzept für Stimmprofile mit Einwilligung pro Spielrunde, Go/No-Go. Reflexionspunkt, kein Umsetzungsblock.", [
        ("TOOL-87", "Konzept: Sprecher über Sessions hinweg wiedererkennen", 1.0, "erledigt: `docs/pilot/TOOL-87-stimmprofile.md`; Ergebnis No-Go, keine Umsetzungstickets; Stimmprofil wäre ein biometrisches Datum (Art. 9 DSGVO) mit Opt-in pro Mitgliedschaft, Neuprüfung erst beim Kriterium aus der Notiz"),
    ]),
    ("Phase 9 — Auslassungen verringern",
     "M9 — Auslassungen verortet und die offenen Hebel gemessen (Epic TOOL-100). Reflexionspunkt: Welcher Hebel bekommt ein Umsetzungsticket?", [
        ("TOOL-101", "Spike: Auslassungen an den Handreferenzen verorten", 1.0, "zuerst, entscheidet die Reihenfolge der übrigen Tickets des Epics und den Zuschnitt von TOOL-82; Überlappung, Beitragslänge, Pegel je Sprecher, Temperatur-Fallback, VAD, Stabilität über die Seeds, Sprache ohne Wörter; Erweiterung von `scripts/spike/asr.py`, nur Kennzahlen"),
        ("TOOL-102", "Spike: Vereinigung mehrerer Seeds gegen Auslassungen messen", 1.0, "Orakel an A, B und C, danach Regeln ohne Referenz nur bei ≥ 3 Punkten; Läufe aus TOOL-93 wiederverwendbar, wenn die Schattenwurzeln noch liegen; Wörter aus einem anderen Lauf sind Alternativen, das ASR-Ergebnis bleibt"),
        ("TOOL-103", "Spike: Pegelausgleich vor der Erkennung messen", 1.0, "`dynaudnorm`, `acompressor`, `loudnorm`, `speechnorm` auf dem Prüfstand aus TOOL-92 (`scripts/spike/denoise.py`), drei Seeds, Go-Regel wie TOOL-92; TOOL-92 hat nur Rauschfilter gemessen"),
        ("TOOL-104", "Recherche: sprecherbedingte Dekodierung, neue lokale Modelle, Batched-Pipeline", 1.0, "nach TOOL-101; höchstens drei Kandidaten für eine Messung; Batched-Pipeline von faster-whisper direkt an A und B messen, falls sie Hotwords trägt; nur lokal lauffähige Ansätze"),
        ("TOOL-105", "Messung: Sitzung mit geänderter Aufnahme am Tisch gegen eine Handreferenz", 0.5, "braucht die Gruppe, Hardware und einen Spielabend, das Datum ist deshalb nur ein Platzhalter; wenn möglich mit dem bisherigen Mikrofon parallel aufnehmen; Handreferenz von der Projektverantwortlichen (20–30 min); aus TOOL-60 und TOOL-93: Mikrofon-Empfehlung bisher nur dokumentiert"),
    ]),
]

CONDITIONAL: set[str] = set()


def workday_calendar(limit: int) -> list[dt.date]:
    """The first `limit` working dates from FROM on: WORKDAYS of each week, skipping PAUSES."""
    out: list[dt.date] = []
    week = 0
    while len(out) < limit:
        for slot in WORKDAYS:
            d = START + dt.timedelta(days=7 * week + slot)
            if d < FROM or any(a <= d <= b for a, b in PAUSES):
                continue
            out.append(d)
        week += 1
    return out[:limit]


def de(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def is_done(note: str) -> bool:
    """A ticket is done when its note starts with "erledigt"; done tickets take no days."""
    return note.startswith("erledigt")


def main() -> None:
    total = sum(days for _, _, items in P for _, _, days, note in items if not is_done(note))
    done_days = sum(days for _, _, items in P for _, _, days, note in items if is_done(note))
    cal = workday_calendar(math.ceil(total) + 1)
    cum = 0.0
    rows, phases = [], []
    for ptitle, milestone, items in P:
        pstart = cum
        for key, title, days, note in items:
            if is_done(note):
                rows.append(dict(key=key, title=title, days=days, note=note, phase=ptitle,
                                 start=None, end=None))
                continue
            s, e = cum, cum + days
            rows.append(dict(key=key, title=title, days=days, note=note, phase=ptitle,
                             start=cal[math.floor(s)], end=cal[math.ceil(e) - 1]))
            cum = e
        open_ = cum > pstart
        phases.append(dict(title=ptitle, milestone=milestone,
                           days=sum(d for _, _, d, _ in items),
                           start=cal[math.floor(pstart)] if open_ else None,
                           end=cal[math.ceil(cum) - 1] if open_ else None))

    cond_days = sum(r["days"] for r in rows if r["key"] in CONDITIONAL)
    ends = [p["end"] for p in phases if p["end"] is not None]
    last = max(ends) if ends else None
    weeks = (last - FROM).days // 7 + 1 if last else 0
    pauses = ", ".join(f"{de(a)}–{de(b)}" for a, b in PAUSES)

    o = []
    o.append("# Transkript-Projekt — Roadmap (TOOL + IOA-1213)\n")
    o.append(f"Stand {GENERATED}, generiert von `transcript-roadmap.py` (Reihenfolge und Aufwände stehen dort). Verbindliche Reihenfolge und Meilensteine für das gesamte Transkript-Vorhaben: die lokale Pipeline (Jira-Projekt **TOOL**, eigenes Python-Repo) und ihr Narrata-Gegenstück (Epic **IOA-1213**). Jira-Gesamtsicht: `project in (TOOL, IOA) AND labels = transcript`.\n")
    o.append("## Annahmen\n")
    o.append("- **Eine Person, ein Zeitbudget.** TOOL- und IOA-Tickets konkurrieren um dieselben Tage; der Plan ist deshalb eine *lineare* Folge. Echte Parallelität gibt es nur dort, wo ASR-Läufe oder Modell-Downloads im Hintergrund laufen — dann wird am Narrata-Ticket derselben Phase gearbeitet.")
    o.append(f"- **Kapazität: {len(WORKDAYS)} Entwicklungstage pro Woche**, Start {de(FROM)}, Pause {pauses}. Das ist der Umrechnungsfaktor für die Kalenderspalte, nicht Teil des Plans — ändert sich die Kapazität, verschieben sich nur die Daten, nicht die Reihenfolge.")
    o.append("- **Aufwände sind Entwicklungstage in 0,5er-Schritten**, grob geschätzt aus den Ticket-Beschreibungen. Sie dienen der Reihenfolge und den Meilenstein-Abständen; keine Zusage.")
    o.append(f"- **Offener Umfang: {total:g} Entwicklungstage** ≈ {weeks} Wochen → letzter Meilenstein {de(last) if last else 'keiner offen'}; erledigt {done_days:g} Tage." + (f" Davon {cond_days:g} Tage bedingt ({', '.join(sorted(CONDITIONAL))})." if CONDITIONAL else ""))
    o.append("- **Neu terminiert am 17.11.2026, Qualität zuerst, fortgeschrieben am 21.11.2026:** Erledigte Tickets belegen keine Tage mehr und tragen kein Datum; die offenen Tickets beginnen am ersten Arbeitstag ab heute, angeführt von der Erkennungsqualität (TOOL-93, TOOL-96) vor dem Pilot-Review (TOOL-60). Nach dem Backlog-Review vom 21.11.2026 folgt die Pipeline-Nacharbeit aus TOOL-60 (TOOL-81, 99, 90, 84, 79) vor den Reflexionspunkten TOOL-85 und TOOL-87. Die Narrata-Nacharbeit aus Epic IOA-1297 (Korrektur, IT/OT, Lesefassung) steht nicht in dieser Folge und konkurriert um dieselben Tage. Am 22.11.2026 kam Phase 9 dazu (Epic TOOL-100): Die ausgelassenen Wörter sind das größte Qualitätsproblem, die Spikes TOOL-101 bis TOOL-105 folgen auf TOOL-87.")
    o.append("- Nicht eingeplant: die Epics selbst, zurückgestellte Tickets (TOOL-82 bis IOA-1326, Label `transcript-v0.2`), verworfene Tickets (TOOL-14 nach TOOL-60; TOOL-88 nach dem Backlog-Review, Review wandert nach Narrata;TOOL-21–32, 34; TOOL-3, 7; TOOL-11, 33 nach TOOL-62; TOOL-78 nach TOOL-59; Epic TOOL-65 mit TOOL-70–75, IT/OT nach Narrata verlegt in Epic IOA-1297), in andere aufgenommene Tickets (TOOL-77 in TOOL-57).\n")
    o.append("## Leitlinien der Reihenfolge\n")
    o.append("1. **Entscheidungen vor Code.** Datenschutz (TOOL-66/IOA-1216) und Contract (IOA-1214) stehen, bevor irgendetwas Daten schreibt — sonst werden Fixtures, Logs und IDs später umgebaut.")
    o.append("2. **Der ASR-Spike (TOOL-62) läuft vor der Audio-Vorbereitung.** Er entscheidet, ob Epic TOOL-8 drei oder fünf Stories hat. Ergebnis: drei, TOOL-11 und TOOL-33 entfallen.")
    o.append("3. **Narrata-Arbeit füllt die Wartezeiten der Pipeline.** Export-Endpoint und Alias-Kategorie entstehen, während Modelle rechnen; Storage/Import entsteht gegen die Fixture, bevor der echte Export existiert.")
    o.append("4. **Der Pilot (Phase 4) ist ein Tor, kein Schritt.** TOOL-60 entscheidet explizit über Review-Kanal, Remote-Backend und die Freigabe der IT/OT-Arbeit in Narrata. Die Phasen 7–8 werden nach dem Pilot-Review neu terminiert.")
    o.append("5. **Lesen vor Analysieren.** Die Narrata-Oberflächen (Phase 5) kommen vor IT/OT (Narrata-Epic IOA-1297) — ein importiertes Transkript muss erst nutzbar sein, bevor es klassifiziert wird; das Lesen deckt zudem Contract-Lücken auf, bevor eine IT/OT-Schicht sie zementiert.")
    o.append("6. **Das Kernziel kommt zuerst.** Innerhalb von Phase 5 stehen Suche und Chat/MCP (IOA-1220, IOA-1223) vor Lese-UI und Links: Sie hängen nur an IOA-1218 und machen das Transkript für den KI-Assistenten nutzbar.\n")
    o.append("## Meilensteine\n")
    o.append("| # | Meilenstein | Phase | Zeitraum | Tage |")
    o.append("|---|---|---|---|---|")
    for i, p in enumerate(phases):
        short = p["milestone"].split("—", 1)[1].split(".")[0].strip()
        span = f"{de(p['start'])} – {de(p['end'])}" if p["start"] else "erledigt"
        o.append(f"| M{i} | {short} | {p['title'].split('—')[0].strip()} | {span} | {p['days']:g} |")
    o.append("")
    o.append("## Reflexionspunkte\n")
    o.append("| Nach | Frage | Ticket, das entscheidet | Was sich ändert |")
    o.append("|---|---|---|---|")
    o.append("| M1 | Braucht das Backend externe Segmentierung? | TOOL-62 | Beantwortet: nein, TOOL-11 und TOOL-33 verworfen; Phase 2 −2 Tage |")
    o.append("| M1 | Liefert Diarisierung stabile Labels? | TOOL-20 | Beantwortet: ja, pyannote hält 4 Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; TOOL-68 bleibt bei 1 Tag |")
    o.append("| M1 | Liefert das ASR-Backend die Sprecher-Labels selbst? | TOOL-20 | Beantwortet: nein, separate Diarisierung mit pyannote; Integration als TOOL-76 (1,5 Tage) in Phase 2, M2 verschiebt sich entsprechend |")
    o.append("| M3 | Trägt der Contract den Import ohne Rückfragen? | IOA-1218 gegen TOOL-69 | Contract-Minor-Bump vor Phase 4, nicht danach; erster Bump erledigt: 1.1 mit `source.recordings[]` (IOA-1287), Pipeline-Seite TOOL-89 |")
    o.append("| M4 | Trägt die Kernhypothese (Konfidenz grenzt Review ein)? Aufwand pro Abend alltagstauglich? | TOOL-60 | Beantwortet: als Rangfolge ja, als Eingrenzung nein (74–89 % der Hörzeit markiert); Review wandert nach Narrata (IOA-1326), Go für IT/OT (IOA-1302), TOOL-14 verworfen |")
    o.append("| M4 | Reicht das Teilen am Sprecherwechsel, oder braucht die Diarisierung selbst ein Ticket? | TOOL-96 | Beantwortet: reicht, 3,4 / 3,6 Punkte Abstand zu Plaud, kein Diarisierungs-Ticket |")
    o.append("| M6 | Welche Fragen aus der Zielliste sind jetzt beantwortbar, welche nicht? | Retro, kein Ticket | V0.2-Backlog beider Projekte |")
    o.append("| M7 | Öffnen wir die Transkription für andere Nutzer, und auf welchem Weg? | TOOL-85 | Beantwortet: nein, keine Nachfrage und Fremdformat-Upload in Narrata vorhanden; lokal rechnen erst bei konkreter Anfrage, keine Folge-Tickets |")
    o.append("| M8 | Lohnt sich die Wiedererkennung der Sprecher, und trägt die Einwilligung pro Spielrunde? | TOOL-87 | Go/No-Go; bei „ja“ Umsetzungstickets in TOOL und IOA |")
    o.append("| M9 | Wo entstehen die Auslassungen, und welcher Hebel verringert sie oder macht sie sichtbar? | TOOL-101, danach TOOL-102 bis TOOL-105 | Umsetzungsticket je Hebel mit Go; Zuschnitt von TOOL-82 (Parakeet-Zweitlauf); bei No-Go überall bleibt die Aufnahme am Tisch der einzige Hebel |\n")
    o.append("## Arbeitsfolge\n")
    o.append("Start/Ende der offenen Tickets sind in Jira als Start date / Due date gespiegelt; erledigte Tickets behalten in Jira ihre damaligen Daten.\n")
    for p in phases:
        o.append(f"### {p['title']}\n")
        o.append(f"**{p['milestone']}**\n")
        o.append("| Ticket | Inhalt | Tage | Start | Ende | Hinweis |")
        o.append("|---|---|---|---|---|---|")
        for r in rows:
            if r["phase"] == p["title"]:
                start, end = (de(r["start"]), de(r["end"])) if r["start"] else ("—", "—")
                o.append(f"| {r['key']} | {r['title']} | {r['days']:g} | {start} | {end} | {r['note']} |")
        o.append("")
    o.append("## Pflege\n")
    o.append("- `transcript-roadmap.py` ist die Quelle (Reihenfolge, Aufwände, Kapazität, Pausen); diese Datei und die Jira-Daten sind generiert. Ändern → Skript laufen lassen → Jira per `editJiraIssue` (`customfield_10015`, `duedate`) aus der JSON-Ausgabe nachziehen.")
    o.append("- Nach jedem Meilenstein `START`/`FROM`/Aufwände an die Realität anpassen und neu rechnen; nach M4 die Phasen 7–8 bewusst neu terminieren (Pilot-Erkenntnisse).")
    o.append("- Verworfene oder neu geschnittene Tickets im Skript entfernen bzw. ergänzen und den Grund im Jira-Ticket festhalten. Ein fertiges Ticket bekommt einen Hinweis, der mit „erledigt“ beginnt; dann belegt es keine Tage mehr.")

    here = pathlib.Path(__file__).resolve().parent
    (here / "transcript-roadmap.md").write_text("\n".join(o) + "\n", encoding="utf-8")
    for r in rows:
        if r["start"] is None:
            continue
        print(json.dumps({"key": r["key"], "start": r["start"].isoformat(), "end": r["end"].isoformat()}))


if __name__ == "__main__":
    main()
