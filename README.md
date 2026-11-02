# narrata-transcript

Lokale Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte Transkripte für [Narrata](https://github.com/A1etheia/ios-archiv) überführen soll.

**Aktueller Stand: nur das Projektgerüst.** Das Paket lässt sich installieren und `transcript --help` läuft. Session-Schlüssel und Verzeichnislayout sind festgelegt. Audioverarbeitung, Transkription und Export existieren noch nicht.

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

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Smoke-Test

```bash
transcript --help
python -m transcript --help
```

## Prüfen

`scripts/check` führt Lint, Formatprüfung und Tests aus; `scripts/check --fix` wendet vorher die automatischen Korrekturen an.

## Verzeichnisstruktur

```
docs/            Roadmap und Ticket-Pläne
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
  manifest.json                Gruppe, Ordinal, play_session_id, Sitzungsdatum, Audio-Hash
  audio/                       extrahierte Spur, Segmente
  snapshot/                    Wissens-Snapshot
  asr/                         ASR-Zwischenergebnisse
  review/                      Review-Kandidaten, CSV
  speakers/                    Sprecherzuordnung
  debug.log                    nur im Debug-Modus
output/beispielgruppe/042/     JSON-Export, TXT, DOCX
```

Die Verzeichnisse von `input/` werden von Hand befüllt. Die Pipeline liest dort nur und schreibt ausschließlich nach `work/` und `output/`. ASR-Ergebnisse werden nie überschrieben.

## Dateiregeln

Einwilligung, Aufbewahrung und Sichtbarkeit regelt [`docs/datenschutz.md`](docs/datenschutz.md). Rohaudio bleibt bis zum Kampagnenende lokal, der Wissens-Snapshot dauerhaft.

**Nie committen:** Audio und Segmente, Transkripte, Klarnamen, Wissens-Snapshots, Secrets. Die `.gitignore` schließt `input/`, `work/`, `output/` in jeder Tiefe aus, dazu `.env`, gängige Audio- und Videoformate sowie `*.srt`, `*.vtt` und `*.docx`. `tests/test_gitignore.py` prüft diese Regeln. `*.json`, `*.txt` und `*.csv` sind nicht global ausgeschlossen; echte Dateien dieser Art gehören deshalb nur in die drei Verzeichnisse.

**Nie hochladen:** Rohaudio, Segmente, Arbeitsdateien aus `work/` und den Wissens-Snapshot. Nach Narrata geht ausschließlich der strukturierte Transkript-Export aus `output/`.

**Echte Sessions** liegen nur lokal: Die Originalaufnahme kommt von Hand nach `input/<gruppe>/<ordinal>/`, alles Weitere erzeugt die Pipeline (siehe [Sessions](#sessions)).

**Secrets** liegen in `.env`, später auch das Narrata-Token. Noch benötigt das Projekt keine Secrets.

**Test-Fixtures** liegen in `tests/fixtures/`. Sie sind klein und synthetisch oder vollständig anonymisiert und enthalten kein Audio; die Regeln stehen in [`tests/fixtures/README.md`](tests/fixtures/README.md).

## Nächste Schritte

Reihenfolge und Meilensteine stehen in [`docs/transcript-roadmap.md`](docs/transcript-roadmap.md); die Tickets laufen im Jira-Projekt `TOOL`.
