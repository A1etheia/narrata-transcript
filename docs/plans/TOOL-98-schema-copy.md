# TOOL-98 — Schema-Kopie des JSON-Contracts auf Contract 1.3 nachziehen

## Ziel
Die Schema-Kopie entspricht wieder Narratas Stand (ios-archiv `b1fa375ef`, Contract 1.3), und `test_the_copy_equals_narratas_schema` ist grün. Der Export bleibt bei 1.0/1.1 und byte-gleich. `contract.validate` darf nach der Aktualisierung nicht laxer werden als bisher.

## Ist-Stand
- `src/transcript/contract.py:43-51`: `CONTRACT_VERSION = "1.1"`, `SCHEMA_SOURCE` = ios-archiv `e8bfb9702`, `SCHEMA_SHA256 = 019ae2df…`. Narratas aktuelles Schema hat `58f9fe56…`. Das letzte Commit am Schema ist `b1fa375ef` (IOA-1300), davor kam `cad8c0741` (IOA-1224).
- `src/transcript/contract.py:1-31` (Docstring) und `:79-98` (`validate`): Schema plus die Regeln von 1.0/1.1 (`_rules`, `_recording_rules`).
- **Das neue Schema ist laxer:** `passages[].start`/`end`, `confidence_tier`, `markers[].at`, `source.duration_seconds`/`audio_sha256` und `pipeline` dürfen jetzt `null` sein, und das ID-Muster erlaubt `u-<6>-<slug>`. Die Einschränkung „nur bei `source.kind = upload`“ steht nur in Narratas Regeln jenseits des Schemas (`docs/transcript-contract.md`). Mit der bloßen Kopie würde eine Pipeline-Datei mit `start: null` die Prüfung bestehen, und `rendering._passage` (`src/transcript/rendering.py:203`, `seconds_to_ms(passage["start"])`) würde abstürzen.
- `src/transcript/rendering.py:110-119` `load_export`: prüft nur mit `validate`.
- `src/transcript/export.py:53-58,189,324-328`: nutzt `SINGLE_RECORDING_VERSION`/`RECORDINGS_SINCE`, nicht `CONTRACT_VERSION`. Der Export hängt also nicht an der Konstante, die steigt.
- `tests/test_contract.py:26-33,65-72`: Pfad zur Narrata-Kopie ist `REPO_ROOT.parent / "ios-archiv"`. In einem Orca-Worktree fehlt der Nachbarordner, dann wird der Test übersprungen. Rot ist er nur im Haupt-Checkout. `:70-72` setzt `multi_fixture` mit `CONTRACT_VERSION` gleich.
- `tests/fixtures/contract/session-v1.json`, `session-v1-multi.json`: byte-gleich mit ios-archiv `origin/main`. Neu in Narrata sind `session-v1-classified.json` (1.2), `session-v1-upload-timed.json` und `session-v1-upload-untimed.json` (1.3).
- `README.md:631`: zählt die Regeln von `contract.validate` auf.

## Entscheidungen
- **Schema 1:1 kopieren** von ios-archiv `b1fa375ef`. `SCHEMA_SOURCE`/`SCHEMA_SHA256` nachziehen, `CONTRACT_VERSION = "1.3"` („latest minor this copy knows“). Der Test in `:70-72` vergleicht `multi_fixture` künftig mit `RECORDINGS_SINCE`.
- **Narratas Regeln teilweise portieren, und zwar nur die, die das Lockern des Schemas auffangen oder Versionen absichern:**
  1. `null` in Zeiten, `confidence_tier`, `markers[].at`, Audio-Feldern oder `pipeline` nur bei `source.kind = upload`, eine Meldung je Datei mit Feldnamen und ID der ersten Passage.
  2. `source.kind`/`source.format` nur ab 1.3; `format` genau dann, wenn `kind = upload`.
  3. `layers.it_ot`/`stats.it_ot` nur ab 1.2.

  Grund: Nur so bleibt die Prüfung für Pipeline-Dateien so streng wie vorher. Die Detailregeln zu IT/OT (Blöcke, Spans, Modus) und zum Upload (Zeitigkeit, `u-`/`p-`-IDs, keine Recordings) portiere ich nicht. Die Pipeline schreibt keines dieser Felder, und Narrata prüft sie beim Import (`transcript:validate`). Der Docstring sagt das ausdrücklich.
- **Rendering verweigert Uploads:** `load_export` bricht bei `source.kind = upload` mit einer eigenen Meldung ab (ohne Wert). `transcript.txt` rendert nur Pipeline-Exporte mit Zeiten. Ein gültiger ungetimter Upload würde sonst an `start: null` scheitern.
- **Neue Narrata-Fixtures als Kopie aufnehmen** (`classified`, `upload-timed`, `upload-untimed`). Damit beweist ein Test, dass `validate` jede von Narratas Referenzdateien ohne Meldung akzeptiert, also keine Fehlalarme durch die portierten Regeln. Die zwei bestehenden Kopien bleiben unverändert.

## Daten-Check
- Fixtures: handled — die drei neuen Dateien erzeugt Narratas Generator `build-session-fixture.php` aus einem erfundenen Abend, keine echten Sitzungsdaten (TOOL-66).
- Meldungen: handled — die neuen Regeln nennen JSON-Pfad, Feldnamen und gültige Passagen-ID wie `_passage_note`, nie einen Wert. Ein Test mit `SECRET` prüft das für die `null`-Regel.
- Logs, Aufnahmen: N/A, weil keine Logausgabe dazukommt und keine Aufnahme gelesen wird.

## Contract-Check
- IOA-1214-Stand: handled — Kopie gleich ios-archiv `b1fa375ef` (Contract 1.3), per SHA und Vergleichstest.
- Export-Version: handled — der Export schreibt weiter 1.0 (eine Aufnahme) bzw. 1.1 (mehrere). `export.py` bleibt unverändert, und Narrata akzeptiert ältere Minors.
- Narrata-Änderung: N/A, weil nur die Pipeline-Kopie nachzieht. Kein IOA-Ticket nötig.

## Format-Check
- Version: handled — `CONTRACT_VERSION` 1.1 → 1.3 (nur bekannter Stand der Kopie). Das Ausgabeformat hat keine neue Version.
- Bestehende Artefakte: handled — vorhandene `output/<s>/transcript.json` (1.0/1.1) bleiben gültig, weil die neuen Regeln nur `null`, `kind`/`format` und `it_ot` betreffen. Der Test „alle Narrata-Fixtures gültig“ deckt 1.0 und 1.1 mit ab.

## Resume-Check
N/A, weil es kein langlaufender oder modellgestützter Schritt ist.

## Dependency-Check
N/A, weil keine neue Abhängigkeit dazukommt (`jsonschema` ist schon da, das Schema nutzt nur Draft-2020-12-Mittel wie `dependentRequired`).

## Chunks
### Chunk 1 — Schema-Kopie, Fixtures und Regeln
- Dateien: `src/transcript/contracts/transcript-v1.schema.json`, `src/transcript/contract.py`, `tests/test_contract.py`, `tests/fixtures/contract/session-v1-{classified,upload-timed,upload-untimed}.json`
- Änderung: Schema und drei Fixtures aus `/home/sabine/dev/workspace/ios-archiv` (Stand `origin/main`) per `cp` kopieren. Konstanten nachziehen. Neue `_null_rules`/Versionsregeln (`_since(data, "1.2")`-Helfer neben `_recording_rules`). Docstring: Regel-Liste ergänzen, nicht portierte Regeln nennen, Kopf „1.2: IOA-1224, 1.3: IOA-1300“. Tests: alle fünf Narrata-Fixtures gültig; Pipeline-Datei mit `start: null` gibt eine Meldung ohne Wert; `confidence_tier: null` und `pipeline: null` ebenso; `source.kind` in 1.1 abgewiesen; `format` ohne `kind = upload` abgewiesen; `layers.it_ot` in 1.1 abgewiesen.
- Verify: `scripts/check`; dazu `cmp src/transcript/contracts/transcript-v1.schema.json /home/sabine/dev/workspace/ios-archiv/ios-archiv-backend/resources/contracts/transcript-v1.schema.json`, weil der Vergleichstest im Worktree übersprungen wird.
- AC: Kopie gleich Narrata 1.3; keine laxere Prüfung für Pipeline-Dateien; Narratas Fixtures ohne Meldung.

### Chunk 2 — Rendering verweigert Uploads, README
- Dateien: `src/transcript/rendering.py`, `tests/test_rendering.py`, `README.md`
- Änderung: `load_export` wirft `ExportUnreadable` bei `source.kind = upload` („not rendered, an upload has no pipeline timeline“), Test mit der `upload-untimed`-Fixture. In README :631 die neuen Regeln aufzählen und den Satz zur Schema-Herkunft um Contract 1.3 ergänzen. Der Export bleibt bei 1.0/1.1.
- Verify: `scripts/check`; im Haupt-Checkout `transcript export` und `transcript txt` für die Pilot-Sitzung vor und nach dem Branch ausführen und per `sha256sum` vergleichen (byte-gleich, Daten bleiben in `output/`).
- AC: Export byte-gleich, schreibt keine 1.2/1.3-Felder; Rendering bricht bei einem Upload klar ab statt abzustürzen.

## Folge-Tickets
- Der Vergleichstest wird in Worktrees ohne `ios-archiv` daneben still übersprungen [kein Ticket: bekannt und bewusst, im Haupt-Checkout läuft er; eventuell bei Bedarf eine `NARRATA_REPO`-Variable].
- IT/OT-Detailregeln portieren, wenn die Pipeline 1.2 schreibt [kein Ticket: gehört zu TOOL-71/TOOL-75, die die Schicht erzeugen würden; die wissensbasierte IT/OT-Einordnung liegt bei Narrata (IOA-1297)].

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schema-Kopie, Fixtures, `contract.validate`-Regeln | no |
| 2 | Rendering-Abbruch bei Uploads, README | no |
