# TOOL-52 — Bereinigtes Transkript aus dem JSON-Export als DOCX rendern

## Ziel
`transcript docx <gruppe>/<ordinal>` schreibt `output/<s>/transcript.docx`, ein gut lesbares Word-Dokument für Archiv und redaktionelle Arbeit. Es entsteht ausschließlich aus dem JSON-Export `output/<s>/transcript.json` (TOOL-69). Heute gibt es zum Lesen nur die TXT-Datei (TOOL-51). Sie trägt keinen Kopf und setzt Sprecher und Markierungen nicht visuell ab.

## Ist-Stand
- Lesekern aus TOOL-51: `src/transcript/rendering.py:74` `load_export` liest `transcript.json` und prüft es mit `contract.validate`. `rendering.py:86` `paragraphs` liefert `Paragraph(speaker, lines)` je Sprecherwechsel. `rendering.py:50` `Line(start_ms, text, markers)` hält Text und Marker-Beschriftungen getrennt, damit ein Dokument-Renderer sie absetzen kann (`rendering.py:53`). `rendering.py:107` `speaker_name` liefert `<label> (nicht zugeordnet)` bzw. `<label> (zugeordnet, ohne Namen)`.
- `render_txt` (`rendering.py:115`) trägt die Layout-Regel `turn`/`passage`. `write_txt` (`rendering.py:133`) nutzt `jsonfile.write_bytes_atomic` (`src/transcript/jsonfile.py:140`).
- Marker-Beschriftungen: `markers.contract_marker_label` und `marker_label` (`src/transcript/markers.py`), Zeit über `timecode.format_clock`.
- Kopfdaten im Contract: `session` mit `group` (Narrata-ID, int), `ordinal`, `play_session_id`, `session_date` (ISO oder `null`). `pipeline` mit `backend`, `model`, `knowledge_snapshot_id` (oder `null`), dazu `contract_version`. Einen Sitzungstitel kennt Contract v1 nicht.
- Pfade: `SessionPaths.transcript_text` (`src/transcript/session.py:177`). Dort kommt `transcript_document` dazu.
- CLI: `_txt` (`src/transcript/__main__.py:1020`) ist das Muster. Registrierung `__main__.py:247`, Dispatch `__main__.py:319`.
- Konfiguration: `Config.render_timestamps` (`src/transcript/config.py:165`).
- Abhängigkeiten: nur `pyyaml`, `jsonschema` (`pyproject.toml`). Eine DOCX-Bibliothek ist nicht installiert.
- Tests: `tests/test_rendering.py` mit den Helfern `passage`/`document` und der Narrata-Fixture `tests/fixtures/contract/session-v1.json`. Smoke-Test für `txt` in `tests/test_smoke.py`.

## Entscheidungen
- **Erzeugung mit der Standardbibliothek** (Entscheidung der Nutzerin): Ein minimales WordprocessingML-Paket wird per `zipfile` geschrieben. Es besteht aus `[Content_Types].xml`, `_rels/.rels`, `word/document.xml`, `word/styles.xml`, `word/_rels/document.xml.rels` und `docProps/core.xml` mit festen Werten. So kommt keine neue Abhängigkeit dazu, und wie bei TXT ergibt eine gleiche JSON-Datei mit gleicher Regel dieselben Bytes (feste Zip-Zeit 1980-01-01, feste Eintragsreihenfolge, `ZIP_DEFLATED`). python-docx scheidet aus, weil es Zip-Einträge mit der aktuellen Zeit stempelt.
- **Text sicher ins XML:** Alle Texte gehen über `xml.sax.saxutils.escape`. In XML 1.0 verbotene Steuerzeichen werden entfernt, sonst wäre die Datei ungültig. Das ist die einzige Abweichung vom Wortlaut, und sie trifft nur Zeichen, die Word gar nicht darstellen kann. Runs bekommen `xml:space="preserve"`.
- **Kopf:** Die Überschrift (Stil `Title`) lautet `Transkript <gruppe>/<ordinal>` aus dem Sitzungsschlüssel, den der Befehl ohnehin bekommt. Das ist kein zweiter Datenpfad. Contract v1 hat keinen Titel, und die Narrata-Gruppen-ID allein sagt niemandem etwas. Darunter folgt eine Zeile `Sitzung <ordinal> · <TT.MM.JJJJ>` (ohne Datum, wenn `session_date` `null` ist). Danach ein kleiner Metadatenblock (Stil `Meta`, klein, grau): `Backend: <backend> / <model>`, `Wissens-Snapshot: <id oder „keiner“>`, `Contract: <contract_version>`, `Narrata: Gruppe <group>, Spielsitzung <play_session_id>`. Der Block ist immer dabei und braucht keinen Schalter.
- **Absätze:** `rendering.paragraphs` unverändert. `render.timestamps` gilt wie bei TXT. Bei `turn` gibt es einen Sprecherabsatz `[HH:MM:SS] Name` und darunter einen Textabsatz. Bei `passage` gibt es den Sprecherabsatz `Name` und darunter je Passage einen Absatz `[HH:MM:SS] Text`. Zeitstempel stehen grau in einem eigenen Run.
- **Sprecher sichtbar unterscheidbar:** Der Sprecherabsatz hat den Stil `Speaker` (fett, mit Abstand davor, `keepNext`). Eine zugeordnete Person erscheint als Name in Schwarz. Ein Label (nicht zugeordnet oder ohne Namen) erscheint kursiv in einem eigenen Zeichenstil `SpeakerLabel`. Dafür braucht `Paragraph` die Information, ob ein Name erscheint: ein neues Feld `named: bool`, gesetzt in `paragraphs`. Eine zugeordnete Person ohne Namen zählt als Label, weil sie als Label erscheint. TXT bleibt byte-gleich.
- **Markierungen nicht versteckt:** Die Beschriftungen aus `Line.markers` stehen in einem eigenen Run mit dem Zeichenstil `Marker` (kursiv, dunkelrot, Hervorhebung hellgrau). Damit fallen sie auch im Schwarzweißdruck auf. Die Reihenfolge und der Wortlaut sind dieselben wie in TXT.
- **Modul:** neues `src/transcript/docx_render.py` (nicht `docx.py`, um keine Verwechslung mit python-docx zu provozieren) mit `render_docx(key, document, found, rule) -> bytes` und `write_docx(paths, data)`. `rendering.py` bleibt der gemeinsame Lesekern. So hält sich der XML-Teil aus dem TXT-Pfad heraus. Nach `/simplify` liegt auch das Layout dort: `rendering.layout(found, rule)` liefert je Sprecher einen `Block` aus Kopf- und Textzeilen mit typisierten `Segment`s (`time`, `name`, `label`, `text`, `marker`), mit einem Leerzeichen dazwischen. `render_txt` verbindet sie zu Text, DOCX ordnet jeder Art einen Zeichenstil zu. So können TXT und DOCX nicht auseinanderlaufen. Ein Test prüft, dass die DOCX-Absätze den TXT-Zeilen entsprechen.
- **Befehl:** `transcript docx <s>` nach dem Muster von `_txt`. Die Konsole zeigt `docx: <n> passage(s), <m> paragraph(s), <k> open` und `wrote <pfad>`. Exit 0 auch mit offenen Passagen, Exit 2 bei Fehler.
- **Datei:** `output/<s>/transcript.docx` neben `report.md`. Sie wird atomar ersetzt und immer überschrieben, weil sie abgeleitet ist.

## Daten-Check
- *handled —* Die DOCX enthält Text und Anzeigenamen. Sie liegt nur unter `output/`, das `.gitignore` in jeder Tiefe ausschließt (`tests/test_gitignore.py`). Ein Test prüft, dass `*.docx` unter `output/` ignoriert wird.
- *handled —* `docProps/core.xml` trägt nur feste Werte (Titel `Transkript`, Autor `narrata-transcript`, kein Rechner- oder Benutzername, keine Zeit). Es landen keine Pfade im Dokument.
- *handled —* Die Konsole zeigt nur Zahlen und den Pfad. Fehler laufen über `load_export` und nennen nie einen Wert. Es wird nichts geloggt.
- *handled —* Die Tests nutzen die erfundene Narrata-Fixture und synthetische Dokumente aus `tests/test_rendering.py`. Es kommen keine neuen Fixtures dazu.
- *handled —* Der Befehl liest nur `transcript.json`. Ein Test prüft, dass `work/` und `transcript.json` byte-gleich bleiben (AK „verändert weder Quellen noch Arbeitsdaten“).

## Contract-Check
- *handled —* Gelesen wird Contract v1 (IOA-1214) über `load_export`, also geprüft gegen die Schema-Kopie. Eine fremde Major wird verweigert.
- *handled —* Benutzt werden `session`, `pipeline.backend`/`model`/`knowledge_snapshot_id`, `contract_version`, `speakers`, `passages`. Alle sind im Schema Pflicht. `session_date` und `knowledge_snapshot_id` dürfen `null` sein, und das wird abgefangen.
- *N/A because* Narrata braucht keine Änderung: Die Datei wird nur gelesen, es entsteht kein IOA-Ticket.

## Resume-Check
*N/A because* der Schritt kurz, deterministisch und modellfrei ist. Durch das atomare Schreiben bleibt keine halbe Datei zurück.

## Dependency-Check
*N/A because* keine neue Abhängigkeit dazukommt (Entscheidung oben). Gebraucht werden nur `zipfile` und `xml.sax.saxutils` aus der Standardbibliothek.

## Format-Check
*N/A because* DOCX ein Leseformat ohne eigenes Versionsfeld ist. Der Aufbau steht im README. `Paragraph.named` ist ein internes Feld ohne gespeichertes Format.

## Chunks
### Chunk 1 — Sprecherart im Lesekern
- Dateien: `src/transcript/rendering.py`, `tests/test_rendering.py`
- Änderung: `Paragraph.named: bool`, in `paragraphs` gesetzt, wenn die Person zugeordnet ist und einen `display_name` hat. Der Moduldocstring nennt DOCX als zweiten Nutzer.
- Verify: `scripts/check`
- AC: Person mit Namen → `named=True`, nicht zugeordnet → `False`, zugeordnet ohne Namen → `False`. Die TXT-Tests bleiben unverändert grün.

### Chunk 2 — DOCX-Renderer
- Dateien: `src/transcript/docx_render.py` (neu), `src/transcript/session.py` (`transcript_document`), `tests/test_docx.py` (neu)
- Änderung: Paketteile als Vorlagen-Strings, `styles.xml` mit `Title`, `Meta`, `Speaker`, `Normal` und den Zeichenstilen `SpeakerLabel`, `Marker`, `Time`. `render_docx` baut Kopf und Absätze und liefert die Zip-Bytes deterministisch. `write_docx` nutzt `write_bytes_atomic`.
- Verify: `scripts/check`
- AC (Tests parsen das Zip mit `zipfile` und `xml.etree`):
  - Alle Teile vorhanden, jedes XML wohlgeformt, Content Types und Relationships konsistent.
  - Reihenfolge und Wortlaut: Die Text-Runs ergeben in Dateireihenfolge die Passagentexte der Fixture.
  - Umlaute, `ß`, Emoji, kombinierende Zeichen bleiben erhalten. `<`, `&` und `"` im Text werden escaped, ein Steuerzeichen wird entfernt.
  - Marker-Runs tragen den Stil `Marker` mit den Beschriftungen aus TXT (`[unklar …]`, `[unverständlich …]`, `[Lücke …]` …). Labels tragen `SpeakerLabel`, Personen nicht.
  - Der Kopf enthält Schlüssel, Ordinal, Datum (`null` ohne Datum), Backend/Modell, Snapshot („keiner“ bei `null`) und Contract-Version.
  - `turn` und `passage` erzeugen das beschriebene Absatzlayout.
  - Zweimal rendern ergibt dieselben Bytes.

### Chunk 3 — Befehl `transcript docx` und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `tests/test_gitignore.py`, README (neuer Abschnitt „DOCX-Ausgabe“ nach „TXT-Ausgabe“, Verzeichnisstruktur `transcript.docx`, Verweis in „JSON-Export“)
- Änderung: Subcommand `docx` mit `--config`, `_docx` nach dem Muster von `_txt`.
- Verify: `scripts/check` und `transcript docx --help`. Dazu öffnet die Nutzerin ein aus der Fixture gerendertes DOCX einmal in Word oder LibreOffice (AK „lässt sich öffnen“).
- AC: Der Smoke-Test exportiert und rendert eine synthetische Session. Exit 0 mit offenen Passagen, Exit 2 ohne `transcript.json` mit Hinweis auf `transcript export`. Die Konsole zeigt keinen Text und keinen Namen. `work/` und `transcript.json` bleiben unverändert.

## Folge-Tickets
- Ein Sitzungstitel fehlt in Contract v1, deshalb heißt die Überschrift nach dem Sitzungsschlüssel. `[kein Ticket: Narrata zeigt den Titel selbst; erst bei Bedarf als Minor-Feld bei IOA-1214 anfragen]`
- Die Gegenprobe des Exports gegen `transcript:validate`/`transcript:import` steht weiter aus. `[kein Ticket: läuft unter TOOL-58, betrifft TOOL-52 nicht]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `Paragraph.named` im Lesekern | no |
| 2 | DOCX-Renderer `docx_render.py` | no |
| 3 | CLI `transcript docx`, README | no |
