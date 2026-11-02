# TOOL-5 — Regeln für große, sensible und temporäre Dateien

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-5-dateiregeln` anlegen (`git fetch origin main && git switch -c tool-5-dateiregeln --no-track origin/main`), prüfen dass `git config --get branch.tool-5-dateiregeln.merge` leer ist, TOOL-5 auf In Progress setzen, diesen Plan als `docs/plans/TOOL-5-dateiregeln.md` committen (`docs(plans): plan file rules (TOOL-5)`), dann die Chunks.

## Ziel
Danach kann eine echte Aufnahme oder ein Transkript nicht mehr aus Versehen im Repo landen, auch nicht in Formaten oder an Orten außerhalb von `input/`, `work/`, `output/`. Heute decken die Regeln nur sechs Audioformate und die drei Verzeichnisse ab, und ein Fixture-Ort fehlt. Das README nennt außerdem noch nicht, was nie committet und was nie hochgeladen wird.

## Ist-Stand
- `.gitignore:15-17`: `.env`, `.env.*`, Ausnahme `.env.example`. Reicht für das Narrata-Token aus TOOL-67.
- `.gitignore:25-33`: `input/`, `work/`, `output/` und `*.mp4 *.m4a *.mp3 *.wav *.flac *.ogg`.
- Geprüft mit `git check-ignore --no-index`: `.aac .opus .webm .mkv .mov .srt .vtt .docx` werden nicht ignoriert.
- Geprüft: `tests/fixtures/input/x.wav` wird ignoriert, weil die Muster in jeder Tiefe greifen; `tests/fixtures/sample.json` wird nicht ignoriert.
- `README.md:78-84`: Abschnitte „Echte Audio- und Transkriptdateien“ und „Secrets“, kurz gehalten und ohne Aufbewahrung.
- `docs/datenschutz.md:9-14,24,33,39`: Datenarten, Aufbewahrung, Fixture-Regel. Dort stehen die Entscheidungen, das README verweist nur.
- `scripts/check:20`: `unittest discover -s tests`, ein neuer Test läuft also automatisch mit.

**Abhängigkeiten (`/check-ticket-deps`):** TOOL-5 hat keine Blocked-by-Links, nur „relates to“ TOOL-66 und TOOL-4, beide Done und ohne Divergenz-Marker. TOOL-67 nennt das Ticket als späteren Nutzer, nicht als Voraussetzung. Keine Blocks-Links, keine Findings, der Plan kann fixiert werden.

## Entscheidungen
- **Muster bleiben unverankert.** `input/`, `work/`, `output/` greifen weiter in jeder Tiefe; das schützt auch verschachtelte Kopien. Der Preis: Unter `tests/fixtures/` darf kein Verzeichnis so heißen.
- **Fixture-Ort ist `tests/fixtures/`.** Dort landet auch die Contract-Fixture aus IOA-1214. Ein kurzes `tests/fixtures/README.md` nennt die Regeln, damit das Verzeichnis existiert und der Ort auffindbar ist.
- **Keine Ausnahme für Audio in Fixtures.** Audio-Muster gelten auch dort. Tests, die Audio brauchen (TOOL-10), erzeugen es zur Laufzeit synthetisch. So bleibt die Regel ohne Prüfung im Einzelfall gültig: Audio kommt nie ins Repo.
- **Ignorierliste: Audio und Video ergänzen, dazu nur die typischen Transkriptformate.** Neu sind `*.aac *.opus *.wma *.aiff *.webm *.mkv *.mov` sowie `*.srt *.vtt *.docx`. Nicht global ignoriert werden `*.json`, `*.txt`, `*.csv`: Die brauchen Fixtures, Konfiguration und das Repo selbst, und echte Inhalte dieser Formate liegen in `work/` und `output/`.
- **Ein Test sichert die Regeln.** `.gitignore` ist die einzige technische Sperre, ein stilles Entfernen fiele sonst nicht auf. Der Test bleibt klein und braucht nur `git`.
- **`.env.example` entsteht nicht hier.** Noch gibt es keine Variable; TOOL-6 oder TOOL-67 legen die Datei an.
- **Das README verweist, es wiederholt nicht.** Fristen und Gründe bleiben in `docs/datenschutz.md`; das README nennt die Aufbewahrung nur in einem Satz, wie die Übergabe aus TOOL-66 verlangt.

## Daten-Check
- Folgt TOOL-66: handled — Rohaudio und Segmente lokal, nur der strukturierte Export geht nach Narrata; Fixtures synthetisch oder vollständig anonymisiert.
- Echtes im Repo: handled — der Test nutzt nur erfundene Pfade unter `beispielgruppe/042`, legt keine Dateien an und enthält keine Sitzungsdaten.
- Logs und Fehlermeldungen: N/A — kein Laufzeitcode.

## Contract-Check
N/A — kein Contract-JSON, kein Endpoint. `tests/fixtures/` ist nur der Ablageort für die spätere Kopie aus IOA-1214.

## Resume-Check
N/A — kein langlaufender Schritt.

## Dependency-Check
N/A — nur Standardbibliothek und das vorhandene `git`.

## Format-Check
N/A — kein versioniertes Format.

## Chunks
### Chunk 1 — Ignorierregeln und Fixture-Ort
- Dateien: `.gitignore`, `tests/fixtures/README.md`, `tests/test_gitignore.py`
- Änderung: Audio-, Video- und Transkriptmuster ergänzen. `tests/fixtures/README.md` (Deutsch) nennt: synthetisch oder vollständig anonymisiert, keine Klarnamen, kein Audio, keine Verzeichnisse namens `input`, `work`, `output`. Der Test ruft pro Pfad `git check-ignore -q --no-index` auf.
- Verify: `scripts/check`
- AC: Ignoriert werden `.env`, `.env.local`, Audio- und Videodateien an beliebigem Ort inklusive `tests/fixtures/`, `*.srt`, `*.vtt`, `*.docx` sowie alles unter `input/`, `work/`, `output/`. Nicht ignoriert werden `.env.example` und `tests/fixtures/contract-v1.json`. Der Test schlägt fehl, wenn eine Regel entfernt wird.

### Chunk 2 — README
- Dateien: `README.md`
- Änderung: Die Abschnitte „Echte Audio- und Transkriptdateien“ und „Secrets“ durch einen Abschnitt „Dateiregeln“ ersetzen. Inhalt: was nie committet wird (Audio, Segmente, Transkripte, Klarnamen, Wissens-Snapshots, Secrets), was nie hochgeladen wird (Rohaudio, Segmente, Arbeitsdateien, Snapshot; nach Narrata geht nur der strukturierte Export), wie eine echte Session abgelegt wird (`input/<gruppe>/<ordinal>/`, Verweis auf „Sessions“), Aufbewahrung in einem Satz mit Verweis auf `docs/datenschutz.md`, `.env` samt künftigem Narrata-Token, Fixture-Ort. `tests/fixtures/` in die Verzeichnisstruktur aufnehmen.
- Verify: `scripts/check`
- AC: Alle Akzeptanzkriterien von TOOL-5 sind im README belegt; nichts widerspricht `docs/datenschutz.md`.

## Folge-Tickets
- TOOL-10: Tests mit Audio erzeugen es zur Laufzeit synthetisch, Audio-Fixtures sind nicht vorgesehen. Kommentar ans Ticket beim Abschluss.
- IOA-1214: Die Kopie der Contract-Fixture liegt hier unter `tests/fixtures/`. Kommentar ans Ticket beim Abschluss.
- TOOL-6: `.env.example` anlegen, sobald es die erste Variable gibt. Kommentar ans Ticket beim Abschluss.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `.gitignore`, Fixture-Ort, Test | no |
| 2 | README | no |
