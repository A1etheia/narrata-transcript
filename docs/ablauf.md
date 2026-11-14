# Ablauf V0.1: eine Sitzung von der Aufnahme bis Narrata

Diese Anleitung führt Schritt für Schritt durch eine Sitzung, so wie V0.1 im Pilot (TOOL-58) gelaufen ist. Einzelheiten zu jedem Befehl stehen im [README](../README.md); die Abschnitte hier verlinken dorthin. Als Beispiel dient die Session `beispielgruppe/042`.

## Was V0.1 ist und was nicht

- **Vollständig lokal.** Spracherkennung (Whisper large-v3-turbo) und Diarisierung (pyannote) laufen auf dem eigenen Rechner. Rohaudio verlässt ihn nie. Ins Netz geht nur der Abruf des Transkriptionskontexts aus Narrata.
- **Kein Alttranskript, kein Alignment.** Die Pipeline braucht nur die Aufnahme und das Wissen aus Narrata. Ein vorhandenes Transkript wird weder importiert noch angeglichen, beides gehört nicht zu V0.1. `transcript calibrate --reference` misst die Erkennung an einer Handreferenz und ist ein optionales Werkzeug, kein Schritt des Ablaufs.
- **Keine Cloud-ASR.** Es gibt kein Remote-Backend.
- **Ergebnis** ist ein JSON-Transkript nach Narrata-Contract 1.0 bzw. 1.1, dazu TXT, DOCX und ein Abschlussbericht.

## 1. Einmalig einrichten

Voraussetzungen: Python 3.10+, `python3-venv`, `ffmpeg` (bringt `ffprobe` und `ffplay` mit). Für die GPU eine NVIDIA-Karte, getestet mit 12 GB VRAM unter WSL.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,whisper,diarization]'
cp config/example.yaml config/config.yaml
cp .env.example .env
```

Modelle einmalig mit Netz in den lokalen Cache laden (Details: README [Spracherkennung](../README.md#spracherkennung) und [Diarisierung](../README.md#diarisierung)):

```bash
.venv/bin/python -c "from faster_whisper import download_model; download_model('large-v3-turbo')"
.venv/bin/hf auth login     # pyannote-Modell ist gated: vorher auf der Modellseite die Bedingungen annehmen
.venv/bin/hf download pyannote/speaker-diarization-community-1
```

Danach brauchen die Läufe kein Netz für Modelle mehr.

**Startskript.** `scripts/transcript` startet die CLI ohne aktivierte venv und setzt `LD_LIBRARY_PATH` für cuBLAS selbst. Ohne den Pfad scheitert die GPU-Erkennung. Am bequemsten einmal verlinken:

```bash
ln -s "$PWD/scripts/transcript" ~/.local/bin/transcript
```

Das Skript wechselt in den Projektordner. Relative Pfade in Argumenten, etwa `--from-file`, gelten deshalb ab dort. Wer lieber die venv aktiviert, setzt den Pfad wie im README unter [Spracherkennung](../README.md#spracherkennung). Alle Beispiele unten schreiben `transcript`.

**WSL-Speicher.** Erkennung und Diarisierung brauchen auf 5 h Audio je bis knapp 14 GB RAM, nacheinander. In `%UserProfile%\.wslconfig` etwa `memory=26GB` setzen, das Standardlimit reicht kaum.

## 2. Konfiguration

In `config/config.yaml` (alle Schlüssel: README [Konfiguration](../README.md#konfiguration)):

- `language: de`, `paths.root: .`
- `asr.model` (Default `large-v3-turbo`, auch ein lokales Modellverzeichnis) und `asr.device` (`auto`, `cuda`, `cpu`). Meist bleiben die Defaults.
- `narrata.url` und unter `narrata.groups` die Narrata-Gruppen-ID je Gruppen-Slug, z. B. `beispielgruppe: 12`. Beides braucht der Kontextabruf, die Gruppe auch der Export.

In `.env` steht `NARRATA_TOKEN`, der Login-Token einer aktiven Spielleitung der Gruppe. Er läuft nach 24 h ab und muss vor dem Kontextabruf frisch sein. Die Datei `.env` wird nie committet.

`transcript config` zeigt die wirksamen Werte, `transcript doctor` prüft Werkzeuge, Konfiguration und Modelle (README [Preflight](../README.md#preflight)).

## 3. Session anlegen und Audio bereitstellen

Der Session-Schlüssel ist `<gruppe>/<ordinal>`: Slug der Narrata-Gruppe und Ordinal der Spielsitzung in Narrata. Die Sitzung muss in Narrata schon angelegt sein. Die Aufnahmen kommen von Hand in den Ordner:

```bash
mkdir -p input/beispielgruppe/042
cp /pfad/zur/aufnahme*.m4a input/beispielgruppe/042/
```

- MP4, M4A, MP3 und WAV werden angenommen. Mehrere Dateien einer Sitzung sind mehrere Segmente, in der Reihenfolge ihrer Dateinamen.
- Nur eine Fassung jeder Aufnahme dort ablegen, sonst zählt sie doppelt.
- Alle hörbaren Personen müssen mündlich zugestimmt haben ([`datenschutz.md`](datenschutz.md)). Vermerkt wird das mit `--consent` beim ersten Lauf.

`input/`, `work/` und `output/` sind von Git ausgeschlossen. Was darin liegt, gehört in kein Repo und in keinen Upload außer dem Export nach Narrata.

## 4. Preflight

```bash
transcript doctor beispielgruppe/042
```

Der Befehl prüft vor dem langen Lauf die Aufnahmen, Schreibrechte, Platz, Narrata-Einrichtung bzw. gespeicherten Kontext, Snapshot und ob gespeicherte Ergebnisse noch passen. Auf der GPU prüft er auch, ob cuBLAS ladbar ist. Exit-Code `0` heißt los, auch mit Warnungen; `2` heißt, ein Fehler muss zuerst behoben werden. `transcript process` ruft denselben Preflight selbst auf, der Schritt hier zeigt Probleme nur früher.

## 5. Erster Lauf bis zum Halt

```bash
transcript process beispielgruppe/042 --consent
```

`process` ruft der Reihe nach `doctor`, `extract`, `context`, `snapshot`, `manifest`, `transcribe` (mit Diarisierung und Bewertung), Review, `speakers`, `working`, `export`, `txt`, `docx` und `report` auf. Im Pilot brauchten Erkennung und Diarisierung auf der GPU rund 12 Minuten für 5:26 h Audio ([TOOL-59](pilot/TOOL-59-auswertung.md)).

Danach **hält der Lauf an** (Exit-Code `3`) und nennt, was von Hand zu tun ist:

```
process: halted for manual steps
  review: fill in the decisions in work/beispielgruppe/042/review/review.csv
  speakers: run transcript speakers beispielgruppe/042 --assign, or edit work/beispielgruppe/042/speakers/assignment.json by hand with work/beispielgruppe/042/speakers/samples.md
then run transcript process beispielgruppe/042 again; what is left open stays open and is named in the report
```

Gibt es keinen Review-Kandidaten, entfällt die Review-Zeile.

### Domänenwissen aus Narrata

Der erste Lauf holt den Transkriptionskontext (Teilnehmende, Spielfiguren, Glossar) aus Narrata nach `work/…/narrata/transcription-context.json` und friert daraus den **Wissens-Snapshot** `snapshot.json` ein. Alle späteren Läufe verwenden beide wieder und fragen Narrata nicht mehr. Die Keywords des Snapshots gehen als Begriffshinweise an Whisper. Einzelheiten: README [Narrata-Kontext](../README.md#narrata-kontext) und [Wissens-Snapshot](../README.md#wissens-snapshot).

- **Ohne Netz:** Eine gespeicherte Antwort lässt sich mit `transcript context beispielgruppe/042 --from-file kontext.json` übernehmen, vor dem ersten `process`.
- **Wissen aktualisieren**, etwa nach neuen Glossar-Einträgen in Narrata:

  ```bash
  transcript context beispielgruppe/042                  # Kontext neu holen, Token frisch
  transcript process beispielgruppe/042 --redo snapshot  # Snapshot neu bauen, alles Spätere neu
  ```

  `--redo context` allein holt nur den Kontext neu. Der vorhandene Snapshot bleibt dann, und `snapshot` warnt, dass er abweicht. Ein neuer Snapshot mit anderen Keywords lässt `transcribe` die betroffenen Segmente neu erkennen. Was das für die Handdateien heißt, steht unter [Nach `--redo transcribe`](#nach---redo-transcribe-oder-neuem-snapshot).

## 6. Manuelle Schritte

### Review-Sheet ausfüllen

`work/beispielgruppe/042/review/review.csv` öffnet sich in Excel oder LibreOffice per Doppelklick. Jede Zeile ist eine unsichere Passage. Auszufüllen sind nur `status`, `target_text` und `note`:

| `status` | wann |
| --- | --- |
| `confirmed` | der erkannte Text stimmt |
| `corrected` | falsch; der richtige Wortlaut kommt in `target_text` |
| `unintelligible` | nicht zu verstehen |
| `kept` | bewusst so gelassen |
| `deferred` | später |
| leer / `open` | noch nicht entschieden |

Sortiert nach der Spalte `order` kommen die wichtigsten Stellen zuerst. Spalten und Regeln: README [Review-CSV](../README.md#review-csv) und [Review-Import](../README.md#review-import).

**Anhören.** Eine Abspielhilfe für das Review gibt es in V0.1 nicht. Mit `ffplay` geht es über die Spalten `segment` und `segment_start`, die Zeit im Segment-WAV. Die Spalte `start` ist Session-Zeit: Ab dem zweiten Segment springt der Player damit hinter das Ende der Datei und bleibt stumm.

```bash
# Zeile mit segment 2, segment_start 00:41:13.200; zwei Sekunden früher einsetzen
ffplay -nodisp -autoexit -ss 00:41:11.200 -t 20 work/beispielgruppe/042/audio/segment-02.wav
```

### Sprecher zuordnen

```bash
transcript speakers beispielgruppe/042 --assign
```

Der Dialog geht jedes Sprecher-Label durch, spielt Hörproben ab (Buchstaben `a`–`e`) und nimmt die Person als Zahl, `u` für unbekannt, `m` für mehrere oder `s` zum Überspringen. Jede Wahl wird sofort gespeichert. Am Ende bietet er die gemessene Dauer als Aufwand an. Er braucht ein echtes Terminal und `ffplay` mit Tonausgabe. Ohne Ton nennt er Datei und Zeit für einen anderen Player. Einzelheiten: README [Interaktiv zuordnen](../README.md#interaktiv-zuordnen).

## 7. Zweiter Lauf bis zum Ergebnis

```bash
transcript process beispielgruppe/042
```

Der Lauf verwendet alles bisher Erledigte wieder, liest Review-Sheet und Zuordnung ein und schreibt Arbeitsfassung, Export, TXT, DOCX und Bericht. Was offen geblieben ist, bleibt offen und steht im Bericht als Lücke. Es wird nichts geraten.

| Exit-Code | Bedeutung |
| --- | --- |
| `0` | fertig, ohne Lücken |
| `1` | fertig mit Lücken (offene Passagen oder Sprecher), oder angehalten an einem unvollständigen Schritt |
| `2` | Fehler, der Lauf steht am genannten Schritt (`process: stopped at <schritt> (exit 2)`) |
| `3` | angehalten für die manuellen Schritte |

Weiteres Review geht jederzeit: neues Sheet mit `transcript review-export beispielgruppe/042 --force` (das alte ist schon eingelesen), ausfüllen, erneut `transcript process beispielgruppe/042`. Alles ab der Arbeitsfassung wird bei jedem Lauf neu geschrieben, die Passagen-IDs im Export bleiben dabei gleich.

## 8. Status, Abbruch und Fortsetzen

```bash
transcript status beispielgruppe/042   # jeder Schritt, Gesamtstatus, wie es weitergeht
transcript status                      # eine Zeile je Sitzung
```

`status` leitet alles aus den Dateien ab, schreibt nichts und nennt am Ende den Befehl zum Fortsetzen. Gesamtstatus und Schrittstatus: README [Status einer Sitzung](../README.md#status-einer-sitzung).

- **Abbruch und Fortsetzen:** Nach Ctrl-C oder Absturz einfach `transcript process beispielgruppe/042` erneut starten. Fertige Segmente werden wiederverwendet, nur offene neu erkannt. Die zurückgebliebene `work/…/process.lock` meldet `status` als `interrupted`, und der nächste Lauf ersetzt sie. Läuft der Prozess der Lock-Datei noch, bricht ein zweiter Lauf mit Exit-Code `2` ab.
- **Strenger Guard:** `process` startet nicht, wenn es fertige Segmente stillschweigend neu erkennen müsste, weil Modell, Einstellungen, Snapshot, Keywords oder Sprache abweichen. Die Meldung nennt die Segmente. Entweder die Konfiguration zurückstellen oder bewusst `transcript process beispielgruppe/042 --redo transcribe` laufen lassen.
- **Protokoll:** `work/beispielgruppe/042/pipeline.log` enthält jeden Schritt mit Exit-Code, Wiederverwendung, fehlgeschlagene Versuche, Halt und Abbruch, mit Zeitstempel. Transkripttext, Keywords und Labels stehen nicht darin.
- **Neu ausführen:** `--redo extract|context|snapshot|manifest|transcribe` erzwingt diesen Schritt und lässt alle späteren laufen.

## 9. Ergebnis und Import in Narrata

Unter `output/beispielgruppe/042/`:

| Datei | Inhalt |
| --- | --- |
| `transcript.json` | strukturiertes Transkript nach Narrata-Contract 1.0, bei mehreren Aufnahmen 1.1 |
| `transcript.txt`, `transcript.docx` | lesbare Fassung zum Archivieren |
| `report.md`, `report.json` | Abschlussbericht: Vollständigkeit, Review- und Zuordnungsaufwand, Lücken, Laufzeit; ohne Text und Namen |

Nach Narrata geht nur `transcript.json`: über den Upload-Endpoint der aktiven Spielleitung (`POST /api/play-sessions/{id}/transcript`) oder in `ios-archiv` mit `scripts/artisan transcript:validate <datei>` und `scripts/artisan transcript:import <datei>`. Ein erneuter Import nach weiterem Review aktualisiert die Passagen. Dieselbe Datei zweimal ändert nichts. Die Hörfehler-Vorschläge aus dem Review (`work/…/review/asr-variant-suggestions.json`) übernimmt `scripts/artisan transcript:import-asr-variants <datei>` einzeln nach Rückfrage.

## 10. Artefakte einer Session

Unter `work/beispielgruppe/042/`, alles lokal und nicht im Repo (Baum: README [Sessions](../README.md#sessions)):

| Pfad | Bedeutung | von Hand? |
| --- | --- | --- |
| `audio/segment-NN.wav`, `audio/audio.json` | Arbeitsaudio je Aufnahme, Metadaten | nein |
| `narrata/transcription-context.json` | Rohantwort von Narrata | nein |
| `narrata/snapshot.json`, `narrata/diagnosis.json` | eingefrorenes Wissen, Prüfbefunde | nein |
| `manifest.json` | Segmente mit Session-Zeitachse, Zustimmung | nein |
| `asr/segment-NN.json`, `asr/segment-NN.raw.json` | Referenztranskript, Rohantwort; wird nie überschrieben, nur bei `--redo transcribe` neu erzeugt | nein |
| `diarization/segment-NN.json` | Sprecher-Turns | nein |
| `review/candidates.json` | unsichere Passagen | nein |
| `review/review.csv` | Review-Sheet | **ja** |
| `review/decisions.json` | eingelesene Entscheidungen | nein |
| `review/asr-variant-suggestions.json` | Hörfehler-Vorschläge für Narrata | nein |
| `speakers/samples.md` | Hörliste je Label | nein |
| `speakers/assignment.json` | Sprecherzuordnung | **ja**, meist über `--assign` |
| `working/transcript.json` | Arbeitsfassung, Grundlage des Exports | nein |
| `pipeline.log`, `process.lock` | Protokoll, Sperre eines laufenden `process` | nein |

## 11. Fehler aus dem Pilot

### `BackendUnavailableError … libcublas.so.12 cannot be loaded`

`LD_LIBRARY_PATH` fehlt. `transcript doctor` meldet das vorher als Fehler. Abhilfe: `scripts/transcript` verwenden oder den Pfad wie im README setzen. Das gilt auch für `transcript: command not found` ohne aktivierte venv.

### Nach `--redo transcribe` oder neuem Snapshot

Neu erkannte Segmente bekommen neue Passagen und neue Sprecher-Labels. Die alten Handdateien gelten dann nicht mehr: Entscheidungen zu altem Text sind veraltet, Zuordnungen zu alten Labels werden nicht angewendet, und `process` schreibt keine frischen Vorlagen, solange die alten Dateien da sind. Deshalb **vor** dem Lauf beiseitelegen:

```bash
mkdir -p work/beispielgruppe/042/vorher
mv work/beispielgruppe/042/review/review.csv work/beispielgruppe/042/speakers/assignment.json work/beispielgruppe/042/vorher/
transcript process beispielgruppe/042 --redo transcribe
```

Wurde das vergessen: `transcript review-export beispielgruppe/042 --force` schreibt ein Sheet mit den offenen Kandidaten, und `transcript speakers beispielgruppe/042 --assign` bietet die nicht angewendeten Labels als offen an.

### `process` verweigert den Start wegen abweichender Ergebnisse

Das ist der strenge Guard aus Abschnitt 8. Entweder die Ursache in der Konfiguration zurücknehmen oder mit `--redo transcribe` neu erkennen, mit den Folgen von oben.

### Kontextabruf scheitert mit 401 oder 404

`401`: Token fehlt oder ist abgelaufen (24 h), neu in `.env` eintragen. `404`: Gruppe, Sitzung oder aktive Spielleitung unbekannt; `narrata.groups` und das Ordinal prüfen.

### Diarisierung bricht mit Speichermangel ab

WSL-Limit erhöhen (Abschnitt 1). Der nächste Lauf setzt an den offenen Segmenten fort.

## 12. Bekannte Grenzen von V0.1

- **Review-Aufwand:** Ein vollständiges Review dauerte im Pilot rund 25 h pro Abend. Wie viel Review künftig nötig ist und über welchen Kanal, entscheidet TOOL-60.
- **Kein Abspielen im Review:** Gehört wird über `ffplay` wie oben, eine Abspielhilfe hängt an der Entscheidung in TOOL-60.
- **Erkennungsqualität:** An zwei Handreferenzen lag die Wortfehlerrate bei 24–33 %, davon 38–57 % Auslassungen ([TOOL-58](pilot/TOOL-58-erste-session.md)). Verbesserungen untersucht TOOL-93. Unsichere Stellen bleiben als Kandidaten sichtbar, der erkannte Text wird nie still verändert.
- **Anwesenheit** führt Narrata noch nicht; zur Zuordnung stehen alle Mitglieder der Gruppe zur Wahl.
