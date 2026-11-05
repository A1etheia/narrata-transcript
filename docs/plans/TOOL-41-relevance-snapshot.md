# TOOL-41 — Relevanzregel und Wissens-Snapshot

## Ziel
Aus dem abgelegten Narrata-Kontext einer Sitzung entsteht ein eingefrorener Wissens-Snapshot. Er enthält Teilnehmende, Glossar und Mehrdeutigkeiten, außerdem die Auswahl der Keyword-Einträge innerhalb eines konfigurierten Budgets pro Typ. Jeder Eintrag trägt Quelle, Narrata-ID und Relevanzgrund. Spätere Schritte lesen den Snapshot ohne Narrata-Zugriff. Ein erneuter Abruf ändert ihn nicht stillschweigend, und eine bewusste Aktualisierung ist an einer neuen Snapshot-ID erkennbar. Heute gibt es nur die Rohdatei. Ein neuer `transcript context` ersetzt sie, und kein Referenztranskript weiß, mit welchem Wissensstand es entstand.

## Ist-Stand
- Rohdatei: `SessionPaths.narrata_context` (`src/transcript/session.py:319`) ist der einzige Schreibpfad über `narrata.store_context` (`src/transcript/narrata.py:146`). Ein erneuter Abruf ersetzt die Datei (Plan TOOL-67, Resume-Check).
- Leser: `read_participants` (`narrata.py:166`) und `read_glossary` (`narrata.py:178`) liefern typisierte, geprüfte Blöcke samt `source` und `contract_version`. `RELEVANCE_TIERS` (`narrata.py:83`) ist nach Nähe geordnet.
- Relevanz: Narrata berechnet die Stufe pro Eintrag selbst (`pc > session > recent > archive`, erste passende) und sortiert das Glossar entsprechend (ios-archiv `docs/transcripts.md`, „Relevanz“, „Reihenfolge“). `archive` ist nach zuletzt geändert sortiert und auf `archive_limit` gekappt.
- Keyword-Kandidaten: `glossary.keyword_terms` (`src/transcript/glossary.py:67`) liefert Name und Aliasse in Glossar-Reihenfolge, ohne Stufenauswahl und ohne Kappung.
- Abruf: `narrata_client.context_url` (`src/transcript/narrata_client.py:159`) sendet weder `n` noch `archive_limit`, es gelten die Server-Defaults 3 und 500.
- Konfiguration: `_NARRATA_KEYS = {"url", "groups"}` (`src/transcript/config.py:31`). Eine Budget-Einstellung gibt es nicht.
- ASR: `__main__._transcribe` übergibt `keywords=()` (`src/transcript/__main__.py:319`), die Übergabe der Keywords macht TOOL-43. Die Wiederverwendung prüft nur Backend, Modell, Revision, Settings und Sprache (`src/transcript/transcription.py:242`). Das Referenzformat ist `REFERENCE_FORMAT_VERSION = 1` (`src/transcript/reference.py:37`), `load_reference` lehnt jede andere Version ab (`reference.py:351`).
- Sprecherzahl: Sie kommt nur über `--num-speakers` (`__main__.py:100`, `:110`), Anwesenheit kennt Narrata nicht (`Participant.present = None`).

## Entscheidungen
Im Chat vom 05.11.2026 entschieden:

- **Relevanzregel = Narratas Stufe übernehmen.** Die Pipeline rechnet die Stufen nicht nach, weil Narrata alle Daten dafür hat (Verknüpfungen, Tagebücher, Erwähnungs-Matcher) und die Regel sonst an zwei Stellen gepflegt würde. `relevance` wird als Relevanzgrund in den Snapshot übernommen. Lokal laufen nur die Keyword-Auswahl und das Budget. Das AK „Relevanzregel anwenden“ gilt damit als erfüllt: Die Regel steht in ios-archiv `docs/transcripts.md`, die README verweist darauf.
- **Keyword-Auswahl:** Keywords kommen aus `pc`, `session` und `recent`, nie aus `archive` (Ticket: „ASR-Keywords aus Stufen 1–3“). `pc` ist immer dabei und zählt nicht gegen das Budget. `session` und `recent` füllen pro Typ in Narratas Reihenfolge bis zum Budget. Alle Glossareinträge bleiben im Snapshot, auch `archive`, denn der spätere Fuzzy-Abgleich (TOOL-40) darf das ganze Archiv nutzen.
- **Budget pro Typ:** `knowledge.keyword_budget` in der Konfiguration ist eine Höchstzahl an Einträgen je `EntryType`. Defaults: person 15, place 10, organisation 5, artifact 5, event 3, lore 3. Fehlende Typen nehmen den Default, `0` heißt „keiner“. Die Token-Kappung auf 223 Tokens bleibt bei TOOL-44.
- **Snapshot als eigene, eingefrorene Datei:** Die Datei liegt unter `work/<key>/narrata/snapshot.json`. Sie enthält die geprüften Daten selbst, nicht nur einen Verweis, damit sie ohne Rohdatei lesbar ist. Kopf: `format_version: 1`, `snapshot_id`, `created_at`, `source` (Dateiname, `contract_version`, `sha256` der Rohdatei, `play_session_id`) und `keyword_budget`. `snapshot_id` ist sha256 über den kanonischen Inhalt ohne `created_at`. Ein Refresh mit unverändertem Narrata-Stand ergibt deshalb dieselbe ID, ein geänderter Stand eine neue.
- **Abruf erlaubt, Snapshot bleibt stehen:** `transcript context` darf die Rohdatei weiter ersetzen. `transcript snapshot <key>` baut den Snapshot nur, wenn keiner existiert, sonst nutzt es ihn wieder. Mit `--refresh` wird er neu gebaut. Weichen sha256 der Rohdatei oder das konfigurierte Budget vom Snapshot ab, warnen `snapshot` und `context` mit dem Hinweis auf `--refresh`. Sie ersetzen ihn aber nicht.
- **`n` und `archive_limit`:** Die Konfiguration bekommt `narrata.recent_sessions` (Default 3, 1–20) und `narrata.archive_limit` (Default 500, 0–2000). Beide gehen ausdrücklich als Query-Parameter an den Endpoint. Die Werte entsprechen den Server-Defaults, hängen aber nicht mehr still von ihnen ab. Der Snapshot vermerkt sie nicht, weil er aus der Rohdatei gebaut wird, die den Abruf nicht kennt (auch bei `--from-file`).
- **Snapshot-ID im Referenztranskript:** Das Feld heißt `asr.knowledge_snapshot_id` (`null` ohne Snapshot). `transcribe` liest die ID aus dem vorhandenen Snapshot, ohne ihn zu bauen. `_reusable` vergleicht sie zusätzlich. Ein neuer Wissensstand führt deshalb zur Neutranskription, ein Resume mit demselben Snapshot nicht. Einmalige Folge: Wer für eine schon transkribierte Session erstmals einen Snapshot baut, transkribiert neu, obwohl bis TOOL-43 noch keine Keywords fließen. Das ist bewusst so, denn sonst stünde in jedem Altbestand ein falscher Wissensstand.
- **`num_speakers` verschoben:** Ohne Anwesenheit wäre die Zahl der aktiven Teilnehmenden eine Vorgabe, die bei fehlenden Personen falsch ist und pyannote eine Stimme spalten ließe. `--num-speakers` bleibt die einzige Quelle. Die Übergabe geht an TOOL-79 (Anwesenheit aus IOA-1271).
- **Mehrdeutigkeiten:** `asr_ambiguities` gehen unverändert in den Snapshot, die Pipeline löst sie nicht auf. `glossary_meta` (`archive_total`, `archive_returned`) bleibt erhalten, damit die Archiv-Kappung sichtbar ist.
- **Zugriff:** `knowledge.load_snapshot(paths)` gibt ein `Snapshot` zurück. Darin stehen `participants`, `glossary` (ein `NarrataGlossary`, damit `GlossaryIndex` und `keyword_terms` unverändert passen), `keyword_entries` und der Kopf. Nachgelagerte Schritte lesen nur das, nie die Rohdatei oder Narrata. Die Wissensschnittstelle darüber baut TOOL-43.

## Daten-Check
- Folgt TOOL-66? *handled*: Der Snapshot enthält Klarnamen und liegt deshalb unter `work/`, das per `.gitignore:28` ausgeschlossen ist. Konsole, Log und Fehlermeldungen nennen Zählungen, Pfade, Feldnamen und Positionen, nie Namen, Aliasse oder Keywords. Das gilt auch für die Warnung bei veralteter Rohdatei: Sie nennt nur, *dass* sich etwas geändert hat.
- Kann Echtes ins Repo? *handled*: Test-Fixtures entstehen inline in den Tests mit erfundenen Namen, wie in `tests/test_glossary.py`. `tests/fixtures/` bekommt keine Datei.
- Fehlermeldungen beim Lesen des Snapshots? *handled*: Sie nennen Datei und Feldpfad mit Index, nie einen Wert, wie bei `narrata._invalid`.

## Contract-Check
- Passt zu IOA-1214/IOA-1215? *handled*: Gelesen wird der Transkriptionskontext 1.x über die vorhandenen Leser. Neu gesendet werden die Query-Parameter `n` und `archive_limit` innerhalb der dokumentierten Grenzen (ios-archiv `docs/transcripts.md`). IOA-1214 (Transcript-Contract v1) bleibt unberührt, der Snapshot ist ein internes Format.
- Narrata-Änderung nötig? N/A, weil der Endpoint so genutzt wird, wie er ist. Anwesenheit kommt mit IOA-1271 (Contract 1.2, additiv) und wird über TOOL-79 gelesen.
- Contract-Version im Snapshot: *handled*: `source.contract_version` wird mitgespeichert. `load_snapshot` prüft sie mit `narrata.check_contract`, damit ein Snapshot aus einem nicht unterstützten Major-Contract abgelehnt wird.

## Resume-Check
- Was passiert bei Abbruch? *handled*: Der Snapshot wird atomar geschrieben (`jsonfile.write_bytes_atomic`). Ein Abbruch hinterlässt entweder den alten oder den neuen Stand, nie eine halbe Datei.
- Wird Fertiges wiederverwendet? *handled*: `transcript snapshot` ohne `--refresh` nutzt einen vorhandenen, lesbaren Snapshot und meldet „reused“. Ein unlesbarer Snapshot bricht ab und verweist auf `--refresh`.
- Gleicher Snapshot beim Resume? *handled*: `transcribe` liest die ID aus dem Snapshot und baut ihn nie selbst. `_reusable` vergleicht die ID, ein Resume mit unverändertem Snapshot nutzt fertige Segmente also wieder. Modell und Settings prüft `BackendIdentity.matches` wie bisher.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt. sha256 und kanonisches JSON kommen aus der stdlib (`hashlib`, `json` mit `sort_keys`), das Lesen läuft über `jsonfile`.

## Format-Check
- Neues Format Snapshot: *handled*: `format_version: 1`. `load_snapshot` lehnt jede andere Version ab und verweist auf `transcript snapshot --refresh`.
- Referenztranskript: *handled*: Neues Feld `asr.knowledge_snapshot_id`, `REFERENCE_FORMAT_VERSION` steigt auf 2. Der Leser akzeptiert 1 und 2, bei 1 ist die ID `None`. Bestehende Dateien bleiben damit lesbar. Hat die Session inzwischen einen Snapshot, werden sie beim nächsten `transcribe` neu transkribiert (siehe Entscheidungen). `docs/referenzformat.md` beschreibt Feld und Versionsregel.
- Manifest, Audio-Metadaten, Diarisierung: N/A, weil sich ihr Format nicht ändert.
- Rohdatei: N/A, weil sie byte-gleich bleibt. `contract_version` gehört Narrata.

## Chunks
### Chunk 1 — Konfiguration und Abrufparameter
- Dateien: `src/transcript/config.py`, `src/transcript/narrata_client.py`, `src/transcript/__main__.py`, `config/example.yaml`, `tests/test_config.py`, `tests/test_narrata_client.py`
- Änderung: `narrata.recent_sessions`, `narrata.archive_limit` mit Grenzprüfung und neue Sektion `knowledge.keyword_budget` (Typen aus `narrata.ENTRY_TYPES`, ganze Zahlen ≥ 0, unbekannter Typ ist ein Fehler). `format_config` gibt beide aus. `context_url`/`fetch_context` hängen `n` und `archive_limit` als Query an.
- Verify: `scripts/check`
- AC: Defaults 3/500 und Budget-Defaults wirken ohne Konfigurationseintrag. Werte außerhalb der Grenzen melden Datei und Schlüssel. Die URL trägt beide Parameter.

### Chunk 2 — Snapshot bauen, schreiben, lesen
- Dateien: `src/transcript/knowledge.py` (neu), `src/transcript/session.py`, `tests/test_knowledge.py` (neu)
- Änderung: `SessionPaths.knowledge_snapshot`. `build_snapshot(paths, budget)` liest Teilnehmende und Glossar über die `narrata`-Leser (`read_raw`, `parse_*`, dafür öffentlich gemacht), wählt die Keywords mit `select_keywords` nach Stufe und Budget, schreibt atomar und gibt den frisch gelesenen Snapshot zurück. `load_snapshot` prüft Version, Session, ID, Contract und Struktur und gibt `Snapshot` zurück. `snapshot_id` ist sha256 über kanonisches JSON ohne `snapshot_id` und `created_at`. `drift(snapshot, paths, budget)` meldet Abweichungen von Rohdatei-sha256 und Budget. `present` kommt erst mit TOOL-79 in den Snapshot, zusammen mit dem Leser.
- Verify: `scripts/check`
- AC: Jeder Eintrag trägt Quelle, Narrata-ID und Relevanzgrund. `pc` steht immer in den Keywords, `session`/`recent` halten das Budget pro Typ ein, `archive` steht nie in den Keywords, bleibt aber im Snapshot. Ambiguitäten und `glossary_meta` überleben einen Rundlauf. Gleicher Inhalt ergibt dieselbe ID, ein geändertes Glossar eine andere. `load_snapshot` funktioniert ohne Rohdatei. Fehlermeldungen enthalten keinen Namen (Test mit eindeutigem Markernamen).

### Chunk 3 — CLI `transcript snapshot` und Doku
- Dateien: `src/transcript/__main__.py`, `README.md`, `tests/test_smoke.py` bzw. die passende CLI-Testdatei
- Änderung: Neuer Befehl `snapshot <key> [--refresh]`. Er baut den Snapshot oder nutzt ihn wieder und gibt nur Zahlen aus: Einträge je Stufe, Keywords je Typ gegen Budget, Ambiguitäten, kurze ID, „built/reused/refreshed“. Ist die Rohdatei neuer oder das Budget anders, warnt er. `transcript context` warnt zusätzlich, wenn ein Snapshot existiert und die neue Rohdatei abweicht. README bekommt den Abschnitt „Wissens-Snapshot“: Relevanzregel als Verweis auf ios-archiv, Budget, Refresh-Ablauf.
- Verify: `scripts/check`
- AC: Erster Aufruf baut. Ein zweiter Aufruf nutzt wieder und behält die ID. Nach einem geänderten `context` warnt der Befehl, behält aber die ID. `--refresh` vergibt eine neue ID. Die Konsole zeigt keine Namen.

### Chunk 4 — Snapshot-ID im Referenztranskript und Wiederverwendung
- Dateien: `src/transcript/reference.py`, `src/transcript/transcription.py`, `src/transcript/__main__.py`, `docs/referenzformat.md`, `tests/test_reference.py`, `tests/test_transcription.py`
- Änderung: `AsrInfo.knowledge_snapshot_id`, `REFERENCE_FORMAT_VERSION = 2`, der Leser akzeptiert 1 (ID `None`) und 2. `transcribe_session(knowledge_snapshot_id=…)` schreibt die ID und vergleicht sie in `_reusable`. `_transcribe` liest die ID per `load_snapshot`, falls ein Snapshot existiert, sonst `None`. `--num-speakers` bleibt unverändert.
- Verify: `scripts/check`
- AC: Eine v1-Datei bleibt lesbar. Gleiche ID heißt Wiederverwendung, andere ID oder neu angelegter Snapshot heißt Neutranskription. Ein Rundlauf erhält die ID. Die Beispiel-JSON in `docs/referenzformat.md` zeigt das Feld.

## Folge-Tickets
- TOOL-79: `num_speakers` bzw. `max_speakers` für die Diarisierung aus der Zahl der Anwesenden ableiten, sobald `present` vorliegt. Die Übergabe aus TOOL-76 landet dort statt in TOOL-41 (Kommentar am Ticket).
- TOOL-43: Die Keywords liest die Wissensschnittstelle aus `knowledge.load_snapshot(...).keyword_entries` über `glossary.keyword_terms`, nicht aus der Rohdatei. Die Snapshot-ID steht schon in der Wiederverwendungsregel, TOOL-43 ergänzt nur `keywords_used`.
- TOOL-44: Die Token-Kappung arbeitet auf den Keyword-Einträgen des Snapshots, die nach dem Budget pro Typ schon vorgekappt sind.
- [kein Ticket: ios-archiv `docs/transcripts.md` beschreibt die Relevanzregel bereits vollständig, eine Narrata-Änderung ist nicht nötig]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Konfiguration, Abrufparameter | no |
| 2 | Snapshot-Modul | no |
| 3 | CLI `snapshot`, README | yes |
| 4 | Referenzformat v2, Wiederverwendung | no |
