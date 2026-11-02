# TOOL-4 — Verzeichnis- und Sessionstruktur

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-4-sessionstruktur` anlegen (`git fetch origin main && git switch -c tool-4-sessionstruktur --no-track origin/main`), TOOL-4 auf In Progress setzen, diesen Plan als `docs/plans/TOOL-4-sessionstruktur.md` committen (`docs(plans): plan session layout (TOOL-4)`), dann die Chunks.

## Ziel
Jede Datei einer Session hat einen festen Ort, abgeleitet aus einem Schlüssel, der der Narrata-Spielsitzung entspricht. Heute gibt es weder Schlüssel noch Pfadlogik; Audio-Extraktion, Manifest, Snapshot und Export hätten keinen gemeinsamen Ablageort. Danach bauen alle Pipeline-Schritte ihre Pfade aus einem geprüften `SessionKey`, sodass sich Sessions nicht vermischen können.

## Ist-Stand
- `src/transcript/__main__.py:9-19`: nur `--help` und `--version`, keine Pipeline-Befehle.
- `tests/test_smoke.py:9-22`: Vorlage für Tests mit `unittest`.
- `.gitignore`: ignoriert `input/`, `work/`, `output/` bereits; `.gitignore`-Änderungen sind Sache von TOOL-5.
- `README.md`, Abschnitt „Verzeichnisstruktur“: nennt nur `docs/`, `scripts/`, `src/transcript/`, `tests/`.
- `docs/datenschutz.md`, Tabelle „Was entsteht und wo es liegt“: legt die Datenarten auf `input/`, `work/`, `output/` fest.
- Narrata (`ios-archiv-backend/database/schema/mysql-schema.sql:1196`): `UNIQUE (group_id, ordinal)` auf `play_sessions`; `groups.slug` ist `varchar(64)`, nullable, Default aus `Str::slug(name)` (`app/Models/Group.php:91-92`).

**Abhängigkeiten (`/check-ticket-deps`):** TOOL-4 hat keine Blocked-by-Links und nennt im Text keine Voraussetzung; TOOL-66 ist Done. Keine Findings, der Plan kann fixiert werden.

## Entscheidungen
- **Kleines Modul statt nur Doku.** Das Ticket erlaubt „angelegt oder dokumentiert“, aber „nicht vermischbar“ lässt sich nur im Code sichern. `src/transcript/session.py` bleibt klein, ohne CLI-Befehl.
- **Gruppen-Kürzel = `groups.slug`.** Das ist der vorhandene lesbare Schlüssel in Narrata. Erlaubt: `[a-z0-9]+(-[a-z0-9]+)*`, höchstens 64 Zeichen, passend zu `Str::slug`. Damit sind auch `..`, `/` und leere Werte ausgeschlossen.
- **Ordinal wird normalisiert.** `42` und `042` ergeben denselben Schlüssel; Darstellung mindestens dreistellig, `1000` bleibt `1000`. Sonst entstünden zwei Ordner für eine Sitzung. Erlaubt sind nur ASCII-Ziffern und Werte ≥ 1.
- **Der Schlüssel ist lesbar, die Identität ist `play_session_id`.** Narrata vergibt das Ordinal als `max(ordinal)+1`; wird die letzte Sitzung gelöscht, kann ein Ordinal erneut vergeben werden. Auch der Slug kann sich ändern. Deshalb trägt das Manifest die `play_session_id`, und bei Abweichung zählt sie.
- **Das Manifest entsteht in TOOL-12.** TOOL-4 legt nur Ort und Pflichtfelder fest, damit beide Tickets kein Format doppelt definieren.
- **`config/` entsteht in TOOL-6.** TOOL-6 liefert auch die konfigurierbaren Session-Pfade; bis dahin nimmt `SessionPaths` das Wurzelverzeichnis als Parameter.
- **Für `input/` gibt es keine Schreib-API.** `SessionPaths` liefert nur Pfade. Die Unveränderlichkeit ist eine dokumentierte Regel; lesende Zugriffe folgen in TOOL-10.

### Layout pro Session
```
input/<gruppe>/<ordinal>/      Originalaufnahme, unveränderlich
work/<gruppe>/<ordinal>/
  manifest.json                Gruppe, Ordinal, play_session_id, Sitzungsdatum, Audio-Hash (TOOL-12)
  audio/                       extrahierte Spur, Segmente
  snapshot/                    Wissens-Snapshot
  asr/                         ASR-Zwischenergebnisse, nie überschrieben
  review/                      Review-Kandidaten, CSV
  speakers/                    Sprecherzuordnung
  debug.log                    nur im Debug-Modus (TOOL-6)
output/<gruppe>/<ordinal>/     JSON-Export, TXT, DOCX
```

## Daten-Check
- Folgt TOOL-66: handled — das Layout übernimmt die Zuordnung aus `docs/datenschutz.md`; Snapshot und Rohaudio bleiben in `work/` bzw. `input/`, nur `output/` geht nach Narrata.
- Echtes im Repo: handled — Doku und Tests nutzen die erfundene Gruppe `beispielgruppe`. Das Ticket-Beispiel `trigon` ist eine echte Gruppe und kommt nicht ins öffentliche Repo.
- Logs und Fehlermeldungen: handled — Fehlertexte enthalten nur den übergebenen Schlüssel, und Session-Schlüssel sind laut TOOL-66 in Logs erlaubt.

## Contract-Check
N/A — kein Contract-JSON, kein Endpoint. Der Schlüssel liest nur vorhandene Narrata-Felder; dort ist keine Änderung nötig.

## Resume-Check
N/A — kein langlaufender Schritt.

## Dependency-Check
N/A — nur Standardbibliothek.

## Format-Check
N/A — kein versioniertes Format; das Manifest entsteht erst in TOOL-12.

## Chunks
### Chunk 1 — Session-Schlüssel und Pfade
- Dateien: `src/transcript/session.py`, `tests/test_session.py`
- Änderung: Frozen Dataclass `SessionKey(group, ordinal)` mit Validierung in `__post_init__`, `SessionKey.parse("gruppe/042")` und `__str__`. Frozen Dataclass `SessionPaths(key, root)` mit `input_dir`, `work_dir`, `output_dir`. Ungültige Werte lösen `ValueError` aus; `fullmatch` verhindert, dass ein angehängter Zeilenumbruch durchgeht.
- Verify: `scripts/check`
- AC: `42` und `042` liefern gleiche Schlüssel und Pfade. `..`, `a/b`, Großbuchstaben, leere Werte, `0`, negative Werte und nicht-ASCII-Ziffern werden abgelehnt. Zwei verschiedene Schlüssel teilen sich kein Verzeichnis, auch nicht `foo/001` und `foo-1/001`.

### Chunk 2 — README
- Dateien: `README.md`
- Änderung: Abschnitt „Verzeichnisstruktur“ um `input/`, `work/`, `output/` und das Layout ergänzen; Schlüssel, Normalisierung, Rolle der `play_session_id` und die Unveränderlichkeit von `input/` erklären; Beispiel-Session `beispielgruppe/042` mit Ablageort von Audio, Snapshot, Zwischenständen, Review und Ergebnis.
- Verify: `scripts/check`; `git grep -n trigon -- README.md src tests` bleibt leer
- AC: Alle Akzeptanzkriterien von TOOL-4 sind im README belegt; das Layout widerspricht `docs/datenschutz.md` nicht.

## Folge-Tickets
- TOOL-12: Manifest liegt unter `work/<gruppe>/<ordinal>/manifest.json`; beim Lesen die `play_session_id` prüfen, weil Ordinale neu vergeben werden können. Kommentar ans Ticket beim Abschluss.
- TOOL-6: Session-Pfade aus der Konfiguration setzen das `root` von `SessionPaths`. Kommentar ans Ticket beim Abschluss.
- TOOL-5: `.gitignore`-Muster `input/` und `work/` greifen in jeder Tiefe; das beim vorgesehenen Fixture-Ort beachten. Kommentar ans Ticket beim Abschluss.
- [kein Ticket: Ein Slug-Wechsel in Narrata wird nicht automatisch nachgezogen; das Risiko ist bei einer festen Gruppe klein und über die `play_session_id` erkennbar]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `SessionKey`, `SessionPaths`, Tests | no |
| 2 | README | no |
