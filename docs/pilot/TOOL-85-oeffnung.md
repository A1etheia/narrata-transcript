# TOOL-85 — Transkription für andere Narrata-Nutzer öffnen?

Entschieden mit der Projektverantwortlichen am 2026-11-22. Beantwortet Meilenstein M7.

## Ergebnis in Kürze

- **Nein, vorerst nicht (Weg 4).** Die Pipeline bleibt das Werkzeug der eigenen Gruppe.
- **Keine Nachfrage.** Aus anderen Gruppen hat bisher niemand gefragt. Ein offenes Angebot passt nicht zu einem Solo-Projekt für eine private Gruppe.
- **Andere Gruppen haben schon einen Weg.** Narrata wandelt Transkripte aus Zoom, Teams, Meet und Otter (WebVTT, SRT, Text) in Contract 1.3 um (IOA-1304, IOA-1306; `ios-archiv/docs/transcript-upload-formats.md`).

## Abgewogene Wege

**1. Nutzer rechnen lokal.** Technisch ist das schon heute möglich: Der Pipeline-Token gilt pro Gruppe und wird von der Spielleitung im Profil erzeugt (TOOL-84). Rohaudio bliebe beim jeweiligen Rechner, hochgeladen würde nur das JSON. Es fehlen Paketierung, Anleitung und eine Hardware-Untergrenze. TOOL-59 hat mit einer GPU mit 12 GiB gemessen: 12 min für 5:26 h Audio, Spitzenwert 13,9 GiB RAM. Ohne GPU wäre die Laufzeit erst zu messen. Weil niemand fragt, lohnt der Aufwand heute nicht. Falls sich das ändert, ist dies der erste Weg.

**2. Eigener Transkriptions-Worker.** Der Prod-VPS (rund 3,8 GB RAM, keine GPU) scheidet nach den Zahlen aus TOOL-59 aus. Ein eigener Server brächte Audio-Upload, Warteschlange, Kontingente, Missbrauchsschutz, Löschfristen und laufende Kosten. Außerdem läge Rohaudio fremder Runden erstmals außerhalb des eigenen Rechners. Das ist für den Umfang zu viel.

**3. Externer ASR-Dienst.** Das Audio verließe die eigene Kontrolle, und es bräuchte einen Verarbeitungsvertrag (`processor-agreements.md`). Einen Qualitätsgewinn gibt es nicht: Plaud als Cloud-Dienst ist bei den Wörtern nicht besser (TOOL-93). TOOL-60 hat das Remote-Backend TOOL-14 aus demselben Grund verworfen.

**4. Nichts tun.** Gewählt. Datenschutz und Betrieb bleiben, wie sie sind (`docs/datenschutz.md`): mündliche Einwilligung pro Sitzung, Rohaudio lokal bis Kampagnenende, nichts Neues im Verarbeitungsverzeichnis von Narrata.

## Wann neu prüfen

Neu geprüft wird erst, wenn eine Spielleitung konkret nach der Pipeline fragt, weil ihrer Gruppe der Fremdformat-Upload nicht reicht. Dann ist für Weg 1 zu klären:

- Installer und Anleitung für jemanden ohne Python-Umgebung.
- Hardware-Untergrenze mit gemessener CPU-Laufzeit.
- Einwilligungshinweis für fremde Runden. Die mündliche Einwilligung pro Sitzung ist heute nur in der eigenen Gruppe eingeübt.
- Modellwahl ohne YAML. Aus TOOL-60: Fremde Nutzer pflegen keine `asr.model`-Konfiguration, und vielleicht wird eine Einstellung auf Gruppenebene in Narrata nötig. Ein Modellwechsel macht gespeicherte Transkripte `stale`.

## Folge-Tickets

- Weg 1 (Paketierung, Anleitung, Einwilligungshinweis): [kein Ticket: keine Nachfrage, Neuprüfung erst bei einer konkreten Anfrage]
- Modellwahl auf Gruppenebene in Narrata: [kein Ticket: entfällt, solange die Transkription nicht geöffnet wird]
- Eigener Worker, externer ASR-Dienst: [kein Ticket: verworfen]
