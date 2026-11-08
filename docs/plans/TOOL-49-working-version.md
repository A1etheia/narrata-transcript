# TOOL-49 — Arbeitsfassung aus Referenz, Sprecherzuordnung und Review-Entscheidungen

## Ziel
`transcript working <session>` leitet die Arbeitsfassung deterministisch aus Referenztranskript, Wissens-Snapshot, Sprecherzuordnung (TOOL-68) und den importierten Review-Entscheidungen (TOOL-48) ab. Pro Passage enthält sie:
- den Ergebnistext,
- die Herkunft (automatisch, entschieden oder offen),
- das Sprecher-Label und, falls zugeordnet, die Person.

Heute liegen diese Teile nur getrennt vor, deshalb hat TOOL-69 keine Grundlage für den Export.

## Ist-Stand
- **Referenz:** `ReferenceTranscript` und `Passage` stehen in `src/transcript/reference.py:63,163`. Geladen wird über `load_transcribed(paths, i)` (`:381`). Der Text wird nie korrigiert (`docs/referenzformat.md:52-57`).
- **Kandidaten:** `candidates.collect(paths, manifest)` (`src/transcript/candidates.py:126`) liefert `SessionCandidates`, frisch gegen Referenz und Bewertung geprüft. Nicht bewertete Segmente landen in `not_rated`. Passagen bewerteter Segmente ohne Kandidat sind `confident` (`:182`, `:317`).
- **Entscheidungen:** `ReviewStatus` ist `open|confirmed|corrected|unintelligible|kept|deferred` (`src/transcript/decisions.py:32-39`), geladen über `load_decisions` (`:187`). `review_items(found, decisions)` (`:144`) teilt sie in drei Gruppen:
  - aktuell,
  - veraltet (`stale`, anderes `reference_processed_at`),
  - verwaist (`orphaned`).
- **Sprecher:** `speakers.check(load_assignment(paths), diarized_references(paths, manifest), snapshot.participants)` liefert eine `SpeakerMap` (`src/transcript/speakers.py:202,291,194,123`). Sie bietet `resolve(segment, label) -> SpeakerRef` (`:131`), `findings` und `persons()`.
- **Snapshot:** `knowledge.load_snapshot(paths)` (`src/transcript/knowledge.py:164`) mit `snapshot_id`.
- **Dateikonventionen:**
  - Geschrieben wird mit `jsonfile.write_atomic` (`src/transcript/jsonfile.py:123`).
  - Jede Datei beginnt mit `format_version` und `session`.
  - Loader lehnen fremde Versionen ab.
  - Fehlermeldungen nennen Datei, Eintrag und Feld, nie Werte.
- **CLI-Muster:** `_speakers` (`src/transcript/__main__.py:810-857`) mit Exit 0, 1 (Funde) und 2 (Fehler). Registriert wird in `:213-280`.
- `SessionPaths` (`src/transcript/session.py:115-155`) hat noch keine Property für eine Arbeitsfassung.
- Das README verweist schon auf TOOL-49 (`:276`, `:356`, `:378`), der `work/`-Baum steht in `:506-517`.

## Entscheidungen
- **Die fünf Regeln des Tickets entsprechen den Status aus TOOL-46.** Ticket und Code weichen nicht voneinander ab:

  | Status | Ergebnis |
  | --- | --- |
  | `confirmed` | ASR-Wortlaut |
  | `corrected` | `target_text` |
  | `unintelligible` | als unverständlich markiert |
  | `kept` | ASR-Wortlaut, bewusst unverändert |
  | `open`, `deferred` | ungeklärt |

- **Ein Block pro Referenzpassage, sortiert nach Segment und Passage.**
  - Die Zeiten bleiben segmentlokal wie in der Referenz; die Sitzungszeit bildet TOOL-69 über `session_time.passage_span`.
  - Es gibt keine Wortliste, weil ein korrigierter Text keine Wortzuordnung mehr hat. Die Wortdetails bleiben in der Referenz und sind über Segment und Passage erreichbar.
- **Blockfelder:**

  | Feld | Inhalt |
  | --- | --- |
  | `segment`, `passage` | Position in der Referenz |
  | `start_ms`, `end_ms` | segmentlokale Zeiten |
  | `level` | `confident`, `needs_review` oder `uncertain` |
  | `origin` | `automatic`: sicher, ohne Kandidat<br>`decided`: aktuelle Entscheidung `confirmed`, `corrected`, `unintelligible` oder `kept`<br>`open`: Kandidat ohne aktuelle Entscheidung, oder Entscheidung `open` bzw. `deferred` |
  | `status` | Review-Status; `null` bei `automatic` |
  | `asr_text` | immer vorhanden, unverändert |
  | `text` | `target_text` bei `corrected`, `null` bei `unintelligible`, sonst der ASR-Wortlaut |
  | `speaker` | `label`, `assigned` und `user_id` aus `resolve` |

  So bleibt jede Unsicherheit sichtbar und kein Schritt erfindet Text. Wie `unintelligible` markiert wird, entscheiden TOOL-50 und TOOL-69.
- **Veraltete und verwaiste Entscheidungen werden nie angewendet.**
  - Eine veraltete Entscheidung zählt als offen (`origin: open`). Ihr früherer Status steht nicht im Block, sondern nur als Fund.
  - Eine verwaiste Entscheidung erscheint als Fund.
- **Die Konsistenz wird bei jedem Lauf frisch geprüft.** Die Kandidaten kommen aus `candidates.collect` statt aus `load_candidates`, damit Referenz, Bewertung und Kandidaten zusammenpassen. Passen sie nicht, bricht der Lauf mit `CandidatesError` ab (Exit 2).
- **Segmente ohne transkribierte Referenz oder ohne Bewertung** (`not_rated`) erzeugen keine Blöcke, sondern einen Fund `missing_segment`. Nichts wird geraten.
- **Eine fehlende Sprecherzuordnung ist erlaubt.** Liefert `load_assignment` den Wert `None`, bleiben alle Labels `open`, und die Konsole weist darauf hin. Segmente ohne Diarisierung tragen `label: null`.
- **Determinismus:** Die Datei enthält keine Zeitstempel des Laufs. Gleiche Eingaben ergeben eine byte-gleiche Datei. Statt eines Zeitstempels hält `inputs` die Eingaben fest:
  - `knowledge_snapshot_id`;
  - pro Segment `reference_processed_at` und `labels_version` (oder `null`);
  - `decisions_updated_at`;
  - `assignment_sha256` über die Dateibytes, `null` ohne Datei.
- **Pfad:** `work/<s>/working/transcript.json` (`SessionPaths.working_transcript`). Die Datei enthält Text und User-IDs und gehört deshalb nach `work/`, nicht nach `output/`.
- **Exit-Codes:**

  | Code | Bedeutung |
  | --- | --- |
  | 0 | geschrieben, keine Funde |
  | 1 | geschrieben, mit Funden (veraltet, verwaist, Sprecherfunde, fehlende Segmente) |
  | 2 | Fehler |

  Offene Blöcke sind ein zulässiger Zustand. Sie werden gezählt, sind aber kein Fund. Die Funde stehen auch in der Datei (`findings`), damit TOOL-69 sie nicht neu berechnen muss.
- **TOOL-69 liest über `load_working(paths)`**, mit Prüfung von Format und Session.

## Daten-Check
- handled — die Arbeitsfassung liegt unter `work/`, das nach TOOL-66 gitignored ist; `tests/test_gitignore.py` deckt `work/` ab.
- handled — die Konsole zeigt nur Zahlen: Blöcke nach Herkunft, Funde nach Art. Texte, Labels und Namen erscheinen nicht; das prüft ein Test mit `SECRET_LABEL`/`NAME` analog `tests/test_smoke.py:1585`.
- handled — Fehlermeldungen nennen Datei, Segment, Passage und Feld, nie Text oder Personen.
- handled — die Fixtures sind synthetisch (`beispielgruppe/042`, `wort{n}`, Teilnehmer-IDs 11–13).
- N/A Klarnamen — die Datei trägt `user_id`, keinen `display_name`.

## Contract-Check
- N/A Contract-JSON — die Arbeitsfassung ist ein internes Zwischenformat. Sie schreibt kein Contract-JSON und spricht den Narrata-Endpoint nicht an. Das Mapping gegen IOA-1214 (`unintelligible` als Marker, sessionweite Labels, `multiple`) übernimmt TOOL-69.
- N/A Narrata-Änderung — keine.

## Resume-Check
- N/A Langlauf — der Schritt leitet nur aus vorhandenen Dateien ab, dauert Sekunden und nutzt kein Modell. Dank `write_atomic` hinterlässt ein Abbruch entweder die alte oder die neue Datei, und jeder Lauf baut vollständig neu.

## Dependency-Check
- N/A — keine neue Abhängigkeit, kein Modell.

## Format-Check
- handled — neues Format `working/transcript.json` mit `format_version: 1`, bestehende Artefakte gibt es nicht. Referenz, Entscheidungen und Zuordnung ändern sich nicht und behalten ihre Version.

## Chunks
### Chunk 1 — Arbeitsfassung ableiten
- Dateien: `src/transcript/working.py` (neu), `tests/test_working.py` (neu)
- Änderung:
  - Dataclasses `Block`, `WorkingFinding` und `WorkingTranscript`.
  - Reine Funktion `build(references, found, review_state, speaker_map, inputs) -> WorkingTranscript` nach den Regeln oben.
  - Die Testhelfer aus `tests/test_candidates.py`, `test_decisions.py` und `test_speakers.py` werden wiederverwendet.
- Verify: `scripts/check`
- AC:
  - Jeder Status führt zum vorgesehenen `text` und `origin`.
  - Sichere Passagen sind `automatic`; offene, veraltete und zurückgestellte sind `open`.
  - Verwaiste und veraltete Entscheidungen sowie Sprecherfunde erscheinen als Funde.
  - Das Label bleibt, die Person kommt hinzu.
  - Das Referenz-Objekt bleibt unverändert.

### Chunk 2 — Datei schreiben und laden
- Dateien: `src/transcript/working.py`, `src/transcript/session.py`, `tests/test_working.py`
- Änderung:
  - `SessionPaths.working_transcript`.
  - `compose(paths, manifest) -> WorkingTranscript` lädt Referenzen, `candidates.collect`, `load_decisions` mit `review_items`, die Zuordnung mit `speakers.check` sowie den Snapshot und bildet `inputs`.
  - `write_working` und `load_working` mit `WorkingError(DataFileError)`.
- Verify: `scripts/check`
- AC:
  - Zwei Läufe mit gleichen Eingaben erzeugen eine byte-gleiche Datei.
  - Eine geänderte Entscheidung ändert nur den betroffenen Block und `inputs`.
  - Die Referenzdateien bleiben byte-gleich.
  - Der Loader lehnt fremde Versionen und Sessions ab.

### Chunk 3 — CLI `transcript working`
- Dateien: `src/transcript/__main__.py`, `tests/test_smoke.py`
- Änderung: Subcommand nach dem Muster von `_speakers`. Die Ausgabe zeigt die Blöcke nach Herkunft (`_by_status`), die Funde nach Art und einen Hinweis bei fehlender Zuordnung. Exit-Codes 0, 1 und 2.
- Verify: `scripts/check`
- AC:
  - Die Exit-Codes folgen den Entscheidungen oben.
  - Fehlen Snapshot oder Bewertung, endet der Lauf mit Exit 2 und dem Hinweis „run transcript …“.
  - stdout und stderr enthalten keine Texte, Labels oder Namen.

### Chunk 4 — Doku
- Dateien: `README.md`, `docs/transcript-roadmap.py`, `docs/transcript-roadmap.md`
- Änderung:
  - Neuer README-Abschnitt „Arbeitsfassung“ nach „Hörfehler-Vorschläge“: Befehl, Beispiel, Blockfelder, Herkunftstabelle, Funde und Exit-Codes.
  - Die Vorverweise `:276`, `:356` und `:378` zeigen auf den neuen Abschnitt; der `work/`-Baum bekommt den neuen Eintrag.
  - Roadmap-Hinweise für TOOL-69 und TOOL-50 ergänzen (Feld `text: null` bei `unintelligible`, `load_working`) und die `.md` neu generieren.
- Verify: `scripts/check`
- AC: Das README beschreibt Befehl und Format vollständig; die Roadmap-`.md` ist aus der `.py` generiert.

## Folge-Tickets
- Arbeitsfassung im Export abbilden (`origin`, `text: null`, Funde): TOOL-69 (Übergabekommentar).
- Markierung für unverständliche und offene Stellen festlegen: TOOL-50 (Übergabekommentar).
- Entscheidungen auf eine neue Transkriptversion übertragen: [kein Ticket: in TOOL-46 bewusst offen gelassen; erst nötig, wenn Segmente nach dem Review neu transkribiert werden]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `build` und Regeln | no |
| 2 | Datei, Pfad, Determinismus | no |
| 3 | CLI | no |
| 4 | README, Roadmap | no |
