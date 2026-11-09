# TOOL-56 — Session-Preflight für End-to-End-Verarbeitung

## Ziel
Vor einem langen lokalen Lauf prüft `transcript doctor <session>`, ob alles für die Session bereitsteht: Werkzeuge, Konfiguration, ASR- und Diarisierungsmodell, Gerät, Plattenplatz, Audio, Narrata-Kontext bzw. Snapshot, beschreibbare Pfade und bestehende Artefakte. Heute prüft `doctor` nur ffmpeg/ffprobe; fehlende Modelle, ein kaputter Snapshot oder eine inkonsistente `audio.json` fallen erst mitten in `transcribe` auf. TOOL-55 ruft denselben Preflight als ersten Schritt auf.

## Ist-Stand
- `transcript doctor` ruft nur `audio_tools.check_audio_tools()` (`src/transcript/__main__.py:333`, `src/transcript/audio_tools.py:35`), ohne `--config`, Exit 2 bei Fehler.
- Backends prüfen ohne Laden: `WhisperBackend.identity()` (`src/transcript/asr/whisper.py:89`) deckt Runtime, Modell im lokalen Cache (`cached_model_dir`, `asr/backend.py:151`) und Gerät (`resolve_device`, `asr/backend.py:142`, `cuda` ohne GPU = Fehler) ab; `PyannoteDiarizer.identity()` (`diarization/pyannote.py:61`) Runtime und Modell, aber kein Gerät.
- Konfiguration: `load_config` (`config.py:171`) wirft `ConfigError` mit Pfad und Schlüssel.
- Audio: `audio.find_recordings` (`audio.py:83`), `audio.probe` (`audio.py:107`, liefert `duration`) — beides nur lesend.
- Narrata: `narrata.read_session` über `paths.narrata_context`; Token über `read_token(os.environ, .env)` (`narrata_client.py:22`); `_fetch` braucht `narrata.url` und `narrata.groups[group]` (`__main__.py:541`).
- Snapshot: `knowledge.load_snapshot` (`knowledge.py:164`) prüft Version, Session, ID und Contract; `knowledge.drift` (`knowledge.py:206`) meldet geänderten Kontext oder Budget.
- Resume-Artefakte: `manifest.load_manifest` (`manifest.py:144`, prüft Session und `play_session_id`), `reference.load_reference` (`reference.py:361`), `BackendIdentity.matches` (`asr/backend.py:124`), `transcribe_session` verlangt die Segment-WAVs (`transcription.py:256`).
- Pfade: `SessionPaths` (`session.py:56`).

## Entscheidungen
- **`doctor` wird erweitert, kein neuer Befehl.** `transcript doctor` prüft die Umgebung (ffmpeg/ffprobe, Konfiguration, Modelle, Gerät); `transcript doctor <session>` zusätzlich die Session. Grund: Übergabe aus TOOL-9, ein Einstieg statt zwei.
- **Neues Modul `src/transcript/preflight.py`** mit `Finding(level, check, message)` (`level` ∈ `ok`/`warning`/`error`) und `run(config_path, key | None, …) -> list[Finding]`. Alle Prüfungen laufen durch, auch nach einem Fehler, damit ein Lauf alle Probleme zeigt. TOOL-55 ruft `run` direkt auf.
- **Fehler blockieren, Warnungen nicht:** Exit 0 mit Bestätigungszeile `preflight ok: <n> checks, <w> warning(s)`, Exit 2 bei mindestens einem Fehler.
- **Narrata ohne Netzwerkaufruf.** Fehlt der gespeicherte Kontext, prüft der Preflight nur `narrata.url`, `narrata.groups[<group>]` und ein lesbares Token; kein HTTP-Request, damit der Preflight offline und ohne Teilnehmerdaten läuft. Fehlt beides (Kontext und Zugang) → Fehler mit Hinweis auf `transcript context --from-file`.
- **Kein Preflight-Bericht als Datei.** Das Ticket nennt ihn optional; TOOL-55 nutzt die Rückgabe von `run`. Der Preflight schreibt nichts, legt auch keine Verzeichnisse an.
- **Konsistenz billig prüfen:** `audio.json` gegen die Aufnahmen über Dateiname und Größe, nicht über SHA-256 (Stunden Audio zu hashen gehört nicht in einen Preflight).
- **Plattenplatz:** fehlen die Segment-WAVs noch, Bedarf = Σ Dauer × `sample_rate` × `channels` × 2 Byte; freier Platz darunter → Fehler.

### Prüfungen
| Check | Fehler | Warnung |
| --- | --- | --- |
| `audio-tools` | ffmpeg/ffprobe fehlt oder läuft nicht | — |
| `config` | Datei fehlt oder ungültig (dann entfallen die abhängigen Checks mit einem Satz) | — |
| `asr` | Runtime/Modell fehlt, `cuda` ohne GPU | `auto` landet auf CPU (langsam) |
| `diarization` | Runtime/Modell fehlt | — |
| `session-input` | kein `input/`-Verzeichnis, keine Aufnahme, Aufnahme nicht lesbar/probebar | mehrere Aufnahmen: Export braucht Contract 1.1 (IOA-1287) |
| `paths` | `work/`/`output/` bzw. nächster existierender Vorfahre nicht beschreibbar | — |
| `disk` | zu wenig Platz für die WAVs | — |
| `knowledge` | kein Kontext und kein Narrata-Zugang; vorhandener Snapshot ungültig | Snapshot hinter Kontext oder Budget (`drift`); kein Snapshot (wird gebaut) |
| `resume` | `audio.json`/Manifest passt nicht zu Aufnahmen bzw. Session; Manifest-Segment ohne WAV; gespeichertes Referenztranskript unlesbar | Referenz mit anderem Modell/Settings → wird neu transkribiert; keine Einwilligungsnotiz im Manifest |

## Daten-Check
- Aufnahmen: *handled* — nur `find_recordings`/`probe`, lesend; keine Kopie, kein Hash.
- Teilnehmernamen: *handled* — Snapshot und Kontext werden nur geladen; Meldungen nennen Pfade, Zähler und Check-Namen, nie Teilnehmer, Glossar oder Transkripttext (TOOL-66).
- Token: *handled* — nur „lesbar ja/nein“, der Wert erscheint nie in Ausgabe oder Fehlertext.
- Logs: *handled* — `doctor` läuft wie bisher ohne `_log_to_stderr`; Backend-Meldungen enthalten Pfade und Modellnamen, keine Inhalte.
- Fixtures: *handled* — Tests nutzen `tests/media.py` und anonymisierte Fixtures aus `tests/fixtures/`, keine echten Daten.

## Contract-Check
- Export-Contract (IOA-1214): N/A — der Preflight liest und schreibt keinen Export.
- Narrata-Kontext: *handled* — Version prüft weiterhin `load_snapshot` → `narrata.check_contract`; keine neue Regel.
- Narrata-Endpoint: N/A — kein Request; Narrata braucht keine Änderung, kein IOA-Ticket.

## Resume-Check
- Abbruch: N/A — der Preflight schreibt nichts; ein Abbruch hinterlässt keinen Zustand.
- Wiederverwendung: *handled* — er meldet, welche Segmente `transcribe` wiederverwenden würde und welche wegen anderem Modell oder anderen Settings neu laufen (`BackendIdentity.matches`); Snapshot- und Keyword-Abgleich bleibt bei `transcribe` (`_reusable`), weil er die Domäne laden müsste.
- Gleiches Modell und Snapshot: *handled* — Modellabweichung und Snapshot-Drift als Warnung. Ein vollständiger Pipeline-Status über alle Stufen ist TOOL-57.

## Dependency-Check
- N/A — keine neue Abhängigkeit, kein neues Modell; nur `shutil.disk_usage`, `os.access` und vorhandene Module.

## Format-Check
- N/A — kein internes Format ändert sich, keine Datei wird geschrieben.

## Chunks
### Chunk 1 — Preflight-Kern: Umgebung
- Dateien: `src/transcript/preflight.py`, `tests/test_preflight.py`
- Änderung: `Finding`, `run(...)` mit `audio-tools`, `config`, `asr`, `diarization`; Seams für Tests: `search_path` an `check_audio_tools`, Backend-Fabriken als Parameter (Default `WhisperBackend.from_config`, `PyannoteDiarizer.from_config`).
- Verify: `scripts/check`
- AC: fehlendes ffmpeg/ffprobe erkannt; fehlendes ASR-Backend erkannt; ungültige Konfiguration erkannt, übrige Checks laufen trotzdem.

### Chunk 2 — Session-Prüfungen
- Dateien: `src/transcript/preflight.py`, `tests/test_preflight.py`
- Änderung: `session-input`, `paths`, `disk`, `knowledge`, `resume` wie in der Tabelle; Tests mit `tmp_path` und Fake-Backend-Identität, darunter: Preflight lässt alle Dateien unverändert (mtime/Inhalt vorher = nachher), läuft ohne Token bei gespeichertem Kontext, kein Alttranskript nötig.
- Verify: `scripts/check`
- AC: fehlende Pflichtdateien, Snapshot-/Wissensprobleme, nicht beschreibbare Pfade erkannt; Preflight verändert keine Daten; weder Alttranskript noch API-Key vorausgesetzt.

### Chunk 3 — CLI und Doku
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py` (oder eigener CLI-Test), `README.md`
- Änderung: `doctor [session] [--config]`; Ausgabe je Finding `ok|warning|error <check>: <message>`, Abschlusszeile `preflight ok: …` bzw. `preflight failed: <e> error(s), <w> warning(s)`; Exit 0/2; README-Abschnitt „Preflight“ ersetzt den `doctor`-Absatz.
- Verify: `scripts/check`; manuell `transcript doctor` und `transcript doctor <session>` gegen eine lokale Session in `input/`
- AC: Warnungen verhindern den Start nicht, Fehler schon; erfolgreicher Preflight eindeutig bestätigt.

## Folge-Tickets
- TOOL-55: Der E2E-Befehl ruft `preflight.run` vor dem ersten Schritt auf und bricht bei Fehlern ab — Übergabe-Kommentar beim Abschluss.
- TOOL-57: Pipeline-Status über alle Stufen (Working, Export, Render) baut auf dem `resume`-Check auf — Übergabe-Kommentar beim Abschluss.
- Netzwerkprobe gegen Narrata (Token gültig, Gruppe erreichbar): [kein Ticket: `transcript context` meldet das beim Abruf selbst, ein Preflight-Request brächte nur Teilnehmerdaten ohne Nutzen]
- Preflight-Bericht als Datei: [kein Ticket: optional laut Ticket, TOOL-55 nutzt die Rückgabe direkt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Preflight-Kern: Umgebung | no |
| 2 | Session-Prüfungen | no |
| 3 | CLI und Doku | no |
