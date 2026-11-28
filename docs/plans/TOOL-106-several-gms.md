# TOOL-106 — Mehrere Spielleitungen im Export als getrennte Sprecher führen

## Ziel
Eine Runde mit zwei Spielleitungen (SL) soll im Export zwei Sprecher-Labels haben, jedes mit eigener `participant_id`, und das soll belegt und durch einen Test gesichert sein. Außerdem liest die Pipeline aus dem Transkriptionskontext 1.5 (IOA-1342) `session_role` und `session_character` und zeigt beim Zuordnen, wer an diesem Abend SL war und welche Figur jemand führte. Bisher kennt die Pipeline nur die gruppenweite Rolle.

## Ist-Stand
- **Ursache gefunden, sie liegt nicht in der Pipeline.** In der Pilotsitzung 022 hat die Zuordnung je Segment ein eigenes Label pro SL (Segment 1: SL 1, SL 2 und 2 Mitspielende; Segment 2: SL 1, SL 2 und 1 Mitspielende\*r). Der Export `output/…/022/transcript.json` (Contract 1.1) enthält 8 Labels: je 2 pro SL, 3 für Mitspielende, 1 `null`. Die Passagen verteilen sich auf SL 1 mit 542, SL 2 mit 665, Mitspielende mit 932 und ohne Person mit 27. Gezählt wurde lokal, ohne Namen.
- Die Kette trennt sauber: `speakers.SpeakerMap.resolve` (`src/transcript/speakers.py:141`) ordnet je (Segment, Label) zu, `export.build` (`src/transcript/export.py:122-127`) macht daraus `s<NN>-<label>` mit eigener `participant_id`. Zusammengelegt wird nur, wenn jemand zwei Labels *derselben* Person zuordnet; der Dialog fragt dann nach (`speaker_assign._confirm_merge`, `src/transcript/speaker_assign.py:195`).
- Das „SL“ in Narrata kam aus `TranscriptWindowContent::speakerName`, das jede SL der Gruppe pauschal `SL` nannte (ios-archiv, `app/Support/Extraction/Transcripts/TranscriptWindowContent.php:189`). Das behebt IOA-1341 (Done) mit `SL (Name)`.
- 017 ist noch nicht zugeordnet (alle Labels `open`) und deshalb kein Prüffall.
- Kontext: `narrata._participant` (`src/transcript/narrata.py:298`) liest `role`, `is_former`, `present` (seit 1.3) und `characters`. `session_role` und `session_character` werden ignoriert. Eine 1.5 wird trotzdem angenommen, denn `SUPPORTED_MAJOR = 1` (`narrata.py:35`).
- Der Snapshot `knowledge._participant_json` (`src/transcript/knowledge.py:300`) schreibt `present` nur, wenn es gesetzt ist, damit ein älterer Kontext seine `snapshot_id` behält. Nach diesem Muster kommen die neuen Felder dazu.
- Wer die Rolle anzeigt: `speaker_assign._Dialogue.__init__` (`speaker_assign.py:102-109`), die Tabelle in `speaker_samples.py:141-149`, die Kontext-Zusammenfassung in `__main__.py:537-544`.
- Messwerkzeug: `scripts/spike/denoise.py:430` `_wder` mit `best_mapping`, Fenster per `--clip NAME=FILE@span` (`scripts/spike/asr.py:932` `parse_clip`). Handreferenzen liegen lokal unter `work/…/022/review/calibration/`.

## Entscheidungen
- **Keine Änderung an Export, Zuordnung oder Diarisierung.** Sie trennen schon richtig. Ein Regressionstest hält fest, dass zwei SL zwei Labels mit je eigener `participant_id` bleiben.
- **Umfang inklusive Kontext 1.5** (so mit der Projektverantwortlichen entschieden). `Participant` bekommt `session_role: Role | None` und `session_character: Character | None` sowie die Properties `role_tonight` (`session_role` oder `role`) und `character_tonight`. Gruppenweite `role` und `characters` bleiben unverändert.
- **Verwendung nur in der Sprecherführung:** Dialog, `samples.md`, Zusammenfassung von `context`. Das ASR-Prompt und die Hotwords ändern sich nicht. Sonst würde sich das Erkennungsergebnis bestehender Läufe verschieben, und das hat der Übergabe-Kommentar nicht verlangt.
- **Messung mit Kennzahlen.** Für jede Handreferenz-Fenster mit beiden SL wird gezählt, wie viele exakt erkannte Wörter jeder SL unter einem Label der jeweils anderen SL stehen (Verwechslung SL↔SL) bzw. unter einem Label von Mitspielenden. Hand-Sprecher werden Personen über `best_mapping` zugeordnet, nicht über Namen. Die Rolle kommt aus dem Snapshot. Die beiden SL heißen im Bericht „SL 1“ und „SL 2“, sortiert nach Sprechanteil.

## Daten-Check
- Fixtures: *handled* — Die Tests bauen Kontext und Teilnehmende inline mit erfundenen Namen und IDs, wie in `tests/test_narrata.py`. Es kommt keine echte Datei ins Repo.
- Logs und Fehlermeldungen: *handled* — Neue Validierungsfehler nennen Datei und Feld (`participants[i].session_role`), nie einen Wert, wie bei `_invalid`.
- Messbericht: *handled* — Er enthält nur Kennzahlen, keine Namen, keine Labels, keinen Session-Schlüssel, keine Zeitspannen der Fenster (TOOL-66, Muster TOOL-96). Die Fensterspannen kommen als CLI-Argument und stehen nicht im Skript.
- Konsole: *handled* — Der Zuordnungsdialog zeigt wie bisher Namen und nur im interaktiven Terminal. Die Figur des Abends kommt dazu, sie steht in derselben Schutzklasse wie `characters`.

## Contract-Check
- Export-Contract (IOA-1214): *N/A, weil* sich weder Export noch Version ändern. 022 bleibt 1.1, eine Sitzung mit einer Aufnahme bleibt 1.0. Das AC „Contract v1 bleibt gültig“ ist damit erfüllt.
- Transkriptionskontext: *handled* — Gelesen wird nach der Spezifikation in `ios-archiv/docs/transcripts.md` → „Transkriptionskontext“ (1.5, IOA-1342): Jedes der beiden Felder ist für sich `null` oder fehlt (vor 1.5), dann gelten `role` bzw. `characters`. `session_character` hat die Form eines `characters`-Eintrags und darf eine Figur nennen, die dort nicht steht. Ein falscher Typ ist ein `NarrataContextError`.
- Narrata-Änderung: *N/A, weil* IOA-1341 und IOA-1343 Done sind und das Ticket keine Narrata-Änderung vorsieht.

## Resume-Check
- *N/A, weil* kein lang laufender oder modellgestützter Schritt dazukommt. Die Messung liest nur gespeicherte Dateien. Beim Zuordnen gilt wie bisher: Jede Wahl wird sofort gespeichert.

## Dependency-Check
- *N/A, weil* weder eine Abhängigkeit noch ein Modell dazukommt.

## Format-Check
- Snapshot (`SNAPSHOT_FORMAT_VERSION = 1`): *handled* — Die Felder sind additiv und optional und werden nur geschrieben, wenn sie nicht `null` sind, wie `present` seit TOOL-79. Kein Bump: Bestehende Snapshots laden unverändert und behalten ihre `snapshot_id`. Ein neu geholter 1.5-Kontext mit gesetzten Feldern ergibt eine andere `snapshot_id`; `_warn_if_snapshot_differs` (`__main__.py:552`) meldet das, ersetzt aber nichts.
- Zuordnungsdatei (`ASSIGNMENT_FORMAT_VERSION = 1`): *N/A, weil* sie sich nicht ändert.

## Chunks

### Chunk 1 — Regressionstest zwei SL
- Dateien: `tests/test_export.py`, `tests/test_speakers.py`
- Änderung: Je ein Test. Erstens: Zwei SL-Teilnehmende in einem Segment, je einem Label zugeordnet, ergeben in `export.build` zwei `speakers`-Einträge mit verschiedener `participant_id` und `display_name`, und ihre Passagen tragen die eigene `participant_id`. Zweitens: `SpeakerMap.persons()` hält die beiden auseinander, `splits` ist leer.
- Verify: `scripts/check`
- AC: Ein Export mit zwei SL hat zwei Labels mit je eigener `participant_id`, durch einen Test belegt.

### Chunk 2 — Messung an 022 und Bericht
- Dateien: `scripts/spike/gms.py` (neu), `scripts/spike/README.md`, `docs/spikes/TOOL-106-spielleitungen.md` (neu)
- Änderung: Das Skript liest Manifest, Referenztranskripte, Zuordnung (`speakers.check`) und Snapshot. Es zählt je SL Labels, Passagen und Sprechzeit über die ganze Sitzung. Für jedes `--clip` mit beiden SL rechnet es die Matrix Hand-Sprecher × zugeordnete Person (Passagen-Label wie im Export, Abbildung der Hand-Sprecher über `denoise.best_mapping`) und gibt die Verwechslung SL↔SL in % mit n aus. Wiederverwendet werden `denoise._wder`-Logik und `HandClip`, Fenster kommen über `asr.parse_clip`. Der Bericht enthält Kennzahlen, Methode, Grenzen und ein Ergebnis gegen das AC „nach Label trennbar“. Liegt die Verwechslung SL↔SL deutlich über dem Sprecherfehler aus TOOL-96 (≈ 4–6 %), wird ein Folge-Ticket für die Diarisierung angelegt, sonst `[kein Ticket: …]`.
- Verify: `scripts/check`, dann das Skript lokal gegen 022 mit den Fenstern A–K
- AC: Prüfung an einer Sitzung mit beiden SL ist dokumentiert, nur Kennzahlen. Es steht fest, ob die Diarisierung allein genügt.

### Chunk 3 — Kontext 1.5 lesen und im Snapshot halten
- Dateien: `src/transcript/narrata.py`, `src/transcript/knowledge.py`, `tests/test_narrata.py`, `tests/test_knowledge.py`
- Änderung: `Participant.session_role` und `.session_character` (Default `None`) sowie die Properties `role_tonight` und `character_tonight`. `_participant` validiert beide Felder (`session_role` in `_ROLES` oder `null`, `session_character` über `_character` oder `null`). Den Docstring auf 1.5 nachziehen. `_participant_json` schreibt beide nur, wenn sie gesetzt sind. Tests: 1.5 mit gesetzten Feldern, mit `null`, ohne Felder (1.4), falscher Typ wird abgelehnt, der Snapshot hält die Werte über einen Round-Trip, und ohne Felder bleibt die `snapshot_id` gleich.
- Verify: `scripts/check`
- AC: Ein 1.5-Kontext wird gelesen, ein 1.4-Kontext ergibt denselben Snapshot wie bisher.

### Chunk 4 — Rolle und Figur des Abends in der Sprecherführung
- Dateien: `src/transcript/speaker_assign.py`, `src/transcript/speaker_samples.py`, `src/transcript/__main__.py`, Tests `tests/test_speaker_assign.py`, `tests/test_speaker_samples.py`; README bzw. `docs/ablauf.md`, wo die Kontextfelder oder die `context`-Ausgabe beschrieben sind
- Änderung: Die Dialogzeile zeigt `role_tonight` und, wenn gesetzt, die Figur des Abends (z. B. `(gm tonight, plays …)`, die genaue Form legt der Test fest). Die `samples.md`-Tabelle bekommt Spalten für Rolle und Figur des Abends. Die Zusammenfassung von `context` zählt SL nach `role_tonight` und nennt, wie viele Einträge eine Sitzungsrolle oder -figur tragen. Die Reihenfolge der Personen bleibt (anwesend zuerst).
- Verify: `scripts/check`; danach manuell im interaktiven Terminal: `context` für 022 holt den 1.5-Kontext und zeigt die neuen Zähler, `speakers --assign --all` zeigt die Rolle des Abends
- AC: Wer an dem Abend SL war und welche Figur jemand führte, sieht man beim Zuordnen. Fehlt das Feld, bleibt die Ausgabe wie bisher.

## Folge-Tickets
- Verwechslung SL↔SL durch die Diarisierung `[kein Ticket: Chunk 2 misst 0,8 % bzw. 5,6 %, unter dem Sprecherfehler aus TOOL-96; siehe docs/spikes/TOOL-106-spielleitungen.md]`.
- Wörter von SL 1 unter Labels der Mitspielenden (24 %) `[kein Ticket: allgemeiner Sprecherfehler, kein Problem zweier SL; TOOL-105 misst ihn neu]`.
- `session_character` im ASR-Prompt bzw. in den Hotwords `[kein Ticket: nicht verlangt; erst sinnvoll, wenn eine Sitzung eine Figur führt, die nicht in characters steht, und das würde das Erkennungsergebnis bestehender Läufe verschieben]`.
- Rückwirkende Trennung bereits importierter Sitzungen `[kein Ticket: laut Ticket Abgrenzung; 022 ist schon getrennt, Re-Export und Re-Import genügen]`.
- Roadmap: den Aufwand von TOOL-106 von 0,5 auf 1 Tag anheben `[kein Ticket: erledigt /close-ticket in transcript-roadmap.py]`.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Regressionstest zwei SL im Export | no |
| 2 | Messung an 022, Spike-Bericht | yes |
| 3 | Kontext 1.5 lesen, Snapshot | no |
| 4 | Rolle und Figur des Abends im Dialog, in `samples.md` und in `context` | no |
