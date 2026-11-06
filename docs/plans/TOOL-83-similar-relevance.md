# TOOL-83 — similar-Präzision nach Relevanz-Stufe neu messen und Gewichtung entscheiden

## Ziel
In TOOL-35 lag die Präzision von `similar` über den Klang bei 29 %, über die Schreibung bei 70 %. Nach Relevanz-Stufe ließ sie sich nicht aufschlüsseln, weil alle 199 Nicht-Spielfiguren im Archiv standen. Seit IOA-1278 ist `recent` gefüllt und Ereignisse sind aus dem Glossar entfernt. Danach lässt sich die Präzision je Methode **und** Stufe messen und entscheiden, ob Archiv-Treffer strenger behandelt werden müssen. Die ASR der Messsitzung wird dabei nicht neu gerechnet.

## Ist-Stand
- Der Bogen `similar_sheet` (`src/transcript/calibration.py:421`) schreibt die Spalten `SHEET_COLUMNS` (`calibration.py:44`) ohne Relevanz-Stufe. Die Stufe steckt nur in `Candidate.relevance` der Hinweisdatei (`src/transcript/hints.py:69`).
- `judged_precision` (`calibration.py:468`) gruppiert nach Methode und Score-Band (`_band`, `calibration.py:509`), nicht nach Stufe.
- `RELEVANCE_TIERS` (`src/transcript/narrata.py:87`) ist von nah nach fern sortiert.
- Hinweise entstehen nur in `transcribe` (`src/transcript/__main__.py:571`, `hints.review_session`, `hints.py:417`). Die Snapshot-Kennung ist Teil der Wiederverwendung (`src/transcript/transcription.py:290`). Ein neuer Snapshot hieße also: alle 5:26 h neu transkribieren. Das Ticket verlangt aber, dass die ASR bleibt.
- Hinweise passen zu einer Referenz über `reference_processed_at` (`hints.py:389`), nicht über den Snapshot. Die Bewertung übernimmt die Snapshot-Kennung der Hinweise (`src/transcript/uncertainty.py:362`). Neue Hinweise auf alter ASR sind also zulässig und nachvollziehbar.
- `assess` (`__main__.py:147`, `_assess` `:609`) bewertet nur, Hinweise baut es nicht.
- Der alte Bogen aus TOOL-35 hat keine Spalte `relevance`.

## Entscheidungen
- **Stufe pro Bogenzeile = die nächste Stufe unter den Kandidaten** (erste Stufe in `RELEVANCE_TIERS`). Ein Hinweis zählt so dort, wo er für die Review am meisten Gewicht hätte. Mehrdeutige Hinweise sind selten (22 von 413).
- **Neue Spalte `relevance` im Bogen**, vor `correct`. `--similar-judged` gibt dann zusätzlich Zeilen `similar <methode> / <stufe>` aus. Fehlt die Spalte wie im alten Bogen, bleibt die Ausgabe wie bisher.
- **`transcript assess --hints`** baut die Hinweise aus dem aktuellen Snapshot neu (`hints.review_session` mit `config.review_similar`) und bewertet danach. Das ist dauerhaft nützlich: nach IOA-1279, nach Glossar-Pflege und für TOOL-60. Ein Wegwerf-Skript wäre nicht reproduzierbar. Ein `transcribe` würde die ASR verwerfen.
- **Die Regelentscheidung (Schritt 3 des Tickets) fällt erst nach dem Anhören.** Es gibt drei Wege, festgelegt wird nur, nach welchen Kriterien entschieden wird:
  - (a) Das neue Glossar reicht: Archiv- und Recent-Präzision liegen nah beieinander, keine Regeländerung.
  - (b) Eigene Stufe für Archiv-Treffer, etwa `similar_archive_level`, analog zu `similar_sound_level`. Infrage kommt das, wenn Archiv-Treffer klar schlechter sind und die Score-Bänder sie nicht trennen.
  - (c) Strengeres `min_ratio` für Archiv-Treffer. Infrage kommt das, wenn Schreibungs-Treffer im Archiv erst ab einem höheren Score stimmen.
  - Ob IOA-1279 abgewartet wird, hängt am Rest der Archiv-Fehlalarme: Gehen sie auf tote Begriffe zurück, die das Ausschluss-Kennzeichen entfernt, wird abgewartet.

## Daten-Check
- Bogen und Hinweisdateien: *handled* — Sie enthalten echte Namen und bleiben unter `work/…/review/` (TOOL-66). Die neue Spalte enthält nur den Stufen-Namen.
- Konsolenausgabe: *handled* — `--similar-judged` und `assess --hints` geben nur Zählwerte, Stufen- und Methodennamen aus, nie Text oder Namen. Ein Test prüft, dass kein Fixture-Begriff in der Ausgabe steht, wie `tests/test_calibration.py:279`.
- Fehlermeldungen: *handled* — Ein ungültiger Wert in `relevance` nennt nur Zeile und Feld, nicht den Wert, wie `test_an_invalid_answer_names_the_line_but_not_the_value`.
- Bericht: *handled* — Er enthält nur Kennzahlen, keine Namen und keinen Session-Schlüssel, wie TOOL-35. Der Agent liest weder Bogen noch Hinweise noch Transkripte, die Zahlen kommen aus der Konsolenausgabe.
- Fixtures: *handled* — nur die fiktiven Begriffe der bestehenden Tests (`Grauwasser`).

## Contract-Check
- Lesen des Kontexts: *handled* — IOA-1278 ändert laut Ticket-Kommentar nur den Inhalt, nicht die Form. Contract 1.1 gilt weiter, die Pipeline braucht keine Änderung. `event` bleibt in `ENTRY_TYPES` (`narrata.py:84`) zulässig, es kommt nur nicht mehr vor.
- Narrata-Änderung: *N/A, weil* keine nötig ist. Fällt die Entscheidung auf Abwarten, trägt IOA-1279 den Rest.
- Messfehler durch Eigenbezug: *handled* — IOA-1278 lässt die aktuelle Sitzung im Fenster, wenn sie eine Quelle hat. Liegt in Narrata schon ein Transkript der Messsitzung, kämen ihre eigenen Begriffe nach `recent`. Der Bericht hält die Stufenzahlen des neuen Snapshots fest. Weichen sie von 3 / 0 / 113 / 86 ab, wird der Grund vor der Auswertung geklärt.

## Resume-Check
- `assess --hints`: *N/A, weil* der Schritt kurz ist und kein Modell braucht. Er schreibt die Hinweise pro Segment neu, ein Abbruch lässt sich durch erneuten Aufruf beheben.
- ASR: *handled* — `assess --hints` lässt `asr/` unberührt. Die Referenz behält ihre alte Snapshot-Kennung, Hinweise und Bewertung tragen die neue. Das README warnt: Ein späteres `transcribe` derselben Sitzung transkribiert wegen der neuen Kennung neu (`transcription.py:290`). Für die Messung wird `transcribe` deshalb nicht aufgerufen.
- Snapshot: *handled* — `transcript snapshot --refresh` baut den neuen Snapshot, seine Kennung kommt in den Bericht.

## Dependency-Check
*N/A, weil* weder Abhängigkeit noch Modell neu sind.

## Format-Check
- Hinweisdatei `format_version: 1`: *N/A, weil* sich das Format nicht ändert, `relevance` steht dort schon.
- Bogen: *handled* — Er hat keine Versionsnummer. Neue Spalte, alte Bögen ohne `relevance` werden weiter gelesen (Test).

## Chunks
### Chunk 1 — Relevanz-Stufe im similar-Bogen
- Dateien: `src/transcript/calibration.py`, `tests/test_calibration.py`, `README.md` (Abschnitt Kalibrierung, `README.md:316`)
- Änderung: `SheetRow.relevance` mit der nächsten Kandidaten-Stufe und Spalte `relevance` in `SHEET_COLUMNS` vor `correct`. `judged_precision` zählt zusätzlich je `<methode> / <stufe>`, falls die Spalte da ist. Ein unbekannter Stufen-Wert ergibt eine Fehlermeldung mit Zeilennummer.
- Verify: `scripts/check`
- AC: Ein Bogen mit Stufen liefert Zeilen wie `similar sound / archive: …`. Ein Bogen ohne Spalte liefert die Ausgabe wie bisher. In der Ausgabe stehen keine Begriffe.

### Chunk 2 — `transcript assess --hints`
- Dateien: `src/transcript/__main__.py` (Parser `:147`, `_assess` `:609`), `tests/test_smoke.py`, `README.md` (Unsicherheitsbewertung `:271`, Hinweise `:267`)
- Änderung: Das Flag `--hints` ruft vor `_rate_passages` `hints.review_session(paths, indices, _domain(paths), config.review_similar)` auf und gibt die Zählzeile `review hints: …` aus, wie `transcribe`. Das README sagt, wann man es braucht (neuer Snapshot ohne neue ASR) und warnt vor einem späteren `transcribe`.
- Verify: `scripts/check`
- AC: Nach einem Snapshot-Wechsel schreibt `assess --hints` Hinweise mit der neuen `knowledge_snapshot_id` und lässt `asr/` unverändert (Smoke-Test). Ohne Snapshot werden alte Hinweise entfernt, wie bei `transcribe`.

### Chunk 3 — Neumessung und Bericht
- Ablauf (Nutzerin): `transcript context`, dann `snapshot --refresh`, `assess --hints`, `calibrate --similar-sheet`, anhören, `calibrate --similar-judged`. Danach Konsolenausgabe weitergeben.
- Dateien: `docs/spikes/TOOL-35-kalibrierung.md`, neuer Abschnitt „Neumessung nach IOA-1278 (TOOL-83)“: Snapshot-Kennung, Stufenzahlen, Hinweiszahl je Methode und Stufe, Präzision je Methode × Stufe, Vergleich mit TOOL-35.
- Verify: `scripts/check`
- AC: Die Präzision je Methode und Relevanz-Stufe ist im Bericht ergänzt.

### Chunk 4 — Entscheidung
- Dateien bei (a): nur der Bericht (Abschnitt „Entscheidung“). Bei (b)/(c) zusätzlich `src/transcript/config.py`, `src/transcript/hints.py` bzw. `src/transcript/uncertainty.py`, `config/example.yaml`, `README.md:287`/`:345–348` und Tests.
- Verify: `scripts/check`, bei Regeländerung zusätzlich `assess` und `--similar-judged` am Bogen wiederholen
- AC: Die Entscheidung ist begründet. Bei einer Regeländerung sind Konfiguration, Defaults und README nachgezogen.

## Folge-Tickets
- Kalibrierung nach IOA-1279 wiederholen, falls die Entscheidung auf Abwarten fällt: `[kein Ticket: entsteht erst mit der Entscheidung in Chunk 4, sonst entfällt es]`. Wird abgewartet, wird es vor dem Abschluss angelegt.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Bogen: Spalte `relevance`, Präzision je Stufe | no |
| 2 | `assess --hints` | yes |
| 3 | Neumessung, Bericht | no |
| 4 | Entscheidung, ggf. Regeländerung | no |
