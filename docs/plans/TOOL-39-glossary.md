# TOOL-39 — Glossarbegriffe und Eigennamen aus Diarium/Narrata ableiten

## Ziel
Der Block `glossary` des Narrata-Transkriptionskontexts wird geprüft und typisiert gelesen, zusammen mit `glossary_meta` und `asr_ambiguities`. Jeder Eintrag hat kanonischen Namen, Archiv-ID, Typ, Aliasse, ASR-Hörfehler, Kurzkontext und Relevanzstufe. Ein Index findet Einträge über Name, Alias oder Hörfehler, unabhängig von Groß-/Kleinschreibung und Unicode-Normalform. Eine geordnete Liste der Keyword-Kandidaten steht für die ASR-Hinweise bereit. Heute liegt das Glossar nur ungeprüft in der Rohdatei, und `transcript context` zählt es bloß. Eine von Hand gepflegte Glossardatei gibt es nicht und braucht es auch nicht.

## Ist-Stand
- `src/transcript/narrata.py:5` überlässt das Glossar ausdrücklich späteren Schritten. `store_context` (`narrata.py:105`) prüft `session` und `participants`. `read_participants` (`narrata.py:124`) und `_participants`/`_participant`/`_character` (`narrata.py:159-230`) sind das Muster für Leser, Meldungen ohne Werte, `_check_unique` und `_invalid`.
- `src/transcript/__main__.py:203-236`: `_context` liest die Datei ein zweites Mal mit `read_object`, zählt `glossary` über `_count` (`__main__.py:259`) und gibt `glossary_meta` ungeprüft aus.
- Contract 1.1 (ios-archiv `docs/transcripts.md:221-272`): `glossary[]` mit `type` ∈ {place, person, artifact, organisation, event, lore}, `id`, `name`, `aliases[]`, `summary|null`, `asr_variants[]` und `relevance` ∈ {pc, session, recent, archive}. Die Reihenfolge ist pc → session → recent nach Name, dann archive nach Änderungsdatum. Ein Consumer mit Budget nimmt das Glossar von vorn. `glossary_meta {archive_total, archive_returned}` gibt es seit 1.0, `asr_ambiguities [{variant, entries:[{type,id}]}]` erst seit 1.1. Ein Hörfehler mit mehreren Kandidaten wird ausgewiesen, aber nie aufgelöst. Die Quelle ist `TranscriptionContextBuilder::entry` (ios-archiv-backend `app/Support/Transcripts/TranscriptionContextBuilder.php`). Events haben `aliases: []` und `asr_variants: []`.
- Die Keywords kommen heute über `transcribe_session(keywords=())` (`src/transcript/transcription.py:92`). Ein Backend ohne Biasing ignoriert sie bereits (`asr/backend.py:307`, `asr/fake.py:69`).
- Fixtures: `tests/test_narrata.py:53-55` (leeres Glossar) und `tests/test_smoke.py:341` (Zählerzeile).

## Entscheidungen
- **Leser in `narrata.py`:** Neu sind `GlossaryEntry`, `Ambiguity` und `NarrataGlossary` sowie `read_glossary(paths)` und `_glossary(data, path)` nach dem Muster von `_participants`. Den Grund hat schon TOOL-38 festgehalten: `store_context` prüft alle Blöcke, und ein eigenes Lesermodul würde einen Import-Zyklus erzeugen.
- **Nachschlagen in `src/transcript/glossary.py`:** Das neue Modul arbeitet nur auf den Dataclasses und hat keine Datei-I/O. Es enthält `normalize(term)` (NFC, `casefold`, Leerraum zusammengefasst und getrimmt), `GlossaryIndex.lookup(term) -> tuple[Match, ...]` mit `Match(entry, kind)`, wobei `kind` ∈ {`name`, `alias`, `asr_variant`}, und `keyword_terms(glossary) -> tuple[str, ...]`. Getrennt von `narrata.py` ist es, weil TOOL-40/43 darauf aufbauen und nicht am Dateiformat hängen sollen.
- **Mehrdeutigkeit bleibt sichtbar:** `lookup` gibt alle Treffer in Glossar-Reihenfolge zurück und wählt nie einen aus. Das passt zu `asr_ambiguities`, die ebenfalls ausgewiesen werden, nie aufgelöst. Ein Begriff, der bei einem Eintrag Name und bei einem anderen Alias ist, liefert beide Treffer.
- **Keyword-Kandidaten:** Das sind Namen und Aliasse in Glossar-Reihenfolge (also nach Stufen), gegen die normalisierte Form dedupliziert, in Originalschreibweise. `asr_variants` sind ausgeschlossen, weil Biasing auf Hörfehler den Fehler verstärkte. Es gibt keine Kappung und keine Stufenauswahl, das Token-Budget gehört zu TOOL-44, die Relevanzregel zu TOOL-41. Ein Backend ohne Biasing bleibt unberührt, denn TOOL-39 übergibt noch keine Keywords (das macht TOOL-43).
- **Pflicht vs. optional:** `glossary` (Liste, darf leer sein) und `glossary_meta` mit `archive_total`/`archive_returned` (int ≥ 0, returned ≤ total) sind Pflicht. Pro Eintrag sind `type`, `id` (`is_narrata_id`), `name` (nicht leer) und `relevance` Pflicht. Optional sind `aliases` und `asr_variants` (fehlt oder `null` → `()`, sonst Liste von Strings) und `summary` (`null`, fehlt oder leer → `None`). `asr_ambiguities` darf fehlen (Contract 1.0) und ergibt dann `()`. Unbekannte Zusatzfelder werden ignoriert.
- **Strenge Wertelisten:** Ein unbekannter `type` oder eine unbekannte `relevance` ist ein Fehler, so wie bei `role` in TOOL-38. Eine neue Stufe würde die Reihenfolge verändern, die TOOL-41 voraussetzt. Ein neuer Wert braucht deshalb ein Pipeline-Update, und die Meldung sagt das.
- **Konsistenz:** `(type, id)` ist eindeutig. Jeder Verweis in `asr_ambiguities.entries` muss auf einen ausgelieferten Eintrag zeigen. Die Meldungen nennen Position und Feld, nie einen Wert.
- **Unicode:** Im Datenobjekt bleiben die Strings unverändert, also Originalschreibweise. Normalisiert wird nur der Index-Schlüssel. Tests decken zusammengesetzte und zerlegte Umlaute ab, dazu `ß`/`SS`, Fantasienamen mit `Æ`, `Þ`, Apostroph und Bindestrich sowie nicht-lateinische Schrift.
- **Herkunft:** `NarrataGlossary` trägt `source`, `contract_version` und `play_session_id`, jeder Eintrag `type` + `id`. Daran lässt sich zu jedem Begriff Archiv-ID und Herkunft nachvollziehen.
- **Snapshot:** TOOL-39 liefert nur Leser und Index. Die Übernahme in den Snapshot macht TOOL-41, wie bei TOOL-38. Der Abruf über die Wissensschnittstelle ist TOOL-43.

## Daten-Check
- TOOL-66 eingehalten? *handled*: Glossarnamen, auch von `secret`-Einträgen, bleiben in `work/…/narrata/`. Die Dataclasses leben nur im Speicher, eine neue Datei entsteht nicht.
- Konsole: *handled*. `context` zeigt nur Zähler (Einträge je Stufe, Archiv-Kappung, Zahl der Mehrdeutigkeiten). Ein Smoke-Test prüft, dass kein Fixture-Name, Alias, Hörfehler oder Summary in stdout/stderr steht.
- Fehlermeldungen: *handled*. Sie nennen Pfad, Index und Feld (`glossary[3].relevance`, `asr_ambiguities[0].entries[1]`), nie einen Wert und auch nicht die doppelte ID. Ein Test prüft das.
- Logs: *handled*. Leser und Index loggen nichts.
- Fixtures: *handled*. Nur erfundene Namen (`Brakk der Beispielhafte`, `Ærwyn Þornfeld`, `Grauwasser`) und erfundene IDs.

## Contract-Check
- Passt zu IOA-1214/IOA-1215 und Version? *handled*. Die Felder folgen `docs/transcripts.md:221-272` (Contract 1.1). Major 1 bleibt, `asr_ambiguities` ist optional, damit 1.0-Dateien weiter lesbar sind.
- Narrata-Änderung nötig? Nein. Glossar, `asr_variants` (IOA-1217) und `asr_ambiguities` liefert Narrata bereits.

## Resume-Check
- N/A, weil der Schritt kurz ist und kein Modell nutzt: Er liest eine lokale Datei. Snapshot-Stabilität und Wiederverwendung sind Thema von TOOL-41.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt, nur stdlib (`unicodedata`) und `jsonfile`.

## Format-Check
- N/A, weil sich kein internes Format ändert. Die Rohdatei bleibt byte-gleich, `contract_version` gehört Narrata. Eine Datei, die vor TOOL-39 abgelegt wurde und gegen den Glossar-Contract verstößt, meldet beim nächsten `read_glossary` einen Fehler, statt still durchzugehen. Ein Test prüft, dass Lesen die Rohdatei und das Referenztranskript nicht verändert.

## Chunks
### Chunk 1 — Glossarleser
- Dateien: `src/transcript/narrata.py`, `tests/test_narrata.py`
- Änderung: Neu sind die Dataclasses `GlossaryEntry(type, id, name, aliases, asr_variants, summary, relevance)`, `Ambiguity(variant, entries: tuple[tuple[EntryType, int | str], ...])` und `NarrataGlossary(source, contract_version, play_session_id, entries, archive_total, archive_returned, ambiguities)`. Dazu `_glossary`, `_glossary_entry`, `_ambiguities` und `read_glossary(paths)`. `store_context` prüft auch das Glossar. `_check_unique` wird auf `(type, id)`-Schlüssel erweitert, der Modul-Docstring angepasst.
- Verify: `scripts/check`
- AC: Einträge aller sechs Typen werden in Narrata-Reihenfolge geladen. Aliasse und Hörfehler bleiben in Originalschreibweise erhalten, `null` oder fehlend ergibt `()`. Leere `summary` ergibt `None`. Ein 1.0-Kontext ohne `asr_ambiguities` ist lesbar. In jedem dieser Fälle gibt es `NarrataContextError` mit Index und Feld, ohne Wert, und `store_context` speichert nichts: fehlende Pflichtangabe, unbekannter `type`/`relevance`, doppeltes `(type, id)`, Mehrdeutigkeit mit unbekanntem Verweis, `archive_returned > archive_total`. Ein Zusatzfeld stört nicht.

### Chunk 2 — Index und Keyword-Kandidaten
- Dateien: `src/transcript/glossary.py` (neu), `tests/test_glossary.py` (neu)
- Änderung: `normalize`, `Match`, `GlossaryIndex` (Aufbau aus `NarrataGlossary`, `lookup`) und `keyword_terms`.
- Verify: `scripts/check`
- AC: `lookup` findet über Name, Alias und Hörfehler und meldet die Trefferart. NFC- und NFD-Schreibweise, Groß-/Kleinschreibung, `ß`/`SS` und zusätzlicher Leerraum treffen denselben Eintrag. Ein Begriff mit zwei Einträgen liefert beide, in Glossar-Reihenfolge. Ein unbekannter Begriff liefert `()`. `keyword_terms` enthält Namen und Aliasse in Stufenreihenfolge, ohne Hörfehler und ohne Dubletten nach `normalize`, in Originalschreibweise. Bei leerem Glossar ist das Ergebnis `()`.

### Chunk 3 — CLI-Zähler und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`
- Änderung: `_context` liest über `read_glossary` statt über `read_object`/`_count`, `_count` entfällt. Die Ausgabe sieht etwa so aus: `12 glossary entries (2 pc, 3 session, 4 recent, 3 archive), archive tier 3 of 40, 1 asr ambiguity`. Im README kommt unter „Narrata-Kontext“ ein Absatz „Glossar“ hinzu: was gelesen und geprüft wird, Index und Keyword-Kandidaten, dazu der Hinweis, dass Mehrdeutigkeiten nicht aufgelöst werden.
- Verify: `scripts/check`
- AC: Der Smoke-Test `context --from-file` mit einem gefüllten Glossar zeigt die Zähler und keinen Namen, Alias, Hörfehler oder Summary. Ein ungültiges Glossar endet mit Exit 2, die vorhandene Datei bleibt unverändert.

## Folge-Tickets
- TOOL-41: übernimmt `narrata.read_glossary` in den Snapshot und legt fest, welche Stufen relevant sind. Das AK „Ergebnis in den Session-Wissens-Snapshot übernehmen“ aus TOOL-39 wird dorthin verschoben.
- TOOL-43: gibt `glossary.keyword_terms` über die Wissensschnittstelle an `transcribe_session(keywords=…)` weiter. Das AK „über die Wissensschnittstelle als ASR-Keywords/Context-Hinweise abrufbar“ wird dorthin verschoben.
- TOOL-44: kappt `keyword_terms` auf das Token-Budget, die wichtigsten Begriffe nach vorn. Die Reihenfolge liefert TOOL-39 schon.
- TOOL-40: baut den Fuzzy-/Phonetik-Abgleich auf `GlossaryIndex` und den `asr_variants`-Treffern auf. Mehrdeutigkeiten kommen aus `NarrataGlossary.ambiguities`.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Glossarleser in `narrata.py`, Prüfung in `store_context`, Tests | no |
| 2 | `glossary.py`: Normalisierung, Index, Keyword-Kandidaten | no |
| 3 | CLI-Zähler `context`, README | no |
