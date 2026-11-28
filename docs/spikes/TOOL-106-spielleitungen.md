# TOOL-106 — Zwei Spielleitungen nach Label trennbar?

Stand 2026-11-28. Bericht zu [TOOL-106](../plans/TOOL-106-several-gms.md), Werkzeug: [`scripts/spike/gms.py`](../../scripts/spike/gms.py). Die Messung lief lokal auf den gespeicherten Transkripten, der Zuordnung und dem Wissens-Snapshot der Pilotsitzung, ohne Modell. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keine Labels, keinen Session-Schlüssel, keine Zeitfenster. Die beiden Spielleitungen (SL) heißen SL 1 und SL 2, nach Passagenzeit geordnet.

## Ergebnis

- **Die Pipeline legt die beiden SL nicht zusammen.** Im Export der Pilotsitzung hat jede SL 2 eigene Labels (eines je Segment), jedes mit der eigenen `participant_id`. Keiner der Zuordnungseinträge ist verworfen. Das „SL“ für beide in Narrata stammte aus Narratas Benennung für KI-Läufe, die jede SL pauschal `SL` nannte. IOA-1341 hat das behoben.
- **Nach Label trennbar: ja.** In den Handreferenzen A und B stehen 0,8 % der Wörter von SL 1 (n = 123) unter einem Label von SL 2. Umgekehrt sind es 5,6 % der Wörter von SL 2 (n = 36, also 2 Wörter). Das liegt im Bereich des Sprecherfehlers auf Passagenebene nach TOOL-96 (A 6,2 %, B 3,6 %). Die Diarisierung allein genügt also für die Trennung der beiden SL, eine andere Zuordnung braucht es nicht.
- **Der größere Fehler liegt zwischen SL 1 und den Mitspielenden.** 24,4 % der Wörter von SL 1 stehen unter einem Label von Mitspielenden, an A wie an B. Das ist der allgemeine Sprecherfehler aus TOOL-96, kein Problem zweier SL. An beiden Fenstern zusammen ergibt das rund 5 % aller gewerteten Wörter. Dass sich der Fehler bei SL 1 ballt, ist mit 30 Wörtern an zwei Fenstern nur ein Hinweis.

## Methode

- **Person je Passage:** Jede Passage spricht als die Person, der ihr Label im Segment zugeordnet ist (`speakers.check`, wie der Export). Wer SL ist, kommt aus `role` im Snapshot.
- **Sitzung:** Labels, Passagen und Passagenzeit je SL, Mitspielende und ohne Person über beide Segmente.
- **Fenster:** Die Handreferenz wird gegen die Wörter des Segments im Fenster ausgerichtet (`SequenceMatcher`, wie die WDER aus TOOL-20). Gewertet werden nur Wörter, die beide gleich erkennen. Die Hand-Sprecher werden den Personen 1:1 so zugeordnet, dass die meisten Wörter stimmen (`denoise.best_mapping`). Gezählt wird für jeden Hand-Sprecher, der so auf eine SL fällt, unter wem seine Wörter stehen.

## Sitzung

| Sprecher | Labels | Passagen | Anteil | Passagenzeit (h:mm) |
| --- | ---: | ---: | ---: | ---: |
| SL 1 | 2 | 665 | 30,7 % | 1:52 |
| SL 2 | 2 | 542 | 25,0 % | 0:54 |
| Mitspielende | 3 | 932 | 43,0 % | 1:58 |
| ohne Person | 0 | 27 | 1,2 % | 0:01 |

„ohne Person“ sind Passagen ohne Label, also solche, in denen kein Sprecherturn die Wörter deckt. Sie erscheinen im Export als `unlabelled`.

## Handreferenzen

| Fenster | SL | Wörter | gleiche SL | andere SL | Mitspielende | ohne Person |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | SL 1 | 73 | 74,0 % | 1,4 % | 24,7 % | 0,0 % |
| A | SL 2 | 36 | 88,9 % | 5,6 % | 5,6 % | 0,0 % |
| B | SL 1 | 50 | 76,0 % | 0,0 % | 24,0 % | 0,0 % |
| alle | SL 1 | 123 | 74,8 % | 0,8 % | 24,4 % | 0,0 % |
| alle | SL 2 | 36 | 88,9 % | 5,6 % | 5,6 % | 0,0 % |

An B fällt kein Hand-Sprecher auf SL 2.

## Grenzen

- **Wenige Wörter von SL 2.** Ihre Werte stützen sich auf 36 Wörter aus einem Fenster. Die Handreferenzen C bis K aus TOOL-107 liegen auch vor. Ihre Zeitfenster stehen aber nicht im Repo, und `gms.py --clip NAME=DATEI@H:MM:SS-H:MM:SS` nimmt sie auf, falls die Zahl wackelt.
- **Eine Sitzung.** 017 ist noch nicht zugeordnet und deshalb nicht gemessen.
- **Rolle gruppenweit.** Gemessen ist mit `role`. Ab Kontext 1.5 kann `session_role` an einem Abend etwas anderes sagen (Chunk 3 und 4 von TOOL-106). Für die Pilotsitzung sind beide SL auch die SL des Abends.

## Folgen

- Keine Änderung an Diarisierung, Zuordnung oder Export. Ein Regressionstest hält fest, dass zwei SL zwei Labels mit je eigener `participant_id` bleiben (TOOL-106, Chunk 1).
- Verwechslung SL↔SL `[kein Ticket: unter dem Sprecherfehler aus TOOL-96, die Diarisierung trennt die beiden]`.
- Wörter von SL 1 unter Labels der Mitspielenden `[kein Ticket: allgemeiner Sprecherfehler, kein Problem zweier SL; TOOL-105 misst ihn neu mit der geänderten Aufnahme am Tisch]`.
