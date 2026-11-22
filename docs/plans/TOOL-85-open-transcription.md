# TOOL-85 — Entscheidung: Transkription für andere Narrata-Nutzer öffnen?

## Ziel
Danach ist M7 beantwortet und im Repo begründet: Die Pipeline bleibt das Werkzeug der eigenen Gruppe. Dazu steht fest, wann die Frage neu gestellt wird. Heute steht die Frage nur als offenes Ticket in der Roadmap (`docs/transcript-roadmap.md:48`, `:181`).

## Ist-Stand
- Grenzen: V0.1 läuft vollständig lokal, Rohaudio verlässt den Rechner nie (`CLAUDE.md`, `docs/datenschutz.md:25-26`, `:43-44`). Die Einwilligung wird mündlich pro Sitzung eingeholt und im Manifest vermerkt (`docs/datenschutz.md:19`).
- Laufzeit (TOOL-59, `docs/pilot/TOOL-59-auswertung.md:7-8`, `:69-72`): 12 min für 5:26 h Audio auf einer GPU mit 12 GiB, Spitzenwert 13,9 GiB RAM. Der Prod-VPS (rund 3,8 GB RAM, keine GPU) könnte das nicht tragen. Der Engpass ist das Review, nicht die Rechenzeit.
- Pilot-Review (TOOL-60, `docs/pilot/TOOL-60-bewertung.md:158`, `:180`): Die Modellwahl gehört zur lokalen Konfiguration (`asr.model`) und ist nur bei einer Öffnung neu zu prüfen. Das Review wandert nach Narrata (IOA-1326).
- Narrata deckt andere Gruppen schon ab: Transkripte aus Zoom, Teams, Meet und Otter (WebVTT, SRT, Text) werden in Contract 1.3 mit `source.kind = upload` umgewandelt (IOA-1304, IOA-1306; `ios-archiv/docs/transcript-upload-formats.md:1-8`).
- Der Pipeline-Token gilt pro Gruppe und wird von der aktiven Spielleitung im Profil erzeugt (TOOL-84; `ios-archiv/docs/data-processing-inventory.md`, K2). Eine fremde Spielleitung könnte die Pipeline also schon heute lokal betreiben. Es fehlen nur Paketierung und Anleitung.

## Entscheidungen
Getroffen mit der Projektverantwortlichen am 2026-11-22:
- **Weg 4: nichts tun.** Die Pipeline bleibt das Werkzeug der eigenen Gruppe. Grund: Es gibt keine Nachfrage, das Projekt ist ein Solo-Projekt für eine private Gruppe, und andere Gruppen haben mit dem Fremdformat-Upload schon einen Weg nach Narrata.
- **Weg 1 (Nutzer rechnen lokal)** bleibt die erste Wahl, falls sich das ändert. Kriterium für eine Neuprüfung: eine konkrete Anfrage einer Spielleitung, deren Gruppe der Fremdformat-Upload nicht reicht. Dann sind zu klären: Installer und Anleitung, Hardware-Untergrenze (nach TOOL-59 GPU oder lange CPU-Laufzeit), Einwilligungshinweis für fremde Runden und eine Modellwahl ohne YAML (Hinweis aus TOOL-60).
- **Weg 2 (eigener Worker) und Weg 3 (externer ASR-Dienst): nein.** Beide brächten Rohaudio auf fremde oder neue Server und damit Audio-Upload, Queue, Kontingente, Missbrauchsschutz, Löschfristen und bei Weg 3 einen Verarbeitungsvertrag. Das passt nicht zum Umfang. Der Prod-VPS scheidet nach TOOL-59 ohnehin aus. TOOL-60 hat das Remote-Backend TOOL-14 aus demselben Grund verworfen.

## Daten-Check
- TOOL-66: N/A, weil die Notiz nur Kennzahlen aus TOOL-59 und TOOL-60 übernimmt und keine Sitzungsdaten, Namen oder Session-Keys enthält.
- Logs, Fehlermeldungen, Fixtures: N/A, weil kein Code geändert wird.
- Mitspielende: handled. Die Entscheidung erweitert nichts. Einwilligung und Löschung bleiben wie in `docs/datenschutz.md`. Bei einer Neuprüfung nennt die Notiz die Einwilligung für fremde Runden als offenen Punkt.

## Contract-Check
- IOA-1214: N/A, weil der Contract unverändert bleibt (1.3). Uploads aus Fremdformaten laufen schon über Contract 1.3 (IOA-1304).
- Narrata: N/A, weil keine Änderung nötig ist und kein IOA-Ticket entsteht.

## Resume-Check
- N/A, weil kein lang laufender oder modellgestützter Schritt dazukommt.

## Dependency-Check
- N/A, weil keine neue Abhängigkeit und kein neues Modell dazukommt.

## Format-Check
- N/A, weil kein internes Format geändert wird.

## Chunks
### Chunk 1 — Entscheidungsnotiz
- Dateien: `docs/pilot/TOOL-85-oeffnung.md` (neu, liegt neben den Reflexionsberichten zu TOOL-59 und TOOL-60)
- Änderung: Abschnitte „Ergebnis in Kürze“ (Weg 4 in drei Sätzen), „Abgewogene Wege“ (je Weg ein Absatz mit Grund), „Wann neu prüfen“ (Kriterium und offene Punkte für Weg 1, darunter die Modellwahl aus TOOL-60). Kurz halten, eine Seite. Dazu ein Jira-Kommentar an TOOL-85 mit der Entscheidung und einem Link auf die Notiz.
- Verify: `scripts/check`; `grep -n -i` auf Gruppen- und Klarnamen in der Notiz liefert nichts.
- AC: Die Ergebnisse des Tickets sind belegt, also Entscheidung, Begründung, Datenschutz, Betrieb und Erkenntnisse aus TOOL-59/60. Jeder Folgepunkt trägt `[kein Ticket: …]`.

## Folge-Tickets
- Weg 1 (Paketierung, Anleitung, Einwilligungshinweis): [kein Ticket: keine Nachfrage, Neuprüfung erst bei einer konkreten Anfrage]
- Modellwahl auf Gruppenebene in Narrata (Übergabe aus TOOL-60): [kein Ticket: entfällt, solange die Transkription nicht geöffnet wird]
- Eigener Worker / externer ASR-Dienst: [kein Ticket: verworfen]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Entscheidungsnotiz `docs/pilot/TOOL-85-oeffnung.md`, Jira-Kommentar | no |
