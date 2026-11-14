# Entrauschen-Spike (TOOL-92)

Wegwerf-Werkzeug für die Frage, ob ein lokaler Rauschfilter vor Spracherkennung und Diarisierung bessere Ergebnisse liefert. Kein Pipeline-Code: Das Skript gehört nicht zum Paket `transcript`, und Werkzeug und Modell stehen nicht in `pyproject.toml`. Plan: [`TOOL-92`](../../docs/plans/TOOL-92-denoise-spike.md), Bericht: [`docs/spikes/TOOL-92-entrauschen.md`](../../docs/spikes/TOOL-92-entrauschen.md).

## Datenschutz

- Gefiltertes Audio, Läufe und Kopien von Manifest und Snapshot liegen nur unter `work/<gruppe>/<ordinal>/experiments/denoise/`.
- Die Konsole bekommt nur Zähler, Anteile und Laufzeiten, nie Transkripttext, Namen oder Sprecher-Labels.
- Alle Filter laufen lokal. Heruntergeladen werden nur das Werkzeug und das Modell, einmal.

## Einrichtung

```bash
D=~/.cache/narrata-spike/denoise; mkdir -p $D
curl -fsSL -o $D/lq.rnnn https://raw.githubusercontent.com/GregorR/rnnoise-models/master/leavened-quisling-2018-08-31/lq.rnnn
curl -fsSL -o $D/deep-filter https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl
chmod +x $D/deep-filter
```

- `lq.rnnn` (RNNoise für ffmpeg `arnndn`): erwartet Stimme samt Lachen unter allgemeinem Störgeräusch. Laut README des Modell-Repos sind die Modelle nicht urheberrechtlich geschützt.
- `deep-filter` (DeepFilterNet 3, MIT/Apache-2.0): ein statisches Binary, läuft auf der CPU und braucht kein Python.

## Ablauf

Aus dem Projektordner, `S=<gruppe>/<ordinal>`:

```bash
K="base hp hp-afftdn arnndn dfn"
.venv/bin/python scripts/spike/denoise.py prepare $S $K --runs 3
.venv/bin/python scripts/spike/denoise.py run $S $K --runs 3
.venv/bin/python scripts/spike/denoise.py score $S $K --runs 3
```

Whisper liefert auf demselben WAV nicht zweimal dasselbe Ergebnis (Temperatur-Fallback ohne Seed). Jeder Kandidat läuft deshalb mehrfach, jeder Lauf in einer eigenen Wurzel `<kandidat>.run<n>` mit demselben WAV wie Lauf 1. `score` gibt zuerst Mittelwert und Spanne der WER pro Kandidat aus, danach jeden Lauf einzeln.

- **`prepare`** macht aus `work/$S/experiments/denoise/<kandidat>/` eine eigene `paths.root`. Darin liegen Kopien von Manifest, `audio.json` und `narrata/` sowie eine Config, die sich von `config/config.yaml` nur in `paths.root` unterscheidet. Dazu kommt das gefilterte `segment-01.wav` mit genau so vielen Frames, wie das Manifest erwartet. `base` und `base-t0` verlinken das Roh-WAV, Wiederholungsläufe das WAV von Lauf 1. Ein schon gefiltertes WAV mit derselben Kette (`filter.json`) wird wiederverwendet.
- **`run`** ruft `transcript transcribe $S --segment 1 --config <wurzel>/config.yaml` nacheinander für jede Wurzel auf: ASR, Hinweise, Bewertung und Diarisierung, genau wie in der Pipeline. Die Wiederaufnahme der Pipeline gilt pro Wurzel.
- **`score`** gibt Markdown-Tabellen aus:
  - WER an den Handreferenzen A und B aus `review/calibration/` (`calibration.measure`)
  - Wiederholungsanteil und Anteil verschiedener Wörter wie in TOOL-62
  - Passagen je Stufe und markierte Zeit über Segment 1
  - Label-Zahl, Wörter ohne Label, WDER an A wie in TOOL-20 und Übereinstimmung der Labels mit `--baseline`
  - Laufzeit von Filter, ASR und Diarisierung pro Stunde Audio

  Das Skript bricht ab, wenn sich Modell-Revision oder Snapshot zwischen den Wurzeln unterscheiden.

## Kandidaten

| Name | Kette |
| --- | --- |
| `base` | Roh-WAV |
| `base-t0` | Roh-WAV, Whisper mit `temperature=0` (ohne Stichproben-Fallback); nur im Spike, steht in `asr.settings` des Transkripts |
| `hp` | `highpass=f=80` |
| `hp-afftdn` | `highpass=f=80,afftdn=nf=-25` (mittlere Kette aus TOOL-91) |
| `arnndn`, `hp-arnndn` | `aresample=48000,arnndn=m=lq.rnnn`, optional mit Hochpass davor |
| `dfn`, `hp-dfn` | 48 kHz, `deep-filter -D` (Verzögerung ausgeglichen), optional mit Hochpass davor |

Nach jedem Filter folgt `aresample=16000,apad,atrim` auf die Frame-Zahl des Manifests, sonst verweigert die Pipeline das WAV.
