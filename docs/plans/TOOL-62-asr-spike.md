# TOOL-62 — Lokale ASR-Modelle an realer Session evaluieren


## Ziel
Danach steht anhand echten Materials fest, welches lokale Backend V0.1 nutzt, welcher Kandidat Fallback ist und ob `TOOL-11`/`TOOL-33` gebraucht werden. Heute gibt es weder ASR-Code noch Messwerte; `TOOL-64` und `TOOL-11` warten auf diese Entscheidung, und Epic TOOL-8 lässt sich erst danach dimensionieren.

## Ist-Stand
- `pyproject.toml:12`: einzige Laufzeitabhängigkeit ist `pyyaml`, kein ASR-Code im Paket.
- `src/transcript/session.py:44-60`: `SessionPaths` liefert `input/`, `work/`, `output/` pro Session.
- `config/example.yaml:12-15`, `README.md:41-42`: Segmentwerte sind `null`, die Entscheidung liegt bei TOOL-62.
- `.gitignore`: `input/`, `work/`, `output/`, Audio und `.venv/` sind ausgeschlossen; `*.json`, `*.txt` und `*.csv` nur innerhalb dieser Verzeichnisse.
- `docs/datenschutz.md:12`: ASR-Ergebnisse verlassen den Rechner nicht.
- Maschine: RTX 3080 Ti (12 GB VRAM), Treiber 616.64, 20 Threads, 15 GB RAM in WSL, 945 GB frei, Python 3.10. `ffmpeg`/`ffprobe` fehlen, `uv` ebenfalls.
- Die volle MP4 mit Zustimmung aller Personen ist vorhanden; sie kommt von Hand nach `input/<gruppe>/<ordinal>/`.

## Entscheidungen
- **Vorgezogen vor `IOA-1216`/`IOA-1214`** (Entscheidung Projektverantwortliche, 2026-11-02): Der Spike schreibt kein Contract-JSON, die Leitlinie aus der Roadmap bleibt gewahrt. Die Abweichung geht als Hinweis in die Roadmap-Quelle.
- **Spike-Code bleibt außerhalb des Pakets:** `scripts/spike/`, eigene venv pro Kandidat unter `~/.cache/narrata-spike/`. Die Runtimes kollidieren vermutlich, und `pyproject.toml` soll erst mit `TOOL-64` eine ASR-Abhängigkeit bekommen.
- **Kandidaten:** faster-whisper (large-v3 und large-v3-turbo), Parakeet TDT 0.6B v3 über NeMo, Granite Speech 4.1 2B Plus. Lizenz, Deutsch-Support und Signale vor dem Lauf an den offiziellen Modellkarten prüfen: Sekundärquellen nennen Apache 2.0 für Granite und die NVIDIA Open Model License für Parakeet, Deutsch für die Plus-Variante ist unbestätigt. Ein Kandidat ohne Deutsch oder ohne lauffähiges Setup wird begründet dokumentiert (das AC erlaubt das).
- **Ein Ergebnisformat pro Lauf:** `run.json` mit Segmenten, Wörtern, Zeiten, Confidence-Signalen und Metadaten (Modell-Revision, Einstellungen, Laufzeit, Peak-VRAM/RAM). Es ist kein Vorgriff auf `TOOL-16`.
- **Bewertung:** `compare.py` richtet Läufe an der Handreferenz aus und gibt nur Kennzahlen aus (WER, Auslassungen, Einfügungen, Trefferquote der Eigennamen aus einer lokalen Liste). stdlib reicht dafür.
- **Akzeptanz der Unsicherheit:** Ein Kandidat mit gutem Wortlaut, aber ohne nutzbares Confidence-Signal zählt gegen die Kernhypothese aus `TOOL-60` und wird entsprechend gewichtet.

## Daten-Check
- Folgt TOOL-66: handled — Audio, Läufe, Handreferenz und Keyword-Liste liegen nur unter `work/<gruppe>/<ordinal>/spike/`.
- Transkripttext an Claude: handled — ASR-Ergebnisse dürfen den Rechner nicht verlassen, daher liest der Agent weder `run.json` noch Referenz noch Keyword-Liste. Hand-Check und Fehlerbeispiele macht die Projektverantwortliche; der Agent sieht nur die Kennzahlen von `compare.py`.
- Konsole und Fehlertexte: handled — Skripte geben nur Session-Schlüssel, Laufzeiten und Zähler aus; Exceptions drucken keine Transkriptinhalte.
- Repo: handled — der Bericht enthält nur Kennzahlen und pseudonymisierte oder nachgestellte Beispiele, keine Fantasienamen aus der Kampagne und keinen Session-Schlüssel. Das Repo gilt als öffentlich.
- Modelle laufen lokal: handled — Download einmalig, die Läufe danach mit `HF_HUB_OFFLINE=1`, sodass kein Audio und kein Text hinausgeht.

## Contract-Check
N/A — kein Contract-JSON, kein Endpoint. Die Keyword-Liste wird von Hand erstellt, `IOA-1215` ist nicht nötig.

## Resume-Check
- Abbruch: handled — jeder Lauf schreibt in ein eigenes Verzeichnis mit Zeitstempel, `run.json` entsteht erst am Ende; ein abgebrochener Lauf wird komplett neu gestartet. Beim Lauf über die volle Aufnahme kostet das Stunden, was für den Spike tragbar ist.
- Wiederverwendung: handled — fertige Läufe werden nie überschrieben.
- Gleiches Modell: handled — Modell-Revision und Einstellungen stehen in `run.json`. Einen Snapshot gibt es hier noch nicht.

## Dependency-Check
- Nötig: handled — `ffmpeg` per `sudo apt install ffmpeg` (Projektverantwortliche). Die Laufzeitpakete bleiben in den Spike-venvs, das Projekt selbst bekommt keine neue Abhängigkeit.
- Lokal und Lizenz: handled — Prüfung pro Kandidat im Bericht.
- Hardware: handled — 15 GB RAM sind für NeMo und den Lauf über die volle Aufnahme möglicherweise knapp. Falls ein Lauf daran scheitert, das Limit über `.wslconfig` erhöhen und das dokumentieren.

## Format-Check
N/A — `run.json` ist ein Wegwerf-Format des Spikes ohne Versionsfeld und ohne Leser im Paket.

## Chunks
### Chunk 1 — Spike-Werkzeug
- Dateien: `scripts/spike/cut.sh`, `scripts/spike/run_whisper.py`, `scripts/spike/run_parakeet.py`, `scripts/spike/run_granite.py`, `scripts/spike/compare.py`, `scripts/spike/README.md`
- Änderung: Ausschnitt per ffmpeg nach `work/.../spike/`, ein Runner pro Kandidat mit gemeinsamem `run.json`, Vergleich mit Kennzahlen, Setup je Kandidat. Die README ist auf Deutsch, der Code auf Englisch.
- Verify: `scripts/check`; `compare.py` an synthetischem Text mit bekannten Fehlern; jeder Runner an einem synthetischen ffmpeg-Sinuston oder einer eigenen Testdatei.
- AC: Mindestens zwei Runner laufen auf der GPU durch; `git status` zeigt nach dem Lauf keine Datendateien.

### Chunk 2 — Vergleich am Ausschnitt
- Dateien: `docs/spikes/TOOL-62-asr-vergleich.md`
- Änderung: Die Projektverantwortliche wählt 20–30 Minuten und prüft eine Teilmenge von Hand. Alle lauffähigen Kandidaten laufen auf identischem Audio mit dokumentierten Einstellungen. Der Bericht vergleicht alle Dimensionen aus dem Ticket.
- Verify: `scripts/check`; `git grep` auf die lokale Eigennamenliste über den Bericht, ohne Treffer.
- AC: Drei Kandidaten betrachtet, mindestens zwei ausgeführt; Wortlaut, Eigennamen, Auslassungen/Halluzinationen, Zeitstempel, Confidence und Laufzeit verglichen; Hardwarebedarf dokumentiert.

### Chunk 3 — Keyword-Biasing und volle Aufnahme
- Dateien: `docs/spikes/TOOL-62-asr-vergleich.md`
- Änderung: Zusätzlicher Lauf mit Keyword-Liste bei mindestens einem geeigneten Modell. Mindestens der Favorit läuft über die volle Aufnahme (Speicherverlauf, Abbrüche, Drift, Halluzinationen in Stille).
- Verify: `scripts/check`; `run.json` des vollen Laufs vorhanden, Gesamtdauer deckt die Aufnahme ab (nur Zähler prüfen).
- AC: Long-Audio-Frage beantwortet; Biasing an mindestens einem Modell bewertet.

### Chunk 4 — Entscheidung
- Dateien: `docs/spikes/TOOL-62-asr-vergleich.md`, `config/example.yaml`, `README.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung: Empfehlung und Fallback, Entscheidung zu `TOOL-11`/`TOOL-33` mit Default-Segmentlänge falls ja. Platzhalter-Hinweise in Konfiguration und README aktualisieren; Roadmap neu generieren (Stand, Hinweise, Abweichung der Reihenfolge).
- Verify: `scripts/check`; `.md` aus `transcript-roadmap.py` neu erzeugt.
- AC: Alle verbleibenden Akzeptanzkriterien des Tickets sind abgehakt; offene Fragen stehen bei `TOOL-20` und `TOOL-35`.

## Folge-Tickets
- `TOOL-20`: Die Handreferenz aus TOOL-62 (3 min, Sprecherkennung pro Zeile, 46 Wechsel) taugt als erste Referenz für die Diarisierung; die Sprecherzuordnung von Granite Plus ist ungetestet.
- `TOOL-35`: Word-Confidence trennt mit einer AUC von 0,79–0,82, die unsichersten 30 % enthalten 62–71 % der falschen Wörter; Auslassungen bleiben unsichtbar; beim Mundartsprecher ist die Fehlerquote mehr als dreimal so hoch. Stichprobe und Referenz aus TOOL-62 wiederverwenden.
- `TOOL-64`: Backend ist Whisper large-v3-turbo über faster-whisper (VAD, Wortzeiten, `beam_size 5`, ohne `condition_on_previous_text`); RAM bis 10,5 GB auf 5 h einplanen; Lizenz der CTranslate2-Konvertierung prüfen; `scripts/spike/` ablösen.
- `TOOL-44`: Hotwords nur mit large-v3-turbo, nie mit large-v3 (zerfällt); faster-whisper nimmt höchstens 223 Tokens, die wichtigsten Begriffe nach vorne; Wirkung auf die WER ist unbelegt.
- `TOOL-12`: `input/<gruppe>/ordinal/` enthält viele Sitzungen ohne gültiges Ordinal; vor dem ersten Manifest pro Sitzung einsortieren.
- `TOOL-11`, `TOOL-33`: verworfen, weil das V0.1-Backend ganze Aufnahmen ohne eigene Segmentierung verarbeitet (`docs/spikes/TOOL-62-asr-vergleich.md`).
- [kein Ticket: Mehrere Aufnahmen enden bei genau 5:00:00; ob das Aufnahmegerät begrenzt, prüft die Projektverantwortliche am Gerät]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Spike-Werkzeug | no |
| 2 | Vergleich am Ausschnitt | no |
| 3 | Keyword-Biasing, volle Aufnahme | no |
| 4 | Entscheidung, Konfiguration, Roadmap | no |
