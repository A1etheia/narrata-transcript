# TOOL-58 — Erste reale Session: Pilotbericht

Stand 2026-11-12. Dieser Bericht enthält nur Kennzahlen, Codes und nachgestellte Beispiele. Session-Key, Gruppe, Namen und Transkripttext stehen nicht darin (TOOL-66). Plan: [`docs/plans/TOOL-58-pilot-session.md`](../plans/TOOL-58-pilot-session.md).

## Ergebnis in Kürze

- **Die Pipeline trägt durchgängig.** Eine reale Sitzung von 5:26 h mit zwei Aufnahmen lief von der Aufnahme bis zum Narrata-Import. Narrata nahm den Export (Contract 1.1) ohne Korrektur an, ein zweiter Import änderte nichts.
- **Maschine und Zuordnung sind alltagstauglich:** knapp 7 min Rechenzeit, 4 min Sprecherzuordnung.
- **Das Review trägt nicht.** Die WER liegt bei 24–33 %, fast jede Passage enthält einen Fehler, und 87 % der Passagen werden Kandidaten. Eine Stunde Review entschied 35 von 870 Kandidaten. Ein vollständiges Review läge bei rund 25 h pro Abend.
- **Die Bewertung selbst trifft:** kein Fehlalarm, 4 übersehene Fehler an zwei Handreferenzen, alle Auslassungen. Strengere Regeln würden echte Fehler verstecken.
- **Konsequenz:** Der Hebel ist die Erkennung (TOOL-93, TOOL-92), nicht die Bewertung. Bis dahin genügen Sprecherzuordnung und Export; unsichere Stellen bleiben im Transkript markiert. Review-Umfang und Review-Kanal entscheidet TOOL-60.

## Pilotsitzung

| Merkmal | Wert |
| --- | --- |
| Aufnahmen | 2, zusammen 05:26:17 |
| Contract | 1.1 (`source.recordings[]`) |
| Sprecher-Labels (Vorlauf) | 8 |

## Umgebung

| | |
| --- | --- |
| GPU | RTX 3080 Ti, 12 GB VRAM |
| ASR | faster-whisper large-v3-turbo, Revision `0a363e91`, CUDA |
| Diarisierung | pyannote/speaker-diarization-community-1, Revision `3533c8cf` |
| Wissens-Snapshot | `186e030dc24e`, ab `transcribe` eingefroren |

## Automatischer Lauf

`transcript process <s> --redo transcribe`, Zeiten aus `work/<s>/pipeline.log`:

| Schritt | Ergebnis | Dauer |
| --- | --- | --- |
| preflight, snapshot | ok, Snapshot wiederverwendet | < 1 s |
| extract, context, manifest | wiederverwendet | — |
| transcribe (ASR, Diarisierung, Hinweise, Bewertung) | 2 von 2 Segmenten | 6:57 min |
| review, speakers | angehalten (Exit 3), Vorlagen geschrieben | < 1 s |

- **Tempo:** 5:26 h Audio in knapp 7 min, also rund 47-fache Echtzeit für den ganzen Schritt. Die Diarisierung allein brauchte im ersten, an der ASR gescheiterten Versuch 231 s und 18 s für die beiden Segmente.
- **Ressourcen:** Im ersten Versuch (nur Diarisierung, die ASR scheiterte vor dem Laden) lagen der Peak-RAM bei 14,5 GB und der Peak-VRAM bei 3,6 GB. Die Messwerte des erfolgreichen Laufs gingen verloren, weil das temporäre Verzeichnis mit den Mitschnitten geleert wurde. Nach TOOL-62 und TOOL-20 sind für die ASR bis 10,5 GB RAM zu erwarten, beide Modelle laufen nacheinander.
- **Bewertung:** 870 Review-Kandidaten, davon 185 `uncertain` und 685 `needs_review`, das sind 160 pro Stunde Audio. Im Vorlauf mit älterem Snapshot waren es 1371 (252 pro Stunde).
- **Diarisierung:** 7 Sprecher-Labels über beide Segmente, alle offen.

## Sprecherzuordnung

Interaktiv mit `transcript speakers <s> --assign` (TOOL-86): **4 min** für 7 Labels in 2 Segmenten, gemessen vom Befehl selbst (`effort_minutes`). Ergebnis: 6 Labels einer Person zugeordnet, 1 `multiple`, 0 offen, 0 `unknown`. Der Vorlauf mit 8 Labels hatte 8 min gebraucht.

**Nachtrag TOOL-91 (Entrauschen der Hörproben):** Die Proben in `--assign` sind schon im Rohsignal fast störungsfrei. Der Pausenpegel liegt in beiden Segmenten bei rund −55 dBFS, die Sprache bei −32 bis −34 dBFS. Verglichen wurden 16 Clips à 8 s an den auffälligsten Pausenstellen (8 laute Pausen, 8 mit Klopfen oder Klappern), jeweils roh, mit `highpass=f=80,afftdn=nf=-25` und mit `highpass=f=100,afftdn=nf=-20:nr=20`. Das Rohsignal klang jeweils am besten, die mittlere Kette war ebenfalls gut, die starke viel zu dumpf. In 2 der 16 Clips machte die mittlere Kette Wörter verständlich, die roh kaum zu verstehen waren. Folge: `playback.filter` ist standardmäßig aus (`false`), die mittlere Kette steht in README und `config/example.yaml` als Vorschlag für verrauschte Aufnahmen.

## Review

Review in `review.csv`, sortiert nach `order`, Timebox **60 min**, gestoppt von der Projektverantwortlichen. Angehört wurde mit einem Hilfsskript, das eine Passage über ihre Kandidaten-ID abspielt (siehe Workarounds).

| | Anzahl |
| --- | --- |
| Kandidaten | 870 (185 `uncertain`, 685 `needs_review`), 160 pro Stunde Audio |
| entschieden | 35: 9 `confirmed`, 23 `corrected`, 3 `unintelligible`, 0 `kept` |
| offen | 835 |
| Hörfehler-Vorschläge | 4 neu, 32 Korrekturen ohne Glossar-Begriff |

- **Tempo:** 35 Entscheidungen pro Stunde. Hochgerechnet bräuchte das vollständige Review dieser Sitzung rund 25 Stunden, fast fünfmal so lange wie die Aufnahme.
- **Trefferquote oben in der Liste:** 26 der 35 entschiedenen Kandidaten waren falsch erkannt oder unverständlich (74 %). Die Reihenfolge `order` bringt die Fehler also nach vorn.
- **Die Auswahl trennt kaum:** 870 der 997 Passagen sind Kandidaten (87 %). Die 127 automatisch übernommenen Passagen decken nur 10:21 min der 5:26 h ab, also 3 %. Praktisch die ganze Aufnahme steht zur Prüfung. Ein Grund sind lange Passagen: Whisper-Passagen dauern im Mittel rund 20 s, und schon ein einziges unsicheres Wort macht die ganze Passage zum Kandidaten (Regel `very_low_confidence`).
- **Zusammenhang beim Hören hilft:** Die Projektverantwortliche hat Wörter in langen Passagen besser erkannt als in kurzen Ausschnitten. Kürzere Hörproben sparen also kaum Zeit. Ansatzpunkte sind eher weniger Kandidaten, hervorgehobene unsichere Wörter beim Abspielen der ganzen Passage und ein Dialog statt der CSV.
- **Halluzination am Aufnahmeende:** Die letzte Passage von Segment 2 (1,7 s, Wort-Confidence nahezu 0) ist von Whisper erfundener Text. Sie wurde richtig als `uncertain` markiert und im Review als `unintelligible` entschieden.

## Ergebnis

`transcript process <s>` nach Zuordnung und Review: Exit 1, einzige Lücke `open_passages` in beiden Segmenten.

| Datei | Inhalt |
| --- | --- |
| `transcript.json` | Contract 1.1, `source.recordings[]` mit 2 Aufnahmen, 997 Passagen; vor dem Schreiben gegen die Schema-Kopie und die Regeln aus `contract.validate` geprüft |
| `transcript.txt`, `transcript.docx` | 481 Absätze, offene Passagen als `[unklar …]` markiert |
| `report.json`, `report.md` | 3 `unintelligible`, 3 `crosstalk`, 835 offen; 4 Personen hinter 7 Labels |

**Grober manueller Aufwand:** 4 min Zuordnung und 60 min Review (35 von 870 Kandidaten), dazu wenige Minuten für die Befehle. Ein vollständiges Review läge bei rund 25 h (siehe oben).

## Fehlerstichprobe

Zwei Handreferenzen der Projektverantwortlichen aus Segment 1, ausgewertet mit `transcript calibrate`. Ausschnitt B ist derselbe Clip wie in TOOL-62 und TOOL-35.

| | A: 0:00:00–0:04:06 | B: 1:20:00–1:23:00 |
| --- | --- | --- |
| Wörter in der Referenz | 551 | 489 |
| WER | 23,6 % (130 Fehler) | 32,9 % (161 Fehler) |
| Ersetzungen / Auslassungen / Einfügungen | 66 / 49 / 15 | 61 / 92 / 8 |
| Fehler je Sprecher | S1 16,8 %, S2 50,0 % (20 Wörter), S3 31,2 % | ohne Sprecherkennung |
| Passagen markiert | 9 von 9 (100 % der Zeit) | 7 von 8 (95,6 % der Zeit) |
| Fehler in markierten Passagen | 130 von 130 | 157 von 161 |
| übersehen (`confident`) | 0 | 4, alle Auslassungen |
| Fehlalarme (markiert, ohne Fehler) | 0 | 0 |
| AUC der Word-Confidence | 0,78 | 0,75 |
| falsche Wörter unter den unsichersten 30 % | 67,9 % | 60,9 % |

- **Die Auswahl ist nicht zu großzügig, das Transkript ist zu fehlerhaft.** Keine einzige markierte Passage war fehlerfrei. Bei einer WER von 24–33 % und Passagen von im Mittel 18 s (Median 13 s, 312 von 997 länger als 30 s) enthält fast jede Passage mindestens einen Fehler. Dass 87 % der Passagen Kandidaten sind, ist also richtig gemessen. Strengere Regeln würden echte Fehler verstecken, nicht Fehlalarme sparen.
- **Auslassungen** sind 38 % (A) bzw. 57 % (B) der Fehler. Sie haben keine Word-Confidence und fallen nur über `gap`, `sparse` oder `crosstalk` auf. Die 4 übersehenen Fehler sind alle Auslassungen.
- **Übersprechen:** In A tragen die 4 Passagen mit `crosstalk` 69 der 130 Fehler.
- **Regeln über die ganze Sitzung:** `very_low_confidence` (mindestens ein Wort unter 0,2) schlägt in 683 der 870 Kandidaten an, in 103 als einziger Grund. Danach folgen `low_confidence` (341), `gap` (316), `low_logprob` (209) und `crosstalk` (185).
- **Abweichung zu TOOL-35:** Dort waren 36 % der Passagen markiert, hier 87 %. Die WER am selben Clip B ist praktisch gleich (32,9 % gegen 32,4 %). Der Unterschied liegt bei den Regeln und den Passagen, nicht beim Wortlaut. Warum, ist nicht geklärt; Kandidaten sind der neuere Snapshot mit mehr Hinweisen und die Regel `crosstalk`.

## Narrata-Gegenprobe

Lokales Narrata (ios-archiv `main`) mit PHP 8.5 nativ und MySQL über Sail. Die leere lokale DB bekam Platzhalter mit denselben IDs wie der Export: Gruppe, Spielsitzung mit Ordinal und vier Personen als Mitglieder.

| Schritt | Ergebnis |
| --- | --- |
| `scripts/artisan transcript:validate <transcript.json>` | `conforms to the transcript contract`, Exit 0 |
| `transcript:import`, 1. Lauf | 997 created, 0 updated, 0 removed; 0 Hinweise verworfen; Exit 0 |
| `transcript:import`, 2. Lauf mit derselben Datei | `already holds this file; nothing changed`, Exit 0 |

- **Ohne Korrektur:** Contract 1.1 mit zwei Aufnahmen wird von Narrata so angenommen, wie die Pipeline ihn schreibt. `contract.validate` und Narratas Validator sind sich an der echten Datei einig.
- **Idempotent:** Ein erneuter Import derselben Datei ändert nichts.
- **Aufräumen:** Das importierte Transkript wurde danach aus der lokalen DB gelöscht, die Passagen gingen über den Fremdschlüssel mit. Die Platzhalter enthalten keine echten Daten.
- **Die Exportdatei** bleibt lokal unter `output/` und ging in kein Repo. Die Fixtures aus IOA-1214 und IOA-1287 decken die Form ab.

Einrichtung der lokalen Umgebung, nur beim ersten Mal:

- **IPv6 in WSL defekt:** `scripts/bootstrap-wsl-php.sh` brach beim Anlegen der PHP-Paketquelle mit `Connection timed out` ab, weil Launchpad per IPv6 nicht erreichbar war (IPv4 antwortet in 0,2 s). Workaround: IPv4 in `/etc/gai.conf` bevorzugen (`precedence ::ffff:0:0/96 100`).
- **Gruppe `docker`:** Nach der Aufnahme in die Gruppe kennen laufende Shells sie erst nach einem neuen Login. Bis dahin hilft `sg docker -c "…"`.
- **Import mit nativem PHP:** `DB_HOST=127.0.0.1 scripts/artisan transcript:import <datei>` erreicht das MySQL im Container. So muss die Exportdatei nicht in das Narrata-Repo kopiert werden.

## Blockierende Fehler und Workarounds

- **Alte Handdateien vor `--redo transcribe`:** Die alte `speakers/assignment.json` und `review/review.csv` stammten aus einem früheren Lauf. Nach einer neuen ASR wären ihre Einträge `stale`, und `process` hätte keine frischen Vorlagen geschrieben. Deshalb wurden sie vorher nach `work/<s>/pre-tool58/` verschoben.
- **CUDA-Bibliotheken für faster-whisper:** Der erste Versuch scheiterte nach 6 min an beiden Segmenten mit `BackendUnavailableError … CUDA libraries not found`, weil `LD_LIBRARY_PATH` in der Shell fehlte (Voraussetzung laut README, Abschnitt „Spracherkennung“). Workaround: den Pfad setzen und `--redo transcribe` wiederholen. Das alte ASR-Ergebnis blieb dabei unverändert.
- **Preflight meldet die ASR zu früh als `ok`:** `transcript doctor` zeigte `asr: … on cuda` als `ok`, obwohl faster-whisper cuBLAS und cuDNN nicht laden konnte. Der Fehler fiel erst nach Snapshot und Diarisierung auf. Der Preflight sollte das Laden der Bibliotheken prüfen, ohne das Modell zu laden.
- **Aufruf ohne aktivierte venv:** Ohne `source .venv/bin/activate` kennt die Shell `transcript` nicht, und `LD_LIBRARY_PATH` muss in jeder Shell neu gesetzt werden. Workaround auf dem Pilotrechner: ein Startskript `~/.local/bin/transcript`, das beides übernimmt. Aufgerufen wird es weiterhin aus dem Projektordner, weil `paths.root` relativ ist.
- **Keine Abspielhilfe im Review:** Fast jede Zeile muss angehört werden, aber die Pipeline spielt nur im Sprecher-Dialog ab. Wer Segment und Zeit von Hand aus der CSV in einen Player überträgt, verliert viel Zeit, und bei der Spalte `start` (Session-Zeit statt Segment-Zeit) springt der Player hinter das Segmentende und bleibt stumm. Workaround: das Skript `~/.local/bin/hoer <id>`, das Segment und Zeiten aus `candidates.json` liest und die Passage mit 2 s Vorlauf und 1 s Nachlauf abspielt. Ein Review-Dialog nach dem Vorbild von `speakers --assign` würde den Aufwand vermutlich spürbar senken.
