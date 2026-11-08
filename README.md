# narrata-transcript

Lokale Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte Transkripte für [Narrata](https://github.com/A1etheia/ios-archiv) überführen soll.

**Aktueller Stand: Audio-Vorbereitung.** Das Paket lässt sich installieren, `transcript config` zeigt die Konfiguration, `transcript doctor` prüft ffmpeg und ffprobe, und `transcript extract` prüft die Aufnahmen einer Session und extrahiert ihre Audiospur, eine Datei pro Aufnahme, `transcript context` holt den Transkriptionskontext aus Narrata, und `transcript manifest` schreibt das Session-Manifest mit absoluter Zeitachse. Session-Schlüssel und Verzeichnislayout sind festgelegt. Die Schnittstelle für ASR-Backends steht, mit einem Fake-Backend für Tests, ebenso das interne Referenztranskript-Format, in dem Ergebnisse gespeichert werden. Das V0.1-Backend (Whisper large-v3-turbo über faster-whisper) transkribiert ein Segment vollständig lokal; ein Befehl, der Segmente einer Session transkribiert, und der Export existieren noch nicht.

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

## Narrata-Kontext

```bash
transcript context beispielgruppe/042                          # von Narrata holen
transcript context beispielgruppe/042 --from-file kontext.json # gespeicherte Antwort übernehmen
```

Der Befehl holt den Transkriptionskontext einer Sitzung vom Narrata-Endpoint `GET /api/groups/{gruppe}/play-sessions/{ordinal}/transcription-context` (IOA-1215, Contract in `ios-archiv` unter `docs/transcripts.md`, „Transkriptionskontext“). Der Kontext enthält Sitzungsdaten, Teilnehmende mit Spielfiguren und ein nach Relevanz gestuftes Glossar. Die Antwort wird unverändert unter `work/<gruppe>/<ordinal>/narrata/transcription-context.json` gespeichert, daraus lesen alle späteren Schritte. Die Konsole zeigt nur `play_session_id`, Datum, Contract-Version und Zähler, keine Namen.

**Einrichtung.** In `config/config.yaml` stehen `narrata.url` (Basis-URL des Narrata-Hosts) und unter `narrata.groups` die Gruppen-ID je Gruppen-Slug, denn der Endpoint adressiert Gruppen über die ID. Der Token gehört als `NARRATA_TOKEN` in `.env` (Vorlage `cp .env.example .env`) oder in die Umgebung, die Vorrang hat. Er muss einer aktiven Spielleitung der Gruppe gehören. Vorerst ist es der normale Narrata-Login-Token, der nach 24 h abläuft und vor dem Abruf frisch eingetragen werden muss. Ein langlebiger Pipeline-Token kommt mit IOA-1251.

**Datei statt Netz.** `--from-file` übernimmt eine gespeicherte Antwort desselben Formats, ohne `narrata.url` und ohne Token. Beide Wege laufen durch dieselbe Prüfung.

**Prüfung.** Akzeptiert wird jede `contract_version` `1.x`, das Ordinal muss zum Session-Schlüssel passen. Auch die Teilnehmenden werden geprüft: Jeder Eintrag braucht `user_id`, `display_name`, `role` (`gm` oder `player`) und `is_former`, IDs dürfen sich nicht wiederholen. Spielfiguren (`characters`) und ihre Aliase dürfen fehlen, etwa bei einer Spielleitung ohne Figur. Fehlermeldungen nennen nur Position und Feld (`participants[2].role`), nie einen Namen. Was die Prüfung nicht besteht, wird nicht gespeichert, eine vorhandene Datei bleibt dann unverändert. Auch `manifest` und `transcribe` prüfen die Version und brechen vor der Spracherkennung ab. Fehler enden mit Exit-Code 2 und nennen die Ursache: 401 heißt Token fehlt oder ist abgelaufen, 404 heißt Gruppe oder Sitzung unbekannt oder keine aktive Spielleitung. Umleitungen werden nicht verfolgt, damit der Token nicht an ein anderes Ziel geht. Ein erneuter Abruf ersetzt die Datei, ein vorhandener [Wissens-Snapshot](#wissens-snapshot) bleibt dabei unverändert. Weicht der neue Kontext von ihm ab, warnt der Befehl.

**Abrufparameter.** Jeder Abruf sendet `n` (`narrata.recent_sessions`, Default 3) und `archive_limit` (`narrata.archive_limit`, Default 500) ausdrücklich mit, das Ergebnis hängt also nicht an Server-Defaults.

**Teilnehmende.** Spätere Schritte (Wissens-Snapshot TOOL-41, Sprecherzuordnung TOOL-68) lesen die Teilnehmenden über `transcript.narrata.read_participants`: Narrata-User-ID, Anzeigename, Rolle, `is_former` und die Spielfiguren mit Archiv-ID, Name und Aliasen, in der Reihenfolge aus Narrata und mit Datei, Contract-Version und `play_session_id` als Herkunft. Ehemalige Mitglieder sind enthalten. Wer an der Sitzung anwesend war, führt Narrata noch nicht (IOA-1271), die Anwesenheit ist deshalb unbekannt (`present = None`). Die Konsole zeigt nur Zähler: Teilnehmende, davon Spielleitung und ehemalig, und Spielfiguren.

**Glossar.** Eigennamen und Begriffe kommen aus dem Welt-Archiv in Narrata, eine eigene Glossardatei gibt es nicht. `transcript.narrata.read_glossary` liest jeden Eintrag mit Typ (`place`, `person`, `artifact`, `organisation`, `event`, `lore`), Archiv-ID, Name, Aliassen, bekannten ASR-Hörfehlern (`asr_variants`), Kurzbeschreibung und Relevanzstufe (`pc`, `session`, `recent`, `archive`), in der Reihenfolge aus Narrata und mit Datei, Contract-Version und `play_session_id` als Herkunft. Dazu kommen die Archiv-Kappung (`glossary_meta`) und die Hörfehler, die mehrere Einträge teilen (`asr_ambiguities`, ab Contract 1.1). Die Prüfung beim Speichern verlangt Typ, ID, Name und Relevanz, eindeutige Paare aus Typ und ID und Mehrdeutigkeiten, die auf mindestens zwei ausgelieferte Einträge zeigen. Ein unbekannter Typ oder eine unbekannte Stufe bricht mit dem Hinweis ab, narrata-transcript zu aktualisieren. `transcript.glossary.GlossaryIndex` findet Einträge über Name, Alias oder Hörfehler, unabhängig von Groß-/Kleinschreibung, Unicode-Normalform und Leerraum. Teilen sich mehrere Einträge einen Begriff, kommen alle zurück, eine Auswahl trifft erst das Review. `transcript.glossary.keyword_terms` liefert Namen und Aliasse als Kandidaten für ASR-Hinweise, ohne Hörfehler und ohne Dubletten. Welche Einträge ein Lauf als Keywords nutzt, legt der [Wissens-Snapshot](#wissens-snapshot) fest, die Kappung auf das Token-Budget des Backends kommt mit TOOL-44. Die Konsole zeigt Einträge je Stufe, die Archiv-Kappung und die Zahl der Mehrdeutigkeiten, keine Namen.

## Wissens-Snapshot

```bash
transcript snapshot beispielgruppe/042            # bauen oder vorhandenen wiederverwenden
transcript snapshot beispielgruppe/042 --refresh  # bewusst neu bauen
```

Der Snapshot friert das Wissen einer Sitzung für alle weiteren Läufe ein: Teilnehmende mit Spielfiguren, das ganze Glossar, die Mehrdeutigkeiten (`asr_ambiguities`) und die Archiv-Kappung (`glossary_meta`). Er liegt unter `work/<gruppe>/<ordinal>/narrata/snapshot.json`, wird aus dem gespeicherten Narrata-Kontext gebaut und ist danach ohne diese Datei und ohne Narrata lesbar. Spätere Schritte lesen ihn über die [Wissensschnittstelle](#wissensschnittstelle), nie die Rohdatei.

**Relevanzregel.** Die Relevanz berechnet Narrata: Jeder Glossar-Eintrag trägt genau eine Stufe, die erste passende von `pc` (Spielfigur eines aktiven Teilnehmenden), `session` (mit der Sitzung oder ihren Abenteuern verknüpft), `recent` (in Tagebüchern der letzten `n` Sitzungen genannt) und `archive` (der Rest, gekappt). Die Regel steht in `ios-archiv` unter `docs/transcripts.md`, „Relevanz“. Der Snapshot übernimmt die Stufe als Relevanzgrund, die Pipeline rechnet sie nicht nach.

**Keywords.** Keyword-Kandidaten für die Spracherkennung sind alle `pc`-Einträge, dann `session`- und `recent`-Einträge in Narratas Reihenfolge, bis `knowledge.keyword_budget` für ihren Typ erreicht ist. `archive`-Einträge werden nie Keyword, bleiben aber für den späteren Abgleich im Snapshot. Jeder Eintrag ist im Snapshot mit `keyword` markiert.

**Kennung und Aktualisierung.** `snapshot_id` ist ein sha256 über den Inhalt ohne Erstellzeitpunkt: Gleiches Wissen mit gleichem Budget ergibt dieselbe Kennung, jede Änderung eine neue. Ohne `--refresh` wird ein vorhandener Snapshot nur wiederverwendet. Hat sich der gespeicherte Kontext oder das Budget seitdem geändert, warnt der Befehl, ändert aber nichts. `--refresh` baut neu und nennt die vorige Kennung, wenn sich das Wissen geändert hat. Ein beschädigter oder von Hand veränderter Snapshot wird abgelehnt, `--refresh` baut ihn neu.

Die Konsole zeigt die kurze Kennung, Erstellzeitpunkt, Contract-Version und Zähler: Einträge je Stufe, Keywords je Typ gegen das Budget, Mehrdeutigkeiten. Namen erscheinen nie. Der Snapshot enthält Klarnamen und bleibt wie alles unter `work/` außerhalb des Repos.

**Diagnose.** Nach jedem Lauf prüft der Befehl das Wissen und schreibt das Ergebnis nach `work/<gruppe>/<ordinal>/narrata/diagnosis.json` (`format_version: 1`). Die Datei wird bei jedem Lauf ersetzt, auch wenn der Lauf abbricht.

- **Fehler.** Technisch unbrauchbare Daten (doppelte IDs, leere Pflichtfelder, unbekannte Typen, Mehrdeutigkeiten ohne gültiges Ziel, fehlende Herkunft im Snapshot) erkennt schon das Lesen. Der Snapshot wird dann weder gebaut noch genutzt. Der Befehl endet mit Exit-Code 2, und der Bericht enthält einen `error` (`unusable_knowledge`) mit der Meldung samt Datei und Feld.
- **Warnungen.** Mehrdeutige, aber nutzbare Einträge bleiben, wie Narrata sie liefert. Sie werden nur gemeldet, über den Exit-Code entscheiden sie nicht:

| Code | Bedeutung |
| --- | --- |
| `empty_term` | Alias oder Hörfehler ist leer |
| `shared_term` | mehrere Einträge teilen Name oder Alias |
| `ambiguous_asr_variant` | mehrere Einträge teilen einen Hörfehler, Narrata weist ihn in `asr_ambiguities` aus |
| `unreported_asr_variant` | wie oben, aber nicht in `asr_ambiguities` (Narrata vergleicht nur ohne Groß-/Kleinschreibung, hier auch Unicode-Form und Leerraum) |
| `stale_ambiguity` | ein Eintrag in `asr_ambiguities` trägt den Hörfehler gar nicht |
| `variant_shadows_term` | ein Hörfehler ist Name oder Alias eines anderen Eintrags |
| `unknown_character` | die Spielfigur einer aktiven teilnehmenden Person fehlt im Glossar |
| `character_not_pc` | ihr Glossar-Eintrag steht nicht in der Stufe `pc` |
| `orphan_pc` | ein `pc`-Eintrag gehört zu keiner aktiven teilnehmenden Person |

Jeder Befund nennt Feldpfade (`glossary[3].aliases[1]`, `participants[0].characters[0]`), Typ und Narrata-ID der Einträge, im Bericht außerdem Snapshot-Datei und Kontextdatei als Quelle. Namen stehen weder im Bericht noch auf der Konsole. Die Konsole zeigt die Zähler je Code und höchstens zehn Befunde, die übrigen stehen in der Datei.

## Wissensschnittstelle

Pipeline-Schritte fragen das Wissen einer Sitzung über `transcript.domain.DomainContext` ab, nicht bei Narrata, in der Rohdatei oder im Snapshot-Format. `DomainContext.load(paths)` liest den [Wissens-Snapshot](#wissens-snapshot). Nur `from_snapshot` kennt dessen Aufbau, eine andere Wissensquelle braucht deshalb nur eine neue Factory.

| Abfrage | Liefert |
| --- | --- |
| `lookup(begriff)` | jeden Eintrag, den der Begriff als Name, Alias oder Hörfehler nennt; bei geteilten Begriffen alle |
| `entry((typ, id))` | einen Glossar-Eintrag per Archiv-ID |
| `participant(user_id)`, `character(person_id)` | Teilnehmende und Spielfigur samt spielender Person |
| `relevant_entries()`, `keyword_entries()` | Einträge der Stufen `pc`, `session`, `recent` bzw. die Keyword-Einträge des Snapshots |
| `transcription_keywords()` | Namen und Aliasse der Keyword-Einträge als ASR-Hinweise, wichtigste zuerst, ohne Hörfehler |
| `match_candidates()` | jeden Begriff jedes Eintrags samt Hörfehlern, als Grundlage für die [Review-Hinweise](#review-hinweise) |
| `is_ambiguous(begriff)` | ob Narrata den Begriff als Hörfehler mehrerer Einträge führt (`asr_ambiguities`) |

Jeder Treffer (`TermHit`) nennt Eintrag mit Typ, Archiv-ID und Stufe, die Art (`name`, `alias`, `asr_variant`), das Feld (`aliases[1]`), die Schreibweise aus Narrata, ob der Eintrag Keyword ist, und die Herkunft (`Origin`: Snapshot-Kennung, Kontextdatei, Contract-Version, `play_session_id`). Abfragen ändern weder Wissen noch Transkripttext und entscheiden nie zwischen Einträgen, die sich einen Begriff teilen. Ob ein Backend die Hinweise nutzt, entscheidet seine Capability `keyword_biasing`. Backends ohne sie brauchen keine Domänenlogik.

## Session-Manifest

```bash
transcript manifest beispielgruppe/042 --consent
```

Das Manifest `work/<gruppe>/<ordinal>/manifest.json` (`format_version: 1`) ist die zentrale Metadatenquelle einer Session. Es enthält Gruppe und Ordinal, `play_session_id`, Sitzungsdatum, den Zustimmungsvermerk, das Arbeitsformat und alle Segmente in Reihenfolge. Zu jedem Segment gehören Datei, Frames, absoluter Start und Ende in Millisekunden, Dauer, Überlappung mit dem Vorgänger und die Originalaufnahme mit Name, Größe, SHA-256, Container und Stream. Spätere Schritte lesen nur das Manifest und analysieren das Audio nicht erneut.

**Voraussetzungen.** `transcript extract` und `transcript context` sind gelaufen (siehe [Narrata-Kontext](#narrata-kontext)). Aus dem Transkriptionskontext liest das Manifest nur den Block `session` (`play_session_id`, `ordinal`, `session_date`). Teilnehmende und Glossar übernimmt das Manifest nicht. Passt das Ordinal nicht zum Schlüssel, bricht der Befehl ab.

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

Es entstehen `work/<gruppe>/<ordinal>/asr/segment-NN.json` und `segment-NN.raw.json` (siehe [ASR-Backends](#asr-backends)). Die Sprache kommt aus `language` der Konfiguration. Liegt ein [Wissens-Snapshot](#wissens-snapshot) vor, übergibt der Befehl dessen Keywords über die [Wissensschnittstelle](#wissensschnittstelle) als Begriffshinweise (Hotwords) und nennt ihre Zahl und die kurze Snapshot-Kennung, nie die Begriffe. Ohne Snapshot läuft er ohne Hinweise. Nach dem Lauf meldet er, wie viele der angebotenen Keywords das Backend tatsächlich genommen hat (`63 of 120 keyword(s) passed`). Was angekommen ist, steht als `asr.keywords_used` im Referenztranskript.

- **Hotwords nur mit Turbo:** Whisper nimmt Hotwords nur bei einem Turbo-Modell, also wenn der Modellname, bei einem lokalen Verzeichnis dessen letzter Teil, `turbo` enthält. Mit `large-v3` zerfällt die Ausgabe unter Hotwords (TOOL-62). Andere Modelle laufen ohne Hinweise, die Capability `keyword_biasing` ist dann `false`, und der Befehl meldet einmal `keywords not passed: model <name> takes no hotwords`.
- **Token-Budget:** faster-whisper nimmt höchstens 223 Tokens. Es gehen die vorderen Keywords, die vollständig hineinpassen, also die nächsten Stufen zuerst (siehe [Wissens-Snapshot](#wissens-snapshot)). Das erste Keyword, das nicht mehr passt, beendet die Liste.

Die Konsole zeigt pro Segment, sobald es fertig ist, den Status mit Laufzeit, Zahl der Passagen und Wörter und der erkannten Sprache, am Ende eine Zusammenfassung mit Modell und Revision. Text erscheint nie.

- **Wiederaufnahme:** Ein fertiges Segment bleibt stehen, wenn Backend, Modell, Revision, Einstellungen und Snapshot-Kennung gleich sind, die erkannte Sprache zu `language` passt und das Backend dieselben Keywords bekommen hat (`reused`). Gekappte Keywords zählen als dieselben, solange die genutzten in derselben Reihenfolge unter den aktuellen stehen. Ein Ergebnis ohne Hinweise wird neu transkribiert, sobald es Keywords gibt. Ein Backend ohne Keyword-Unterstützung ignoriert sie, für die Wiederaufnahme zählen sie dann nicht. Ein abgebrochener Lauf macht beim nächsten Aufruf mit den offenen Segmenten weiter. Sind alle Segmente fertig, lädt Whisper gar nicht. Hat sich das Modell geändert, werden die betroffenen Segmente neu transkribiert.
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

## Review-Hinweise

Nach der Spracherkennung vergleicht `transcript transcribe` den erkannten Text jedes fertigen Segments mit dem [Wissens-Snapshot](#wissens-snapshot) (`transcript.hints`). Wo das Transkript vermutlich einen Glossar-Eintrag meint, entsteht ein Hinweis für die Durchsicht. Der Text bleibt unverändert: Ein Hinweis ist nur ein Verweis, die Entscheidung trifft das Review mit dem Audio.

| Signal | Wann | Stärke |
| --- | --- | --- |
| `known_variant` | Die Wortfolge ist ein in Narrata gepflegter Hörfehler (`asr_variants`) | stark |
| `similar` | Die Wortfolge ähnelt Name oder Alias eines Eintrags: Schreibung (`method: spelling`, Ähnlichkeit ab 0,85, Leerzeichen zählen nicht, „Grau Wasser“ trifft „Grauwasser“) oder Klang (`method: sound`, gleicher Code der Kölner Phonetik mit mindestens 3 Stellen) | schwach |

- **Kein Hinweis** entsteht für einen richtig erkannten Namen oder Alias und für Wörter unter 4 Buchstaben. `similar` braucht einen großen Anfangsbuchstaben, wie Whisper ihn bei Namen setzt, und eine Länge, die höchstens 30 % vom Begriff abweicht. Ähnlichkeit, Mindestlänge und Längenabweichung stehen unter `review.similar` in der Konfiguration (Defaults 0,85, 4 und 0,3), kalibriert wird in TOOL-35.
- **Wortfolgen** bis zur Wortzahl des längsten Begriffs, höchstens 4. Überlappen sich Treffer, gewinnt ein richtig erkannter Begriff, dann das starke Signal, dann die längere Folge.
- **Mehrdeutig** (`ambiguous: true`) ist ein Hinweis, wenn mehrere Einträge passen oder Narrata den Hörfehler in `asr_ambiguities` führt. Dann stehen alle Kandidaten in Glossar-Reihenfolge darin, ausgewählt wird keiner.
- **Hörfehler aus Narrata:** Hörfehler pflegt die Spielleitung in Narrata („Bekannte Hörfehler“), narrata-transcript führt keine eigene Fehlerliste. Ein Hörfehler gilt genau für seinen Eintrag und dessen Relevanzstufe, einen eigenen Kontext pro Hörfehler liefert Contract 1.1 nicht. Mehrere Hörfehler können auf denselben Eintrag zeigen, das Feld (`asr_variants[0]`, `asr_variants[1]`, …) sagt, welcher getroffen hat. Führt Narrata keine Hörfehler, entstehen nur `similar`-Hinweise. Eine Vorschlagsliste neuer Hörfehler aus den Review-Korrekturen folgt mit TOOL-80.
- **Einfluss des Wissens:** Jeder Kandidat nennt Typ, Archiv-ID, Begriff, Art (`name`, `alias`, `asr_variant`), Feld und Stufe, dazu `biased`, also ob der Begriff als Hotword an die Spracherkennung ging. Der Dateikopf nennt Snapshot-Kennung, Zahl der Hotwords und das gelesene Referenztranskript.

Die Datei `work/<gruppe>/<ordinal>/review/segment-NN.hints.json` (`format_version: 1`) entsteht bei jedem Lauf neu, auch für wiederverwendete Segmente. Der Abgleich braucht kein Modell und dauert Sekunden. Ohne Snapshot entsteht keine Datei, und eine vorhandene wird entfernt. Die Konsole zeigt nur Zahlen, etwa `review hints: 3 known variant(s), 11 similar, 2 ambiguous`, nie Text oder Namen. Die Datei selbst enthält erkannten Text und Archivnamen und bleibt deshalb unter `work/`.

**Neues Wissen ohne neue ASR:** `transcript assess <gruppe>/<ordinal> --hints` gleicht die gespeicherten Transkripte mit dem aktuellen Snapshot neu ab und bewertet danach die Passagen. So kommt ein neuer Snapshot, etwa nach `transcript snapshot --refresh`, in die Review, ohne die Aufnahme neu zu transkribieren. Hinweise und Bewertung tragen dann die neue Snapshot-Kennung, das ASR-Ergebnis behält die alte. Ein späteres `transcript transcribe` derselben Session transkribiert deshalb neu (siehe Wiederaufnahme).

## Unsicherheitsbewertung

Jede Passage eines transkribierten Segments bekommt eine Stufe (`transcript.uncertainty`): `confident` (sicher), `needs_review` (prüfenswert) oder `uncertain` (unsicher). Die Namen sind die von `confidence_tier` im Narrata-Contract. Die Bewertung läuft am Ende von `transcript transcribe` (nach der Diarisierung, bei `--no-diarize` nach der ASR) und von `transcript diarize`. Allein, etwa nach geänderten Schwellen, läuft sie mit `transcript assess <gruppe>/<ordinal> [--segment N] [--hints]`. `--hints` erzeugt vorher die Hinweise aus dem aktuellen Snapshot neu. Sie braucht kein Modell und dauert Sekunden.

Die Stufe einer Passage ist die höchste ihrer Gründe. Die Schwellen stehen unter `review.uncertainty` (siehe [Konfiguration](#konfiguration)); die Defaults sind Startwerte, kalibriert wird in TOOL-35.

| Regel | Wann | Stufe |
| --- | --- | --- |
| `low_confidence` | Anteil der Wörter unter `word_low` ab `low_share_review` bzw. `low_share_uncertain` | `needs_review` / `uncertain` |
| `very_low_confidence` | mindestens ein Wort unter `word_very_low` | `needs_review` |
| `no_speech` / `low_logprob` | Whisper-Signal der Passage ab `no_speech_prob` bzw. bis `avg_logprob` | `needs_review` |
| `repetition` | `compression_ratio` ab der Schwelle, das Zeichen einer Whisper-Schleife | `uncertain` |
| `gap` | längste Pause zwischen zwei Wörtern ab `gap_ms`, dort fehlen womöglich Wörter | `needs_review` |
| `sparse` | weniger als `min_words_per_second` Wörter pro Sekunde in einer Passage ab 1 s | `needs_review` |
| `missing_times` | das Backend kann Zeiten liefern, Passage oder Wörter haben aber keine | `needs_review` |
| `speaker_unclear` | Diarisierung vorhanden, aber kein Mehrheitslabel der Wörter | `needs_review` |
| `crosstalk` | die Passage überschneidet Bereiche mit Übersprechen für insgesamt mindestens `crosstalk_ms` | `needs_review` |
| `known_variant` | Review-Hinweis auf einen bekannten Hörfehler | `needs_review` |
| `similar` | Review-Hinweis auf eine ähnliche Schreibung oder einen ähnlichen Klang | `similar_level` (Schreibung), `similar_sound_level` (nur Klang, Default `confident`: Hinweis sichtbar, Passage nicht angehoben); `confident` heißt ohne Wirkung |
| `ambiguous` | mehrdeutiger Review-Hinweis | `uncertain` |
| `no_signals` | weder Word-Confidence noch Whisper-Signale vorhanden | `needs_review` |

- **Fehlende Daten werden nie ersetzt.** Fehlt einer Passage eine Signalart, greifen ihre Regeln nicht, und die Art steht unter `missing`: `word_confidence`, `segment_signals`, `word_times`, `speaker` (keine Diarisierung) oder `hints` (keine Hinweisdatei, oder sie passt nicht zum Referenztranskript). Sicher wird eine Passage nur durch Confidence oder Whisper-Signale. Zeiten, Sprecher und Hinweise können eine Stufe nur anheben.
- **Gleiche Eingabe, gleiche Stufen:** Die Regeln sind deterministisch und lesen nur Referenztranskript, Hinweisdatei und Konfiguration. Beide Dateien bleiben unverändert.
- **Sprecher und Mundart:** Labels gelten pro Segment und sind bis TOOL-68 keiner Person zugeordnet. Schwellen pro Person gibt es deshalb nicht.

Die Datei `work/<gruppe>/<ordinal>/review/segment-NN.uncertainty.json` (`format_version: 1`) enthält pro Passage Index, Stufe, Gründe (`rule`, `level`, gesehener `value`, `threshold`, Wortpositionen `words`) und `missing`. Dazu kommen im Kopf die verwendeten Schwellen, das gelesene Referenztranskript und die Snapshot-Kennung der Hinweise. Text enthält sie nicht. Ein fehlgeschlagenes Segment verliert seine Datei. Die Konsole zeigt nur Zahlen, etwa `passages: 412 confident, 96 needs_review, 31 uncertain`.

### Kalibrierung

`transcript calibrate` misst die Bewertung an einer Handreferenz: einer Textdatei, die beim Anhören eines Abschnitts eines Segments entsteht. Jede Zeile darf mit einer Sprecherkennung beginnen (`Name:`), Notizen in eckigen Klammern sind keine Sprache, `???` markiert Unverständliches. Was die Spracherkennung dort erkennt, zählt weder als richtig noch als Einfügung (Konvention aus [TOOL-62](docs/spikes/TOOL-62-asr-vergleich.md)).

```bash
transcript calibrate beispielgruppe/042 --segment 1 --reference work/beispielgruppe/042/review/calibration/reference.txt \
  --start 01:20:00.000 --end 01:23:00.000
```

`--start` und `--end` sind Zeiten im Segment-WAV. Gezählt werden die Wörter, die in diesem Bereich beginnen. Die Ausrichtung beruht auf `difflib` und liegt nahe an der minimalen Wortfehlerrate. Jede Ersetzung und Einfügung zeigt auf ein erkanntes Wort, jede Auslassung auf die Stelle daneben und damit auf eine Passage. Die Bewertung entsteht mit den Schwellen der aktuellen Konfiguration neu, gespeichert wird nichts. Wer Schwellen ändert, ruft `calibrate` einfach noch einmal auf.

Der Bericht enthält nur Zahlen:
- Fehler gesamt und nach Art
- Fehlerquote je Sprecher der Handreferenz, als `S1`, `S2`, … in der Reihenfolge ihres Auftretens
- pro Stufe und für alle markierten Passagen: Anteil an Passagen und Zeit, enthaltene Fehler und Auslassungen
- übersehene Fehler in `confident`-Passagen und Fehlalarme, also markierte Passagen ohne Fehler
- pro Regel die Passagen, in denen sie angeschlagen hat
- die AUC der Word-Confidence und der Anteil falscher Wörter unter den unsichersten 10, 20 und 30 %

Für `similar` gibt es einen Bogen zum Anhören. `transcript calibrate <session> --similar-sheet` schreibt höchstens 50 `similar`-Hinweise nach `work/<gruppe>/<ordinal>/review/calibration/similar-sheet.csv`, gleichmäßig über die Session verteilt und bei gleichen Hinweisdateien immer dieselben. In die Spalte `correct` kommt `ja` oder `nein`, leer heißt nicht beurteilt. Die Spalte `relevance` nennt die Relevanz-Stufe des Hinweises. Bei mehreren Kandidaten ist es die nächste (`pc` vor `session`, `recent`, `archive`). `--similar-judged <datei>` liest den ausgefüllten Bogen und gibt die Präzision je Methode und Score-Band aus, außerdem je Methode und Relevanz-Stufe, etwa `similar sound / archive`. Ein älterer Bogen ohne `relevance` liefert nur Methode und Score-Band. Eine Trefferquote ergibt sich daraus nicht. Handreferenz und Bogen enthalten echte Namen und bleiben unter `work/`. Ein mit Semikolon gespeicherter Bogen, etwa aus einer deutschen Tabellenkalkulation, und zusätzliche Spalten werden ebenfalls gelesen.

Die Defaults der Schwellen stammen aus der ersten Kalibrierung, siehe [TOOL-35-Bericht](docs/spikes/TOOL-35-kalibrierung.md).

## Review-Kandidaten

Nach jeder [Unsicherheitsbewertung](#unsicherheitsbewertung) entsteht die Prüfliste der Session neu (`transcript.candidates`): jede Passage mit der Stufe `needs_review` oder `uncertain` aus allen bewerteten Segmenten. Sichere Passagen erscheinen nicht. Eine eigene Regel hat die Liste nicht, sie übernimmt die Bewertung. Läuft `transcript assess --segment N`, entsteht die Liste trotzdem für die ganze Session.

- **Reihenfolge:** erst `uncertain`, dann `needs_review`. Innerhalb einer Stufe kommen Passagen mit einem bekannten Hörfehler (`known_variant`) oder einem mehrdeutigen Hinweis zuerst, danach gilt die Aufnahmereihenfolge.
- **Domänenwissen** löst einen Kandidaten aus, wenn ein Hinweis die Stufe hebt, und verstärkt ihn, weil seine Hinweise mit Kandidaten aus Narrata am Kandidaten hängen. Korrigiert wird nichts. Ein `similar`-Hinweis nur über den Klang hebt nach Default nicht an und macht deshalb keinen Kandidaten, er bleibt in der Hinweisdatei sichtbar.
- **Pro Kandidat:** Kennung (`s01-p0042` für Segment 1, Passage 42), Stufe, Gründe mit Werten und Schwellen, `missing`, der erkannte Text unverändert, das Sprecher-Label (bis TOOL-68 keine Person), die Session-Zeit (siehe [Referenzformat](docs/referenzformat.md), `null`, wenn das Backend keine Zeit lieferte) und die Hinweise, mit denen die Passage bewertet wurde.
- **Kennzahl:** Kandidaten pro Stunde Audio, gerechnet nur über die bewerteten Segmente. Segmente ohne Transkript oder mit Fehlschlag stehen unter `not_rated`.
- **Aktualität:** Passt eine Bewertung nicht mehr zu ihrem Referenztranskript, bricht der Schritt mit `run transcript assess` ab, statt auf veralteten Text zu zeigen.

Die Datei `work/<gruppe>/<ordinal>/review/candidates.json` (`format_version: 1`) enthält erkannten Text und Archivnamen und bleibt deshalb unter `work/`. Die Konsole zeigt nur Zahlen, etwa `review candidates: 57 (12.3 per hour of audio)`. Die [Review-Entscheidungen](#review-entscheidungen) und die [Review-CSV](#review-csv) lesen diese Datei. Überlappende Segmenttranskriptionen sind kein Signal: Ohne eigene Segmentierung ([TOOL-62](docs/spikes/TOOL-62-asr-vergleich.md)) gibt es sie nicht.

## Review-Entscheidungen

Was beim Anhören eines Kandidaten entschieden wird, steht in einer eigenen Datei (`transcript.decisions`): `work/<gruppe>/<ordinal>/review/decisions.json` (`format_version: 1`). Die Kandidatendatei bleibt rein automatisch und entsteht bei jeder Bewertung neu. Die Entscheidungsdatei entsteht nur von Hand. So überschreibt keine Seite die andere, und Text, Stufe, Gründe und Hinweise des Kandidaten bleiben, wie die Pipeline sie erzeugt hat.

| Status | Bedeutung |
| --- | --- |
| `open` | noch nicht entschieden; das gilt auch für jeden Kandidaten ohne Eintrag |
| `confirmed` | der erkannte Wortlaut stimmt |
| `corrected` | der Wortlaut ist falsch; der richtige steht in `target_text` |
| `unintelligible` | nicht zu verstehen |
| `kept` | bewusst unverändert gelassen, auch wenn er falsch sein kann |
| `deferred` | später prüfen |

- **Pro Eintrag:** Kandidaten-ID, Segment, Passage, die Fassung des Transkripts, auf die sich die Entscheidung bezieht (`reference_processed_at`), Status, Zeitpunkt, optional `target_text` und `note`. Einen `target_text` gibt es nur bei `corrected`, dort ist er Pflicht. Ein Eintrag pro Kandidat, ein späterer ersetzt den früheren.
- **Veraltet:** Ist das Segment seitdem neu transkribiert, gilt die Entscheidung nicht mehr, und der Kandidat ist wieder offen. Eine neue Bewertung bei gleichem Transkript ändert nichts, denn die Entscheidung betrifft den Text.
- **Verwaist:** Ist der Kandidat verschwunden, etwa weil die Passage nach neuer Kalibrierung sicher ist, bleibt die Entscheidung ebenfalls in der Datei stehen.
- Veraltete und verwaiste Entscheidungen werden gemeldet, nie gelöscht und nie angewendet. Angewendet wird eine Entscheidung erst in der Arbeitsfassung (TOOL-49).

Die Datei enthält Zieltexte und Notizen und bleibt deshalb unter `work/`. Die [Review-CSV](#review-csv) liest sie, der [Review-Import](#review-import) schreibt sie.

## Review-CSV

`transcript review-export <gruppe>/<ordinal> [--all] [--force]` schreibt die Kandidaten, die noch zu entscheiden sind, als Tabelle nach `work/<gruppe>/<ordinal>/review/review.csv` (`transcript.review_sheet`). Gelesen werden `candidates.json` und `decisions.json`, beide bleiben unverändert. Fehlt die Kandidatendatei, verweist der Befehl auf `transcript assess`.

- **Umfang:** standardmäßig die Status `open` und `deferred`. Ein Kandidat mit veralteter Entscheidung zählt als `open`. Mit `--all` kommen alle Kandidaten dazu, entschiedene mit Status, Zieltext und Notiz. Sichere Passagen erscheinen nie, sie sind keine Kandidaten.
- **Reihenfolge:** chronologisch nach Segment und Passage. Gleiche Daten ergeben byteweise dieselbe Datei, sie enthält keinen Exportzeitpunkt. Die Spalte `order` nennt die Position in der Review-Reihenfolge der Kandidaten (`uncertain` und starke Hinweise zuerst). Wer nach ihr sortiert, hört die wichtigsten Stellen zuerst.
- **Format für deutsches Excel:** Trennzeichen `;`, UTF-8 mit BOM, Zeilenende CRLF. Die Datei öffnet per Doppelklick mit richtigen Spalten und Umlauten. Mehrzeilige Zellen stehen in Anführungszeichen. LibreOffice liest das ebenso.
- **Formelschutz:** Eine Freitextzelle (`text`, `hints`, `target_text`, `note`), die mit `=`, `+`, `-` oder `@` beginnt, bekommt ein führendes `'`, damit Excel sie nicht als Formel liest. Der [Review-Import](#review-import) entfernt das Zeichen wieder. Das Transkript selbst bleibt unverändert, `text` ist nur eine Anzeigekopie.
- **Kein stilles Überschreiben:** Eine vorhandene `review.csv` kann ausgefüllte, noch nicht importierte Entscheidungen enthalten. Der Befehl bricht dann ab, `--force` ersetzt sie.

| Spalte | Inhalt |
| --- | --- |
| `id` | Kandidaten-ID, z. B. `s01-p0042` |
| `start`, `end` | Session-Zeit `HH:MM:SS.mmm`, leer ohne Zeit |
| `segment`, `segment_start` | Segment und Zeit im Segment-WAV, zum Suchen im Audio |
| `speaker` | Sprecher-Label (bis TOOL-68 keine Person) |
| `level` | `needs_review` oder `uncertain` |
| `order` | Position in der Review-Reihenfolge |
| `reasons` | Gründe mit gesehenem Wert und Schwelle, z. B. `low_confidence 0.333/0.2` |
| `missing` | fehlende Signalarten |
| `hints` | je Hinweis Signal, gehörte Wörter und Archiv-Einträge mit Typ, ID, Begriff, Art und Stufe, `ambiguous` bei mehreren |
| `text` | erkannter Text, unverändert |
| `status` | Review-Status (siehe [Review-Entscheidungen](#review-entscheidungen)) |
| `target_text` | richtiger Wortlaut, nur bei `corrected` |
| `note` | Notiz |
| `earlier_decision` | eine veraltete Entscheidung zu älterem Transkript, etwa `corrected 2027-02-01T…, older transcript`; ihr Zieltext wird nicht übernommen |
| `version` | Fassung des Transkripts, die die Zeile zeigt |

Der [Review-Import](#review-import) liest nur `id`, `status`, `target_text`, `note` und `version`. Alle anderen Spalten dienen der Anzeige. Verwaiste Entscheidungen haben keinen Kandidaten mehr und stehen deshalb nicht in der Tabelle. Die Konsole nennt ihre IDs, sonst zeigt sie nur Zahlen, etwa `review sheet: 61 row(s): 7 deferred, 54 open`. Die Datei enthält erkannten Text, Archivnamen und Notizen und bleibt unter `work/`.

## Review-Import

`transcript review-import <gruppe>/<ordinal>` liest die ausgefüllte `review/review.csv` zurück und speichert die Entscheidungen in `review/decisions.json` (`transcript.review_import`). `candidates.json` und das Transkript werden nur gelesen. Fehlt die Kandidatendatei, verweist der Befehl auf `transcript assess`, fehlt die Tabelle, auf `transcript review-export`. Danach lassen sich die Entscheidungen ohne die CSV laden.

- **Gelesen:** nur `id`, `status`, `target_text`, `note` und `version`. Reihenfolge und weitere Spalten sind egal, das Trennzeichen (`;` oder `,`) wird an der Kopfzeile erkannt. Zellen werden getrimmt, ein leerer Status gilt als `open`, Groß- und Kleinschreibung des Status zählt nicht. Leere Zeilen, auch `;;;`-Zeilen, werden übersprungen.
- **Unverändert ist keine Entscheidung:** Stimmen Status, Zieltext und Notiz einer Zeile mit der geltenden Entscheidung überein (ohne Entscheidung: `open` und leer), bleibt alles, wie es ist, samt Zeitpunkt. Eine unverändert zurückgelesene Tabelle ändert nichts. Wer dieselbe Datei zweimal importiert, ändert beim zweiten Mal ebenfalls nichts.
- **Fehlerhafte Zeilen:** Sie werden gemeldet und ausgelassen. Die übrigen Zeilen werden trotzdem gespeichert, der Befehl endet mit Exit-Code 2. Fehler sind: fehlende oder unbekannte ID, ungültiger Status, `corrected` ohne Zieltext, ein Zieltext bei anderem Status und eine geänderte Zeile, deren `version` nicht mehr die aktuelle Fassung des Transkripts ist. In diesem letzten Fall neu exportieren. Unberührte Zeilen eines älteren Exports sind kein Fehler.
- **Ganze Tabelle abgelehnt:** wenn sie unlesbar ist, eine der fünf Spalten fehlt oder eine ID zweimal vorkommt. Dann ist unklar, welche Zeile gilt. `decisions.json` bleibt unverändert.
- **Formelschutz:** Ein führendes `'` vor `=`, `+`, `-` oder `@` in `target_text` und `note` wird entfernt. Ein anderes führendes `'` bleibt stehen.
- **Konsole:** Fehlermeldungen nennen Datei, Tabellenzeile (Kopfzeile = 1), ID und Feld, nie einen Zellinhalt, etwa `row 7 (s01-p0042): field 'target_text' required for corrected`. Eine Zelle, die nicht wie eine ID aussieht, erscheint als `invalid id`. Die Zusammenfassung zeigt nur Zahlen, etwa `review import: 3 decision(s): 1 confirmed, 2 corrected, 58 unchanged, 1 left out`. `decisions.json` wird nur bei einer Änderung geschrieben, atomar.
- `review.csv` bleibt nach dem Import liegen. Ein neuer Export braucht deshalb `--force`.

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
| `narrata.url` | nein | `null` | Basis-URL des Narrata-Hosts für `transcript context`; `https`, `http` nur für `localhost`, ohne Zugangsdaten und Query |
| `narrata.groups` | nein | `{}` | Gruppen-ID in Narrata je Gruppen-Slug, z. B. `beispielgruppe: 12` |
| `narrata.recent_sessions` | nein | `3` | Fenster der Stufe `recent`: die letzten `n` Sitzungen, diese eingeschlossen, `1` bis `20` |
| `narrata.archive_limit` | nein | `500` | Höchstzahl der Glossar-Einträge der Stufe `archive`, `0` bis `2000` |
| `knowledge.keyword_budget` | nein | person 15, place 10, organisation 5, artifact 5, event 3, lore 3 | Höchstzahl der Keyword-Einträge je Typ aus den Stufen `session` und `recent`; Spielfiguren zählen nicht mit, ein fehlender Typ behält seinen Default, `0` heißt keiner |
| `review.similar.min_ratio` | nein | `0.85` | Mindestähnlichkeit der Schreibung für einen Hinweis `similar`, `0` bis `1` |
| `review.similar.min_length` | nein | `4` | Mindestlänge von Begriff und Wortfolge in Buchstaben, `1` bis `50` |
| `review.similar.max_length_deviation` | nein | `0.3` | höchste Längenabweichung als Anteil der Begriffslänge, `0` bis `0.9` |
| `review.uncertainty.*` | nein | siehe `config/example.yaml` | Schwellen der [Unsicherheitsbewertung](#unsicherheitsbewertung): `word_low` (0,5), `word_very_low` (0,2), `low_share_review` (0,2), `low_share_uncertain` (0,5), `no_speech_prob` (0,6), `avg_logprob` (−1,0), `compression_ratio` (2,4), `gap_ms` (2500), `min_words_per_second` (1,0), `crosstalk_ms` (1000), `similar_level` (`needs_review`), `similar_sound_level` (`confident`); `word_very_low` darf `word_low` nicht übersteigen, `low_share_review` nicht `low_share_uncertain` |
| `debug` | nein | `false` | schreibt Transkripttext nach `work/<gruppe>/<ordinal>/debug.log`, nie auf die Konsole |

Einen eigenen Ausgabepfad gibt es nicht: `output/` liegt immer unter `paths.root`, damit echte Daten im Layout unter [Sessions](#sessions) bleiben. Secrets gehören nicht in diese Datei, sondern in `.env` (Vorlage `.env.example`, heute nur `NARRATA_TOKEN`).

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
  narrata/                     transcription-context.json (Rohantwort von Narrata), snapshot.json (Wissens-Snapshot), diagnosis.json (Diagnose)
  audio/                       segment-NN.wav (Arbeitsformat, eine pro Aufnahme), audio.json (Audio-Metadaten)
  asr/                         segment-NN.json (Referenztranskript), segment-NN.raw.json (Backend-Rohantwort)
  diarization/                 segment-NN.json (Sprecher-Turns von pyannote)
  review/                      segment-NN.hints.json (Review-Hinweise aus dem Wissen), segment-NN.uncertainty.json (Unsicherheitsbewertung), candidates.json (Review-Kandidaten der Session), decisions.json (Review-Entscheidungen), review.csv (Review-CSV)
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
