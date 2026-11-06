# TOOL-40 — Bekannte Fehltranskriptionen aus Archivwissen nutzbar machen

## Ziel
Hörfehler, die Narrata pflegt (`asr_variants`, IOA-1217), sind nachweislich als starkes, kontrolliertes Kandidatenwissen nutzbar. Die Abdeckung ist getestet und dokumentiert, auch für den Fall ohne Hörfehler. Den größten Teil haben TOOL-39, TOOL-43 und TOOL-44 schon gebaut. Dieses Ticket schließt die Lücken bei den Akzeptanzkriterien und legt fest, wie weit eine Variante gilt. Die Vorschlagsliste aus Review-Korrekturen wandert nach TOOL-80.

## Ist-Stand
- `src/transcript/narrata.py:95-102`: `GlossaryEntry.asr_variants`; `:112` `Ambiguity`; `:299-326` liest `asr_ambiguities` optional (fehlt vor Contract 1.1).
- `src/transcript/glossary.py:16`: `MatchKind` mit `asr_variant`; `:96-97` liefert Varianten mit Feld `asr_variants[i]`.
- `src/transcript/domain.py:95-101`: `lookup`, `is_ambiguous`; `:128` `match_candidates` samt Hörfehlern; `:125` Keywords ohne Hörfehler.
- `src/transcript/hints.py:50`: Signal `known_variant`; `Candidate` (`:61-74`) mit Typ, Archiv-ID, Begriff, Art, Feld, Stufe → zurückführbar auf den Narrata-Datensatz.
- Tests: `tests/test_hints.py:65` (Variante → kanonischer Eintrag), `:83`/`:97` (mehrdeutig), `:158` (leeres Glossar), `:183` (Text unverändert).
- Lücken: kein Test für mehrere Varianten auf denselben Eintrag und keiner für ein Glossar mit Einträgen ganz ohne `asr_variants`. Im README (`README.md:252-266`) fehlt, wie weit eine Variante gilt.
- Contract 1.1 (`ios-archiv/docs/transcripts.md:234,251-256`): `asr_variants` ist eine reine String-Liste am Eintrag ohne eigenen Kontext pro Variante.

## Entscheidungen
- **Gültigkeitsbereich = der Eintrag.** Narrata liefert keinen Kontext pro Variante. Eine Variante gilt deshalb genau für ihren Eintrag (Typ, Archiv-ID) und trägt dessen Relevanzstufe; beides steht schon in jedem Kandidaten. Der Punkt wird dokumentiert, Code ist dafür nicht nötig. Eigener Kontext pro Variante bräuchte einen Contract-Bump in Narrata; dafür gibt es aktuell keinen Bedarf.
- **Vorschlagsliste abgespalten (TOOL-80).** Die Datei „ASR-Variante → kanonischer Begriff (Archiv-ID)“ braucht Review-Entscheidungen „manuell korrigiert“ mit Zieltext. Die gibt es erst mit TOOL-46 (Datenmodell) und TOOL-48 (Reimport). Ein eigenes Eingabeformat jetzt würde TOOL-46 vorgreifen.
- Keine eigene Transcript-Fehlerliste, kein Ersetzen im ASR-Text (unverändert).

## Daten-Check
- handled — neue Tests verwenden nur erfundene Namen wie in `tests/test_hints.py:25`; es entstehen keine Fixtures mit echten Daten.
- handled — kein neuer Log- oder Fehlerpfad; `hints.py` loggt weiterhin nichts.

## Contract-Check
- handled — liest nur Contract 1.1 wie heute (`glossary[].asr_variants`, `asr_ambiguities`), keine Änderung. Narrata braucht nichts, also auch kein IOA-Ticket.

## Resume-Check
- N/A, weil kein lang laufender oder modellgestützter Schritt dazukommt.

## Dependency-Check
- N/A, weil weder Abhängigkeit noch Modell neu sind.

## Format-Check
- N/A, weil `segment-NN.hints.json` (`HINTS_FORMAT_VERSION = 1`) unverändert bleibt.

## Chunks
### Chunk 1 — Abdeckung der Hörfehler belegen und dokumentieren
- Dateien: `tests/test_hints.py`, `README.md`
- Änderung:
  - Test: Ein Eintrag mit zwei `asr_variants` liefert für beide gehörten Varianten einen `known_variant`-Hinweis auf denselben Eintrag, mit Feld `asr_variants[0]` bzw. `[1]`.
  - Test: Ein Glossar ohne jede Variante (wie Contract 1.0) liefert keinen `known_variant`, `similar` funktioniert weiter.
  - README „Review-Hinweise“: Absatz **Hörfehler aus Narrata**. Die Variante gilt für ihren Eintrag, mehrere Varianten können auf einen Eintrag zeigen, ohne Varianten bleibt nur `similar`, gepflegt wird in Narrata („Bekannte Hörfehler“), die Vorschlagsliste kommt mit TOOL-80.
- Verify: `scripts/check`
- AK: Alle AKs von TOOL-40 außer der Vorschlagsliste sind durch Tests belegt; die README beschreibt Gültigkeitsbereich und den Fall ohne Hörfehler.

## Folge-Tickets
- TOOL-80 — Vorschlagsdatei neuer Hörfehler aus Review-Korrekturen (nach TOOL-48; Zielfeld `asr_variants`, nur Datei, keine automatische Übernahme).
- Import-Command für Vorschlagsdateien in Narrata `[kein Ticket: entsteht erst, wenn TOOL-80 ein Format festlegt; bis dahin pflegt die SL die Hörfehler auf der Bearbeiten-Seite]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Tests + README zu Hörfehlern | no |
