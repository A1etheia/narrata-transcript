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
- **`score`** gibt Markdown-Tabellen aus: Modell, Revision und Snapshot je Variante (Abbruch, wenn sie zwischen den Seeds abweichen), WER-Mittel und Spanne mit Auslassungen, Wortzahl und Wiederholung je Variante, dann jeden Lauf einzeln (E/A/Ei, Auslassungen getrennt nach Füllwörtern aus `FILLERS` und übrigen Wörtern samt WER ohne Füllwörter, Stufen, übersehene Fehler), für diarisierte Wurzeln Labels, WDER und Übereinstimmung mit `--baseline`, zuletzt Laufzeit pro Stunde, RAM und VRAM. Andere Clips gibt `--clip NAME=DATEI@H:MM:SS-H:MM:SS` an (mehrfach), z. B. für Referenz C.
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
| `+de-turbo` | `primeline/whisper-large-v3-turbo-german`, selbst nach CTranslate2 konvertiert (Einrichtung unten); mit `turbo` im Namen bekommt es Hotwords, außer auf `nohw` |
| `+crisper` | `nyralabs/faster_CrisperWhisper` (CrisperWhisper 1.0, Deutsch und Englisch, wortgetreu) |
| `+twin` | ändert nur die Wurzel; prüft, ob ein Seed einen Lauf reproduziert |

## Modelle einrichten

large-v3 kommt wie in der Haupt-README in den HF-Cache. Die beiden anderen Modelle:

```bash
# CrisperWhisper 1.0, schon im CTranslate2-Format (CC-BY-NC-4.0 vom Basismodell)
.venv/bin/python -c "from huggingface_hub import snapshot_download as d; d('nyralabs/faster_CrisperWhisper')"

# Deutsches Turbo-Modell (Apache-2.0): Konvertierung in einer Wegwerf-venv, nicht in .venv
C=~/.cache/narrata-spike/asr; O=$C/whisper-large-v3-turbo-german-ct2-9e7012dad924
python3 -m venv $C/convert-venv
$C/convert-venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch
$C/convert-venv/bin/pip install ctranslate2==4.8.5 transformers
$C/convert-venv/bin/ct2-transformers-converter --model primeline/whisper-large-v3-turbo-german \
  --revision 9e7012dad924 --output_dir $O --copy_files preprocessor_config.json --quantization float16
# das Repo hat kein tokenizer.json, die Pipeline braucht eins
$C/convert-venv/bin/python -c "import sys; from transformers import AutoTokenizer as T; T.from_pretrained('primeline/whisper-large-v3-turbo-german', revision='9e7012dad924').save_pretrained(sys.argv[1])" $O/tok
mv $O/tok/tokenizer.json $O/ && rm -r $O/tok
```

`snapshot_download` ohne feste Revision, damit `refs/main` im Cache steht: Pipeline und faster-whisper suchen das Modell über `main`. Das konvertierte Verzeichnis trägt die Quell-Revision im Namen, `score` zeigt dafür keine Hub-Revision (`n/a`). CrisperWhisper 2.0 (`nyralabs/CrisperWhisper2.0_*`) läuft nur mit eigener Laufzeit `crisperwhisper` und steht unter einer Forschungslizenz ohne Betriebseinsatz; es ist nicht Teil des Spikes.

# Sprecherwechsel-Spike (TOOL-96)

Misst, was das Teilen der Passagen am Sprecherwechsel bringt und welche Mindestschwelle passt. `turns.py` schneidet nur im Speicher mit `transcript.diarization.turns.split_at_speaker_changes` und nutzt Clips und Kennzahlen aus `denoise.py`. Plan: [`TOOL-96`](../../docs/plans/TOOL-96-speaker-turns.md), Bericht: [`docs/spikes/TOOL-96-sprecherwechsel.md`](../../docs/spikes/TOOL-96-sprecherwechsel.md).

## Datenschutz

Das Skript schreibt nichts. Es liest die gespeicherten Transkripte unter `work/<gruppe>/<ordinal>/` und die Handreferenzen A und B aus `review/calibration/`. Die Konsole bekommt Zähler, Anteile und Zeiten, nie Text, Namen oder Sprecher-Labels.

## Ablauf

```bash
.venv/bin/python scripts/spike/turns.py $S [--config PATH]
```

- **Voraussetzung:** Alle Segmente der Sitzung sind transkribiert und diarisiert. Ohne Modell, ohne GPU.
- **Varianten:** die gespeicherten Passagen (ungeteilt), dann Schnitte mit 0, 250, 500, 1000, 1500 und 2000 ms sowie 2, 3 und 4 Wörtern Mindestlänge pro Label-Lauf.
- **Ausgabe:** zwei Markdown-Tabellen.
  - *Sprecherfehler an A und B:* WDER wie in TOOL-20 auf Passagenebene (jedes Wort trägt das Label seiner Passage, wie im Export) und einmal auf Wortebene (Wortlabel der Diarisierung, gleich für alle Schnitte). Dazu der Anteil der Passagen mit Wörtern mehrerer Hand-Sprecher.
  - *Ganze Sitzung:* Passagen gesamt und pro Stunde, Länge P10/Median/P90, gemischte Passagen (mehr als ein Wortlabel), Anteil der Wörter unter fremdem Label, Review-Kandidaten und markierte Zeit, Zahl der Hinweise. Hinweise und Bewertung werden für jede Variante neu berechnet (`segment_hints`, `segment_assessment`), mit den Schwellen der Config.
  - Zuletzt die Zahl der Passagen mit mehr als einem Label, die nicht geteilt werden, weil ihre Wortfolge nicht genau den Text ergibt.

# Auslassungs-Spike (TOOL-101)

Misst, unter welchen Bedingungen Whisper Wörter auslässt. `omissions.py` liest die Läufe von `asr.py` (eine Wurzel je Seed), die Diarisierung der Sitzung und die Handreferenzen. Plan: [`TOOL-101`](../../docs/plans/TOOL-101-omission-location.md), Bericht: [`docs/spikes/TOOL-101-auslassungen-verorten.md`](../../docs/spikes/TOOL-101-auslassungen-verorten.md).

## Datenschutz

Das Skript schreibt nur `work/<gruppe>/<ordinal>/experiments/asr/vad.json`, die Sprachabschnitte der VAD als Zahlen. Die Konsole bekommt Zähler, Anteile, Pegel und Zeiten, nie Text, Namen oder Sprecher-Labels. Sprecher erscheinen als Rang nach Wortzahl.

## Ablauf

```bash
.venv/bin/python scripts/spike/omissions.py $S [--variant base] [--seeds 3] [--clip NAME=DATEI@H:MM:SS-H:MM:SS]… [--config PATH]
```

- **Voraussetzung:** Die Wurzeln `<variante>.seed1..N` sind mit `asr.py run` transkribiert, und Segment 1 der Sitzung selbst ist diarisiert. Ohne GPU. Die VAD rechnet einmal rund 20 s auf der CPU, danach kommt sie aus `vad.json`.
- **Wortzeiten:** Die Ausrichtung ist dieselbe wie in `calibration.measure`, das Skript bricht ab, wenn seine Auslassungen davon abweichen. Ein erkanntes Wort bekommt die Mitte seiner Wortzeit. Eine Folge ausgelassener Wörter wird gleichmäßig zwischen dem Ende des Wortes davor und dem Anfang des Wortes danach verteilt.
- **VAD:** Silero mit den Optionen der Pipeline (`threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`). Das Skript bricht ab, wenn die Summe der Abschnitte mehr als 1 s von `duration_after_vad` eines Laufs abweicht.
- **Ausgabe:** Markdown-Tabellen.
  - *Segment:* von der VAD behaltene Zeit; je Seed die Zeit, in der die Diarisierung Sprache hört und Whisper kein Wort hat (Pausen zwischen Wörtern bis 1 s gelten als gedeckt), und die Stellen ab 2 s.
  - *Je Referenz, Merkmale:* je Klasse die Auslassungen und die Referenzwörter je Seed, ihr Anteil an allen Auslassungen bzw. Referenzwörtern als Mittel und Spanne und die Auslassungen je Wort der Klasse.
  - *Je Referenz, Sprecher:* Wörter, Auslassungen und der Pegel (RMS über die Turns des zugeordneten Labels im Clip) relativ zum lautesten Sprecher, dazu der Pegel außerhalb aller Turns.
  - *Je Referenz, Stabilität:* wie viele Referenzwörter in 3, 2 oder 1 der Seeds fehlen.
  - *Je Referenz, Verortung:* Zahl und Breite der Lücken, in die Auslassungen gelegt wurden, und der Anteil der Clip-Zeit mit Sprache ohne Wörter.

## Merkmale

| Merkmal | Regel |
| --- | --- |
| Überlappung | Wortzeit in einem Bereich, in dem sich zwei Turns überlappen |
| Beitragslänge (Diarisierung) | exklusiver Turn an der Wortzeit, gleiche Labels mit höchstens 500 ms Abstand verbunden: unter 2 s, 2–10 s, über 10 s |
| Beitrag laut Handreferenz | Wörter in Folge vom selben Sprecher: 1–3, 4–10, über 10 |
| Pegel des Beitrags | RMS des Turns mindestens 6 dB unter dem lautesten Sprecher des Clips |
| Fallback-Fenster | 30-s-Fenster des Laufs an der Wortzeit mit `temperature > 0` |
| dünnes Fenster | Fenster mit weniger als 0,5 Wörtern pro Sekunde (TOOL-81) |
| von der VAD entfernt | Wortzeit außerhalb aller Sprachabschnitte |
| Sprache ohne Wörter | Wortzeit in einer Stelle ab 1 s, an der ein Turn läuft und Whisper kein Wort hat |
| erklärt | Überlappung, Beitrag unter 2 s, leiser Beitrag oder Fallback-Fenster |
