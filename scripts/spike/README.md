# ASR-Spike (TOOL-62)

Wegwerf-Werkzeug für den Vergleich lokaler ASR-Modelle. Kein Pipeline-Code: Die Skripte gehören nicht zum Paket `transcript`, und ihre Abhängigkeiten stehen nicht in `pyproject.toml`. Mit `TOOL-64` wird das Verzeichnis abgelöst. Plan: [`docs/plans/TOOL-62-asr-spike.md`](../../docs/plans/TOOL-62-asr-spike.md).

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
