# TOOL-91 — Hörproben bei der Sprecherzuordnung entrauscht abspielen

## Ziel
`transcript speakers --assign` spielt die Hörproben über einen Rauschfilter von ffmpeg ab (`highpass` gegen Trittschall und Brummen, `afftdn` gegen breitbandiges Rauschen). Das macht die Zuordnung angenehmer. Heute spielt ffplay die unbearbeitete Segment-WAV, und im Pilot (TOOL-58) waren viele Störgeräusche zu hören. Der Filter wirkt nur in der Wiedergabe, Erkennung, Arbeitsdateien und Export bleiben unverändert.

## Ist-Stand
- `src/transcript/speaker_player.py:37` `command()` baut den ffplay-Aufruf ohne Filter. `play()` (`:53`) verwirft die Ausgabe von ffplay und wertet nur den Exit-Code aus.
- `src/transcript/__main__.py:1061` `_assign_console()` sucht ffplay einmal pro Lauf. `_speakers` (`:1001`) lädt die Konfiguration, behält aber nur `session_paths`.
- `src/transcript/config.py:17` zählt die erlaubten Top-Level-Schlüssel auf, `Config` steht in `:138`, `format_config` in `:311`. Die Konfiguration fließt in keinen Fingerabdruck, `format_config` wird nur von `transcript config` ausgegeben (`__main__.py:1613`).
- Gemessen mit ffplay 4.4.2: Bei einem unbekannten Filter (`-af bogusfilter`) meldet ffplay „No such filter“, spielt nichts und **endet mit Exit 0**. Am Exit-Code von `play()` lässt sich ein unbrauchbarer Filter also nicht erkennen. `ffmpeg -f lavfi -i anullsrc … -af <kette> -f null -` endet dagegen mit Exit 1, sowohl bei einem unbekannten Filter als auch bei einer unbekannten Option.
- Doku: README „Hörproben“ (`README.md:362`), Konfigurationstabelle (`README.md:722`), `config/example.yaml:111`. Der Pilotbericht `docs/pilot/TOOL-58-erste-session.md` hat den Abschnitt „Sprecherzuordnung“ (Zeile 46).

## Entscheidungen
- **Neuer Schlüssel `playback.filter`**, eine ffmpeg-Filterkette als Text. Standard ist `highpass=f=80,afftdn=nf=-25`, `false` schaltet den Filter ab und ergibt das Rohsignal. Fehlt der Schlüssel oder ist er `null`, gilt wie bei den anderen Schlüsseln der Standard. Eine leere Zeichenkette ist ungültig. Eine eigene Sektion `playback` statt eines Schlüssels unter `review`, weil die Wiedergabe mit den Review-Schwellen nichts zu tun hat. Der Standard ist ein Startwert und wird in Chunk 3 am Gehör festgelegt.
- **Die Kette wird einmal pro Lauf mit ffmpeg geprüft**, bevor das erste Label gezeigt wird. Dafür gibt es `speaker_player.usable_filter(chain) -> str | None`, das ffmpeg auf `anullsrc` mit der Kette laufen lässt (Timeout 10 s, Ausgabe verworfen). Scheitert die Prüfung oder fehlt ffmpeg, spielen die Proben ungefiltert, und der Dialog zeigt einmal `note: playback filter not usable; samples play unfiltered`. Einen Exit-Code von ffplay gibt es dafür nicht (siehe Ist-Stand). ffmpeg ist ohnehin Pflicht-Abhängigkeit und kommt aus demselben Paket wie ffplay. Der Preflight bleibt unverändert, wie es das Ticket verlangt.
- **`command()` bekommt `audio_filter: str | None`** und setzt `-af <kette>` vor die Eingabedatei. Mit `None` bleibt der Aufruf derselbe wie heute.
- **Byte-gleich wird über den Datenfluss belegt.** `playback_filter` wird nur in `_assign_console` gelesen, und ffplay öffnet die WAV nur zum Lesen. Ein Test spielt mit einem ffplay-Stub ab und vergleicht danach die Segment-WAV per Hash. ASR und Export lesen den Schlüssel nicht, das zeigt `grep`.

## Daten-Check
- Hörproben und Segment-WAVs: handled, sie werden nur gelesen; der Filter läuft in ffplay im Speicher, es entsteht keine Datei.
- Meldungen und Logs: handled, der Hinweis auf einen unbrauchbaren Filter nennt keinen Pfad, keinen Namen und keinen Text; die Ausgabe von ffmpeg wird wie die von ffplay verworfen. `speaker_player` loggt weiterhin nichts.
- Fixtures: handled, die Tests nutzen Stubs und eine erzeugte Sinus-WAV, keine Aufnahme.
- Pilotbericht (Chunk 3): handled, er bekommt nur das Hörurteil und die gewählte Kette, keine Namen und keine Zitate (TOOL-66).

## Dependency-Check
- Neue Abhängigkeit: N/A, `afftdn` und `highpass` sind eingebaute Filter von ffmpeg (geprüft mit `ffmpeg -filters`, Version 4.4.2). Es gibt keine Modelldatei und kein neues Paket.
- Lokal, Lizenz, Hardware: N/A, unverändert wie ffmpeg (LGPL/GPL aus dem Distributionspaket), CPU-Last für Proben von 12 s vernachlässigbar.

## Chunks
### Chunk 1 — Schlüssel `playback.filter`
- Dateien: `src/transcript/config.py`, `tests/test_config.py`, `config/example.yaml`, `README.md`
- Änderung: `playback` in `_TOP_LEVEL_KEYS`, `_PLAYBACK_KEYS = {"filter"}`, `DEFAULT_PLAYBACK_FILTER`, Feld `Config.playback_filter: str | None`. Laden: fehlt oder `null` ergibt den Standard, `false` ergibt `None`, sonst ein nicht leerer Text. `format_config` schreibt `false` für `None`. Dazu `example.yaml` mit Kommentar und eine Zeile in der Konfigurationstabelle.
- Tests: Standard, `false`, eigene Kette, `""`/`true`/Zahl ungültig, unbekannter Schlüssel `playback.x`, Round-Trip in `test_config.py:95` mit `playback_filter=None`.
- Verify: `scripts/check`
- AC: Teil von AK 1, abschaltbar per Konfiguration.

### Chunk 2 — Filter in der Wiedergabe
- Dateien: `src/transcript/speaker_player.py`, `src/transcript/__main__.py`, `tests/test_speaker_player.py`, `tests/test_smoke.py` (falls `_assign_console` dort gepatcht wird), `README.md`
- Änderung: `command(..., audio_filter)` mit `-af`. `usable_filter(chain, search_path=None)` über ffmpeg auf `anullsrc`. `_speakers` behält die Config, `_assign_console(playback_filter)` prüft die Kette einmal und reicht das Ergebnis an `play()` weiter; der Hinweis erscheint einmal über `say`. README „Hörproben“ beschreibt Filter, Abschalten und Fallback.
- Tests: `command()` mit Kette enthält `-af <kette>` vor der WAV, mit `None` kein `-af` (AK 1). `usable_filter` gibt mit einem ffmpeg-Stub, der mit Exit 0 endet, die Kette zurück, und `None` bei Exit 1, bei fehlendem ffmpeg und bei `None` als Eingabe. Der Hash der Segment-WAV ist nach `play()` mit Filter gleich (Stub-ffplay, AK 2).
- Verify: `scripts/check`; `grep -rn playback_filter src` zeigt nur `config.py` und `_assign_console`.
- AC: AK 1, AK 2.

### Chunk 3 — Hörprobe an der Pilot-Session
- Dateien: `docs/pilot/TOOL-58-erste-session.md`, ggf. `src/transcript/config.py` und `config/example.yaml` (Standardkette), `README.md`
- Änderung: Die Person spielt mit `transcript speakers <pilot> --assign --all` Proben mit dem Standard und mit `playback.filter: false` ab; bei Bedarf werden `nf`/`nr` von `afftdn` oder die Grenzfrequenz angepasst. Das Urteil (Störgeräusche leiser? Stimmen unterscheidbar?) und die gewählte Kette kommen als kurzer Nachtrag in den Abschnitt „Sprecherzuordnung“ des Pilotberichts. Eine geänderte Standardkette wird in Config, Beispiel und README nachgezogen.
- Verify: `scripts/check`; Hörprobe durch die Person an der Pilot-Session.
- AC: AK 3.

## Folge-Tickets
- Entrauschen vor der Erkennung: TOOL-92 (Spike, bereits angelegt); er kann die in Chunk 3 gewählte Kette als `afftdn`-Variante übernehmen.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Konfigurationsschlüssel `playback.filter`, Tests, Doku | no |
| 2 | `-af` in `command()`, Filterprüfung, Verdrahtung, Tests, README | no |
| 3 | Hörprobe an der Pilot-Session, Nachtrag im Pilotbericht | no |
