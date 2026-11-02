# narrata-transcript

Lokale Pipeline, die Aufnahmen von Rollenspielsitzungen in strukturierte Transkripte für [Narrata](https://github.com/A1etheia/ios-archiv) überführen soll.

**Aktueller Stand: nur das Projektgerüst.** Das Paket lässt sich installieren und `transcript --help` läuft. Audioverarbeitung, Transkription und Export existieren noch nicht.

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
pip install -e .
```

## Smoke-Test

```bash
transcript --help
python -m transcript --help
python -m unittest discover -s tests
```

## Verzeichnisstruktur

```
docs/            Roadmap
src/transcript/  Python-Paket
tests/           Tests
```

## Echte Audio- und Transkriptdateien

Die Verzeichnisse `input/`, `work/` und `output/` sowie gängige Audioformate sind per `.gitignore` ausgeschlossen. Echte Aufnahmen und Transkripte gehören nicht in dieses Repository.

## Secrets

Lokale Secrets liegen in `.env`, die ebenfalls ignoriert wird. Noch benötigt das Projekt keine Secrets.

## Nächste Schritte

Reihenfolge und Meilensteine stehen in [`docs/transcript-roadmap.md`](docs/transcript-roadmap.md); die Tickets laufen im Jira-Projekt `TOOL`.
