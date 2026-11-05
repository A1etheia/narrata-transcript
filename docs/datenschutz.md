# Datenschutz im Transkript-Projekt

Stand 2026-11-02. Das Projekt ist ein privates Werkzeug für die eigene Spielgruppe, betrieben von einer Person; kein öffentlicher Dienst. Diese Seite hält fest, wie wir mit Aufnahmen und Transkripten umgehen. Sie ist keine juristische Prüfung.

Dieses Dokument enthält keine Klarnamen und keine Sitzungsdaten.

## Was entsteht und wo es liegt

| Daten | Ort | Verlässt den Rechner? |
| --- | --- | --- |
| Rohaudio, Audiosegmente | `input/`, `work/` | Nein, nie |
| ASR-Ergebnisse, Sprecher-Turns, Review-Dateien, Sprecherzuordnung | `work/` | Nein |
| Transkriptionskontext aus Narrata (Teilnehmende, Glossar; Klarnamen) | `work/<gruppe>/<ordinal>/narrata/` | Nein, kommt nur herein |
| Wissens-Snapshot (kann Klarnamen enthalten) | `work/` | Nein |
| Strukturierter Transkript-Export | `output/` | Ja, nach Narrata |

## Entscheidungen

**Einwilligung.** Alle hörbaren Personen stimmen zu Beginn jeder Sitzung mündlich zu; das Session-Manifest vermerkt, dass die Zustimmung vorlag. Fehlt die Zustimmung einer Person, wird nicht aufgenommen.
*Grund:* In einer festen Gruppe am Spieltisch ist das der einfachste Weg, und die Frage stellt sich jedes Mal neu. Belegbar ist die Zustimmung danach nur über den Manifest-Vermerk.

**Widerruf (vorläufig).** Ein Widerruf gilt sofort für künftige Sitzungen. Für vergangene Sitzungen werden Audio, Arbeitsdateien und Snapshot-Einträge der Person lokal gelöscht; in Narrata gelten die Regeln aus IOA-1216.
*Grund:* Wer nicht mehr beteiligt sein will, soll das ohne Sonderweg durchsetzen können. Ob sich das in der Praxis trägt, zeigt der Pilot (TOOL-60).

**Rohaudio.** Rohaudio und Segmente bleiben lokal, bis die Kampagne endet (letzte Sitzung der Gruppe), und werden dann von Hand gelöscht. Ein erfolgreicher Export löst keine Löschung aus.
*Grund:* So bleiben Nachhören und neue Läufe mit besseren Modellen möglich. Bis dahin ist der lokale Rechner der einzige Schutz der Aufnahmen.

**Transkripte in Narrata.** Standardmäßig sieht sie nur die Spielleitung; die Freigabe an Mitspielende ist eine bewusste Aktion pro Transkript.
*Grund:* Am Tisch Gesagtes ist nicht automatisch für alle zum Nachlesen gedacht.

**Auswertungen pro Person.** Redeanteile und IT/OT-Wechsel erscheinen nur mit Opt-in der betroffenen Person namentlich, sonst aggregiert oder nur mit Sprecher-Label.
*Grund:* Solche Zahlen sagen etwas über das Verhalten einer Person aus; das soll sie selbst entscheiden.

**Wissens-Snapshot.** Der Snapshot darf Klarnamen enthalten, weil Sprecherzuordnung und Keyword-Biasing sie brauchen. Er bleibt dauerhaft lokal in `work/`, nachvollziehbar pro Sitzung. Eine Löschfrist gibt es nicht; er überdauert das Rohaudio und wird nur bei einem Widerruf bereinigt.
*Grund:* Die Reproduzierbarkeit eines Laufs hängt am Snapshot, und er enthält nur Daten, die in Narrata ohnehin stehen.

**Logs und Fehlermeldungen.** Sie enthalten standardmäßig nur Session-Schlüssel, Passagen-IDs, Laufzeiten und Zähler. Nur ein ausdrücklich aktivierter Debug-Modus darf Transkripttext schreiben, und zwar in eine Logdatei unter `work/`, nie auf die Konsole.
*Grund:* Konsolenausgaben landen schnell in Tickets oder Chats; zum Fehlersuchen braucht es den Text trotzdem manchmal.

**Modelle und Telemetrie.** Modelle kommen einmalig per Download in den lokalen Cache; danach läuft die Pipeline ohne Netz. Bibliotheken, die von sich aus Daten nach außen melden, werden abgeschaltet: pyannote.audio 4 schickt sonst Laufmetadaten (Audiodauer, Sprecherzahl) an seinen Hersteller.
*Grund:* Auch Metadaten über eine Sitzung gehören nicht zu Dritten, und „vollständig lokal“ soll ohne Ausnahmen gelten.

**Abruf aus Narrata (TOOL-67).** Die einzige Verbindung im Lauf ist `transcript context`. Der Befehl holt den Transkriptionskontext einer Sitzung lesend vom eigenen Narrata und läuft nur, wenn man ihn ausdrücklich aufruft. Dabei geht nichts aus der Aufnahme hinaus, mitgeschickt werden nur Gruppen-ID, Ordinal und der Token. Der Token steht in `.env`, nie in Konfiguration, Log oder Fehlermeldung, und reist nur über `https` (`http` nur zu `localhost`). Die Konsole zeigt vom Ergebnis nur Zähler. Ohne Netz übernimmt `--from-file` eine gespeicherte Antwort.
*Grund:* Teilnehmende und Glossar stehen bereits in Narrata. Eine zweite, von Hand gepflegte Liste würde veralten und Klarnamen an einem weiteren Ort führen.

**Test-Fixtures.** Fixtures sind synthetisch oder vollständig anonymisiert.
*Grund:* Sie liegen im Repo, und das Repo ist derzeit öffentlich erreichbar.

## Anforderungen an Narrata (IOA-1216)

- **Sichtbarkeit:** Transkripte standardmäßig nur für die Spielleitung, Freigabe pro Transkript.
- **Opt-in:** Personen-Auswertungen namentlich nur mit Opt-in der betroffenen Person.
- **Retention:** Narrata speichert kein Rohaudio. Das Rohaudio bleibt bis Kampagnenende lokal, wie lange das Transkript in Narrata bleibt, regelt IOA-1216.
- **Export:** Transkripte und Personenstatistik gehören in den Datenexport der betroffenen Person.
- **Widerruf:** Narrata braucht einen Weg, die Passagen einer Person nach einem Widerruf zu behandeln.
