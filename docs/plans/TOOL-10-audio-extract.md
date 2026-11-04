# TOOL-10 — Eingabeformate erkennen, validieren und Audiospur extrahieren

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-10-audio-extract` anlegen (`git fetch origin main && git switch -c tool-10-audio-extract --no-track origin/main`), prüfen dass `git config --get branch.tool-10-audio-extract.merge` leer ist, TOOL-10 auf In Progress setzen, in Jira „im Manifest festhalten“ zu „in `work/<session>/audio/audio.json` festhalten, TOOL-12 übernimmt es ins Manifest“ ändern, diesen Plan als `docs/plans/TOOL-10-audio-extract.md` committen (`docs(plans): plan audio extraction (TOOL-10)`), dann die Chunks.

## Ziel
Danach nimmt die Pipeline eine Aufnahme aus `input/<gruppe>/<ordinal>/` an, prüft sie per ffprobe (Container, Codec, Audiostreams, Dauer) und extrahiert die gewählte Audiospur als 16-kHz-Mono-WAV nach `work/<gruppe>/<ordinal>/audio/`. Daneben legt sie eine `audio.json` mit den Metadaten ab. Ungeeignete, beschädigte oder audiolose Dateien werden mit einer verständlichen Meldung abgelehnt. Heute gibt es nur den Preflight (`transcript doctor`). ffprobe ruft bisher nur das Wegwerf-Werkzeug `scripts/spike/` auf.

## Ist-Stand
- `src/transcript/audio_tools.py:35-46`: `check_audio_tools()` liefert `AudioTools` mit Pfad und Version von ffmpeg/ffprobe und loggt beide auf INFO (`:76`). Die Extraktion ruft genau diese Pfade auf.
- `src/transcript/audio_tools.py:18-19`, `src/transcript/config.py:19-20`: Fehlerklassen, deren Meldung für die Nutzerin gedacht ist. Das ist das Vorbild für `AudioError`.
- `src/transcript/session.py:43-64`: `SessionPaths` mit `input_dir` und `work_dir`. Laut Layout im README gehört die extrahierte Spur nach `work/<session>/audio/`.
- `src/transcript/config.py:14-16, 23-29, 75-88`: Abschnitte über `_section` und Zahlen über `_positive_number`, `format_config` spiegelt das Layout. Ein neuer Abschnitt `audio` folgt diesem Muster.
- `src/transcript/__main__.py:23-43`: Subcommands `config` und `doctor`, Fehler als `error: …` auf stderr mit Exit 2.
- `scripts/spike/common.py:92-106`: Ungeprüfter ffprobe-Aufruf für die Dauer. Bleibt unberührt, TOOL-64 löst ihn ab.
- `tests/fixtures/README.md:6`: Kein Audio im Repo, Tests erzeugen es zur Laufzeit.
- Entwicklungsumgebung: ffmpeg 4.4.2 unter WSL2/Ubuntu 22.04.

**Abhängigkeiten (`/check-ticket-deps`):** Es gibt keine Blocked-by- und keine Blocks-Links. TOOL-5 und TOOL-9 (Relates) sind Done, ohne Divergenz. Ein Finding: „im Manifest festhalten“, obwohl das Manifest erst mit TOOL-12 kommt. Entschieden: eigene `audio.json`, die TOOL-12 übernimmt.

## Entscheidungen
- **Modul `src/transcript/audio.py`**, getrennt vom Preflight. Es enthält:
  - `probe(path, tools) -> AudioInfo`
  - `extract(info, paths, settings, tools, stream=0) -> ExtractedAudio`
  - `AudioError(Exception)`
  - die Dataclasses `AudioStream(index, codec, channels, sample_rate, duration)` und `AudioInfo(path, container, duration, audio_streams, has_video)`

  `AudioInfo` ist die zentrale interne Repräsentation, die das Ticket verlangt.
- **Format über ffprobe, nicht über die Endung.** `ffprobe -v error -show_format -show_streams -of json` wird geparst. Akzeptiert werden die `format_name`-Werte der Allowlist `mov,mp4,m4a,3gp,3g2,mj2` (MP4/M4A), `mp3` und `wav`, als Konstante, die sich erweitern lässt. Jeder Audio-Codec, den ffprobe erkennt, gilt als zulässig.
- **Ablehnungen, je mit eigener Meldung:**
  - Datei fehlt oder ist nicht lesbar
  - ffprobe scheitert („beschädigt oder kein Medienformat“, letzte stderr-Zeile angehängt)
  - Container nicht auf der Allowlist (der erkannte Name wird genannt)
  - kein Audiostream
  - Dauer fehlt oder ist ≤ 0
  - Streamindex außerhalb des Bereichs
- **Stream-Wahl:** `stream` zählt nur die Audiostreams, Default 0, also der erste. In `audio.json` stehen der gewählte Audio-Index und der absolute Streamindex.
- **Extraktion:** `ffmpeg -nostdin -v error -i <src> -map 0:<abs index> -vn -ac <channels> -ar <rate> -c:a pcm_s16le -f wav <tmp>` schreibt in eine Temp-Datei in `work/<session>/audio/`. Danach folgt `os.replace` nach `audio.wav`, im Fehlerfall wird die Temp-Datei gelöscht. Das Videobild wird nie dekodiert (`-map` auf den Audiostream, `-vn`). Exit ≠ 0 führt zu `AudioError` mit der letzten stderr-Zeile.
- **Dauer-Abgleich:** Die Dauer des WAV kommt exakt aus dem `wave`-Header (Frames ÷ Rate). Sie wird mit der Stream-Dauer aus ffprobe verglichen, ersatzweise mit der Format-Dauer. Bei mehr als 0,5 s Abweichung folgt `AudioError` mit beiden Werten, und das WAV wird verworfen. Grund: Eine solche Abweichung deutet auf eine abgeschnittene Datei. Risiko: VBR-MP3 ohne Header, bei denen ffprobe die Dauer schätzt. Zeigt sich das an echten Dateien, kommt ein Folge-Ticket für die Toleranz.
- **`audio.json`** (`format_version: 1`) neben `audio.wav` enthält:
  - die Quelle als Dateiname und Größe
  - `container`, alle Audiostreams, die gewählte Spur, `has_video`
  - die Quelldauer, die extrahierte Dauer und das Zielformat (Rate, Kanäle, `pcm_s16le`)
  - die Versionen von ffmpeg und ffprobe

  Geschrieben wird atomar über Temp-Datei und `os.replace`.
- **Konfiguration:** neuer optionaler Abschnitt `audio` mit `sample_rate` (Default 16000, positive Ganzzahl) und `channels` (Default 1, 1 oder 2). Der Container bleibt fest WAV/PCM16. Das Ticket verlangt nur, dass das Arbeitsformat konfigurierbar ist, und alle Konsumenten lesen WAV.
- **Preflight:** `extract` bekommt `AudioTools`. Die CLI ruft vorher `check_audio_tools()` auf, das die Versionen bereits auf INFO loggt (Übergabe aus TOOL-9).
- **CLI `transcript extract <gruppe>/<ordinal> [--config] [--stream N]`.** Sie erwartet genau eine Datei in `input/<session>/`, sonst `error:` mit der Anzahl. Ausgabe: Container, Codec, Dauer und Zielpfad. Grund: Nur so lässt sich das AC an einer echten Aufnahme von Hand belegen. TOOL-55 baut später den E2E-Befehl darauf auf.
- **Kein Resume, kein Hash.** Ein erneuter Lauf extrahiert neu und ersetzt beide Dateien atomar. Den Audio-Hash braucht das Manifest, er gehört zu TOOL-12.

## Daten-Check
- Folgt TOOL-66: handled. Rohaudio wird nur gelesen. WAV und `audio.json` liegen unter `work/` und sind per `.gitignore` ausgeschlossen. Nichts verlässt den Rechner.
- Echtes im Repo: handled. Tests erzeugen ihr Audio zur Laufzeit per `ffmpeg -f lavfi` (Sinuston, `testsrc`) in einem `TemporaryDirectory`. Keine Fixture, kein Audio im Repo.
- Logs: handled. INFO-Logs nennen nur Session-Schlüssel, Container, Codec, Stream-Anzahl und Dauern, keinen Dateinamen.
- Fehlermeldungen: handled. Sie nennen den Dateinamen der Aufnahme, weil die Nutzerin die Datei sonst nicht findet. Sie enthalten keinen Transkripttext, und den gibt es in diesem Schritt auch noch nicht. Der Dateiname steht auch in `audio.json`, also nur unter `work/`.
- Original unverändert: handled. Die Pipeline schreibt nur nach `work/`. Ein Test vergleicht den SHA-256 der Quelle vor und nach der Extraktion.

## Contract-Check
N/A, weil kein Contract-JSON und kein Endpoint berührt wird. `audio.json` ist eine interne Arbeitsdatei.

## Resume-Check
- Abbruch: handled. Die Temp-Dateien werden im `finally` gelöscht, ein halbes `audio.wav` oder `audio.json` entsteht nie (`os.replace`).
- Wiederverwendung: N/A. Die Extraktion dauert Minuten, nicht Stunden, also extrahiert ein neuer Lauf neu. Resume für die ganze Session regelt TOOL-17/57.
- Modell/Snapshot: N/A, weil kein Modell beteiligt ist.

## Dependency-Check
- Nötig: handled. ffmpeg und ffprobe sind schon durch TOOL-9 eingeführt. In Python kommt nur Standardbibliothek dazu (`json`, `subprocess`, `wave`, `hashlib` in Tests), kein neues Paket.
- Lokal: handled. Alles läuft lokal, ohne Netzwerk.
- Lizenz: handled. ffmpeg läuft als separates Programm im Subprozess.
- Hardware: N/A. Nur CPU, das WAV einer 5-Stunden-Session ist etwa 576 MB groß (16 kHz × 2 Byte × 18 000 s).

## Format-Check
- Version: handled. `audio.json` ist ein neues internes Format und beginnt mit `format_version: 1`.
- Bestehende Artefakte: N/A, weil es noch keine gibt.
- Config: N/A, weil sie kein Versionsfeld hat. Der neue Abschnitt ist optional, also bleiben bestehende `config.yaml` gültig.

## Chunks
### Chunk 1 — Konfiguration `audio`
- Dateien: `src/transcript/config.py`, `tests/test_config.py`, `config/example.yaml`, `README.md` (Konfigurationstabelle)
- Änderung: `Config.audio_sample_rate: int = 16000` und `Config.audio_channels: int = 1`, Abschnitt `audio` in `_TOP_LEVEL_KEYS`, Validierung (positive Ganzzahl; Kanäle 1 oder 2), `format_config` gibt beides aus.
- Verify: `scripts/check`
- AC: Ohne Abschnitt gelten die Defaults 16000/1. `sample_rate: 0`, `channels: 3` und ein unbekannter Schlüssel werden mit Datei und Schlüssel gemeldet. `transcript config` zeigt den Abschnitt.

### Chunk 2 — Probe und Validierung
- Dateien: `src/transcript/audio.py`, `tests/test_audio.py`
- Änderung: `AudioError`, `AudioStream`, `AudioInfo`, `probe()` wie in den Entscheidungen. Der Test-Helfer `synth(path, *args)` ruft ffmpeg mit `lavfi` auf. Die Klasse wird mit `skipUnless(shutil.which("ffmpeg"))` übersprungen, wenn ffmpeg fehlt.
- Verify: `scripts/check`
- AC:
  - MP4 (Video + Audio), M4A, MP3 und WAV werden erkannt, mit Container, Codec, Stream-Anzahl und Dauer ≈ 2 s.
  - MP4 ohne Audio führt zu „no audio stream“.
  - Zufallsbytes mit Endung `.mp3` führen zu „damaged or not a media file“.
  - Ein OGG/Opus-File meldet „unsupported container ogg“.
  - Fehlende Datei: Meldung nennt den Pfad.

### Chunk 3 — Extraktion und `audio.json`
- Dateien: `src/transcript/audio.py`, `tests/test_audio.py`
- Änderung: `extract()`, Dauer-Abgleich, atomares Schreiben von `audio.wav` und `audio.json` wie in den Entscheidungen.
- Verify: `scripts/check`
- AC:
  - Aus einer MP4 mit 48-kHz-Stereo-Audio entsteht ein WAV mit 16 kHz, 1 Kanal und PCM16, Dauerabweichung ≤ 0,5 s.
  - `audio.json` hat `format_version: 1` und `has_video: true`.
  - Bei zwei Audiostreams (440 Hz und 880 Hz) wählt der Default den ersten, `stream=1` den zweiten. `audio.json` hält die Wahl fest, `stream=2` führt zu `AudioError`.
  - Der SHA-256 der Quelle bleibt gleich.
  - Ein gepatchter ffmpeg-Fehler hinterlässt keine Datei in `audio/`.

### Chunk 4 — CLI `transcript extract` und README
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`
- Änderung: Subcommand wie in den Entscheidungen (Config laden, `check_audio_tools()`, genau eine Eingabedatei, `probe` und `extract`, Zusammenfassung ausgeben). Tests über `run("extract", …)` mit temporärem `paths.root`. README: Stand-Satz, neuer Abschnitt zu `transcript extract`, `audio/audio.wav` und `audio.json` im Session-Layout.
- Verify: `scripts/check`, dann `.venv/bin/transcript extract <echte Session>` an einer realen MP4 unter `input/`. Danach `ffprobe work/<session>/audio/audio.wav` und die Dauer gegen das Original vergleichen.
- AC:
  - Erfolg mit Exit 0 und Zusammenfassung.
  - Leeres Eingabeverzeichnis, zwei Dateien oder eine audiolose Datei: Exit 2, `error:` auf stderr, kein Traceback.
  - Alle Akzeptanzkriterien von TOOL-10 sind an der echten Aufnahme belegt.

## Folge-Tickets
- TOOL-12: Das Manifest übernimmt aus `work/<session>/audio/audio.json` Quelle, gewählten Stream und Dauern, dazu den Audio-Hash der Originalaufnahme. Kommentar ans Ticket beim Abschluss.
- TOOL-64, TOOL-76: Eingabe ist `work/<session>/audio/audio.wav` (Rate und Kanäle stehen in `audio.json`). Kommentar an beide Tickets beim Abschluss.
- TOOL-55: `transcript extract` ist der erste Schritt des E2E-Befehls. Kommentar ans Ticket beim Abschluss.
- Toleranz des Dauer-Abgleichs für VBR-MP3 ohne Header: [kein Ticket: nur falls es an echten Dateien auftritt, dann neu anlegen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Konfiguration `audio` | no |
| 2 | Probe und Validierung | no |
| 3 | Extraktion und `audio.json` | no |
| 4 | CLI `transcript extract`, README | no |
