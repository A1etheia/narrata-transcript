# Transkript-Projekt — Roadmap (TOOL + IOA-1213)

Stand 2026-11-09, generiert von `transcript-roadmap.py` (Reihenfolge und Aufwände stehen dort). Verbindliche Reihenfolge und Meilensteine für das gesamte Transkript-Vorhaben: die lokale Pipeline (Jira-Projekt **TOOL**, eigenes Python-Repo) und ihr Narrata-Gegenstück (Epic **IOA-1213**). Jira-Gesamtsicht: `project in (TOOL, IOA) AND labels = transcript`.

## Annahmen

- **Eine Person, ein Zeitbudget.** TOOL- und IOA-Tickets konkurrieren um dieselben Tage; der Plan ist deshalb eine *lineare* Folge. Echte Parallelität gibt es nur dort, wo ASR-Läufe oder Modell-Downloads im Hintergrund laufen — dann wird am Narrata-Ticket derselben Phase gearbeitet.
- **Kapazität: 3 Entwicklungstage pro Woche**, Start 02.11.2026, Pause 21.12.2026–03.01.2027. Das ist der Umrechnungsfaktor für die Kalenderspalte, nicht Teil des Plans — ändert sich die Kapazität, verschieben sich nur die Daten, nicht die Reihenfolge.
- **Aufwände sind Entwicklungstage in 0,5er-Schritten**, grob geschätzt aus den Ticket-Beschreibungen. Sie dienen der Reihenfolge und den Meilenstein-Abständen; keine Zusage.
- **Gesamtumfang: 74 Entwicklungstage** ≈ 27 Wochen inkl. Pause → letzter Meilenstein 04.05.2027. Davon 2 Tage bedingt (TOOL-73, TOOL-78).
- **Neu terminiert am 02.11.2026:** Vom Plan des 03.10. war noch kein Ticket begonnen (alle TOOL- und IOA-Tickets To Do, kein Python-Repo, keine Transkript-Commits). Die 3 Tage pro Woche sind damit unbelegt; Reihenfolge belastbar, Daten nur bei dieser Kapazität.
- Nicht eingeplant: TOOL-14 (Remote-Backend, geparkt), die Epics selbst, verworfene Tickets (TOOL-21–32, 34; TOOL-3, 7; TOOL-11, 33 nach TOOL-62), in andere aufgenommene Tickets (TOOL-77 in TOOL-57).

## Leitlinien der Reihenfolge

1. **Entscheidungen vor Code.** Datenschutz (TOOL-66/IOA-1216) und Contract (IOA-1214) stehen, bevor irgendetwas Daten schreibt — sonst werden Fixtures, Logs und IDs später umgebaut.
2. **Der ASR-Spike (TOOL-62) läuft vor der Audio-Vorbereitung.** Er entscheidet, ob Epic TOOL-8 drei oder fünf Stories hat. Ergebnis: drei, TOOL-11 und TOOL-33 entfallen.
3. **Narrata-Arbeit füllt die Wartezeiten der Pipeline.** Export-Endpoint und Alias-Kategorie entstehen, während Modelle rechnen; Storage/Import entsteht gegen die Fixture, bevor der echte Export existiert.
4. **Der Pilot (Phase 4) ist ein Tor, kein Schritt.** TOOL-60 entscheidet explizit über Review-Kanal, Remote-Backend und die Freigabe von Phase 6. Phasen 5–7 werden nach dem Pilot-Review neu terminiert.
5. **Lesen vor Analysieren.** Die Narrata-Oberflächen (Phase 5) kommen vor IT/OT (Phase 6) — ein importiertes Transkript muss erst nutzbar sein, bevor es klassifiziert wird; das Lesen deckt zudem Contract-Lücken auf, die TOOL-71 sonst zementiert.
6. **Das Kernziel kommt zuerst.** Innerhalb von Phase 5 stehen Suche und Chat/MCP (IOA-1220, IOA-1223) vor Lese-UI und Links: Sie hängen nur an IOA-1218 und machen das Transkript für den KI-Assistenten nutzbar.

## Meilensteine

| # | Meilenstein | Phase | Zeitraum | Tage |
|---|---|---|---|---|
| M0 | Repo steht, Datenschutz entschieden, Contract v1 eingefroren | Phase 0 | 02.11.2026 – 10.11.2026 | 5 |
| M1 | Backend gewählt, Diarisierung entschieden, TOOL-11/33 entschieden, Export-Endpoint live | Phase 1 | 12.11.2026 – 01.12.2026 | 8.5 |
| M2 | Eine Session läuft vom MP4 bis zur Referenztranskription mit Sprecher-Labels und Wissens-Snapshot | Phase 2 | 01.12.2026 – 25.01.2027 | 17 |
| M3 | JSON-Export (Contract v1) einer Session importiert lokal in Narrata und rendert dort als Rohliste | Phase 3 | 25.01.2027 – 22.02.2027 | 12.5 |
| M4 | Pilot-Review (TOOL-60): Kernhypothese geprüft; Entscheidungen Review-Kanal, Remote-Backend, Freigabe IT/OT | Phase 4 | 23.02.2027 – 15.03.2027 | 9 |
| M5 | Transkript per Chat/MCP befragbar, in Narrata durchsuchbar, lesbar, verlinkt | Phase 5 | 16.03.2027 – 01.04.2027 | 8 |
| M6 | IT/OT-Schicht im Export, Statistik im Bericht | Phase 6 | 05.04.2027 – 20.04.2027 | 7.5 |
| M7 | Erste Welt-Archiv-Einträge mit Transkript-Provenienz; IT/OT-Statistik und Abendvergleich sichtbar | Phase 7 | 20.04.2027 – 03.05.2027 | 5 |
| M8 | Entscheidung, ob und wie andere Narrata-Nutzer ihre Aufnahmen transkribieren können | Phase 8 | 03.05.2027 – 03.05.2027 | 0.5 |
| M9 | Konzept für Stimmprofile mit Einwilligung pro Spielrunde, Go/No-Go | Phase 9 | 04.05.2027 – 04.05.2027 | 1 |

## Reflexionspunkte

| Nach | Frage | Ticket, das entscheidet | Was sich ändert |
|---|---|---|---|
| M1 | Braucht das Backend externe Segmentierung? | TOOL-62 | Beantwortet: nein, TOOL-11 und TOOL-33 verworfen; Phase 2 −2 Tage |
| M1 | Liefert Diarisierung stabile Labels? | TOOL-20 | Beantwortet: ja, pyannote hält 4 Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; TOOL-68 bleibt bei 1 Tag |
| M1 | Liefert das ASR-Backend die Sprecher-Labels selbst? | TOOL-20 | Beantwortet: nein, separate Diarisierung mit pyannote; Integration als TOOL-76 (1,5 Tage) in Phase 2, M2 verschiebt sich entsprechend |
| M3 | Trägt der Contract den Import ohne Rückfragen? | IOA-1218 gegen TOOL-69 | Contract-Minor-Bump vor Phase 4, nicht danach; erster Bump erledigt: 1.1 mit `source.recordings[]` (IOA-1287), Pipeline-Seite TOOL-89 |
| M4 | Trägt die Kernhypothese (Konfidenz grenzt Review ein)? Aufwand pro Abend alltagstauglich? | TOOL-60 | Go/No-Go Phase 6; Review-Kanal CSV vs. Narrata-UI (→ ggf. neues IOA-Ticket); TOOL-14 |
| Phase 6, Tag 2 | Reicht ein lokales LLM für IT/OT? Bringt der zweite Durchlauf messbar etwas? | TOOL-70 | TOOL-73 bleibt oder entfällt; ggf. Remote-Option |
| M7 | Welche Fragen aus der Zielliste sind jetzt beantwortbar, welche nicht? | Retro, kein Ticket | V0.2-Backlog beider Projekte |
| M8 | Öffnen wir die Transkription für andere Nutzer, und auf welchem Weg? | TOOL-85 | Entscheidung; bei „ja“ Folge-Tickets |
| M9 | Lohnt sich die Wiedererkennung der Sprecher, und trägt die Einwilligung pro Spielrunde? | TOOL-87 | Go/No-Go; bei „ja“ Umsetzungstickets in TOOL und IOA |

## Arbeitsfolge

Start/Ende sind in Jira als Start date / Due date gespiegelt.

### Phase 0 — Fundament und Entscheidungen

**M0 — Repo steht, Datenschutz entschieden, Contract v1 eingefroren. Nichts auf beiden Seiten schreibt JSON, bevor IOA-1214 steht.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-66 | Datenschutz-/Einwilligungs-/Sichtbarkeitsentscheidungen | 0.5 | 02.11.2026 | 02.11.2026 | erledigt: `docs/datenschutz.md` |
| TOOL-2 | Repo, Python-Projekt, README | 0.5 | 02.11.2026 | 02.11.2026 | erledigt |
| TOOL-4 | Verzeichnis-/Sessionstruktur (Narrata-Schlüssel) | 0.5 | 03.11.2026 | 03.11.2026 | erledigt: `src/transcript/session.py`, Layout im README |
| TOOL-5 | Dateiregeln, Rohaudio bleibt lokal | 0.5 | 03.11.2026 | 03.11.2026 | erledigt: `.gitignore`, `tests/fixtures/`, Dateiregeln im README |
| TOOL-6 | Basiskonfiguration | 0.5 | 05.11.2026 | 05.11.2026 | erledigt: `src/transcript/config.py`, `config/example.yaml` |
| IOA-1216 | Privacy-/Sichtbarkeitsmodell, Opt-in-Flag | 1.5 | 05.11.2026 | 09.11.2026 | erledigt: ios-archiv PR #1121; Narrata-Seite von TOOL-66; Anforderungen in `docs/datenschutz.md` |
| IOA-1214 | Contract v1: Schema, Fixture, Validator | 1 | 10.11.2026 | 10.11.2026 | erledigt: ios-archiv PR #1128, `transcript:validate`; Fixture dient IOA-1218, bis TOOL-58 liefert; aus TOOL-5: die Kopie der Contract-Fixture liegt im Pipeline-Repo unter `tests/fixtures/` |

### Phase 1 — ASR-Spike und Backend-Entscheidung

**M1 — Backend gewählt, Diarisierung entschieden, TOOL-11/33 entschieden, Export-Endpoint live. Reflexionspunkt: Epic TOOL-8 wird hier dimensioniert.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-62 | ASR-Kandidaten an realer Session (inkl. Hand-Check, Long-Audio-Frage) | 3 | 12.11.2026 | 17.11.2026 | erledigt: `docs/spikes/TOOL-62-asr-vergleich.md`; Whisper large-v3-turbo, Fallback Parakeet, keine eigene Segmentierung; vor IOA-1216/IOA-1214 vorgezogen (02.–04.11.2026) |
| TOOL-20 | Diarisierung / Label-Stabilität | 2 | 19.11.2026 | 23.11.2026 | erledigt: `docs/spikes/TOOL-20-diarisierung.md`; separate Diarisierung mit pyannote community-1, 4 stabile Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; NeMo braucht auf 5 h über 25 GB RAM; Integration in TOOL-76 |
| IOA-1215 | Transcription-context Export-Endpoint | 2 | 24.11.2026 | 26.11.2026 | erledigt: ios-archiv PR #1124; gelesen von `transcript context` (TOOL-67) |
| IOA-1217 | asr_variants-Alias-Kategorie | 1.5 | 30.11.2026 | 01.12.2026 | erledigt: ios-archiv PR #1129; `asr_variants` und `asr_ambiguities` ab Contract 1.1, keine Hörfehler an Ereignissen; Import-Command für Vorschlagsdateien (Format aus TOOL-80) an IOA-1285 |

### Phase 2 — Pipeline-Kern bis Referenztranskription

**M2 — Eine Session läuft vom MP4 bis zur Referenztranskription mit Sprecher-Labels und Wissens-Snapshot.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-9 | ffmpeg/ffprobe-Preflight | 0.5 | 01.12.2026 | 01.12.2026 | erledigt: `src/transcript/audio_tools.py`, `transcript doctor` |
| TOOL-10 | Formate erkennen, Audiospur extrahieren | 1 | 03.12.2026 | 03.12.2026 | erledigt: `src/transcript/audio.py`, `transcript extract` |
| TOOL-12 | Session-Manifest, absolute Zeiten | 1 | 07.12.2026 | 07.12.2026 | erledigt: `src/transcript/manifest.py`, `transcript manifest`; Teilaufnahmen einer Sitzung sind die Segmente |
| TOOL-63 | Backend-Schnittstelle, Capabilities, Fake-Backend | 1 | 08.12.2026 | 08.12.2026 | erledigt: `src/transcript/asr/`, `docs/asr-backends.md`; AK „V0.1-Backend implementiert die Schnittstelle“ an TOOL-64 übergeben |
| TOOL-16 | Internes Referenztranskript-Format | 1 | 10.12.2026 | 10.12.2026 | erledigt: `src/transcript/reference.py`, `docs/referenzformat.md`; eine Datei pro Segment unter `work/<session>/asr/`, Rohform getrennt |
| TOOL-64 | Lokales V0.1-Backend | 2 | 14.12.2026 | 15.12.2026 | erledigt: `src/transcript/asr/whisper.py`, README „Spracherkennung“; `scripts/spike/` entfernt, Runner im Stand `2f5b875` |
| TOOL-76 | Diarisierung mit pyannote integrieren | 1.5 | 17.12.2026 | 04.01.2027 | erledigt: `src/transcript/diarization/`, `transcript diarize`, README „Diarisierung“; Labels pro Segment, Rohform unter `work/<session>/diarization/`; pyannote-Telemetrie per `transcript/__init__.py` abgeschaltet |
| TOOL-15 | Einzelsegment transkribieren | 0.5 | 04.01.2027 | 04.01.2027 | erledigt: `src/transcript/transcription.py`, `transcript transcribe --segment N`, README „Spracherkennung“; ein Fehlschlag ersetzt nie ein erfolgreiches Ergebnis |
| TOOL-17 | Ganze Session, Resume | 1 | 05.01.2027 | 05.01.2027 | erledigt: `transcription.transcribe_session`, `transcript transcribe <session>` mit Wiederaufnahme und Diarisierung, README „Lauf“ |
| TOOL-18 | Fehlerkategorien, Retry, Force | 1 | 07.01.2027 | 07.01.2027 | erledigt: `src/transcript/retry.py`, `asr.retries`/`diarization.retries`, README „Lauf“; Diarisierung markiert Segmente `failed` statt abzubrechen |
| TOOL-19 | Absolute Zeitstempel im Format | 0.5 | 11.01.2027 | 11.01.2027 | erledigt: `src/transcript/session_time.py`, `docs/referenzformat.md` „Session-Zeit“; Spannen mit Granularität, Zeiten bis 1 s hinter dem WAV-Ende als `clamped` begrenzt |
| TOOL-67 | Narrata-Kanal + Datei-Fallback | 1 | 11.01.2027 | 12.01.2027 | erledigt: `transcript context` (`src/transcript/narrata.py`, `src/transcript/narrata_client.py`), README „Narrata-Kontext“; Contract 1.x, Token aus `.env`, `--from-file` als Datei-Fallback |
| TOOL-38 | Teilnehmerwissen | 0.5 | 12.01.2027 | 12.01.2027 | erledigt: `narrata.read_participants`, README „Narrata-Kontext“; `store_context` prüft `participants`; Anwesenheit unbekannt bis IOA-1271/TOOL-79 |
| TOOL-39 | Glossarbegriffe | 0.5 | 14.01.2027 | 14.01.2027 | erledigt: `narrata.read_glossary`, `src/transcript/glossary.py` (`GlossaryIndex`, `keyword_terms`), README „Narrata-Kontext“ / „Glossar“; `store_context` prüft Glossar, Archiv-Kappung und `asr_ambiguities`; Mehrdeutigkeiten werden ausgewiesen, nie aufgelöst |
| TOOL-41 | Relevanzregel + Snapshot | 1 | 14.01.2027 | 18.01.2027 | erledigt: `src/transcript/knowledge.py`, `transcript snapshot`, README „Wissens-Snapshot“; Relevanzstufe kommt aus Narrata, lokal nur Keyword-Auswahl und `knowledge.keyword_budget`; `asr.knowledge_snapshot_id` im Referenzformat v2 und in der Wiederverwendungsregel; `n`/`archive_limit` konfigurierbar; `num_speakers` an TOOL-79 |
| TOOL-42 | Validator + Diagnose | 0.5 | 18.01.2027 | 18.01.2027 | erledigt: `src/transcript/diagnosis.py`, `transcript snapshot` schreibt `narrata/diagnosis.json`, README „Diagnose“; technische Fehler bleiben in den Parsern, Querbezüge (geteilte Begriffe, Hörfehler, Spielfiguren gegen `pc`) sind Warnungen ohne Namen |
| TOOL-43 | Wissensschnittstelle | 1 | 19.01.2027 | 19.01.2027 | erledigt: `src/transcript/domain.py` (`DomainContext`), README „Wissensschnittstelle“; `transcribe` übergibt die Snapshot-Keywords, die Wiederverwendungsregel prüft `keywords_used` als geordnete Teilfolge der aktuellen Keywords |
| TOOL-44 | Keyword-Biasing + Review-Signal | 1 | 21.01.2027 | 21.01.2027 | erledigt: `src/transcript/hints.py`, README „Review-Hinweise“; Hotwords nur für Turbo-Modelle, `transcribe` meldet die Zahl der übergebenen Keywords; pro Segment `review/segment-NN.hints.json` mit `known_variant` (stark) und `similar` (schwach), Mehrdeutiges als `ambiguous`, ASR-Text unverändert |
| TOOL-40 | Fehlvarianten (leer-lauffähig) + Vorschlagsliste | 0.5 | 25.01.2027 | 25.01.2027 | erledigt: Tests in `tests/test_hints.py`, README „Review-Hinweise“ / „Hörfehler aus Narrata“; ein Hörfehler gilt für seinen Eintrag, Contract 1.1 liefert keinen Kontext pro Variante; Vorschlagsliste an TOOL-80 |

### Phase 3 — Review, Sprecherzuordnung, Export

**M3 — JSON-Export (Contract v1) einer Session importiert lokal in Narrata und rendert dort als Rohliste.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-35 | Konfidenz-/Unsicherheitsregeln kalibrieren | 1.5 | 25.01.2027 | 26.01.2027 | erledigt: `transcript assess`/`calibrate`, Bericht `docs/spikes/TOOL-35-kalibrierung.md` (85 % der Fehler in 46 % der Session-Zeit); Folge-Tickets außerhalb der Roadmap: TOOL-81 (Hotwords verschlucken Wörter), TOOL-82 (Parakeet-Zweitlauf), TOOL-83 (`similar` nach Relevanz-Stufe, erledigt: keine Archiv-Regel, Abschnitt im Bericht) |
| TOOL-36 | Review-Kandidaten | 1 | 28.01.2027 | 28.01.2027 | erledigt: `src/transcript/candidates.py`, `review/candidates.json`, README „Review-Kandidaten“; Kandidat = Stufe `needs_review`/`uncertain`, `uncertain` und starke Hinweise zuerst; Signal „überlappende Segmenttranskriptionen“ gestrichen (keine Segmentierung seit TOOL-62); erster Lauf an einer realen Session: 252 Kandidaten pro Stunde Audio |
| TOOL-46 | Review-Datenmodell | 0.5 | 01.02.2027 | 01.02.2027 | erledigt: `src/transcript/decisions.py`, `review/decisions.json`, README „Review-Entscheidungen“; Entscheidungen getrennt von den Kandidaten, sechs Status, Zieltext nur bei `corrected`, veraltete und verwaiste Entscheidungen werden gemeldet, nie angewendet; Hinweise aus TOOL-44 kommen über `candidates.json` |
| TOOL-47 | Review-CSV | 0.5 | 01.02.2027 | 01.02.2027 | erledigt: `transcript review-export`, `src/transcript/review_sheet.py`, `review/review.csv`, README „Review-CSV“; `;`, UTF-8 mit BOM für deutsches Excel; Standard `open`/`deferred`, `--all` alle; chronologisch, Spalte `order` für die Review-Reihenfolge; veraltete Entscheidungen in `earlier_decision`, verwaiste per ID auf der Konsole; vorhandene CSV nur mit `--force` ersetzt |
| TOOL-48 | CSV-Reimport | 0.5 | 02.02.2027 | 02.02.2027 | erledigt: `transcript review-import`, `src/transcript/review_import.py`, README „Review-Import“; gültige Zeilen übernommen, fehlerhafte mit Zeile/ID/Feld gemeldet (Exit 2); fehlende Spalte oder doppelte ID lehnt die Tabelle ab; unveränderte Zeilen sind keine Entscheidung, Reimport idempotent; `version` nur bei geänderten Zeilen geprüft; CSV-Leser geteilt in `src/transcript/sheetfile.py` |
| TOOL-80 | Vorschlagsdatei neuer Hörfehler | 0.5 | 02.02.2027 | 02.02.2027 | erledigt: `src/transcript/variant_suggestions.py`, README „Hörfehler-Vorschläge“; `transcript review-import` schreibt `review/asr-variant-suggestions.json` (`format_version: 1`) aus geltenden `corrected`-Entscheidungen, Ersetzungen bis 4 Wörter auf Glossar-Begriffe, Mehrdeutiges nie aufgelöst, ohne Zeitstempel reproduzierbar; Import-Command in Narrata an IOA-1285 |
| TOOL-68 | Sprecherzuordnung manuell | 1 | 04.02.2027 | 04.02.2027 | erledigt: `src/transcript/speakers.py`, `transcript speakers`, README „Sprecherzuordnung“; Zuordnung von Hand in `speakers/assignment.json` (`format_version: 1`) pro Segment und Label, Kandidaten aus dem Snapshot, Hörliste `speakers/samples.md`; unbekannte Segmente, Labels und Personen sowie veraltete Einträge werden gemeldet, nie angewendet |
| TOOL-49 | Arbeitsfassung | 1 | 08.02.2027 | 08.02.2027 | erledigt: `src/transcript/working.py`, `transcript working`, README „Arbeitsfassung“; `work/<s>/working/transcript.json` (`format_version: 1`), ein Block pro Passage mit `origin` (`automatic`/`decided`/`open`), unverändertem `asr_text`, Ergebnistext (`null` bei `unintelligible`) und Label plus Person; veraltete und verwaiste Entscheidungen, nicht anwendbare Sprecher-Einträge und fehlende Segmente als `findings` (Exit 1), nie angewendet; ohne Zeitstempel, `inputs` mit Versionen und Datei-Hashes, gleiche Eingaben byte-gleich |
| TOOL-50 | Markierungskonvention | 0.5 | 09.02.2027 | 09.02.2027 | erledigt: `src/transcript/markers.py`, README „Markierungen“; aus jedem Block der Arbeitsfassung abgeleitet, nicht gespeichert: `unintelligible` (`[unverständlich HH:MM:SS]`, ohne Text), `unresolved` (Text plus `[unklar …]`), `speaker_unclear` (`unknown`), `crosstalk` (`multiple`); Zeit = Sitzungszeit des Blockanfangs, auf Sekunden abgerundet, ohne Startzeit keine Zeit; Sprecher `open` und `label: null` unmarkiert |
| TOOL-53 | Abschlussbericht | 0.5 | 09.02.2027 | 09.02.2027 | erledigt: `src/transcript/report.py`, `transcript report`, README „Abschlussbericht“; `output/<s>/report.json` (`format_version: 1`) und `report.md` aus der gespeicherten Arbeitsfassung, die aktuell sein muss (`working.load_current`); Passagen je `origin`, Kandidaten je Stufe und Status, Kandidaten pro Stunde, Markierungen, Labels pro Segment mit Redezeit, Personen nur als Anzahl, `effort_minutes`; ASR, Diarisierung, Schwellenwerte und Snapshot mit ihren Segmenten; `gaps` (Exit 1) und `notes`; keine Genauigkeitsangabe, kein Text, keine Namen oder User-IDs |
| TOOL-69 | JSON-Export Contract v1 | 1 | 11.02.2027 | 11.02.2027 | erledigt: `src/transcript/export.py`, `src/transcript/contract.py`, `transcript export`, README „JSON-Export“; `output/<s>/transcript.json` nach Contract 1.0, vor dem Schreiben gegen die Schema-Kopie (`jsonschema`) und die Regeln jenseits des Schemas geprüft; Labels sessionweit `s01-SPEAKER_00`, ohne Label `unlabelled`; Passagen-ID aus Sitzungsstart und Label, über Review stabil; verweigert Passagen ohne Zeit, mehrere Aufnahmen (Contract 1.1 aus IOA-1287, Export in TOOL-89) und nicht ganzzahlige IDs; `review_note` `null`, `knowledge_hints` `[]`; Gegenprobe mit `transcript:validate`/`transcript:import` steht aus (lokale Narrata-Umgebung fehlte) |
| TOOL-51 | TXT-Rendering | 0.5 | 15.02.2027 | 15.02.2027 | erledigt: `src/transcript/rendering.py`, `transcript txt`, README „TXT-Ausgabe“; `output/<s>/transcript.txt` nur aus `transcript.json` (vorher gegen die Schema-Kopie geprüft), ein Absatz je Sprecherwechsel, `render.timestamps` `turn`/`passage`, Marker aus dem Contract inkl. `gap` (`markers.contract_marker_label`), byte-gleich bei erneutem Lauf |
| TOOL-52 | DOCX-Rendering | 0.5 | 15.02.2027 | 15.02.2027 | erledigt: `src/transcript/docx_render.py`, `transcript docx`, README „DOCX-Ausgabe“; `output/<s>/transcript.docx` nur aus `transcript.json`, Marker aus dem Contract, gleiche Regel `render.timestamps` wie TXT |
| IOA-1218 | Storage + idempotenter Import | 2 | 16.02.2027 | 18.02.2027 | erledigt: `transcript:import` und Upload-Endpoint in Narrata (ios-archiv PR #1138), gegen die IOA-1214-Fixture; die Probe gegen einen echten TOOL-69-Export folgt mit TOOL-58 |
| IOA-1287 | Contract 1.1: mehrere Aufnahmen in `source` | 1 | 22.02.2027 | 22.02.2027 | erledigt: optionales `source.recordings[]` (`file_name`, `duration_seconds`, `audio_sha256`, `starts_at`) in Sitzungsreihenfolge, `recordings[0]` gleich den Top-Level-Feldern; 1.0-Dateien bleiben gültig, Referenz-Fixture `session-v1-multi.json`; Pipeline-Seite in TOOL-89 |

### Phase 4 — End-to-End-Pilot

**M4 — Pilot-Review (TOOL-60): Kernhypothese geprüft; Entscheidungen Review-Kanal, Remote-Backend, Freigabe IT/OT. Zweiter großer Reflexionspunkt.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-56 | Preflight | 0.5 | 23.02.2027 | 23.02.2027 | erledigt: `src/transcript/preflight.py`, `transcript doctor`; prüft Werkzeuge, Konfiguration, Modelle sowie Eingabe, Wissen und Artefakte einer Sitzung; aus TOOL-9: `transcript doctor` war der Ausgangspunkt |
| TOOL-55 | E2E-CLI mit Halt an manuellen Schritten | 1 | 23.02.2027 | 25.02.2027 | aus TOOL-10: `transcript extract` ist der erste Schritt des E2E-Befehls; aus TOOL-56: der E2E-Befehl ruft `preflight.run` vor dem ersten Schritt auf und bricht bei Fehlern ab; erledigt: `transcript process` (`pipeline.py`, `docs/plans/TOOL-55-e2e-cli.md`) |
| TOOL-57 | Pipeline-Status + Resume, Fehlversuche dauerhaft protokollieren | 1.5 | 25.02.2027 | 01.03.2027 | in Arbeit: `docs/plans/TOOL-57-pipeline-status.md`; `transcript status` leitet Gesamt- und Schrittstatus nur aus den Dateien ab, ohne Statusdatei; `process` stoppt bei Modell- oder Snapshot-Wechsel bis `--redo`, Lock gegen parallele Läufe; TOOL-77 aufgenommen: Schrittwechsel und Fehlversuche aus `transcript.retry.FailureLog` in `work/<s>/pipeline.log`; aus TOOL-56: baut auf dem `resume`-Check auf; aus TOOL-55: baut auf `pipeline.STEPS` und `StepResult` auf |
| TOOL-86 | Sprecherzuordnung interaktiv (`transcript speakers --assign`) | 1 | 02.03.2027 | 02.03.2027 | vor TOOL-58, damit der Pilot den Zuordnungsaufwand mit dem Alltagsweg misst; Hörproben lokal abspielen, Auswahl aus dem Snapshot, atomar nach jedem Label; offen: Namen nur im interaktiven TTY (TOOL-66), Schreibregel für die handgemachte `assignment.json` (TOOL-68); aus TOOL-55: die Haltanweisung nennt für die Zuordnung dann `transcript speakers --assign` statt die Datei von Hand zu bearbeiten |
| TOOL-89 | Sitzungen mit mehreren Aufnahmen gegen Contract 1.1 exportieren | 0.5 | 04.03.2027 | 04.03.2027 | aus IOA-1287: `transcript export` schreibt `source.recordings[]` und `contract_version` `1.1`, statt mehrere Aufnahmen zu verweigern (`export._source`); Schema-Kopie und Fixture `session-v1-multi.json` aus ios-archiv übernehmen; Sitzungen mit einer Aufnahme bleiben unverändert; Reader vor Writer: erst exportieren, wenn Narrata 1.1 deployt hat; aus TOOL-55: bis dahin stoppt `process` bei Sitzungen mit mehreren Aufnahmen an `export` |
| TOOL-58 | Erste reale Session komplett (inkl. Review- und Zuordnungszeit) | 2 | 04.03.2027 | 09.03.2027 | Export → Fixture für IOA-1218; aus TOOL-69: AK „Import der Testsession über IOA-1218 ohne Korrektur“ liegt hier, dazu `transcript:validate`; `narrata.groups` muss die Gruppe kennen; eine Sitzung aus mehreren Aufnahmen braucht vorher TOOL-89 |
| TOOL-59 | Laufzeit/Ressourcen/Aufwand auswerten | 0.5 | 09.03.2027 | 09.03.2027 | aus TOOL-18: entscheidet, ob TOOL-78 (Versuche pro Segment im Referenzformat) gebraucht wird; aus TOOL-68/TOOL-53: `speakers.effort_minutes`, `review.per_hour` und die Review-Zähler sessionübergreifend aus `output/<s>/report.json` lesen, nicht aus `assignment.json` |
| TOOL-78 | Versuche pro Segment im Referenzformat | 0.5 | 11.03.2027 | 11.03.2027 | entfällt, wenn TOOL-59 keine Fehlerraten auswerten will; braucht eine neue `format_version` |
| TOOL-61 | E2E-Workflow dokumentieren | 0.5 | 11.03.2027 | 11.03.2027 | aus TOOL-55: die E2E-Doku beschreibt `transcript process`, die Haltpunkte und die Exit-Codes 0/1/2/3 |
| TOOL-60 | V0.1 bewerten, Entscheidungen, V0.2-Backlog | 1 | 15.03.2027 | 15.03.2027 | Go/No-Go für Phase 6; aus TOOL-35: am vollen Pilotlauf mit `transcript calibrate` prüfen, ob die Eingrenzung aus dem Bericht hält; aus TOOL-83: Archiv-Schreibtreffer am vollen Pilotlauf nach Methode und Stufe nachmessen (`--similar-judged`), bisher nur ein beurteilter Hinweis; aus TOOL-68: prüfen, ob die Unsicherheit pro Person gewichtet werden muss (Mundart 47,5 % gegen 14,0 % falsche Wörter, aus TOOL-36) |

### Phase 5 — Narrata-Oberflächen

**M5 — Transkript per Chat/MCP befragbar, in Narrata durchsuchbar, lesbar, verlinkt.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| IOA-1220 | Volltextsuche | 1.5 | 16.03.2027 | 18.03.2027 | erledigt, vor Phase 4 vorgezogen; Voraussetzung für IOA-1223 |
| IOA-1223 | Chat + MCP | 1.5 | 18.03.2027 | 22.03.2027 | Kernziel: der KI-Assistent antwortet der Spielleitung aus dem Transkript |
| IOA-1219 | Lese-UI am Session-Detail | 3 | 23.03.2027 | 29.03.2027 | erledigt, vor Phase 4 vorgezogen |
| IOA-1221 | Passage-Links | 2 | 30.03.2027 | 01.04.2027 | erledigt, vor Phase 4 vorgezogen |

### Phase 6 — IT/OT-Klassifikation

**M6 — IT/OT-Schicht im Export, Statistik im Bericht. Reflexionspunkt: TOOL-70 entscheidet ein oder zwei Durchläufe — oder Remote-Option.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-70 | Spike: lokales LLM an Goldstandard, Nutzen 2. Durchlauf | 2 | 05.04.2027 | 06.04.2027 | Labeln kostet die halbe Zeit |
| TOOL-71 | IT/OT-Datenmodell, Contract-Bump | 1 | 08.04.2027 | 08.04.2027 |  |
| TOOL-72 | Erstdurchlauf | 1.5 | 12.04.2027 | 13.04.2027 |  |
| TOOL-73 | Zweitdurchlauf + Metrik | 1.5 | 13.04.2027 | 15.04.2027 | entfällt, wenn TOOL-70 keinen Mehrwert misst |
| TOOL-74 | IT/OT-Review-Kandidaten | 0.5 | 19.04.2027 | 19.04.2027 |  |
| TOOL-75 | Sessionstatistik | 1 | 19.04.2027 | 20.04.2027 |  |

### Phase 7 — Extraktion und Analytik in Narrata

**M7 — Erste Welt-Archiv-Einträge mit Transkript-Provenienz; IT/OT-Statistik und Abendvergleich sichtbar.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| IOA-1222 | Transkript als Extraktionsquelle, polymorphe Provenienz | 3 | 20.04.2027 | 27.04.2027 | größte Migration des Epics |
| IOA-1224 | IT/OT-Flächen + Statistik | 2 | 27.04.2027 | 03.05.2027 |  |

### Phase 8 — Öffnung für andere Nutzer

**M8 — Entscheidung, ob und wie andere Narrata-Nutzer ihre Aufnahmen transkribieren können. Reflexionspunkt, kein Umsetzungsblock.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-85 | Entscheidung: Transkription für andere Narrata-Nutzer öffnen? | 0.5 | 03.05.2027 | 03.05.2027 | Wege: Nutzer rechnen lokal, eigener Worker getrennt vom Prod-VPS, externer ASR-Dienst, nichts tun; Datenschutz der Mitspielenden und Betriebsgrenzen klären; Erkenntnisse aus TOOL-59 und TOOL-60 einbeziehen; bei „ja“ Folge-Tickets |

### Phase 9 — Sprecher-Wiedererkennung

**M9 — Konzept für Stimmprofile mit Einwilligung pro Spielrunde, Go/No-Go. Reflexionspunkt, kein Umsetzungsblock.**

| Ticket | Inhalt | Tage | Start | Ende | Hinweis |
|---|---|---|---|---|---|
| TOOL-87 | Konzept: Sprecher über Sessions hinweg wiedererkennen | 1 | 04.05.2027 | 04.05.2027 | nur Konzept, Umsetzung als Folge-Tickets (TOOL und IOA); Stimmprofil = biometrisches Datum (Art. 9 DSGVO), Opt-in pro Mitgliedschaft im Narrata-Profil; Profile nur lokal, nur aus bestätigten Zuordnungen, Vorschläge nie ohne Bestätigung; Go/No-Go nach `effort_minutes` aus TOOL-59 mit TOOL-86; Kandidaten auf Anwesende eingrenzen (TOOL-79) |

## Pflege

- `transcript-roadmap.py` ist die Quelle (Reihenfolge, Aufwände, Kapazität, Pausen); diese Datei und die Jira-Daten sind generiert. Ändern → Skript laufen lassen → Jira per `editJiraIssue` (`customfield_10015`, `duedate`) aus der JSON-Ausgabe nachziehen.
- Nach jedem Meilenstein `START`/Aufwände an die Realität anpassen und neu rechnen; nach M4 die Phasen 5–7 bewusst neu terminieren (Pilot-Erkenntnisse).
- Verworfene oder neu geschnittene Tickets im Skript entfernen bzw. ergänzen und den Grund im Jira-Ticket festhalten.
