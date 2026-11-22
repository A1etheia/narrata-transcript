# TOOL-84 — Kontext mit dem Pipeline-Token statt dem Login-Token abrufen

## Ziel
`transcript context` ruft den Transkriptionskontext mit dem Pipeline-Token aus IOA-1251 ab. Diesen Token erzeugt die aktive Spielleitung für eine Runde, er gilt 90 Tage und öffnet nur diesen Endpoint. Heute liest die Pipeline einen einzigen `NARRATA_TOKEN`, vorgesehen ist dafür der 24-h-Login-Token mit voller Konto-Reichweite. Danach steht in `.env` ein Token je Runde. Die Fehlermeldungen sagen, was bei 401 und 404 zu tun ist.

## Ist-Stand
- `src/transcript/narrata_client.py:14` `TOKEN_VARIABLE = "NARRATA_TOKEN"`. `read_token` (`:22`) liest den Token aus der Umgebung, sonst aus `.env`. Laut Meldung (`:29`) ist es ein Login-Token.
- `src/transcript/narrata_client.py:127` `_http_message`: 401 meldet „login tokens last 24 h“, 404 rät, `narrata.groups` und die aktive Spielleitung zu prüfen.
- `src/transcript/__main__.py:680` `_fetch` kennt `key.group`, ruft aber `read_token(os.environ, _DOTENV)` ohne Gruppe auf (`:688`).
- `src/transcript/preflight.py:340` `_narrata_access` ruft `read_token` ebenfalls ohne Gruppe auf.
- Ein Login-Flow existiert nicht, die Pipeline liest nur den Token. Auch einen Transkript-Import gibt es in der Pipeline nicht, der Upload nach Narrata geschieht von Hand (`docs/ablauf.md:184`). Dieser Teil des Ticketumfangs braucht deshalb keine Code-Änderung.
- Gruppen-Slugs folgen `[a-z0-9]+(-[a-z0-9]+)*` (`src/transcript/session.py:12`).
- Tests: `tests/test_narrata_client.py` (ReadTokenTest, Statusmeldungen), `tests/test_smoke.py:441,583-597`, `tests/test_preflight.py:452,463`.
- Doku: `.env.example`, `config/example.yaml:58`, `README.md:125,129,747,812`, `docs/ablauf.md:51,105,248`, `docs/datenschutz.md:46`.
- Narrata-Seite: `ios-archiv/docs/transcripts.md:356-374`. Der Token bekommt 200 für die eigene Runde und 404 für eine fremde Runde oder eine ausgetretene SL. Abgelaufen oder widerrufen ergibt 401.

## Entscheidungen
- **Eine Variable je Gruppe:** `NARRATA_TOKEN_<SLUG>`, der Slug in Großbuchstaben, `-` wird zu `_` (`beispielgruppe` → `NARRATA_TOKEN_BEISPIELGRUPPE`). Grund: Der Token gilt nur für eine Runde. Bei einem gemeinsamen Token ergäbe die falsche Runde eine schwer deutbare 404. Die Abbildung ist eindeutig, weil Slugs keinen `_` enthalten. Im Planungsgespräch so entschieden.
- **`NARRATA_TOKEN` wird nicht mehr gelesen.** Ist er gesetzt und fehlt die Gruppenvariable, nennt die Meldung den neuen Namen und den Weg zum Pipeline-Token. Sie nennt nie den Wert.
- **Der Token kommt mit seinem Namen:** `read_token(environ, dotenv, group)` gibt ein kleines `Token(variable, value)` zurück, `value` mit `repr=False`. `fetch_context` nimmt es an, damit die 401-Meldung die richtige Variable nennt. So entsteht kein zusätzlicher Parameter, und der Wert bleibt aus jedem `repr`.
- **Meldungen:** Bei 401: „`<VAR>` is expired or revoked; create a new pipeline token for this group in Narrata (Profil → Aktive Sitzungen)“. Bei 404: falsche Runde (`narrata.groups`), oder die Spielleitung, die den Token erzeugt hat, ist nicht mehr aktiv.
- Die Rohdatei `.env` wird pro Aufruf einmal gelesen, wie bisher.

## Daten-Check
- Token in Meldungen, Logs, Exceptions: handled. Meldungen nennen nur den Variablennamen. `Token.value` steht nicht im `repr`. Ein Test prüft, dass der Wert in keiner Meldung und in keinem stderr vorkommt (der bestehende `assertNotIn(TOKEN, …)` wird übernommen).
- Gruppen-Slug in Meldungen: handled. Slugs stehen schon heute in Meldungen (`narrata.groups has no group id for …`) und in Pfaden. Sie sind keine Klarnamen von Personen. Fixtures nutzen `beispielgruppe`.
- Echte Tokens im Repo: handled. `.env` bleibt gitignored, `.env.example` zeigt nur leere Variablen, `test_example_file_holds_no_token` bleibt.
- Audio, Transkripte, Teilnehmende: N/A, weil der Abruf und die Ausgabe von `transcript context` (nur Zähler) unverändert bleiben.

## Contract-Check
- Endpoint und Contract-Version: N/A, weil sich nur der Bearer-Token ändert. Die URL (`context_url`), Parameter und Antwort (Contract 1.x, IOA-1214/IOA-1215) bleiben gleich.
- Narrata-Änderung: N/A, weil IOA-1251 erledigt ist (PR #1154). Der Endpoint nimmt den Pipeline-Token schon an, Login-Tokens funktionieren weiter.
- Import: N/A, weil die Pipeline nichts nach Narrata schreibt. Der Upload bleibt laut `ios-archiv/docs/transcripts.md:373` beim Login-Token, und das ist nur ein Hinweis in `docs/ablauf.md`.

## Resume-Check
N/A, weil der Kontextabruf ein einzelner, kurzer HTTP-Aufruf ist und weder Modell noch Snapshot berührt.

## Dependency-Check
N/A, weil keine neue Abhängigkeit und kein Modell hinzukommt.

## Format-Check
N/A, weil sich kein versioniertes internes Format ändert. `.env` hat keine Version, und `narrata/context.json` bleibt gleich.

## Chunks
### Chunk 1 — Token je Gruppe im Client
- Dateien: `src/transcript/narrata_client.py`, `src/transcript/__main__.py`, `src/transcript/preflight.py`, `tests/test_narrata_client.py`, `tests/test_smoke.py`, `tests/test_preflight.py`
- Änderung: `token_variable(group)`, `Token`-Dataclass, `read_token(environ, dotenv, group)` mit dem Hinweis auf den veralteten `NARRATA_TOKEN`, `fetch_context(…, token: Token, …)`, neue 401- und 404-Meldungen. Aufrufer in `_fetch` und `_narrata_access` geben `key.group` mit. Modul-Docstring auf IOA-1251 aktualisieren.
- Verify: `scripts/check`
- AC: `transcript context beispielgruppe/42` schickt den Wert von `NARRATA_TOKEN_BEISPIELGRUPPE` als Bearer. Ein nur gesetzter `NARRATA_TOKEN` ergibt Exit 2 mit dem neuen Variablennamen. 401 und 404 nennen Variable und Abhilfe, nie den Wert. Der Preflight meldet eine fehlende Gruppenvariable.

### Chunk 2 — Doku
- Dateien: `.env.example`, `config/example.yaml`, `README.md`, `docs/ablauf.md`, `docs/datenschutz.md`
- Änderung: Pipeline-Token statt Login-Token, je Runde eine Variable, 90 Tage, erzeugen unter Profil → Aktive Sitzungen. Fehlerbild 401 (abgelaufen oder widerrufen, neu erzeugen) und 404 (falsche Runde oder SL nicht mehr aktiv). Hinweis, dass der Upload nach Narrata weiter den Login-Token braucht. Die Sätze „kommt mit IOA-1251“ und „24 h“ fallen weg.
- Verify: `scripts/check`, dazu `grep -n "NARRATA_TOKEN\b\|24 h" README.md docs/ablauf.md docs/datenschutz.md .env.example config/example.yaml`. Übrig bleiben darf nur der Login-Token des Uploads.
- AC: Kein Dokument verlangt mehr einen frischen Login-Token für den Kontextabruf.

## Folge-Tickets
- Roadmap-Zeile TOOL-84 auf erledigt setzen: [kein Ticket: erledigt `/close-ticket`]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Token je Gruppe in Client, CLI und Preflight | no |
| 2 | Doku und Vorlagen | no |
