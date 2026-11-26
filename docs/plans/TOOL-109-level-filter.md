# TOOL-109 — Pegelausgleich mit zweistufigem `loudnorm` als Schalter

## Ziel

Die Erkennung kann auf einer pegelnormalisierten Fassung des Segments laufen (`loudnorm=I=-16:TP=-1.5:LRA=11`, zweistufig), geschaltet über die Konfiguration. Heute gibt es den Filter nur im Spike-Werkzeug, mit Hardlinks in Schattenwurzeln. Nach dem Ticket ist an A bis K über die echte Pipeline gemessen, ob `loudnorm` Hauptlauf wird, und der Default steht fest. Das Roh-WAV und ein vorhandenes ASR-Ergebnis werden nie überschrieben.

Geänderter Zuschnitt gegenüber dem Ticket (Entscheidung der Projektverantwortlichen vom 26.11.2026): Schalter statt fest an, Messung an A bis K statt A bis E, Neukalibrierung der Bewertung nur, wenn der Default `loudnorm` wird.

## Ist-Stand

- **Erkennung und Diarisierung lesen dasselbe WAV:** `paths.segment_wav()` in `src/transcript/transcription.py:204` und `src/transcript/diarization/__init__.py:270`. Die Hörproben lesen es ebenfalls (`src/transcript/speaker_assign.py:251`).
- **Extraktion** schreibt in ein temporäres Verzeichnis und ersetzt erst am Ende (`src/transcript/audio.py:186-197`); `segment_wavs()` sammelt `audio/segment-*.wav` und `extract` löscht daraus alles Fremde (`src/transcript/audio.py:199-202`, `src/transcript/session.py:110-112`). Eine gefilterte Datei mit diesem Namensmuster im selben Ordner würde gelöscht.
- **Resume der Erkennung** vergleicht `BackendIdentity.settings` auf Gleichheit mit `asr.settings` des gespeicherten Ergebnisses (`src/transcript/asr/backend.py:150-160`, `src/transcript/transcription.py:276-290`). Die Identität steht vor dem Laden fest und gilt für alle Segmente. Dieselbe Prüfung nutzt der Preflight (`src/transcript/preflight.py:435`); `process` macht daraus einen Fehler statt einer Warnung (`:454-456`).
- **Einstellungen** baut das Backend selbst (`src/transcript/asr/whisper.py:216-227`), das Ergebnis trägt sie über `result.settings` ins Referenzformat (`src/transcript/reference.py:344-352`).
- **Audio-Werkzeuge:** `check_audio_tools` liefert Pfad und Version von ffmpeg (`src/transcript/audio_tools.py:35-46`), der Preflight meldet sie (`src/transcript/preflight.py:125-138`). Ob ein Filter vorhanden ist, prüft niemand. `audio._run` kapselt ffmpeg-Aufrufe und kürzt Pfade in Fehlermeldungen (`src/transcript/audio.py:342-360`).
- **Vorlage im Spike:** `_two_pass` misst mit `print_format=json` und setzt `measured_*`, `offset` und `linear=true` (`scripts/spike/asr.py:489-518`); `denoise._filter` hält die Frame-Zahl mit `apad`/`atrim` und verschiebt erst nach der Prüfung (`scripts/spike/denoise.py:206-235`); `filter_check` misst Versatz und Verstärkung (`scripts/spike/asr.py:537-571`).
- **Messwerkzeug:** `asr.py` legt je Variante und Seed eine Schattenwurzel mit eigener `config.yaml` an und ruft dort das echte CLI auf (`scripts/spike/asr.py:402-433`, `:580-620`). `Variant.config` setzt `asr.*`-Schlüssel der Wurzel (`:109-110`, `:417`). `score` gibt WER, Auslassungen, Stufen, übersehene Fehler in `confident`-Passagen und WDER aus (`:835-891`).
- **Contract:** `pipeline.config_hash` wird aus den ASR-Läufen samt `settings` gebildet (`src/transcript/export.py:340-353`, `src/transcript/report.py:353`); das Schema lässt in `pipeline` keine weiteren Felder zu (`src/transcript/contracts/transcript-v1.schema.json:95-99`).
- **Tests** erzeugen Audio zur Laufzeit mit ffmpeg (`tests/media.py`), ein ffmpeg-Stub für Fehlerfälle steht in `tests/test_audio.py:289-293`.
- **Messstand an A bis K** (WER, Mittel über drei Seeds, aus TOOL-103, TOOL-104, TOOL-108): `base` 21,3 / 29,8 / 30,8 / 61,2 / 34,0 / 28,4 / 36,0 / 36,5 / 27,2 / 74,8 / 35,5; `loud` 20,2 / 26,5 / 23,9 / 36,7 / 29,6 / 27,5 / 42,3 / 32,8 / 30,3 / 35,9 / 26,5. `loud` ist an G und I schlechter als `base`, sonst besser. Sprecherfehler mit Diarisierung auf dem gefilterten WAV: an E 8,7 % statt 5,3 %; Diarisierung auf dem Roh-WAV ist nicht gemessen.

## Entscheidungen

- **Schalter `asr.level_filter`** mit `none` (Default) und `loudnorm`. Unter `asr`, weil er nur den Eingang der Erkennung ändert und `Variant.config` im Messwerkzeug `asr.*`-Schlüssel setzt. Die Zielwerte sind Konstanten, nicht konfigurierbar: gemessen ist nur diese eine Kette.
- **Neues Modul `src/transcript/level.py`**, kein Ausbau von `audio.py`: Messdurchgang, Filterdurchgang, Wiederverwendung, Protokoll. Es nutzt `audio._run`, `audio.wav_frames` und `audio.sha256_file`.
- **Ablage `audio/level/segment-NN.wav` und `segment-NN.json`.** Ein eigener Ordner, damit `segment_wavs()` und das Aufräumen von `extract` die Datei nicht treffen. `extract` löscht den Ordner, wenn es neue Roh-WAVs schreibt.
- **Der Filter läuft in `transcribe`, nicht in `extract`,** und nur für Segmente, die neu transkribiert werden, vor dem Laden des Modells. So wirkt der Schalter ohne neue Extraktion, und ein wiederverwendetes Transkript kostet keine 5 min ffmpeg.
- **Wiederverwendung:** Das gefilterte WAV gilt, wenn das Protokoll daneben dieselbe Kette, dieselbe ffmpeg-Version, die SHA-256 des Roh-WAV und die Frame-Zahl des Manifests nennt und das WAV diese Frame-Zahl hat. Das Protokoll wird zuletzt geschrieben; ein WAV ohne passendes Protokoll wird neu erzeugt.
- **`asr.settings` bekommt `level_filter` mit Kette und ffmpeg-Version, die Messwerte stehen im Protokoll.** Abweichung vom Ticket („Messwerte in `asr.settings`“): Die Messwerte gelten je Segment, die Identität für Resume muss aber vor dem ersten Segment feststehen, und Preflight und Status vergleichen, ohne ffmpeg zu starten. Die Messwerte sind durch Roh-WAV, Kette und Version bestimmt. Bei `none` fehlt der Schlüssel, gespeicherte Transkripte bleiben dann gültig.
- **Die Identität setzt `transcription.py` zusammen,** nicht das Backend: Backend-Identität plus `level_filter`. Derselbe Helfer dient dem Preflight; `_run` trägt denselben Eintrag in das gespeicherte Ergebnis. So gilt es für jedes Backend, auch `FakeBackend`.
- **Die Diarisierung liest weiter das Roh-WAV,** ebenso die Hörproben. Das ist der Rückfall, den das Ticket vorsieht, und der Fall, der im Spike nicht gemessen ist; Chunk 3 misst ihn. Eine Option für das gefilterte WAV entsteht nur, wenn die Messung sie verlangt.
- **Kein stiller Rückfall auf das Roh-WAV.** Scheitert der Filter oder liefert der Messdurchgang keine endlichen Werte (stilles oder zu kurzes Segment), endet `transcribe` vor dem Laden mit einem Fehler. Sonst stünden zwei Eingänge unter denselben Einstellungen.
- **Zeitachse:** Ausgabe mit `apad`/`atrim` auf die Frame-Zahl des Manifests, danach Prüfung der Frame-Zahl. Den Versatz der Hüllkurve prüft die Pipeline nicht (bräuchte numpy); Chunk 3 misst ihn einmal mit `filter_check` am WAV der Pipeline.
- **Messvariante `norm`** in `scripts/spike/asr.py`: Roh-WAV verlinkt, `asr.level_filter: loudnorm` in der Wurzel. Sie misst die Pipeline, `loud` bleibt als Vergleich. Erwartet sind dieselben Zahlen wie bei `loud`; eine Abweichung wird benannt.
- **Entscheidung über den Default** trifft die Projektverantwortliche nach Chunk 3, mit `base`, `norm`, `base+batched` und `loud+batched` an A bis K nebeneinander. Vorab festgelegt ist nur die Darstellung: je Referenz Mittel und Spanne, schlechtestes Fenster, Zahl der Referenzen über und unter `base`.
- **Neukalibrierung nur bei Default `loudnorm`** (Chunk 5). Maßstab aus dem Ticket: Fehler in `confident`-Passagen nicht über dem heutigen Stand von `base`.

## Daten-Check

- Gefiltertes WAV und Protokoll: *handled* — liegen unter `work/<s>/audio/level/`, also außerhalb des Repos; `.gitignore` deckt `work/` ab (`tests/test_gitignore.py`).
- Logs und Konsole: *handled* — nur Segmentnummer, Lautheit, Umfang, Spitze, Filterzeit und „wiederverwendet“; kein Text, keine Namen.
- Fehlermeldungen: *handled* — ffmpeg-Fehler laufen über `audio._last_line`, das den vollen Pfad auf den Dateinamen kürzt.
- Fixtures: *handled* — Tests erzeugen Töne mit ffmpeg zur Laufzeit (`tests/media.py`), kein Audio im Repo.
- Messung und Dokument: *handled* — Läufe bleiben unter `work/` im Hauptcheckout; das Dokument enthält nur Kennzahlen, Sitzungen heißen „Pilotsitzung“ und „zweite Sitzung“; vor dem Commit `grep` auf Sitzungsschlüssel, Gruppenname und Personennamen.

## Contract-Check

- Schema IOA-1214: *N/A*, weil kein Feld dazukommt und keines sich ändert.
- Unterscheidbarkeit: *handled* — `pipeline.config_hash` wird aus `asr.settings` gebildet und ändert sich mit dem Filter; ein Test in Chunk 2 hält das fest.
- Änderung in Narrata: *N/A*, weil Narrata keine Pipeline-Einstellungen anzeigt und der Hash genügt, um Läufe zu trennen. Die Frage aus dem Ticket ist damit ohne Schemaänderung beantwortet; siehe Folge-Tickets.

## Resume-Check

- Abbruch im Filter: *handled* — ffmpeg schreibt in ein temporäres Verzeichnis unter `audio/level/`, das WAV wird mit `os.replace` eingesetzt, das Protokoll danach. Ein Abbruch hinterlässt kein halbes WAV; ein WAV ohne Protokoll wird nicht wiederverwendet.
- Fertige Arbeit: *handled* — ein passendes gefiltertes WAV wird ohne ffmpeg wiederverwendet; ein Transkript mit gleicher Kette und Version wird wiederverwendet, ohne dass der Filter läuft.
- Gleiches Modell und gleicher Snapshot: *handled* — die bestehende Prüfung bleibt, `level_filter` ist ein weiterer Teil der Identität. Wechsel des Schalters oder der ffmpeg-Version macht die Transkripte `stale`; `process` verlangt dann `--redo transcribe`.
- Vorhandenes Ergebnis: *handled* — ein transkribiertes Ergebnis wird von einem Fehlschlag nicht ersetzt (`keep_existing`, `src/transcript/transcription.py:215`); ein Test deckt den Fall mit Filter.

## Dependency-Check

- Neues Paket oder Modell: *N/A*, weil nur ffmpeg gebraucht wird, das schon Voraussetzung ist.
- Filter `loudnorm`: *handled* — in ffmpeg enthalten (gemessen mit 4.4.2), läuft lokal auf der CPU, knapp 5 min je 5-Stunden-Segment. Der Preflight prüft bei eingeschaltetem Filter, dass ffmpeg ihn kennt.
- Platz: *handled* — das gefilterte WAV ist so groß wie das Roh-WAV; die Platzprüfung des Preflight rechnet es bei eingeschaltetem Filter ein.

## Format-Check

- Referenzformat 3: *handled* — `asr.settings` ist eine offene Abbildung, der neue Schlüssel braucht keine neue Version. Vorhandene Transkripte bleiben bei `none` gültig und werden bei `loudnorm` neu erzeugt.
- `audio.json` (Version 2): *N/A*, weil es unverändert bleibt; das gefilterte WAV steht nicht darin.
- Protokoll des Filters: *handled* — neues Format mit `format_version: 1`; eine unbekannte Version gilt als „nicht wiederverwendbar“.
- Bewertungsformat 2: *handled* — ändert Chunk 5 die Schwellen, gelten vorhandene Bewertungen über die bestehende Prüfung als veraltet (`rating outdated`, `src/transcript/status.py:198`); die Version bleibt.

## Chunks

### Chunk 1 — Filter-Modul `level.py`

- Dateien: `src/transcript/level.py` (neu), `src/transcript/session.py`, `src/transcript/audio_tools.py`, `src/transcript/audio.py`, `tests/test_level.py` (neu), `tests/test_audio_tools.py`, `tests/test_audio.py`
- Änderung:
  - `SessionPaths.level_wav(index)` und `level_record(index)` unter `audio/level/`.
  - `level.py`: Zielwerte und Kette als Konstanten; `settings(tools)` (Kette, ffmpeg-Version); `measure` (erster Durchgang, JSON aus stderr, nur endliche Werte); `ensure(paths, segment, tools)` liefert das gefilterte WAV, wiederverwendet oder neu erzeugt; Protokoll mit Kette, Version, SHA-256 des Roh-WAV, Frames, Messwerten, `linear_expected`, Filterzeit.
  - `audio_tools.has_filter(ffmpeg, name)` über `ffmpeg -filters`.
  - `audio.extract` entfernt `audio/level/`, wenn es neue WAVs einsetzt.
- Verify: `scripts/check`
- AC: Das gefilterte WAV hat die Frame-Zahl des Roh-WAV; das Roh-WAV ist Byte für Byte unverändert; ein zweiter Aufruf startet kein ffmpeg; geändertes Roh-WAV, andere Version oder fehlendes Protokoll erzeugen neu; ein scheiternder oder abgebrochener Durchgang hinterlässt weder WAV noch Protokoll.

### Chunk 2 — Schalter, Erkennung, Preflight

- Dateien: `src/transcript/config.py`, `config/example.yaml`, `src/transcript/transcription.py`, `src/transcript/__main__.py`, `src/transcript/preflight.py`, `tests/test_config.py`, `tests/test_transcription.py`, `tests/test_preflight.py`, `tests/test_export.py`, `README.md`, `docs/asr-backends.md`, `docs/ablauf.md`
- Änderung:
  - `Config.asr_level_filter`, Wahl aus `none` und `loudnorm`, Default `none`.
  - `transcribe_session` nimmt den Filter entgegen: Identität plus `level_filter`, für jedes offene Segment `level.ensure` vor dem Laden, `TranscriptionRequest.audio` zeigt auf das gefilterte WAV, das gespeicherte Ergebnis trägt den Eintrag.
  - `_transcribe` (auch über `process`) baut den Filter aus Config und Audio-Werkzeugen und meldet je Segment „gefiltert in n s“ oder „wiederverwendet“.
  - Preflight: Identität mit Filter; bei `loudnorm` Fehler, wenn ffmpeg den Filter nicht kennt; Platzbedarf verdoppelt.
  - Doku: Schalter in der Konfigurationstabelle, Ablage und Wiederverwendung, Hinweis „noch nicht Default, Messung in TOOL-109“.
- Verify: `scripts/check`; im Hauptcheckout zeigt `transcript doctor` mit `none` keinen neuen Befund, und `transcript transcribe` an einer vorhandenen Sitzung verwendet mit `none` alle Transkripte wieder.
- AC: Mit `loudnorm` bekommt das Backend das gefilterte WAV und `asr.settings` trägt Kette und Version; mit `none` ist alles wie vorher und kein Schlüssel kommt dazu; ein Transkript ohne Eintrag ist mit `loudnorm` nicht wiederverwendbar; die Diarisierung liest das Roh-WAV; `config_hash` unterscheidet beide Fälle.

### Chunk 3 — Messung an A bis K

- Voraussetzung: Clip-Angaben für C bis K (Datei und Fenster) wie in den Messaufrufen von TOOL-104 und TOOL-108; fehlen J und K, nennt die Projektverantwortliche sie im Chat.
- Dateien: `scripts/spike/asr.py`, `scripts/spike/README.md`, `docs/spikes/TOOL-109-hauptlauf.md` (neu)
- Änderung:
  - Basis `norm` in `asr.py`: `Variant(config={"level_filter": "loudnorm"})`, Roh-WAV verlinkt.
  - Läufe an beiden Sitzungen: `norm`, Seeds 1 bis 3, Seed 1 mit `--diarize`; als Hintergrundbefehle nacheinander, aus dem Worktree mit `.venv` und `config/config.yaml` des Hauptcheckouts.
  - `score` an A bis K für `base`, `loud`, `norm`, `base+batched`, `loud+batched`; `filter_check` am WAV der Pipeline.
  - Dokument: WER mit Ersetzungen, Auslassungen und Einfügungen je Referenz, Abweichung `norm` gegen `loud`, Stufen und übersehene Fehler, WDER mit Diarisierung auf dem Roh-WAV gegen `base` und gegen die Spike-Werte, Filterzeit, Versatz, Verstärkung, `linear_expected`; am Ende die Entscheidungstabelle.
- Verify: `scripts/check`; `score` für `base` gibt weiter 21,3 % (A) und 29,8 % (B); `grep` im Dokument auf Sitzungsschlüssel, Gruppenname und Personennamen ohne Treffer.
- AC: Tabellen an A bis K mit drei Seeds; Abweichung zum Spike benannt; WDER an jeder Referenz gegen `base` ausgewiesen; die Projektverantwortliche hat die Entscheidungstabelle.

### Chunk 4 — Default nach Entscheidung

- Voraussetzung: Entscheidung der Projektverantwortlichen über den Default.
- Dateien: `docs/spikes/TOOL-109-hauptlauf.md`; bei Go zusätzlich `src/transcript/config.py`, `config/example.yaml`, `tests/test_config.py`, `README.md`, `docs/ablauf.md`
- Änderung: Entscheidung mit Datum und Begründung im Dokument. Bei Go Default `loudnorm`, Hinweis in der Doku, dass gespeicherte Transkripte `stale` werden und `process` `--redo transcribe` verlangt. Bei No-Go bleibt `none`, der Schalter bleibt als Option dokumentiert. Kommentar an TOOL-114 mit dem Hauptlauf, Kommentar an TOOL-100.
- Verify: `scripts/check`; `grep` wie in Chunk 3.
- AC: Default und Doku stimmen mit der Entscheidung überein; TOOL-114 weiß, ob `base` Hauptlauf bleibt.

### Chunk 5 — Bewertung auf gefiltertem Audio (nur bei Go)

- Voraussetzung: Default `loudnorm` aus Chunk 4. Bei No-Go entfällt der Chunk, und das Dokument nennt den Grund.
- Dateien: `docs/spikes/TOOL-35-kalibrierung.md`, `docs/spikes/TOOL-109-hauptlauf.md`; bei geänderten Schwellen `src/transcript/config.py`, `config/example.yaml`, `tests/test_config.py`
- Änderung: Fehler in `confident`-Passagen und markierte Zeit von `norm` gegen `base` an A bis K mit den heutigen Schwellen. Liegen die übersehenen Fehler nicht über `base`, bleiben die Schwellen. Sonst die Schwellen aus `review.uncertainty` mit der Methode aus TOOL-35 anheben, bis das Kriterium hält, und die markierte Zeit daneben ausweisen.
- Verify: `scripts/check`; `score` mit den neuen Schwellen zeigt an keiner Referenz mehr übersehene Fehler als `base` heute.
- AC: Abschnitt „Neumessung auf gefiltertem Audio (TOOL-109)“ im Kalibrierungsdokument; Kriterium des Tickets erfüllt oder die Abweichung benannt.

## Folge-Tickets

- Umsetzung von Regel A hängt am Hauptlauf — TOOL-114, Kommentar in Chunk 4.
- Ergebnis für den Reflexionspunkt M9 — TOOL-100, Kommentar in Chunk 4.
- Batched-Lauf als Hauptlauf (samt großzügigerer VAD und `loud+batched` an E, aus TOOL-108) — [kein Ticket: entsteht nur, wenn die Entscheidung nach Chunk 3 auf einen Batched-Lauf fällt].
- Diarisierung auf dem gefilterten WAV als Option — [kein Ticket: nur nötig, wenn Chunk 3 mit dem Roh-WAV einen Nachteil zeigt; dann vor Chunk 4 mit der Projektverantwortlichen klären].
- Filterangaben im Contract (IOA-1214) — [kein Ticket: `config_hash` trennt die Läufe, Narrata zeigt keine Pipeline-Einstellungen].
- `loudnorm` an einer deutlich lauteren oder leiseren Aufnahme (Vorbehalt aus TOOL-103) — TOOL-105, als Kommentar in Chunk 4: die Sitzung mit geänderter Aufnahme ist die erste solche Aufnahme.
- Zeile für TOOL-109 in `docs/transcript-roadmap.py` — [kein Ticket: kommt mit `/close-ticket`].

## Chunk-Tabelle

| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Filter-Modul `level.py`, Pfade, Filterprüfung, Tests | no |
| 2 | Schalter `asr.level_filter`, Erkennung, Preflight, Doku | yes |
| 3 | Variante `norm`, Läufe und Messung an A bis K, Dokument | yes |
| 4 | Default nach Entscheidung, Übergaben | no |
| 5 | Bewertung auf gefiltertem Audio, nur bei Go | no |
