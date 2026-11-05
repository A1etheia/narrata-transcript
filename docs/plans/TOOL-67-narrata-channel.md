# TOOL-67 — Transkriptionskontext über den Narrata-Exportkanal beziehen

## Ziel
`transcript context <gruppe>/<ordinal>` holt den Transkriptionskontext einer Spielsitzung vom Narrata-Endpoint (IOA-1215) und legt die Antwort unverändert unter `work/<gruppe>/<ordinal>/narrata/transcription-context.json` ab. Mit `--from-file` übernimmt derselbe Befehl eine lokal gespeicherte Antwort gleichen Formats. Beide Wege laufen durch dieselbe Prüfung, vor allem die der `contract_version`. Heute wird die Datei von Hand abgelegt, ungeprüft auf Version und ohne Abruf.

## Ist-Stand
- `src/transcript/narrata.py:34` `read_session` liest nur den Block `session` und prüft Ordinal und Datum. `contract_version` prüft es nicht. Der Docstring (`narrata.py:3-4`) nennt das Ablegen von Hand als Übergang bis TOOL-67.
- `src/transcript/session.py:115` `SessionPaths.narrata_context` ist der Ablageort.
- `src/transcript/manifest.py:96` `build_manifest` und `manifest.py:158` `load_manifest` lesen den Kontext. `load_manifest` läuft in `__main__.py:233` vor der ASR (`transcribe_session`, `__main__.py:240`). Eine Prüfung in `read_session` greift damit vor der ASR.
- `src/transcript/jsonfile.py:104` `write_atomic` serialisiert ein dict neu. Für Rohbytes fehlt ein atomarer Schreibweg.
- `src/transcript/config.py:14` kennt die Top-Level-Schlüssel, eine Sektion `narrata` gibt es nicht. `config/example.yaml:2` sagt bereits: „Keine Secrets in diese Datei: Die gehören in .env.“ `.gitignore` ignoriert `.env`/`.env.*` und lässt `.env.example` zu, eine `.env.example` fehlt aber noch.
- `src/transcript/__init__.py:13` setzt die Offline-Umgebung für Modellbibliotheken. HTTP-Code gibt es bisher keinen.
- Die Fixtures in `tests/test_manifest.py:86` und `tests/test_smoke.py:238` schreiben `contract_version: "1.0"`.
- Contract (ios-archiv `docs/transcripts.md` „Transkriptionskontext“, Stand 05.11.2026): `GET /api/groups/{group}/play-sessions/{ordinal}/transcription-context`, `Authorization: Bearer <Sanctum-Token>`. `{group}` ist die **Gruppen-ID**, denn `Group` bindet die Route nicht über den Slug. Die Antwort hat die Felder `contract_version` (aktuell `"1.1"`), `session`, `participants`, `glossary`, `glossary_meta` und `asr_ambiguities`. Statuscodes: 401 ohne Token, 404 für jede Ablehnung und jedes unbekannte Ordinal, 422 bei ungültigen Parametern. `TranscriptContract` in ios-archiv versioniert nach `MAJOR.MINOR` mit `SUPPORTED_MAJORS = [1]`.

## Entscheidungen
- **Version:** Akzeptiert wird `contract_version` im Format `MAJOR.MINOR` mit Major 1. Minor-Bumps sind additiv (1.1 brachte `asr_ambiguities`). Fehlt die Version, ist sie ungültig oder hat sie einen anderen Major, kommt ein Fehler, der die gefundene und die unterstützte Version nennt. Die Regel spiegelt `TranscriptContract::SUPPORTED_MAJORS`.
- **Ein Weg, zwei Quellen:** `narrata.store_context(paths, raw: bytes)` ist der einzige Schreiber. Er prüft das JSON-Objekt, die Version, den Block `session` und das Ordinal gegen den Schlüssel und schreibt die Bytes erst danach atomar und unverändert. Die HTTP-Quelle und `--from-file` liefern nur Bytes an. Eine ungültige Antwort überschreibt eine vorhandene gültige Datei nie.
- **Version vor ASR:** `read_session` prüft die Version ebenfalls. Damit bricht auch eine von Hand abgelegte Datei in `manifest` und `transcribe` ab, bevor ein Modell lädt.
- **Token:** `NARRATA_TOKEN` kommt aus der Umgebung, sonst aus `.env` im Arbeitsverzeichnis, mit Zeilen der Form `KEY=VALUE`, `#`-Kommentaren und optionalen Anführungszeichen. Es gibt keine neue Abhängigkeit, und der Token liegt nie in der Config. Bis IOA-1251 ist es der 24-h-Login-Token, deshalb nennt die Meldung bei 401 „Token fehlt oder abgelaufen“.
- **Gruppen-ID:** Die neue Config-Sektion `narrata` hat die Schlüssel `url` (Basis-URL) und `groups` (Slug → Gruppen-ID). Die Zuordnung ist kein Secret und ändert sich selten. Eine CLI-Option müsste man bei jedem Lauf tippen.
- **HTTP:** stdlib `urllib.request` mit 30 s Timeout und ohne Retry, denn der Befehl lässt sich einfach neu starten. `url` muss `https` sein, `http` gilt nur für `localhost`/`127.0.0.1` (lokales Narrata, Tests). So geht der Bearer-Token nie unverschlüsselt übers Netz.
- **Query-Parameter:** TOOL-67 sendet weder `n` noch `archive_limit`, es gelten die Server-Defaults 3 und 500. Die Wahl gehört zur Relevanzregel in TOOL-41.
- **Kapselung:** Das Modul ist schmal: `narrata.py` (Prüfen, Ablegen, Lesen) plus `narrata_client.py` (HTTP). Ein Domain-Context mit Abfragen bleibt TOOL-43 überlassen, TOOL-67 nimmt dessen Interface nicht vorweg.

## Daten-Check
- Rohantwort mit Klarnamen: *handled*. Sie landet nur in `work/` (gitignored, `tests/test_gitignore.py`), nie in `output/`.
- Konsolenausgabe: *handled*. `context` gibt nur Zähler aus (Teilnehmende, Glossar, `archive_returned`/`archive_total`), keine Namen. Das entspricht der Regel aus TOOL-66 („nur Zahlen, Zeiten, Herkunft“).
- Fehlermeldungen: *handled*. Sie nennen Datei, Feld, HTTP-Status und Gruppen-ID/Ordinal, nie Feldwerte (Konvention `jsonfile.py:3`) und nie den Token. Ein Test prüft, dass der Token in keiner Meldung und keinem Log steht (401, 404, 500, Netzfehler).
- Debug-Log: *handled*. Der Client loggt weder Header noch Response-Body.
- Fixtures: *handled*. Nur erfundene Namen (Muster `Erika Beispiel`), Gruppen-ID und Token sind Platzhalter.
- Netz: *handled*. Rohaudio verlässt den Rechner nicht, der Abruf ist rein lesend und wird nur ausdrücklich per Befehl ausgelöst. `docs/datenschutz.md:39` („danach läuft die Pipeline ohne Netz“) bekommt die Ausnahme dazugeschrieben.

## Contract-Check
- Passt zu IOA-1214/IOA-1215? *handled*. Pfad, Header, Statuscodes und Felder folgen ios-archiv `docs/transcripts.md`. Gelesen wird weiterhin nur `session`, der Rest bleibt roh für TOOL-41.
- Version: *handled*. Akzeptiert wird Major 1, also `1.0` und `1.1`. Die Fixtures werden auf `1.1` gehoben, ein Test hält `1.0` lauffähig.
- Narrata-Änderung nötig? N/A, weil der Endpoint so genutzt wird, wie er ist. Der langlebige Token kommt mit IOA-1251 und ändert nur den Wert von `NARRATA_TOKEN`.

## Resume-Check
- Abbruch: *handled*. Der Abruf ist ein einzelner Request, geschrieben wird atomar und erst nach der Prüfung. Ein Abbruch hinterlässt also die alte Datei oder gar keine.
- Wiederverwendung: N/A, weil nichts Teures entsteht. Ein erneuter Abruf ersetzt die Rohdatei. Ändert sich dabei die `play_session_id`, meldet `load_manifest` die Neuvergabe (`manifest.py:158-161`).
- Gleiches Modell/Snapshot beim Resume: N/A, weil TOOL-67 kein Modell nutzt. Die Reproduzierbarkeit über einen Snapshot liefert TOOL-41.

## Dependency-Check
- Neue Abhängigkeit: N/A, weil HTTP über `urllib.request` und `.env` über einen eigenen Zeilenparser laufen, beides stdlib. `pyproject.toml` bleibt unverändert.

## Format-Check
- `contract_version` gehört Narrata. Die Pipeline prüft die Version und bumpt sie nicht. Bestehende Dateien mit `1.0` bleiben gültig.
- Manifest, Referenz und Audio-Metadaten: N/A, weil sich ihr Format nicht ändert.

## Chunks
### Chunk 1 — Contract-Prüfung und Ablage
- Dateien: `src/transcript/narrata.py`, `src/transcript/jsonfile.py`, `tests/test_narrata.py` (neu), `tests/test_manifest.py`, `tests/test_smoke.py`, `tests/test_transcription.py` oder die CLI-Tests
- Änderung: `SUPPORTED_MAJOR = 1` und `check_contract(data, path)` kommen dazu, `read_session` ruft sie auf. `store_context(paths, raw)` prüft und schreibt dann Bytes über ein neues `jsonfile.write_bytes_atomic`. `write_atomic` nutzt es intern. Den Docstring aktualisieren und die Fixtures auf `1.1` heben.
- Verify: `scripts/check`
- AC: `1.0` und `1.1` werden akzeptiert. Fehlend, `"1"`, `2.0`, eine Zahl statt eines Strings: verständlicher Fehler mit unterstützter Version. `store_context` schreibt die Bytes identisch, und eine ungültige Antwort lässt die vorhandene Datei unberührt. `transcribe` mit einem `2.0`-Kontext endet mit Exit 2, ohne dass das Backend geladen wird.

### Chunk 2 — Config-Sektion `narrata` und Token
- Dateien: `src/transcript/config.py`, `config/example.yaml`, `.env.example` (neu), `src/transcript/narrata_client.py` (neu, nur `read_token`), `tests/test_config.py`, `tests/test_narrata_client.py` (neu)
- Änderung: `narrata.url` (optional, prüft das Schema https bzw. http nur für localhost) und `narrata.groups` (Slug → positive Ganzzahl) kommen in `Config`, `load_config` und `format_config`. `read_token(env, dotenv_path)` liest `NARRATA_TOKEN` aus der Umgebung, sonst aus `.env`. Dazu kommt eine `.env.example` mit `NARRATA_TOKEN=`.
- Verify: `scripts/check`
- AC: Ungültige URL, Remote-`http` und ungültige Gruppen-ID melden Datei und Schlüssel. Die Umgebung schlägt `.env`. Ohne Token kommt ein Fehler mit Hinweis auf `.env.example`, aus dem sich kein Token-Wert ablesen lässt.

### Chunk 3 — HTTP-Client
- Dateien: `src/transcript/narrata_client.py`, `tests/test_narrata_client.py`
- Änderung: `fetch_context(url, group_id, ordinal, token, timeout=30) -> bytes` baut den Pfad laut Contract und sendet `Authorization: Bearer` und `Accept: application/json`. Statuscodes werden auf Meldungen abgebildet: 401 Token fehlt/abgelaufen, 404 unbekannt oder keine aktive Spielleitung, 422, sonstiges HTTP, Netzfehler/Timeout. Alle Exceptions werden ohne Kette (`from None`) weitergereicht.
- Verify: `scripts/check`
- AC: Die Tests laufen gegen einen `http.server` auf 127.0.0.1. Sie prüfen den Pfad (`play-sessions`, Gruppen-ID, Ordinal), den Bearer-Header und jede Statusmeldung. Der Token-String steht in keiner Exception-Meldung und keinem Log-Record.

### Chunk 4 — CLI `context` und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`, `docs/datenschutz.md`
- Änderung: `transcript context <gruppe>/<ordinal> [--from-file PATH] [--config …]` kommt dazu. Ohne `--from-file` werden Gruppen-ID, URL und Token aufgelöst, dann folgt `fetch_context`. Beide Wege enden in `store_context`, danach gibt der Befehl die Zähler aus. Der README bekommt einen Abschnitt „Narrata-Kontext“, die Voraussetzung in `README.md:58` wird angepasst, Token und `.env` werden unter „Konfiguration“ beschrieben. `docs/datenschutz.md` bekommt die Netzausnahme.
- Verify: `scripts/check`
- AC: Der Smoke-Test `context --from-file` legt die Datei ab, und `manifest` läuft danach. Mit lokalem Server läuft `context` über HTTP gegen eine Config auf `http://127.0.0.1`. Die Konsole zeigt keine Namen aus der Fixture. Fehlt die Gruppe in `narrata.groups`, kommt Exit 2 mit Hinweis auf den Config-Schlüssel.

## Folge-Tickets
- TOOL-41: `n` und `archive_limit` für den Abruf festlegen. Dazu klären, ob ein erneuter Abruf die Rohdatei ersetzen darf, nachdem ein Snapshot daraus gebaut wurde.
- IOA-1251: Langlebiger Pipeline-Token. Danach den Hinweis „24 h“ in README und in der 401-Meldung anpassen.
- TOOL-43: Der Domain-Context baut auf `narrata.store_context` und die Rohdatei auf, TOOL-67 legt kein Abfrage-Interface fest.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Contract-Prüfung, `store_context`, atomare Rohbytes | no |
| 2 | Config `narrata`, Token aus `.env`, `.env.example` | no |
| 3 | HTTP-Client mit Fehlerabbildung | no |
| 4 | CLI `context`, Smoke-Tests, README, Datenschutz | no |
