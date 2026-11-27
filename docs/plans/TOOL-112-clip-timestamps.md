# TOOL-112 — Spike: Dekodierung je Redebeitrag über `clip_timestamps` der Batched-Pipeline messen

## Ziel
`base+batched` verliert bei Einwürfen mit 1–3 Wörtern 43,4 % der Wörter (`base`: 35,5 %) und bei Wörtern ohne Turn 35,8 %, weil ihre enge VAD die Einwürfe trifft. Nach dem Ticket ist an den Referenzen A bis K gemessen, ob die Batched-Pipeline weniger auslässt, wenn sie statt der VAD die Turns der gespeicherten Diarisierung als Abschnitte bekommt. Ergebnis ist ein Spike-Dokument mit Go/No-Go nach einer vorab festgelegten Regel und, bei Go, ein Umsetzungsticket. Das Ergebnis legt den Hauptlauf fest, auf den TOOL-113 und TOOL-114 warten.

## Ist-Stand
- **Der Weg existiert in faster-whisper 1.2.1.** `BatchedInferencePipeline.transcribe` nimmt `clip_timestamps` als Liste von `{"start", "end"}` in Sekunden (`faster_whisper/transcribe.py:293`), überspringt dann die VAD und schneidet je Abschnitt (`:426`–`:451`). Über 30 s warnt sie nur und dekodiert die ersten 30 s. Die Zeiten bleiben über `offset` auf der Originalzeit; `restore_speech_timestamps` entfällt (`:573`). `duration_after_vad` ist die Summe der Abschnitte (`:453`).
- **Jeder Abschnitt kostet einen vollen Encoder-Durchgang** (`feature_extractor(chunk)` je Stück, `:464`). Die Diarisierung liefert Beiträge mit einem Median von 1,2 s, also ein Vielfaches der rund 480 VAD-Stücke eines Segments. Die Laufzeit ist damit selbst eine Messgröße.
- **`+batched` ist ein Stellvertreter um das Modell** (`scripts/spike/asr.py:778`, `_Batched`), eingesetzt in `_cli_with_variant` (`:707`, `:762`). Modifikatoren stehen in `MODIFIERS` (`:291`) und landen über `whisper.FIXED_SETTINGS` (`src/transcript/asr/whisper.py:54`, `:220`) in `asr.settings`; `transcribed` prüft sie beim Lesen (`scripts/spike/asr.py:942`). `+ts` ohne `+batched` ist ein Fehler (`:354`).
- **`prepare` baut je Variante und Seed eine Schattenwurzel** (`:414`) ohne Diarisierung. Die Diarisierung von Segment 1 liegt in der Hauptwurzel der Sitzung und ist auf dem Roh-WAV gerechnet; `omissions.diarized` liest sie (`scripts/spike/omissions.py:702`).
- **Verbundene Turns gibt es schon:** `Turns.joined` verbindet exklusive Turns gleichen Labels bis 500 ms Abstand (`omissions.py:49`, `:218`). `Ranges` trägt Vereinigung, Schnitt und Differenz (`:95`).
- **`omissions.py` rechnet für `+batched` die VAD nach** (`vad_speech`, `:284`) und bricht ab, wenn deren Summe nicht zu `duration_after_vad` des Laufs passt (`:745`). Für Abschnitte aus der Diarisierung gibt es keine VAD; an ihre Stelle treten die Abschnitte selbst.
- **Hauptlauf ist seit TOOL-109 `loudnorm`.** `norm` (Filter der Pipeline) und `loud` (Filter des Spikes) liefern Byte für Byte dasselbe WAV und dieselben Wortzahlen (`docs/spikes/TOOL-109-hauptlauf.md:9`). `chain_wav` kennt das gefilterte WAV nur für `loud` (`asr.py:517`); `norm` verlinkt das Roh-WAV.
- **Vergleichsläufe liegen im Hauptcheckout:** `base`, `loud`, `norm` (Seeds 1–3), `base+batched`, `loud+batched` für beide Sitzungen. Referenzen A, B, D, E, F, G, I an der Pilotsitzung, C, H, J, K an der zweiten (`docs/spikes/TOOL-108-blockverlust.md:28`).
- **Vergleichswerte:** WER im Mittel der elf Referenzen `base` 37,8 %, `norm` 30,2 %, `base+batched` 31,6 %, `loud+batched` 32,7 % (`docs/spikes/TOOL-109-hauptlauf.md:161`). `loud+batched` entgleist an E (67,5 %), `base+batched` an H (53,6 %, Block von 94 Wörtern).
- **Umgebung:** RTX 3080 Ti, 12 GB. Der Worktree hat weder `.venv` noch `work/`. Die Spike-Skripte haben keine Unit-Tests, `scripts/check` prüft sie mit ruff.

## Entscheidungen
- **Gemessen wird auf beiden Audios, die Go-Regel gilt gegen `norm`** (Entscheidung der Projektverantwortlichen, 2026-11-27). Rohaudio (`base+batched+…`) hält den Vergleich mit TOOL-104 und erfüllt das Ticket, `loudnorm`-Audio ist das, was die Pipeline heute bekommt.
- **Basis für `loudnorm` ist `loud`, nicht `norm`.** Das Audio ist identisch, `loud+batched` liegt schon vor, und `omissions.py` findet das gefilterte WAV nur über die Kette von `loud`.
- **Referenzen A bis K** (Entscheidung der Projektverantwortlichen, 2026-11-27). Summen laufen über A bis H, J und K. I steht wegen der gemeinsamen Minute mit F daneben, wie in TOOL-104.
- **Abschnitte kommen aus den exklusiven Turns der gespeicherten Diarisierung der Hauptwurzel,** für beide Audios dieselben (Roh-WAV, wie `norm` in TOOL-109). `prepare` rechnet sie und legt sie als `clips.json` in die Schattenwurzel; der Lauf liest nur diese Datei. Ein neues Modul `scripts/spike/clips.py` trägt die Regeln, damit `asr.py` und `omissions.py` sie ohne Kreisimport nutzen.
- **Fünf Varianten, vor der Messung festgelegt.** Alle setzen `+batched` voraus und teilen Abschnitte über 30 s.

  | Modifikatoren nach `+batched` | Abschnitte | Frage |
  | --- | --- | --- |
  | `+clips` | exklusive Turns, wie die Diarisierung sie liefert | der naive Weg: ein Stück je Turn |
  | `+clips+join` | gleiche Labels bis 500 ms Abstand verbunden (`JOIN_TURNS_MS`, TOOL-96) | Hilft es, zerstückelte Sätze einer Person zusammenzuhalten? |
  | `+clips+join+pad` | dazu 400 ms Polster je Seite | Fehlen Wortanfänge und -enden an den Turn-Grenzen? |
  | `+clips+join+pad+min` | dazu Mindestlänge 2 s | Schaden sehr kurze Stücke (Kontextverlust, Halluzination)? |
  | `+clips+pack` | verbunden und gepolstert, dann über Labels hinweg bis 30 s gepackt | Trennt die Abdeckung (Diarisierung statt VAD) vom Schnitt am Sprecherwechsel |

- **Regeln der Abschnitte:**
  - *Polster:* 400 ms wie `speech_pad_ms` der Pipeline-VAD, aber nur in freie Lücken und höchstens bis zur Mitte der Lücke zum Nachbarn. Abschnitte überschneiden sich nie, sonst stünden Wörter doppelt im Transkript.
  - *Mindestlänge:* Ein Abschnitt unter 2 s (`SHORT_TURN_MS`) geht im näheren Nachbarn auf, wenn die Lücke höchstens 1 s beträgt und beide zusammen unter 30 s bleiben. Sonst bleibt er stehen. Kein Abschnitt wird verworfen.
  - *Packen:* Aufeinanderfolgende Abschnitte werden zusammengelegt, solange die Lücke höchstens 2 s beträgt (Stille-Schwelle der Pipeline-VAD) und die Spanne unter 30 s bleibt.
  - *Teilen über 30 s:* an der größten Lücke zwischen den ursprünglichen Turns im Abschnitt; gibt es keine, an der Pause der Batched-VAD, die der Mitte am nächsten liegt (`vad-batched.json`); sonst in gleich lange Teile.
  - *Prüfung in `prepare`:* sortiert, überschneidungsfrei, keiner über 30 s, und die Vereinigung deckt jeden Turn. Ein Verstoß ist ein `SpikeError`.
- **Go-Regel, vor der Messung festgelegt.** Eine Variante auf `loudnorm`-Audio bekommt ein Umsetzungsticket, wenn alle vier Punkte gelten:
  1. Die Summe der Auslassungen über A bis H, J und K liegt unter der von `norm` (Mittel der drei Seeds) und unter der von `loud+batched`.
  2. Die Auslassungsrate in Beiträgen mit 1–3 Wörtern (Handreferenz) liegt über dieselben Referenzen unter der von `norm`.
  3. An keiner Referenz A bis K liegt die WER über dem schlechtesten einzelnen Lauf von `norm` an dieser Referenz, und an keiner fehlen 30 oder mehr Wörter am Stück.
  4. Die Summe der Einfügungen und der Wiederholungsanteil über das Segment liegen nicht über `norm`.

  Die Varianten auf Rohaudio sind Gegenprobe gegen `base` und `base+batched` und bekommen kein eigenes Go. Die Entscheidung liegt wie bei TOOL-103 und TOOL-104 bei der Projektverantwortlichen.
- **Seeds: Abweichung vom Ticket, begründet.** Die Batched-Pipeline hat keinen Fallback und würfelt nicht; in TOOL-104 waren alle Seeds Wort für Wort gleich. Weil ein Lauf je Redebeitrag ein Vielfaches der Encoder-Durchgänge braucht, laufen drei Seeds nur für `+clips+join` (beide Audios, beide Sitzungen) als Beleg. Alle übrigen Varianten laufen mit Seed 1. Weicht im Beleg ein Wort ab, laufen alle Varianten mit drei Seeds.
- **Laufzeit:** Chunk 1 misst sie am ersten Lauf von `+clips`. Braucht ein Lauf über 60 Minuten, hält die Messung an und die Projektverantwortliche entscheidet über den Umfang. Läufe aus dem Worktree wie in TOOL-101 bis TOOL-109: Python aus der `.venv` des Hauptcheckouts mit `PYTHONPATH=src`, `--config` auf dessen `config/config.yaml`, als Hintergrundbefehl nacheinander, nie parallel.
- **Der Pipeline-Code unter `src/` bleibt unverändert.** Die Umkehr der Reihenfolge von Erkennung und Diarisierung gehört ins Umsetzungsticket (Abgrenzung des Tickets).

## Daten-Check
- Läufe, `clips.json`, Kopien von Manifest und Snapshot: *handled* — alles bleibt unter `work/<s>/experiments/asr/` im Hauptcheckout (TOOL-66). Rohaudio verlässt den Rechner nicht.
- `clips.json`: *handled* — nur Zeiten in ms, Parameter und ein Hash der Diarisierung, keine Labels.
- Konsole und Logs: *handled* — nur Zähler, Anteile, WER, Zeiten und Abschnittszahlen. `SpikeError` nennt Variante, Seed und Clipname.
- Spike-Dokument und README: *handled* — nur Kennzahlen, Sitzungen heißen „Pilotsitzung“ und „zweite Sitzung“, Befehle nutzen `$S`. Chunk 3 und 4 prüfen mit `grep` gegen Session-Schlüssel, Gruppenname und Personennamen aus beiden Snapshots.
- Handreferenzen: *N/A*, weil keine neue entsteht; A bis K liegen unter `review/calibration/` im Hauptcheckout.
- Fixtures: *N/A*, weil keine angelegt werden.

## Contract-Check
*N/A*, weil das Ticket keine Contract-JSON liest oder schreibt. Bei Go klärt das Umsetzungsticket, ob der Contract (IOA-1214) Abschnitte aus der Diarisierung in `asr.settings` trägt.

## Resume-Check
- Abbruch beim Transkribieren: *handled* — die Wiederaufnahme der Pipeline gilt je Wurzel, ein neuer `run` überspringt fertige Wurzeln.
- Gleiches Modell und gleicher Snapshot: *handled* — `asr.transcribed` prüft Seed, Modell und Settings, neu auch die Abschnittsparameter. `check_provenance` bricht bei abweichender Revision oder abweichendem Snapshot ab.
- Gleiche Abschnitte: *handled* — `asr.settings` trägt einen Hash der Abschnittsliste. Ändert sich die Diarisierung oder eine Regel, passt der Hash nicht mehr und die Wurzel läuft neu.
- Vergleichsläufe: *handled* — `base`, `norm`, `loud`, `base+batched` und `loud+batched` werden wiederverwendet. Chunk 1 prüft die Kontrollwerte (21,3 % an A, 29,8 % an B für `base`).

## Dependency-Check
*handled* — `clip_timestamps` ist Teil des installierten faster-whisper 1.2.1 (MIT). Kein neues Paket, kein neues Modell, alles lokal auf der GPU. VRAM und Laufzeit misst `run.json`.

## Format-Check
*N/A*, weil sich kein internes Format und keine Versionsnummer ändert. Die neuen Schlüssel in `asr.settings` und `clips.json` entstehen nur in Spike-Wurzeln.

## Chunks
### Chunk 1 — Werkzeug: Abschnitte aus der Diarisierung und `+clips` in `asr.py`
- Dateien: `scripts/spike/clips.py` (neu), `scripts/spike/asr.py`
- Änderung:
  - `clips.py`: reine Funktionen für Verbinden, Polster, Mindestlänge, Packen und Teilen über 30 s, dazu die Prüfung (sortiert, überschneidungsfrei, höchstens 30 s, deckt jeden Turn)
  - `asr.py`: Modifikatoren `clips`, `join`, `pad`, `min`, `pack`; `clips` ohne `batched` und `join`/`pad`/`min`/`pack` ohne `clips` sind Fehler
  - `prepare` schreibt `clips.json` aus der Diarisierung der Hauptwurzel und gibt Zahl, Median und Summe der Abschnitte aus
  - `_Batched` reicht die Abschnitte als `clip_timestamps` durch; Parameter und Hash stehen in `asr.settings` und in der Prüfung von `transcribed`
- Verify: `scripts/check`. Im Hauptcheckout:
  - `asr.py score $S base --seeds 3` ergibt weiter 21,3 % (A) und 29,8 % (B); `base+batched` weiter 19,6 % (A)
  - `prepare` für alle fünf Varianten an beiden Sitzungen besteht die Prüfung
  - `run` für `base+batched+clips`, Seed 1, Pilotsitzung: Der Lauf endet, `asr.settings` trägt Parameter und Hash, `keywords_used` ist nicht leer, jede Wortzeit liegt in ihrem Abschnitt (Toleranz 1 s), `duration_after_vad` ist die Summe der Abschnitte
  - Laufzeit und VRAM aus `run.json` notiert
- AC: Modifikator im Spike-Wrapper, aufbauend auf `+batched`; Varianten vorab festgelegt.

### Chunk 2 — `omissions.py` für Läufe mit Abschnitten, README
- Dateien: `scripts/spike/omissions.py`, `scripts/spike/README.md` (Abschnitt „Redebeitrag-Spike (TOOL-112)“)
- Änderung:
  - Für `+clips`-Varianten liest `vad_speech` die Abschnitte aus `clips.json` statt eine VAD zu rechnen; die Prüfung gegen `duration_after_vad` bleibt
  - Das Merkmal „von der VAD entfernt“ zählt dort Wörter außerhalb der Abschnitte; „Fallback-Fenster“ und „dünnes Fenster“ heißen wie bei `+batched` „entfällt“
  - README: Varianten, Regeln der Abschnitte, Ablauf, Datenschutz
- Verify: `scripts/check`. Im Hauptcheckout:
  - `omissions.py $S` für `base` ergibt weiter 31/31/36 Auslassungen an A
  - `omissions.py $S --variant base+batched+clips --seeds 1` läuft durch; die Auslassungen an A stimmen mit `asr.py score` überein
- AC: Auslassungsrate je Klasse für die neuen Varianten messbar.

### Chunk 3 — Messung an A bis K
- Dateien: `docs/spikes/TOOL-112-redebeitrag.md` (neu)
- Änderung:
  - `asr.py run` für die fünf Varianten auf `base` und `loud`, beide Sitzungen, Seeds nach der Entscheidung oben
  - `asr.py score` gegen `base`, `base+batched`, `norm`, `loud+batched` an A bis K: WER, Auslassungen, Einfügungen, Wiederholungsanteil
  - `omissions.py` je Variante: Auslassungsrate in Überlappung, Beitrag unter 2 s, kein Turn, Beitrag mit 1–3 Wörtern; längste Folge ausgelassener Wörter
  - `asr.py sections --against base`: Wortzahl und Abschnitte mit Defizit über das Segment
  - Bericht: Material und Methode mit der Go-Regel im Wortlaut, Abschnittsstatistik je Variante (Zahl, Median, Anteil unter 2 s, Abdeckung in Minuten gegen VAD), Messtabellen, Laufzeit und VRAM, Beleg zu den Seeds
- Verify: `scripts/check`. Tabellen 1:1 aus dem Skript. Die Auslassungen aus `omissions.py` stimmen je Lauf mit `asr.py score` überein. `grep` im Bericht gegen Session-Schlüssel, Gruppenname und Personennamen ergibt keinen Treffer.
- AC: WER, Auslassungen, Einfügungen und Wiederholungsanteil je Variante an den Referenzen, dazu die vier Klassen; alles lokal, nur Kennzahlen.

### Chunk 4 — Auswertung, Go/No-Go, Übergaben
- Dateien: `docs/spikes/TOOL-112-redebeitrag.md`, `docs/plans/TOOL-112-clip-timestamps.md` (Folge-Tickets nachtragen)
- Änderung:
  - Kurzfassung und Regeltabelle: jeder der vier Punkte je Variante mit Zahl
  - Abschnitt „Was der Weg nicht erreicht“: Wörter ohne Turn der Diarisierung, mit Wortzahl und Anteil an den Auslassungen
  - Hinweis für eine Umsetzung: Reihenfolge von Diarisierung und Erkennung, Passagenzuschnitt und Bewertung, Laufzeit
  - Entscheidung der Projektverantwortlichen einholen und mit Datum eintragen; bei Go das Umsetzungsticket im Epic TOOL-100 anlegen
  - Kommentare an TOOL-113 und TOOL-114 (Hauptlauf) und an TOOL-100
- Verify: `scripts/check`. Jede Aussage der Kurzfassung verweist auf eine Tabelle. Jeder Eintrag unter „Folge-Tickets“ trägt einen Key oder `[kein Ticket: …]`. `grep` wie in Chunk 3.
- AC: Spike-Dokument mit Go/No-Go nach der vorab festgelegten Regel; benannt, was der Weg nicht erreicht; bei Go ein Umsetzungsticket.

## Folge-Tickets
- Umsetzung der Dekodierung je Redebeitrag in der Pipeline: [kein Ticket: No-Go vom 2026-11-27, `norm` bleibt Hauptlauf]
- Lauf je Redebeitrag als Zusatzlauf nur für kurze Beiträge: [kein Ticket: Obergrenze 19 % der Auslassungen, die Auswahlregel ist die Frage von TOOL-114; Befund dort kommentiert]
- TOOL-113 (auffälliges Stück neu dekodieren): Kommentar vom 2026-11-27 mit dem Hauptlauf und den Blockverlusten der neuen Varianten.
- TOOL-114 (Blöcke aus einem zweiten Lauf): Kommentar vom 2026-11-27 mit dem Hauptlauf und der Obergrenze eines Zusatzlaufs.
- TOOL-100: Kommentar vom 2026-11-27 mit dem Ergebnis.
- Großzügigere VAD für die Batched-Pipeline (offen aus TOOL-104): [kein Ticket: erledigt; `+clips+pack` dekodiert 18 bis 21 min mehr als die VAD der Pipeline und verliert trotzdem Blöcke]
- Roadmap führt TOOL-109 noch als „läuft“: [kein Ticket: `/close-ticket` aktualisiert die Roadmap]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Werkzeug: `clips.py`, `+clips` und Varianten in `asr.py`, erster Lauf | no |
| 2 | `omissions.py` für Läufe mit Abschnitten, README | yes |
| 3 | Messung an A bis K auf beiden Audios, Messtabellen | no |
| 4 | Auswertung, Go/No-Go, Übergaben | no |
