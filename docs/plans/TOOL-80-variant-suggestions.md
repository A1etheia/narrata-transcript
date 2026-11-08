
# TOOL-80 — Vorschlagsdatei neuer Hörfehler aus Review-Korrekturen

## Ziel
Nach einem Review-Import liegt pro Session eine Datei mit neuen Hörfehlern als Vorschlag vor: `ASR-Variante → kanonischer Begriff (Typ, Archiv-ID)`, jeweils mit den Review-Entscheidungen, aus denen der Vorschlag stammt. Die Spielleitung kann sie dann in Narrata unter `asr_variants` (IOA-1217) pflegen. Bisher gehen die Korrekturen aus `decisions.json` nicht zurück in das Archivwissen. Übernommen wird nichts automatisch.

## Ist-Stand
- `src/transcript/decisions.py:47` `ReviewDecision` mit `target_text` nur bei `corrected`. `review_items` (`:144`) liefert die geltenden Entscheidungen ohne veraltete und verwaiste, `load_decisions` steht in `:187`.
- `src/transcript/candidates.py:59` `ReviewCandidate.text`: der erkannte Text der ganzen Passage, unverändert. `load_candidates` steht in `:282`.
- `src/transcript/domain.py:95` `DomainContext.lookup(term)` liefert `TermHit` mit Eintrag, Art (`name`/`alias`/`asr_variant`) und Feld. `is_ambiguous` steht in `:99`, `DomainContext.load` in `:91`.
- `src/transcript/hints.py:55` `MAX_SPAN_WORDS = 4`. `_tokens`/`_key` (`:301`, `:310`) zerlegen Text in Wörter und normalisieren ohne Satzzeichen am Rand.
- `src/transcript/__main__.py:762` `_review_import` schreibt `decisions.json` nur bei einer Änderung. `_domain` (`:829`) gibt `None` zurück, wenn kein Snapshot da ist.
- `src/transcript/session.py:128` Pfade unter `review/`.
- Narrata: Events tragen keine `asr_variants` (`ios-archiv/docs/transcripts.md:274`). `archive:import` verwirft einen Hörfehler, der Name oder Alias des Ziels gleicht (`ios-archiv/docs/archive.md:127`).

## Entscheidungen
- **Auslöser:** `transcript review-import` schreibt die Vorschläge am Ende jedes erfolgreichen Imports mit, auch wenn sich keine Entscheidung geändert hat. So passt die Datei immer zum aktuellen Stand von Entscheidungen und Snapshot. Es gibt keinen eigenen Befehl (Wahl der Nutzerin).
- **Ableitung:** Erkannter Text und `target_text` werden wortweise mit `difflib` verglichen, Schlüssel wie in `hints`. Vorschlag wird jede Ersetzung, deren korrigierte Seite genau ein Name oder Alias eines Glossar-Eintrags ist und deren beide Seiten höchstens `MAX_SPAN_WORDS` Wörter haben. Die Variante ist die erkannte Wortfolge mit Groß- und Kleinschreibung, ohne Satzzeichen am Rand. Reine Einfügungen und Löschungen sind keine Hörfehler. Grenze: Zieht `difflib` ein Nachbarwort in die Ersetzung, steht es mit in der Variante, etwa „der Kwendolin“. Die Spielleitung prüft jeden Vorschlag ohnehin.
- **Nicht vorgeschlagen:** wenn die Variante für denselben Eintrag schon Name, Alias oder Hörfehler ist (gepflegt bzw. von Narrata ohnehin verworfen), außerdem für Einträge vom Typ `event`, da Narrata dort keine Hörfehler führt.
- **Mehrdeutig:** Trägt der korrigierte Begriff mehrere Einträge, entsteht ein Vorschlag mit allen Einträgen und `ambiguous: true`, ausgewählt wird keiner. Benennt die Variante schon einen anderen Eintrag, steht der unter `also_names`.
- **Zusammenfassen:** gleiche Variante (normalisiert) mit gleichen Einträgen ergibt einen Vorschlag mit allen Entscheidungen (`candidate`, `decided_at`), in der Reihenfolge Segment und Passage.
- **Leer:** Die Datei entsteht immer, ohne Korrekturen mit leerer Liste. Ohne Snapshot entsteht keine, eine vorhandene wird entfernt (wie bei den Hinweisdateien), und die Konsole verweist auf `transcript snapshot`. Der Import selbst scheitert daran nicht.
- **Kein Zeitstempel in der Datei:** Gleiche Entscheidungen und gleicher Snapshot ergeben byteweise dieselbe Datei, so bleibt der Import idempotent.

Format `work/<g>/<o>/review/asr-variant-suggestions.json`:
```json
{"format_version": 1, "session": "…", "knowledge_snapshot_id": "…", "target_field": "asr_variants",
 "counts": {"corrected": 5, "suggested": 2, "known": 1, "no_term": 2},
 "suggestions": [{"variant": "Kwendolin",
   "entries": [{"type": "person", "id": 5, "term": "Quendolin", "field": "name"}],
   "ambiguous": false, "also_names": [],
   "decisions": [{"candidate": "s01-p0042", "decided_at": "…"}]}]}
```

## Daten-Check
- Datei mit echten Namen und Korrekturen: handled, sie liegt nur unter `work/<g>/<o>/review/` (TOOL-66).
- Konsole und Fehlermeldungen: handled, sie zeigen nur Zahlen, Pfade und Kandidaten-IDs, nie Variante, Begriff oder Zieltext. Das Modul loggt nichts.
- Fixtures und Tests: handled, nur erfundene Namen (`Quendolin`/`Kwendolin` usw.), keine echten Sitzungstexte.
- Repo: N/A, weil kein neuer Pfad außerhalb von `work/` entsteht und `work/` bereits ignoriert ist.

## Contract-Check
- Lesen: handled, nur über den bestehenden Snapshot und `DomainContext` (Contract 1.1 mit `asr_variants`). Neu wird kein Contract-JSON gelesen.
- Schreiben: N/A, weil die Vorschlagsdatei kein Teil von IOA-1214 ist. Sie ist eine interne Arbeitsdatei, die die Spielleitung liest. Narrata liest nichts aus `work/`.
- Narrata-Änderung: Ein Import-Command für das Format folgt als IOA-Folge-Ticket (siehe unten). Für TOOL-80 selbst ist keine Narrata-Änderung nötig.

## Format-Check
- Neues internes Format `asr-variant-suggestions.json` mit `format_version: 1`: handled.
- Bestehende Artefakte: N/A, weil es die Datei bisher nicht gibt. `decisions.json`, `candidates.json` und der Snapshot behalten ihre Versionen und werden nur gelesen.

## Chunks
### Chunk 1 — Vorschläge ableiten und schreiben
- Dateien: `src/transcript/variant_suggestions.py` (neu), `src/transcript/session.py` (Pfad `review_variant_suggestions`), `src/transcript/hints.py` (Randzeichen-Logik aus `_key` als wiederverwendbare Funktion, Verhalten unverändert), `tests/test_variant_suggestions.py` (neu).
- Änderung: `suggest(found, decisions, domain) -> VariantSuggestions` über `review_items` nur aus geltenden `corrected`-Entscheidungen. Dazu `write_suggestions(paths, suggestions)` (atomar, `jsonfile.write_atomic`) und `remove_suggestions(paths)`.
- Verify: `scripts/check`
- AC: Tests decken ab: einfacher Hörfehler mit Typ, ID und Entscheidung; schon gepflegter Hörfehler erscheint nicht; Korrektur ohne Glossar-Begriff zählt als `no_term`; mehrdeutiger Begriff; `also_names`; Event-Eintrag ausgelassen; veraltete und verwaiste Entscheidungen ignoriert; Zusammenfassen über zwei Entscheidungen; ohne Korrekturen leere Liste; Satzzeichen am Rand entfernt, Schreibung erhalten; gleiche Eingabe ergibt dieselben Bytes.

### Chunk 2 — In review-import einhängen und dokumentieren
- Dateien: `src/transcript/__main__.py` (`_review_import`), `tests/test_smoke.py`, `README.md` (neuer Abschnitt „Hörfehler-Vorschläge“ nach „Review-Import“, Verweis in „Review-Hinweise“ `:264` statt „folgt mit TOOL-80“).
- Änderung: Nach dem Import werden mit Snapshot die Vorschläge geschrieben, die Konsole zeigt `asr variant suggestions: 2 new, 1 known, 2 without glossary term` und `wrote …`. Ohne Snapshot wird eine alte Datei entfernt und ein Hinweis auf `transcript snapshot` ausgegeben, der Exit-Code bleibt wie gehabt. Ist der Snapshot ungültig, bleiben die gespeicherten Entscheidungen erhalten, es kommt eine Fehlermeldung und Exit 2.
- Verify: `scripts/check`
- AC: Smoke-Tests für den Import mit und ohne Snapshot. Keine Konsolenausgabe enthält einen Namen. Die README dokumentiert das Format, den leeren Fall und den Fall ohne Snapshot.

## Folge-Tickets
- Narrata-Import-Command für `asr-variant-suggestions.json` (Format v1) nach `asr_variants`: IOA-1285.
- Nachbarwort in der Variante (siehe Grenze unter Entscheidungen) `[kein Ticket: erst nach realen Vorschlagsdateien beurteilbar, die Spielleitung prüft jeden Vorschlag]`.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `variant_suggestions.py`, Pfad, Tests | no |
| 2 | `review-import`, Smoke-Tests, README | no |
