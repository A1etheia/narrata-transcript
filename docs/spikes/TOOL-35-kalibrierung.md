# TOOL-35 — Kalibrierung der Unsicherheitsbewertung

Stand 2026-11-06. Bericht zu [TOOL-35](../plans/TOOL-35-confidence-rules.md), gemessen mit `transcript calibrate` (siehe [README](../../README.md#kalibrierung)) und zwei Wegwerf-Skripten für den Parakeet-Abgleich. Der Bericht enthält nur Kennzahlen: keine Transkriptauszüge, keine Namen, keinen Session-Schlüssel. Der Agent hat weder Handreferenz noch Transkripte, Hinweise oder den Bewertungsbogen gelesen, er kennt nur Zählwerte.

## Kurzfassung

- **Die Signale grenzen die Review ein, aber nur auf etwa die Hälfte.** Am Clip liegen 85 % der Fehler in markierten Passagen, die 78 % der Clip-Zeit ausmachen. Über die ganze Session sind 46 % der Zeit markiert (36 % der Passagen). Ohne Bewertung müsste man alles anhören.
- **Word-Confidence ist das stärkste Signal** (AUC 0,79). Die übrigen Regeln ergänzen sie vor allem bei Auslassungen.
- **Auslassungen bleiben die Schwachstelle.** 9 der 17 übersehenen Fehler sind ausgelassene Wörter. Ein Parakeet-Zweitlauf würde 8 davon finden, kostet aber deutlich mehr Review-Zeit. Er wird als [TOOL-82](https://alethe1a.atlassian.net/browse/TOOL-82) umgesetzt.
- **Hotwords verschlucken Text.** Mit den Glossar-Begriffen als Hotwords fehlen auf der 5-h-Aufnahme etwa 16 % der Wörter. Das wird in [TOOL-81](https://alethe1a.atlassian.net/browse/TOOL-81) behoben, gemessen wurde ohne Hotwords.
- **`similar` über den Klang ist meist Fehlalarm** (29 % richtig), über die Schreibung meist berechtigt (70 %). Klang-Treffer heben eine Passage deshalb nicht mehr an, bleiben aber in der Hinweisdatei.
- **Mundart verdreifacht die Fehlerquote** (14 % gegen 48 %). Die Regeln fangen das über die Confidence teilweise auf. Schwellen pro Person sind erst mit TOOL-68 möglich.

## Material und Methode

| | |
| --- | --- |
| Aufnahme | eine Sitzung, 2 Segmente, zusammen etwa 5:26 h |
| Pipeline | Whisper large-v3-turbo (faster-whisper 1.2.1, CTranslate2 4.8.5), ohne Hotwords; pyannote-Diarisierung |
| Snapshot | `685c0402a061…`: 202 Glossar-Einträge, davon 3 `pc` und 199 `archive`, kein Eintrag mit `asr_variants` |
| Handreferenz | 3:00 aus Segment 1 (aus TOOL-62), 358 gewertete Wörter, 2 Sprecher |
| Clip-Lage | per exaktem PCM-Abgleich bei 1:25:00 in Segment 1 gefunden; gemessen wird im 5-h-Lauf, nicht in einem Clip-Lauf |
| `similar`-Bogen | 50 Hinweise, gleichmäßig über die Session verteilt, von der Nutzerin angehört; 48 beurteilt |

Die Fehler sind gegen die Handreferenz ausgerichtet wie in [TOOL-62](TOOL-62-asr-vergleich.md). Eine Ersetzung oder Einfügung zählt in der Passage ihres Wortes, eine Auslassung in der Passage des Nachbarworts. Eine Passage gilt als „markiert“, wenn sie `needs_review` oder `uncertain` ist. Wie in TOOL-62 entspricht ein Prozentpunkt am Clip knapp vier Wörtern, kleine Unterschiede sind Rauschen.

## Fehler am Clip

| | |
| --- | --- |
| WER | 32,4 % (116 Fehler: 52 Ersetzungen, 58 Auslassungen, 6 Einfügungen; 2 Wörter in `???` absorbiert) |
| Sprecher A | 14,0 % der Wörter falsch |
| Sprecher B (Mundart) | 47,5 % der Wörter falsch |
| Confidence-AUC | 0,79 |
| Anteil falscher Wörter unter den unsichersten 10 / 20 / 30 % | 29 / 45 / 69 % |

Die WER liegt über der aus TOOL-62, weil hier der Lauf auf der ganzen Aufnahme zählt und nicht ein Lauf auf dem Clip allein. Die Hälfte der Fehler sind Auslassungen. Eine Word-Confidence haben sie nicht, sie lassen sich nur über Lücken, Sprechdichte oder einen Zweitlauf finden.

## Schwellen

Gemessen wurde zuerst mit den Startwerten aus dem Plan. Danach wurden die Regeln mit der höchsten Session-Last nachgezogen. Ausschlaggebend waren Regeln, die oft als einziger Grund anschlagen:

| Regel (Startwerte) | schlägt an in Passagen | davon einziger Grund |
| --- | --- | --- |
| `low_confidence` | 703 | 282 |
| `crosstalk` (jede Überlappung) | 660 | 355 |
| `gap` (1500 ms) | 423 | 169 |
| `similar` | 352 | 186 |

| Variante | Clip: Fehler gefunden | Clip: Zeit markiert | Session: Zeit markiert |
| --- | --- | --- | --- |
| Startwerte | 85 % | 78 % | 62 % |
| A: `gap_ms` 2500, Übersprechen erst ab 1000 ms | 85 % | 78 % | 52 % |
| A + `similar` über Klang ohne Stufe (**gewählt**) | 85 % | 78 % | 46 % |

Neue Defaults sind deshalb `gap_ms: 2500`, der neue Schlüssel `crosstalk_ms: 1000` und der neue Schlüssel `similar_sound_level: confident`. Übersprechen unter einer Sekunde ist am Spieltisch der Normalfall und für sich kein Fehlerhinweis. Alle übrigen Startwerte bleiben, weil am Clip keine Änderung mehr Fehler gefunden hätte, ohne die Session-Last deutlich zu erhöhen.

Ergebnis mit den Defaults:

| | Clip | Session |
| --- | --- | --- |
| `confident` | 10 Passagen, 23 % der Zeit, 17 Fehler (9 Auslassungen) | 2472 Passagen |
| `needs_review` | 23 Passagen, 77 % der Zeit, 95 Fehler | 1170 Passagen |
| `uncertain` | 1 Passage, 1 % der Zeit, 4 Fehler | 201 Passagen |
| markiert | 85 % der Fehler, 78 % der Zeit | 36 % der Passagen, 46 % der Zeit |
| Fehlalarme | 4 markierte Passagen ohne Fehler | — |

Am Clip tragen die Regeln so bei:

| Regel | Passagen | davon mit Fehler | Fehler darin |
| --- | --- | --- | --- |
| `low_confidence` | 17 | 15 | 74 |
| `very_low_confidence` | 12 | 10 | 58 |
| `gap` | 4 | 3 | 20 (13 Auslassungen) |
| `crosstalk` | 1 | 1 | 7 |
| `speaker_unclear` | 1 | 1 | 4 |

Der Clip ist besonders fehlerreich: Er wurde in TOOL-62 dort gewählt, wo die Modelle am stärksten voneinander abweichen. Dass er zu 78 % markiert ist, die Session aber nur zu 46 %, passt dazu. Wie gut die Eingrenzung auf durchschnittlichem Material ist, muss [TOOL-60](https://alethe1a.atlassian.net/browse/TOOL-60) am vollen Pilotlauf zeigen.

## `similar`-Hinweise

In der Session gibt es 413 `similar`-Hinweise. 312 davon wurden über den Klang gefunden, 101 über die Schreibung. 22 sind mehrdeutig, sie bleiben unabhängig von der Methode `uncertain`. Bewertet wurde nach Anhören:

| Methode | richtig | Präzision |
| --- | --- | --- |
| Klang | 11 von 38 | 29 % |
| Schreibung, Score < 0,9 | 1 von 2 | 50 % |
| Schreibung, Score 0,9–0,95 | 5 von 7 | 71 % |
| Schreibung, Score ≥ 0,95 | 1 von 1 | 100 % |
| gesamt | 18 von 48 | 38 % |

Gemessen ist nur die Präzision, eine Trefferquote nicht. Wie viele falsch erkannte Namen gar keinen Hinweis bekommen, bleibt offen. Für Score-Bänder sind die Zahlen zu klein, `min_ratio` bleibt deshalb bei 0,85.

Ein Teil der Fehlalarme kommt vom Glossar. Narrata hat für diese Sitzung keinen Eintrag als `session` oder `recent` eingestuft, alle 199 Nicht-Spielfiguren stehen im Archiv. Die Pipeline prüft deshalb gegen Figuren und Orte, die seit langem nicht mehr vorkommen. Sind die letzten Sitzungen in Narrata mit Tagebuch-Einträgen verknüpft, werden die aktuellen Einträge erkennbar. Archiv-Treffer strenger zu behandeln ist ein eigenes Folge-Ticket.

`known_variant` ließ sich nicht messen, weil der Snapshot keine `asr_variants` enthält.

## Parakeet als Zweitlauf

Verglichen wurden Whisper und Parakeet TDT 0.6B v3 (Läufe aus TOOL-62). Wo Whisper Parakeet widerspricht, gilt die Whisper-Passage als markiert. Lässt Whisper ein Wort aus, wird das Nachbarwort markiert.

| Messung | Ergebnis |
| --- | --- |
| Clip: Whisper-Fehlerstellen in einer Abweichung | 48 von 70 |
| Clip: abweichende Tokens ohne Fehler | 42 |
| Clip: zusätzlich gefundene Fehler in `confident`-Passagen | 16 von 17, davon 8 von 9 Auslassungen |
| Clip: zusätzliche Zeit, Fehlalarme | +15 % der Clip-Zeit, 1 Passage ohne Fehler |
| Segment 1: markierte Zeit, Regeln / Parakeet / beides | 49 / 74 / 81 % (vor `similar_sound_level`) |

Parakeet findet fast alles, was die Regeln übersehen, vor allem Auslassungen. Als harte Stufe würde es die Review aber auf vier Fünftel der Session ausdehnen. Entschieden wurde: aufnehmen. Wie der Abgleich wirkt (eigene Stufe, schwaches Signal oder nur Auslassungs-Hinweise), entscheidet [TOOL-82](https://alethe1a.atlassian.net/browse/TOOL-82).

## Mundart

Der Mundartsprecher hat eine dreimal so hohe Fehlerquote. Die Diarisierungs-Labels gelten nur innerhalb eines Segments und sind bis TOOL-68 keiner Person zugeordnet, Schwellen pro Person gibt es deshalb nicht. Die Zahl geht an [TOOL-36](https://alethe1a.atlassian.net/browse/TOOL-36) zur Gewichtung der Review-Kandidaten, sobald die Labels Personen zugeordnet sind.

## Offen

- **Repräsentativität:** ein Clip, zwei Sprecher, eine Sitzung. TOOL-60 misst mit `transcript calibrate` nach.
- **Trefferquote von `similar`:** Dafür bräuchte es eine Handreferenz mit vielen Namen.
- **`known_variant`:** erst messbar, wenn Narrata `asr_variants` pflegt.
- **Hotwords:** Nach TOOL-81 muss die Kalibrierung mit Hotwords wiederholt werden.
