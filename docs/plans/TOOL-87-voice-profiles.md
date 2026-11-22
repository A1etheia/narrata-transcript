# TOOL-87 — Konzept: Sprecher über Sessions hinweg wiedererkennen (Stimmprofile mit Einwilligung)

## Ziel
Danach ist M8 beantwortet und im Repo begründet. Stimmprofile bekommen ein No-Go, und es steht fest, wann die Frage neu gestellt wird. Die Fragen des Tickets sind so weit beantwortet, dass ein späteres Go nicht bei null anfängt. Heute steht die Frage nur als offenes Ticket in der Roadmap (`docs/transcript-roadmap.md:49`, `:189`).

## Ist-Stand
- **Aufwand der Handzuordnung:** 4 min für 7 Labels im Pilot, das sind 0,7 min pro Audiostunde (`docs/pilot/TOOL-59-auswertung.md:62`). Nach TOOL-86 sind es 2–4 min pro Abend, 0,4–0,7 min pro Audiostunde, und die Zuordnung trifft alle Labels (`docs/pilot/TOOL-60-bewertung.md:116`, `:125`). Zum Vergleich: 47 min Hören pro Audiostunde allein für die markierten Passagen.
- **Erwarteter Nutzen laut TOOL-60:** die Gewichtung pro Person ohne Handarbeit (`docs/pilot/TOOL-60-bewertung.md:179`). Diese Gewichtung ist seit TOOL-60 in Narrata entschieden (IOA-1326), weil Narrata die Person hinter dem Label kennt (`:150`). Sie braucht also nur die bestehende Zuordnung, keine Wiedererkennung.
- **Embeddings:** Die pyannote-Ausgabe hat `speaker_embeddings` mit einem Zentroid pro Label (`.venv/…/pyannote/audio/pipelines/speaker_diarization.py:75`, `:751`). `PyannoteDiarizer.diarize` übernimmt nur die Turns und verwirft die Embeddings (`src/transcript/diarization/pyannote.py:113-121`). Ein Speichern hieße: Diarisierungsrohdatei erweitern und neu rechnen, rund 4,5 min pro Abend (`docs/pilot/TOOL-59-auswertung.md:41`).
- **Zuordnung:** `assignment.json` hat `format_version` 1, `assigned` ∈ `open|person|unknown|multiple` und `effort_minutes` (`src/transcript/speakers.py:39-47`, `:63`, `:81`). Ein Feld für einen Vorschlag gibt es nicht. `--assign` ordnet Anwesende zuerst (`docs/plans/TOOL-86-speakers-assign.md:22`, TOOL-79).
- **Labels pro Segment:** Eine Aufnahme ist ein Segment, im Pilot zwei pro Abend (`docs/pilot/TOOL-59-auswertung.md:17-18`). Der Export macht Labels nur per Präfix sessionweit (`s01-SPEAKER_00`, `docs/plans/TOOL-69-json-export.md:23`). Dieselbe Person hat also pro Aufnahme ein eigenes Label.
- **Einwilligung heute:** mündlich pro Sitzung, vermerkt im Manifest. Der Widerruf löscht lokal (`docs/datenschutz.md:19-23`). Ein Opt-in für Auswertungen pro Person gibt es in Narrata als `analytics_opt_in_at` an `user_group` (IOA-1216; `ios-archiv-backend/app/Support/Groups/AnalyticsConsent.php`).
- **Kontext:** Contract 1.4 liefert `participants[]` mit `user_id`, `role`, `is_former` und `present` (`ios-archiv/docs/transcripts.md:387-412`). Ein Einwilligungsfeld fehlt.

## Entscheidungen
Getroffen mit der Projektverantwortlichen am 2026-11-22:
- **No-Go für Stimmprofile.** Die Handzuordnung kostet 2–4 min pro Abend. Der genannte Nutzen, die Gewichtung pro Person, kommt in Narrata über die bestehende Zuordnung. Dem stünden gegenüber: ein biometrisches Datum nach Art. 9 DSGVO, ein Opt-in pro Mitgliedschaft in Narrata, ein Contract-Bump, Löschwege bei Widerruf, Austritt und Purge, ein neues lokales Format und eine Kalibrierung.
- **Kriterium für eine Neuprüfung:** Die Zuordnung liegt über mehrere Abende bei mehr als 10 min pro Abend, oder die Pipeline verarbeitet regelmäßig mehrere Runden (bei TOOL-85 ausgeschlossen). Bei einer Neuprüfung beginnt man mit dem Abgleich innerhalb einer Session, weil er ohne Profil auskommt.
- **Abgleich zwischen den Segmenten einer Session:** Er wird im Konzept bewertet, bekommt aber kein Ticket. Er braucht kein dauerhaftes Profil, die Embeddings leben nur innerhalb einer Session, deshalb gibt es keinen Art.-9-Bezug über die Aufnahme hinaus. Die Zuordnung der zweiten Aufnahme kostet aber nur Sekunden. TOOL-69 hat das Thema nur per Präfix gelöst, das hält die Notiz fest.
- **Form:** eine Konzeptnotiz `docs/pilot/TOOL-87-stimmprofile.md` neben TOOL-59, TOOL-60 und TOOL-85, kurz gehalten. Sie beantwortet jede Frage des Tickets in ein bis drei Sätzen als „so wäre es“ und benennt offene Punkte bewusst. Grund: Das Projekt ist eine private Gruppe, die Doku soll verhältnismäßig bleiben. Eine spätere Neuprüfung soll trotzdem nicht neu recherchieren müssen.
- **Akzeptanzkriterium „IOA- und TOOL-Tickets angelegt“:** entfällt mit dem No-Go. Die Roadmap sieht Tickets nur bei „ja“ vor (`docs/transcript-roadmap.md:49`). Die Notiz nennt die Tickets, die ein Go bräuchte, als Liste mit `[kein Ticket: No-Go]`.

## Daten-Check
- TOOL-66: *handled — die Notiz übernimmt nur Kennzahlen aus TOOL-59 und TOOL-60 (Minuten, Labelzahlen), keine Session-Keys, Gruppen, Namen, Labels oder Texte.*
- Echte Daten oder Embeddings im Repo: *N/A because kein Code und keine Datei unter `work/` werden angefasst; es wird nichts gemessen oder extrahiert.*
- Logs, Fehlermeldungen, Fixtures: *N/A because kein Code wird geändert.*
- Datenschutzbewertung (AK): *handled — die Notiz hält Rechtsgrundlage (ausdrückliche Einwilligung, Art. 9 Abs. 2 lit. a), Einwilligungsweg (Opt-in pro Mitgliedschaft in Narrata, über den Kontext geliefert), Löschung (Profil fällt weg, sobald die Einwilligung im Kontext fehlt; Abgleich bei jedem `transcript context`) und Speicherort (nur `work/`, nie Repo, nie Narrata) als Bewertung für ein späteres Go fest. `docs/datenschutz.md` bleibt unverändert, weil nichts davon umgesetzt wird.*

## Contract-Check
- IOA-1214: *N/A because der Contract bleibt bei 1.4. Die Notiz beschreibt nur, welches Feld ein Go bräuchte (`participants[].voice_profile_consent`, Minor-Bump).*
- Narrata: *N/A because keine Änderung nötig ist und kein IOA-Ticket entsteht.*

## Resume-Check
- N/A, weil kein lang laufender oder modellgestützter Schritt dazukommt. Die Notiz hält fest, dass gespeicherte Embeddings an Modell und Audio-Hash der Diarisierungsrohdatei hängen müssten und ein Modellwechsel die Profile entwertet.

## Dependency-Check
- N/A, weil keine neue Abhängigkeit und kein neues Modell dazukommt. Ein Go käme mit den Embeddings aus der vorhandenen pyannote-Ausgabe aus.

## Format-Check
- N/A, weil kein internes Format geändert wird. Die Notiz nennt die Formate, die ein Go berühren würde: Diarisierungsrohdatei (Embeddings), `assignment.json` (Vorschlag, `format_version` 2) und eine neue Profildatei.

## Chunks
### Chunk 1 — Konzeptnotiz
- Dateien: `docs/pilot/TOOL-87-stimmprofile.md` (neu)
- Änderung: Abschnitte
  - „Ergebnis in Kürze“: No-Go mit Grund in drei Sätzen.
  - „Entscheidungsgrundlage“: Aufwand aus TOOL-59/60, Nutzen nach IOA-1326.
  - „Datenschutzbewertung“: Rechtsgrundlage, Einwilligungsweg, Löschung, Speicherort.
  - „So wäre es gebaut“: Einwilligung, Profile, Vorschläge, je Frage des Tickets kurz.
  - „Abgleich innerhalb einer Session“.
  - „Wann neu prüfen“: Kriterium, Einstieg und die Ticketliste für ein Go.

  Eine bis zwei Seiten. Dazu ein Jira-Kommentar an TOOL-87 mit der Entscheidung und einem Link auf die Notiz.
- Verify: `scripts/check`; `grep -n -i` auf Gruppen- und Klarnamen sowie Session-Keys in der Notiz liefert nichts.
- AC: Jede Frage des Tickets ist beantwortet oder bewusst offen. Die Datenschutzbewertung steht. Das No-Go ist mit Pilotdaten belegt. Jeder Folgepunkt trägt `[kein Ticket: …]`.

## Folge-Tickets
- Opt-in pro Mitgliedschaft für Stimmprofile in Narrata, Feld im Transkriptionskontext, Widerruf und Purge (IOA): [kein Ticket: No-Go, Neuprüfung erst beim Kriterium aus der Notiz]
- Embeddings speichern, lokale Profile, Vorschläge in `--assign` (TOOL): [kein Ticket: No-Go, Neuprüfung erst beim Kriterium aus der Notiz]
- Labels zwischen den Segmenten einer Session abgleichen: [kein Ticket: die Zuordnung der zweiten Aufnahme kostet Sekunden; Einstieg bei einer Neuprüfung]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Konzeptnotiz `docs/pilot/TOOL-87-stimmprofile.md`, Jira-Kommentar | no |
