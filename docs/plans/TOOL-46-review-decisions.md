# TOOL-46 — Review-Datenmodell und Entscheidungsstatus

## Ziel
Zu jedem Review-Kandidaten kann eine manuelle Entscheidung festgehalten werden: Status, optional Zieltext und Notiz. Sie wird gespeichert und geladen, ohne Kandidat, Referenztext oder Bewertung anzutasten. Heute gibt es nur die automatisch erzeugte Kandidatenliste (TOOL-36). Sie wird nach jeder Bewertung neu geschrieben, eine Entscheidung darin ginge also verloren. TOOL-47/48 (CSV hin und zurück) und TOOL-80 brauchen dieses Modell als Ziel.

## Ist-Stand
- `src/transcript/candidates.py:55` `ReviewCandidate` mit `id` (`s01-p0042`, `:72`), `segment`, `rating` (Stufe, Gründe mit `value`/`threshold`, `missing`), `text` (unverändert), `speaker`, `time` (`SessionSpan` oder `None`) und `hints` (aus TOOL-44, mit Narrata-Kandidaten).
- `candidates.py:226` `write_candidates` ersetzt `review/candidates.json` (v1) bei jedem `assess`/`transcribe`/`diarize` (`src/transcript/__main__.py:705`). Der Kopf enthält pro Segment `reference.processed_at` und `knowledge_snapshot_id` (`:239-250`). `load_candidates` (`:272`) prüft `format_version` und die Session.
- `src/transcript/session.py:111-125` `review_dir` und `review_candidates`, noch ohne Pfad für Entscheidungen.
- `src/transcript/jsonfile.py`: `read_object`, `field`, `optional_field`, `one_of`, `list_of`, `write_atomic`, `DataFileError` als Bausteine.

Fast alle Kandidatenfelder des Tickets gibt es damit schon: Review-ID, Session, Passage, Zeit, Referenztext, Stufe, Gründe, Confidence-Werte und Domänenhinweise. Neu ist nur die Entscheidungsseite.

## Entscheidungen
- **Eigene Datei `work/<s>/review/decisions.json`**, getrennt von `candidates.json`. Die Kandidatendatei bleibt rein automatisch und darf weiter bei jedem Lauf neu entstehen. Die Entscheidungsdatei schreibt nur ein manueller Schritt (später TOOL-48). So bleibt die Trennung zwischen Kandidat und Entscheidung strukturell erhalten, und kein Feld des Kandidaten wird je überschrieben.
- **Neues Modul `src/transcript/decisions.py`**, `candidates.py` bleibt unverändert.
- **Status als Literal** `ReviewStatus`: `open`, `confirmed` (ASR-Wortlaut bestätigt), `corrected` (manuell korrigiert), `unintelligible`, `kept` (bewusst unverändert), `deferred` (später prüfen). Ein Kandidat ohne Eintrag gilt als `open`. Ein expliziter `open`-Eintrag ist erlaubt, damit eine Notiz ohne Entscheidung gespeichert werden kann.
- **`ReviewDecision`**: `candidate` (ID), `segment`, `passage`, `reference_processed_at` (Fassung, auf die sich die Entscheidung bezieht), `status`, `target_text: str | None`, `note: str | None`, `decided_at`. `target_text` ist bei `corrected` Pflicht und nicht leer, bei jedem anderen Status verboten. Damit schreibt kein Status stillschweigend Text um.
- **Zuordnung beim Laden** (`review_items(candidates, decisions)`): Jeder Kandidat bekommt seinen Status. Eine Entscheidung heißt **veraltet**, wenn `reference_processed_at` nicht mehr zur Fassung im Kandidatenkopf passt, also nach einer Neutranskription. Sie heißt **verwaist**, wenn ihr Kandidat fehlt, etwa weil die Passage nach neuer Kalibrierung sicher ist. Beide Fälle bleiben in der Datei stehen und werden gezählt zurückgegeben, keiner wird gelöscht oder angewendet. Eine neue Bewertung bei gleicher Referenz lässt Entscheidungen gültig, denn sie beziehen sich auf den Text, nicht auf die Stufe.
- **`decide(decisions, candidate, status, target_text=None, note=None)`** liefert eine neue Menge mit genau einem Eintrag pro Kandidat und ersetzt einen früheren Eintrag. Eine Historie gibt es nicht, bis jemand sie braucht.
- **Format:** `format_version: 1`, `session`, `updated_at`, `decisions: [...]`, sortiert nach Segment und Passage, damit Diffs stabil bleiben. Der Loader lehnt andere Versionen, eine fremde Session, doppelte IDs, einen unbekannten Status und `target_text`-Regelverstöße mit Datei, Eintragsnummer und Feld ab, ohne Inhalt zu zitieren. Eine fehlende Datei bedeutet: keine Entscheidungen.
- **Kein CLI-Befehl.** Die Review-Oberfläche ist nicht im Scope. TOOL-47/48 sind die ersten Aufrufer.

## Daten-Check
- TOOL-66: handled. `decisions.json` enthält Zieltexte und Notizen, also echten Sitzungsinhalt, und liegt nur unter `work/` (gitignored). Fehlermeldungen nennen Datei, Eintragsnummer und Feld, nie Text oder Notiz.
- Repo/Fixtures: handled. Die Tests bauen Kandidaten synthetisch wie `tests/test_candidates.py`, ohne echte Session.
- Logs: handled. Das Modul loggt nichts.

## Contract-Check
- N/A, weil `decisions.json` internes Zwischenformat ist und Narrata es nie liest. Wie Status auf den Export wirken (etwa `unintelligible` → Marker), entscheidet TOOL-49/69 gegen IOA-1214. Narrata braucht keine Änderung.

## Resume-Check
- N/A, weil weder Modell noch lange Laufzeit im Spiel sind. Geschrieben wird atomar mit `write_atomic`, ein Abbruch lässt die alte Fassung stehen.

## Format-Check
- handled. Neues Format `decisions.json` mit `format_version: 1` und einem Loader, der andere Versionen ablehnt. `candidates.json` bleibt unverändert v1. Bestehende Artefakte gibt es keine.

## Chunks
### Chunk 1 — Entscheidungsmodell
- Dateien: `src/transcript/decisions.py`, `src/transcript/session.py` (`review_decisions`), `tests/test_decisions.py`
- Änderung: `ReviewStatus`, `ReviewDecision`, `SessionDecisions`, `decide`, `write_decisions`/`load_decisions`, `review_items` mit `ReviewItem` (Kandidat + Entscheidung + Status) sowie veralteten und verwaisten Entscheidungen.
- Verify: `scripts/check`
- AC: Kandidat ohne Entscheidung → `open`; Entscheidung ergänzt, `candidates.json` byteweise unverändert; alle sechs Status speicher- und ladbar; `corrected` ohne Zieltext und Zieltext bei `confirmed` werden abgelehnt; Notiz bei jedem Status; Neutranskription → veraltet; Kandidat weg → verwaist, Eintrag bleibt; falsche Version oder Session wird abgelehnt; Fehlermeldung ohne Text.

### Chunk 2 — Dokumentation
- Dateien: `README.md` (Abschnitt „Review-Entscheidungen“ nach „Review-Kandidaten“, Verzeichnisbaum `review/`, Satz in `:332` anpassen), `docs/transcript-roadmap.py` (Hinweis TOOL-46; `.md` neu generieren)
- Änderung: Status, Regeln für den Zieltext, veraltet/verwaist, Ort der Datei.
- Verify: `scripts/check`
- AC: README nennt alle Status und die Trennung von Kandidat und Entscheidung.

## Folge-Tickets
- Entscheidungen auf eine neue Transkriptfassung übertragen statt sie nur als veraltet zu melden: `[kein Ticket: erst, wenn TOOL-48 zeigt, dass Neutranskription nach dem Review vorkommt]`
- Entscheidungshistorie: `[kein Ticket: kein Bedarf, ein Eintrag pro Kandidat reicht für TOOL-47/48/80]`

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Modul `decisions.py`, Format, Tests | no |
| 2 | README, Roadmap-Hinweis | no |
