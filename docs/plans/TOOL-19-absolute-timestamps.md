# TOOL-19 — Absolute Zeitstempel in Referenztranskription übernehmen

## Ziel
Danach kann jeder nachgelagerte Schritt (Konfidenz TOOL-35, Review TOOL-46, Export TOOL-69) aus Manifest und Referenztranskript die Session-Zeit einer Passage oder eines Worts abfragen, ohne das Backend zu kennen. Er erfährt dabei auch, ob die Zeit wort- oder passagengenau ist, ob sie fehlt und ob sie am WAV-Ende begrenzt wurde. Heute gibt es nur `Segment.to_absolute_ms(local_seconds)`. Die Funktion nimmt Sekunden, obwohl das Referenzformat Millisekunden speichert, und sie bricht bei einer Zeit auch nur 1 ms hinter dem WAV-Ende mit `ValueError` ab.

## Ist-Stand
- `src/transcript/manifest.py:97-119`: `Segment` mit `start_ms`, `end_ms`, `overlap_before_ms`, `duration_ms`. `to_absolute_ms(local_seconds: float)` rechnet über `seconds_to_ms` und lehnt `local_ms > duration_ms` ab. Außer Tests (`tests/test_manifest.py:253-260`) ruft niemand die Funktion auf.
- `src/transcript/manifest.py:296-310` `_check_timeline`: Segmente sind lückenlos, `start_ms = previous_end - overlap_before_ms`. Heute ist `overlap_before_ms` immer 0 (`:182`), weil TOOL-11 entfällt.
- `src/transcript/reference.py:442-471`: `Word` und `Passage` speichern `start_ms`/`end_ms` lokal zum Segment-WAV, beide optional (`None`). `check_span` (`:948-953`) erlaubt auch nur eine gesetzte Grenze. `AsrInfo.capabilities` (`:491`) hält `word_timestamps` und `segment_timestamps` des Backends fest, also die Herkunft.
- `src/transcript/reference.py:717-740` `_passage_from`: Hier normalisiert der Adapter. Er macht Sekunden zu ms und lässt `None` stehen. Die Normalisierung aus dem Ticket („über den Adapter“) gibt es also schon seit TOOL-16.
- `src/transcript/timecode.py:16-23` `format_ms`: `HH:MM:SS.mmm`, Stunden laufen über 99 hinaus.
- `src/transcript/asr/whisper.py:214-226`: Whisper liefert Passagen- und Wortzeiten. Granite liefert laut `docs/referenzformat.md:50` gar keine Zeiten, ein Backend ohne Wörter liefert leere `words`.
- Doku: `docs/referenzformat.md:54` und `docs/asr-backends.md:39` verweisen auf `Segment.to_absolute_ms`.

## Entscheidungen
- **Absolute Zeiten werden nicht gespeichert** (Übergabe TOOL-16). Sie werden beim Lesen aus Manifest und Referenz berechnet und bleiben so richtig, wenn das Manifest neu gebaut wird. Auch die Granularität wird nicht gespeichert. Sie folgt aus den vorhandenen Feldern, die Herkunft steht schon in `asr.backend_id` und `asr.capabilities`. Der Punkt „Granularität nachvollziehbar speichern“ ist damit ohne Formatänderung erfüllt.
- **`Segment.to_absolute_ms(local_ms: int) -> int`** nimmt künftig Millisekunden, die Einheit des Referenzformats. Die Sekunden-Variante hat keinen Aufrufer außerhalb der Tests.
- **Begrenzung am WAV-Ende:** Eine lokale Zeit bis `END_TOLERANCE_MS = 1000` hinter `duration_ms` wird auf das Segmentende gesetzt, alles darüber hinaus ist ein `ValueError` mit Segmentnummer und ms-Wert. 1 s deckt das Runden der Backends und das Polstern des letzten Worts ab. Ein größerer Abstand deutet auf ein falsches WAV oder ein veraltetes Manifest hin und darf nicht still verschwinden. Negative Werte bleiben ein Fehler.
- **Begrenzung ist sichtbar, nicht still:** Das Ergebnis trägt `clamped=True`, der lokale Originalwert bleibt erhalten. Damit gilt weiterhin „kein Schritt korrigiert Zeiten still“ (TOOL-16).
- **Neues Modul `src/transcript/session_time.py`**, weil es Manifest und Referenz zusammenführt und `reference.py` schon 570 Zeilen hat:
  - `SessionSpan` (frozen): `granularity` (`"word"` | `"passage"`), `local_start_ms`, `local_end_ms`, `start_ms`, `end_ms` (jeweils `int | None`, nur bei fehlendem Backendwert `None`) und `clamped: bool`. Dazu `timecode()`, das `HH:MM:SS.mmm–HH:MM:SS.mmm` über `format_ms` liefert und für eine fehlende Grenze `?` schreibt.
  - `passage_span(segment, passage)` und `word_span(segment, word)` geben `None` zurück, wenn beide Grenzen fehlen. Erfunden wird kein Wert, und eine Passagenzeit wird nicht auf ihre Wörter übertragen oder umgekehrt.
  - `time_granularity(reference) -> "word" | "passage" | "none"`: die feinste Stufe, für die das Transkript tatsächlich Zeiten hat. Maßgeblich sind die Daten, nicht die Capabilities, denn ein Wort-fähiges Backend kann für ein stilles Segment trotzdem nichts liefern.
  - Prüft, dass `reference.segment.index == segment.index`, sonst `ValueError`. So landet keine Zeit im falschen Segment.
- **Überlappung:** Da `start_ms ≥ 0` und das Ergebnis höchstens `segment.end_ms ≤ manifest.duration_ms` ist, kann kein Wert negativ werden oder hinter der Session liegen, auch im Überlappungsbereich nicht. Deduplizieren gehört nicht zum Scope. Getestet wird mit einem konstruierten Manifest mit `overlap_before_ms > 0`.

## Daten-Check
- Fehlermeldungen: handled. `ValueError`s nennen nur Segmentnummer, ms-Wert und Segmentdauer, nie Text, Wörter oder Labels (wie `reference.py:8-9`).
- Logs: N/A. Das Modul loggt nichts.
- Fixtures/Tests: handled. Nur erfundene `Segment`-, `Passage`- und `Word`-Objekte im Code, keine neuen Fixture-Dateien.
- Arbeitsdateien und Rohaudio: N/A. Es wird nichts geschrieben und kein Audio gelesen.

## Contract-Check
N/A. Es wird kein Contract-JSON gelesen oder geschrieben. TOOL-69 bildet die Passagenzeiten des Exports später über `passage_span` ab. Ob IOA-1214 Granularität oder `clamped` abbildet, entscheidet TOOL-69 gegen den Validator. Auf der Narrata-Seite ändert sich nichts.

## Resume-Check
N/A. Eine reine Berechnung, ohne Modell, lang laufenden Schritt oder Zustand.

## Dependency-Check
N/A. Weder neues Paket noch neues Modell.

## Format-Check
- Referenzformat: handled. Unverändert, `REFERENCE_FORMAT_VERSION` bleibt 1, vorhandene `segment-NN.json` bleiben lesbar.
- Manifest: handled. Unverändert, `MANIFEST_FORMAT_VERSION` bleibt 1. Nur die Signatur von `to_absolute_ms` ändert sich, nicht die Datei.

## Chunks
### Chunk 1 — Umrechnung in Millisekunden mit Toleranz am WAV-Ende
- Dateien: `src/transcript/manifest.py`, `tests/test_manifest.py`
- Änderung: `END_TOLERANCE_MS`, `Segment.to_absolute_ms(local_ms: int)`, das bis zur Toleranz auf `end_ms` begrenzt und dahinter oder bei negativem Wert `ValueError` wirft. Bestehenden Test auf ms umstellen.
- Verify: `scripts/check`
- AC: `to_absolute_ms(250)` im zweiten Segment ergibt `start_ms + 250`. `duration_ms + 1000` ergibt `end_ms`. `duration_ms + 1001` und `-1` werfen `ValueError`, die Meldung nennt Segmentnummer und Wert.

### Chunk 2 — `session_time`: Spannen, Granularität, Darstellung
- Dateien: `src/transcript/session_time.py`, `tests/test_session_time.py`
- Änderung: `SessionSpan`, `passage_span`, `word_span`, `time_granularity`, `SessionSpan.timecode()`, wie unter Entscheidungen beschrieben.
- Verify: `scripts/check`
- AC:
  - Wort bei lokal `00:02:13.500` in einem Segment ab `01:19:45.000` → `start_ms` ergibt `01:21:58.500`, `local_start_ms` bleibt 133 500, `granularity == "word"`.
  - Ereignis in einem Segment nach mehr als einer Stunde → `timecode()` beginnt mit `01:`.
  - Passage mit Zeiten und ohne Wörter → `time_granularity == "passage"`. Mit Wortzeiten → `"word"`. Nur Text (Granite-artig) → `"none"`, `passage_span` ist `None`.
  - Nur `start_ms` gesetzt → `end_ms is None`, `timecode()` endet auf `?`.
  - Endzeit 400 ms hinter dem WAV-Ende → `end_ms == segment.end_ms`, `clamped`, `local_end_ms` unverändert. Im letzten Segment gilt `end_ms ≤ manifest.duration_ms`.
  - Segment mit `overlap_before_ms > 0`, Zeit 0 → `start_ms == segment.start_ms ≥ 0`.
  - Referenz von Segment 2 mit Segment 1 → `ValueError`.

### Chunk 3 — Doku
- Dateien: `docs/referenzformat.md`, `docs/asr-backends.md`
- Änderung: In `referenzformat.md` neuer Abschnitt „Session-Zeit“: Aufruf von `passage_span`/`word_span`, die drei Granularitäten, das Verhalten ohne Zeiten bzw. mit nur Passagenzeiten, Toleranz und `clamped`, Überlappung. Regel `:54` darauf verweisen lassen. In `asr-backends.md:39` steht dann: Der Adapter macht Sekunden zu ms, `session_time` rechnet sie in Session-Zeit um.
- Verify: `scripts/check`
- AC: Beide Fälle aus dem Ticket („nur Segment-“ und „gar keine Zeitinformationen“) sind beschrieben. Kein Verweis auf eine Sekunden-Signatur von `to_absolute_ms` bleibt übrig.

## Folge-Tickets
- TOOL-69: Beim Export Passagenzeiten über `session_time.passage_span` bilden und prüfen, ob Contract v1 die Granularität und `clamped` aufnehmen soll. Kommentar ans Ticket beim Abschluss.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | `Segment.to_absolute_ms` in ms, Toleranz am WAV-Ende | no |
| 2 | `session_time`: Spannen, Granularität, Timecode | no |
| 3 | Doku Referenzformat und Backends | no |
