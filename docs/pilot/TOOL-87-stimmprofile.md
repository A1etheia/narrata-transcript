# TOOL-87 — Sprecher über Sitzungen wiedererkennen: Stimmprofile mit Einwilligung

Stand 2026-11-22. Die Notiz beantwortet M8 der Roadmap: Lohnt sich die Wiedererkennung der Sprecher, und trägt die Einwilligung pro Spielrunde? Sie enthält nur Kennzahlen aus [TOOL-59](TOOL-59-auswertung.md) und [TOOL-60](TOOL-60-bewertung.md), keine Session-Keys, Gruppen, Namen oder Labels (TOOL-66). Es ist keine juristische Prüfung. Plan: [`docs/plans/TOOL-87-voice-profiles.md`](../plans/TOOL-87-voice-profiles.md).

## Ergebnis in Kürze

- **No-Go.** Die Pipeline bekommt keine Stimmprofile. Die Zuordnung der Labels zu Personen bleibt Handarbeit mit `transcript speakers --assign` (TOOL-86).
- **Grund:** Die Handzuordnung kostet 2–4 min pro Abend. Den einzigen genannten Nutzen, die Gewichtung pro Person, liefert Narrata schon über die bestehende Zuordnung (IOA-1326). Ein Stimmprofil wäre dagegen ein biometrisches Datum mit Opt-in, Contract-Bump, Löschwegen und eigener Kalibrierung.
- **Neu prüfen**, wenn die Zuordnung über mehrere Abende mehr als 10 min pro Abend braucht oder die Pipeline regelmäßig mehrere Runden verarbeitet. Der Einstieg wäre dann der Abgleich innerhalb einer Sitzung (siehe unten), weil er ohne Profil auskommt.

## Entscheidungsgrundlage

| | Wert | Quelle |
| --- | --- | --- |
| Sprecherzuordnung pro Abend | 2–4 min, alle Labels | TOOL-60 |
| Sprecherzuordnung pro Stunde Audio | 0,4–0,7 min | TOOL-59, TOOL-60 |
| Labels im Pilot | 7 für 5:26 h, 2 Aufnahmen | TOOL-59 |
| Hören der markierten Passagen pro Stunde Audio | 47 min | TOOL-60 |

- **Die Zuordnung ist nicht der Engpass.** Sie macht unter 1 % der Handarbeit eines Abends aus, das Review dominiert.
- **Der Nutzen aus TOOL-60 fällt anders an.** TOOL-60 nannte als Hauptnutzen die Gewichtung pro Person ohne Handarbeit. Diese Gewichtung liegt jetzt in Narrata (IOA-1326) und braucht nur die `participant_id` an der Passage. Die liefert die Handzuordnung schon heute.
- **Vorschläge würden die Handarbeit nicht abschaffen.** Bestätigung bliebe Pflicht (siehe unten). Gespart würde nur die Auswahl aus einer Liste von meist vier bis sechs Anwesenden.

## Datenschutzbewertung

So wäre es bei einem Go:

- **Einordnung:** Ein Stimmprofil, das eine Person über Sitzungen hinweg wiedererkennt, verarbeitet biometrische Daten zur eindeutigen Identifizierung (Art. 4 Nr. 14, Art. 9 Abs. 1 DSGVO). Die mündliche Zustimmung pro Sitzung (`docs/datenschutz.md`) deckt die Aufnahme ab, ein dauerhaftes Profil aber nicht.
- **Rechtsgrundlage:** ausdrückliche Einwilligung der betroffenen Person (Art. 9 Abs. 2 lit. a), je Spielrunde, freiwillig und ohne Nachteil bei Ablehnung. Die Zuordnung von Hand bleibt immer möglich. Ob in einer privaten Runde die Haushaltsausnahme (Art. 2 Abs. 2 lit. c) greift, bleibt offen. Das Projekt behandelt die Frage so, als griffe sie nicht.
- **Einwilligungsweg:** Opt-in pro Mitgliedschaft im Narrata-Profil, sichtbar und jederzeit widerrufbar, analog zu `analytics_opt_in_at` (IOA-1216). Die Pipeline erfährt davon nur über den Transkriptionskontext.
- **Speicherort:** Profile nur lokal unter `work/`, nie im Repo und nie in Narrata. Narrata speichert nur die Einwilligung.
- **Löschung:** Fehlt die Einwilligung im Kontext oder fehlt die Person ganz, löscht die Pipeline das Profil dieser Person beim nächsten Abruf vollständig. Ein rückwirkender Widerruf löscht auch alle Beiträge aus früheren Sitzungen, weil sie im Profil selbst liegen. Die Embeddings pro Label in den Diarisierungsrohdateien einer Sitzung gehören zu den Sitzungsdaten. Sie fallen unter die bestehende Widerrufsregel und werden mit dem Rohaudio gelöscht.
- **Doku bei einem Go:** `docs/datenschutz.md` (neuer Eintrag und Tabellenzeile), in Narrata das Verarbeitungsinventar und die Datenschutzerklärung.

## So wäre es gebaut

### Einwilligung (Narrata)

- **Opt-in:** Spalte `voice_profile_opt_in_at` an `user_group`, gesetzt und zurückgesetzt nur von der Person selbst, wie bei `AnalyticsConsent`.
- **Lieferung:** Feld `participants[].voice_profile_consent` (Boolean) im Transkriptionskontext, Minor-Bump von 1.4. Es ist unabhängig von `present`. Kandidaten für einen Vorschlag sind Personen mit Einwilligung, Anwesende zuerst (TOOL-79).
- **Widerruf, Austritt, Purge:** Narrata kann der Pipeline nichts schicken, die Pipeline schreibt nie in die Datenbank. Sie erfährt es deshalb beim nächsten `transcript context`. Dort steht das Feld auf `false`, `is_former` steht auf `true` oder die Person fehlt nach einem Purge ganz. Damit kein veralteter Kontext Profile weiterleben lässt, nutzt die Pipeline Profile nur in einem Lauf, dessen Kontext sie in diesem Lauf abgerufen hat, nicht über `--from-file`.
- **Offen:** Ob Ehemalige (`is_former`) ihr Profil behalten dürfen, solange die Einwilligung steht. Vorschlag: nein, Austritt löscht.

### Profile (Pipeline)

- **Ablage:** eine Datei pro Person unter `work/<gruppe>/voice-profiles/<user_id>.json`, Schlüssel Gruppe und `user_id`, eigenes `format_version`. Dazu kommt die Modellkennung, denn Embeddings eines anderen Modells sind nicht vergleichbar. Ein Modellwechsel entwertet alle Profile.
- **Aufbau:** nur aus bestätigten Einträgen (`assigned: person`), nie aus Vorschlägen, `unknown` oder `multiple`. Ein Label, das einen Vorschlag ungeprüft übernähme, gibt es nicht.
- **Mehrere Zentroide statt Mittelwert:** Jede Sitzung, Aufnahme und jedes Label einer Person ergibt einen Eintrag. Der Vergleich nimmt die höchste Ähnlichkeit über alle Einträge. Grund: Die Spielleitung spricht mit NSC-Stimmen, und Mikrofon oder Platz wechseln. Ein Mittelwert verwischt genau das.
- **Nachvollziehbarkeit:** Jeder Eintrag trägt Session-Key, Segment, Label und `labels_version`. Damit ist sichtbar, welche Sitzungen eingeflossen sind, und ein Eintrag lässt sich gezielt entfernen.
- **Löschen:** siehe Datenschutzbewertung. Ohne Einwilligung entsteht gar kein Profil.

### Vorschläge

- **Embeddings:** Die pyannote-Ausgabe liefert schon ein Zentroid pro Label (`DiarizeOutput.speaker_embeddings`). Heute übernimmt `PyannoteDiarizer.diarize` nur die Turns (`src/transcript/diarization/pyannote.py`). Die Embeddings kämen in die Diarisierungsrohdatei pro Segment. Sie hängen dann wie die Turns an Modell, Einstellungen und Audio-Hash und werden mit ihnen wiederverwendet. Ändert sich `labels_version`, ändern sich auch die Embeddings. Bestehende Sitzungen müssten einmal neu diarisiert werden, rund 4,5 min pro Abend (TOOL-59). Ein eigenes Embedding-Modell wäre nicht nötig.
- **Ähnlichkeit und Zuordnung:** Kosinus-Ähnlichkeit, pro Segment als Zuordnungsproblem: höchstens ein Label pro Person, höchstens eine Person pro Label, Anwesende zuerst. Bei vier bis acht Labels reicht eine vollständige Suche, eine neue Bibliothek braucht es nicht. Unter der Schwelle gibt es keinen Vorschlag.
- **Darstellung:** `assignment.json` bekäme `format_version` 2 und pro Eintrag `suggestion: {user_id, score}`. `assigned` bleibt `open`, bis jemand bestätigt. `--assign` zeigt den Vorschlag mit Wert als vorausgewählte Person, die Bestätigung bleibt ein Tastendruck. Kein Schritt setzt `person` automatisch.
- **Personen ohne Einwilligung:** kein Profil, kein Vorschlag. Ihr Label wird **nicht** als „keine bekannte Person“ markiert, weil schon der Vergleich ihrer Stimme mit den Profilen der anderen eine Erkennung wäre. Es bleibt einfach ohne Vorschlag.
- **Kalibrierung:** Kreuzprobe an den Handzuordnungen der zwei Pilotsitzungen. Profile entstehen aus der einen Sitzung, Vorschläge für die andere, und umgekehrt. Gemessen werden der Anteil richtiger Vorschläge, falsche Vorschläge über der Schwelle und Labels ohne Vorschlag. Die Basis ist mit zwei Sitzungen und rund 14 Labels sehr schmal, belastbar wäre die Schwelle erst nach mehreren Abenden.

## Abgleich innerhalb einer Sitzung

Pro Aufnahme diarisiert pyannote getrennt, dieselbe Person hat deshalb in jeder Aufnahme ein eigenes Label. TOOL-69 macht die Labels nur per Präfix sessionweit (`s01-…`, `s02-…`), einen Abgleich gibt es nicht. Mit denselben Embeddings ließen sich die Labels der zweiten Aufnahme denen der ersten vorschlagen.

- **Datenschutz:** Die Embeddings verlassen die Sitzung nicht, es entsteht kein dauerhaftes Profil. Sie sind Sitzungsdaten wie die Turns und werden mit ihnen gelöscht. Eine eigene Einwilligung braucht es nach dieser Bewertung nicht.
- **Nutzen:** gering. Im Pilot ist die zweite Aufnahme 26 min lang. Ihre Labels zuzuordnen kostet Sekunden, und die Anwesenden sind dieselben.
- **Ergebnis:** kein Ticket. Bei einer Neuprüfung ist das der erste Schritt, weil er die Embeddings, die Kalibrierung und die Vorschlagsdarstellung ohne Art.-9-Fragen erprobt.

## Wann neu prüfen

**Kriterium:** Die Zuordnung braucht über mehrere Abende mehr als 10 min pro Abend (`speakers.effort_minutes` in `report.json`), oder die Pipeline verarbeitet regelmäßig mehrere Runden. Das hat TOOL-85 heute ausgeschlossen.

Ein Go bräuchte diese Tickets, mit den Abhängigkeiten in dieser Reihenfolge:

1. TOOL: Embeddings pro Label in der Diarisierungsrohdatei speichern. [kein Ticket: No-Go]
2. TOOL: Labels zwischen den Aufnahmen einer Sitzung vorschlagen, `assignment.json` 2, Anzeige in `--assign`, braucht 1. [kein Ticket: No-Go]
3. IOA unter IOA-1213: Opt-in `voice_profile_opt_in_at`, Feld im Transkriptionskontext, Inventar und Datenschutzerklärung. [kein Ticket: No-Go]
4. TOOL: lokale Profile mit Löschung beim Kontextabruf und Vorschläge über Sitzungen, braucht 2 und 3, Kalibrierung an den Handzuordnungen. [kein Ticket: No-Go]
