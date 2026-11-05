# TOOL-43 — Einheitliche Wissensschnittstelle für Pipeline-Schritte

## Ziel
Pipeline-Schritte fragen das Session-Wissen über eine Komponente ab, `transcript.domain.DomainContext`. Damit erreichen sie Begriffe, Aliase und Hörfehler, Sprecher und Spielfiguren per Archiv-ID, die Session-relevanten Einträge, die ASR-Keywords und die Herkunft jedes Treffers, ohne Narrata, die Rohdatei oder das Snapshot-Format zu kennen. Heute übergibt `transcript transcribe` `keywords=()`. Danach bekommt das Backend die Keywords aus dem Snapshot, und ein Ergebnis ohne diese Hinweise gilt nicht mehr als wiederverwendbar.

## Ist-Stand
- `src/transcript/__main__.py:480`: `keywords=()  # … come with TOOL-43`. `_snapshot_id` (`:527`) lädt den Snapshot nur für die ID.
- `src/transcript/transcription.py:260` `_reusable` vergleicht Backend-Identität, `knowledge_snapshot_id` und Sprache, aber keine Keywords.
- `src/transcript/reference.py:99`: `AsrInfo.keywords_used` existiert schon im Referenzformat v2 (`:37`) und wird aus `BackendResult.keywords_used` gefüllt (`:236`).
- `src/transcript/asr/backend.py:74` `Capabilities.keyword_biasing`, `:307` lehnt `keywords_used` ohne Capability ab. `asr/whisper.py:196` kappt Hotwords als Präfix auf `HOTWORD_TOKENS`. `asr/fake.py:69` meldet die Keywords nur mit Capability als genutzt.
- `src/transcript/knowledge.py:450` `Snapshot` (participants, glossary, keyword_entries, source, snapshot_id), `:549` `load_snapshot`.
- `src/transcript/glossary.py:340` `GlossaryIndex.lookup` → `Match(entry, kind)` ohne Feld. `:358` `keyword_terms(NarrataGlossary)` wird nur in Tests aufgerufen. `:376` `entry_terms` liefert `(kind, field, term)`.
- `src/transcript/narrata.py:63` `Participant(user_id, …, characters)`, `:92` `GlossaryEntry` mit `ref`, `relevance`.

## Entscheidungen
- **Neues Modul `src/transcript/domain.py`.** Darin `DomainContext` mit `from_snapshot(snapshot)` und `load(paths)`. Der Konstruktor nimmt geparste Teile (Teilnehmende, Glossar, Keyword-Refs, `Origin`), nicht den `Snapshot`. So hängt nur die Factory am Snapshot-Format, und eine andere Quelle braucht nur eine neue Factory.
- **Abfragen** (alle rein lesend, Ergebnisse sind frozen dataclasses oder Tupel):
  - `lookup(term) -> tuple[TermHit, ...]`: kanonischer Eintrag zu Name, Alias oder Hörfehler. Bei Mehrdeutigkeit kommen alle Treffer, eine Auswahl trifft die Schnittstelle nie.
  - `entry(ref)`, `participant(user_id)`, `character(person_id) -> (Participant, Character) | None`.
  - `relevant_entries()`: Einträge der Stufen `pc`/`session`/`recent` in Narratas Reihenfolge. `keyword_entries()`.
  - `transcription_keywords() -> tuple[str, ...]`: `glossary.keyword_terms` über die Keyword-Einträge des Snapshots.
  - `match_candidates() -> tuple[TermHit, ...]`: jeder Begriff jedes Eintrags inklusive Hörfehler, als Rohmaterial für den Fuzzy-Abgleich in TOOL-40. Der Abgleich selbst gehört nicht hierher.
  - `ambiguities`, `origin`.
- **Herkunft:** `Origin(snapshot_id, source_file, contract_version, play_session_id)` und `TermHit(entry, kind, field, term, keyword, origin)`. Damit nennt jeder Treffer Archiv-Ref, Stufe, Feld (`aliases[1]`), Keyword-Flag und Quelle.
- **`glossary.Match` bekommt `field`.** `GlossaryIndex` hat es aus `entry_terms` schon zur Hand. Das ist kleiner als ein zweiter Index in `domain`.
- **`keyword_terms` nimmt `Iterable[GlossaryEntry]`** statt `NarrataGlossary`, damit es auf `keyword_entries` läuft. Es gibt keinen Produktivaufrufer, also gibt es nur Teständerungen.
- **Wiederverwendung:** `_reusable` bekommt `keywords` und die Capability. Ein gespeichertes `keywords_used` muss eine geordnete Teilfolge der aktuellen Keywords sein. Hat das Backend `keyword_biasing` und gibt es Keywords, darf es nicht leer sein. So wird ein Lauf von vor TOOL-43 (gleicher Snapshot, `keywords_used=()`) einmal neu transkribiert, und die Präfix-Kappung von Whisper bleibt wiederverwendbar. Es gibt kein neues Feld und keinen Format-Bump. Randfall: Passt schon das erste Keyword nicht ins Token-Budget, ist `keywords_used` leer und das Segment wird bei jedem Lauf neu transkribiert. Das wird hingenommen und dokumentiert.
- **Backends ohne `keyword_biasing`** bekommen die Keywords weiter im Request und ignorieren sie. Es braucht keine Domänenlogik im Backend, und die Wiederverwendung bleibt unberührt, weil `keywords_used` leer bleibt.
- **CLI:** Ist ein Snapshot da, lädt `_transcribe` ihn einmal als `DomainContext` und übergibt ID und `transcription_keywords()`. Ohne Snapshot bleibt alles wie heute. Die Konsole zeigt nur die Anzahl der Keywords, keine Begriffe.
- **Diagnose bleibt auf `Snapshot`.** Sie läuft im `snapshot`-Befehl direkt nach dem Bau, eine Umstellung bringt dort nichts.

## Daten-Check
- TOOL-66: handled. `DomainContext` loggt nichts und gibt keine Begriffe in Fehlermeldungen aus. Die CLI druckt nur Anzahlen und eine gekürzte Snapshot-ID.
- Fixtures: handled. Die Tests nutzen die bestehenden anonymisierten Muster (`Beispielfigur`, `Grauwasser`, `beispielgruppe/042`), es kommen keine echten Namen dazu.
- Fehlermeldungen: handled. Die `SnapshotError`-Texte aus `knowledge` nennen Datei und Feld und bleiben unverändert.

## Contract-Check
- IOA-1214 / Version: N/A, weil nur der lokale Snapshot gelesen wird. Den Contract prüft weiter `knowledge.load_snapshot` über `narrata.check_contract`.
- Narrata-Änderung: N/A, es braucht keine, kein IOA-Ticket.

## Resume-Check
- Abbruch: handled. `transcribe_session` schreibt weiter pro Segment atomar, das Verhalten bei Abbruch ändert sich nicht.
- Wiederverwendung: handled. Die neue Regel prüft `keywords_used` gegen die aktuellen Keywords, Snapshot-ID und Modell bleiben Teil der Regel.
- Gleicher Snapshot beim Resume: handled. Die Keywords leiten sich deterministisch aus dem Snapshot ab, ein neuer Snapshot erzwingt wie bisher einen Neulauf.

## Dependency-Check
- N/A, weil weder eine neue Abhängigkeit noch ein neues Modell dazukommt.

## Format-Check
- Referenzformat: N/A für einen Bump. `keywords_used` existiert in v2 schon. Bestehende v2-Referenzen mit Snapshot-ID, aber leerem `keywords_used`, werden beim nächsten Lauf mit Whisper einmal neu transkribiert. Das ist gewollt, weil das Wissen bisher nicht ankam.
- Snapshot-Format: N/A, unverändert (`SNAPSHOT_FORMAT_VERSION = 1`).

## Chunks
### Chunk 1 — Wissensschnittstelle
- Dateien: `src/transcript/glossary.py`, `src/transcript/domain.py` (neu), `tests/test_glossary.py`, `tests/test_domain.py` (neu)
- Änderung: `Match.field`, `keyword_terms(entries)`, `DomainContext` mit `Origin`, `TermHit` und den Abfragen oben.
- Tests: Lookup über Name, Alias und Hörfehler mit Feld und Herkunft; Mehrdeutigkeit liefert alle Treffer; Teilnehmende und Spielfigur per ID, unbekannte ID gibt `None`; `relevant_entries` ohne `archive`; `transcription_keywords` nur aus Keyword-Einträgen, ohne Hörfehler; `match_candidates` mit Hörfehlern; `load(paths)` liest einen gebauten Snapshot, und die Snapshot-Datei ist nach allen Abfragen byte-gleich.
- Verify: `scripts/check`
- AC: Sprecher-, Begriffs- und Variantenwissen sind über eine Komponente erreichbar, mit Herkunft. Abfragen ändern nichts. Unit-Tests decken das ab.
- Commit: `feat(knowledge): add the domain context for pipeline steps (TOOL-43)`

### Chunk 2 — Keywords in der Wiederverwendungsregel
- Dateien: `src/transcript/transcription.py`, `tests/test_transcription.py`
- Änderung: `_reusable(…, keywords, biasing)` mit der Teilfolgen-Regel, der Docstring von `transcribe_session` ergänzt.
- Tests: gleiche Keywords werden wiederverwendet; vorher ohne Keywords und jetzt mit Keywords plus Biasing-Backend führt zum Neulauf; gekappter Präfix wird wiederverwendet; geänderte Keywords führen zum Neulauf; ein Backend ohne Biasing verwendet trotz Keywords wieder.
- Verify: `scripts/check`
- AC: Ein Segment mit anderen Hinweisen gilt nicht als wiederverwendbar (Übergabe TOOL-17).
- Commit: `feat(transcription): reuse results only with the same keywords (TOOL-43)`

### Chunk 3 — CLI und Doku
- Dateien: `src/transcript/__main__.py`, `README.md`, ggf. `tests/test_smoke.py`
- Änderung: `_snapshot_id` wird durch `_knowledge(paths) -> DomainContext | None` ersetzt, `keywords=context.transcription_keywords()`, und eine Konsolenzeile `<key>: <n> keyword(s) from snapshot <id12>`. README: neuer Abschnitt „Wissensschnittstelle“ und die Keyword-Zeile im Abschnitt `transcribe` aktualisiert.
- Tests: Der Helfer liefert ohne Snapshot `None` und mit Snapshot ID und Keywords. Der Whisper-Lauf bleibt ungetestet, weil er das Modell braucht.
- Verify: `scripts/check`
- AC: Backends beziehen Session-Keywords über die zentrale Schnittstelle (Übergaben TOOL-15 und TOOL-39).
- Commit: `feat(cli): pass snapshot keywords to transcription (TOOL-43)`

## Folge-Tickets
- Fuzzy- und Phonetik-Abgleich auf `DomainContext.match_candidates()`: TOOL-40
- Token-Kappung und Priorisierung der Keywords pro Backend: TOOL-44. Hinweis: `whisper.py:196` kappt schon als Präfix, und TOOL-44 sollte darauf aufbauen.
- Diagnose auf `DomainContext` umstellen: [kein Ticket: Die Diagnose läuft direkt nach dem Snapshot-Bau und hat keinen Nutzen von der Umstellung]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `domain.py`, `glossary.py` + Tests | no |
| 2 | `_reusable` mit Keywords | no |
| 3 | CLI-Verdrahtung, README | no |
