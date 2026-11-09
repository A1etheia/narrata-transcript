# TOOL-51 — Bereinigtes Transkript aus dem JSON-Export als TXT rendern

## Ziel
`transcript txt <gruppe>/<ordinal>` schreibt `output/<s>/transcript.txt` als lesbares UTF-8-Transkript. Die Datei entsteht ausschließlich aus dem JSON-Export `output/<s>/transcript.json` (TOOL-69). Heute gibt es nur JSON für Narrata und den Bericht ohne Text. Eine Fassung zum Lesen und Archivieren fehlt. Der Lesekern (Contract-Datei → Sprecherabsätze mit Markierungen) ist so geschnitten, dass TOOL-52 (DOCX) ihn übernimmt.

## Ist-Stand
- Export: `src/transcript/export.py:158` `write_export` schreibt `paths.transcript_export` (`src/transcript/session.py:172`), sortierte Keys, `ensure_ascii=False`. Passagen chronologisch. Marker nur `unintelligible`/`speaker_unclear`/`crosstalk` mit `at` in Sekunden (`export.py:240`). Offene Passagen haben `review_status: open` und keinen Marker (`export.py:66`). Unverständliche Passagen haben `text: ""` (`export.py:228`).
- Sprecher: `speakers.<label>` ist `{participant_id, display_name}` oder `null` (`export.py:198`). `display_name` kann `null` sein, wenn die Person im Snapshot fehlt.
- Prüfung: `src/transcript/contract.py:69` `validate` prüft Schema und Zusatzregeln. Die Meldungen nennen nie einen Wert.
- Markierungen: `src/transcript/markers.py:37` `MARKER_LABELS`, `markers.py:78` `marker_label(Marker)` → `[unverständlich 01:42:17]`. Zeiten werden mit `timecode.format_clock` (`src/transcript/timecode.py:26`) auf die Sekunde abgerundet. `rendered_text` (`markers.py:86`) arbeitet auf Blöcken der Arbeitsfassung und ist nach TOOL-69 für Renderer nicht mehr die Quelle. `MARKER_KINDS` zählt im Bericht (`src/transcript/report.py:199`) und darf deshalb keinen neuen Wert bekommen.
- Lesen und Schreiben: `jsonfile.read_object` (`src/transcript/jsonfile.py:19`), `jsonfile.write_bytes_atomic` (`jsonfile.py:140`), so wie `report.md` es nutzt (`report.py:432`).
- CLI: `_export` (`src/transcript/__main__.py:978`) ist das Muster: nur Zahlen, Codes und den Pfad ausgeben, Exit 2 bei Fehlern. Die Subcommands werden in `__main__.py:240`–`261` registriert.
- Konfiguration: `Config` (`src/transcript/config.py:131`), `load_config` (`config.py:163`) mit `_section`/`_choice`, `format_config` (`config.py:297`), README-Tabelle „Konfiguration“.
- Testdaten: `tests/fixtures/contract/session-v1.json` (Narrata-Fixture, 320 erfundene Passagen, alle Marker-Typen außer `gap`, alle `review_status`). Dazu die Export-Helfer in `tests/test_export.py`.

## Entscheidungen
- **Quelle:** nur `output/<s>/transcript.json`. Sie wird gelesen und vor dem Rendern mit `contract.validate` geprüft. Bei einem Verstoß wird nichts geschrieben. Kein Zugriff auf `work/`, kein `working.load_current`. So verlangt es die AK von TOOL-69.
- **Layout:** ein Absatz je Sprecherwechsel, Absätze durch eine Leerzeile getrennt (Entscheidung der Nutzerin). Ein Wechsel liegt vor, wenn sich die Person (`participant_id`) ändert, bei nicht zugeordneten Sprechern das Label. Zwei Labels derselben Person hintereinander bilden also einen Absatz. Die Passagen eines Absatzes werden mit einem Leerzeichen verbunden.
- **Sprecher:** zugeordnet → `display_name`. Nicht zugeordnet (`null`) → `<label> (nicht zugeordnet)`. Zugeordnet ohne Namen → `<label> (zugeordnet, ohne Namen)`. So sind Person und Label immer unterscheidbar.
- **Zeitstempel:** `render.timestamps` mit `turn` (Default) oder `passage`. `turn` heißt: Kopfzeile `[HH:MM:SS] Name`, Text darunter. `passage` heißt: Kopfzeile `Name`, darunter jede Passage in einer eigenen Zeile `[HH:MM:SS] Text`. Die Zeit ist `start` der Passage, auf die Sekunde abgerundet wie bei den Markierungen.
- **Markierungen:** offene Passage → `[unklar HH:MM:SS]` mit `start` der Passage. Danach folgen die `markers[]` in Dateireihenfolge, jeweils mit ihrem `at`. Die Reihenfolge ist dieselbe wie bei `rendered_text`: erst zum Text, dann zum Sprecher. `gap` wird `[Lücke HH:MM:SS]` (Entscheidung der Nutzerin). Die Beschriftungen kommen zentral nach `markers.py` (`CONTRACT_MARKER_LABELS`, `contract_marker_label(type, at_ms)`). `marker_label` und das neue Label teilen sich einen Formatierer. `MARKER_KINDS` bleibt unverändert. Ein Passagentext von `""` erscheint als Markierung allein.
- **Wortlaut:** Der Text wird nicht verändert und nicht Unicode-normalisiert. Nur Zeilenumbrüche und Leerraumfolgen im Text werden zu einem Leerzeichen, damit die Zeilenstruktur hält.
- **Keine Metadaten im Text:** keine Kopfzeile mit Sitzung, Datum, Pipeline oder Statistik. Die Datei liegt neben `report.md` und `transcript.json`, die diese Angaben tragen.
- **Datei:** `paths.transcript_text` → `output/<s>/transcript.txt`, UTF-8 ohne BOM, `\n`, abschließender Zeilenumbruch, atomar ersetzt. Die Datei wird immer überschrieben, weil sie abgeleitet ist und niemand sie von Hand bearbeitet. Kein Zeitstempel: gleiche JSON-Datei und gleiche Regel ergeben eine byte-gleiche Datei.
- **Befehl:** `transcript txt <s>`, analog zu `report` und `export`. TOOL-52 bekommt entsprechend `transcript docx`. Konsole: `txt: <n> passage(s), <m> paragraph(s), <k> open` und `wrote <pfad>`. Exit 0 auch mit offenen Passagen, Exit 2 bei Fehler oder Verweigerung.
- **Modul:** `src/transcript/rendering.py`. `load_export(paths)` liest und prüft. `paragraphs(document)` liefert Absätze aus Sprecheranzeige und Passagen mit Zeit und gerendertem Text, gemeinsam für TXT und DOCX. `render_txt(paragraphs, rule)` baut den Text, `write_txt` schreibt ihn.

## Daten-Check
- *handled —* Die TXT-Datei enthält Text und Anzeigenamen. Sie liegt nur unter `output/`, und `.gitignore` schließt `output/` in jeder Tiefe aus (`tests/test_gitignore.py`). `*.txt` ist nicht global ausgeschlossen, die Datei liegt aber nie außerhalb von `output/`.
- *handled —* Die Konsole zeigt nur Zahlen und den Pfad. Fehlermeldungen nennen Pfad, JSON-Pfad, Regel und Passagen-ID wie in `contract.validate`, nie Text, Namen oder User-IDs. Es wird nichts geloggt.
- *handled —* Die Tests nutzen die erfundene Narrata-Fixture und synthetische Export-Dokumente aus `tests/test_export.py`. Es kommen keine neuen Fixtures mit echten Daten dazu.
- *handled —* Der Befehl liest nur `transcript.json`. Arbeits- und Quelldaten bleiben unberührt (AK „verändert keine Arbeits- oder Quelldaten“). Ein Test prüft, dass `work/` und `transcript.json` byte-gleich bleiben.

## Contract-Check
- *handled —* Gelesen wird Contract v1 (IOA-1214), geprüft gegen die Schema-Kopie (`contract.SCHEMA_SOURCE`). Eine unbekannte Major wird wie in Narrata verweigert.
- *handled —* Alle Marker-Typen des Schemas werden beschriftet, `gap` eingeschlossen. Die drei `review_status`-Werte außer `open` tragen keine Markierung.
- *N/A because* Narrata braucht keine Änderung: Der Renderer liest die Datei nur, nichts geht zu Narrata, und es entsteht kein IOA-Ticket.

## Resume-Check
*N/A because* der Schritt kurz, deterministisch und modellfrei ist. Ein Abbruch hinterlässt durch das atomare Schreiben keine halbe Datei, und ein erneuter Lauf erzeugt dieselbe Datei.

## Dependency-Check
*N/A because* keine neue Abhängigkeit dazukommt. Nur Standardbibliothek und das vorhandene `jsonschema`.

## Format-Check
- *N/A because* die TXT-Datei ein Leseformat ohne Versionsfeld ist. Ihr Aufbau steht im README.
- *N/A because* `render.timestamps` ein neuer optionaler Schlüssel mit Default ist. Bestehende Konfigurationen bleiben gültig.

## Chunks
### Chunk 1 — Contract-Marker beschriften
- Dateien: `src/transcript/markers.py`, `tests/test_markers.py`, README „Markierungen“
- Änderung: `CONTRACT_MARKER_LABELS` (die drei Contract-Typen aus `MARKER_LABELS` plus `gap: "Lücke"`) und `contract_marker_label(type, at_ms)`. Ein Formatierer `_bracket(label, at_ms)` wird mit `marker_label` geteilt. Ein unbekannter Typ ergibt `ValueError`. README: Zeile `gap` in der Tabelle, Hinweis „kommt nur aus dem Contract, die Pipeline schreibt es nicht“.
- Verify: `scripts/check`
- AC: Jeder Marker-Typ des Schemas hat eine Beschriftung. Ein Test vergleicht mit dem Enum aus `contract.load_schema()`. `marker_label` liefert unverändert dieselben Ausgaben.

### Chunk 2 — Konfiguration `render.timestamps`
- Dateien: `src/transcript/config.py`, `config/example.yaml`, `tests/test_config.py`, README „Konfiguration“
- Änderung: Abschnitt `render` mit `timestamps: turn | passage` (Default `turn`), `Config.render_timestamps`, aufgenommen in `format_config`. Unbekannte Schlüssel und Werte werden wie bisher abgelehnt.
- Verify: `scripts/check`
- AC: Default, gültige Werte und ein ungültiger Wert mit Meldung (Datei und Schlüssel) sind getestet. `transcript config` zeigt den Wert.

### Chunk 3 — Renderer
- Dateien: `src/transcript/rendering.py` (neu), `src/transcript/session.py` (`transcript_text`), `tests/test_rendering.py` (neu)
- Änderung: `load_export`, `paragraphs`, `render_txt`, `write_txt` wie unter Entscheidungen beschrieben. `ExportUnreadable(DataFileError)` für eine fehlende, unlesbare oder ungültige Datei.
- Verify: `scripts/check`
- AC (Tests auf der Narrata-Fixture und auf Dokumenten aus `export.build`):
  - Reihenfolge und Wortlaut: Die Passagentexte in Dateireihenfolge, verbunden, entsprechen dem Text ohne Markierungen und Kopfzeilen.
  - Umlaute, `ß`, Emoji und kombinierende Zeichen bleiben byte-gleich, die Datei ist UTF-8 ohne BOM.
  - `[unklar …]` bei `open`, `[unverständlich …]` ohne Text, `[Sprecher unklar …]`, `[durcheinander …]`, `[Lücke …]`.
  - Person, nicht zugeordnetes Label und zugeordnet ohne Namen sind unterscheidbar. Zwei Labels einer Person ergeben einen Absatz.
  - `turn` und `passage` liefern das beschriebene Layout.
  - Zweimal rendern ergibt dieselben Bytes. Eine ungültige Datei oder eine fremde Major wird verweigert, ohne etwas zu schreiben und ohne einen Wert zu zitieren.

### Chunk 4 — Befehl `transcript txt` und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, README (neuer Abschnitt „TXT-Ausgabe“ nach „JSON-Export“, Verzeichnisstruktur `transcript.txt`, Verweis in „JSON-Export“)
- Änderung: Subcommand `txt` mit `--config`, `_txt` nach dem Muster von `_export`.
- Verify: `scripts/check`, dazu `transcript txt --help`
- AC: Der Smoke-Test exportiert und rendert eine synthetische Session. Exit 0 mit offenen Passagen, Exit 2 ohne `transcript.json` mit Hinweis auf `transcript export`. Die Konsole zeigt keinen Text und keinen Namen. `work/` und `transcript.json` bleiben unverändert.

## Folge-Tickets
- Übergabe an TOOL-52: `rendering.paragraphs` und `markers.contract_marker_label` wiederverwenden, Befehl `transcript docx`, gleiche Regel `render.timestamps`. `[kein Ticket: Kommentar an TOOL-52 und Roadmap-Hinweis über /close-ticket]`
- Gegenprobe des Exports gegen `transcript:validate`/`transcript:import` steht weiter aus. `[kein Ticket: läuft schon unter TOOL-58, betrifft TOOL-51 nicht]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Contract-Marker-Beschriftungen in `markers.py` | no |
| 2 | Konfiguration `render.timestamps` | no |
| 3 | Renderer `rendering.py` | no |
| 4 | CLI `transcript txt`, README | no |
