# TOOL-9 — ffmpeg-Abhängigkeit einrichten und prüfen

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-9-ffmpeg-preflight` anlegen (`git fetch origin main && git switch -c tool-9-ffmpeg-preflight --no-track origin/main`), prüfen dass `git config --get branch.tool-9-ffmpeg-preflight.merge` leer ist, TOOL-9 auf In Progress setzen, das AC „vor dem Start der Segmentierung“ in Jira zu „vor der Audio-Extraktion (TOOL-10)“ ändern (Grund: TOOL-62, TOOL-11/33 verworfen), diesen Plan als `docs/plans/TOOL-9-ffmpeg-preflight.md` committen (`docs(plans): plan ffmpeg preflight (TOOL-9)`), dann die Chunks.

## Ziel
Danach weiß die Pipeline vor dem ersten ffmpeg-Aufruf, ob `ffmpeg` und `ffprobe` vorhanden und ausführbar sind, kennt deren Versionen und bricht sonst mit einer Meldung ab, die das fehlende Werkzeug und die Installation nennt. `transcript doctor` zeigt das auf der Kommandozeile. Heute ruft nur das Wegwerf-Werkzeug `scripts/spike/` ffmpeg direkt auf, ohne jede Prüfung.

## Ist-Stand
- `src/transcript/__main__.py:23-37`: Subparser mit nur `config`; Fehler laufen als `error: …` auf stderr mit Exit 2 (`:41-50`). Dieses Muster übernimmt `doctor`.
- `src/transcript/config.py:20-21`: `ConfigError` als Vorbild für eine Fehlerklasse, deren Meldung für die Nutzerin gedacht ist.
- `scripts/spike/common.py:92-106`, `scripts/spike/cut.sh:15`: rufen `ffprobe`/`ffmpeg` ohne Prüfung auf; bleiben unberührt, TOOL-64 löst `scripts/spike/` ab.
- `README.md:22-25`: „Voraussetzungen“ nennt nur Python und `python3-venv`, kein ffmpeg.
- `tests/test_smoke.py:14-19`: Helfer `run(*argv)` für CLI-Tests.
- Entwicklungsumgebung: WSL2/Ubuntu 22.04, `/usr/bin/ffmpeg` 4.4.2; `ffprobe` kommt im selben apt-Paket.

**Abhängigkeiten (`/check-ticket-deps`):** keine Blocked-by- und keine Blocks-Links, keine Voraussetzung in der Beschreibung. Ein Finding: Das AC zur Segmentierung ist seit TOOL-62 überholt; entschieden, es in Jira auf die Audio-Extraktion umzuschreiben. Downstream laut Roadmap TOOL-10 und TOOL-56, beide To Do.

## Entscheidungen
- **Eigenes Modul `src/transcript/audio_tools.py`.** `check_audio_tools(search_path: str | None = None) -> AudioTools` liefert pro Werkzeug `ToolInfo(name, path, version)`; `search_path` wird an `shutil.which(path=…)` durchgereicht und macht den Check ohne echte Installation testbar.
- **„Ausführbar“ heißt: `<tool> -version` läuft mit Exit 0 innerhalb von 10 s.** `shutil.which` findet nur ausführbare Dateien; der Versionsaufruf fängt kaputte Installationen ab. `OSError`, Timeout oder Exit ≠ 0 gelten als nicht nutzbar.
- **Version aus der ersten Zeile** per `^(ffmpeg|ffprobe) version (\S+)`; passt sie nicht, wird die ganze erste Zeile übernommen, statt zu scheitern. Keine Mindestversion: Das Ticket verlangt keine, und 4.4 reicht für das Extrahieren.
- **Ein Fehler für beide Werkzeuge.** `AudioToolError(Exception)` nennt alle fehlenden oder kaputten Werkzeuge in einer Meldung und hängt den Hinweis `sudo apt install ffmpeg (installiert ffmpeg und ffprobe)` an. Fehlt nur `ffprobe`, steht nur `ffprobe` in der Meldung.
- **Logging auf INFO** über `logging.getLogger("transcript.audio_tools")`: Werkzeug, Version, Pfad. Kein Transkripttext beteiligt.
- **CLI `transcript doctor`.** Gibt pro Werkzeug `ffmpeg 4.4.2 (/usr/bin/ffmpeg)` aus und endet mit 0; bei einem Fehler `error: …` auf stderr, Exit 2. Liest keine Konfiguration. TOOL-56 kann den Befehl später erweitern.
- **Keine Mindestversion, keine automatische Installation** (Ticket: nicht im Scope).

## Daten-Check
- Folgt TOOL-66: handled — der Check fasst keine Aufnahmen, Transkripte oder Namen an.
- Echtes im Repo: handled — Tests legen Stub-Skripte in einem temporären Verzeichnis an; kein Audio, keine Fixture.
- Logs und Fehlermeldungen: handled — sie enthalten nur Werkzeugname, Pfad und Versionszeile.

## Contract-Check
N/A — kein Contract-JSON, kein Endpoint.

## Resume-Check
N/A — kein langlaufender oder modellgestützter Schritt.

## Dependency-Check
- Nötig: handled — ffmpeg/ffprobe sind Systemwerkzeuge, die TOOL-10 braucht; keine neue Python-Abhängigkeit (`shutil`, `subprocess`, `re` aus der Standardbibliothek).
- Lokal: handled — läuft vollständig lokal, kein Netzwerk.
- Lizenz: handled — ffmpeg (LGPL/GPL) wird als separates Programm per Subprozess aufgerufen und nicht mitgeliefert.
- Hardware: N/A — keine Anforderungen.

## Format-Check
N/A — kein internes Format mit Versionsfeld.

## Chunks
### Chunk 1 — Preflight-Modul
- Dateien: `src/transcript/audio_tools.py`, `tests/test_audio_tools.py`
- Änderung: `ToolInfo`, `AudioTools`, `AudioToolError`, `check_audio_tools(search_path=None)` wie in den Entscheidungen. Tests erzeugen in einem `TemporaryDirectory` ausführbare Shell-Stubs (`#!/bin/sh` + `echo "ffmpeg version 6.1.1 …"` bzw. `exit 1`) und übergeben das Verzeichnis als `search_path`.
- Verify: `scripts/check`
- AC: Beide Stubs vorhanden → Versionen `6.1.1` erkannt, INFO-Log enthält sie. Nur `ffprobe` fehlt → Meldung nennt nur `ffprobe` und den apt-Hinweis. Beide fehlen → beide genannt. Stub mit Exit 1 → als nicht nutzbar gemeldet. Unbekanntes Versionsformat → erste Zeile übernommen.

### Chunk 2 — `transcript doctor` und README
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`
- Änderung: Subcommand `doctor` wie in den Entscheidungen; Test über `run("doctor")` mit gepatchtem `check_audio_tools` (Erfolg: Exit 0, Version in stdout; Fehler: Exit 2, `error:` in stderr, kein Traceback). README: ffmpeg unter „Voraussetzungen“ mit `sudo apt install ffmpeg`, `transcript doctor` im Setup, Stand-Satz oben aktualisieren.
- Verify: `scripts/check`, dann `.venv/bin/transcript doctor` und `PATH=/nonexistent .venv/bin/python -m transcript doctor` (Fehlerfall von Hand)
- AC: Alle Akzeptanzkriterien von TOOL-9 sind belegt; der Fehlerfall von Hand nennt ffmpeg und ffprobe samt Installationshinweis.

## Folge-Tickets
- TOOL-10: `check_audio_tools()` vor der ersten Extraktion aufrufen und die Versionen ins Log schreiben. Kommentar ans Ticket beim Abschluss.
- TOOL-56: `transcript doctor` ist der Ausgangspunkt des Gesamt-Preflights. Kommentar ans Ticket beim Abschluss.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Preflight-Modul mit Tests | no |
| 2 | CLI `transcript doctor`, README | no |
