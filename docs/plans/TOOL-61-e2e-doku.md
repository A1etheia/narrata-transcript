# TOOL-61 — V0.1-End-to-End-Workflow dokumentieren

## Ziel
Eine weitere Session lässt sich ohne Entwicklungswissen von der Aufnahme bis zum Narrata-Import verarbeiten. Heute ist das README eine Referenz nach Befehlen: Es gibt keinen linearen Ablauf und kein Troubleshooting. Die Workarounds aus dem Pilot (Startskript, Abspielen, Handdateien) stehen nur im Pilotbericht.

## Ist-Stand
- `README.md` (795 Zeilen) ist nach Befehlen gegliedert. `process` mit Wiederverwenden, `--redo`, Haltpunkten, Lock, `pipeline.log` und Exit-Codes steht schon in `README.md:57-75`, `status` in `README.md:77-99`.
- Veraltet: `README.md:5` (Stand „Audio-Vorbereitung“), `README.md:789` („keine Secrets“, im Widerspruch zu `NARRATA_TOKEN`, `README.md:123`) und der Verzeichnisbaum `README.md:762-775` (ohne `pipeline.log`, `process.lock`, `review/asr-variant-suggestions.json`, `review/calibration/`).
- cuDNN: `pyproject.toml:18` `nvidia-cudnn-cu12<9`, `README.md:221-232` (Pfad, erprobte Versionen, Lizenz). TOOL-94 (`docs/plans/TOOL-94-preflight-cuda.md:14,45`): CTranslate2 4.8.5 lädt nur `libcublas.so.12`, der Smoke-Test lief mit cuBLAS allein.
- Ablauf in `src/transcript/pipeline.py:16-47`, die Halts in `src/transcript/__main__.py:1373-1408`, Artefakte als Konstanten in `src/transcript/session.py:83-245`.
- Review-CSV: Die Spalte `segment_start` ist die Zeit im Segment-WAV (`src/transcript/review_sheet.py:44`). Mit ihr lässt sich ohne neuen Code abspielen.
- Pilot-Probleme in `docs/pilot/TOOL-58-erste-session.md:119-131`, Übergaben in `docs/plans/TOOL-55-e2e-cli.md:83,86`, `TOOL-57-pipeline-status.md:87`, `TOOL-58-pilot-session.md:83,90` und `TOOL-94-preflight-cuda.md:45`.
- Es gibt kein Startskript im Repo, `scripts/` enthält nur `check`.

## Entscheidungen
- **Eigene Ablauf-Doku `docs/ablauf.md`** statt einer weiteren README-Sektion. Sie beschreibt Schritt für Schritt und verlinkt für Details auf die README-Abschnitte, statt sie zu kopieren. Das README verweist oben darauf.
- **`scripts/transcript` im Repo** (Wahl der Nutzerin). Der Wrapper löst Symlinks auf, setzt `LD_LIBRARY_PATH` auf `.venv/…/nvidia/cublas/lib`, falls es den Ordner gibt, wechselt in den Projektordner (`paths.root` ist relativ) und ruft `exec .venv/bin/transcript "$@"` auf. Fehlt die venv, meldet er das mit Exit 2. Er lässt sich nach `~/.local/bin` verlinken. Relative Pfadargumente gelten damit relativ zum Projektordner; das steht in der Doku.
- **cuDNN entfernen** aus `pyproject.toml` und aus dem README (Pfad, Versionszeile, Lizenzsatz), vorher am Smoke-Test bestätigt (Wahl der Nutzerin).
- **Abspielen im Review nur dokumentiert:** `ffplay -nodisp -autoexit -ss <segment_start> work/<gruppe>/<NNN>/audio/segment-NN.wav`, ausdrücklich nicht die Spalte `start`. Ein Review-Dialog hängt an TOOL-60.
- Alle Beispiele verwenden `beispielgruppe/042` wie das README.

## Daten-Check
- handled — Beispiele nur mit `beispielgruppe/042` und erfundenen Werten. Vor jedem Commit prüft ein `grep` auf die echten Gruppennamen unter `input/`, dass sie im Diff nicht vorkommen.
- handled — Aus dem Pilotbericht kommen nur Fehlerbilder und Workarounds, keine Namen, kein Transkripttext und keine Laufzeitdaten der Session. Die Verifikation am Pilotlauf (`transcript status`, `--help`) bleibt in der Konsole, nichts davon kommt ins Repo.
- handled — Das Startskript gibt keine Pfade außer dem venv-Pfad aus und keinen Sitzungsinhalt. Die Test-Fixtures sind ein Fake-Stub.
- handled — Folgt TOOL-66 (`docs/datenschutz.md`): Die Doku nennt, wo Arbeits- und Ausgabedateien liegen und dass sie nicht ins Repo gehören.

## Contract-Check
- N/A, weil weder Contract-JSON noch der Endpoint geändert wird. Die Doku nennt nur, dass `output/…/transcript.json` den Contract 1.0/1.1 (IOA-1214) erfüllt und in Narrata importiert wird. Narrata braucht keine Änderung.

## Resume-Check
- N/A, weil kein langlaufender Schritt hinzukommt. Das vorhandene Resume-Verhalten (strenger Guard, `--redo`, `process.lock`) wird nur beschrieben.

## Dependency-Check
- handled — `nvidia-cudnn-cu12<9` entfällt, es kommt nichts hinzu. Vorher läuft der Whisper-Smoke-Test auf `cuda` mit `LD_LIBRARY_PATH` nur auf cuBLAS, dazu der Diarisierungs-Smoke-Test (pyannote/torch bringen ihr eigenes cuDNN mit) und `pip check`. Die lokale venv behält das Paket; der Effekt betrifft nur Neuinstallationen. Lizenzhinweis: Es bleibt nur cuBLAS unter der NVIDIA-Laufzeitlizenz.
- handled — `scripts/transcript` ist ein Bash-Skript ohne neue Abhängigkeit.

## Format-Check
- N/A, weil kein internes Format mit Versionsfeld geändert wird.

## Chunks
### Chunk 1 — cuDNN entfernen
- Dateien: `pyproject.toml`, `README.md` (Abschnitt Spracherkennung, `README.md:221-232`)
- Änderung: `nvidia-cudnn-cu12<9` raus. `LD_LIBRARY_PATH`-Snippet nur mit `nvidia/cublas/lib`, Satz „bringt cuBLAS mit“, Versionszeile ohne cuDNN, Lizenzsatz nur cuBLAS.
- Verify: `LD_LIBRARY_PATH=<sp>/nvidia/cublas/lib TRANSCRIPT_WHISPER_SMOKE=1 TRANSCRIPT_WHISPER_DEVICE=cuda .venv/bin/python -m unittest discover -s tests -p test_whisper_smoke.py -v`, dasselbe für `test_diarization_smoke.py`, `.venv/bin/pip check`, `scripts/check`
- AC: Die Smoke-Tests sind grün auf `cuda` ohne cuDNN-Pfad, und weder README noch pyproject erwähnen cuDNN.

### Chunk 2 — Startskript `scripts/transcript`
- Dateien: `scripts/transcript` (neu, ausführbar), `tests/test_start_script.py` (neu), `README.md` (Setup, Spracherkennung)
- Änderung: der Wrapper wie unter Entscheidungen. Der Test kopiert das Skript in ein Temp-Verzeichnis mit einem Fake-`.venv/bin/transcript`, der Arbeitsverzeichnis, `LD_LIBRARY_PATH` und Argumente ausgibt, und einem Fake-Ordner `nvidia/cublas/lib`. Er prüft: Aufruf aus einem fremden Verzeichnis, Aufruf über einen Symlink, `LD_LIBRARY_PATH` bleibt erhalten und wird ergänzt, fehlende venv ergibt Exit 2. Das README nennt das Skript als Alternative zu `source .venv/bin/activate` plus `export`.
- Verify: `scripts/check`; `env -u LD_LIBRARY_PATH scripts/transcript doctor` meldet cuBLAS ok
- AC: `transcript` läuft ohne aktivierte venv und ohne manuelles `LD_LIBRARY_PATH`, auch über einen Symlink.

### Chunk 3 — Ablauf-Doku `docs/ablauf.md`
- Dateien: `docs/ablauf.md` (neu)
- Änderung: in dieser Reihenfolge:
  1. Umfang V0.1: lokal, kein Alttranskript, kein Alignment, keine Cloud-ASR.
  2. Voraussetzungen und Setup inkl. Modelle, Narrata-Token und Startskript.
  3. Session anlegen und Audio nach `input/<gruppe>/<NNN>/` legen.
  4. Konfiguration (ASR-Modell/-Gerät, `narrata.*`).
  5. Domänenwissen: der erste Lauf holt Kontext und Snapshot. Aktualisieren über `--redo context` bzw. `--redo snapshot`, mit Folgen für die ASR. Offline über `context --from-file`.
  6. Preflight `doctor`.
  7. `process`, erster Lauf bis zum Halt (Exit 3).
  8. Manuelle Schritte: `review.csv` ausfüllen inkl. Abspielen über `segment_start`; Sprecher mit `speakers --assign`.
  9. Zweiter `process`-Lauf, Exit-Codes 0/1/2/3.
  10. `status`, `pipeline.log`, Abbruch und Resume, `process.lock`, strenger Guard.
  11. Ergebnis: `output/…` mit JSON, TXT, DOCX, Bericht; Import in Narrata.
  12. Artefakt-Tabelle `work/` und `output/`.
  13. Troubleshooting: fehlendes `LD_LIBRARY_PATH` bzw. venv; alte Handdateien vor `--redo transcribe` beiseitelegen; neue Kandidaten nach importiertem Sheet (`review-export --all --force`, `TOOL-55-e2e-cli.md:86`); Guard verweigert den Start; WSL-RAM (`.wslconfig`); abgelaufenes Narrata-Token (24 h); Netz/IPv6 zu Narrata unter WSL.
  14. Bekannte Grenzen: kein Review-Dialog, rund 25 h Review pro Abend bei vollständigem Review, Entscheidung in TOOL-60.

  Jede Aussage wird vor dem Schreiben gegen Code und `--help` geprüft. Für Details verlinkt die Doku auf die README-Anker.
- Verify: `scripts/check`. Jeder Befehl und jede Option in `docs/ablauf.md` gegen `transcript <cmd> --help` abgleichen. `scripts/transcript status <echte Session>` lokal mit der Beschreibung vergleichen, nur in der Konsole. Grep auf echte Gruppennamen im Diff ist leer.
- AC: Alle Akzeptanzkriterien des Tickets: Reihenfolge, alle Befehle, wann manuell, Resume, Snapshot, Artefakte, keine privaten Inhalte, am Pilot geprüft, weder Alttranskript noch Cloud.

### Chunk 4 — README nachziehen
- Dateien: `README.md`
- Änderung: Stand `README.md:5` aktualisieren und auf `docs/ablauf.md` verweisen. `README.md:789` korrigieren (`NARRATA_TOKEN` in `.env`, nie committen). Verzeichnisbaum `README.md:762-775` ergänzen. „Nächste Schritte“ (`README.md:793`) prüfen. `scripts/transcript` in der Verzeichnisstruktur nennen.
- Verify: `scripts/check`; die Anker-Links aus `docs/ablauf.md` aufs README lösen auf (grep auf Überschriften)
- AC: Im README steht keine veraltete Stand- oder Secret-Aussage mehr, und der Baum entspricht `SessionPaths`.

## Folge-Tickets
- Review-Dialog mit Abspielen nach dem Vorbild von `speakers --assign` [kein Ticket: hängt an der Review-Kanal-Entscheidung in TOOL-60, dort schon vermerkt]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | cuDNN aus pyproject und README | no |
| 2 | Startskript `scripts/transcript` + Test | no |
| 3 | Ablauf-Doku `docs/ablauf.md` | no |
| 4 | README nachziehen | no |
