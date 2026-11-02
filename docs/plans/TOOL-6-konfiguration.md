# TOOL-6 — Zentrale Basiskonfiguration einführen

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-6-konfiguration` anlegen (`git fetch origin main && git switch -c tool-6-konfiguration --no-track origin/main`), prüfen dass `git config --get branch.tool-6-konfiguration.merge` leer ist, TOOL-6 auf In Progress setzen, diesen Plan als `docs/plans/TOOL-6-konfiguration.md` committen (`docs(plans): plan base configuration (TOOL-6)`), dann die Chunks.

## Ziel
Danach stehen Sprache, Datenwurzel, Segmentierung und Debug-Modus in einer Datei außerhalb des Codes, und das Programm liest sie ein und meldet Fehler verständlich. Heute gibt es keine Konfiguration: `SessionPaths` bekommt sein `root` von niemandem, und die Regel aus TOOL-66, dass Transkripttext nur in eine Logdatei unter `work/` darf, ist nirgends technisch umgesetzt.

## Ist-Stand
- `src/transcript/session.py:43-60`: `SessionPaths(key, root)` leitet `input_dir`, `work_dir`, `output_dir` aus `root` ab. Einen Aufrufer gibt es noch nicht.
- `src/transcript/__main__.py:9-19`: nur `--version` und Hilfe, keine Subcommands.
- `pyproject.toml:10`: `dependencies = []`, `requires-python = ">=3.10"`. Die `.venv` läuft auf Python 3.10.12, `tomllib` fehlt also; PyYAML ist nicht installiert.
- `README.md:73`: Layout nennt `work/<gruppe>/<ordinal>/debug.log`, „nur im Debug-Modus“.
- `docs/datenschutz.md:36`: Debug-Text nur in eine Logdatei unter `work/`, nie auf die Konsole.
- `.gitignore:15-17`: `.env` ist ignoriert, `.env.example` erlaubt. `config/` gibt es noch nicht.
- `tests/test_gitignore.py:7-37`: Tabellen `IGNORED` und `NOT_IGNORED`, einfach erweiterbar.
- `scripts/check:20`: `unittest discover -s tests`, neue Tests laufen automatisch mit.

**Abhängigkeiten (`/check-ticket-deps`):** TOOL-6 hat keine Blocked-by-Links und keine Voraussetzungen in der Beschreibung, nur „relates to“ TOOL-66, TOOL-4 und TOOL-5, alle Done. Keine Blocks-Links, keine Findings, der Plan kann fixiert werden.

## Entscheidungen
- **YAML mit PyYAML.** Das Ticket schlägt es vor, die Datei braucht Kommentare, und `tomllib` gäbe es erst ab Python 3.11. Gelesen wird nur mit `yaml.safe_load`.
- **Zwei Dateien.** `config/example.yaml` liegt im Repo, die lokale `config/config.yaml` wird aus ihr kopiert und ist ignoriert, weil sie lokale Pfade enthalten kann. `transcript config --config <pfad>` überschreibt den Standardpfad.
- **Pflicht sind `language` und `paths.root`.** Beide sind bewusste Entscheidungen pro Installation; `debug` (`false`) und die Segmentwerte haben Defaults.
- **`paths.root` deckt Session- und Ausgabepfade ab, abweichend vom Wortlaut des Tickets.** TOOL-4 legt `input/`, `work/`, `output/` unter einem `root` fest. Ein eigener Ausgabepfad könnte echte Daten aus diesem Layout und damit aus den Ignorierregeln herausführen. Ein relatives `root` gilt ab dem aktuellen Arbeitsverzeichnis.
- **Segmentwerte sind `null`, bis TOOL-62 entscheidet.** `segmentation.length_seconds` und `segmentation.overlap_seconds` sind Platzhalter; ein erfundener Zahlenwert sähe wie eine Entscheidung aus. Gesetzte Werte müssen positiv sein, und die Überlappung muss kleiner als die Länge sein.
- **Unbekannte Schlüssel sind ein Fehler.** Sonst bliebe ein Tippfehler wie `debgu: true` still wirkungslos.
- **Ein Feld `debug`, kein Log-Level.** Nichts würde ein Level bisher lesen. Der Text-Logger aus Chunk 3 setzt die Übergabe aus TOOL-66 um: `propagate = False`, nur ein `FileHandler` auf `work/<gruppe>/<ordinal>/debug.log`, ohne Debug-Modus ein `NullHandler` und keine Datei.
- **Keine `.env.example`.** Die Konfiguration kommt ohne Umgebungsvariablen aus, die erste Variable ist das Narrata-Token. Die Übergabe wandert an TOOL-67.

## Daten-Check
- Folgt TOOL-66: handled — Transkripttext geht nur im Debug-Modus und nur nach `work/.../debug.log`; ein Test prüft, dass dabei nichts auf stderr erscheint.
- Echtes im Repo: handled — `config/config.yaml` ist ignoriert, `config/example.yaml` enthält nur `root: .` und `language: de`; Tests nutzen `beispielgruppe/042` und temporäre Verzeichnisse.
- Logs und Fehlermeldungen: handled — Meldungen nennen Dateipfad, Schlüssel und Regel; die Konfiguration enthält keinen Transkripttext.

## Contract-Check
N/A — kein Contract-JSON, kein Endpoint.

## Resume-Check
N/A — kein langlaufender Schritt.

## Dependency-Check
- Nötig: handled — `pyyaml>=6` als erste Laufzeitabhängigkeit, sonst kein YAML unter Python 3.10.
- Lokal: handled — reiner Parser, kein Netzwerkzugriff.
- Lizenz: handled — MIT.
- Hardware: N/A — keine Anforderungen. `.venv` braucht einmal `pip install -e '.[dev]'`.

## Format-Check
N/A — die Konfiguration hat kein Versionsfeld, und es gibt keine Bestandsartefakte.

## Chunks
### Chunk 1 — Konfiguration laden und prüfen
- Dateien: `pyproject.toml`, `src/transcript/config.py`, `config/example.yaml`, `.gitignore`, `tests/test_config.py`, `tests/test_gitignore.py`
- Änderung: `Config` als frozen Dataclass (`language`, `root`, `debug`, `segment_length_seconds`, `segment_overlap_seconds`), `load_config(path) -> Config`, `ConfigError(Exception)`. `config/config.yaml` in `.gitignore`. `language` muss `[a-z]{2}` entsprechen; `bool` gilt nicht als Zahl.
- Verify: `.venv/bin/pip install -e '.[dev]' && scripts/check`
- AC: `config/example.yaml` lädt. Fehlende Datei, kaputtes YAML, fehlender Pflichtwert, falscher Typ, unbekannter Schlüssel und Überlappung ≥ Länge führen je zu einem `ConfigError`, der Datei und Schlüssel nennt. Defaults greifen. `config/config.yaml` ist ignoriert, `config/example.yaml` nicht.

### Chunk 2 — CLI-Befehl `transcript config`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`
- Änderung: Subcommand `config [--config PATH]` (Default `config/config.yaml`) gibt die wirksamen Werte zeilenweise aus. `ConfigError` erscheint als `error: …` auf stderr mit Exit-Code 2, ohne Traceback; bei fehlender Standarddatei nennt die Meldung die Kopie aus `config/example.yaml`. Der Aufruf ohne Subcommand bleibt unverändert.
- Verify: `scripts/check`, dann `.venv/bin/transcript config --config config/example.yaml`
- AC: Ein Smoke-Test liest `config/example.yaml` und findet `language: de` in der Ausgabe. Ein zweiter Test prüft Fehlertext und Exit-Code bei fehlendem Pflichtwert.

### Chunk 3 — Debug-Log und `SessionPaths`-Anbindung
- Dateien: `src/transcript/config.py`, `src/transcript/session.py`, `src/transcript/debug_log.py`, `tests/test_debug_log.py`, `tests/test_config.py`
- Änderung: `Config.session_paths(key) -> SessionPaths` setzt `root` aus der Konfiguration. `SessionPaths.debug_log` zeigt auf `work_dir / "debug.log"`. `transcript_logger(config, paths)` liefert den Logger für Transkripttext wie in den Entscheidungen beschrieben und legt `work_dir` nur im Debug-Modus an.
- Verify: `scripts/check`
- AC: Mit `debug: true` steht der Text in `debug.log` und nicht auf stderr. Mit `debug: false` entsteht keine Datei und kein Verzeichnis. Auch ein konfigurierter Root-Logger empfängt den Text nicht. Die Pfade aus `session_paths` liegen unter dem konfigurierten `root`.

### Chunk 4 — README
- Dateien: `README.md`
- Änderung: Abschnitt „Konfiguration“ (Kopie anlegen, Schlüsseltabelle mit Pflicht/Default, `transcript config`, relatives `root`, keine Secrets in der Datei), `config/` in der Verzeichnisstruktur, Stand-Satz oben aktualisieren.
- Verify: `scripts/check`
- AC: Alle Akzeptanzkriterien von TOOL-6 sind belegt; nichts widerspricht `docs/datenschutz.md`.

## Folge-Tickets
- TOOL-67: `.env.example` anlegen, sobald das Narrata-Token die erste Variable ist. Kommentar ans Ticket beim Abschluss.
- TOOL-11: Die Segmentwerte in der Konfiguration sind `null`; das Ticket setzt die Defaults nach der Entscheidung aus TOOL-62. Kommentar ans Ticket beim Abschluss.
- TOOL-64: Transkripttext im Debug-Modus nur über `transcript_logger` schreiben. Kommentar ans Ticket beim Abschluss.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Laden, Prüfen, Beispieldatei, PyYAML | no |
| 2 | CLI `transcript config` | no |
| 3 | Debug-Log, `SessionPaths`-Anbindung | no |
| 4 | README | no |
