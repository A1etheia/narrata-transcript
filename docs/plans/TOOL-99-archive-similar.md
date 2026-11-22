# TOOL-99 — similar-Schreibtreffer auf Archivbegriffe heben keine Passage mehr an

## Ziel
Ein `similar`-Hinweis, der über die Schreibung gefunden wurde und dessen nächste Relevanz-Stufe `archive` ist, macht eine sonst sichere Passage heute zu `needs_review`. An der Pilotsitzung waren davon nur 2 von 18 richtig (TOOL-60). Danach regelt eine eigene Schwelle `similar_archive_level` (Default `confident`) diese Treffer. Der Hinweis bleibt in der Hinweisdatei, wie bei Klang-Treffern seit TOOL-35.

## Ist-Stand
- `src/transcript/uncertainty.py:277-299` `_hints`: `ambiguous` → `uncertain`, `known_variant` → `needs_review`, sonst `similar_sound_level` bei `method == "sound"`, sonst `similar_level`. Bei `confident` entsteht kein Grund.
- `src/transcript/config.py:112-114` Felder `similar_level` / `similar_sound_level`, `:147-148` Spec `("choice", LEVELS, None)`.
- `src/transcript/hints.py:103` `Hint.nearest_relevance` (min über `RELEVANCE_TIERS`), `Relevance = pc|session|recent|archive` (`narrata.py:88`).
- Bewertungsdatei: `uncertainty.py:423-447` schreibt `thresholds` als `asdict`. `:476-483` `_thresholds_from` lehnt eine abweichende Feldmenge mit „field 'thresholds' invalid“ ab. `UNCERTAINTY_FORMAT_VERSION = 1` (`:38`).
- Leser: `candidates.py:162` (Abbruch mit „run transcript assess“), `status.py:261` (`DataFileError` → „rating outdated“), `report.py:483`.
- `transcript assess` (`assess_session`, `uncertainty.py:399`) bewertet immer neu und verwendet nichts weiter.
- Entscheidungen zu weggefallenen Kandidaten werden `orphaned` und gemeldet, nie verworfen (`decisions.py:10-11`, `working.py:82`).
- Doku: README `:414` (Regeltabelle) und `:739` (Konfigurationstabelle), `config/example.yaml:113-117`. Tests: `tests/test_uncertainty.py:408-424`, `tests/test_config.py:392-432`.

## Entscheidungen
- **Reihenfolge der Regel:** Klang geht vor Archiv. `method == "sound"` → `similar_sound_level`; sonst `nearest_relevance == "archive"` → `similar_archive_level`; sonst `similar_level`. Klang-Treffer behalten damit ihre bisherige Schwelle. Laut Ticket gilt die neue nur für Schreibtreffer.
- **`ambiguous` und `known_variant` bleiben unverändert.** Das Ticket nennt nur `similar`. Mehrdeutige Hinweise auf Archivbegriffe heben die Passage weiter auf `uncertain`.
- **Mehrere Kandidaten:** Es zählt `nearest_relevance`, wie bisher. Ein Hinweis mit einem `recent`- und einem `archive`-Kandidaten wirkt also mit `similar_level`.
- **Formatversion 1 → 2:** Das neue Feld ändert die Feldmenge von `thresholds`. Alte Dateien würden zwar schon abgelehnt, aber mit der unklaren Meldung „field 'thresholds' invalid“. Mit v2 lautet sie „unsupported format_version; run transcript assess again“, und `status` meldet „rating outdated“.
- **Kein allgemeiner Abgleich geänderter Schwellen in `status`:** Für dieses Ticket reicht der Versionssprung, denn nach dem Update ist jede alte Bewertung ungültig. Einen Abgleich der Schwellen mit der Konfiguration gibt es heute für kein Feld. Siehe Folge-Tickets.

## Daten-Check
- handled — Tests arbeiten nur mit synthetischen Hinweisen aus `tests/test_uncertainty.py`. Neue Fixtures sind nicht nötig.
- handled — Der Neulauf an der Pilotsitzung schreibt nur nach `work/`. In Repo, Plan und Roadmap kommen nur Zahlen (Kandidaten vorher/nachher, Passagen je Stufe), keine Begriffe, Namen oder Textstellen.
- N/A because — Die neuen Fehlermeldungen nennen nur Pfad und Version, keinen Inhalt.

## Contract-Check
- N/A because — Weder der Contract-JSON noch der Endpoint ändern sich. Betroffen ist nur die Zahl der `needs_review`-Passagen und damit `confidence_tier` einzelner Passagen im Export. Das Feld und seine Werte bleiben dieselben, deshalb braucht Narrata keine Änderung.

## Resume-Check
- N/A because — `assess` ist modellfrei, dauert Sekunden und bewertet immer neu (`uncertainty.py:399-420`). Es gibt keinen Zwischenstand zum Wiederaufnehmen. Hinweisdatei und Snapshot bleiben unverändert.

## Dependency-Check
- N/A because — keine neue Abhängigkeit und kein neues Modell.

## Format-Check
- handled — `UNCERTAINTY_FORMAT_VERSION` geht von 1 auf 2. Bestehende `review/uncertainty-*.json` werden abgelehnt: `candidates` und `working` verweisen auf `transcript assess`, `status` meldet „rating outdated“. Ein `transcript assess` schreibt sie neu. Review-Entscheidungen bleiben erhalten. Fällt ihr Kandidat weg, werden sie `orphaned`. `candidates.json` und `decisions.json` speichern keine Schwellen und ändern ihr Format nicht.

## Chunks
### Chunk 1 — Schwelle `similar_archive_level`
- Dateien: `src/transcript/config.py`, `src/transcript/uncertainty.py`, `tests/test_uncertainty.py`, `tests/test_config.py`, `config/example.yaml`, `README.md`
- Änderung: Feld `similar_archive_level: Level = "confident"` mit Kommentar und Spec-Eintrag. In `_hints` die Stufe über eine kleine Hilfsfunktion `_similar_level(hint)` wählen: sound → archive → default. `UNCERTAINTY_FORMAT_VERSION = 2`. README `:414` und `:739` ergänzen, ebenso `example.yaml` (Kommentar: TOOL-60, 2 von 18).
- Tests: Ein Archiv-Schreibtreffer allein ergibt keinen Grund und `confident`, mit `similar_archive_level="needs_review"` wird die Passage angehoben. `pc`/`session`/`recent` bleiben bei `similar_level`. Ein gemischter Hinweis (`recent` + `archive`) nutzt `similar_level`. Ein Klang-Treffer auf `archive` folgt `similar_sound_level`. Die Konfiguration liest das Feld und lehnt einen ungültigen Wert mit `review.uncertainty.similar_archive_level` ab. Eine v1-Datei wird abgelehnt.
- Verify: `scripts/check`
- AC: AK 1, 2 und 4 des Tickets.
- Commit: `feat(review): add a separate similar level for archive terms (TOOL-99)`

### Chunk 2 — Neulauf an der Pilotsitzung
- Dateien: `docs/plans/TOOL-99-archive-similar.md` (Abschnitt „Ergebnis“), `docs/transcript-roadmap.py` und die daraus generierte `.md`
- Änderung: Kandidatenzahl vorher notieren (`candidates.json` bzw. `transcript status`), dann `.venv/bin/transcript assess <pilot>` ausführen. Vorher/nachher eintragen: Kandidaten, Anteil an den Passagen, Passagen je Stufe. Nur Zahlen.
- Verify: `scripts/check`
- AC: AK 3 des Tickets.
- Commit: `docs(review): record the archive threshold on the pilot session (TOOL-99)`

## Ergebnis
Neulauf von `transcript assess` an der Pilotsitzung am 22.11.2026, ohne neue Hinweise und mit den Defaults (`similar_archive_level: confident`):

| | vorher | nachher |
| --- | --- | --- |
| Review-Kandidaten | 1.424 (65,7 % von 2.166 Passagen) | 1.416 (65,4 %) |
| pro Stunde Audio | 262 | 260,4 |
| Passagen je Stufe | — | 750 `confident`, 1.116 `needs_review`, 300 `uncertain` |

8 Passagen werden `confident`, weniger als die rund 15 aus TOOL-83. Die übrigen Passagen mit Archiv-Schreibtreffern haben noch einen anderen Grund. Die Hinweise selbst sind unverändert.

## Folge-Tickets
- [kein Ticket: bisher kein Bedarf] `status` könnte gespeicherte Schwellen mit `review.uncertainty` vergleichen und eine Bewertung mit anderen Schwellen als veraltet melden. Heute merkt das nur, wer `transcript assess` selbst startet. Ein Ticket lohnt erst, wenn Schwellen wieder öfter ohne Formatsprung geändert werden.

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Schwelle, Bewertungsregel, Formatversion, Doku, Tests | no |
| 2 | Neulauf Pilotsitzung, Zahlen in Plan und Roadmap | no |
