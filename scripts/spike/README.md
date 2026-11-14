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

# ASR-Spike (TOOL-93)

Misst, welche lokalen Whisper-Einstellungen und Modelle die WER an den Handreferenzen senken. `asr.py` nutzt Kette, Filter und Kennzahlen aus `denoise.py`, das selbst unverändert bleibt. Plan: [`TOOL-93`](../../docs/plans/TOOL-93-asr-quality.md), Bericht: [`docs/spikes/TOOL-93-erkennungsqualitaet.md`](../../docs/spikes/TOOL-93-erkennungsqualitaet.md).

## Datenschutz

Wie oben: Wurzeln, Audio und Snapshots liegen nur unter `work/<gruppe>/<ordinal>/experiments/asr/`. Die Konsole bekommt Zähler, Anteile, Zeiten und Fenstergrenzen, nie Text, Namen oder Sprecher-Labels.

## Ablauf

```bash
V="base pchw nohw nohw-hp"
.venv/bin/python scripts/spike/asr.py prepare $S $V --seeds 3
.venv/bin/python scripts/spike/asr.py run $S $V --seeds 3
.venv/bin/python scripts/spike/asr.py score $S $V --seeds 3
```

- **Varianten** heißen `<basis>[+<modifikator>…]`, z. B. `nohw+vad-t35+beam10`. Jede Kombination ist erlaubt, jeder Modifikator höchstens einmal.
- **`prepare`** legt pro Variante und Seed die Wurzel `work/$S/experiments/asr/<variante>.seed<n>/` an: Kopien von Manifest, `audio.json` und `narrata/`, eine Config mit eigener `paths.root` und `asr.model` (bei `beam10` auch `asr.beam_size`) und einen Hardlink auf das WAV. Gefiltertes Audio entsteht einmal pro Kette unter `experiments/asr/audio/<kette>/`. `pchw` setzt jedes Budget in `knowledge.keyword_budget` auf 0 und baut den Snapshot der Wurzel neu, damit nur `pc`-Einträge Hotwords werden.
- **`run`** ruft `transcript transcribe $S --segment 1 --no-diarize` je Wurzel nacheinander auf, mit `--diarize` samt Diarisierung. Ein Wrapper setzt `ctranslate2.set_random_seed(<n>)` vor jeder Transkription, schaltet bei `nohw*` die Hotwords ab und ergänzt die Whisper-Settings. `seed` und `hotwords` stehen mit den Overrides in `asr.settings`, so greift die Wiederaufnahme der Pipeline pro Wurzel. Wall-Zeit, Peak-RAM (`os.wait4` auf den Kindprozess) und Peak-VRAM (`nvidia-smi` im Sekundentakt, ganze GPU, dazu der Stand davor) landen in `<wurzel>/run.json`, aber nur, wenn wirklich neu gerechnet wurde.
- **`score`** gibt Markdown-Tabellen aus: Modell, Revision und Snapshot je Variante (Abbruch, wenn sie zwischen den Seeds abweichen), WER-Mittel und Spanne mit Auslassungen, Wortzahl und Wiederholung je Variante, dann jeden Lauf einzeln (E/A/Ei, Stufen, übersehene Fehler), für diarisierte Wurzeln Labels, WDER und Übereinstimmung mit `--baseline`, zuletzt Laufzeit pro Stunde, RAM und VRAM. Andere Clips gibt `--clip NAME=DATEI@H:MM:SS-H:MM:SS` an (mehrfach), z. B. für Referenz C.
- **`windows $S <variante> [--seed n]`** schlägt drei sich nicht überlappende 3-min-Fenster für eine neue Handreferenz vor: mindestens mediane Wortdichte, 2–4 Sprecher mit je 10 Wörtern, möglichst wenig markierte Passagen und Wörter ohne Label. Braucht eine diarisierte Wurzel.

## Varianten

| Name | Wirkung |
| --- | --- |
| `base` | wie die Pipeline: large-v3-turbo, alle Hotwords |
| `pchw` | nur `pc`-Einträge als Hotwords |
| `nohw` | keine Hotwords |
| `nohw-hp` | keine Hotwords, `highpass=f=80` |
| `+novad` | `vad_filter: false` |
| `+vad-t35`, `+vad-pad800`, `+vad-sil500` | `vad_parameters` mit `threshold 0.35`, `speech_pad_ms 800` bzw. `min_silence_duration_ms 500`; kombinierbar |
| `+beam10` | `asr.beam_size: 10` |
| `+nospeech-off` | `no_speech_threshold: null` |
| `+logprob-lax` | `log_prob_threshold: -1.5` |
| `+cond-prev` | `condition_on_previous_text: true` |
| `+large-v3` | Modell large-v3 statt large-v3-turbo |
| `+twin` | ändert nur die Wurzel; prüft, ob ein Seed einen Lauf reproduziert |
