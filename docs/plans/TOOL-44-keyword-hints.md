# TOOL-44 — Domänenwissen kontrolliert als ASR- und Review-Signal verwenden

## Ziel
Archivbegriffe wirken vor der ASR nur, wo sie nachweislich nicht schaden. Nach der ASR erzeugen sie Review-Hinweise mit Verweis auf den Archiveintrag. Heute bekommt jedes Whisper-Modell die Hotwords, auch `large-v3`, dessen Ausgabe dadurch zerfällt (TOOL-62). Nach der ASR nutzt die Pipeline das Wissen gar nicht: Ein bekannter Hörfehler im Text bleibt unbemerkt. Danach gibt es pro Segment eine Hinweisdatei. Sie markiert bekannte Hörfehler als starkes Signal, ähnliche Schreibungen als schwaches Signal und Mehrdeutiges als unsicher. Der ASR-Text bleibt unverändert.

## Ist-Stand
- Keywords: `__main__._transcribe` holt `domain.transcription_keywords()` (`src/transcript/__main__.py:477`) und übergibt sie an `transcribe_session(keywords=…)` (`src/transcript/transcription.py:92`). Ein Backend ohne `keyword_biasing` bekommt `hints = None` und ignoriert sie (`transcription.py:123`).
- Token-Kappung: `fit_hotwords` nimmt das längste Präfix, das in `HOTWORD_TOKENS = 223` passt (`src/transcript/asr/whisper.py:45`, `:195`). Was ankam, steht als `asr.keywords_used` im Referenztranskript (`src/transcript/reference.py:98`). Die Priorität kommt aus der Glossar-Reihenfolge nach Stufen (TOOL-39) und dem Budget pro Typ (TOOL-41). Damit sind „Kappung“ und „Priorisierung pro Backend“ aus den Übergaben erledigt.
- Turbo-Regel: `CAPABILITIES` ist eine Modulkonstante mit `keyword_biasing=True` für jedes Modell (`whisper.py:36`, `:61`). `Config.asr_model` darf ein beliebiger faster-whisper-Name oder ein lokales Verzeichnis sein (`src/transcript/config.py:69`).
- Wissen nach der ASR: `DomainContext.lookup` (exakt, normalisiert) und `match_candidates()` (alle Terme samt `asr_variant`) liegen bereit (`src/transcript/domain.py:93`, `:122`). `ambiguities` kommen aus Narrata (`domain.py:68`). `TermHit` trägt Eintrag, Art, Feld, Term, Keyword-Flag und Herkunft (`domain.py:44`). `glossary.normalize` ist der Vergleichsschlüssel (`src/transcript/glossary.py:21`).
- Transkriptdaten: `ReferenceTranscript.passages` mit `Passage.text` und `words` samt Zeiten (`reference.py:61`, `:47`).
- Muster für eine abgeleitete Datei mit eigener Version und ohne Namen auf der Konsole: `diagnosis.py` (`REPORT_FORMAT_VERSION`, `write_atomic`).
- Ein Review-Datenmodell gibt es noch nicht (TOOL-46), Review-Kandidaten folgen in TOOL-36.

## Entscheidungen
Im Chat vom 05.11.2026 entschieden:

- **Abgrenzung zu TOOL-40:** TOOL-44 liefert beide Signalarten, also bekannte Hörfehler (stark) und Ähnlichkeit (schwach). TOOL-40 übernimmt Kontext/Gültigkeitsbereich von Varianten und die Vorschlagsliste aus Review-Korrekturen. Die Roadmap-Hinweise an TOOL-40 werden umgeschrieben, und TOOL-40 bekommt einen Übergabekommentar.
- **Turbo-Regel im Backend:** `WhisperBackend` setzt `self.capabilities` pro Instanz. `keyword_biasing` ist nur wahr, wenn der Modellname, bei einem Verzeichnis dessen letzter Teil, `turbo` enthält (Groß-/Kleinschreibung egal). Andere Modelle bekommen keine Hotwords, `keywords_used` bleibt leer, und `transcribe` meldet einmal: `keywords not passed: model <name> takes no hotwords`. Es gibt keinen neuen Konfigurationsschlüssel. Das Referenztranskript hält die Capabilities schon fest, damit ist die Entscheidung nachvollziehbar.
- **Nachvollziehbarkeit vor der ASR:** `keywords_used` plus `knowledge_snapshot_id` reichen. Die Konsole meldet nach dem Lauf zusätzlich, wie viele der angebotenen Keywords angekommen sind (`63 of 120 keyword(s) passed`). Sie nennt nur Zahlen.
- **Hinweise als eigene Datei:** `work/<key>/review/segment-NN.hints.json` mit `format_version: 1`. Das Referenztranskript wird weder geändert noch versioniert. TOOL-46 entscheidet später, wie die Hinweise ins Review-Modell eingehen.
- **Abgleich (`src/transcript/hints.py`):** Er läuft über Wortfolgen aus 1 bis n Wörtern der Passagen. n ist die größte Wortzahl eines Terms, höchstens 4. Satzzeichen am Rand werden entfernt, verglichen wird über `normalize`, zusätzlich ohne Leerraum. So trifft „Grau Wasser“ auf „Grauwasser“.
  - *Exakter Treffer auf `asr_variant`* → Signal `known_variant` (stark).
  - *Exakter Treffer auf Name oder Alias* → kein Hinweis, der Begriff ist richtig erkannt.
  - *Kein exakter Treffer, aber ähnlich* zu Name oder Alias → Signal `similar` (schwach), mit `method` `spelling` (difflib-Ratio ≥ 0,85) oder `sound` (gleicher Kölner-Phonetik-Code). Der Term muss mindestens 4 Zeichen lang sein, die Länge darf höchstens um 30 % abweichen. Vorgefiltert wird über Längen- und Phonetik-Buckets, damit 5 h Audio gegen das volle Archiv in Sekunden laufen.
  - Überlappende Treffer: Es bleibt der längste, bei gleicher Länge der stärkere.
- **Mehrdeutigkeit:** Ein Hinweis trägt alle Kandidaten-Einträge. `ambiguous: true` gilt, wenn mehr als ein Eintrag passt oder Narrata die Variante in `asr_ambiguities` führt. Das Signal wird dann nie zur Empfehlung, die Kandidaten stehen in Glossar-Reihenfolge, gewählt wird keiner.
- **Einfluss dokumentieren:** Jeder Kandidat trägt `type`, `id`, `term`, `kind`, `field`, `relevance` und `biased` (der Term stand in `keywords_used`). Der Dateikopf trägt `knowledge_snapshot_id`, `keywords_used`-Anzahl und die Herkunft der Referenz (`processed_at`).
- **Sprecherwissen:** Es ist über `DomainContext.participants`/`character` schon als Metadaten verfügbar (TOOL-43). TOOL-44 schreibt dafür nichts, die Sprecherprüfung ist TOOL-68.
- **Kein Ersetzen:** `hints.py` gibt nur Daten zurück, kein Code-Pfad schreibt `Passage.text` oder `Word.text`. Ein Test prüft das byte-genau an der Referenzdatei.
- **Phonetik ohne Abhängigkeit:** Die Kölner Phonetik wird mit etwa 40 Zeilen stdlib selbst implementiert, Ähnlichkeit über `difflib.SequenceMatcher`. Beides passt zu deutscher Aussprache, für Fantasienamen ist es ein Näherungswert. Die Schwellen sind Startwerte, kalibriert wird in TOOL-35.

## Daten-Check
- Folgt TOOL-66? *handled*: Die Hinweisdatei enthält erkannten Text und Archivnamen. Sie liegt unter `work/` und ist per `.gitignore` ausgeschlossen. Die Konsole meldet nur Zahlen (`3 known variant(s), 11 similar, 2 ambiguous`). Die Turbo-Meldung nennt den Modellnamen, nie Keywords.
- Kann Echtes ins Repo? *handled*: Die Tests nutzen erfundene Namen inline (`Grauwasser`, `Ærwyn Þornfeld`, Muster `tests/test_glossary.py`), `tests/fixtures/` bekommt nichts.
- Logs/Fehlermeldungen? *handled*: `hints.py` loggt nichts. Fehler beim Lesen der Hinweisdatei nennen Datei, Feld und Index, nie einen Wert (Muster `reference._field`). Ein Smoke-Test prüft stdout/stderr auf Fixture-Namen.

## Contract-Check
- N/A, weil weder Contract-JSON noch der Narrata-Endpoint berührt werden. Gelesen wird nur der Snapshot über `DomainContext`. Ob Hinweise in den Export gehen, entscheidet TOOL-69 gegen IOA-1214.

## Resume-Check
- Abbruch? *handled*: Die Hinweise entstehen am Ende von `transcribe` pro Segment mit transkribiertem Ergebnis und werden atomar geschrieben (`jsonfile.write_atomic`). Ein Abbruch hinterlässt höchstens alte Dateien, und die überschreibt der nächste Lauf.
- Wiederverwendung? *handled*: Der Abgleich ist deterministisch, billig und ohne Modell. Er läuft deshalb bei jedem `transcribe` neu, auch für wiederverwendete Segmente, und hält so stets Snapshot und Referenz ein. Ohne Snapshot entsteht keine Hinweisdatei, und eine vorhandene wird entfernt, damit kein veralteter Wissensstand liegen bleibt.
- Gleiches Modell/Snapshot? *handled*: Die ASR-Wiederverwendung bleibt unverändert (`_reusable`). Ein Turbo-Wechsel ändert die Modell-Identität und damit ohnehin die Wiederverwendung. Die Hinweisdatei trägt die `knowledge_snapshot_id`, aus der sie entstand.

## Dependency-Check
- N/A, weil es keine neue Abhängigkeit gibt: `difflib`, `unicodedata` und eine eigene Kölner Phonetik, alles stdlib und lokal.

## Format-Check
- Neues Format Hinweisdatei: *handled*: `format_version: 1`. Der Leser lehnt andere Versionen ab und verweist auf `transcript transcribe`, das sie neu erzeugt.
- Referenztranskript: N/A, weil kein Feld hinzukommt. `capabilities.keyword_biasing` wird schon geschrieben, `REFERENCE_FORMAT_VERSION` bleibt 2.
- Snapshot, Manifest, Diarisierung: N/A, weil unverändert.

## Chunks
### Chunk 1 — Turbo-Regel und Keyword-Zählung
- Dateien: `src/transcript/asr/whisper.py`, `src/transcript/__main__.py`, `tests/test_asr_whisper.py`, `tests/test_smoke.py`, `README.md` („Spracherkennung“)
- Änderung: `takes_hotwords(model)`. `WhisperBackend.__init__` setzt `self.capabilities = replace(CAPABILITIES, keyword_biasing=takes_hotwords(model))`. `_transcribe` meldet die Abschaltung einmal und nach dem Lauf „M of N keyword(s) passed“ aus den Referenzen.
- Verify: `scripts/check`
- AC: `large-v3-turbo` und `/models/whisper-Large-V3-Turbo` biasen, `large-v3` und `medium` nicht. Mit `large-v3` geht kein Hotword an das Modell (Fake-Model im Test), `keywords_used` ist leer. Die Konsole nennt keine Keywords.

### Chunk 2 — Abgleich nach der ASR
- Dateien: `src/transcript/hints.py` (neu), `tests/test_hints.py` (neu)
- Änderung: `cologne_phonetic(term)`, `Candidate`, `Hint(passage, first_word, last_word, start_ms, end_ms, heard, signal, method, score, candidates, ambiguous)`, `find_hints(reference, domain) -> tuple[Hint, ...]` mit Wortfolgen, exaktem Abgleich über `domain.lookup`, Ähnlichkeit mit Vorfilter und Überlappungsregel.
- Verify: `scripts/check`
- AC: eindeutiger Fall (Hörfehler eines Eintrags → `known_variant`, ein Kandidat, nicht mehrdeutig) und mehrdeutiger Fall (Variante zweier Einträge bzw. in `asr_ambiguities` → `ambiguous`, beide Kandidaten in Glossar-Reihenfolge). Ein richtig erkannter Name ergibt keinen Hinweis. „Grau Wasser“ ergibt `similar` auf „Grauwasser“. Ein Allerweltswort unter 4 Zeichen ergibt keinen Hinweis. `biased` folgt `keywords_used`. Die Referenzdatei ist danach byte-gleich. Ein synthetisches Segment mit 30 000 Wörtern gegen 1 500 Terme läuft unter 10 s.

### Chunk 3 — Hinweisdatei, CLI und Doku
- Dateien: `src/transcript/hints.py`, `src/transcript/session.py`, `src/transcript/__main__.py`, `tests/test_hints.py`, `tests/test_smoke.py`, `README.md` (neuer Abschnitt „Review-Hinweise“), `docs/transcript-roadmap.py` (Hinweis TOOL-40)
- Änderung: `SessionPaths.review_hints(index)`, `write_hints`/`load_hints` mit `format_version: 1`. `_transcribe` schreibt nach dem Lauf pro transkribiertem Segment die Hinweise oder entfernt sie ohne Snapshot und meldet Zahlen.
- Verify: `scripts/check`
- AC: Ein Rundlauf erhält alle Felder. Eine fremde Version wird mit Datei und Feld abgelehnt. Der Smoke-Test `transcribe` mit Fake-Backend und Snapshot schreibt die Datei, und stdout/stderr enthalten keinen Fixture-Namen. Ohne Snapshot gibt es keine Datei. Die README beschreibt Signale, Schwellen und dass nichts ersetzt wird.

## Verifikation gesamt
`scripts/check` nach jedem Chunk. Am Ende `transcript transcribe <key>` auf einer echten Session mit Snapshot: Konsole prüfen (nur Zahlen), `work/<key>/review/` stichprobenartig gegen das Audio lesen.

## Folge-Tickets
- TOOL-40: Kontext/Gültigkeitsbereich der Varianten und die Vorschlagsliste aus Review-Korrekturen. Der Fuzzy-/Phonetik-Abgleich ist mit TOOL-44 erledigt (`transcript.hints`), Kommentar am Ticket.
- TOOL-35: Schwellen von `similar` (Ratio 0,85, Mindestlänge 4, Längenabweichung 30 %) an der Stichprobe kalibrieren.
- TOOL-36: Review-Kandidaten lesen `review/segment-NN.hints.json`; `known_variant` und `ambiguous` gehen bevorzugt in die Auswahl.
- TOOL-46: Hinweise ins Review-Datenmodell übernehmen, das Format der Hinweisdatei ist Eingang dafür.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Turbo-Regel, Keyword-Zählung | no |
| 2 | `hints.py`: Abgleich | no |
| 3 | Hinweisdatei, CLI, README, Roadmap-Hinweis | no |
