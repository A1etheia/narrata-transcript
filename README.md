# narrata-transcript

Lokale Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte Transkripte für [Narrata](https://github.com/A1etheia/ios-archiv) überführen soll.

**Aktueller Stand: Audio-Vorbereitung.** Das Paket lässt sich installieren, `transcript config` zeigt die Konfiguration, `transcript doctor` prüft ffmpeg und ffprobe, und `transcript extract` prüft die Aufnahmen einer Session und extrahiert ihre Audiospur, eine Datei pro Aufnahme, und `transcript manifest` schreibt das Session-Manifest mit absoluter Zeitachse. Session-Schlüssel und Verzeichnislayout sind festgelegt. Die Schnittstelle für ASR-Backends steht, mit einem Fake-Backend für Tests, ebenso das interne Referenztranskript-Format, in dem Ergebnisse gespeichert werden. Das V0.1-Backend (Whisper large-v3-turbo über faster-whisper) transkribiert ein Segment vollständig lokal; ein Befehl, der Segmente einer Session transkribiert, und der Export existieren noch nicht.

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

Das Ergebnis eines Segments wird als Referenztranskript gespeichert: `work/<gruppe>/<ordinal>/asr/segment-NN.json` (`format_version: 1`) in einer Normalform, die kein Backend kennt, daneben `segment-NN.raw.json` mit der unveränderten Backend-Antwort. Zeiten, Confidence und Sprecher-Labels sind optional, Backend und Modell stehen in jeder Datei. Felder und Regeln: [`docs/referenzformat.md`](docs/referenzformat.md).

## Spracherkennung

Das V0.1-Backend ist Whisper large-v3-turbo über faster-whisper (`transcript.asr.whisper.WhisperBackend`, Wahl und Gründe in [TOOL-62](docs/spikes/TOOL-62-asr-vergleich.md)). Es läuft vollständig lokal und lädt das Modell nur aus dem lokalen Cache, nie aus dem Netz.

**Installation.** Die Runtime ist ein optionales Extra; ohne sie laufen alle anderen Befehle und `scripts/check` weiter.

```bash
pip install -e '.[dev,whisper]'
# einmalig, mit Netz: Modell (gut 1,5 GB) in den Hugging-Face-Cache laden
python -c "from faster_whisper import download_model; download_model('large-v3-turbo')"
```

Für die GPU bringt das Extra cuBLAS und cuDNN als pip-Pakete mit. faster-whisper findet sie nur über `LD_LIBRARY_PATH`, etwa in `.venv/bin/activate` oder vor jedem Lauf:

```bash
SP=$(python -c "import site; print(site.getsitepackages()[0])")
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib
```

Erprobt sind faster-whisper 1.2.1, ctranslate2 4.8, cuBLAS 12.9 und cuDNN 8.9.

**Hardware.** Getestet auf einer NVIDIA-GPU mit 12 GB VRAM (RTX 3080 Ti, unter WSL). Ohne GPU läuft dasselbe auf der CPU (`int8`), aber um ein Vielfaches langsamer. Eine Aufnahme von 5 h braucht bis 10,5 GB RAM. Die [Diarisierung](#diarisierung) braucht auf 5 h bis 13,8 GB und darf nicht gleichzeitig laufen; das Whisper-Modell wird vorher freigegeben. Unter WSL reicht das Standardlimit von 15 GB dafür kaum, in `%UserProfile%\.wslconfig` etwa `memory=26GB` wie auf dem Testrechner setzen.

**Lizenzen.** faster-whisper und CTranslate2 stehen unter MIT. Das Modell `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (auf Hugging Face inzwischen unter `dropbox-dash/faster-whisper-large-v3-turbo`) ist laut Modellkarte eine FP16-Konvertierung von `openai/whisper-large-v3-turbo` und steht wie dieses unter MIT. cuBLAS und cuDNN unterliegen den NVIDIA-Lizenzen für Laufzeitbibliotheken; sie werden nur lokal installiert, nicht weitergegeben.

**Fehler.** Fehlt die Runtime, das Modell im Cache, eine GPU bei `asr.device: cuda` oder eine CUDA-Bibliothek, meldet das Backend `BackendUnavailableError` mit dem nächsten Schritt; Speichermangel kommt als `ResourceError`. Die Meldungen nennen Modell, Gerät und Audiodatei, nie Transkripttext oder Begriffe.

**Lauf.** `transcript transcribe` transkribiert alle Segmente einer Session aus dem Manifest. Whisper lädt dafür einmal, danach diarisiert der Befehl die Session (siehe [Diarisierung](#diarisierung)). Vorher müssen `transcript extract` und `transcript manifest` gelaufen sein.

```bash
transcript transcribe beispielgruppe/042                    # alle Segmente, danach Diarisierung
transcript transcribe beispielgruppe/042 --num-speakers 4   # Personenzahl für die Diarisierung
transcript transcribe beispielgruppe/042 --segment 2        # nur Segment 2 laut Manifest
transcript transcribe beispielgruppe/042 --no-diarize       # nur Spracherkennung
transcript transcribe beispielgruppe/042 --force            # auch passende Ergebnisse neu rechnen
```

Es entstehen `work/<gruppe>/<ordinal>/asr/segment-NN.json` und `segment-NN.raw.json` (siehe [ASR-Backends](#asr-backends)). Die Sprache kommt aus `language` der Konfiguration. Begriffshinweise (Hotwords) übergibt der Befehl noch nicht; sie kommen mit der Wissensschnittstelle (TOOL-43). Die Konsole zeigt pro Segment, sobald es fertig ist, den Status mit Laufzeit, Zahl der Passagen und Wörter und der erkannten Sprache, am Ende eine Zusammenfassung mit Modell und Revision. Text erscheint nie.

- **Wiederaufnahme:** Ein fertiges Segment bleibt stehen, wenn Backend, Modell, Revision und Einstellungen gleich sind und die erkannte Sprache zu `language` passt (`reused`). Ein abgebrochener Lauf macht beim nächsten Aufruf mit den offenen Segmenten weiter. Sind alle Segmente fertig, lädt Whisper gar nicht. Hat sich das Modell geändert, werden die betroffenen Segmente neu transkribiert.
- **Vor dem Laden geprüft:** Fehlende Runtime, ein Modell, das nicht im Cache liegt, eine fehlende GPU, ein Segment, das nicht im Manifest steht, ein fehlendes WAV oder ein unlesbares Ergebnis brechen ab, bevor das Modell lädt. Ohne `--no-diarize` gilt das auch für pyannote.
- **`--force`:** Rechnet auch passende Ergebnisse neu. Die Sprecher-Labels fallen dabei weg; die Diarisierung im selben Lauf setzt sie aus der gespeicherten Rohform ohne Modell wieder.
- **Vorübergehender Fehler** (`ResourceError` bei Speichermangel, `BackendRuntimeError`): Das Segment wird mit dem schon geladenen Modell nach 5 s erneut versucht, höchstens `asr.retries`-mal (Default 2, höchstens 5). Gelingt ein Versuch, zählt das Segment als `transcribed`.
- **Dauerhafter Fehler** (`AudioInputError`, `BackendUnavailableError`, `UnsupportedCapabilityError`): wird nicht wiederholt, ein zweiter Versuch käme zum selben Ergebnis.
- **Protokoll:** Jeder fehlgeschlagene Versuch steht als `WARNING` auf stderr, mit Session, Segment, Backend, Versuch, Fehlerklasse und Meldung, etwa `beispielgruppe/042 segment 2: faster-whisper: attempt 1/3 failed: ResourceError: …; retrying in 5 s`. Die Meldungen nennen Backend, Aktion und Datei, nie Transkripttext; die Originalmeldung der Runtime erscheint nie.
- **Fehlschlag bei einem Segment:** Sind die Versuche aufgebraucht oder ist der Fehler dauerhaft, steht das Segment als `status: failed` mit Fehlerklasse in der Datei. Die Konsole zeigt `failed after N attempt(s): <Klasse> (retryable|not retryable): <Meldung>`, und der Lauf geht mit dem nächsten Segment weiter. Der nächste Aufruf versucht es ohne `--force` erneut. Ein erfolgreiches Ergebnis ersetzt ein Fehlschlag nie.
- **Fehlschlag beim Laden** (Modell, Runtime, GPU): schreibt nichts, alle offenen Segmente bleiben `open`.
- **Exit-Code:** 0, wenn alle Segmente `transcribed` oder `reused` und diarisiert sind; 1, wenn eines `failed` oder `open` ist, auch in der Diarisierung; 2, wenn der Lauf gar nicht starten konnte.
- **Seit TOOL-17:** `--segment` ist optional. Ein zweiter Aufruf für ein fertiges Segment verwendet es wieder, statt mit „already transcribed“ abzubrechen.

**Smoke-Test** mit dem echten Modell. ffmpeg spricht dafür mit `flite` einen erfundenen englischen Satz, der Test transkribiert ihn und speichert das Ergebnis im Referenzformat:

```bash
TRANSCRIPT_WHISPER_SMOKE=1 python -m unittest discover -s tests -p test_whisper_smoke.py -v
TRANSCRIPT_WHISPER_SMOKE=1 TRANSCRIPT_WHISPER_DEVICE=cpu python -m unittest discover -s tests -p test_whisper_smoke.py
```

## Diarisierung

Wer wann spricht, bestimmt pyannote `speaker-diarization-community-1` (`transcript.diarization.pyannote.PyannoteDiarizer`, Wahl und Messwerte in [TOOL-20](docs/spikes/TOOL-20-diarisierung.md)). Die Diarisierung läuft nach der Transkription, automatisch am Ende von `transcript transcribe` oder als eigener Befehl, vollständig lokal und nur aus dem lokalen Modell-Cache.

**Installation.** Ebenfalls ein optionales Extra; es bringt torch mit und macht die venv um einige GB größer. Es verträgt sich mit dem Whisper-Extra in derselben venv: torch nutzt CUDA 13 und cuDNN 9, faster-whisper CUDA 12 und cuDNN 8, in getrennten Paketen.

```bash
pip install -e '.[dev,whisper,diarization]'
```

**Einmaliger Download.** Das Modell ist auf Hugging Face *gated*: Einmal auf der [Modellseite](https://huggingface.co/pyannote/speaker-diarization-community-1) mit einem Hugging-Face-Konto die Bedingungen annehmen, dann mit Netz:

```bash
hf auth login          # Token mit Leserechten; liegt danach im HF-Cache, nie im Repo oder in .env
hf download pyannote/speaker-diarization-community-1
```

Danach braucht die Pipeline weder Token noch Netz.

**Offline und ohne Telemetrie.** pyannote.audio 4 schickt per Default Laufmetadaten (Audiodauer, Sprecherzahl, Version, eine Session-ID) an `otel.pyannote.ai`. Das Paket `transcript` setzt deshalb beim Import `PYANNOTE_METRICS_ENABLED=false` und `HF_HUB_OFFLINE=1`, auch wenn die Umgebung etwas anderes vorgibt (`src/transcript/__init__.py`). Ein Lauf lädt also nichts nach und meldet nichts nach außen.

**Lauf.** Voraussetzung sind Manifest und Referenztranskripte unter `work/<gruppe>/<ordinal>/asr/`, erzeugt mit [`transcript transcribe`](#spracherkennung).

```bash
transcript diarize beispielgruppe/042                  # die Zahl der Personen findet das Modell selbst
transcript diarize beispielgruppe/042 --num-speakers 4 # Vorgabe, falls bekannt
transcript diarize beispielgruppe/042 --force          # neu rechnen statt wiederverwenden
```

Pro Segment entsteht `work/<gruppe>/<ordinal>/diarization/segment-NN.json` mit den Turns des Modells. Danach trägt jedes Wort im Referenztranskript das Label des Turns, in dem seine Mitte liegt, jede Passage das Mehrheitslabel; Wörter ohne Turn bleiben ohne Label. Text, Zeiten und Confidence bleiben unverändert. Ein zweiter Lauf verwendet die gespeicherten Turns wieder, solange WAV, Modell-Revision, Einstellungen und `--num-speakers` gleich sind, und lädt dann kein Modell. Die Konsole zeigt nur Zähler und Laufzeiten, nie Labels oder Text.

**Labels gelten pro Segment.** `SPEAKER_00` der ersten Aufnahme ist nicht automatisch dieselbe Person wie `SPEAKER_00` der zweiten. Die Zuordnung zu Personen kommt mit TOOL-68.

**Hardware.** Auf 5 h unter 4 GB VRAM, bis 13,8 GB RAM und etwa 4 Minuten auf der GPU des Testrechners. Nicht gleichzeitig mit Whisper laufen lassen; `transcript transcribe` gibt Whisper vorher frei. Ohne GPU läuft es auf der CPU, deutlich langsamer.

**Lizenzen.** pyannote.audio steht unter MIT. Das Modell [`pyannote/speaker-diarization-community-1`](https://huggingface.co/pyannote/speaker-diarization-community-1) von pyannoteAI steht unter [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); es wird nur lokal genutzt, nicht weitergegeben.

**Fehler.** Fehlt die Runtime, das Modell im Cache oder eine GPU bei `diarization.device: cuda`, meldet der Befehl `BackendUnavailableError` mit dem nächsten Schritt und endet mit Exit-Code 2; Speichermangel kommt als `ResourceError`. Ein Fehler an einem Segment wird wie bei der [Spracherkennung](#spracherkennung) wiederholt (`diarization.retries`) und protokolliert. Schlägt es endgültig fehl, zeigt die Konsole `failed`, gespeicherte Turns und Labels des Segments bleiben unverändert, die übrigen Segmente laufen weiter, und der Befehl endet mit Exit-Code 1. Der nächste Aufruf versucht das Segment erneut. Die Meldungen nennen Modell, Gerät und Segmentdatei, nie Labels oder Text.

**Smoke-Test** mit beiden echten Modellen: ffmpeg spricht mit zwei `flite`-Stimmen zwei erfundene Sätze, Whisper transkribiert, pyannote vergibt die Labels, ein zweiter Lauf verwendet sie wieder. `LD_LIBRARY_PATH` wie unter [Spracherkennung](#spracherkennung).

```bash
TRANSCRIPT_DIARIZATION_SMOKE=1 python -m unittest discover -s tests -p test_diarization_smoke.py -v
```

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
| `asr.model` | nein | `large-v3-turbo` | Modellname von faster-whisper oder ein lokales Modellverzeichnis mit `model.bin` und `tokenizer.json` |
| `asr.device` | nein | `auto` | `auto` nimmt die GPU, wenn eine erreichbar ist, sonst die CPU; `cpu` oder `cuda` erzwingen das Gerät |
| `asr.compute_type` | nein | `null` | `null`: `float16` auf der GPU, `int8` auf der CPU; sonst ein CTranslate2-Typ wie `int8_float16` |
| `asr.beam_size` | nein | `5` | Strahlbreite der Suche; VAD, Wortzeiten und `condition_on_previous_text: false` sind fest |
| `asr.retries` | nein | `2` | weitere Versuche pro Segment nach `ResourceError` oder `BackendRuntimeError`, `0` bis `5`; `0` schaltet die Wiederholung ab |
| `diarization.model` | nein | `pyannote/speaker-diarization-community-1` | Modellname auf Hugging Face oder ein lokales Verzeichnis mit `config.yaml`; nur aus dem lokalen Cache |
| `diarization.device` | nein | `auto` | wie `asr.device` |
| `diarization.retries` | nein | `2` | wie `asr.retries` |
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
scripts/         Prüfskripte
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
  asr/                         segment-NN.json (Referenztranskript), segment-NN.raw.json (Backend-Rohantwort)
  diarization/                 segment-NN.json (Sprecher-Turns von pyannote)
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
