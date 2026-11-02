# TOOL-66 — Datenschutz-, Einwilligungs- und Sichtbarkeitsentscheidungen


## Ziel
Vor der ersten echten Sitzung steht schriftlich fest, welche personenbezogenen Daten entstehen, wer eingewilligt haben muss, was lokal bleibt und was mit welcher Sichtbarkeit nach Narrata geht. Heute regeln das nur die Grenzen in `CLAUDE.md`; TOOL-4, TOOL-5, TOOL-58 und IOA-1216 bauen auf diesen Entscheidungen auf.

## Ist-Stand
- `CLAUDE.md:9-13`: Rohaudio bleibt lokal, echte Daten kommen nie ins Repo.
- `.gitignore`: schließt `input/`, `work/`, `output/`, Audioformate und `.env` aus.
- `README.md`: Abschnitt „Echte Audio- und Transkriptdateien“, noch ohne Verweis auf ein Datenschutzdokument.
- `docs/`: kein Datenschutzdokument vorhanden.

## Entscheidungen
Stand 2026-11-02, Wahl der Projektverantwortlichen, keine juristische Prüfung (laut Ticket nicht im Scope).

| Punkt | Entscheidung | Quelle |
| --- | --- | --- |
| Einwilligung | Alle hörbaren Personen stimmen pro Sitzung mündlich zu Beginn zu; das Session-Manifest vermerkt, dass die Zustimmung vorlag. Ohne Zustimmung aller keine Aufnahme. | Festlegung |
| Rohaudio | Rohaudio und Segmente bleiben lokal, bis die Kampagne endet, und werden dann gelöscht. | Festlegung |
| Transkripte in Narrata | Standard nur Spielleitung; Freigabe an Mitspielende ist eine bewusste Aktion pro Transkript (Umsetzung IOA-1216). | Ticket |
| Auswertungen pro Person | Nur mit Opt-in der betroffenen Person, sonst aggregiert oder Label-basiert (Flag in IOA-1216). | Ticket |
| Wissens-Snapshot | Darf Klarnamen enthalten, bleibt dauerhaft lokal in `work/` und verlässt den Rechner nicht. | Festlegung |
| Logs und Fehlermeldungen | Standard nur Session-Schlüssel, Passagen-IDs, Laufzeiten und Zähler. Nur ein ausdrücklicher Debug-Modus darf Transkripttext schreiben, und zwar in eine Logdatei unter `work/`, nie auf die Konsole und nie ins Repo. | Festlegung |
| Test-Fixtures | Synthetisch oder vollständig anonymisiert. | Festlegung |
| Widerruf (vorläufig) | Ein Widerruf wirkt für künftige Sitzungen. Für vergangene Sitzungen werden Audio, Arbeitsdateien und Snapshot-Einträge der Person lokal gelöscht und Narrata-seitig die IOA-1216-Regeln angewandt. | Vorschlag, im Dokument als vorläufig markiert |

Das Dokument enthält das Ablaufdatum „Kampagnenende“ als Ereignis (letzte Sitzung der Gruppe). Es nennt keine Klarnamen, da das GitHub-Repo derzeit öffentlich erreichbar ist.

Maßstab: eine Einzelperson, die eigene Gruppe, kein öffentlicher Dienst. Das Dokument bleibt deshalb kurz und praktisch, ohne formales Compliance-Vokabular.

Drei Folgen der Wahl stehen ausdrücklich im Dokument:
- Mündliche Zustimmung ist nachträglich nur über den Manifest-Vermerk belegbar.
- Audio kann über eine lange Kampagne hinweg liegen bleiben; der Rechner ist damit der einzige Schutz.
- Der Snapshot hat keine Löschfrist und überdauert das Audio; nur der Widerruf löscht daraus.

## Daten-Check
- Folgt TOOL-66: handled — dieses Ticket definiert die Regeln.
- Echtes im Repo, Log oder Fehlertext: handled — nur Regeltext, keine Klarnamen, keine Sitzungsdaten, kein Code.

## Contract-Check
N/A — kein Contract-JSON und kein Endpoint betroffen. Narrata-Anforderungen gehen als Kommentar an IOA-1216.

## Resume-Check
N/A — kein Modell und kein langlaufender Schritt.

## Dependency-Check
N/A — keine neue Abhängigkeit.

## Format-Check
N/A — kein versioniertes Format. Das Manifest-Feld für die Zustimmung wird in TOOL-12 eingeführt.

## Chunks
### Chunk 1 — Datenschutzdokument
- Dateien: `docs/datenschutz.md`, `README.md`
- Änderung: Jede Entscheidung mit Begründung und Stand festhalten, Datenarten und Speicherorte auflisten, die Narrata-Anforderungen als eigenen Abschnitt führen. README verweist darauf.
- Verify: `scripts/check`; `grep -n datenschutz README.md`
- AC: Jeder Punkt aus „Zu entscheiden“ hat einen Stand; kein „später“; README verweist auf das Dokument.

### Chunk 2 — Anforderungen an IOA-1216
- Dateien: keine (Jira)
- Änderung: Kommentar an IOA-1216 mit Sichtbarkeit, Opt-in, Retention, Export, Widerruf; Verweis auf `docs/datenschutz.md`. Erst nach dem Merge, damit der Link stimmt.
- Verify: Kommentar am Ticket sichtbar
- AC: Die Narrata betreffenden Punkte sind in IOA-1216 hinterlegt.

## Folge-Tickets
- TOOL-12: Session-Manifest vermerkt die mündliche Zustimmung pro Sitzung.
- TOOL-6: Debug-Modus so konfigurieren, dass Transkripttext nur in eine Logdatei unter `work/` geht.
- TOOL-5: README dokumentiert die Aufbewahrung (Rohaudio bis Kampagnenende, Snapshot dauerhaft lokal).
- [kein Ticket: Löschung am Kampagnenende erfolgt vorerst manuell; ein Skript lohnt erst nach dem Pilot TOOL-60]

## Chunk-Tabelle
| Chunk | Scope | Clear context after? |
| --- | --- | --- |
| 1 | Datenschutzdokument, README | no |
| 2 | Kommentar an IOA-1216 nach dem Merge | no |

## Verifikation
`scripts/check` grün; die Akzeptanzkriterien von TOOL-66 gegen `docs/datenschutz.md` abhaken; nach dem Merge den Kommentar an IOA-1216 prüfen.
