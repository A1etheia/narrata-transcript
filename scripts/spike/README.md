# ASR- und Diarisierungs-Spike (TOOL-62, TOOL-20)

Wegwerf-Werkzeug für den Vergleich lokaler ASR-Modelle (TOOL-62) und lokaler Diarisierung (TOOL-20, [Abschnitt unten](#diarisierung-tool-20)). Kein Pipeline-Code: Die Skripte gehören nicht zum Paket `transcript`, und ihre Abhängigkeiten stehen nicht in `pyproject.toml`. Mit `TOOL-64` wird das Verzeichnis abgelöst. Pläne: [`TOOL-62`](../../docs/plans/TOOL-62-asr-spike.md), [`TOOL-20`](../../docs/plans/TOOL-20-diarisierung.md).

## Datenschutz

- Audio, Läufe, Referenz und Begriffsliste liegen nur unter `work/<gruppe>/<ordinal>/spike/`.
- Die Skripte geben auf der Konsole nur Zähler und Laufzeiten aus, nie Transkripttext. `compare.py` liefert nur Kennzahlen.
- Modelle einmal herunterladen, danach jeden Lauf mit `HF_HUB_OFFLINE=1`. `run.json` vermerkt das im Feld `offline`.
- Der GPU-Speicher wird für die ganze Karte gemessen. Andere Programme auf der GPU verfälschen den Wert.

## Einrichtung

Voraussetzung: `ffmpeg` und eine NVIDIA-GPU mit CUDA. Jeder Kandidat bekommt eine eigene venv, weil sich die Runtimes beißen:

```bash
B=~/.cache/narrata-spike
python3 -m venv $B/whisper  && $B/whisper/bin/pip install faster-whisper nvidia-cublas-cu12 "nvidia-cudnn-cu12<9"
python3 -m venv $B/parakeet && $B/parakeet/bin/pip install "nemo_toolkit[asr]"
python3 -m venv $B/granite  && $B/granite/bin/pip install torch torchaudio "transformers>=5.8" peft soundfile accelerate torchcodec
```

faster-whisper findet die CUDA-Bibliotheken aus den pip-Paketen nur über `LD_LIBRARY_PATH`:

```bash
export LD_LIBRARY_PATH=$(echo $B/whisper/lib/python3.10/site-packages/nvidia/{cublas,cudnn}/lib | tr ' ' ':')
```

## Ablauf

Aus dem Verzeichnis `scripts/spike/`, mit `W=../../work/<gruppe>/<ordinal>/spike`:

```bash
./cut.sh <aufnahme> $W/excerpt.wav 4800 1500       # 16 kHz mono, ab Sekunde 4800, 25 Minuten
HF_HUB_OFFLINE=1 $B/whisper/bin/python run_whisper.py $W/excerpt.wav --out $W/runs --model large-v3-turbo
HF_HUB_OFFLINE=1 $B/parakeet/bin/python run_parakeet.py $W/excerpt.wav --out $W/runs --model nvidia/parakeet-tdt-0.6b-v3
HF_HUB_OFFLINE=1 $B/granite/bin/python run_granite.py $W/excerpt.wav --out $W/runs --model ibm-granite/granite-speech-4.1-2b-plus
python3 compare.py $W/reference.txt $W/runs/*/run.json --names $W/names.txt --start <s> --end <s>
```

Jeder Lauf landet in einem eigenen Verzeichnis `<zeitstempel>-<kandidat>/run.json` und wird nie überschrieben. `--keywords <datei>` gibt Whisper und Granite eine Begriffsliste mit, einen Begriff pro Zeile. Parakeet hat kein dokumentiertes Biasing und bricht dann ab. Parakeet und Granite nehmen `--block-seconds`, Granite zusätzlich `--repetition-penalty`; die Werte stehen in `run.json` unter `settings`.

`compare.py` vergleicht nur den Bereich der Handreferenz (`--start`/`--end` in Sekunden). Die WER beruht auf einer `difflib`-Ausrichtung und liegt nahe an der minimalen WER, ohne sie exakt zu treffen. Die Namensquote zählt jeden Begriff aus `names.txt`, auch mehrteilige, höchstens so oft, wie er in der Referenz vorkommt.

## Einstellungen und ihre Gründe

| Kandidat | Einstellung | Grund |
| --- | --- | --- |
| Whisper | `vad_filter`, `word_timestamps`, `beam_size 5`, ohne `condition_on_previous_text` | VAD für lange Aufnahmen, kein Mitschleppen von Fehlern über Segmente |
| Whisper | `hotwords` aus `--keywords` | Abgeschnitten nach `max_length // 2 - 1` = 223 Tokens. Was hinten in der Liste steht, fällt weg |
| Parakeet | Local Attention `[256, 256]`, Blöcke à 300 s | Am Stück bricht der Encoder schon bei 26 Minuten mit `CUDA driver error: device not ready` ab; Conv-Chunking hilft nicht |
| Granite | Blöcke à 90 s, `repetition_penalty` 1,2 | 2,0 laut Modellkarte liefert Unsinn ohne Wiederholungen, 1,0 läuft auch in 90-s-Blöcken in Schleifen |

Blöcke überlappen nicht und können ein Wort an der Grenze zerschneiden. Granite liefert im reinen ASR-Modus weder Wortzeiten noch Confidence, und die Plus-Variante setzt keine Satzzeichen. Parakeet schreibt jeden Block kurz als Datei in ein temporäres Verzeichnis unter `--out`, damit auch diese Kopien unter `work/` bleiben.

## Diarisierung (TOOL-20)

Zwei Runner schreiben pro Lauf `<zeitstempel>-<kandidat>/diar.json` mit `meta` und `turns` (`start`, `end`, `label`). Labels sind die generischen Labels des Backends, nie Namen. pyannote schreibt zusätzlich `exclusive_turns`, in denen immer nur eine Person spricht; diese nutzt die Auswertung für die Zuordnung zu Wörtern. `--num-speakers <n>` gibt die bekannte Personenzahl vor.

| Kandidat | venv | Modell | Einrichtung |
| --- | --- | --- | --- |
| pyannote.audio 4 | `$B/pyannote` | `pyannote/speaker-diarization-community-1` (CC-BY-4.0, gated) | `pip install pyannote.audio`; Bedingungen auf Hugging Face akzeptieren, einmal mit Token herunterladen |
| NeMo-Clustering-Diarizer | `$B/parakeet` | `titanet_large` (CC-BY-4.0) + `vad_multilingual_marblenet` | keine; erster Lauf lädt beide Modelle von NGC |

```bash
python3 -m venv $B/pyannote && $B/pyannote/bin/pip install pyannote.audio
$B/pyannote/bin/python -c "from huggingface_hub import snapshot_download as s; s('pyannote/speaker-diarization-community-1')"
HF_HUB_OFFLINE=1 $B/pyannote/bin/python run_pyannote.py $W/excerpt.wav --out $W/diar-excerpt --model pyannote/speaker-diarization-community-1 [--num-speakers <n>]
HF_HUB_OFFLINE=1 $B/parakeet/bin/python run_nemo_diar.py $W/excerpt.wav --out $W/diar-excerpt --model titanet_large [--num-speakers <n>]
```

Der Token liegt im lokalen Hugging-Face-Cache (`hf auth login`), nie im Repo. Der NeMo-Runner legt VAD-Ausgaben und Embeddings in ein temporäres Verzeichnis unter `--out` und löscht es danach.

### Auswertung mit `speakers.py`

Nur Standardbibliothek, gibt nur Kennzahlen aus. Sprecherkennungen der Referenz erscheinen als `S1`, `S2`, … in der Reihenfolge ihres ersten Auftretens.

```bash
python3 speakers.py reference $W/reference.txt <whisper-run.json> $W/diar-excerpt/*/diar.json --start <s> --end <s>
python3 speakers.py stats $W/diar-full/*/diar.json
python3 speakers.py sample <whisper-run-voll.json> --out $W/speaker-sample.csv
python3 speakers.py score-sample $W/speaker-sample.csv $W/diar-full/*/diar.json
```

- **`reference`:** Die Handreferenz hat keine Zeiten. Ihre Wörter werden an die Whisper-Wörter ausgerichtet und übernehmen deren Zeit; gewertet werden nur exakt getroffene Wörter. Jedes Wort bekommt das Label, in dessen Turn seine Mitte liegt. Ausgabe: WDER nach bester 1:1-Zuordnung von Labels zu Sprechern, Anteil ohne Label, gefundene und zusätzliche Sprecherwechsel (Toleranz ±0,5 s), Overlap-Anteil.
- **`stats`:** Anzahl Labels, Sprechanteil pro Label, Turns, Median-Turnlänge, Sprach- und Overlap-Anteil, aktive Labels (mindestens 30 s) pro Stunde.
- **`sample`:** Zieht pro 10-Minuten-Fenster ein Whisper-Segment von 2–10 s, unabhängig von beiden Diarisierern. Die CSV enthält nur Zeiten und überschreibt nie eine vorhandene Datei.
- **`score-sample`:** Jedes Segment bekommt das Label mit dem größten Overlap, jedes Label die Person, die es in der Stichprobe am häufigsten trägt. Ausgabe: Fehlzuordnungen, Labels pro Person und abgespaltene NSC-Stimmen.

Ausfüllen der Stichprobe: Segment bei `at` anhören und eintragen.

| Spalte | Inhalt |
| --- | --- |
| `person` | `SL` für die Spielleitung, `P1`, `P2`, … für Mitspielende. Keine Klarnamen; andere Einträge erscheinen nur als `Person <n>` |
| `nsc` | `x`, wenn die Spielleitung mit verstellter Stimme spricht |
| `mixed` | `x`, wenn mehrere Personen sprechen oder die Person nicht erkennbar ist; die Zeile zählt dann nicht |
| `note` | frei, bleibt lokal |

Die Datei darf mit Komma oder Semikolon gespeichert sein.
