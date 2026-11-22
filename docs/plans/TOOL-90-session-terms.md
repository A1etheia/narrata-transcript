# TOOL-90 — Kontext 1.4: freie Sitzungsbegriffe ins Biasing und in die Review-Zuordnung

## Ziel
Narrata liefert ab Kontext 1.4 `session_terms`. Das sind Namen, die die Pflegenden vor einer Sitzung eintragen, weil das Welt-Archiv sie noch nicht kennt. Danach kommen diese Begriffe in die ASR-Hotwords, direkt hinter der Stufe `session` und vor `recent`. Ihre `asr_variants` erzeugen Review-Hinweise wie die von Glossar-Einträgen. Heute verwirft die Pipeline den Schlüssel stillschweigend: Ein neuer NSC ist weder im Prompt noch in der Review-Zuordnung.

## Ist-Stand
- `src/transcript/narrata.py:298-330` `parse_glossary` liest `glossary`, `glossary_meta` und `asr_ambiguities`. `session_terms` wird ignoriert. `check_contract` (`:141`) akzeptiert jede 1.x, also auch 1.4.
- `src/transcript/knowledge.py:99-117` `select_keywords`: `pc` ohne Budget, danach `session` und `recent` mit einem Budget pro Typ. Der Snapshot (`:120-170`) speichert die Kontextblöcke im Kontext-Format. `snapshot_id` ist der Hash des Inhalts (`:233`).
- `src/transcript/domain.py:56-144` `DomainContext`: Einträge in Narratas Reihenfolge. `transcription_keywords` gibt Namen und Aliase der Keyword-Einträge in dieser Reihenfolge zurück (`glossary.py:85`), `match_candidates` und `lookup` liefern zusätzlich die `asr_variants`.
- `src/transcript/hints.py:65-80` `Candidate` mit `type`/`id` aus `ENTRY_TYPES`. `_candidate_from` (`:557`) lehnt andere Typen ab.
- `src/transcript/transcription.py:295-310`: Die Wiederaufnahme vergleicht `knowledge_snapshot_id`. Ein neuer Snapshot-Inhalt bedeutet neu transkribieren.
- Der Schutz aus TOOL-81 (`asr/whisper.py`, `hotword_min_tokens`) wirkt auf die fertige Keyword-Liste und gilt damit automatisch auch für freie Begriffe.
- Narrata-Seite (`ios-archiv/docs/transcripts.md:401,425-428`, `TranscriptionContextResource.php:50`): `session_terms: [{term, asr_variants}]`, sortiert nach `term`, ohne Stufe, nicht in `asr_ambiguities`, `asr_variants` nie `null`.
- Review-Entscheidungen hängen an Passagen-IDs (`review_import.py:86-113`), nicht an Einträgen.

## Entscheidungen
- **Modell: freie Begriffe als eigene Einträge im `DomainContext`.** Im Parser und im Snapshot bleiben sie ein eigener Block (`NarrataGlossary.session_terms`, Klasse `SessionTerm`). `DomainContext` macht aus jedem Begriff einen `GlossaryEntry` mit `type = "session_term"`, `id` = 1-basierte Position, `name = term`, ohne Aliase, `relevance = "session"`. Diese Einträge stehen hinter dem letzten Eintrag der Stufe `pc`/`session` und vor `recent`. Grund: Lookup, Hinweise, Keyword-Reihenfolge und Mehrdeutigkeit laufen dann ohne zweiten Codepfad. Die Stufe `session` passt, weil die Begriffe genau für diese Sitzung gepflegt sind.
- **Kein Budget pro Typ für freie Begriffe.** Wie `pc` sind sie immer Keywords. Die Liste ist klein und von Hand gepflegt. Die Hotword-Grenze von 223 Tokens schneidet weiter von hinten, also bei `recent`.
- **Mehrdeutigkeit:** `asr_ambiguities` bleibt Narratas Angabe. Trifft eine Variante einen freien Begriff und einen Archiv-Eintrag, hat der Hinweis zwei Kandidaten und gilt deshalb schon jetzt als `ambiguous` (`hints.py:236`).
- **Variantenvorschläge (TOOL-80) nur für Archiv-Einträge.** `session_term` gehört nicht zu `VARIANT_TYPES`. Ein freier Begriff wird über die Extraktion zum Eintrag, und erst dann hat ein Vorschlag ein Ziel in Narrata.
- **Snapshot ohne Begriffe bleibt bytegleich.** Der Schlüssel `session_terms` wird nur geschrieben, wenn die Liste nicht leer ist. So behält ein 1.3-Kontext oder ein 1.4-Kontext ohne Begriffe beim Refresh dieselbe `snapshot_id`, und es gibt keine Neutranskription (AC 2).
- **Diagnose (`diagnosis.py`) bleibt bei Narratas Glossar.** Ihre Befunde verweisen auf Glossar-Positionen.

## Daten-Check
- Freie Begriffe sind Klarnamen: *handled* — sie liegen nur in `work/<s>/narrata/` (Kontext, Snapshot) und `review/` (Hinweise), wie bisher die Glossar-Namen (TOOL-66).
- Fehlermeldungen: *handled* — sie nennen nur Datei und Position (`session_terms[2].term missing or invalid`), nie einen Wert. Dafür dienen die vorhandenen `_invalid`/`_strings`.
- Konsole: *handled* — `context`, `snapshot` und `transcribe` melden nur die Zahl freier Begriffe.
- Fixtures und Tests: *handled* — nur erfundene Begriffe im Stil der vorhandenen (`Drachenhort`, `Beispielfigur`).

## Contract-Check
- Kontext 1.4 gemäß `ios-archiv/docs/transcripts.md` (IOA-1279): *handled* — Shape `{term, asr_variants}`, `asr_variants` als Liste von Strings, Reihenfolge übernommen.
- 1.3-Server ohne Schlüssel: *handled* — ein fehlender Schlüssel oder `null` gilt als leer (`_optional_list`). Ein Test mit einem 1.3-Kontext ergibt denselben Snapshot wie vorher.
- Versionsprüfung: *N/A, weil* `narrata.SUPPORTED_MAJOR = 1` jede 1.x liest und der Kontext-Contract unabhängig vom Transkript-Contract (`contract.py`, 1.3) steigt. Der Export bleibt unverändert, `knowledge_hints` bleibt leer (`export.py:292`).
- Narrata-Änderung: *N/A, weil* IOA-1279 (PR #1168) die Seite schon liefert. Der Füllstand der Hotword-Liste beim Pflegen kommt in IOA-1336.

## Resume-Check
- Abbruch: *N/A, weil* Parser, Snapshot und Domain schnell und ohne Modell laufen. Die Transkription behält ihre Wiederaufnahme pro Segment (`transcription.py:275`).
- Wiederverwendung: *handled* — Ohne freie Begriffe bleiben Snapshot-Inhalt und `snapshot_id` gleich, vorhandene Transkripte gelten weiter. Mit Begriffen ergibt `snapshot --refresh` eine neue Kennung, und die Segmente werden neu transkribiert. Das ist gewollt, denn es ist neues Wissen. Hinweise werden aus dem neuen Snapshot neu erzeugt.
- Gleiches Modell und gleicher Snapshot: *handled* — unverändert über `asr.settings` und `knowledge_snapshot_id`.

## Dependency-Check
- *N/A, weil* keine neue Abhängigkeit und kein neues Modell dazukommt.

## Format-Check
- Snapshot `format_version: 1`: *handled* — `session_terms` ist ein optionaler Block, und ein fehlender Block gilt als leer. Alte Snapshots laden unverändert, deshalb kein Versionssprung (siehe Entscheidung zur Bytegleichheit).
- Hinweise `format_version: 1`: *handled* — `candidates[].type` kann zusätzlich `session_term` sein. Alte Dateien bleiben gültig, deshalb kein Sprung. Neue Hinweise entstehen ohnehin mit jedem neuen Snapshot.
- Referenztranskript: *N/A, weil* sich nur der Inhalt von `keywords_used` ändert, nicht seine Form.

## Chunks
### Chunk 1 — `session_terms` lesen und im Snapshot einfrieren
- Dateien: `src/transcript/narrata.py`, `src/transcript/knowledge.py`, `src/transcript/__main__.py` (Zähler in `_tier_summary`/`_snapshot`), `tests/test_narrata.py`, `tests/test_knowledge.py`
- Änderung:
  - `SessionTerm(term, asr_variants)` und `NarrataGlossary.session_terms`, gelesen in `parse_glossary` als optionale Liste. `term` muss Text sein, `asr_variants` Strings.
  - `build_snapshot` schreibt den Block nur, wenn er nicht leer ist. `load_snapshot` liest ihn über `parse_glossary` mit.
  - Die Konsole zeigt nur die Zahl der freien Begriffe.
- Verify: `scripts/check`
- AC: Ein 1.4-Kontext mit Begriffen landet im Snapshot. Ein 1.3-Kontext ergibt denselben Snapshot-Inhalt wie vor der Änderung. Ungültige Einträge werden mit ihrer Position gemeldet, ohne Wert.

### Chunk 2 — Biasing und Review-Zuordnung
- Dateien: `src/transcript/narrata.py` (`SESSION_TERM`, `CANDIDATE_TYPES`), `src/transcript/domain.py`, `src/transcript/hints.py`, `tests/test_domain.py`, `tests/test_hints.py`, `tests/test_smoke.py`
- Änderung:
  - `DomainContext` fügt die freien Begriffe als Einträge vom Typ `session_term` hinter `pc`/`session` ein und macht sie zu Keywords.
  - `hints._candidate_from` akzeptiert `CANDIDATE_TYPES`.
  - `VARIANT_TYPES` bleibt ohne `session_term`.
- Verify: `scripts/check`
- AC: `transcription_keywords()` enthält die Begriffe zwischen `session` und `recent`, ohne ihre `asr_variants` (AC 1, Smoke-Test mit dem Fake-Backend prüft die übergebenen Keywords). Eine `asr_variant` eines freien Begriffs erzeugt einen `known_variant`-Hinweis. Eine geteilte Variante wird `ambiguous`. Ohne `session_terms` sind Keywords und Hinweise unverändert (AC 2).

### Chunk 3 — Doku und Probe an einer echten Sitzung
- Dateien: `README.md` (Abschnitt Wissen/Kontext), `docs/transcript-roadmap.py` und die daraus generierte `.md` (TOOL-81 als erledigt nachziehen)
- Änderung:
  - Das README beschreibt `session_terms`: Platz im Biasing, kein Budget, Review-Hinweise, keine Variantenvorschläge, Neutranskription nur bei neuen Begriffen.
  - Lokale Probe: `transcript context` → `snapshot --refresh` → `transcript keywords <session>` gegen eine Sitzung mit freiem Begriff. Ins Repo kommen nur Zahlen, keine Namen.
- Verify: `scripts/check`
- AC: Das README nennt das Verhalten. Die Probe zeigt die Zahl freier Begriffe im Snapshot und in den Keywords.

## Folge-Tickets
- Diagnose meldet freie Begriffe, die einen Archivnamen doppeln: [kein Ticket: Narrata kennt beide Listen und kann das beim Pflegen zeigen; erst anlegen, wenn es in der Praxis vorkommt]
- Variantenvorschläge für freie Begriffe: [kein Ticket: Ein freier Begriff wird über die Extraktion zum Archiv-Eintrag, und dann gilt der Vorschlag dem Eintrag]
- Füllstand der Hotword-Liste beim Pflegen in Narrata: IOA-1336

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Parser und Snapshot für `session_terms` | no |
| 2 | Domain, Biasing, Hinweise | no |
| 3 | README, Roadmap-Drift, lokale Probe | no |
