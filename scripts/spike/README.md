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
- **Wortzeiten:** Die Ausrichtung ist dieselbe wie in `calibration.measure`, das Skript bricht ab, wenn seine Auslassungen davon abweichen. Jedes Referenzwort bekommt eine Zeit, die für alle Seeds gilt: den Median der Zeiten aus den Seeds, die es erkannt haben (Wortanfang plus halbe Wortlänge, die Länge auf 1 s begrenzt). Nur Wörter, die in allen Seeds fehlen, werden gleichmäßig zwischen ihren Nachbarn verteilt. Die Zeit der Nachbarwörter im selben Lauf taugt dafür nicht: Whisper dehnt das Wort vor übersprungener Sprache über die Lücke.
- **VAD:** Silero mit den Optionen der Pipeline (`threshold 0.5`, `min_silence_duration_ms 2000`, `speech_pad_ms 400`). Das Skript bricht ab, wenn die Summe der Abschnitte mehr als 1 s von `duration_after_vad` eines Laufs abweicht.
- **Ausgabe:** Markdown-Tabellen.
  - *Segment:* von der VAD behaltene Zeit; je Seed die Zeit, in der die Diarisierung Sprache hört und Whisper kein Wort hat (Pausen zwischen Wörtern bis 1 s gelten als gedeckt), und die Stellen ab 2 s.
  - *Je Referenz, Merkmale:* je Klasse die Auslassungen und die Referenzwörter je Seed, ihr Anteil an allen Auslassungen bzw. Referenzwörtern als Mittel und Spanne und die Auslassungen je Wort der Klasse.
  - *Je Referenz, Sprecher:* Wörter, Auslassungen und der Pegel (RMS über die Turns des zugeordneten Labels im Clip) relativ zum lautesten Sprecher, dazu der Pegel außerhalb aller Turns.
  - *Je Referenz, Stabilität:* wie viele Referenzwörter in 3, 2 oder 1 der Seeds fehlen.
  - *Je Referenz, Verortung:* je Seed die Folgen von Auslassungen, die längste Folge und der Anteil der Clip-Zeit mit Sprache ohne Wörter; dazu, wie viele Wörter kein Seed erkannt hat und wie weit die Wortzeiten der Seeds auseinanderliegen.

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

# Seed-Spike (TOOL-102)

Misst, was ein zweiter und dritter Whisper-Lauf mit anderem Seed an ausgelassenen Wörtern zurückbringt. `seeds.py` liest die Läufe von `asr.py` (eine Wurzel je Seed) und die Handreferenzen. Plan: [`TOOL-102`](../../docs/plans/TOOL-102-seed-union.md), Bericht: [`docs/spikes/TOOL-102-seed-vereinigung.md`](../../docs/spikes/TOOL-102-seed-vereinigung.md).

## Datenschutz

Das Skript schreibt nichts. Die Konsole bekommt Zähler, Anteile, Fehlerraten und Zeiten, nie Text, Tokens, Namen oder Sprecher-Labels.

## Ablauf

```bash
.venv/bin/python scripts/spike/seeds.py $S [--variant base] [--seeds 3] [--clip NAME=DATEI@H:MM:SS-H:MM:SS]… [--suggest] [--config PATH]
```

- **Voraussetzung:** Die Wurzeln `<variante>.seed1..N` sind mit `asr.py run` transkribiert. Ohne Modell, ohne GPU, wenige Sekunden.
- **Segmentvergleich, ohne Handreferenz:** Die Tokenfolgen der Seeds werden paarweise ausgerichtet, abschnittsweise je 5 Minuten. Ein Wort zählt dort, wo es beginnt.
  - *Wörter und Wiederholungsanteil* je Seed.
  - *Je Seed-Paar und Richtung:* Wörter, die an derselben Stelle anders lauten; Wörter, die dem einen Seed fehlen und im anderen stehen; Blöcke ab 20 Wörtern in Folge.
  - *Stellen mit Blockverlust* je Seed, zeitlich zusammengefasst, und wie viele davon gegen alle anderen Seeds bestehen. Fehlt ein Block nur gegen einen Seed, kann auch dieser Seed etwas erfunden haben.
  - *Raster:* Anteil der 30-s-Fenster, in denen ein Seed-Paar um mindestens 5 Wörter abweicht.
- **`--suggest`** schlägt drei sich nicht überlappende 3-min-Fenster mit der größten Abweichung für eine neue Handreferenz vor, außerhalb der angegebenen Clips. Ausgegeben werden nur Zeiten und Zähler.
- **Orakel je Referenz**, jeder Seed einmal als Basis:
  - *Rückgewinn:* Für jede Auslassung der Basis, ob ein anderer Seed das Wort richtig hat, nur als Ersetzung, oder ob es in allen fehlt. Die WER des Orakels setzt nur die richtigen Wörter ein und nichts Falsches.
  - *Naive Vereinigung:* Die anderen Läufe werden gegen die Basis ausgerichtet. Was sie an einer Stelle mehr haben, kommt dazu, und die vereinigte Folge wird mit `calibration.align` gegen die Handreferenz gemessen. Die Tabelle zeigt, wie viele Auslassungen wegfallen und wie viele Einfügungen und Ersetzungen dazukommen.
  - Der Gewinn steht in Punkten WER gegenüber der Basis, negativ heißt schlechter.
- **Regeln ohne Referenz**, über das Segment und je Referenz. Sie nutzen die Ausrichtung aus dem Segmentvergleich, die Handreferenz dient nur zum Nachzählen. Keine Regel schreibt ein Transkript.
  - *R1, Fensterwahl:* Je 30-s-Fenster gewinnt der Lauf mit den meisten Wörtern, bei Gleichstand der niedrigste Seed. Ein Lauf scheidet in einem Fenster aus, wenn dort eine Passage die `compression_ratio`-Schwelle aus `review.uncertainty` erreicht oder der Wiederholungsanteil seiner Wörter im Fenster über 0 liegt. Scheiden alle aus, bleiben alle. Ausgegeben werden die WER gegen die Seeds und über das Segment Wortzahl, Wiederholungsanteil, Passagen je Stufe und markierte Zeit. Die Zeilen der Seeds laufen durch dieselbe Rechnung wie R1.
  - *R2, Alternative an der Lücke:* Die Basis bleibt. Was ein anderer Seed an einer Stelle mehr hat, gilt als Alternative. Gezählt wird, wie viele Auslassungen der Basis ein richtiges Wort bekommen, wie viele Alternativ-Wörter falsch sind und wie viel Zeit die Stellen einnehmen. Bieten zwei Seeds dasselbe Wort an, zählt es bei den Alternativ-Wörtern doppelt und bei den Auslassungen einmal. Drei Zeilen je Basis: jede Alternative, nur Blöcke ab 20 Wörtern, nur Blöcke, die jeder andere Seed an der Stelle anbietet.
  - *R3, Abweichung als Review-Hinweis:* Eine `confident`-Passage der Basis bekommt einen Hinweis, wenn ein anderer Seed dort um mindestens 1, 2 oder 3 Wörter abweicht. Gezählt wird wie in TOOL-35: Fehler und Auslassungen in `confident`-Passagen, wie viele davon in Passagen mit Hinweis liegen, Passagen mit Hinweis ohne Fehler und die zusätzlich markierte Zeit.
  - *Markierte Zeit* ist hier die Zeit der Passagen, die nicht `confident` sind, geteilt durch die Zeit aller Passagen. Überlappende Passagen zählen einmal.

# Pegel-Spike (TOOL-103)

Misst, ob ein Ausgleich der Lautstärke vor der Erkennung die Auslassungen verringert. Die Kandidaten sind Basen in `asr.py`, mit allen Hotwords wie `base`. `denoise.py` bleibt unverändert und liefert Kette und Filter. Plan: [`TOOL-103`](../../docs/plans/TOOL-103-level-normalization.md), Bericht: [`docs/spikes/TOOL-103-pegelausgleich.md`](../../docs/spikes/TOOL-103-pegelausgleich.md).

## Datenschutz

Wie beim ASR-Spike: Gefiltertes Audio und Wurzeln liegen nur unter `work/<gruppe>/<ordinal>/experiments/asr/`. Die Konsole bekommt Zähler, Anteile, Pegel und Zeiten, nie Text, Namen oder Sprecher-Labels. Alle Filter sind lokales ffmpeg.

## Ablauf

```bash
K="dyn dynx comp loud spn"
.venv/bin/python scripts/spike/asr.py prepare $S $K --seeds 3
.venv/bin/python scripts/spike/asr.py run $S $K --seeds 3
.venv/bin/python scripts/spike/asr.py score $S base $K --seeds 3 [--clip NAME=DATEI@H:MM:SS-H:MM:SS]…
.venv/bin/python scripts/spike/omissions.py $S --variant dyn [--clip …]
```

- **`prepare`** filtert einmal je Kette nach `experiments/asr/audio/<kette>/` und schreibt dort `filter.json`:
  - *Versatz:* die Hüllkurve gegen das Roh-WAV an drei Stellen (10 %, 50 %, 90 % des Segments, je 60 s, Auflösung 5 ms). Über 10 ms bricht `prepare` ab, weil Wortzeiten und Diarisierung sonst nicht mehr passen.
  - *Verstärkung:* je Sekunde an denselben Stellen, Median, P10 und P90 in dB. Ein Ausgleich zeigt sich als breite Spanne, eine feste Verstärkung als keine.
  - *Vollausschlag:* Anteil der Samples am Anschlag über die ganze Datei.
- **`loud`** läuft zweistufig: Ein erster Durchgang misst, der zweite bekommt die Messwerte (`measured_*`, `offset`, `linear=true`). Sie stehen unter `loudnorm` in `filter.json`, dazu `linear_expected`: ob ffmpeg nach seiner Regel mit fester Verstärkung normalisiert oder dynamisch regelt.
- **`omissions.py --variant`** rechnet für eine gefilterte Variante VAD und Pegel auf dem gefilterten WAV. Die VAD liegt als `vad.json` neben dem WAV. Die Diarisierung bleibt die der Sitzung.

## Kandidaten

| Name | Kette |
| --- | --- |
| `dyn` | `dynaudnorm=f=500:g=31:m=5` (mild) |
| `dynx` | `dynaudnorm=f=200:g=11:m=30` (stark) |
| `comp` | `acompressor=threshold=0.05:ratio=4:attack=5:release=200:makeup=4,alimiter=limit=0.95:level=false` |
| `loud` | `loudnorm=I=-16:TP=-1.5:LRA=11`, zweistufig |
| `spn` | `speechnorm=e=12.5:r=0.0001:l=1` |
| `gain` | `volume=12dB,alimiter=limit=0.95:level=false` (Kontrolle: feste Verstärkung, der Limiter fängt nur die Spitzen) |
| `<name>-hp` | `highpass=f=80` vor der Kette |

# Batched-Spike (TOOL-104)

Misst, ob die `BatchedInferencePipeline` von faster-whisper weniger Wörter auslässt als die fortlaufende Dekodierung der Pipeline. Sie ist ein Modifikator in `asr.py`, kein eigenes Skript. Plan: [`TOOL-104`](../../docs/plans/TOOL-104-asr-research.md), Bericht: [`docs/spikes/TOOL-104-recherche-auslassungen.md`](../../docs/spikes/TOOL-104-recherche-auslassungen.md).

## Datenschutz

Wie beim ASR-Spike: Wurzeln und Zwischenspeicher liegen nur unter `work/<gruppe>/<ordinal>/experiments/asr/`. Die Konsole bekommt Zähler, Anteile und Zeiten, nie Text, Namen oder Sprecher-Labels. `--suggest` gibt nur Fenstergrenzen und Zähler aus.

## Ablauf

```bash
V="base+batched base+batched+ts loud+batched"
.venv/bin/python scripts/spike/asr.py prepare $S $V --seeds 3
.venv/bin/python scripts/spike/asr.py run $S $V --seeds 3
.venv/bin/python scripts/spike/asr.py score $S base base+temp0 loud $V --seeds 3 [--clip NAME=DATEI@H:MM:SS-H:MM:SS]…
.venv/bin/python scripts/spike/omissions.py $S --variant base+batched [--clip …]
.venv/bin/python scripts/spike/omissions.py $S --suggest [--clip …]
```

- **`+batched`** legt im Wrapper für die Dauer von `transcribe` einen Stellvertreter um das geladene Modell, der an `BatchedInferencePipeline(model).transcribe` weiterreicht. Hotwords, Wortzeiten und alle übrigen Settings gehen unverändert durch. `batch_size` (8) und `without_timestamps` stehen wie jeder Modifikator in `asr.settings`, so greift die Wiederaufnahme pro Wurzel.
- **Was die Batched-Pipeline anders macht** (faster-whisper 1.2.1):
  - Sie schneidet das Audio an den Sprachabschnitten der VAD in Stücke von höchstens 30 s und dekodiert jedes für sich.
  - Ohne `vad_parameters` schneidet ihre VAD schon ab 160 ms Stille, die Pipeline erst ab 2000 ms.
  - Sie dekodiert nur mit der ersten Temperatur, also ohne Fallback. Die Schwellen für `log_prob`, `no_speech` und Kompression wirken nicht. Ohne Stichproben sollte der Seed nichts ändern; der Bericht nennt, ob das an den Läufen stimmt.
  - Sie setzt `without_timestamps`: ein Segment je Stück. Wortzeiten kommen trotzdem aus der Ausrichtung.
- **`+ts`** schaltet `without_timestamps` ab und gilt nur zusammen mit `+batched`.
- **`omissions.py --variant <…+batched>`** rechnet die VAD mit den Optionen der Batched-Pipeline und legt sie als `vad-batched.json` ab. Die Merkmale „Fallback-Fenster“ und „dünnes Fenster“ gibt es für solche Läufe nicht, ihre Klasse heißt „entfällt“. „Erklärt“ zählt dort nur Überlappung, kurze und leise Beiträge.
- **`seeds.py $S --with base+batched [--clip …]`** misst nur das Orakel über zwei Varianten, ohne Segmentvergleich und Regeln; `--suggest` ist dort ein Fehler. Je Referenz, in beiden Richtungen und für jedes Paar aus einem Lauf je Variante:
  - wie viele Auslassungen des Hauptlaufs der zweite Lauf richtig hat, wie viele davon in Folgen ab 5 Referenzwörtern liegen, wie viele er nur als Ersetzung hat und wie viele auch dort fehlen;
  - die WER des Orakels und der naiven Vereinigung, mit dem Gewinn in Punkten gegenüber dem Hauptlauf.
  - Ein Paar mit denselben Wörtern wie ein früheres wird ausgelassen.
- **`omissions.py --suggest`** schlägt drei sich nicht überlappende 3-min-Fenster für eine Handreferenz an unruhigen Stellen vor. Es liest nur die Diarisierung von Segment 1.
  - Raster 1 min, außerhalb der angegebenen Clips, mindestens mediane Sprachzeit.
  - Rang: Summe der Ränge nach Überlappungszeit und nach Zahl der Turns unter 2 s (gleiche Labels mit höchstens 500 ms Abstand verbunden).
  - Ausgabe: Fenster, Überlappung in Sekunden, kurze Turns, Anteil Sprache, Zahl der Labels.
