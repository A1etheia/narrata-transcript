# TOOL-42 — Validator und Diagnosebericht für das Domänenwissen

## Ziel
Der Wissens-Snapshot einer Sitzung wird nach dem Bauen oder Wiederverwenden geprüft, und das Ergebnis landet in einem Diagnosebericht. Technisch unbrauchbare Daten führen weiterhin zum Abbruch. Fachlich mehrdeutige, aber nutzbare Einträge werden als Warnung gemeldet: geteilte Namen und Aliasse, Hörfehler mit mehreren Zielen, Hörfehler, die einen echten Begriff verdecken, Spielfiguren ohne passenden Glossar-Eintrag. Heute bricht `parse_*` beim ersten technischen Fehler ab. Querbezüge zwischen Einträgen prüft niemand, und eine gespeicherte Diagnose gibt es nicht.

## Ist-Stand
- Technische Prüfung beim Lesen, Abbruch beim ersten Fehler mit Datei und Feldpfad und ohne Wert:
  - doppelte IDs: `narrata._check_unique` für `user_id`, `person_id` sowie Typ und ID im Glossar (`src/transcript/narrata.py:238`, `:242`, `:300`)
  - leere Pflichtfelder: `_is_text` für Name, `display_name` und `variant`
  - ungültige Typen und Werte: `_known` für Typ und Stufe, `is_narrata_id`, `_strings`
  - Mehrdeutigkeit mit unbekanntem oder einzelnem Ziel: `_ambiguity` (`narrata.py:351`)
- Snapshot: Die Herkunft (`source.*`) prüft `knowledge._source` (`src/transcript/knowledge.py:275`). `load_snapshot` (`knowledge.py:164`) prüft Version, Session, ID und Contract und lässt die Blöcke über dieselben Parser laufen. `SnapshotError` beendet `transcript snapshot` mit Exit-Code 2 (`src/transcript/__main__.py:305`), `transcribe` liest den Snapshot über `load_snapshot` (`__main__.py:497`).
- Ungeprüft:
  - leere oder nur aus Leerraum bestehende Aliasse und Hörfehler: `_strings` lässt `""` durch, `GlossaryIndex` überspringt sie still (`src/transcript/glossary.py:56`)
  - Name oder Alias, den mehrere Einträge teilen: `GlossaryIndex.lookup` liefert dann alle Treffer (`glossary.py:62`)
  - Hörfehler, die mehrere Einträge tragen, ohne dass `asr_ambiguities` sie nennt, und genannte Mehrdeutigkeiten, deren Einträge den Hörfehler gar nicht tragen
  - Hörfehler, die Name oder Alias eines anderen Eintrags sind
  - Spielfiguren (`Character.person_id`) ohne Glossar-Eintrag vom Typ `person`, eine falsche Stufe, und `pc`-Einträge ohne aktive teilnehmende Person (Regel in ios-archiv `docs/transcripts.md`, „Relevanz“: `pc` = Figur eines aktiven Teilnehmenden)
- Pfade: `SessionPaths.knowledge_snapshot` (`src/transcript/session.py:120`), `jsonfile.write_atomic` (`src/transcript/jsonfile.py:98`). Die CLI-Tests für `snapshot` liegen in `tests/test_smoke.py:541`, die Fixture-Helfer `context`, `glossary_entry` und `participant` in `tests/test_narrata.py`.

## Entscheidungen
- **Fehler bleiben in den Parsern.** Die technischen Fälle (doppelte IDs, leere Pflichtfelder, falsche Typen, fehlende Herkunft) brechen schon heute mit Datei und Feldpfad ab, und ein fehlerhafter Snapshot wird weder gebaut noch geladen. Damit ist das AK „Kritische technische Fehler verhindern die Nutzung“ erfüllt. Diese Prüfung wird nicht verdoppelt. Bei einem Abbruch schreibt `transcript snapshot` diese eine Meldung als `error` in den Bericht, damit auch dann eine Diagnose vorliegt. Die Parser auf „alle Fehler sammeln“ umzubauen, bringt bei 0,5 Tagen Aufwand und Daten aus einer einzigen Quelle zu wenig.
- **Der neue Validator meldet Warnungen.** `diagnosis.diagnose(participants, glossary)` ist eine reine Funktion ohne I/O. Sie liefert `Finding`s mit `severity`, `code`, `where` (Feldpfad mit Index, z. B. `glossary[3].aliases[1]`) und `entries` (Paare aus Typ und ID). Codes:
  - `empty_term`: leerer Alias oder Hörfehler
  - `shared_term`: Name oder Alias bei mehreren Einträgen, normalisiert über `glossary.normalize`
  - `ambiguous_asr_variant`: Hörfehler bei mehreren Einträgen, von Narrata gemeldet
  - `unreported_asr_variant`: wie oben, aber ohne Eintrag in `asr_ambiguities`
  - `stale_ambiguity`: Eintrag in `asr_ambiguities`, dessen Ziele den Hörfehler nicht tragen
  - `variant_shadows_term`: Hörfehler ist Name oder Alias eines anderen Eintrags
  - `unknown_character`: Spielfigur ohne Glossar-Eintrag
  - `character_not_pc`: Figur einer aktiven teilnehmenden Person, deren Eintrag nicht `pc` ist
  - `orphan_pc`: `pc`-Eintrag ohne Figur einer aktiven teilnehmenden Person

  Alle Codes sind Warnungen, weil die Daten technisch nutzbar bleiben und die Auswahl beim Review liegt. Der Typ `Finding` kennt trotzdem `error`, damit der Bericht beide Stufen gleich führt.
- **Unterschiede beim Vergleichen gehen an `unreported_asr_variant`.** Narrata vergleicht Hörfehler ohne Groß-/Kleinschreibung, hier vergleicht `glossary.normalize` (casefold, NFC, Leerraum). In Grenzfällen (ß, Leerraum) kann die Pipeline deshalb eine Mehrdeutigkeit finden, die Narrata nicht gemeldet hat. Das ist eine Warnung und kein Fehler.
- **Der Bericht enthält keine Namen.** Ein Eintrag wird über Typ, Narrata-ID und Feldpfad benannt, die Quelle über die Snapshot-Datei und `source.file`. Das erfüllt das AK „benennt Eintrag und Quelle“. Den Bericht kann man außerdem in ein Ticket kopieren, ohne ihn vorher zu prüfen.
- **Bericht als Datei und auf der Konsole.** Die Datei liegt unter `work/<key>/narrata/diagnosis.json` (`SessionPaths.knowledge_diagnosis`) und enthält `format_version: 1`, `created_at`, `snapshot_id` (`null` bei Abbruch), `source`, Zähler für `errors` und `warnings` und `findings`. `transcript snapshot` schreibt sie bei jedem Lauf neu, bei Erfolg wie bei Abbruch, damit nie ein veralteter Bericht liegen bleibt. Die Konsole zeigt `diagnosis: N error(s), M warning(s)`, die Zähler je Code und höchstens 10 Befundzeilen, danach einen Verweis auf die Datei. Warnungen ändern den Exit-Code nicht.
- **Nur `transcript snapshot` prüft.** `transcribe` lädt den Snapshot weiter ohne Validator, denn Warnungen sollen nicht bei jedem Lauf erscheinen, und Fehler fängt `load_snapshot` schon ab. `transcript context` bleibt unverändert, der Snapshot ist der vorgesehene Prüfpunkt vor der Transkription.

## Daten-Check
- Folgt TOOL-66? *handled*: Befunde, Konsole und `diagnosis.json` nennen Code, Feldpfad, Typ und Narrata-ID, nie Namen, Aliasse oder Hörfehler. `diagnosis.json` liegt unter `work/` (`.gitignore`).
- Kann Echtes ins Repo, ein Log oder eine Fehlermeldung? *handled*: Tests bauen die Daten inline mit erfundenen Namen über die Helfer in `tests/test_narrata.py`. Ein `MARKER`-Test stellt sicher, dass kein Name in Befund, Datei oder Konsole erscheint. `tests/fixtures/` bekommt keine Datei.

## Contract-Check
- Passt zu IOA-1214/IOA-1215? *handled*: Gelesen werden nur die schon geprüften Blöcke aus dem Snapshot (Kontext 1.x). Die Regeln für `pc` und `asr_ambiguities` folgen ios-archiv `docs/transcripts.md`. IOA-1214 bleibt unberührt.
- Narrata-Änderung nötig? N/A, weil der Validator die gelieferten Daten nur prüft. Meldet er bei echten Daten `unreported_asr_variant` oder `orphan_pc`, wäre das ein Befund für ios-archiv, den wir dann einzeln als Ticket anlegen.

## Resume-Check
- N/A, weil der Schritt kurz läuft, kein Modell braucht und deterministisch ist. Der Bericht wird atomar geschrieben (`write_atomic`) und bei jedem `snapshot`-Lauf neu erzeugt. Der Snapshot und seine ID ändern sich durch die Diagnose nicht.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt. Es reichen die stdlib und die vorhandenen Funktionen `glossary.normalize` und `jsonfile.write_atomic`.

## Format-Check
- Neues Format `diagnosis.json`: *handled*: `format_version: 1`. Kein Schritt liest die Datei, sie wird bei jedem Lauf ersetzt. Bestehende Artefakte gibt es nicht.
- Snapshot und Referenzformat: N/A, weil ihre Formate unverändert bleiben und `snapshot_id` gleich bleibt.

## Chunks
### Chunk 1 — Validator
- Dateien: `src/transcript/diagnosis.py` (neu), `tests/test_diagnosis.py` (neu)
- Änderung: `Finding` (frozen dataclass: `severity`, `code`, `where`, `entries`) und `diagnose(participants, glossary) -> tuple[Finding, ...]` mit den neun Codes. Die Reihenfolge ist deterministisch, nach Glossar-Position. Die Begriffe vergleicht `glossary.normalize`.
- Verify: `scripts/check`
- AC: Ein gültiger Kontext ohne Querkonflikte ergibt keinen Befund. Jeder Code hat einen Test, der ihn auslöst. Ein von Narrata gemeldeter Hörfehler ergibt nur `ambiguous_asr_variant`, ein ungemeldeter zusätzlich `unreported_asr_variant`. Ehemalige Teilnehmende lösen `character_not_pc` nicht aus. Kein Befund enthält den `MARKER`-Namen.

### Chunk 2 — Bericht, CLI und Doku
- Dateien: `src/transcript/session.py`, `src/transcript/diagnosis.py`, `src/transcript/__main__.py`, `README.md`, `tests/test_diagnosis.py`, `tests/test_smoke.py`
- Änderung: `SessionPaths.knowledge_diagnosis` und `write_report(paths, snapshot | None, findings, error | None)`, ein Fehler wird zum Befund mit `severity: error`. `_snapshot` ruft nach Erfolg `diagnose` auf und schreibt den Bericht. Nach `SnapshotError` oder `NarrataContextError` schreibt es den Fehlerbericht, dann wie bisher Exit-Code 2. Die Konsole zeigt die Zusammenfassung, höchstens 10 Zeilen und den Pfad. README: Unterabschnitt „Diagnose“ unter „Wissens-Snapshot“ mit den Codes, der Trennung Fehler/Warnung und der Datei, dazu die Zeile in der Verzeichnisübersicht (`README.md:278`).
- Verify: `scripts/check`
- AC: Ein gültiger Snapshot ergibt `0 error(s)` und Exit-Code 0. Bei Warnungen bleibt Exit-Code 0, und die Konsole nennt sie mit Feldpfad und ID. Ein kaputter Kontext ergibt Exit-Code 2, und `diagnosis.json` enthält einen `error` mit dem Pfad. Ein neuer Lauf ersetzt den alten Bericht. Konsole und Datei enthalten keinen Namen.

## Folge-Tickets
- [kein Ticket: Ein Narrata-Befund (`unreported_asr_variant`, `orphan_pc`) bekommt erst ein IOA-Ticket, wenn er bei echten Daten auftritt]
- TOOL-68: Referenzen auf unbekannte Sprecher prüfen, sobald Sprecherzuordnungen entstehen; TOOL-42 hat dafür noch keine Daten.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Validator `diagnosis.diagnose` | no |
| 2 | Bericht, CLI `snapshot`, README | no |
