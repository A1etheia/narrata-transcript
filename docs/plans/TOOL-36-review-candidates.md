# TOOL-36 — Review-Kandidaten aus ASR-Unsicherheit und Domänenwissen

## Ziel
Nach dem Lauf liegt pro Session eine Prüfliste vor: nur Passagen mit Warnsignal, je mit unverändertem Referenztext, Session-Zeit und allen Gründen, die unsichersten zuerst. Heute gibt es Stufen und Hinweise nur verstreut pro Segment und ohne Text (`uncertainty.json`) bzw. ohne Stufe (`hints.json`); TOOL-46/47 hätten nichts Zusammenhängendes zu lesen. Dazu die Kennzahl Kandidaten pro Stunde Audio für TOOL-60.

## Ist-Stand
- `src/transcript/uncertainty.py:91` `assess` bewertet jede Passage; Gründe (`Reason`, `:73`) decken bereits Confidence, Whisper-Signale, Pausen, fehlende Zeiten, Sprecher, Übersprechen und alle Hinweisarten ab. `load_assessment` (`:437`) liest `review/segment-NN.uncertainty.json` mit `reference_processed_at` zur Aktualitätsprüfung.
- `src/transcript/hints.py:78` `Hint` mit `passage`, Wortbereich, `heard`, `signal`, `method`, `candidates`, `ambiguous`; `stored_hints` (`:476`), `SegmentHints.matches` (`:394`).
- `src/transcript/session_time.py:51` `passage_span` liefert Session-Zeit mit `granularity` und `clamped`; `segment_of` (`:40`) prüft Manifest gegen Referenz.
- `src/transcript/reference.py:63` `Passage.text` (nie korrigiert), `speaker`; `load_reference`.
- `src/transcript/session.py:111` `review_dir`; dort fehlt ein Pfad für die Kandidatendatei.
- `src/transcript/__main__.py:704` `_rate_passages` läuft am Ende von `transcribe`, `diarize` und `assess`.
- `src/transcript/config.py:89-91`: `similar_sound_level` Default `confident` → Klang-Hinweise heben nicht an (TOOL-35/83).

## Entscheidungen
- **Neues Modul `src/transcript/candidates.py`**, eine Datei pro Session: `work/<s>/review/candidates.json`. TOOL-46/47 brauchen die Session als Ganzes, und die Kennzahl pro Stunde ist sessionweit.
- **Kandidat = Passage mit Stufe ≠ `confident`.** Die Auswahl trifft allein die TOOL-35-Bewertung; TOOL-36 erfindet keine zweite Regel. Domänenwissen *löst aus*, weil `known_variant`/`ambiguous`/`similar` (Schreibung) die Stufe heben, und *verstärkt*, weil die Hinweise am Kandidaten hängen und die Sortierung bestimmen. Hinweise einer `confident`-Passage (nur Klang) bleiben in `hints.json` sichtbar, erzeugen aber keinen Kandidaten. Eine Option „auch sichere Passagen“ gibt es nicht, bis TOOL-47 sie braucht.
- **Sortierung:** `uncertain` vor `needs_review`; innerhalb der Stufe Passagen mit `known_variant` oder `ambiguous` zuerst (Übergabe TOOL-44); dann Segment und Passage in Aufnahmereihenfolge. Deterministisch.
- **Inhalt pro Kandidat:** stabile `id` (`s01-p0042`), `segment`, `passage`, `level`, `reasons` (wie in `uncertainty.json`, inkl. `value`/`threshold`, also Confidence-Werte), `missing`, `text`, `speaker` (Label, bis TOOL-68 keine Person), `time` (Session-Span aus `passage_span` oder `null`, nie geschätzt), `hints` (die Hinweise der Passage unverändert, mit Kandidaten-Refs aus Narrata).
- **Kopf:** `format_version: 1`, Session, `created_at`, pro Segment die gelesenen `processed_at` von Referenz, Bewertung und Hinweisen samt `knowledge_snapshot_id`, `counts` je Stufe, `audio_ms` der bewerteten Segmente, `per_hour`, und `not_rated` (Segmente ohne Transkript oder fehlgeschlagen), damit die Kennzahl nicht stillschweigend über Lücken gerechnet wird.
- **Aktualität:** Eine Bewertung, deren `reference_processed_at` nicht zur Referenz passt, bricht ab mit `run transcript assess` (keine veralteten Kandidaten). Hinweise werden nur bei `matches` übernommen, sonst fehlen sie, und das steht schon in `missing`.
- **Kein eigener Befehl:** `_rate_passages` schreibt die Kandidatendatei direkt nach der Bewertung neu, auch bei `--segment` (aus allen vorhandenen Segmentdateien). Konsole nur Zahlen: `review candidates: 57 (12.3 per hour of audio)`.
- **Überlappende Segmenttranskriptionen:** gestrichen (Entscheidung 2026-11-08, Kommentar in TOOL-36). Seit TOOL-62 gibt es keine eigene Segmentierung, `overlap_before_ms` ist immer 0, der Fall tritt nicht auf.

## Daten-Check
- TOOL-66: handled — `candidates.json` enthält Text und Archivnamen und liegt nur unter `work/` (gitignored); Konsole und Fehlermeldungen nennen nur Datei, Feld, Segment- und Passagennummer.
- Repo/Fixtures: handled — Tests bauen synthetische Transkripte wie `tests/test_uncertainty.py:46-105`; keine echte Session.
- Logs: handled — das Modul loggt nichts.

## Contract-Check
- N/A, weil die Kandidatendatei internes Zwischenformat ist; der Contract-Export ist TOOL-69. Die Stufennamen sind bereits die von `confidence_tier`, nichts weicht von IOA-1214 ab, Narrata braucht keine Änderung.

## Resume-Check
- N/A, weil kein Modell läuft und der Schritt Sekunden dauert. Die Datei wird bei jedem Lauf atomar (`write_atomic`) vollständig neu geschrieben; ein Abbruch lässt die alte Fassung stehen.

## Format-Check
- handled — neues Format `candidates.json` mit `format_version: 1` und Loader, der andere Versionen ablehnt. Bestehende Artefakte: keine; `uncertainty.json` und `hints.json` bleiben unverändert in v1.

## Chunks
### Chunk 1 — Kandidaten bilden
- Dateien: `src/transcript/candidates.py`, `src/transcript/session.py` (`review_candidates`), `tests/test_candidates.py`
- Änderung: `Candidate`/`SessionCandidates`, `collect(paths, manifest, indices)` liest Referenz, Bewertung, Hinweise; Auswahl, Sortierung, Session-Zeit, Kennzahl; `write_candidates`/`load_candidates`.
- Verify: `scripts/check`
- AC: sichere Passagen fehlen; mehrere Gründe pro Kandidat; Text unverändert; Zeit `null` statt geschätzt; `known_variant` sortiert vor gleichstufigem Kandidaten ohne Hinweis; veraltete Bewertung bricht ab; Datei speicher- und ladbar; `per_hour` bei bekannten Segmentdauern korrekt.

### Chunk 2 — In den Lauf einhängen und dokumentieren
- Dateien: `src/transcript/__main__.py` (`_rate_passages`), CLI-Test, `README.md` (neuer Abschnitt „Review-Kandidaten“, Verzeichnisbaum `review/`), `docs/transcript-roadmap.py` Hinweis TOOL-36
- Änderung: nach `assess_session` Kandidaten schreiben und Zahlen drucken; Fehler → Exit 2 wie bisher.
- Verify: `scripts/check`, dazu `transcript assess` an einer lokalen Session, nur die Konsolenzahlen ansehen
- AC: Konsole zeigt nur Zahlen; README beschreibt Format und Kennzahl.

## Folge-Tickets
- Gewichtung pro Sprecher (Mundart, 47,5 % gegen 14,0 % Fehler): `[kein Ticket: erst sinnvoll, wenn TOOL-68 Labels Personen zuordnet; steht als Hinweis bei TOOL-68]`
- Option „auch sichere Passagen ausgeben“: `[kein Ticket: erst, wenn TOOL-47 sie braucht]`
- Überlappungssignal: `[kein Ticket: gestrichen, tritt ohne Segmentierung nicht auf (TOOL-62)]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Modul `candidates.py`, Format, Tests | no |
| 2 | CLI-Anbindung, README, Roadmap-Hinweis | no |
