# TOOL-12 — Session-Manifest und absolute Zeiten

Nach der Freigabe, in dieser Reihenfolge: Branch `tool-12-session-manifest` anlegen (`git fetch origin main && git switch -c tool-12-session-manifest --no-track origin/main`), prüfen dass `git config --get branch.tool-12-session-manifest.merge` leer ist, TOOL-12 auf In Progress setzen, die Response-Form von IOA-1215 gegen `ios-archiv` prüfen, an TOOL-12 kommentieren, dass die Überlappung nach TOOL-62 per Konstruktion 0 ist und die Segmente die Teilaufnahmen einer Sitzung sind, diesen Plan als `docs/plans/TOOL-12-session-manifest.md` committen (`docs(plans): plan session manifest (TOOL-12)`), dann die Chunks.

**Abhängigkeiten (`/check-ticket-deps`):** Es gibt keine Blocked-by- und keine Blocks-Links. TOOL-4, TOOL-10, TOOL-62 und TOOL-66 (Relates) sind Done. Ein Finding: TOOL-11 ist nach TOOL-62 verworfen, die Überlappungs-ACs setzen aber Segmentierung voraus. Entschieden: Die Teilaufnahmen sind die Segmente, Überlappung explizit 0.

## Ziel
Danach hat jede Session ein `work/<gruppe>/<ordinal>/manifest.json`. Es enthält Session-Schlüssel, `play_session_id`, Sitzungsdatum, Zustimmungsvermerk und die Segmente in chronologischer Reihenfolge, je Segment mit Quelldatei, Audio-Hash, Arbeits-WAV und absolutem Start und Ende. Spätere Schritte lesen es ohne erneute Audioanalyse und rechnen segmentlokale Zeiten in absolute Session-Zeiten um (`HH:MM:SS.mmm`). Heute gibt es nur `audio.json` für genau eine Aufnahme. Sitzungen aus mehreren Teilaufnahmen (Teil 1/2, I/II, vermutlich wegen der 5-h-Grenze des Geräts aus TOOL-62) lassen sich gar nicht verarbeiten.

## Ist-Stand
- `src/transcript/audio.py:70` `find_recording` verlangt genau eine Datei in `input/<session>/`. Versteckte Dateien und `:Zone.Identifier` ignoriert die Funktion.
- `src/transcript/audio.py:136` `extract` schreibt `audio/audio.wav` und `audio/audio.json` (`METADATA_FORMAT_VERSION = 1`, `audio.py:31`), atomar über ein Temp-Verzeichnis und `os.replace`. Die WAV-Dauer kommt exakt aus dem Header (`_wav_duration`, `audio.py:244`).
- `src/transcript/audio.py:209` `_metadata` liefert Quelle (Name, Größe, Container, Dauer, Streams), gewählten Stream, Ausgabe und Werkzeugversionen. Einen Hash gibt es nicht.
- `src/transcript/session.py:44` `SessionPaths` hat `audio_wav` und `audio_metadata`. `manifest.json` steht bisher nur im README-Layout (`README.md:102`).
- `src/transcript/__main__.py:70` `_extract` ruft `find_recording`, `probe` und `extract` auf.
- `src/transcript/config.py:16` kennt `segmentation.length_seconds/overlap_seconds` (TOOL-6). Seit TOOL-62 nutzt sie niemand.
- IOA-1215 (Done) liefert `GET …/transcription-context` mit `contract_version` und `session: {play_session_id, ordinal, session_date, title, …}`. Den Client, das Token und die Rohdatei baut TOOL-67 (To Do, 11.01.2027).
- Lokal liegen die Aufnahmen noch unsortiert in `input/<gruppe>/ordinal/`, einige Sitzungen in zwei Teilen, dazu bearbeitete Varianten („ohne Stille“, „aufbereitet“).

## Entscheidungen
- **Teilaufnahmen sind die Segmente.** Alle Aufnahmen in `input/<session>/` gehören zur Sitzung. Ihre Reihenfolge ist die lexikalische der Dateinamen; die CLI gibt sie aus, und wer eine andere will, benennt um. Grund: Externe Segmentierung entfällt (TOOL-62), aber echte Sitzungen bestehen aus mehreren Dateien. Die Segment-ACs werden damit ohne Splitting erfüllt.
- **Ein WAV pro Segment, kein Zusammenfügen.** `extract` schreibt `audio/segment-01.wav`, `segment-02.wav`, … Grund: Der Speicherbedarf von ASR und Diarisierung bleibt pro Datei bei höchstens 5 h (TOOL-62: 10,5 GB, TOOL-20: 13,8 GB). Absolute Zeiten liefert das Manifest. `audio/audio.wav` entfällt, TOOL-64 und TOOL-76 bekommen dazu einen Kommentar.
- **Die Session-Zeitachse ist die aneinandergereihte Aufnahmezeit, keine Uhrzeit.** Pausen zwischen den Teilen kennt niemand. Segment n+1 beginnt exakt dort, wo Segment n endet.
- **Zeiten als ganze Millisekunden, abgeleitet aus Sample-Frames.** `start_ms = round(frames_davor · 1000 / rate)`, `end_ms` entsprechend kumuliert. Damit gilt `end_ms(n) == start_ms(n+1)`: keine Lücke, kein negativer Wert, keine Float-Drift über 10 h. `frames` wird mitgespeichert.
- **Überlappung explizit 0.** Jedes Segment hat `overlap_before_ms: 0`. Der Leser prüft `start_ms(n+1) == end_ms(n) - overlap_before_ms(n+1)`. Die `segmentation.*`-Config bleibt unberührt.
- **Hash in `extract`.** SHA-256 jeder Originalaufnahme, gestreamt in 1-MiB-Blöcken, im selben Durchgang, in dem die Datei ohnehin gelesen wird. Er steht in `audio.json` und wird ins Manifest übernommen.
- **`audio.json` → `format_version: 2`** mit einer Liste `segments` (je Quelle, gewählter Stream, Ausgabe, Hash). Werkzeugversionen und Arbeitsformat stehen einmal oben.
- **`play_session_id` und Datum kommen aus der Narrata-Rohdatei** `work/<session>/narrata/transcription-context.json` (Endpoint-Format von IOA-1215). TOOL-12 liest nur den Block `session`. Bis TOOL-67 steht, legt die Nutzerin die Datei selbst ab, danach schreibt TOOL-67 sie an diesen Ort. Grund: kein zweiter Client, kein Token in TOOL-12. Weicht `session.ordinal` vom Schlüssel ab, folgt ein Fehler.
- **`transcript manifest <gruppe>/<ordinal> [--consent] [--config]`** baut das Manifest aus `audio.json`, der Rohdatei und den WAV-Headern. Mit `--consent` entsteht `consent: {"oral": true, "noted_at": "<ISO-Zeit>"}`. Ohne das Flag steht `consent: null` mit einer Warnung auf stderr; nichts blockiert (so entschieden). Ein Neuaufbau ohne Flag übernimmt einen vorhandenen Vermerk bei gleicher `play_session_id`.
- **`play_session_id` als Identität.** Hat ein vorhandenes Manifest eine andere `play_session_id` als die Rohdatei, bricht `manifest` ab: Das Ordinal wurde neu vergeben, das Arbeitsverzeichnis gehört zu einer anderen Sitzung. `load_manifest` prüft dasselbe gegen die Rohdatei, sofern sie vorhanden ist.
- **Einsortieren bleibt Handarbeit.** Die Nutzerin legt die Aufnahmen vor dem ersten Manifest nach `input/<gruppe>/<ordinal>/` und wählt dabei Original oder bearbeitete Variante. Das README beschreibt die Erwartung, Code dafür gibt es nicht.

## Daten-Check
- Folgt TOOL-66: handled. Manifest, `audio.json` und Rohdatei liegen nur unter `work/`. Der Zustimmungsvermerk aus `docs/datenschutz.md:18` steht im Manifest.
- Logs: handled. INFO-Logs nennen Session-Schlüssel, Segmentanzahl und Dauern, keine Dateinamen (Dateinamen enthalten teils Figurennamen) und nichts aus der Rohdatei.
- Fehlermeldungen: handled. Sie nennen Pfade und Feldnamen der Rohdatei, nie deren Werte außer dem Ordinal. Teilnehmernamen aus `participants` werden gar nicht gelesen.
- Fixtures: handled. Die Tests erzeugen Audio synthetisch (`tests/media.py`) und die Rohdatei als minimales Dict mit Fantasie-ID und `beispielgruppe`. Echte Daten kommen nicht ins Repo.

## Contract-Check
- Es wird kein Export-Contract (IOA-1214) gelesen oder geschrieben. Das Manifest ist eine interne Arbeitsdatei.
- Gelesen wird die Response von IOA-1215, nur `session.play_session_id`, `session.ordinal` und `session.session_date`. Handled mit offener Annahme: Die Prüfung gegen `ios-archiv` war beim Planen nicht möglich (kein Lesezugriff aus dieser Umgebung, der lokale Klon kennt noch keinen IOA-1215-Commit). Grundlage ist deshalb die Response-Form aus der Beschreibung von IOA-1215. Der Leser nimmt `play_session_id` als Zahl oder String an und meldet fehlende Felder mit Namen. Belegt wird die Annahme in Chunk 4 an einer echten Response. `contract_version` prüft TOOL-67, TOOL-12 meldet nur fehlende Felder.
- Eine Narrata-Änderung ist nicht nötig. N/A, kein IOA-Ticket.

## Resume-Check
- Abbruch in `extract`: handled. Alle Segment-WAVs entstehen im Temp-Verzeichnis. Erst nach Erfolg werden sie ersetzt, `audio.json` zuletzt als Commit-Punkt, danach werden übrige `segment-*.wav` aus einem älteren Lauf entfernt. `manifest` gleicht die Frame-Zahlen der WAVs mit `audio.json` ab und merkt so eine halbe Ersetzung.
- Wiederverwendung: N/A. Es ist kein modellgestützter Schritt. Ein erneuter `extract` rechnet alles neu, `manifest` ist billig.
- Modell und Snapshot: N/A, kein Modell beteiligt.

## Dependency-Check
N/A, weil keine neue Abhängigkeit entsteht. `hashlib`, `wave` und `json` gehören zur Standardbibliothek.

## Format-Check
- `audio.json` geht von 1 auf 2. Bestehende v1-Dateien (nur unter `work/*/ordinal/spike`, keine echte Session) weist `manifest` ab mit „run transcript extract again“.
- `manifest.json` ist neu und startet mit `format_version: 1`. `load_manifest` lehnt unbekannte Versionen ab.

## Chunks
### Chunk 1 — Zeitstempel-Helfer
- Dateien: `src/transcript/timecode.py`, `tests/test_timecode.py`
- Änderung: `format_ms(ms) -> "HH:MM:SS.mmm"` (Stunden ohne 24-h-Umbruch, negative Werte → `ValueError`), `parse_timecode(str) -> ms`, `frames_to_ms(frames, rate)` mit Rundung auf ganze ms.
- Verify: `scripts/check`
- AC: `00:02:13.500` + `01:19:45.000` = `01:21:58.500`. `format_ms` von 10 h und von 100 h stimmt. Ein Roundtrip parse/format ist verlustfrei.

### Chunk 2 — Mehrteilige Extraktion und Hash
- Dateien: `src/transcript/audio.py`, `src/transcript/session.py`, `src/transcript/__main__.py`, `tests/test_audio.py`, `tests/test_session.py`, `tests/test_smoke.py`, `README.md`
- Änderung: `find_recordings` gibt alle Aufnahmen sortiert zurück (mindestens eine). `extract` nimmt die Infos aller Teile, schreibt `segment-NN.wav`, berechnet SHA-256 und schreibt `audio.json` v2. `SessionPaths.segment_wav(n)` ersetzt `audio_wav`. Die CLI gibt die Teile in Reihenfolge mit Dauer aus. Im README werden der `extract`-Abschnitt und das Layout angepasst und das Einsortieren nach `input/<gruppe>/<ordinal>/` mit der Reihenfolgeregel beschrieben.
- Verify: `scripts/check`
- AC: Zwei synthetische Dateien ergeben zwei WAVs, `audio.json` listet beide in Namensreihenfolge mit korrektem Hash (`hashlib` über die Testdatei). Ein Lauf mit erst zwei, dann einer Datei hinterlässt nur `segment-01.wav`. Ein gepatchter ffmpeg-Fehler im zweiten Teil lässt den vorherigen Stand unverändert.

### Chunk 3 — Manifest-Modell, Aufbau und Lesen
- Dateien: `src/transcript/manifest.py`, `src/transcript/session.py`, `tests/test_manifest.py`
- Änderung: Dataclasses `Manifest` und `Segment` (`index`, `file`, `source{file, size_bytes, sha256, container, stream}`, `frames`, `start_ms`, `end_ms`, `duration_ms`, `overlap_before_ms`). `build_manifest(paths, consent)` liest `audio.json` v2, die Rohdatei und die WAV-Header und schreibt atomar. `load_manifest(paths)` prüft Version, Schlüssel, Lückenlosigkeit und `play_session_id` gegen die Rohdatei. `Segment.to_absolute_ms(local_seconds)` lehnt Werte < 0 oder > Segmentdauer ab. `SessionPaths.manifest` und `narrata_context` kommen dazu.
- Verify: `scripts/check`
- AC: Die Segmente sind chronologisch und lückenlos, `end_ms(1) == start_ms(2)`, Überlappung 0 ist erkennbar. Eine Abweichung der WAV-Frames von `audio.json` → Fehler. Ein abweichendes Ordinal oder eine andere `play_session_id` → Fehler. Mit zwei Teilen über 5 h (Frames simuliert, ohne echtes Audio) bleiben alle Zeiten ≥ 0. `load_manifest` braucht kein ffprobe.

### Chunk 4 — CLI `transcript manifest`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`, `README.md`
- Änderung: Subcommand mit `--consent` und `--config`. Ohne Vermerk erscheint eine Warnung. Fehlen `audio.json` oder die Rohdatei, folgt Exit 2 mit Hinweis auf `transcript extract` bzw. den Ablageort der Rohdatei. Die Ausgabe nennt Segmente mit `HH:MM:SS.mmm`-Bereichen. README: Abschnitt zu Manifest, Rohdatei und Zeitachse, das Layout bekommt `narrata/`.
- Verify: `scripts/check`, danach von Hand an einer eingeordneten zweiteiligen Sitzung: `transcript extract`, Rohdatei per curl ablegen, `transcript manifest --consent`.
- AC: Alle ACs von TOOL-12 sind belegt. Die Bereiche der Ausgabe schließen lückenlos aneinander an.

## Folge-Tickets
- TOOL-67: Die Rohdatei liegt unter `work/<session>/narrata/transcription-context.json`, TOOL-12 liest daraus den Block `session`. Kommentar ans Ticket beim Abschluss.
- TOOL-64, TOOL-76: Die Eingabe ist nicht mehr `audio/audio.wav`, sondern die Segmente aus `manifest.json` (`audio/segment-NN.wav`). Absolute Zeiten kommen über `Segment.to_absolute_ms`. Kommentar an beide Tickets beim Abschluss.
- TOOL-19: Für das Format `timecode.format_ms` und `manifest.Segment` nutzen. Kommentar ans Ticket beim Abschluss.
- Roadmap: Aufwand TOOL-12 von 0,5 auf 1 Tag (Mehrteiligkeit), beim Abschluss in `docs/transcript-roadmap.py`. [kein Ticket: Teil von /close-ticket]
- [kein Ticket: Die Zustimmung wird bewusst nicht erzwungen (Entscheidung der Nutzerin), ASR prüft den Vermerk nicht]
- [kein Ticket: Reihenfolge der Teile über Dateinamen; eine explizite Reihenfolge nur, falls Umbenennen nicht reicht]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Zeitstempel-Helfer | no |
| 2 | Mehrteilige Extraktion, Hash, `audio.json` v2 | no |
| 3 | Manifest-Modell, Aufbau, Lesen | no |
| 4 | CLI `transcript manifest`, README | no |
