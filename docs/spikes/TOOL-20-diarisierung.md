# TOOL-20 — Sprecher-Diarisierung im Vergleich

Stand 2026-11-04. Spike-Bericht zu [TOOL-20](../plans/TOOL-20-diarisierung.md), Werkzeug unter [`scripts/spike/`](../../scripts/spike/README.md#diarisierung-tool-20). Alle Läufe liefen lokal und offline. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel.

## Kurzfassung

- **Entscheidung V0.1: separate Diarisierung mit pyannote `speaker-diarization-community-1`.** Whisper turbo liefert keine Sprecher, eine integrierte Attribution gibt es also nicht.
- **Labels sind stabil:** über fünf Stunden genau 4 Labels für 4 Personen, alle in jeder halben Stunde aktiv. In einer blinden Stichprobe gehört jedes Label mehrheitlich genau einer Person, 8 % der Segmente liegen falsch.
- **NSC-Stimmen** der Spielleitung bekommen kein eigenes Label; 3 von 4 bleiben bei ihr.
- **NeMo** ist auf dem Ausschnitt genauer (WDER 4,7 % gegen 16,5 %), braucht auf einer ganzen Sitzung aber über 25 GB RAM und fällt damit aus. Einen Fallback für ganze Sitzungen gibt es nicht.
- **Kosten:** pyannote braucht auf fünf Stunden 4 Minuten, 3,8 GB VRAM und 13,8 GB RAM. Es darf nicht parallel zu Whisper laufen.

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

### Volle Aufnahme (5:00:00)

| Kandidat | Ergebnis | Laufzeit | Spitzen-RAM | Spitzen-VRAM |
| --- | --- | --- | --- | --- |
| pyannote | 4 Labels, Anteile 36/24/21/19 %, 4.985 Turns, Median 1,2 s, Sprache 68 % der Aufnahme, Overlap 4,2 % der Sprache | 4:13 min (71×) | 13,8 GB | 3,8 GB |
| NeMo | Abbruch durch das OOM-Kill des Kernels im Clustering, bei 15 GB und bei 25 GB RAM | — | über 25 GB | — |

- **pyannote bleibt über fünf Stunden bei vier Labels.** Kein Label liegt unter 1 % Sprechzeit, und alle vier sind in jedem der zehn Halbstunden-Fenster mit mindestens 30 s aktiv. Die Labels zerfallen also nicht über die Zeit. `num_speakers 4` ändert nichts, das Modell findet die Zahl selbst.
- **NeMo ist für ganze Sitzungen nicht tragfähig.** VAD und Embeddings auf allen sechs Skalen kommen mit 2,5 GB aus. Erst das Clustering wächst über 25 GB, trotz Long-Form-Clustering, und auch mit halbierter Chunk-Größe (5.000 statt 10.000 Embeddings) bei 15 GB. In Blöcken liefe es zwar, aber jeder Block vergibt eigene Labels, und genau die Stabilität über die Sitzung ginge verloren.
- **RAM bei pyannote:** 13,8 GB auf fünf Stunden. Mit dem Standard-Limit von WSL (15 GB) ist das knapp. Whisper braucht nach TOOL-62 bis 10,5 GB, deshalb dürfen beide nicht gleichzeitig laufen.

### Stichprobe (30 Segmente, pyannote)

Pro 10-Minuten-Fenster ein zufälliges Whisper-Segment von 2–10 s, also unabhängig vom Diarisierer und über die ganze Sitzung verteilt. Die Projektverantwortliche hat alle 30 blind angehört; die Labels kannte sie dabei nicht.

| | |
| --- | --- |
| gewertet | 24 von 30; 6 (20 %) waren Übersprechen oder nicht eindeutig einer Person zuzuordnen |
| Personen in der Stichprobe | alle 4 |
| Labels in der Stichprobe | 4, jedes Label gehört mehrheitlich genau einer Person |
| Fehlzuordnungen | 2 von 24 (8 %) |
| Labels pro Person | Spielleitung 2, eine mitspielende Person 2, die anderen beiden je 1 |
| Anteil der Segmente auf dem eigenen Label | 8/9, 5/6, 5/5, 4/4 |
| NSC-Stimmen der Spielleitung | 4 Segmente; 3 auf ihrem eigenen Label, 1 auf dem Label einer mitspielenden Person |

Die beiden Fehler sind spiegelbildlich: ein NSC-Segment der Spielleitung landet auf dem Label einer mitspielenden Person, und ein Segment dieser Person auf dem Label der Spielleitung. Ein eigenes Label für NSC-Stimmen entsteht nicht. Die Stichprobe ist klein, ±6 Prozentpunkte sind bei 24 Segmenten Rauschen.

**Label-Stabilität als Zahl:** 1 Label pro realer Person, 4 Labels für 4 Personen über fünf Stunden, 8 % Fehlzuordnung in der Stichprobe.

## Entscheidung

**V0.1: separate Diarisierung mit pyannote `speaker-diarization-community-1`**, als eigener Schritt nach der Transkription, ohne Vorgabe der Personenzahl.

- Einziger Kandidat, der eine ganze Sitzung verarbeitet.
- Stabile Labels über fünf Stunden; TOOL-68 bleibt eine 1:1-Zuordnung von wenigen Labels zu Personen.
- Liefert exklusive Turns für die Zuordnung zu Wörtern und Overlap als eigene Information.
- `num_speakers` ändert auf diesem Material nichts. Der Snapshot kann die Zahl liefern, Pflicht ist sie nicht.

**Kein Fallback für ganze Sitzungen.** NeMo ginge nur in Blöcken und verlöre dabei die Stabilität der Labels. Falls pyannote auf anderem Material versagt, ist das ein neuer Spike, kein Konfigurationswechsel.

**Wortlaut und Zeitstempel:** Die Diarisierung läuft getrennt von der Transkription und lässt die Whisper-Wörter und ihre Zeiten unverändert. Sie fügt nur ein Label pro Wort hinzu. Bei schnellen Wechseln liegt die Turngrenze im Test oft mehr als 0,5 s neben dem Wechsel in der Referenz. Ein Wort an einer Grenze kann deshalb beim falschen Sprecher landen.

**Integration in das Referenzformat (TOOL-16), Aufwand 1,5 Tage als TOOL-76:**

- optionales Sprecher-Label pro Wort; „kein Label“ ist ein gültiger Wert (6–14 % der Wörter im Test),
- Segment-Label aus der Mehrheit der Wörter, Wechsel innerhalb eines Segments bleiben sichtbar,
- Label-Menge und Diarisierungs-Metadaten (Modell-Revision, Einstellungen) getrennt von den ASR-Metadaten,
- Overlap-Bereiche optional als eigene Information.

## Folgearbeiten

- `TOOL-76`: pyannote in die Pipeline integrieren (neu, 1,5 Tage, nach TOOL-64).
- `TOOL-16`: Sprecherfeld pro Wort, Diarisierungs-Metadaten.
- `TOOL-64`: nicht parallel zu pyannote laufen lassen, Wortzeiten bleiben an.
- `TOOL-68`: Labels 1:1 zuordnen; Wörter ohne Label durchreichen.

## Offen

- Die Handreferenz enthält nur 2 der 4 Personen; Label-Stabilität und NSC-Stimmen beruhen allein auf der Stichprobe mit 24 gewerteten Segmenten.
- Übersprechen: Jedes fünfte Segment der Stichprobe war nicht eindeutig einer Person zuzuordnen. Ob pyannotes Overlap-Turns (4,2 % der Sprache) diese Stellen treffen, ist nicht gemessen.
- Nur eine Sitzung einer Gruppe ist getestet. Andere Gruppen, Mikrofonaufstellungen oder mehr Personen können anders ausfallen.
