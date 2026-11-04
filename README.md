# narrata-transcript

Lokale Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte Transkripte für [Narrata](https://github.com/A1etheia/ios-archiv) überführen soll.

**Aktueller Stand: Audio-Vorbereitung.** Das Paket lässt sich installieren, `transcript config` zeigt die Konfiguration, `transcript doctor` prüft ffmpeg und ffprobe, und `transcript extract` prüft die Aufnahmen einer Session und extrahiert ihre Audiospur, eine Datei pro Aufnahme, und `transcript manifest` schreibt das Session-Manifest mit absoluter Zeitachse. Session-Schlüssel und Verzeichnislayout sind festgelegt. Die Schnittstelle für ASR-Backends steht, mit einem Fake-Backend für Tests; ein echtes Backend, Transkription und Export existieren noch nicht.

## Zielarchitektur

Die Pipeline soll vollständig lokal laufen:

1. Audio vorbereiten (MP4, M4A, MP3, WAV)
2. Lokale Transkription mit Sprechertrennung
3. Domänenwissen aus Narrata einbeziehen
4. Unsichere Stellen bewerten, gezielter manueller Review, Sprecherzuordnung
5. Strukturierter JSON-Export für den Import in Narrata

Der JSON-Contract ist die einzige Kopplung zu Narrata. Sein Schema liegt in `ios-archiv`.

## Voraussetzungen

- Python 3.10 oder neuer
- Unter Ubuntu das Paket `python3-venv`
- `ffmpeg` und `ffprobe` im `PATH`; unter Ubuntu/WSL beide über `sudo apt install ffmpeg`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config/example.yaml config/config.yaml
transcript doctor
```

`transcript doctor` gibt die gefundenen Versionen von `ffmpeg` und `ffprobe` aus. Fehlt eines oder läuft es nicht, endet der Befehl mit Exit-Code 2 und einer Meldung, die das Werkzeug und die Installation nennt.

## Audiospur extrahieren

```bash
transcript extract beispielgruppe/042            # erster Audiostream
transcript extract beispielgruppe/042 --stream 1 # zweiter Audiostream
```

Der Befehl liest alle Aufnahmen in `input/<gruppe>/<ordinal>/` (versteckte Dateien und `:Zone.Identifier` zählen nicht). Eine Sitzung darf aus mehreren Aufnahmen bestehen, etwa wenn das Gerät nach fünf Stunden eine neue Datei beginnt. Jede Aufnahme wird ein Segment. Die Reihenfolge der Segmente ist die Sortierung der Dateinamen; der Befehl gibt sie aus, und wer eine andere will, benennt die Dateien um (`… 1.m4a`, `… 2.m4a`). Geht eine Sitzung über Mitternacht, trägt der zweite Teil oft das Datum des Folgetags; das Datumspräfix sortiert trotzdem richtig, und als Sitzungsdatum gilt allein `session_date` aus Narrata. Welches Format vorliegt, entscheidet ffprobe, nicht die Dateiendung. Angenommen werden MP4, M4A, MP3 und WAV; bei MP4 wird nur die Audiospur gelesen, das Bild nie dekodiert. Hat eine Datei mehrere Audiostreams, gilt ohne `--stream` der erste, und zwar für alle Aufnahmen der Sitzung.

Ergebnis ist pro Aufnahme ein `work/<gruppe>/<ordinal>/audio/segment-NN.wav` im Arbeitsformat aus `audio.*` (Default 16 kHz mono, 16 bit PCM) und daneben `audio.json` (`format_version: 2`). Sie enthält das Arbeitsformat, die Versionen von ffmpeg und ffprobe und je Segment Quelle, Größe, SHA-256, Container, alle Audiostreams, den gewählten Stream, die Quelldauer und die exakte Länge in Frames. Ein erneuter Lauf ersetzt alle Dateien erst, wenn jede Aufnahme extrahiert ist; Segmente eines früheren Laufs, die es nicht mehr gibt, werden entfernt. Bricht er ab, bleibt der alte Stand. Die Originalaufnahmen werden nur gelesen.

Abgelehnt werden mit Exit-Code 2 und einer Meldung, die die Datei nennt: Dateien, die ffprobe nicht lesen kann (beschädigt oder kein Medienformat), andere Container, Dateien ohne Audiostream oder ohne Dauer und Extraktionen, deren Dauer um mehr als 0,5 s von der Angabe der Aufnahme abweicht. Das Log auf stderr enthält Werkzeugversionen, Container, Codec und Dauern, keine Dateinamen.

## Session-Manifest

```bash
transcript manifest beispielgruppe/042 --consent
```

Das Manifest `work/<gruppe>/<ordinal>/manifest.json` (`format_version: 1`) ist die zentrale Metadatenquelle einer Session. Es enthält Gruppe und Ordinal, `play_session_id`, Sitzungsdatum, den Zustimmungsvermerk, das Arbeitsformat und alle Segmente in Reihenfolge. Zu jedem Segment gehören Datei, Frames, absoluter Start und Ende in Millisekunden, Dauer, Überlappung mit dem Vorgänger und die Originalaufnahme mit Name, Größe, SHA-256, Container und Stream. Spätere Schritte lesen nur das Manifest und analysieren das Audio nicht erneut.

**Voraussetzungen.** `transcript extract` ist gelaufen, und die Antwort des Narrata-Endpoints `transcription-context` (IOA-1215) liegt unverändert unter `work/<gruppe>/<ordinal>/narrata/transcription-context.json`. Bis TOOL-67 sie abholt, wird sie von Hand dort abgelegt. Gelesen wird nur der Block `session` (`play_session_id`, `ordinal`, `session_date`). Teilnehmende und Glossar übernimmt das Manifest nicht. Passt das Ordinal nicht zum Schlüssel, bricht der Befehl ab.

**Zeitachse.** Die Session-Zeit ist die Aufnahmezeit aller Segmente hintereinander, keine Uhrzeit, denn Pausen zwischen zwei Aufnahmen kennt niemand. Die Zeiten sind ganze Millisekunden, gerundet aus den kumulierten Frames. Ein Segment endet deshalb exakt dort, wo das nächste beginnt: Lücken und negative Werte gibt es nicht, auch nicht über viele Stunden. Die Überlappung ist ohne eigene Segmentierung 0 und steht trotzdem explizit im Manifest. Die Ausgabe zeigt die Bereiche als `HH:MM:SS.mmm`. Ein Ereignis bei `00:02:13.500` in einem Segment, das bei `01:19:45.000` beginnt, liegt bei `01:21:58.500`.

**Zustimmung.** `--consent` vermerkt, dass alle hörbaren Personen mündlich zugestimmt haben (siehe [`docs/datenschutz.md`](docs/datenschutz.md)), mit Zeitpunkt. Ohne das Flag steht `consent: null` im Manifest, und der Befehl warnt; ein früherer Vermerk derselben Spielsitzung bleibt bei einem Neuaufbau erhalten.

**Identität.** Hat ein vorhandenes Manifest eine andere `play_session_id` als die Narrata-Datei, wurde das Ordinal in Narrata neu vergeben. Der Befehl bricht dann ab, und das Arbeitsverzeichnis muss beiseitegelegt werden. Dieselbe Prüfung läuft beim Lesen des Manifests. Weichen die WAV-Dateien von `audio.json` ab, verlangt der Befehl ein erneutes `transcript extract`.

## ASR-Backends

Die Pipeline spricht lokale Spracherkennung nur über `transcript.asr` an: Backend laden, Fähigkeiten abfragen, ein Segment transkribieren, ein einheitliches Ergebnis und einheitliche Fehler erhalten. Modellbibliotheken bleiben in den Adaptern. Schnittstelle, Fähigkeiten, Fehlerkategorien und die Regeln für Adapter stehen in [`docs/asr-backends.md`](docs/asr-backends.md). Für Tests ohne Modell gibt es `transcript.asr.fake.FakeBackend`.

## Konfiguration

Die Einstellungen stehen in `config/config.yaml`. Die Datei ist lokal und nicht im Repo, ebenso alles andere unter `config/` außer `config/example.yaml`. `transcript config` zeigt die wirksamen Werte, `transcript config --config <pfad>` liest eine andere Datei. Fehlende Pflichtwerte, ungültige Werte und unbekannte Schlüssel enden mit einer Meldung, die Datei und Schlüssel nennt.

| Schlüssel | Pflicht | Default | Bedeutung |
| --- | --- | --- | --- |
| `language` | ja | | Sprache der Aufnahmen als zweistelliger Code, z. B. `de` |
| `paths.root` | ja | | Wurzel für `input/`, `work/`, `output/`; ein relativer Pfad gilt ab dem aktuellen Arbeitsverzeichnis |
| `segmentation.length_seconds` | nein | `null` | bleibt `null`: Das V0.1-Backend braucht keine eigene Segmentierung ([TOOL-62](docs/spikes/TOOL-62-asr-vergleich.md)); nur für ein Backend, das in Blöcken arbeiten muss |
| `segmentation.overlap_seconds` | nein | `null` | wie oben; muss kleiner als die Segmentlänge sein |
| `audio.sample_rate` | nein | `16000` | Abtastrate der extrahierten Audiospur in Hz; die Spur ist immer WAV mit 16 bit PCM |
| `audio.channels` | nein | `1` | Kanäle der extrahierten Audiospur: `1` mono, `2` stereo |
| `debug` | nein | `false` | schreibt Transkripttext nach `work/<gruppe>/<ordinal>/debug.log`, nie auf die Konsole |

Einen eigenen Ausgabepfad gibt es nicht: `output/` liegt immer unter `paths.root`, damit echte Daten im Layout unter [Sessions](#sessions) bleiben. Secrets gehören nicht in diese Datei, sondern in `.env`.

## Smoke-Test

```bash
transcript --help
python -m transcript --help
```

## Prüfen

`scripts/check` führt Lint, Formatprüfung und Tests aus; `scripts/check --fix` wendet vorher die automatischen Korrekturen an.

## Verzeichnisstruktur

```
config/          Beispielkonfiguration, lokale Konfiguration (nicht im Repo)
docs/            Roadmap, Ticket-Pläne, Spike-Berichte
scripts/         Prüfskripte; `scripts/spike/` Wegwerf-Werkzeug des ASR-Spikes
src/transcript/  Python-Paket
tests/           Tests
tests/fixtures/  kleine synthetische oder anonymisierte Beispieldaten
input/           Originalaufnahmen pro Session (lokal, nicht im Repo)
work/            Zwischenstände pro Session (lokal, nicht im Repo)
output/          Ergebnisse pro Session (lokal, nicht im Repo)
```

### Sessions

Eine Session ist eine Narrata-Spielsitzung. Ihr Schlüssel lautet `<gruppe>/<ordinal>`: `<gruppe>` ist der `slug` der Narrata-Gruppe, `<ordinal>` das Ordinal der Spielsitzung, mindestens dreistellig. `42` und `042` bezeichnen dieselbe Session. Alle Pfade entstehen aus diesem geprüften Schlüssel (`src/transcript/session.py`), sodass jede Session eigene Verzeichnisse hat und sich Arbeits- und Ausgabedaten nicht vermischen.

Der Schlüssel ist die lesbare Adresse, die Identität ist die `play_session_id` im Manifest: Narrata kann ein Ordinal neu vergeben, wenn die letzte Sitzung gelöscht wird, und auch der Slug kann sich ändern. Weichen Schlüssel und `play_session_id` voneinander ab, zählt die `play_session_id`.

Beispiel-Session `beispielgruppe/042`:

```
input/beispielgruppe/042/      Originalaufnahme, unveränderlich
work/beispielgruppe/042/
  manifest.json                Gruppe, Ordinal, play_session_id, Sitzungsdatum, Zustimmung, Segmente mit absoluten Zeiten
  narrata/                     transcription-context.json (Rohantwort von Narrata)
  audio/                       segment-NN.wav (Arbeitsformat, eine pro Aufnahme), audio.json (Audio-Metadaten)
  snapshot/                    Wissens-Snapshot
  asr/                         ASR-Zwischenergebnisse
  review/                      Review-Kandidaten, CSV
  speakers/                    Sprecherzuordnung
  debug.log                    nur im Debug-Modus
output/beispielgruppe/042/     JSON-Export, TXT, DOCX
```

Die Verzeichnisse von `input/` werden von Hand befüllt: Vor dem ersten Lauf kommen die Aufnahmen einer Sitzung nach `input/<gruppe>/<ordinal>/`, mit dem Ordinal aus Narrata. Liegt eine Aufnahme auch bearbeitet vor (etwa ohne Stille), gehört nur eine Fassung dorthin, sonst zählt sie doppelt. Die Pipeline liest dort nur und schreibt ausschließlich nach `work/` und `output/`. ASR-Ergebnisse werden nie überschrieben.

## Dateiregeln

Einwilligung, Aufbewahrung und Sichtbarkeit regelt [`docs/datenschutz.md`](docs/datenschutz.md). Rohaudio bleibt bis zum Kampagnenende lokal, der Wissens-Snapshot dauerhaft.

**Nie committen:** Audio und Segmente, Transkripte, Klarnamen, Wissens-Snapshots, Secrets. Die `.gitignore` schließt `input/`, `work/`, `output/` in jeder Tiefe aus, dazu `.env`, gängige Audio- und Videoformate sowie `*.srt`, `*.vtt` und `*.docx`. `tests/test_gitignore.py` prüft diese Regeln. `*.json`, `*.txt` und `*.csv` sind nicht global ausgeschlossen; echte Dateien dieser Art gehören deshalb nur in die drei Verzeichnisse.

**Nie hochladen:** Rohaudio, Segmente, Arbeitsdateien aus `work/` und den Wissens-Snapshot. Nach Narrata geht ausschließlich der strukturierte Transkript-Export aus `output/`.

**Echte Sessions** liegen nur lokal: Die Originalaufnahme kommt von Hand nach `input/<gruppe>/<ordinal>/`, alles Weitere erzeugt die Pipeline (siehe [Sessions](#sessions)).

**Secrets** liegen in `.env`, später auch das Narrata-Token. Noch benötigt das Projekt keine Secrets.

**Test-Fixtures** liegen in `tests/fixtures/`. Sie sind klein und synthetisch oder vollständig anonymisiert und enthalten kein Audio; die Regeln stehen in [`tests/fixtures/README.md`](tests/fixtures/README.md).

## Nächste Schritte

Reihenfolge und Meilensteine stehen in [`docs/transcript-roadmap.md`](docs/transcript-roadmap.md); die Tickets laufen im Jira-Projekt `TOOL`.
