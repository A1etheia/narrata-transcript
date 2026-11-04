# TOOL-20 — Sprecher-Diarisierung im Vergleich

Stand 2026-11-04. Spike-Bericht zu [TOOL-20](../plans/TOOL-20-diarisierung.md), Werkzeug unter [`scripts/spike/`](../../scripts/spike/README.md#diarisierung-tool-20). Alle Läufe liefen lokal und offline. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

*Folgt mit Chunk 4.*

## Material und Methode

| | |
| --- | --- |
| Testaufnahme | dieselbe wie in TOOL-62: 5:00:00 einer Sitzung, 4 Personen (Spielleitung und drei Mitspielende) |
| Ausschnitt | die 25:00 aus TOOL-62 |
| Handreferenz | die 3:00 aus TOOL-62 (300–480 s im Ausschnitt): 358 Wörter, Sprecherkennung pro Zeile, 2 Sprecher, 46 Wechsel, keine Zeiten |
| ASR-Zeiten | Whisper large-v3-turbo ohne Begriffsliste, Lauf aus TOOL-62 |
| Hardware | RTX 3080 Ti (12 GB VRAM), 20 Threads, 15 GB RAM in WSL2 |
| Versionen | pyannote.audio 4.0.7 (torch 2.14.1), NeMo 3.0.0 |

**Zuordnung zu Wörtern.** Beide Diarisierer liefern Turns (Start, Ende, Label), aber keine Wörter. Jedes Whisper-Wort erhält das Label des Turns, in dem seine Mitte liegt. Liegt sie in keinem Turn, bleibt das Wort ohne Label. Bei pyannote zählen dafür die exklusiven Turns, in denen immer nur eine Person spricht. Die Pipeline würde ebenso integrieren.

**Handreferenz.** Die Referenz hat keine Zeiten. Ihre Wörter werden deshalb an die Whisper-Wörter ausgerichtet und übernehmen deren Zeit. Gewertet werden nur die 244 der 358 Wörter (68 %), die Whisper exakt getroffen hat. Dadurch liegen nur 24 der 46 Wechsel zwischen zwei gewerteten Wörtern und sind überhaupt messbar. Die Kennzahlen:

- **WDER:** Anteil der gewerteten Wörter mit Label, die nach der besten 1:1-Zuordnung von Labels zu Sprechern beim falschen Sprecher landen. Ein überzähliges Label zählt vollständig als falsch.
- **ohne Label:** Anteil der gewerteten Wörter, deren Mitte in keinem Turn liegt.
- **Wechsel gefunden:** Referenzwechsel, bei denen der Diarisierer innerhalb der Toleranz ebenfalls das Label wechselt. *Zusätzlich* zählt Labelwechsel ohne Referenzwechsel in der Nähe.

## Kandidaten

| Kandidat | Ansatz | Lizenz | Einrichtung |
| --- | --- | --- | --- |
| Whisper large-v3-turbo | integriert | — | liefert keine Sprecher, damit keine integrierte Attribution |
| Granite Speech 4.1 2B Plus | integriert (`[Speaker N]:`) | Apache 2.0 | nicht getestet: läuft nach TOOL-62 nur in 90-s-Blöcken stabil und nummeriert Sprecher pro Block neu, stabile Labels über eine Sitzung sind damit ausgeschlossen |
| pyannote `speaker-diarization-community-1` | separat | pyannote.audio MIT, Modell CC-BY-4.0 (gated, einmaliger Download mit Token) | 5,9 GB venv |
| NeMo-Clustering-Diarizer | separat: MarbleNet-VAD, TitaNet-Embeddings auf sechs Skalen, Long-Form-Clustering | TitaNet CC-BY-4.0, MarbleNet NGC Terms of Use | vorhandene Parakeet-venv, Modelle von NGC |

## Ergebnisse

### Ausschnitt (25 min)

| Kandidat | Labels | Sprechanteile | Turns | Median-Turn | Overlap | Laufzeit | Spitzen-VRAM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pyannote | 4 | 43/20/19/18 % | 521 | 1,2 s | 7,6 % der Sprache | 20 s (77×) | 3,2–6,4 GB |
| NeMo | 4 | 44/20/18/17 % | 329 | 2,5 s | keiner (Modell kennt keinen) | 10–22 s (bis 149×) | 10,9–11,7 GB |

Beide finden ohne Vorgabe genau vier Labels. Mit `num_speakers 4` sind die Ergebnisse identisch. Wiederholte Läufe liefern dieselben Turns. Die VRAM-Werte messen die ganze Karte, auf der vor dem Lauf schon 4,2 GB belegt waren; NeMo kommt damit an die 12 GB heran.

### Handreferenz (3 min, 2 Sprecher)

| Kandidat | Labels im Abschnitt | WDER | ohne Label | Wechsel gefunden (±0,5 s) | zusätzlich | ±1 s: gefunden / zusätzlich |
| --- | --- | --- | --- | --- | --- | --- |
| pyannote | 3 | 16,5 % | 5,7 % | 6/24 | 15 | 11/24 / 9 |
| NeMo | 2 | 4,7 % | 13,5 % | 12/24 | 12 | 18/24 / 6 |

- **pyannote** vergibt im Abschnitt mit zwei Sprechern drei Labels. Fast die ganze WDER entsteht durch dieses dritte Label. Es trennt Wechsel schlecht und schneidet Turns kurz (Median 1,2 s).
- **NeMo** ordnet zugewiesene Wörter fast immer richtig zu und findet doppelt so viele Wechsel. Dafür fällt jedes siebte Wort in keinen Turn, vermutlich kurze Einwürfe unterhalb der VAD-Schwelle.
- **Übersprechen:** pyannote markiert 1,5 % des Abschnitts als Overlap, NeMo kann Overlap nicht abbilden. Die Referenz kennzeichnet Übersprechen nicht, daher ist offen, ob die 1,5 % stimmen.
- **Wechsel:** Bei schnellen Wechseln liegen beide eher daneben. Erst mit ±1 s findet NeMo drei Viertel der Wechsel. Die Wechsel in der Referenz sind dicht (46 in 3 min, also einer alle 4 s).

*Volle Aufnahme und Stichprobe folgen mit Chunk 3.*

## Entscheidung

*Folgt mit Chunk 4.*

## Offen

- Die Handreferenz enthält nur 2 der 4 Personen. Label-Stabilität über die Sitzung und NSC-Stimmen misst erst die Stichprobe über die volle Aufnahme.
