# TOOL-38 — Teilnehmer- und Sprecherwissen für eine Session aus Narrata beziehen

## Ziel
Der Block `participants` im Narrata-Transkriptionskontext wird geprüft und typisiert gelesen: reale Teilnehmende mit User-ID, Anzeigename, Rolle und `is_former`, dazu ihre Spielfiguren mit Archiv-ID, Name und Aliasen. Heute liegt der Block nur ungeprüft in der Rohdatei, `transcript context` zählt ihn bloß. Danach können TOOL-41 (Stufe `pc`, Snapshot) und TOOL-68 (Sprecherzuordnung) auf einem einzigen Leser aufbauen. Die Anwesenheit pro Sitzung bleibt vorerst „unbekannt“, weil Narrata sie nicht führt.

## Ist-Stand
- `src/transcript/narrata.py:66` `store_context` prüft nur Version und `session`, dann schreibt es die Bytes. `narrata.py:5` sagt ausdrücklich, dass `participants` späteren Schritten überlassen bleibt.
- `src/transcript/narrata.py:90` `_session` ist das Muster für einen Blockleser mit Meldungen ohne Feldwerte. `src/transcript/jsonfile.py:44-90` liefert `field`, `optional_field` und `list_of`.
- `src/transcript/__main__.py:203-233` `_context` liest die gespeicherte Datei neu und gibt `_count(data.get('participants'))` aus.
- Contract (ios-archiv `docs/transcripts.md:219-247`, Version `1.1`): Jeder Eintrag hat `user_id`, `display_name` (= `users.name`), `role` `gm|player`, `is_former` und `characters` mit `person_id`, `name`, `aliases`. Ehemalige sind enthalten. Sortiert wird nach `display_name`, dann `user_id`. Quelle: `TranscriptionContextBuilder::participants` (ios-archiv-backend `app/Support/Transcripts/TranscriptionContextBuilder.php:92`).
- Anwesenheit: Narrata hat weder eine Anwesenheit pro Sitzung noch Ein- oder Austrittsdaten der Mitglieder, nur `is_former`.
- Fixtures: `tests/test_narrata.py:32` (ohne `role`/`is_former`), `tests/test_manifest.py:88` (nur `display_name`), `tests/test_smoke.py` (Kontext-Fixture um Zeile 238).

## Entscheidungen
- **Ort:** Der Leser kommt in `narrata.py`, das schon Eigentümer der Datei ist. Neu sind `Character`, `Participant` und `NarrataParticipants` sowie `read_participants(paths)`. Ein eigenes Modul würde einen Import-Zyklus über `NarrataContextError` erzeugen.
- **Prüfen beim Ablegen:** `store_context` prüft zusätzlich `participants`. Ein Kontext, dessen Teilnehmerblock gegen den Contract verstößt, wird dann gar nicht erst gespeichert. `read_session` bleibt schmal, `manifest` hängt nicht an den Teilnehmenden.
- **Pflicht vs. optional:** Pflicht sind `participants` (Liste, darf leer sein), `user_id` (Narrata-ID nach `is_play_session_id`), `display_name` (nicht leer), `role` ∈ {`gm`, `player`} und `is_former` (bool, ohne Default, weil ein falscher Default eine Ehemalige zur aktiven Spielerin machte). Optional sind `characters` (fehlt oder `null` → leer) und `aliases` (fehlt oder `null` → leer). `name` und `person_id` einer Figur sind Pflicht. Unbekannte Zusatzfelder werden ignoriert, Minor-Bumps sind additiv.
- **Doppelte IDs:** Eine doppelte `user_id` oder eine doppelte `person_id` über alle Teilnehmenden hinweg ist ein Fehler. TOOL-68 ordnet über diese IDs zu.
- **Herkunft:** `NarrataParticipants` trägt `source` (Pfad der Rohdatei), `contract_version` und `play_session_id`, jeder Eintrag seine Narrata-ID. Die Reihenfolge aus Narrata bleibt erhalten.
- **Anwesenheit:** Es gibt `Participant.present: bool | None`, immer `None` = „Narrata führt es nicht“. Nichts wird aus `is_former` abgeleitet. Die Narrata-Seite kommt als IOA-1271 (Epic IOA-1213), das Einlesen als TOOL-79 (Epic TOOL-37).
- **Snapshot:** TOOL-38 liefert nur den Leser. Die Übernahme in den Snapshot macht TOOL-41 (Entscheidung im Chat vom 05.11.2026).
- **Keine Sprecherzuordnung:** Weder das Referenzformat noch die Diarisierung werden angefasst.

## Daten-Check
- TOOL-66 eingehalten? *handled*: Klarnamen bleiben in `work/…/narrata/`. Die Dataclasses leben nur im Speicher, eine neue Datei entsteht nicht.
- Konsole: *handled*. `context` gibt nur Zähler aus (Teilnehmende, davon SL und ehemalig, Figuren). Ein Smoke-Test prüft, dass kein Fixture-Name in stdout/stderr steht.
- Fehlermeldungen: *handled*. Sie nennen Pfad, Index und Feld (`participants[2].role`), nie einen Wert, auch nicht die ungültige Rolle oder die doppelte ID. Ein Test prüft, dass der Name nicht in der Meldung steht.
- Logs: *handled*. Der Leser loggt nichts.
- Fixtures: *handled*. Nur erfundene Namen (`Erika Beispiel`, Figur `Brakk der Beispielhafte`) und erfundene IDs.

## Contract-Check
- Passt zu IOA-1214/IOA-1215 und Version? *handled*. Die Felder folgen `docs/transcripts.md:228-247` (Contract 1.1). Akzeptiert wird weiter Major 1. Zusatzfelder späterer Minors werden ignoriert.
- Narrata-Änderung nötig? Für TOOL-38 nein. Die Anwesenheit braucht eine Narrata-Erweiterung mit Contract-Minor-Bump, getragen von IOA-1271.

## Resume-Check
- N/A, weil der Schritt kurz ist und kein Modell nutzt: Er liest eine lokale Datei. Wiederverwendung und Snapshot-Stabilität sind Thema von TOOL-41.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt, nur stdlib und `jsonfile`.

## Format-Check
- N/A, weil sich kein internes Format ändert. Die Rohdatei bleibt byte-gleich, `contract_version` gehört Narrata. Bestehende Rohdateien unter `work/` werden beim nächsten `read_participants` geprüft. Eine Datei, die vor TOOL-38 abgelegt wurde und dem Contract widerspricht, meldet einen Fehler, statt still durchzugehen.

## Chunks
### Chunk 1 — Teilnehmerleser
- Dateien: `src/transcript/narrata.py`, `tests/test_narrata.py`, `tests/test_manifest.py`, `tests/test_smoke.py`
- Änderung: Neu sind die Dataclasses `Character(person_id, name, aliases)`, `Participant(user_id, display_name, role, is_former, characters, present=None)` und `NarrataParticipants(source, contract_version, play_session_id, participants)`. Dazu `_participants(data, path)` nach dem Muster von `_session` und `read_participants(paths)`. `store_context` prüft beide Blöcke. Der Modul-Docstring wird angepasst, die Fixtures werden contract-vollständig gemacht.
- Verify: `scripts/check`
- AC: Mehrere Teilnehmende werden in Narrata-Reihenfolge geladen. Eine SL ohne Figur (`characters: []`, fehlend, `null`) und eine Spielerin mit zwei Figuren sind darstellbar. Aliase werden übernommen, `aliases: null` ergibt `()`. Eine fehlende Pflichtangabe, eine ungültige Rolle oder eine doppelte `user_id`/`person_id` ergibt `NarrataContextError` mit Index und Feld, ohne Wert. `store_context` speichert in diesen Fällen nichts. `present` ist immer `None`. Ein Zusatzfeld stört nicht.

### Chunk 2 — CLI-Zähler und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`
- Änderung: `_context` zählt über `read_participants`, die Ausgabe sieht etwa so aus: `4 participant(s) (1 gm, 1 former), 5 character(s)`. Der README-Abschnitt „Narrata-Kontext“ / „Prüfung“ bekommt die Teilnehmerprüfung und den Hinweis, dass Anwesenheit noch nicht geführt wird.
- Verify: `scripts/check`
- AC: Der Smoke-Test `context --from-file` zeigt die Zähler und keinen Namen. Ein Kontext mit ungültigem Teilnehmerblock endet mit Exit 2, und die Datei bleibt unverändert.

## Folge-Tickets
- TOOL-41: übernimmt `narrata.read_participants` in den Snapshot. Das AK „Ergebnis in den Session-Wissens-Snapshot übernehmen“ aus TOOL-38 wird dorthin verschoben.
- TOOL-68: nimmt die Kandidaten der Zuordnung aus `read_participants` (aktive zuerst, Ehemalige wählbar). `present` ist bis TOOL-79 `None`.
- IOA-1271 (Epic IOA-1213): Anwesenheit pro Spielsitzung in Narrata führen und im Transkriptionskontext ausliefern, als `participants[].present`, Contract-Minor-Bump `1.2`.
- TOOL-79 (Epic TOOL-37, blockiert durch IOA-1271): `participants[].present` aus Contract ≥ 1.2 lesen. Fehlt das Feld, bleibt es bei `None`.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Teilnehmerleser in `narrata.py`, Prüfung in `store_context`, Fixtures | no |
| 2 | CLI-Zähler `context`, README | no |
