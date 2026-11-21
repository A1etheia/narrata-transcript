# TOOL-60 — V0.1-Ergebnisse bewerten und V0.2-Backlog ableiten

## Ziel
Danach liegt mit `docs/pilot/TOOL-60-bewertung.md` eine Bewertung jedes V0.1-Bereichs vor, mit allen Entscheidungen aus dem Ticket, den bekannten Grenzen von V0.1 und einem V0.2-Backlog, der beobachtete Fehler von Ideen trennt. Heute sind die Befunde über die Berichte zu TOOL-35, 58, 59, 92, 93 und 96 verteilt. Die Zahlen zur Review-Auswahl stammen vom ungeteilten Stand vor TOOL-96, und es gibt keine Messung außerhalb der Pilotsitzung.

## Ist-Stand
- Pilotbericht `docs/pilot/TOOL-58-erste-session.md:5-11`: Pipeline trägt durchgängig, WER 24–33 %, 87 % Kandidaten, vollständiges Review rund 25 h; Bewertung ohne Fehlalarm, 4 übersehene Auslassungen (`:85-102`); Narrata-Import ohne Korrektur (`:104-117`); Workarounds (`:125-131`, inzwischen durch TOOL-94/95 behoben).
- Laufzeit `docs/pilot/TOOL-59-auswertung.md:5-11`: 12 min für 5:26 h, 13,9 GiB RAM, 2,5 GiB VRAM; der Mensch ist der Engpass.
- Erkennung `docs/spikes/TOOL-93-erkennungsqualitaet.md:318-326`: No-Go, `base` bleibt; Mikrofon-Empfehlung `:328-344`; Fenster für Referenz C an einer zweiten Sitzung `:282-296` (empfohlen 1:15:00–1:18:00, Segment 1).
- Sprecher `docs/spikes/TOOL-96-sprecherwechsel.md:5-11`, `:86-147`: Sprecherfehler 6,2 % / 3,6 %, kein Diarisierungs-Ticket; 2.166 Passagen, Kandidaten 65,7 %, markierte Zeit 79,0 %; 9 veraltete Review-Entscheidungen (`:119-130`); Befund zum Guard IOA-1280 (`:147`); Parser-Korrektur und Neuwertung von TOOL-93: `base` A 21,3 %, B 29,8 % (25,6–35,4) (`:158-174`).
- Bewertung `docs/spikes/TOOL-35-kalibrierung.md:5-12`, `:132-143`: Eingrenzung am Clip auf rund die Hälfte; `similar` über den Klang meist Fehlalarm; Archiv-Schreibung mit nur einem beurteilten Hinweis; offen ist die Nachmessung am vollen Lauf (`:163-169`).
- Werkzeuge: `transcript calibrate` mit `--reference/--start/--end`, `--similar-sheet`, `--similar-judged` (`src/transcript/__main__.py:221-226`, `:877`; README „Kalibrierung“ `README.md:421-442`). Der Bogen landet fest unter `review/calibration/similar-sheet.csv` (`__main__.py:877`).
- Echte Daten liegen im Hauptcheckout `/home/sabine/dev/workspace/narrata-transcript/work/`, nicht in diesem Worktree (`paths.root: .`).

## Entscheidungen
Getroffen mit der Projektverantwortlichen am 2026-11-21:
- **Messungen: Referenz C und neuer Bogen.** Die Projektverantwortliche tippt Referenz C an der zweiten Sitzung ab (Fenster aus TOOL-93, Stufe 4) und beurteilt einen neuen `similar`-Bogen am geteilten Pilotstand. Dazu misst `calibrate` A und B am Stand nach TOOL-96 neu. So stammen die Zahlen zur Review-Auswahl vom heutigen Stand, und die Übertragbarkeit auf eine zweite Sitzung ist geprüft.
- **Review-Kanal: Narrata-UI** (IOA-1326). Das Review mit Anhören wandert nach Narrata. Das CSV-Review der Pipeline wird eingefroren: Es bleibt lauffähig, bekommt aber keine Erweiterung mehr, also weder Hörblöcke noch einen Terminal-Dialog. Rohaudio verlässt den Rechner weiterhin nicht; IOA-1326 verlangt lokales Abspielen im Browser ohne Upload.
- **IT/OT: Go.** IOA-1302 wird wieder aufgenommen. Der Wortlaut ist lokal ausgereizt (TOOL-93), der Sprecherfehler liegt unter der Grenze (TOOL-96). Der Bericht nennt das Kriterium, ab dem die Diarisierung wieder aufgegriffen wird (TOOL-96, `:154`).
- **Aufnahme am Tisch: nur dokumentieren.** Die Empfehlung aus TOOL-93 steht im Bericht. Es gibt kein Ticket und keine Mehrspur-Aufnahme.
- **Diarisierung:** Schon in TOOL-96 entschieden, der Bericht übernimmt nur die Begründung.

Im Bericht entschieden, hier vorgeschlagen:
- **Guard IOA-1280: IOA-Ticket** (IOA-1327). Narrata warnt vor dem Aktualisieren, wenn an einer Passage mit geändertem Text Links oder Archiv-Provenienz hängen. Mit dem Go für IT/OT und dem Review in Narrata entstehen solche Bezüge bald wirklich.
- **Remote-Backend TOOL-14: nein, schließen.** Plaud als Cloud-Dienst ist bei den Wörtern nicht besser (TOOL-93, `:312`), und das Problem liegt in der Aufnahme. Es gibt also kein Qualitätsproblem, das nur remote lösbar wäre.
- **Alt-Transkripte:** Der Pilot zeigt keinen beobachteten Bedarf, sie bleiben verworfen.
- **Gewichtung pro Person (TOOL-68/TOOL-36) und Parakeet-Zweitlauf TOOL-82:** Die Entscheidung fällt nach den Messungen in Chunk 1, anhand der Fehler je Sprecher und der übersehenen Auslassungen an A, B und C.

## Daten-Check
- TOOL-66: handled. Referenz C, der neue Bogen und die `calibrate`-Ausgaben enthalten echte Namen und bleiben unter `work/` im Hauptcheckout. Der Bericht übernimmt nur Kennzahlen, wie die Berichte zu TOOL-58, 59 und 96.
- Repo: handled. Session-Key, Gruppe, Namen, Labels und Transkripttext stehen nicht im Bericht. Vor jedem Commit prüft `grep -n` den Bericht auf Session-Key und Gruppennamen.
- Logs/Fehlermeldungen: N/A, weil kein Code geändert wird. `calibrate` gibt laut README nur Zahlen aus.
- Fixtures: N/A, es gibt keine neuen.
- Agent und Handreferenz: handled. Wie in TOOL-35 liest der Agent weder Referenz noch Bogen inhaltlich, er übernimmt nur die Zählwerte aus der `calibrate`-Ausgabe.

## Contract-Check
- IOA-1214: N/A für die Pipeline. Der Export bleibt Contract 1.3, es wird nichts neu exportiert.
- Narrata: handled. Das Review in der Narrata-UI trägt IOA-1326, die Prüfung abhängiger Links IOA-1327. Ob das Review in Narrata die Felder `review_status` im Contract ablöst oder ergänzt, klärt IOA-1326. Die Pipeline ändert in TOOL-60 nichts am Contract.

## Resume-Check
- `calibrate`: handled. Der Schritt ist deterministisch, speichert nichts und braucht kein Modell. Nach einem Abbruch wird er einfach neu aufgerufen.
- Zweite Sitzung: handled. Zuerst zeigt `transcript status`, ob sie im echten `work/` bis `transcribe` durchgelaufen ist; der TOOL-93-Lauf lag in einer Spike-Wurzel. Fehlt der Lauf, rechnet `transcript process` ihn mit `base` und dem gespeicherten Snapshot (rund 12 min) und hält an den manuellen Schritten an. Nach einem Abbruch werden fertige Schritte wiederverwendet (TOOL-57).
- `--similar-sheet`: handled. Der Befehl überschreibt `review/calibration/similar-sheet.csv`, deshalb wird der beurteilte TOOL-83-Bogen vorher unter neuem Namen gesichert.

## Dependency-Check
- N/A, weil keine neue Abhängigkeit und kein neues Modell hinzukommt. Es werden nur vorhandene CLI-Befehle genutzt.

## Format-Check
- N/A, weil kein internes Format geändert wird.

## Chunks
### Chunk 1 — Nachmessung am Stand nach TOOL-96
- Dateien: `docs/pilot/TOOL-60-bewertung.md` (Abschnitt „Messungen“)
- Handarbeit der Projektverantwortlichen, vom Agenten angesagt:
  1. Referenz C abtippen: zweite Sitzung, Segment 1, 1:15:00–1:18:00. Die Datei kommt nach `work/<zweite Sitzung>/review/calibration/reference-c.txt`.
  2. Den neuen Bogen am Pilotstand beurteilen und die Spalte `correct` mit `ja` oder `nein` füllen.
- Änderung:
  - Den alten Bogen sichern und `calibrate --similar-sheet` erzeugen.
  - `calibrate` an A, B (Pilot, geteilter Stand) und C laufen lassen, dazu `--similar-judged`.
  - Im Bericht stehen: WER mit Spanne laut TOOL-93/96, Fehler je Sprecher, Anteil markierter Passagen und markierter Zeit, Fehler in markierten Passagen, übersehene Fehler (davon Auslassungen), Fehlalarme, AUC und die Präzision von `similar` je Methode und Stufe, jeweils im Vergleich zu TOOL-35 und TOOL-58.
  - Die Aufrufe laufen über `.venv/bin/transcript` im Hauptcheckout, ohne `cd` und mit absoluten Pfaden.
- Verify: `scripts/check`; `grep -n` auf Session-Key und Gruppennamen beider Sitzungen im Bericht liefert nichts.
- AC: Am heutigen Stand ist an zwei Sitzungen nachvollziehbar, wie viele relevante Fehler die Review-Auswahl gefunden und wie viele sie übersehen hat. Die Archiv-Schreibtreffer sind nachgemessen.

### Chunk 2 — Bewertung, Entscheidungen, V0.2-Backlog
- Dateien: `docs/pilot/TOOL-60-bewertung.md`; `README.md` (kurzer Hinweis im Abschnitt „Review-CSV“: eingefroren, das Review wandert nach Narrata, IOA-1326)
- Änderung, Abschnitte des Berichts:
  - „Ergebnis in Kürze“: die Kernhypothese, an Daten bewertet.
  - Je Bereich aus dem Ticket eine kurze Bewertung: Referenztranskription mit Plaud-Vergleich, Konfidenzsignale, Sprechertrennung und Zuordnung, Segmentüberlappung (N/A ohne Segmentierung), Review-Kandidaten pro Stunde mit Fehlalarmen und Übersehenen, Domänenwissen mit Relevanzregel, CSV-Review, Contract-Tauglichkeit, TXT/DOCX, Resume und Fehlerverhalten, Laufzeit und Ressourcen, manuelle Zeit pro Stunde Audio.
  - „Bekannte Grenzen von V0.1“.
  - „Entscheidungen“: jede Entscheidung aus dem Ticket mit Begründung, dazu die Liste dessen, was bewusst nicht weiterverfolgt wird.
  - „V0.2-Backlog“: eine Tabelle mit den Spalten *beobachtet / Idee*, Ticket-Key und Code-Ort (TOOL oder IOA).
  - Die Tickets, die sich aus den Messungen ergeben, werden angelegt. Dazu kommen Kommentare an IOA-1302 (Go) und TOOL-14 (Schließgrund).
- Verify: `scripts/check`; `grep -n` wie in Chunk 1.
- AC: Alle Akzeptanzkriterien des Tickets sind im Bericht belegt. Jeder Backlog-Punkt trägt einen Key oder `[kein Ticket: …]`.

## Folge-Tickets
- Review in der Narrata-UI mit lokalem Abspielen ohne Audio-Upload; ersetzt das CSV-Review: IOA-1326
- Warnung beim Re-Import, wenn an einer geänderten Passage Links oder Provenienz hängen (Befund TOOL-96, Guard IOA-1280): IOA-1327
- IT/OT-Spike wieder aufnehmen: IOA-1302 (besteht; Kommentar mit dem Go in Chunk 2)
- Remote-Backend: TOOL-14 (wird in `/close-ticket` mit Begründung geschlossen)
- Mikrofon-Empfehlung umsetzen: [kein Ticket: Entscheidung „nur dokumentieren“]
- Hörblöcke und Review-Dialog in der Pipeline: [kein Ticket: das Review wandert nach Narrata, die CSV ist eingefroren]
- Mehrspur-Aufnahme: [kein Ticket: erst sinnvoll, wenn die Gruppe ein Mehrspur-Setup ausprobieren will (TOOL-93)]
- Die 9 veralteten Review-Entscheidungen: [kein Ticket: werden im Review in Narrata neu entschieden (IOA-1326)]
- Weitere Punkte aus den Messungen (Gewichtung pro Person, TOOL-82, Archiv-Regel): [kein Ticket: entstehen erst aus den Messungen in Chunk 2, dort jeweils mit Key oder Grund]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Nachmessung A/B/C und `similar`-Bogen, Abschnitt „Messungen“ | no |
| 2 | Bewertung, Entscheidungen, Grenzen, V0.2-Backlog, Folge-Tickets | no |
