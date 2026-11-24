# TOOL-104 — Recherche: Batched-Pipeline, neue lokale Modelle und sprecherbedingte Erkennung gegen Auslassungen

Stand 2026-11-23. Bericht zu [TOOL-104](../plans/TOOL-104-asr-research.md), Werkzeug: [`scripts/spike/asr.py`](../../scripts/spike/asr.py) und [`scripts/spike/omissions.py`](../../scripts/spike/omissions.py). Alle Messungen liefen lokal. Der Bericht enthält nur Kennzahlen und öffentliche Quellen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

Folgt in Chunk 5, wenn Recherche und neue Handreferenz vorliegen. Bis dahin steht das Ergebnis der Messung unter [Ergebnis](#ergebnis).

## Punkt 4: die Batched-Pipeline von faster-whisper

### Was sie trägt

**Die `BatchedInferencePipeline` nimmt in faster-whisper 1.2.1 Hotwords und Wortzeiten an.** Belegt am Quelltext (`faster_whisper/transcribe.py`, `BatchedInferencePipeline.transcribe`) und am Lauf: Jede Batched-Wurzel hat die 48 Hotwords der Basis übergeben, und jedes Wort trägt eine Zeit und eine Konfidenz.

### Was sie anders macht

| | Pipeline (`WhisperModel.transcribe`) | Batched-Pipeline |
| --- | --- | --- |
| Zuschnitt | fortlaufende 30-s-Fenster über das VAD-Audio; das nächste Fenster beginnt, wo der Decoder aufgehört hat | ein Stück je Sprachabschnitt der VAD, höchstens 30 s, jedes für sich |
| VAD ohne `vad_parameters` | Schnitt ab 2000 ms Stille | Schnitt ab 160 ms Stille, Abschnitte auf 30 s begrenzt |
| Temperatur | Fallback 0 bis 1 in sechs Stufen nach `log_prob`, Kompression und `no_speech` | nur die erste Temperatur (0), die drei Schwellen wirken nicht |
| Zeitstempel-Tokens | ja | ohne (`without_timestamps`), mit `+ts` ja; Wortzeiten kommen in beiden Fällen aus der Ausrichtung |
| Text des vorigen Fensters | abgeschaltet (`condition_on_previous_text: false`) | nie |
| Stapel | 1 | 8 Stücke gleichzeitig |

- **Ein verlorenes Fenster kann kein folgendes mitreißen.** In der Pipeline bestimmt der Decoder selbst, wo das nächste Fenster beginnt. Überspringt er Sprache, fehlt sie. Die Batched-Pipeline legt die Stücke vor der Dekodierung fest.
- **Der Seed hat nichts mehr zu würfeln.** Ohne Fallback gibt es keine Stichprobe.

## Material und Methode

| | |
| --- | --- |
| Läufe | large-v3-turbo mit Hotwords, Segment 1 beider Sitzungen, Seeds 1–3 |
| Varianten | `base+batched`, `base+batched+ts`, `loud+batched` |
| Vergleich | `base` (Pipeline wie ausgeliefert), `base+temp0` (Pipeline ohne Fallback), `loud` (zweistufiges `loudnorm`, TOOL-103) |
| Referenz A | Pilotsitzung, 0:00:00–0:04:06, 531 Wörter |
| Referenz B | Pilotsitzung, 1:20:00–1:23:00, 441 Wörter |
| Referenz C | zweite Sitzung, 1:10:00–1:18:08, Fassung Hochdeutsch, 909 Wörter |
| Referenz D | Pilotsitzung, 0:43:00–0:46:00, 449 Wörter |
| Referenz E | Pilotsitzung, 1:23:00–1:26:00, 369 Wörter |
| Hardware | RTX 3080 Ti, 12 GB |

- **Regel, vor der Messung festgelegt** (Plan): Eine Variante bekommt ein Umsetzungsticket, wenn an A und an B ihre höchste WER der drei Seeds unter der niedrigsten des Vergleichs liegt (`base+batched` gegen `base`, `loud+batched` gegen `loud`) und Einfügungen und Wiederholungsanteil im Mittel nicht darüber liegen. C, D und E sind Gegenprobe.
- **`base+temp0`** trennt zwei Wirkungen: den fehlenden Fallback und den Zuschnitt je VAD-Abschnitt.
- **Blockverluste** über zwei Zahlen: „Sprache ohne Wörter“ aus `omissions.py` (Stellen, an denen die Diarisierung Sprache hört und der Lauf kein Wort hat) und die Wortzahl je 5 Minuten gegen `base` (`asr.py sections`).

## Ergebnis

**`base+batched` verliert keine Blöcke mehr, ist an allen fünf Referenzen besser als `base` und liefert bei jedem Seed dasselbe. Die vorab festgelegte Regel verfehlt die Variante trotzdem knapp, am Wiederholungsanteil.** `loud+batched` fällt durch, `+ts` bringt nichts.

**Nachtrag nach den neuen Fenstern:** Dieses Ergebnis gilt an den Referenzen A bis E. An drei von vier unruhigen Fenstern ist `base+batched` schlechter als `base` und verliert Blöcke von bis zu 94 Wörtern, siehe [Überlappung und kurze Beiträge an unruhigen Stellen](#überlappung-und-kurze-beiträge-an-unruhigen-stellen).

WER und Auslassungen als Mittel über drei Seeds, aus den Tabellen unter [Messwerte](#messwerte):

| Referenz | `base` | `loud` | `base+batched` | `base+batched+ts` | `loud+batched` | `base+temp0` |
| --- | --- | --- | --- | --- | --- | --- |
| A | 21,3 % / 33 | 20,2 % / 29 | 19,6 % / 29 | 20,5 % / 32 | 18,8 % / 27 | 29,8 % / 74 |
| B | 29,8 % / 44 | 26,5 % / 42 | 25,4 % / 38 | 25,4 % / 37 | 28,1 % / 39 | 40,8 % / 100 |
| C | 30,8 % / 138 | 23,9 % / 89 | 25,9 % / 110 | 32,2 % / 127 | 23,7 % / 97 | 47,9 % / 231 |
| D | 61,2 % / 138 | 36,7 % / 62 | 36,3 % / 65 | 36,3 % / 55 | 38,3 % / 77 | 52,8 % / 132 |
| E | 34,0 % / 56 | 29,6 % / 30 | 29,0 % / 40 | 28,7 % / 37 | 67,5 % / 96 | 46,6 % / 55 |

### Die Regel an A und B

| | `base+batched` gegen `base` | `loud+batched` gegen `loud` |
| --- | --- | --- |
| A: höchste WER unter der niedrigsten des Vergleichs | ja (19,6 % gegen 21,3 %) | ja (18,8 % gegen 20,2 %) |
| B: höchste WER unter der niedrigsten des Vergleichs | ja (25,4 % gegen 25,6 %) | nein (28,1 % gegen 26,5 %) |
| Einfügungen im Mittel nicht darüber | ja (A 15 gegen 17, B 4 gegen 18) | ja (A 16 gegen 17, B 5 gegen 6) |
| Wiederholungsanteil im Mittel nicht darüber | nein (1,0 % gegen 0,7 %) | nein (1,7 % gegen 0,6 %) |
| Gegenprobe C, D, E gegen das Mittel des Vergleichs | besser an allen drei | C gleich, D schlechter, E 67,5 % gegen 29,6 % |

- **`base+batched` verfehlt die Regel an einem Kriterium.** Der Wiederholungsanteil über das Segment liegt bei 1,0 % statt 0,7 % (zweite Sitzung 1,2 % statt 0,7 %). Die Einfügungen an den Referenzen sind dabei niedriger als bei `base`, die zusätzlichen Wiederholungen liegen also nicht in den Clips.
- **Der Abstand an B ist ein Wort.** 25,4 % gegen 25,6 % sind 112 gegen 113 Fehler. Gegen das Mittel von `base` (29,8 %) sind es 4,4 Punkte, weil `base` an B zwischen den Seeds um fast 10 Punkte streut.
- **Die Entscheidung über ein Umsetzungsticket fällt in Chunk 5** und liegt bei der Projektverantwortlichen, wie bei TOOL-103. Die Regel sagt nein, die Gegenprobe und die Blockverluste sprechen dafür.

### Blockverluste

Längste Folge ausgelassener Wörter je Seed (`omissions.py`):

| Referenz | `base` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- |
| A | 4 / 4 / 9 | 2 | 2 |
| B | 5 / 5 / 6 | 5 | 5 |
| C | 11 / 54 / 54 | 12 | 12 |
| D | 38 / 57 / 45 | 9 | 17 |
| E | 5 / 5 / 40 | 3 | 49 |

| Segment 1 | `base` | `base+batched` | `loud+batched` |
| --- | --- | --- | --- |
| Pilotsitzung: Sprache ohne Wörter | 4,0 % | 4,7 % | 4,4 % |
| Pilotsitzung: Stellen ab 2 s | 59–62 | 67 | 67 |
| zweite Sitzung: Sprache ohne Wörter | 6,3–6,5 % | 4,8 % | 4,2 % |
| zweite Sitzung: Stellen ab 2 s | 103–114 | 62 | 40 |
| 5-min-Abschnitte mit Defizit gegen `base#1` (Pilot / zweite Sitzung) | 0 / 0–2 | 0 / 0 | 0 / 0 |

- **Die Blöcke aus TOOL-101 und TOOL-102 sind mit `base+batched` weg.** An C fehlten in zwei von drei Seeds 54 Wörter am Stück, an D in jedem Seed 38–57. Jetzt sind es höchstens 12 und 9. Kein 5-min-Abschnitt hat ein Defizit.
- **Der Gewinn kommt aus dem Zuschnitt, nicht aus dem fehlenden Fallback.** `base+temp0`, die Pipeline ohne Fallback, ist an vier von fünf Referenzen deutlich schlechter als `base`, mit 8,9 % Wiederholungsanteil und vier Abschnitten mit Defizit an der zweiten Sitzung. Ohne Fallback gerät der fortlaufende Decoder in Schleifen; je Stück dekodiert passiert das kaum.
- **Ohne Fallback bleibt ein misslungenes Stück stehen.** `loud+batched` hat an E 96 Auslassungen und 96 Einfügungen, die längste Folge sind 49 Wörter: Ein Stück ist entgleist, und nichts wiederholt es. `base+batched` zeigt das an keiner Referenz, der Wiederholungsanteil von 1,0–1,2 % deutet aber darauf, dass es anderswo im Segment vorkommt.
- **Die engere VAD kostet Wörter.** Die Batched-Pipeline behält 225,6 von 300,0 min (Pipeline: 241,3) und 207,0 von 286,9 min (222,6). In entferntem Audio liegen an C, D und E 24, 9 und 11 Referenzwörter (Pipeline: 20, 3 und 3), davon fehlen 12, 8 und 8. Das sind 11–20 % der Auslassungen von `base+batched` an diesen Referenzen. Eine Variante mit großzügigerer VAD ist nicht gemessen.

### Seeds, Laufzeit, Bewertung

- **Die drei Seeds sind identisch,** in jeder Batched-Variante und an beiden Sitzungen, bis auf das Wort. Die Streuung von `base` (an D 49–82 %, an C 80–177 Auslassungen) entfällt.
- **`base+batched` und `loud` landen fast gleich,** auf verschiedenen Wegen: A 19,6 / 20,2 %, B 25,4 / 26,5 %, C 25,9 / 23,9 %, D 36,3 / 36,7 %, E 29,0 / 29,6 %. Beide beseitigen die Blockverluste. Zusammen addieren sie sich nicht: `loud+batched` ist an A und C gleich gut oder leicht besser, an B, D und E schlechter.
- **`+ts` lohnt nicht.** An der Pilotsitzung gleich, an C 32,2 % statt 25,9 % mit 72 statt 34 Einfügungen, und doppelt so langsam.
- **Laufzeit und Speicher:** 0,33–0,38 min je Stunde Audio statt 1,25–1,42, also unter 2 min für ein 5-h-Segment statt 6–7 min. Peak-RAM 4,0–4,4 GiB statt 12,8–13,9, Peak-VRAM 4,6–4,8 GiB statt 3,6–4,3.
- **Die Bewertung passt nicht mehr.** Ohne Zeitstempel-Tokens ist jedes Stück eine Passage: 479 und 435 Passagen je Segment, davon 22 und 19 `confident`. An A und D liegen 15 und 44 Fehler in `confident`-Passagen (`base`: 0–5 und 5–10). Die Läufe sind nicht diarisiert, der Schnitt am Sprecherwechsel (TOOL-96) fehlt hier also; eine Umsetzung müsste Passagenzuschnitt und Schwellen neu prüfen.

### Offen nach dieser Messung

- Großzügigere VAD für die Batched-Pipeline (`speech_pad_ms`, `threshold`): 11–20 % ihrer Auslassungen an C, D und E liegen in entferntem Audio.
- Wo im Segment `base+batched` wiederholt, und ob sich ein entgleistes Stück erkennen und einzeln neu dekodieren lässt (Kompression, `avg_logprob`).
- `loud+batched` an E: Warum entgleist das Stück auf dem normalisierten Audio und nicht auf dem rohen?

## Recherche: Punkt 3, 1, 2 und 5

Quellenstand 2026-11-23. Kein Modell wurde heruntergeladen oder installiert. Alle Angaben stammen aus Modellkarten, Repos und Papern; „nicht belegt“ heißt, dass die Primärquelle dazu nichts sagt. Der Aufwand ist eine Schätzung gegen das heutige Backend: faster-whisper mit Wortzeiten, Wortkonfidenz und Hotwords, fünf Stunden am Stück.

**Für keinen Kandidaten gibt es veröffentlichte Werte auf deutscher Meeting- oder Fernfeldsprache.** Das wichtigste Auswahlkriterium aus dem Plan lässt sich also bei keinem prüfen. Deutsche Gesprächssprache gibt es nur auf MLC-SLM: zwei Personen, Mobiltelefon, ruhiger Raum, kaum Überlappung ([Beschreibung](https://arxiv.org/html/2509.13785v1)). Alles andere ist gelesene Sprache.

Schon gemessen und deshalb nicht in den Tabellen: Whisper large-v3-turbo und large-v3, Parakeet TDT 0.6B v3, Granite Speech 4.1 2B Plus (TOOL-62), das deutsche Turbo-Modell von primeline und CrisperWhisper 1.0 (TOOL-93).

### Punkt 3: neue lokale Modelle

| Kandidat | Quelle | Lizenz | Hardware | Deutsch | Wortzeiten | Biasing | Aufwand für ein Backend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3-ASR-1.7B | [Karte](https://huggingface.co/Qwen/Qwen3-ASR-1.7B), [Paper](https://arxiv.org/html/2601.21337), 2026-01-29 | Apache-2.0 | 2 Mrd. Parameter, BF16; VRAM nicht belegt; Paket `qwen-asr` oder transformers | ja; WER MLS 6,05, Common Voice 5,85, FLEURS 3,92, MLC-SLM (Gespräch) 17,19; Fernfeld nicht belegt | nicht nativ; eigener Aligner Qwen3-ForcedAligner-0.6B mit Deutsch, bis 5 min je Aufruf | Kontext im System-Prompt laut Paper; in Karte und Beispielen nicht belegt | hoch: eigene Umgebung, Zuschnitt (laut Paper höchstens 20 min je Aufruf), Aligner als zweiter Schritt; Wortkonfidenz nicht belegt |
| Cohere Transcribe 03-2026 | [Karte](https://huggingface.co/CohereLabs/cohere-transcribe-03-2026), 2026-03-26 | Apache-2.0, Download nach Zustimmung | 2 Mrd. Parameter; VRAM nicht belegt; transformers ≥ 5.4 | ja (14 Sprachen); Mittel aus CoVoST-2 und FLEURS 3,84 ([Leaderboard-Paper](https://arxiv.org/html/2510.06961v4)); nur gelesene Sprache | keine | nicht belegt | hoch: Zwangsausrichtung nötig, VAD davor Pflicht, kein Biasing; Wortkonfidenz nicht belegt; Zuschnitt langer Dateien ist eingebaut |
| Voxtral Mini 3B | [Karte](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507), [Paper](https://arxiv.org/html/2507.13264v1), 2025-07 | Apache-2.0 | rund 9,5 GB VRAM laut Karte; vLLM oder transformers | ja (8 Sprachen); FLEURS 4,40, Common Voice 6,07, MLS 7,09 (large-v3: 5,46 / 6,25 / 5,72); nur gelesene Sprache | nicht belegt | nicht belegt; „System prompts are not yet supported“ | hoch: bis 30 min je Aufruf, Zwangsausrichtung nötig, kein Biasing, kaum VRAM-Reserve |
| Canary-1b-v2 | [Karte](https://huggingface.co/nvidia/canary-1b-v2), [Paper](https://arxiv.org/html/2509.14128v2), 2025-08-14 | CC-BY-4.0 | 978 Mio. Parameter; VRAM nicht belegt; NeMo | ja (25 Sprachen); FLEURS 4,40, CoVoST2 5,53; nur gelesene Sprache | Wort und Segment über den NeMo Forced Aligner | nicht belegt | mittel: NeMo-Umgebung aus TOOL-62, Zuschnitt in 30–40 s eingebaut; die Karte rät von wörtlicher Transkription unvollständiger Sätze ab |
| primeline/parakeet-primeline | [Karte](https://huggingface.co/primeline/parakeet-primeline), Datum nicht belegt | CC-BY-4.0 | 600 Mio. Parameter; VRAM nicht belegt; NeMo oder ONNX Runtime | deutsches Feintuning von Parakeet v3; Tuda-De 4,11 (Parakeet v3: 7,05), MLS 2,60 (2,95), Common Voice 3,03 (3,70); nur gelesene Sprache | nativ | nicht belegt | niedrig als Variante des Parakeet-Laufs aus TOOL-62 (Blöcke à 300 s); betrifft den Zweitlauf in TOOL-82 |
| Granite Speech 5.0 2B | [Karte](https://huggingface.co/ibm-granite/granite-speech-5.0-2b), 2026-10-20 | Apache-2.0 | 2 Mrd. Parameter; VRAM nicht belegt; transformers, vLLM oder llama.cpp | ja (6 Sprachen); deutsche Werte nur als Grafik, als Zahl nicht belegt | nicht belegt | Keywords im Prompt, bis 2000 | hoch: Abschnitte bis rund 2 min, also eigener Zuschnitt; der Vorgänger lag in TOOL-62 bei 60,6 % WER und lief in Schleifen |

- **Kein Kandidat ist ein Ersatz ohne Umbau.** Nur Whisper liefert heute Wortzeiten, Wortkonfidenz und Hotwords zusammen. Jeder Kandidat verliert mindestens eines davon, und die Wortkonfidenz ist bei keinem belegt. Auf ihr beruht die Bewertung der Passagen (TOOL-60).
- **Am ehesten eine Messung wert sind Qwen3-ASR-1.7B und Cohere Transcribe.** Qwen3-ASR hat als einziger Kandidat einen deutschen Gesprächswert und bringt einen deutschen Aligner mit. Cohere Transcribe neigt laut Karte dazu, zu viel zu transkribieren („eager to transcribe, even non-speech sounds“), also in die Gegenrichtung unseres Fehlers; auf langen englischen Aufnahmen ist es das beste offene Modell des Leaderboards (WER 9,73 gegen 11,2 bei large-v3). Beide dekodieren mit einem anderen Decoder als Whisper und Parakeet, das Auslassungsprofil ist offen.
- **Die Benchmark-Abstände sind klein.** Auf gelesenem Deutsch liegen alle Kandidaten innerhalb von 1–2 Punkten um large-v3. TOOL-62 und TOOL-93 haben gezeigt, dass solche Abstände an unserem Material nichts vorhersagen.
- **Granite 4.1 Plus hat am 2026-10-19 neue Gewichte bekommen** ([Karte](https://huggingface.co/ibm-granite/granite-speech-4.1-2b-plus)): besseres Keyword-Biasing, Wortzeiten auf langen Abschnitten im Mittel 328 statt 814 ms daneben, WER im Mittel unverändert (6,10 gegen 6,01). TOOL-62 hat am 2026-11-04 gemessen, also nach dem Update; die Revision steht nicht im Bericht. Ein neuer Lauf ist damit nicht begründet.

#### Mundart

**Für Bairisch gibt es kein nutzbares lokales Modell.** Die Suche auf Hugging Face nach bairischen oder österreichischen Mundart-Modellen ergibt kein ASR-Modell.

- **Whisper ist auf Mundart schon das beste verfügbare Modell und schreibt hochdeutsch.** Betthupferl ([Blaschke et al., Interspeech 2025](https://arxiv.org/abs/2506.02894)): rund 4 h gelesene Mundart (Fränkisch, Bairisch, Alemannisch), nur Evaluation, kein Modell. large-v3 ist in jedem Aufbau am besten, die WER gegen die hochdeutsche Referenz liegt trotzdem bei 31 statt 9. Ein zweites Paper mit einem oberbairischen Sprecher ([arXiv 2510.07890](https://arxiv.org/html/2510.07890v2)) misst für large-v3-turbo 26,0 gegen 9,0, für die CTC-Modelle XLS-R und MMS 81–83. Das Verhältnis deckt sich mit dem Zwei- bis Dreifachen aus TOOL-60.
- **Schweizerdeutsch zeigt, dass Feintuning auf Mundart mit hochdeutscher Ausgabe geht, wenn es Daten gibt.** Auf ASGDTS liegen die feingetunten Modelle bei 20–22 % WER, large-v3 ohne Feintuning bei 24,0 %, Parakeet v3 bei 36,2 % ([Vergleichstabelle](https://huggingface.co/Flurin17/parakeet-tdt-0.6b-v3-swiss-german)). Dafür waren 300–1900 h Mundart mit hochdeutschem Transkript nötig. Für Bairisch gibt es kein solches Korpus, und laut Betthupferl überträgt sich ein Schweizer Modell nicht.
- **Folge für den Zweitlauf (TOOL-82):** Parakeet fällt auf Mundart ohne Feintuning viel stärker ab als Whisper. Ein Zweitlauf mit Parakeet dürfte beim Mundartsprecher am wenigsten beitragen.

### Punkt 1: sprecherbedingte Erkennung

| Kandidat | Quelle | Lizenz | Hardware | Deutsch | Wortzeiten | Biasing | Aufwand für ein Backend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DiCoW v3.3 | [Karte](https://huggingface.co/BUT-FIT/DiCoW_v3_3), [Paper](https://arxiv.org/html/2601.19194v1), [Repo](https://github.com/BUTSpeechFIT/DiCoW), 2026-01 | Gewichte CC-BY-4.0, Code Apache-2.0; der dokumentierte Diarisierer DiariZen ist CC-BY-NC-4.0 | 0,9 Mrd. Parameter auf Basis large-v3-turbo; VRAM nicht belegt; transformers mit `trust_remote_code`, ein Durchlauf je Sprecher | Training nur auf Englisch (AMI, NOTSOFAR-1, LibriMix); Deutsch nicht belegt | Karte: nicht belegt; der Code gibt nur Segmentzeiten aus | keines dokumentiert | hoch: Maske je Sprecher aus der Diarisierung (Stille, Ziel, andere, Überlappung); die CLI kennt nur DiariZen, pyannote community-1 ist nicht belegt; feste Versionen (transformers 4.55, torch 2.5.1); Hotwords und Wortzeiten entfallen |
| DiCoW_v3_MLC | [Karte](https://huggingface.co/BUT-FIT/DiCoW_v3_MLC), [Paper](https://arxiv.org/html/2506.13414v1), 2025-09 | auf der Karte widersprüchlich: CC-BY-4.0 und Apache-2.0 | 1,0 Mrd. Parameter; VRAM nicht belegt; transformers | ja, einzige Variante mit deutschem Training; tcpWER Deutsch auf MLC-SLM 27,3 mit echter Diarisierung, 23,9 mit Referenzsegmenten (large-v3 dort: 20,7) | nicht belegt | keines dokumentiert | hoch, wie v3.3; die Werte gelten mit einem auf MLC-SLM feingetunten DiariZen |
| SE-DiCoW | [Karte](https://huggingface.co/BUT-FIT/SE_DiCoW), [Paper](https://arxiv.org/html/2601.19194v1), 2026-02 | Apache-2.0 | 1 Mrd. Parameter; VRAM nicht belegt; transformers | nur Englisch; Deutsch nicht belegt | nicht belegt | keines dokumentiert | hoch, wie v3.3, dazu ein Referenzfenster je Sprecher; an echtem Fernfeld kaum Gewinn (AMI SDM 18,6 → 18,5 tcpWER) |
| Trelis/tiron | [Karte](https://huggingface.co/Trelis/tiron), 2026-07-21 | Apache-2.0 | 2 Mrd. Parameter auf Basis large-v3; 3–12 GB VRAM laut Karte | nicht belegt | 20-ms-Raster, unter Überlappung laut Karte ungefähr; Wortebene nicht belegt | keines dokumentiert | hoch: ersetzt ASR und Diarisierung, 30-s-Fenster, Sprecher über Fenster hinweg per Embedding verknüpft; cpWER AMI 34,68 |
| MOSS-Transcribe-Diarize 0.9B | [Karte](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize), [Repo](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize), 2026-07-09 | Apache-2.0 | 0,9 Mrd. Parameter; VRAM nicht belegt, das Repo warnt vor Speichermangel bei langen Aufnahmen | „50+ Sprachen“; deutscher Wert nicht belegt | nur Segment | Hotwords im Prompt | hoch: bis 90 min je Durchlauf, Verknüpfung der Sprecher über Blöcke fehlt |

- **Kein Beleg für Deutsch im Fernfeld, und der einzige deutsche Wert spricht nicht dafür.** Auf MLC-SLM ist DiCoW mit Referenzsegmenten auf Deutsch nicht besser als large-v3 (21,2 und 23,9 gegen 20,7). Der große Vorsprung mit echter Diarisierung (27,3–30,1 gegen 86,7) zeigt vor allem, wie schlecht die Diarisierung des Vergleichs dort war. Die Autoren warnen selbst, dass ein nur englisch trainiertes Modell auf anderen Sprachen begrenzt ist.
- **Auslassungen bleiben auch dort der größte Fehler, und sie hängen an der Diarisierung.** Im [DiCoW-Paper](https://arxiv.org/html/2501.00114v1) sind auf NOTSOFAR-1 mit echter Diarisierung 14,5 von 33,5 Punkten tcpWER Auslassungen; die Autoren führen sie auf Sprache zurück, die der Diarisierer verpasst. Zwischen Referenz- und echter Diarisierung liegen 16,0 gegen 26,6 (NOTSOFAR-1) und 14,5 gegen 18,6 (AMI SDM). Kurze Beiträge, die der Diarisierer nicht findet, bekommt auch DiCoW nicht.
- **Der Umbau ist der größte aller Punkte.** DiCoW läuft nicht über faster-whisper. Hotwords, Wortzeiten, Wortkonfidenz und die Batched-Dekodierung fielen weg, die Laufzeit wächst mit der Sprecherzahl. Dem steht gegenüber, dass Überlappung an A und C nur 3–6 % der Wörter trägt.
- **Die Modelle mit eingebauter Sprecherzuordnung** (tiron, MOSS-Transcribe-Diarize) haben weder deutsche Werte noch Wortzeiten und ersetzen zwei Schritte auf einmal. Granite 4.1 Plus hat ebenfalls einen solchen Modus, er ist nur auf englischen Daten bewertet (WDER auf AMI SDM 13,9).

### Punkt 2: Sprachtrennung vor der Erkennung

| Kandidat | Quelle | Lizenz | Hardware | Deutsch | Wortzeiten | Biasing | Aufwand für ein Backend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pyannote PixIT (`speech-separation-ami-1.0`) | [Karte](https://huggingface.co/pyannote/speech-separation-ami-1.0), [Paper](https://arxiv.org/html/2403.02288v2), 2024 | MIT, Download nach Zustimmung | Parameter und VRAM nicht belegt; der Code hält alle Quellen in voller Länge im RAM | Training nur auf AMI SDM (Englisch, 79 h); Deutsch nicht belegt | 16 kHz auf der Originalzeit; jede Sprecherspur wird einzeln transkribiert, das Zusammenführen der Wortzeiten ist nicht beschrieben | unverändert, wirkt vor dem ASR | hoch: Karte nennt pyannote.audio 3.3.2, Laden unter 4.x nicht belegt; ein ASR-Lauf je Sprecherspur; höchstens 3 Sprecher je 5-s-Fenster im Paper; fünf Stunden nicht belegt |
| MossFormer2_SS_16K | [Karte](https://huggingface.co/alibabasglab/MossFormer2_SS_16K), [Repo](https://github.com/modelscope/ClearerVoice-Studio), 2024-11 | Apache-2.0 | Parameter und VRAM nicht belegt; Paket `clearvoice` | Training auf gelesener und synthetischer Sprache, Englisch und Mandarin; Deutsch nicht belegt | 16 kHz; ob die Zeitachse erhalten bleibt, ist nicht belegt | unverändert, wirkt vor dem ASR | hoch: zwei Sprecher, voll überlagert trainiert; kein ASR-Ergebnis und keine echte Aufnahme veröffentlicht |
| SepFormer WHAMR! 16k | [Karte](https://huggingface.co/speechbrain/sepformer-whamr16k), 2021 | Apache-2.0 | Parameter und VRAM nicht belegt; SpeechBrain | simuliertes Englisch mit Hall und Rauschen; Deutsch nicht belegt | 16 kHz; ob die Zeitachse erhalten bleibt, ist nicht belegt | unverändert, wirkt vor dem ASR | hoch: zwei Ausgänge, kein Verfahren für lange Aufnahmen; die Karte gibt keine Gewähr außerhalb des Testsets |

- **Nur PixIT ist auf echten Fernfeld-Meetings trainiert, und sein Gewinn ist vor allem Sprecherzuordnung.** Auf AMI SDM mit Whisper large-v2 fällt die cpWER von 38,3 auf 31,7. Die WER je Äußerung, ohne Sprecherzuordnung, fällt nur von 35,4 auf 33,8.
- **Artefakte sind das Hauptrisiko.** Im selben Paper steigt die cpWER ohne die beiden Schutzmaßnahmen (WavLM-Merkmale, Entfernen von Übersprechen zwischen den Spuren) von 38,8 auf 50,1. Auf LibriCSS kostet einkanalige Trennung in Abschnitten ohne Überlappung je nach Modell bis zu 4 Punkte ([Chen et al.](https://ar5iv.labs.arxiv.org/html/2008.05773)); erst mit sieben Kanälen wird sie dort besser. Das passt zu TOOL-92: Entrauschen vor Whisper hat nicht geholfen.
- **Die übrigen Trennmodelle sind auf simulierten, voll überlagerten Mischungen trainiert.** Für echte, hallige Aufnahmen mit seltener Überlappung gilt das als bekannte Schwäche ([Wang und Cornell 2026](https://arxiv.org/abs/2605.19695)). Die besten Systeme der Einkanal-Wertung von NOTSOFAR-1 liegen bei 22,2 % tcpWER, mit Mikrofon-Array bei 10,8 % ([Zusammenfassung](https://arxiv.org/html/2501.17304v2)).
- **Für Deutsch gibt es keine einzige Messung einer Trennung vor dem ASR.** Der Nutzen wäre auf die 3–6 % der Wörter in Überlappung begrenzt, das Risiko trifft die übrigen 94–97 %.

### Punkt 5: Dekodierung je Redebeitrag

| Kandidat | Quelle | Lizenz | Hardware | Deutsch | Wortzeiten | Biasing | Aufwand für ein Backend |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Turns der Diarisierung als `clip_timestamps` der Batched-Pipeline | [faster-whisper 1.2.1](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py) | MIT | wie `base+batched`: 4,6–4,8 GiB VRAM | unverändert, dasselbe Modell | bleiben, auf der Originalzeit | Hotwords bleiben | niedrig für eine Messung: ein Modifikator im Spike-Wrapper, die Diarisierung muss vor dem ASR laufen; für die Pipeline mittel, weil sich die Reihenfolge der Schritte umkehrt |

- **Der Weg ist da, aber niemand dokumentiert ihn für diesen Zweck.** Die Batched-Pipeline nimmt eine Liste von Abschnitten, überspringt dann die VAD und dekodiert jeden Abschnitt für sich. Abschnitte über 30 s schneidet sie ab, eine Mindestlänge gibt es nicht, ein Fallback auch nicht. Lange Beiträge müssten also geteilt, kurze verbunden oder gepolstert werden. Die Maintainer nennen die Option einen Nachbau von Whispers eigenem `clip_timestamps`, nicht einen Eingang für eigene Segmente ([Issue 1205](https://github.com/SYSTRAN/faster-whisper/issues/1205)).
- **Die Literatur spricht gegen sehr kurze Stücke.** WhisperX verbindet VAD-Abschnitte ausdrücklich bis 30 s, weil kurze Stücke den Kontext verlieren ([Paper](https://arxiv.org/html/2303.00747v2)). Bei NOTSOFAR-1 hat ein Team durch das Verbinden kurzer Segmente die tcORC-WER von 37,6 auf 31,0 gesenkt ([Zusammenfassung](https://arxiv.org/html/2501.17304v2)). Auf Stücken von 1 s ohne Sprache halluziniert large-v3 in 52 % der Fälle ([Barański et al. 2025](https://arxiv.org/html/2501.11378)). Unsere Diarisierung liefert Beiträge mit einem Median von 1,2 s (TOOL-20).
- **Die Batched-Pipeline ist schon der halbe Weg.** Sie schneidet bei 160 ms Stille und dekodiert jedes Stück für sich. Was Punkt 5 darüber hinaus bringen kann, ist der Schnitt am Sprecherwechsel ohne Pause und die Abdeckung von Sprache, die die VAD verwirft (11–20 % der Auslassungen von `base+batched` an C, D und E).
- **Ein Vergleich „erst diarisieren, dann je Beitrag transkribieren“ gegen „erst transkribieren, dann zuordnen“ mit getrennt ausgewiesenen Auslassungen ist nicht veröffentlicht.** Für deutsche Kurzbeiträge wie „ja“ oder „mhm“ gibt es keine Quelle. Die Frage lässt sich nur an den eigenen Referenzen klären, und Punkt 5 ist der einzige der vier Punkte, der das ohne neues Modell erlaubt.

### Ausgeschieden

| Ansatz | Grund |
| --- | --- |
| [Voxtral Small 24B](https://huggingface.co/mistralai/Voxtral-Small-24B-2507) | VRAM: rund 55 GB |
| [Voxtral Mini 4B Realtime](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602) | VRAM: ab 16 GB, Streaming-Modell |
| [Voxtral Mini Transcribe V2](https://mistral.ai/news/voxtral-transcribe-2) | nur Cloud; die Variante mit Wortzeiten, Sprechern und Biasing |
| [Nemotron 3.5 Transcribe 30B-A4B](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B-FP8) | VRAM: ab 24 GB auch quantisiert; sonst der beste Treffer (Deutsch mit Sprecherzuordnung, Wortzeiten, Kontextbegriffe, 1 h Audio) |
| [Microsoft VibeVoice-ASR](https://huggingface.co/microsoft/VibeVoice-ASR) | VRAM: 9 Mrd. Parameter, keine offizielle quantisierte Fassung; transkribiert bei Überlappung laut Autoren nur den dominanten Sprecher |
| [Salesforce SOV-Transcribe-1](https://huggingface.co/salesforce-sovereign-intelligence/SOV-Transcribe-1) | VRAM: 26,6 Mrd. Parameter |
| [Meta Omnilingual ASR](https://github.com/facebookresearch/omnilingual-asr) | 7B braucht rund 17 GiB und ist auf Deutsch schlechter als large-v3 (4,58 gegen 4,26); keine Wortzeiten |
| [Canary-Qwen-2.5B](https://huggingface.co/nvidia/canary-qwen-2.5b), [Kyutai STT](https://kyutai.org/stt), [Moonshine](https://arxiv.org/html/2509.02523v1), [Fun-ASR-MLT-Nano](https://huggingface.co/FunAudioLLM/Fun-ASR-MLT-Nano-2512) | kein Deutsch |
| [BUT-FIT/Pandemonium](https://huggingface.co/BUT-FIT/Pandemonium) | kein Deutsch; sonst der Aufgabe am nächsten (einkanaliges Fernfeld mit mehreren Sprechern, Wortzeiten) |
| [Phi-4-multimodal](https://huggingface.co/microsoft/Phi-4-multimodal-instruct) | höchstens 40 s je Aufruf, keine Wortzeiten, laut Karte experimentell |
| [parakeet-ultra](https://huggingface.co/moondream/parakeet-ultra), [fluid-speech-pro](https://huggingface.co/FluidVoice-Labs/fluid-speech-pro), [nemotron-labs-unified-asr-0.6b](https://huggingface.co/nvidia/nemotron-labs-unified-asr-0.6b) | Nachtrainings von Parakeet v3 mit unter 1 Punkt Gewinn auf gelesenem Deutsch; dieselbe Architektur ist in TOOL-62 gemessen |
| [NVIDIA Multitalker Parakeet mit Sortformer](https://huggingface.co/nvidia/multitalker-parakeet-streaming-0.6b-v1) | kein Deutsch |
| [syvai/cohere-transcribe-diarize](https://huggingface.co/syvai/cohere-transcribe-diarize) | nur englisch trainiert, keine veröffentlichten Werte |
| [TagSpeech](https://huggingface.co/AudenAI/TagSpeech-AMI), [SOT-DiCoW](https://github.com/BUTSpeechFIT/SOT-DiCoW) | kein Deutsch beziehungsweise keine veröffentlichten Gewichte |
| [SepReformer](https://github.com/dmlguq456/SepReformer), [TF-Locoformer](https://github.com/merlresearch/tf-locoformer), TF-GridNet | nur Gewichte für simulierte Mischungen (WSJ0-2mix, Libri2Mix, WHAMR!) |
| [WeSep](https://github.com/wenet-e2e/wesep) und andere Zielsprecher-Extraktion | keine veröffentlichten Gewichte für 16 kHz ohne Video; braucht Referenzaudio je Person |
| Guided Source Separation und die Mehrkanal-Systeme aus CHiME | brauchen ein Mikrofon-Array |
| pyannoteAI, gehostete Trennung | nur Cloud |
| CrisperWhisper 2.0 | Lizenz, siehe TOOL-93 |

### Stand nach der Recherche

- **Punkt 3:** zwei Modelle mit einem anderen Decoder als Whisper, die eine Messung an A, B und C rechtfertigen könnten (Qwen3-ASR-1.7B, Cohere Transcribe), beide mit hohem Aufwand und ohne Beleg für unser Material. Für Mundart gibt es nichts.
- **Punkt 1 und 2:** kein Kandidat mit Beleg für Deutsch oder für weniger Auslassungen im einkanaligen Fernfeld. Beide zielen auf Überlappung, die nach TOOL-101 höchstens ein Fünftel der Auslassungen trägt.
- **Punkt 5:** kein neues Modell, mit dem vorhandenen Werkzeug messbar, Ausgang offen.
- Welche davon einen der höchstens drei Plätze bekommen, entscheidet sich nach der neuen Handreferenz (Chunk 4 und 5).

## Überlappung und kurze Beiträge an unruhigen Stellen

TOOL-101 stand bei Überlappung auf 17 und 52 Referenzwörtern, bei Beiträgen mit 1–3 Wörtern auf 16 und 23. Für eine Entscheidung zu Punkt 1, 2 und 5 hat die Projektverantwortliche vier weitere Fenster abgetippt, an den Stellen mit der meisten Überlappung und den meisten kurzen Beiträgen laut Diarisierung (`omissions.py --suggest`).

| | |
| --- | --- |
| Referenz F | Pilotsitzung, 1:40:00–1:43:00, 584 Wörter |
| Referenz G | Pilotsitzung, 1:31:00–1:34:00, 551 Wörter |
| Referenz H | zweite Sitzung, 1:38:00–1:41:00, 470 Wörter |
| Referenz I | Pilotsitzung, 1:38:00–1:41:00, 597 Wörter; überschneidet sich eine Minute mit F |

Die Zahlen dieses Abschnitts kommen aus `omissions.py`, Auslassungen als Mittel über drei Seeds. Die Summen laufen über A bis H. I steht wegen der gemeinsamen Minute mit F daneben und geht in keine Summe ein. Die Klassen überschneiden sich, ihre Anteile lassen sich nicht addieren.

### WER an den neuen Fenstern

Mittel über drei Seeds, bei `base` mit Spanne. Tabellen unter [Messwerte](#neue-fenster-f-g-h-und-i).

| Referenz | `base` | `loud` | `base+batched` | `base+batched+ts` | `loud+batched` |
| --- | --- | --- | --- | --- | --- |
| F | 28,4 % (26,7–31,0) | 27,5 % | 26,4 % | 26,7 % | 26,7 % |
| G | 36,0 % (33,4–39,2) | 42,3 % | 39,6 % | 53,4 % | 35,6 % |
| H | 36,5 % (34,9–37,2) | 32,8 % | 53,6 % | 34,9 % | 37,2 % |
| I | 27,2 % (26,6–28,3) | 30,3 % | 33,2 % | 26,3 % | 31,7 % |

- **`base+batched` ist an drei der vier unruhigen Fenster schlechter als jeder `base`-Lauf.** An H fehlen 149 statt 73–86 Wörter, an I 124 statt 66–82. Nur an F ist die Variante besser.
- **Die Blockverluste sind nicht weg, sie liegen woanders.** Die längste Folge ausgelassener Wörter ist mit `base+batched` an H 94 Wörter (`base`: 15) und an I 48 (`base`: 9–10). An H liegen 77 der 149 Auslassungen an Stellen, an denen die Diarisierung Sprache hört und der Lauf kein Wort hat; die VAD hat dort nur 16 Wörter entfernt. Das Audio kam also beim Decoder an, und ein Stück ist ohne Text oder entgleist zurückgekommen. Ohne Fallback wiederholt es niemand.
- **Keine Variante ist an allen vier Fenstern die beste.** `+ts` rettet H und I und verliert G, `loud+batched` ist an G am besten und an I schlecht, `loud` hilft an H und schadet an G und I. Die Reihenfolge wechselt von Fenster zu Fenster stärker, als `base` zwischen den Seeds streut.
- **Die Aussage aus dem [Ergebnis](#ergebnis), `base+batched` sei an allen Referenzen besser und verliere keine Blöcke, gilt an A bis F und nicht an G, H und I.** Sie war an ruhigeren Stellen gemessen.

### Wie viel in den Klassen liegt

`base`, acht Referenzen (A bis H), 4304 Wörter, im Mittel 634 Auslassungen (14,7 %):

| Klasse | Wörter | Anteil an den Wörtern | Auslassungen | je Wort der Klasse | Anteil an allen Auslassungen |
| --- | --- | --- | --- | --- | --- |
| Überlappung | 362 | 8,4 % | 112 | 30,9 % | 18 % |
| Beitrag unter 2 s (Diarisierung) | 610 | 14,2 % | 100 | 16,3 % | 16 % |
| kein Turn der Diarisierung | 235 | 5,5 % | 60 | 25,7 % | 10 % |
| Beitrag mit 1–3 Wörtern (Handreferenz) | 152 | 3,5 % | 54 | 35,5 % | 9 % |
| außerhalb von Überlappung | 3942 | 91,6 % | 522 | 13,2 % | 82 % |

Wörter je Referenz (A / B / C / D / E / F / G / H): Überlappung 17 / 1 / 52 / 38 / 17 / 110 / 83 / 44, Beiträge mit 1–3 Wörtern 16 / 1 / 23 / 38 / 13 / 13 / 5 / 43. Referenz I hat 114 Wörter in Überlappung, davon fehlen 24 %, und 10 in Beiträgen mit 1–3 Wörtern.

- **Die Wortzahl reicht jetzt.** Überlappung steht auf 362 statt 69 Wörtern, Beiträge mit 1–3 Wörtern auf 152 statt 39. Beide liegen über dem Ziel von rund 100, und beide Sitzungen tragen dazu bei.
- **Der Befund aus TOOL-101 hält.** In Überlappung fehlen 31 % der Wörter, außerhalb 13 %. In Beiträgen mit 1–3 Wörtern fehlen 36 %. Beide Klassen bleiben klein: Überlappung trägt 18 % der Auslassungen, die Kurzbeiträge 9 %.
- **Auch an den unruhigsten Stellen liegt die Mehrheit außerhalb.** In Überlappung liegen an F 35 % der Auslassungen, an G 20 %, an H 26 %, an I 37 %, bei 9–19 % der Wörter.
- **Echte Einwürfe sind seltener, als die Diarisierung nahelegt.** Sie zählt an F und G 57 und 55 Beiträge unter 2 s, die Handreferenz enthält dort 13 und 5 Wörter in Beiträgen mit 1–3 Wörtern. Die kurzen Beiträge der Diarisierung sind überwiegend Stücke längerer Sätze derselben Person. Nur H hat mit 43 Wörtern viele Einwürfe.

### Was die Batched-Pipeline dort ändert

Acht Referenzen (A bis H), 4304 Wörter:

| | `base` | `base+batched` |
| --- | --- | --- |
| Auslassungen gesamt | 634 (14,7 %) | 586 (13,6 %) |
| außerhalb von Überlappung, je Wort | 13,2 % | 12,4 % |
| in Überlappung, je Wort | 30,9 % | 27,9 % |
| Beitrag unter 2 s, je Wort | 16,3 % | 16,7 % |
| kein Turn der Diarisierung, je Wort | 25,7 % | 35,8 % |
| Beitrag mit 1–3 Wörtern, je Wort | 35,5 % | 43,4 % |

Die Wortzahl je Klasse weicht zwischen den Varianten um wenige Wörter ab, weil die Wortzeiten aus den Läufen kommen.

- **Über alle acht Referenzen bleibt von dem Vorsprung der Batched-Pipeline ein Punkt.** An A bis G waren es 11,4 % gegen 14,4 % Auslassungen je Wort; der Block an H nimmt den größten Teil davon zurück.
- **In kurzen Beiträgen gewinnt sie nichts, bei Einwürfen und bei Wörtern ohne Turn verliert sie.** An D fehlen mit `base+batched` 25 der 38 Wörter in Beiträgen mit 1–3 Wörtern (`base`: 15–21), an H 13 von 43 (`base`: 7–9).
- **Die engere VAD trifft die Einwürfe.** Von den Wörtern, die die Batched-VAD entfernt, fehlen an den acht Referenzen 55 von 89.

### Was Punkt 1, 2 und 5 höchstens erreichen

| Punkt | zielt auf | Obergrenze mit `base` | Obergrenze mit `base+batched` |
| --- | --- | --- | --- |
| 1 und 2 | Überlappung | 18 % der Auslassungen, wenn in Überlappung kein Wort mehr fehlt; 10 %, wenn dort die Rate von außerhalb erreicht wird | 17 % und 9 % |
| 5 | Beiträge unter 2 s und Einwürfe | 16 % der Auslassungen (Beiträge unter 2 s), 9 % aus Einwürfen mit 1–3 Wörtern | 18 % und 11 % |

- **Punkt 1 und 2 bekommen nach diesen Zahlen keinen Messkandidaten.** Die realistische Obergrenze liegt bei rund 10 % der Auslassungen. Dem stehen der größte Umbau aller Punkte, kein Beleg für Deutsch und bei der Trennung ein belegtes Risiko für die übrigen 92 % der Wörter gegenüber ([Recherche](#punkt-1-sprecherbedingte-erkennung)).
- **Punkt 5 ist eine Messung wert, weil sie fast nichts kostet,** nicht weil die Obergrenze hoch wäre. Sie setzt dort an, wo `base+batched` schlechter ist als `base`: bei Einwürfen und bei Sprache, die die VAD verwirft. Was die Diarisierung nicht als Turn findet, erreicht auch dieser Weg nicht; dort liegen mit `base+batched` 14 % der Auslassungen. Ohne Fallback bliebe außerdem das Risiko des entgleisten Stücks.
- **Dringender als Punkt 1, 2 und 5 ist nach diesen Fenstern das entgleiste Stück.** Ein Block von 94 Wörtern wiegt mehr als alle Einwürfe einer Referenz zusammen. Die offene Frage aus der ersten Messung, ob sich ein solches Stück erkennen und einzeln neu dekodieren lässt, entscheidet darüber, ob die Batched-Pipeline überhaupt in Frage kommt.
- **Die Entscheidung fällt in Chunk 5** und liegt bei der Projektverantwortlichen.

## Orakel: `base` und `base+batched` kombinieren

Die beiden Läufe verlieren ihre Blöcke an verschiedenen Stellen: `base` an C, D und E, `base+batched` an H und I. Gemessen ist deshalb, was ein zweiter Lauf der anderen Variante höchstens zurückbringt (`seeds.py --with`, wie das Orakel in TOOL-102).

- **Orakel:** Für jede Auslassung des Hauptlaufs zählt, ob der zweite Lauf das Wort richtig hat. Die WER des Orakels setzt nur diese richtigen Wörter ein und nichts Falsches. Es ist eine Obergrenze: Ohne Referenz weiß niemand, welche Wörter richtig sind.
- **Blöcke:** dasselbe, beschränkt auf Auslassungen in Folgen ab 5 Referenzwörtern. Das ist die Obergrenze einer engen Regel, die nur Blöcke füllt.
- **Naive Vereinigung:** Was der zweite Lauf an einer Stelle mehr hat, kommt dazu, richtig oder falsch.

WER in Prozent, jeweils als Mittel über die drei Seeds von `base`:

| Referenz | `base` | `base+batched` | Hauptlauf `base+batched`, Blöcke aus `base` | Hauptlauf `base+batched`, alle Wörter aus `base` | Hauptlauf `base`, alle Wörter aus `base+batched` | naive Vereinigung (`base+batched` mit `base`) |
| --- | --- | --- | --- | --- | --- | --- |
| A | 21,3 | 19,6 | 19,6 | 18,2 | 19,2 | 20,3 |
| B | 29,8 | 25,4 | 25,3 | 24,8 | 28,4 | 27,8 |
| C | 30,8 | 25,9 | 25,2 | 23,8 | 25,3 | 26,2 |
| D | 61,2 | 36,3 | 35,9 | 35,1 | 45,7 | 44,9 |
| E | 34,0 | 29,0 | 29,0 | 28,1 | 28,6 | 30,0 |
| F | 28,4 | 26,4 | 25,7 | 25,0 | 26,6 | 26,0 |
| G | 36,0 | 39,6 | 37,7 | 36,8 | 33,8 | 40,7 |
| H | 36,5 | 53,6 | 38,4 | 37,4 | 32,4 | 40,1 |
| I | 27,2 | 33,2 | 25,0 | 24,3 | 24,9 | 26,6 |
| A bis H zusammen | 33,9 | 31,3 | 29,1 | 28,1 | 29,3 | 31,3 |

- **Die Kombination trägt als Obergrenze.** Mit `base+batched` als Hauptlauf und den Blöcken aus `base` fällt die WER über A bis H von 31,3 % auf 29,1 %, gegenüber `base` allein sind es 4,8 Punkte. Der Gewinn sitzt fast ganz an H (15 Punkte) und I (8 Punkte), an den übrigen Referenzen sind es höchstens 2.
- **Fast alles Rückholbare liegt in Blöcken.** An H hat `base` 75–78 der 149 fehlenden Wörter richtig, davon 70–74 in Folgen ab 5 Wörtern; an I 49–59 von 124, davon 45–56. Eine Regel, die nur Blöcke füllt, verschenkt gegenüber dem vollen Orakel einen Punkt.
- **Umgekehrt gilt dasselbe für die Blöcke von `base`.** An D hat `base+batched` 55–87 der 115–166 fehlenden Wörter richtig, an C in zwei von drei Seeds 66 und 79, an E in einem Seed 38. Mit `base` als Hauptlauf bleibt aber dessen Streuung: An D steht das Orakel immer noch bei 45,7 %.
- **`base+batched` ist der bessere Hauptlauf,** außer an G und H. Dort bleibt die Kombination auch als Orakel 1–2 Punkte über `base`, weil das Orakel nur Auslassungen füllt und die 40 und 43 Einfügungen von `base+batched` stehen lässt.
- **Die naive Vereinigung lohnt nicht,** wie in TOOL-102. Über A bis H landet sie bei 31,3 % und damit genau bei `base+batched` allein: Was sie an H und I gewinnt, verliert sie an B, D und G durch falsche Wörter. Je nach Seed von `base` kostet sie an D bis zu 22 Punkte.
- **Offen ist die Regel ohne Referenz.** Das Signal dafür gibt es: An H liegen 77 der 149 Auslassungen von `base+batched` an Stellen, an denen die Diarisierung Sprache hört und der Lauf kein Wort hat. Ob eine Regel „Sprache ohne Wörter über mehrere Sekunden, der zweite Lauf hat dort Text“ die Blöcke trifft, ohne an ruhigen Stellen falsche Wörter einzuschleppen, ist nicht gemessen. Daran ist TOOL-102 mit drei Seeds derselben Variante gescheitert; hier sind die Blöcke größer und die Läufe verschieden geschnitten.

## Messwerte

Die Tabellen kommen unverändert aus `asr.py score`. Nicht abgedruckt sind die Aufteilung nach Füllwörtern und der Sprecherfehler, der nur für diarisierte Wurzeln (`base`, `loud`) vorliegt.

### Pilotsitzung, Referenzen A, B, D und E

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 186e030dc24e | base, base+temp0, loud, base+batched, base+batched+ts, loud+batched |

| Variante | Seeds | Hotwords | WER A Mittel (Spanne) | Auslassungen A | WER B Mittel (Spanne) | Auslassungen B | WER D Mittel (Spanne) | Auslassungen D | WER E Mittel (Spanne) | Auslassungen E | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 21,3% (21,3%–21,3%) | 31/31/36 | 29,8% (25,6%–35,4%) | 44/42/45 | 61,2% (49,4%–81,5%) | 133/115/166 | 34,0% (29,8%–40,7%) | 43/46/78 | 33009 (32923–33067) | 0,7% (0,5%–0,8%) |
| base+temp0 | 3 | 48 | 29,8% (29,8%–29,8%) | 74/74/74 | 40,8% (40,8%–40,8%) | 100/100/100 | 52,8% (52,8%–52,8%) | 132/132/132 | 46,6% (46,6%–46,6%) | 55/55/55 | 33142 (33142–33142) | 8,9% (8,9%–8,9%) |
| loud | 3 | 48 | 20,2% (20,2%–20,2%) | 29/29/29 | 26,5% (26,5%–26,5%) | 42/42/42 | 36,7% (36,1%–38,1%) | 59/64/64 | 29,6% (29,5%–29,8%) | 30/30/30 | 33503 (33218–33672) | 0,6% (0,6%–0,7%) |
| base+batched | 3 | 48 | 19,6% (19,6%–19,6%) | 29/29/29 | 25,4% (25,4%–25,4%) | 38/38/38 | 36,3% (36,3%–36,3%) | 65/65/65 | 29,0% (29,0%–29,0%) | 40/40/40 | 32642 (32642–32642) | 1,0% (1,0%–1,0%) |
| base+batched+ts | 3 | 48 | 20,5% (20,5%–20,5%) | 32/32/32 | 25,4% (25,4%–25,4%) | 37/37/37 | 36,3% (36,3%–36,3%) | 55/55/55 | 28,7% (28,7%–28,7%) | 37/37/37 | 33134 (33134–33134) | 1,5% (1,5%–1,5%) |
| loud+batched | 3 | 48 | 18,8% (18,8%–18,8%) | 27/27/27 | 28,1% (28,1%–28,1%) | 39/39/39 | 38,3% (38,3%–38,3%) | 77/77/77 | 67,5% (67,5%–67,5%) | 96/96/96 | 32886 (32886–32886) | 1,7% (1,7%–1,7%) |

| Lauf | WER A (E/A/Ei) | WER B (E/A/Ei) | WER D (E/A/Ei) | WER E (E/A/Ei) |
| --- | --- | --- | --- | --- |
| base#1 | 21,3% (65/31/17) | 25,6% (61/44/8) | 49,4% (77/133/12) | 29,8% (62/43/5) |
| base#2 | 21,3% (64/31/18) | 28,3% (67/42/16) | 52,6% (98/115/23) | 31,4% (62/46/8) |
| base#3 | 21,3% (61/36/16) | 35,4% (81/45/30) | 81,5% (86/166/114) | 40,7% (63/78/9) |
| base+temp0#1 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| base+temp0#2 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| base+temp0#3 | 29,8% (69/74/15) | 40,8% (74/100/6) | 52,8% (75/132/30) | 46,6% (103/55/14) |
| loud#1 | 20,2% (61/29/17) | 26,5% (69/42/6) | 36,1% (93/59/10) | 29,5% (67/30/12) |
| loud#2 | 20,2% (61/29/17) | 26,5% (69/42/6) | 38,1% (87/64/20) | 29,8% (68/30/12) |
| loud#3 | 20,2% (61/29/17) | 26,5% (69/42/6) | 36,1% (85/64/13) | 29,5% (67/30/12) |
| base+batched#1 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched#2 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched#3 | 19,6% (60/29/15) | 25,4% (70/38/4) | 36,3% (87/65/11) | 29,0% (61/40/6) |
| base+batched+ts#1 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| base+batched+ts#2 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| base+batched+ts#3 | 20,5% (61/32/16) | 25,4% (70/37/5) | 36,3% (89/55/19) | 28,7% (61/37/8) |
| loud+batched#1 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |
| loud+batched#2 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |
| loud+batched#3 | 18,8% (57/27/16) | 28,1% (80/39/5) | 38,3% (84/77/11) | 67,5% (57/96/96) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen A | übersehen B | übersehen D | übersehen E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | 33067 | 0,8% | 14,5% | 699 / 1033 / 257 | 79,2% | 5 | 11 | 8 | 35 |
| base#2 | 33038 | 0,5% | 14,6% | 115 / 598 / 151 | 97,3% | 0 | 4 | 10 | 0 |
| base#3 | 32923 | 0,6% | 14,7% | 142 / 637 / 149 | 96,7% | 0 | 0 | 5 | 0 |
| base+temp0#1 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| base+temp0#2 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| base+temp0#3 | 33142 | 8,9% | 13,2% | 122 / 496 / 124 | 96,2% | 0 | 4 | 0 | 0 |
| loud#1 | 33620 | 0,6% | 13,9% | 777 / 1053 / 169 | 77,8% | 11 | 4 | 37 | 20 |
| loud#2 | 33672 | 0,7% | 13,8% | 202 / 598 / 110 | 95,0% | 0 | 0 | 2 | 0 |
| loud#3 | 33218 | 0,6% | 14,1% | 169 / 590 / 110 | 95,5% | 0 | 0 | 9 | 0 |
| base+batched#1 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched#2 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched#3 | 32642 | 1,0% | 13,8% | 22 / 442 / 15 | 96,2% | 15 | 0 | 44 | 0 |
| base+batched+ts#1 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| base+batched+ts#2 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| base+batched+ts#3 | 33134 | 1,5% | 13,8% | 442 / 623 / 125 | 88,4% | 24 | 16 | 41 | 4 |
| loud+batched#1 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |
| loud+batched#2 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |
| loud+batched#3 | 32886 | 1,7% | 13,7% | 17 / 443 / 21 | 97,2% | 0 | 4 | 0 | 0 |

| Lauf | ASR (min/h) | Diarisierung (min/h) | Peak-RAM (GiB) | Peak-VRAM (GiB, davor) |
| --- | --- | --- | --- | --- |
| base#1 | 1.25 | 0.77 | 13,9 | 4,0 (1,8) |
| base#2 | 1.28 | n/a | 13,9 | 3,6 (1,1) |
| base#3 | 1.30 | n/a | 13,8 | 3,6 (1,1) |
| base+temp0#1 | 0.98 | n/a | 13,9 | 3,8 (1,3) |
| base+temp0#2 | 0.98 | n/a | 13,9 | 3,7 (1,4) |
| base+temp0#3 | 0.99 | n/a | 13,9 | 3,7 (1,3) |
| loud#1 | 1.17 | 0.77 | 14,2 | 4,0 (1,6) |
| loud#2 | 1.19 | n/a | 14,1 | 4,0 (1,6) |
| loud#3 | 1.16 | n/a | 14,1 | 4,0 (1,6) |
| base+batched#1 | 0.38 | n/a | 4,4 | 4,8 (1,4) |
| base+batched#2 | 0.37 | n/a | 4,4 | 4,8 (1,5) |
| base+batched#3 | 0.37 | n/a | 4,3 | 4,8 (1,4) |
| base+batched+ts#1 | 0.71 | n/a | 4,3 | 4,7 (1,4) |
| base+batched+ts#2 | 0.66 | n/a | 4,3 | 4,7 (1,3) |
| base+batched+ts#3 | 0.66 | n/a | 4,3 | 4,7 (1,3) |
| loud+batched#1 | 0.35 | n/a | 4,4 | 4,7 (1,3) |
| loud+batched#2 | 0.38 | n/a | 4,3 | 4,6 (1,3) |
| loud+batched#3 | 0.38 | n/a | 4,3 | 4,6 (1,3) |

### Neue Fenster F, G, H und I

Dieselben Läufe wie in den übrigen Tabellen, gemessen an den neuen Fenstern. Zuerst F und G (Pilotsitzung), dann I (Pilotsitzung), dann H (zweite Sitzung).

| Variante | Seeds | Hotwords | WER F Mittel (Spanne) | Auslassungen F | WER G Mittel (Spanne) | Auslassungen G | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 28,4% (26,7%–31,0%) | 74/71/99 | 36,0% (33,4%–39,2%) | 72/70/48 | 33009 (32923–33067) | 0,7% (0,5%–0,8%) |
| base+temp0 | 3 | 48 | 47,1% (47,1%–47,1%) | 151/151/151 | 75,9% (75,9%–75,9%) | 74/74/74 | 33142 (33142–33142) | 8,9% (8,9%–8,9%) |
| loud | 3 | 48 | 27,5% (26,7%–27,9%) | 80/80/76 | 42,3% (39,7%–45,0%) | 73/95/87 | 33503 (33218–33672) | 0,6% (0,6%–0,7%) |
| base+batched | 3 | 48 | 26,4% (26,4%–26,4%) | 81/81/81 | 39,6% (39,6%–39,6%) | 74/74/74 | 32642 (32642–32642) | 1,0% (1,0%–1,0%) |
| base+batched+ts | 3 | 48 | 26,7% (26,7%–26,7%) | 77/77/77 | 53,4% (53,4%–53,4%) | 107/107/107 | 33134 (33134–33134) | 1,5% (1,5%–1,5%) |
| loud+batched | 3 | 48 | 26,7% (26,7%–26,7%) | 75/75/75 | 35,6% (35,6%–35,6%) | 59/59/59 | 32886 (32886–32886) | 1,7% (1,7%–1,7%) |

| Lauf | WER F (E/A/Ei) | WER G (E/A/Ei) |
| --- | --- | --- |
| base#1 | 27,4% (74/74/12) | 39,2% (108/72/36) |
| base#2 | 26,7% (75/71/10) | 35,4% (104/70/21) |
| base#3 | 31,0% (72/99/10) | 33,4% (115/48/21) |
| base+temp0#1 | 47,1% (59/151/65) | 75,9% (138/74/206) |
| base+temp0#2 | 47,1% (59/151/65) | 75,9% (138/74/206) |
| base+temp0#3 | 47,1% (59/151/65) | 75,9% (138/74/206) |
| loud#1 | 27,9% (71/80/12) | 42,1% (117/73/42) |
| loud#2 | 27,7% (70/80/12) | 45,0% (104/95/49) |
| loud#3 | 26,7% (68/76/12) | 39,7% (103/87/29) |
| base+batched#1 | 26,4% (63/81/10) | 39,6% (104/74/40) |
| base+batched#2 | 26,4% (63/81/10) | 39,6% (104/74/40) |
| base+batched#3 | 26,4% (63/81/10) | 39,6% (104/74/40) |
| base+batched+ts#1 | 26,7% (68/77/11) | 53,4% (120/107/67) |
| base+batched+ts#2 | 26,7% (68/77/11) | 53,4% (120/107/67) |
| base+batched+ts#3 | 26,7% (68/77/11) | 53,4% (120/107/67) |
| loud+batched#1 | 26,7% (63/75/18) | 35,6% (113/59/24) |
| loud+batched#2 | 26,7% (63/75/18) | 35,6% (113/59/24) |
| loud+batched#3 | 26,7% (63/75/18) | 35,6% (113/59/24) |

| Variante | Seeds | Hotwords | WER I Mittel (Spanne) | Auslassungen I | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 27,2% (26,6%–28,3%) | 70/66/82 | 33009 (32923–33067) | 0,7% (0,5%–0,8%) |
| base+temp0 | 3 | 48 | 39,4% (39,4%–39,4%) | 80/80/80 | 33142 (33142–33142) | 8,9% (8,9%–8,9%) |
| loud | 3 | 48 | 30,3% (30,3%–30,3%) | 60/60/60 | 33503 (33218–33672) | 0,6% (0,6%–0,7%) |
| base+batched | 3 | 48 | 33,2% (33,2%–33,2%) | 124/124/124 | 32642 (32642–32642) | 1,0% (1,0%–1,0%) |
| base+batched+ts | 3 | 48 | 26,3% (26,3%–26,3%) | 61/61/61 | 33134 (33134–33134) | 1,5% (1,5%–1,5%) |
| loud+batched | 3 | 48 | 31,7% (31,7%–31,7%) | 117/117/117 | 32886 (32886–32886) | 1,7% (1,7%–1,7%) |

| Lauf | WER I (E/A/Ei) |
| --- | --- |
| base#1 | 26,8% (78/70/12) |
| base#2 | 26,6% (79/66/14) |
| base#3 | 28,3% (69/82/18) |
| base+temp0#1 | 39,4% (84/80/71) |
| base+temp0#2 | 39,4% (84/80/71) |
| base+temp0#3 | 39,4% (84/80/71) |
| loud#1 | 30,3% (74/60/47) |
| loud#2 | 30,3% (74/60/47) |
| loud#3 | 30,3% (74/60/47) |
| base+batched#1 | 33,2% (61/124/13) |
| base+batched#2 | 33,2% (61/124/13) |
| base+batched#3 | 33,2% (61/124/13) |
| base+batched+ts#1 | 26,3% (81/61/15) |
| base+batched+ts#2 | 26,3% (81/61/15) |
| base+batched+ts#3 | 26,3% (81/61/15) |
| loud+batched#1 | 31,7% (59/117/13) |
| loud+batched#2 | 31,7% (59/117/13) |
| loud+batched#3 | 31,7% (59/117/13) |

| Variante | Seeds | Hotwords | WER H Mittel (Spanne) | Auslassungen H | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 36,5% (34,9%–37,2%) | 86/86/73 | 28927 (28896–28960) | 0,7% (0,5%–0,9%) |
| base+temp0 | 3 | 48 | 37,2% (37,2%–37,2%) | 86/86/86 | 27872 (27872–27872) | 9,2% (9,2%–9,2%) |
| loud | 3 | 48 | 32,8% (32,3%–33,2%) | 66/68/67 | 29878 (29767–30021) | 0,4% (0,4%–0,5%) |
| base+batched | 3 | 48 | 53,6% (53,6%–53,6%) | 149/149/149 | 29450 (29450–29450) | 1,2% (1,2%–1,2%) |
| base+batched+ts | 3 | 48 | 34,9% (34,9%–34,9%) | 51/51/51 | 30031 (30031–30031) | 2,6% (2,6%–2,6%) |
| loud+batched | 3 | 48 | 37,2% (37,2%–37,2%) | 70/70/70 | 29974 (29974–29974) | 1,6% (1,6%–1,6%) |

| Lauf | WER H (E/A/Ei) |
| --- | --- |
| base#1 | 37,2% (73/86/16) |
| base#2 | 37,2% (73/86/16) |
| base#3 | 34,9% (72/73/19) |
| base+temp0#1 | 37,2% (73/86/16) |
| base+temp0#2 | 37,2% (73/86/16) |
| base+temp0#3 | 37,2% (73/86/16) |
| loud#1 | 32,3% (71/66/15) |
| loud#2 | 33,2% (73/68/15) |
| loud#3 | 32,8% (72/67/15) |
| base+batched#1 | 53,6% (60/149/43) |
| base+batched#2 | 53,6% (60/149/43) |
| base+batched#3 | 53,6% (60/149/43) |
| base+batched+ts#1 | 34,9% (82/51/31) |
| base+batched+ts#2 | 34,9% (82/51/31) |
| base+batched+ts#3 | 34,9% (82/51/31) |
| loud+batched#1 | 37,2% (76/70/29) |
| loud+batched#2 | 37,2% (76/70/29) |
| loud+batched#3 | 37,2% (76/70/29) |

### Zweite Sitzung, Referenz C

| Modell | Revision | Snapshot | Varianten |
| --- | --- | --- | --- |
| large-v3-turbo | 0a363e9161cb | 8c3c941c5688 | base, base+temp0, loud, base+batched, base+batched+ts, loud+batched |

| Variante | Seeds | Hotwords | WER C Mittel (Spanne) | Auslassungen C | Wörter | Wiederholung |
| --- | --- | --- | --- | --- | --- | --- |
| base | 3 | 48 | 30,8% (27,3%–33,3%) | 80/156/177 | 28927 (28896–28960) | 0,7% (0,5%–0,9%) |
| base+temp0 | 3 | 48 | 47,9% (47,9%–47,9%) | 231/231/231 | 27872 (27872–27872) | 9,2% (9,2%–9,2%) |
| loud | 3 | 48 | 23,9% (23,2%–24,8%) | 88/92/88 | 29878 (29767–30021) | 0,4% (0,4%–0,5%) |
| base+batched | 3 | 48 | 25,9% (25,9%–25,9%) | 110/110/110 | 29450 (29450–29450) | 1,2% (1,2%–1,2%) |
| base+batched+ts | 3 | 48 | 32,2% (32,2%–32,2%) | 127/127/127 | 30031 (30031–30031) | 2,6% (2,6%–2,6%) |
| loud+batched | 3 | 48 | 23,7% (23,7%–23,7%) | 97/97/97 | 29974 (29974–29974) | 1,6% (1,6%–1,6%) |

| Lauf | WER C (E/A/Ei) |
| --- | --- |
| base#1 | 27,3% (111/80/57) |
| base#2 | 31,9% (110/156/24) |
| base#3 | 33,3% (93/177/33) |
| base+temp0#1 | 47,9% (126/231/78) |
| base+temp0#2 | 47,9% (126/231/78) |
| base+temp0#3 | 47,9% (126/231/78) |
| loud#1 | 23,9% (107/88/22) |
| loud#2 | 24,8% (112/92/21) |
| loud#3 | 23,2% (105/88/18) |
| base+batched#1 | 25,9% (91/110/34) |
| base+batched#2 | 25,9% (91/110/34) |
| base+batched#3 | 25,9% (91/110/34) |
| base+batched+ts#1 | 32,2% (94/127/72) |
| base+batched+ts#2 | 32,2% (94/127/72) |
| base+batched+ts#3 | 32,2% (94/127/72) |
| loud+batched#1 | 23,7% (92/97/26) |
| loud+batched#2 | 23,7% (92/97/26) |
| loud+batched#3 | 23,7% (92/97/26) |

| Lauf | Wörter | Wiederholung | verschiedene Wörter | confident / needs_review / uncertain | markierte Zeit | übersehen C |
| --- | --- | --- | --- | --- | --- | --- |
| base#1 | 28960 | 0,6% | 15,5% | 565 / 919 / 337 | 80,9% | 77 |
| base#2 | 28896 | 0,5% | 15,9% | 140 / 505 / 216 | 96,1% | 6 |
| base#3 | 28926 | 0,9% | 15,8% | 168 / 555 / 218 | 95,7% | 6 |
| base+temp0#1 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| base+temp0#2 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| base+temp0#3 | 27872 | 9,2% | 14,2% | 127 / 439 / 259 | 96,1% | 0 |
| loud#1 | 29846 | 0,5% | 14,7% | 681 / 964 / 245 | 79,7% | 67 |
| loud#2 | 30021 | 0,5% | 14,7% | 183 / 548 / 108 | 95,7% | 28 |
| loud#3 | 29767 | 0,4% | 14,7% | 219 / 562 / 149 | 95,0% | 28 |
| base+batched#1 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched#2 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched#3 | 29450 | 1,2% | 14,5% | 19 / 389 / 27 | 96,5% | 0 |
| base+batched+ts#1 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| base+batched+ts#2 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| base+batched+ts#3 | 30031 | 2,6% | 14,3% | 403 / 603 / 139 | 89,7% | 35 |
| loud+batched#1 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |
| loud+batched#2 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |
| loud+batched#3 | 29974 | 1,6% | 14,3% | 10 / 398 / 32 | 98,2% | 0 |

| Lauf | ASR (min/h) | Diarisierung (min/h) | Peak-RAM (GiB) | Peak-VRAM (GiB, davor) |
| --- | --- | --- | --- | --- |
| base#1 | 1.30 | 0.74 | 0,2 | 1,3 (1,3) |
| base#2 | 1.42 | n/a | 12,8 | 3,9 (1,3) |
| base#3 | 1.42 | n/a | 12,8 | 4,3 (1,3) |
| base+temp0#1 | 0.98 | n/a | 12,9 | 3,6 (1,3) |
| base+temp0#2 | 0.98 | n/a | 13,0 | 3,6 (1,3) |
| base+temp0#3 | 0.97 | n/a | 13,0 | 3,6 (1,3) |
| loud#1 | 1.14 | 0.76 | 13,1 | 4,0 (1,6) |
| loud#2 | 1.17 | n/a | 13,1 | 4,0 (1,6) |
| loud#3 | 1.16 | n/a | 13,1 | 4,0 (1,6) |
| base+batched#1 | 0.34 | n/a | 4,0 | 4,6 (1,3) |
| base+batched#2 | 0.34 | n/a | 4,1 | 4,6 (1,3) |
| base+batched#3 | 0.33 | n/a | 4,0 | 4,6 (1,3) |
| base+batched+ts#1 | 0.64 | n/a | 4,1 | 4,6 (1,3) |
| base+batched+ts#2 | 0.67 | n/a | 4,0 | 4,8 (1,3) |
| base+batched+ts#3 | 0.72 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#1 | 0.34 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#2 | 0.35 | n/a | 4,1 | 4,6 (1,3) |
| loud+batched#3 | 0.37 | n/a | 4,1 | 4,6 (1,3) |

### Orakel über `base` und `base+batched`

Aus `seeds.py --with base+batched`. Ein Paar mit denselben Wörtern wie ein früheres steht nur einmal da; die drei Seeds von `base+batched` sind identisch.

#### Referenz A

531 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 21,3% | 65 / 31 / 17 | 10 | 0 | 2 | 19 | 19,4% | 1,9 | 21,1% | 0,2 |
| base#2 | base+batched#1 | 21,3% | 64 / 31 / 18 | 9 | 0 | 2 | 20 | 19,6% | 1,7 | 21,3% | 0,0 |
| base#3 | base+batched#1 | 21,3% | 61 / 36 / 16 | 15 | 7 | 3 | 18 | 18,5% | 2,8 | 20,3% | 0,9 |
| base+batched#1 | base#1 | 19,6% | 60 / 29 / 15 | 7 | 0 | 3 | 19 | 18,3% | 1,3 | 20,5% | −0,9 |
| base+batched#1 | base#2 | 19,6% | 60 / 29 / 15 | 7 | 0 | 2 | 20 | 18,3% | 1,3 | 20,5% | −0,9 |
| base+batched#1 | base#3 | 19,6% | 60 / 29 / 15 | 9 | 0 | 2 | 18 | 17,9% | 1,7 | 19,8% | −0,2 |

#### Referenz B

441 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 25,6% | 61 / 44 / 8 | 6 | 2 | 8 | 30 | 24,3% | 1,4 | 24,3% | 1,4 |
| base#2 | base+batched#1 | 28,3% | 67 / 42 / 16 | 6 | 2 | 6 | 30 | 27,0% | 1,4 | 27,4% | 0,9 |
| base#3 | base+batched#1 | 35,4% | 81 / 45 / 30 | 6 | 1 | 7 | 32 | 34,0% | 1,4 | 35,6% | −0,2 |
| base+batched#1 | base#1 | 25,4% | 70 / 38 / 4 | 4 | 1 | 4 | 30 | 24,5% | 0,9 | 25,4% | 0,0 |
| base+batched#1 | base#2 | 25,4% | 70 / 38 / 4 | 3 | 0 | 5 | 30 | 24,7% | 0,7 | 27,0% | −1,6 |
| base+batched#1 | base#3 | 25,4% | 70 / 38 / 4 | 1 | 0 | 5 | 32 | 25,2% | 0,2 | 31,1% | −5,7 |

#### Referenz D

449 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 49,4% | 77 / 133 / 12 | 66 | 60 | 21 | 46 | 34,7% | 14,7 | 37,0% | 12,5 |
| base#2 | base+batched#1 | 52,6% | 98 / 115 / 23 | 55 | 49 | 17 | 43 | 40,3% | 12,2 | 43,7% | 8,9 |
| base#3 | base+batched#1 | 81,5% | 86 / 166 / 114 | 87 | 79 | 30 | 49 | 62,1% | 19,4 | 63,5% | 18,0 |
| base+batched#1 | base#1 | 36,3% | 87 / 65 / 11 | 6 | 3 | 13 | 46 | 35,0% | 1,3 | 36,5% | −0,2 |
| base+batched#1 | base#2 | 36,3% | 87 / 65 / 11 | 5 | 2 | 17 | 43 | 35,2% | 1,1 | 40,1% | −3,8 |
| base+batched#1 | base#3 | 36,3% | 87 / 65 / 11 | 5 | 0 | 11 | 49 | 35,2% | 1,1 | 58,1% | −21,8 |

#### Referenz E

369 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 29,8% | 62 / 43 / 5 | 10 | 3 | 6 | 27 | 27,1% | 2,7 | 30,1% | −0,3 |
| base#2 | base+batched#1 | 31,4% | 62 / 46 / 8 | 12 | 3 | 6 | 28 | 28,2% | 3,3 | 30,9% | 0,5 |
| base#3 | base+batched#1 | 40,7% | 63 / 78 / 9 | 38 | 31 | 11 | 29 | 30,4% | 10,3 | 31,2% | 9,5 |
| base+batched#1 | base#1 | 29,0% | 61 / 40 / 6 | 3 | 0 | 10 | 27 | 28,2% | 0,8 | 29,5% | −0,5 |
| base+batched#1 | base#2 | 29,0% | 61 / 40 / 6 | 3 | 0 | 9 | 28 | 28,2% | 0,8 | 30,4% | −1,4 |
| base+batched#1 | base#3 | 29,0% | 61 / 40 / 6 | 4 | 0 | 7 | 29 | 27,9% | 1,1 | 30,1% | −1,1 |

#### Referenz F

584 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 27,4% | 74 / 74 / 12 | 8 | 4 | 3 | 63 | 26,0% | 1,4 | 27,1% | 0,3 |
| base#2 | base+batched#1 | 26,7% | 75 / 71 / 10 | 4 | 0 | 3 | 64 | 26,0% | 0,7 | 26,7% | 0,0 |
| base#3 | base+batched#1 | 31,0% | 72 / 99 / 10 | 18 | 14 | 10 | 71 | 27,9% | 3,1 | 29,3% | 1,7 |
| base+batched#1 | base#1 | 26,4% | 63 / 81 / 10 | 11 | 6 | 7 | 63 | 24,5% | 1,9 | 25,7% | 0,7 |
| base+batched#1 | base#2 | 26,4% | 63 / 81 / 10 | 10 | 6 | 7 | 64 | 24,7% | 1,7 | 25,5% | 0,9 |
| base+batched#1 | base#3 | 26,4% | 63 / 81 / 10 | 4 | 0 | 6 | 71 | 25,7% | 0,7 | 26,7% | −0,3 |

#### Referenz G

551 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 39,2% | 108 / 72 / 36 | 16 | 7 | 10 | 46 | 36,3% | 2,9 | 44,1% | −4,9 |
| base#2 | base+batched#1 | 35,4% | 104 / 70 / 21 | 14 | 6 | 10 | 46 | 32,8% | 2,5 | 43,7% | −8,3 |
| base#3 | base+batched#1 | 33,4% | 115 / 48 / 21 | 6 | 1 | 6 | 36 | 32,3% | 1,1 | 39,2% | −5,8 |
| base+batched#1 | base#1 | 39,6% | 104 / 74 / 40 | 12 | 8 | 16 | 46 | 37,4% | 2,2 | 41,6% | −2,0 |
| base+batched#1 | base#2 | 39,6% | 104 / 74 / 40 | 13 | 8 | 15 | 46 | 37,2% | 2,4 | 41,0% | −1,5 |
| base+batched#1 | base#3 | 39,6% | 104 / 74 / 40 | 20 | 15 | 18 | 36 | 35,9% | 3,6 | 39,6% | 0,0 |

#### Referenz I

597 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 26,8% | 78 / 70 / 12 | 11 | 6 | 4 | 55 | 25,0% | 1,8 | 26,3% | 0,5 |
| base#2 | base+batched#1 | 26,6% | 79 / 66 / 14 | 10 | 7 | 4 | 52 | 25,0% | 1,7 | 26,5% | 0,2 |
| base#3 | base+batched#1 | 28,3% | 69 / 82 / 18 | 21 | 18 | 5 | 56 | 24,8% | 3,5 | 27,3% | 1,0 |
| base+batched#1 | base#1 | 33,2% | 61 / 124 / 13 | 49 | 45 | 20 | 55 | 25,0% | 8,2 | 26,3% | 6,9 |
| base+batched#1 | base#2 | 33,2% | 61 / 124 / 13 | 51 | 46 | 21 | 52 | 24,6% | 8,5 | 26,5% | 6,7 |
| base+batched#1 | base#3 | 33,2% | 61 / 124 / 13 | 59 | 56 | 9 | 56 | 23,3% | 9,9 | 27,0% | 6,2 |

#### Referenz C

909 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 27,3% | 111 / 80 / 57 | 5 | 1 | 6 | 69 | 26,7% | 0,6 | 28,4% | −1,1 |
| base#2 | base+batched#1 | 31,9% | 110 / 156 / 24 | 66 | 56 | 21 | 69 | 24,6% | 7,3 | 27,7% | 4,2 |
| base#3 | base+batched#1 | 33,3% | 93 / 177 / 33 | 79 | 74 | 23 | 75 | 24,6% | 8,7 | 26,5% | 6,8 |
| base+batched#1 | base#1 | 25,9% | 91 / 110 / 34 | 22 | 9 | 19 | 69 | 23,4% | 2,4 | 27,3% | −1,4 |
| base+batched#1 | base#2 | 25,9% | 91 / 110 / 34 | 16 | 4 | 25 | 69 | 24,1% | 1,8 | 25,9% | 0,0 |
| base+batched#1 | base#3 | 25,9% | 91 / 110 / 34 | 17 | 4 | 18 | 75 | 24,0% | 1,9 | 25,3% | 0,6 |

#### Referenz H

470 Referenzwörter

| Basis | zweiter Lauf | WER | E / A / Ei | Auslassungen: der zweite Lauf hat das Wort richtig | davon in Folgen ab 5 Wörtern | nur als Ersetzung | fehlt auch dort | WER Orakel | Gewinn (Punkte) | WER Vereinigung | Gewinn (Punkte) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base#1 | base+batched#1 | 37,2% | 73 / 86 / 16 | 21 | 10 | 8 | 57 | 32,8% | 4,5 | 34,5% | 2,8 |
| base#3 | base+batched#1 | 34,9% | 72 / 73 / 19 | 15 | 12 | 4 | 54 | 31,7% | 3,2 | 34,3% | 0,6 |
| base+batched#1 | base#1 | 53,6% | 60 / 149 / 43 | 75 | 70 | 17 | 57 | 37,7% | 16,0 | 40,2% | 13,4 |
| base+batched#1 | base#3 | 53,6% | 60 / 149 / 43 | 78 | 74 | 17 | 54 | 37,0% | 16,6 | 40,0% | 13,6 |
