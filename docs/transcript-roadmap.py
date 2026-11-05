#!/usr/bin/env python3
"""Recompute docs/transcript-roadmap.md and the Jira date list.

Single source for the transcript project's schedule (Jira TOOL + IOA-1213).
Edit START, WORKDAYS, PAUSES or the task list P, then run:

    python3 docs/transcript-roadmap.py

Writes transcript-roadmap.md next to this file and prints one JSON line per
ticket (key, start, end) for mirroring into Jira (customfield_10015 / duedate).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib

START = dt.date(2026, 11, 2)  # a Monday
WORKDAYS = [0, 1, 3]  # Mon, Tue, Thu -> 3 dev-days per week
PAUSES = [(dt.date(2026, 12, 21), dt.date(2027, 1, 3))]  # inclusive ranges, no work
GENERATED = "2026-11-05"

# (phase title, milestone sentence, [(key, title, dev-days, note)])
P = [
    ("Phase 0 — Fundament und Entscheidungen",
     "M0 — Repo steht, Datenschutz entschieden, Contract v1 eingefroren. Nichts auf beiden Seiten schreibt JSON, bevor IOA-1214 steht.", [
        ("TOOL-66", "Datenschutz-/Einwilligungs-/Sichtbarkeitsentscheidungen", 0.5, "erledigt: `docs/datenschutz.md`"),
        ("TOOL-2", "Repo, Python-Projekt, README", 0.5, "erledigt"),
        ("TOOL-4", "Verzeichnis-/Sessionstruktur (Narrata-Schlüssel)", 0.5, "erledigt: `src/transcript/session.py`, Layout im README"),
        ("TOOL-5", "Dateiregeln, Rohaudio bleibt lokal", 0.5, "erledigt: `.gitignore`, `tests/fixtures/`, Dateiregeln im README"),
        ("TOOL-6", "Basiskonfiguration", 0.5, "erledigt: `src/transcript/config.py`, `config/example.yaml`"),
        ("IOA-1216", "Privacy-/Sichtbarkeitsmodell, Opt-in-Flag", 1.5, "Narrata-Seite von TOOL-66; Anforderungen in `docs/datenschutz.md`"),
        ("IOA-1214", "Contract v1: Schema, Fixture, Validator", 1.0, "Fixture dient IOA-1218, bis TOOL-58 liefert; aus TOOL-5: die Kopie der Contract-Fixture liegt im Pipeline-Repo unter `tests/fixtures/`"),
    ]),
    ("Phase 1 — ASR-Spike und Backend-Entscheidung",
     "M1 — Backend gewählt, Diarisierung entschieden, TOOL-11/33 entschieden, Export-Endpoint live. Reflexionspunkt: Epic TOOL-8 wird hier dimensioniert.", [
        ("TOOL-62", "ASR-Kandidaten an realer Session (inkl. Hand-Check, Long-Audio-Frage)", 3.0, "erledigt: `docs/spikes/TOOL-62-asr-vergleich.md`; Whisper large-v3-turbo, Fallback Parakeet, keine eigene Segmentierung; vor IOA-1216/IOA-1214 vorgezogen (02.–04.11.2026)"),
        ("TOOL-20", "Diarisierung / Label-Stabilität", 2.0, "erledigt: `docs/spikes/TOOL-20-diarisierung.md`; separate Diarisierung mit pyannote community-1, 4 stabile Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; NeMo braucht auf 5 h über 25 GB RAM; Integration in TOOL-76"),
        ("IOA-1215", "Transcription-context Export-Endpoint", 2.0, "während ASR-Läufe laufen"),
        ("IOA-1217", "asr_variants-Alias-Kategorie", 1.5, ""),
    ]),
    ("Phase 2 — Pipeline-Kern bis Referenztranskription",
     "M2 — Eine Session läuft vom MP4 bis zur Referenztranskription mit Sprecher-Labels und Wissens-Snapshot.", [
        ("TOOL-9", "ffmpeg/ffprobe-Preflight", 0.5, "erledigt: `src/transcript/audio_tools.py`, `transcript doctor`"),
        ("TOOL-10", "Formate erkennen, Audiospur extrahieren", 1.0, "erledigt: `src/transcript/audio.py`, `transcript extract`"),
        ("TOOL-12", "Session-Manifest, absolute Zeiten", 1.0, "erledigt: `src/transcript/manifest.py`, `transcript manifest`; Teilaufnahmen einer Sitzung sind die Segmente"),
        ("TOOL-63", "Backend-Schnittstelle, Capabilities, Fake-Backend", 1.0, "erledigt: `src/transcript/asr/`, `docs/asr-backends.md`; AK „V0.1-Backend implementiert die Schnittstelle“ an TOOL-64 übergeben"),
        ("TOOL-16", "Internes Referenztranskript-Format", 1.0, "erledigt: `src/transcript/reference.py`, `docs/referenzformat.md`; eine Datei pro Segment unter `work/<session>/asr/`, Rohform getrennt"),
        ("TOOL-64", "Lokales V0.1-Backend", 2.0, "erledigt: `src/transcript/asr/whisper.py`, README „Spracherkennung“; `scripts/spike/` entfernt, Runner im Stand `2f5b875`"),
        ("TOOL-76", "Diarisierung mit pyannote integrieren", 1.5, "erledigt: `src/transcript/diarization/`, `transcript diarize`, README „Diarisierung“; Labels pro Segment, Rohform unter `work/<session>/diarization/`; pyannote-Telemetrie per `transcript/__init__.py` abgeschaltet"),
        ("TOOL-15", "Einzelsegment transkribieren", 0.5, "erledigt: `src/transcript/transcription.py`, `transcript transcribe --segment N`, README „Spracherkennung“; ein Fehlschlag ersetzt nie ein erfolgreiches Ergebnis"),
        ("TOOL-17", "Ganze Session, Resume", 1.0, "erledigt: `transcription.transcribe_session`, `transcript transcribe <session>` mit Wiederaufnahme und Diarisierung, README „Lauf“"),
        ("TOOL-18", "Fehlerkategorien, Retry, Force", 1.0, "aus TOOL-63: Fehlerklassen mit `retryable` stehen in `transcript.asr`; TOOL-18 ergänzt Retry, Resume, Force, Protokollierung; aus TOOL-16: `status: failed` mit `error.category`/`retryable` nimmt Fehler auf, `reference.failed_reference`; aus TOOL-64: Retry auf `ResourceError`/`BackendRuntimeError`; aus TOOL-76: Retry auch für `ResourceError`/`BackendRuntimeError` der Diarisierung, Nahtstelle ist der Segment-Körper von `diarize_session`; aus TOOL-15: Retry bei `ResourceError`/`BackendRuntimeError`, Protokollierung; aus TOOL-17: `transcribe_session` speichert `failed`, läuft weiter und versucht es beim nächsten Lauf ohne `--force` erneut, Nahtstelle für Retry ist `transcription._run` pro Segment; Exit 1 bei `failed`/`open`"),
        ("TOOL-19", "Absolute Zeitstempel im Format", 0.5, "aus TOOL-12: für das Format `timecode.format_ms` und `manifest.Segment` nutzen; aus TOOL-16: absolute Zeiten werden nicht gespeichert, sondern über `Segment.to_absolute_ms` berechnet; Zeiten knapp hinter dem WAV-Ende hier behandeln"),
        ("TOOL-67", "Narrata-Kanal + Datei-Fallback", 1.0, "braucht IOA-1215; aus TOOL-6: `.env.example` anlegen, sobald das Narrata-Token die erste Variable ist; aus TOOL-12: Rohdatei unter `work/<session>/narrata/transcription-context.json`, `transcript.narrata.read_session` liest daraus den Block `session`; Response-Form gegen die IOA-1215-Doku prüfen"),
        ("TOOL-38", "Teilnehmerwissen", 0.5, ""),
        ("TOOL-39", "Glossarbegriffe", 0.5, ""),
        ("TOOL-41", "Relevanzregel + Snapshot", 1.0, "aus TOOL-16: sobald der Snapshot eine ID hat, gehört sie in den `asr`-Block (Formatversion erhöhen); aus TOOL-76: `num_speakers` aus dem Snapshot statt der CLI-Option `--num-speakers`; aus TOOL-17: Snapshot-ID und Keywords in die Wiederverwendungsregel `transcription._reusable` aufnehmen"),
        ("TOOL-42", "Validator + Diagnose", 0.5, ""),
        ("TOOL-43", "Wissensschnittstelle", 1.0, "aus TOOL-15: Keywords aus der Wissensschnittstelle statt `()` an `transcribe_session(keywords=…)`, die CLI übergibt heute `()`; das AK „Keyword-Hinweise übergeben“ aus TOOL-15 liegt hier; aus TOOL-17: Keywords in die Wiederverwendungsregel `transcription._reusable` aufnehmen, sobald welche übergeben werden"),
        ("TOOL-44", "Keyword-Biasing + Review-Signal", 1.0, "aus TOOL-62: Hotwords nur mit large-v3-turbo, höchstens 223 Tokens, wichtigste Begriffe nach vorne; Wirkung auf die WER unbelegt; aus TOOL-15: Keywords erreichen das Backend über `transcribe_session(keywords=…)`"),
        ("TOOL-40", "Fehlvarianten (leer-lauffähig) + Vorschlagsliste", 0.5, ""),
    ]),
    ("Phase 3 — Review, Sprecherzuordnung, Export",
     "M3 — JSON-Export (Contract v1) einer Session importiert lokal in Narrata und rendert dort als Rohliste.", [
        ("TOOL-35", "Konfidenz-/Unsicherheitsregeln kalibrieren", 1.5, "Stichprobe aus Phase 1 wiederverwenden; aus TOOL-62: AUC 0,79–0,82, unsicherste 30 % enthalten 62–71 % der falschen Wörter, Auslassungen unsichtbar, Mundart verdreifacht die Fehlerquote"),
        ("TOOL-36", "Review-Kandidaten", 1.0, ""),
        ("TOOL-46", "Review-Datenmodell", 0.5, ""),
        ("TOOL-47", "Review-CSV", 0.5, ""),
        ("TOOL-48", "CSV-Reimport", 0.5, ""),
        ("TOOL-68", "Sprecherzuordnung manuell", 1.0, "braucht TOOL-76; aus TOOL-20: 1:1-Zuordnung von 4 Labels zu Personen, NSC-Stimmen ohne eigenes Label; aus TOOL-76: Labels gelten nur pro Segment, über mehrere Aufnahmen einer Session zusammenführen"),
        ("TOOL-49", "Arbeitsfassung", 1.0, ""),
        ("TOOL-50", "Markierungskonvention", 0.5, ""),
        ("TOOL-53", "Abschlussbericht", 0.5, "vor TOOL-69: liefert `stats` für den Export"),
        ("TOOL-69", "JSON-Export Contract v1", 1.0, "gegen IOA-1214-Validator"),
        ("TOOL-51", "TXT-Rendering", 0.5, ""),
        ("TOOL-52", "DOCX-Rendering", 0.5, ""),
        ("IOA-1218", "Storage + idempotenter Import", 2.0, "erst gegen Fixture, dann gegen echten TOOL-69-Export"),
    ]),
    ("Phase 4 — End-to-End-Pilot",
     "M4 — Pilot-Review (TOOL-60): Kernhypothese geprüft; Entscheidungen Review-Kanal, Remote-Backend, Freigabe IT/OT. Zweiter großer Reflexionspunkt.", [
        ("TOOL-56", "Preflight", 0.5, "aus TOOL-9: `transcript doctor` ist der Ausgangspunkt des Gesamt-Preflights"),
        ("TOOL-55", "E2E-CLI mit Halt an manuellen Schritten", 1.0, "aus TOOL-10: `transcript extract` ist der erste Schritt des E2E-Befehls"),
        ("TOOL-57", "Pipeline-Status + Resume", 1.0, "aus TOOL-18: Fehlversuche stehen nur als `WARNING` auf stderr (`transcript.retry.FailureLog`); dauerhaftes Protokoll unter `work/<session>/` ist TOOL-77, mit TOOL-57 zusammen entwerfen"),
        ("TOOL-58", "Erste reale Session komplett (inkl. Review- und Zuordnungszeit)", 2.0, "Export → Fixture für IOA-1218"),
        ("TOOL-59", "Laufzeit/Ressourcen/Aufwand auswerten", 0.5, "aus TOOL-18: entscheidet, ob TOOL-78 (Versuche pro Segment im Referenzformat) gebraucht wird"),
        ("TOOL-61", "E2E-Workflow dokumentieren", 0.5, ""),
        ("TOOL-60", "V0.1 bewerten, Entscheidungen, V0.2-Backlog", 1.0, "Go/No-Go für Phase 6"),
    ]),
    ("Phase 5 — Narrata-Oberflächen",
     "M5 — Transkript per Chat/MCP befragbar, in Narrata durchsuchbar, lesbar, verlinkt.", [
        ("IOA-1220", "Volltextsuche", 1.5, "Voraussetzung für IOA-1223"),
        ("IOA-1223", "Chat + MCP", 1.5, "Kernziel: der KI-Assistent antwortet der Spielleitung aus dem Transkript"),
        ("IOA-1219", "Lese-UI am Session-Detail", 3.0, "Mockup vor Code"),
        ("IOA-1221", "Passage-Links", 2.0, ""),
    ]),
    ("Phase 6 — IT/OT-Klassifikation",
     "M6 — IT/OT-Schicht im Export, Statistik im Bericht. Reflexionspunkt: TOOL-70 entscheidet ein oder zwei Durchläufe — oder Remote-Option.", [
        ("TOOL-70", "Spike: lokales LLM an Goldstandard, Nutzen 2. Durchlauf", 2.0, "Labeln kostet die halbe Zeit"),
        ("TOOL-71", "IT/OT-Datenmodell, Contract-Bump", 1.0, ""),
        ("TOOL-72", "Erstdurchlauf", 1.5, ""),
        ("TOOL-73", "Zweitdurchlauf + Metrik", 1.5, "entfällt, wenn TOOL-70 keinen Mehrwert misst"),
        ("TOOL-74", "IT/OT-Review-Kandidaten", 0.5, ""),
        ("TOOL-75", "Sessionstatistik", 1.0, ""),
    ]),
    ("Phase 7 — Extraktion und Analytik in Narrata",
     "M7 — Erste Welt-Archiv-Einträge mit Transkript-Provenienz; IT/OT-Statistik und Abendvergleich sichtbar.", [
        ("IOA-1222", "Transkript als Extraktionsquelle, polymorphe Provenienz", 3.0, "größte Migration des Epics"),
        ("IOA-1224", "IT/OT-Flächen + Statistik", 2.0, ""),
    ]),
]

CONDITIONAL = {"TOOL-73"}


def workday_calendar(limit: int) -> list[dt.date]:
    """The first `limit` working dates: WORKDAYS of each week, skipping PAUSES."""
    out: list[dt.date] = []
    week = 0
    while len(out) < limit:
        for slot in WORKDAYS:
            d = START + dt.timedelta(days=7 * week + slot)
            if any(a <= d <= b for a, b in PAUSES):
                continue
            out.append(d)
        week += 1
    return out[:limit]


def de(d: dt.date) -> str:
    return d.strftime("%d.%m.%Y")


def main() -> None:
    total = sum(days for _, _, items in P for _, _, days, _ in items)
    cal = workday_calendar(math.ceil(total) + 1)
    cum = 0.0
    rows, phases = [], []
    for ptitle, milestone, items in P:
        pstart = cum
        for key, title, days, note in items:
            s, e = cum, cum + days
            rows.append(dict(key=key, title=title, days=days, note=note, phase=ptitle,
                             start=cal[math.floor(s)], end=cal[math.ceil(e) - 1]))
            cum = e
        phases.append(dict(title=ptitle, milestone=milestone, days=cum - pstart,
                           start=cal[math.floor(pstart)], end=cal[math.ceil(cum) - 1]))

    cond_days = sum(r["days"] for r in rows if r["key"] in CONDITIONAL)
    weeks = math.ceil(total / len(WORKDAYS)) + sum((b - a).days // 7 + 1 for a, b in PAUSES)
    pauses = ", ".join(f"{de(a)}–{de(b)}" for a, b in PAUSES)

    o = []
    o.append("# Transkript-Projekt — Roadmap (TOOL + IOA-1213)\n")
    o.append(f"Stand {GENERATED}, generiert von `transcript-roadmap.py` (Reihenfolge und Aufwände stehen dort). Verbindliche Reihenfolge und Meilensteine für das gesamte Transkript-Vorhaben: die lokale Pipeline (Jira-Projekt **TOOL**, eigenes Python-Repo) und ihr Narrata-Gegenstück (Epic **IOA-1213**). Jira-Gesamtsicht: `project in (TOOL, IOA) AND labels = transcript`.\n")
    o.append("## Annahmen\n")
    o.append("- **Eine Person, ein Zeitbudget.** TOOL- und IOA-Tickets konkurrieren um dieselben Tage; der Plan ist deshalb eine *lineare* Folge. Echte Parallelität gibt es nur dort, wo ASR-Läufe oder Modell-Downloads im Hintergrund laufen — dann wird am Narrata-Ticket derselben Phase gearbeitet.")
    o.append(f"- **Kapazität: {len(WORKDAYS)} Entwicklungstage pro Woche**, Start {de(START)}, Pause {pauses}. Das ist der Umrechnungsfaktor für die Kalenderspalte, nicht Teil des Plans — ändert sich die Kapazität, verschieben sich nur die Daten, nicht die Reihenfolge.")
    o.append("- **Aufwände sind Entwicklungstage in 0,5er-Schritten**, grob geschätzt aus den Ticket-Beschreibungen. Sie dienen der Reihenfolge und den Meilenstein-Abständen; keine Zusage.")
    o.append(f"- **Gesamtumfang: {total:g} Entwicklungstage** ≈ {weeks} Wochen inkl. Pause → letzter Meilenstein {de(phases[-1]['end'])}. Davon {cond_days:g} Tage bedingt ({', '.join(sorted(CONDITIONAL))}).")
    o.append("- **Neu terminiert am 02.11.2026:** Vom Plan des 03.10. war noch kein Ticket begonnen (alle TOOL- und IOA-Tickets To Do, kein Python-Repo, keine Transkript-Commits). Die 3 Tage pro Woche sind damit unbelegt; Reihenfolge belastbar, Daten nur bei dieser Kapazität.")
    o.append("- Nicht eingeplant: TOOL-14 (Remote-Backend, geparkt), die Epics selbst, verworfene Tickets (TOOL-21–32, 34; TOOL-3, 7; TOOL-11, 33 nach TOOL-62).\n")
    o.append("## Leitlinien der Reihenfolge\n")
    o.append("1. **Entscheidungen vor Code.** Datenschutz (TOOL-66/IOA-1216) und Contract (IOA-1214) stehen, bevor irgendetwas Daten schreibt — sonst werden Fixtures, Logs und IDs später umgebaut.")
    o.append("2. **Der ASR-Spike (TOOL-62) läuft vor der Audio-Vorbereitung.** Er entscheidet, ob Epic TOOL-8 drei oder fünf Stories hat. Ergebnis: drei, TOOL-11 und TOOL-33 entfallen.")
    o.append("3. **Narrata-Arbeit füllt die Wartezeiten der Pipeline.** Export-Endpoint und Alias-Kategorie entstehen, während Modelle rechnen; Storage/Import entsteht gegen die Fixture, bevor der echte Export existiert.")
    o.append("4. **Der Pilot (Phase 4) ist ein Tor, kein Schritt.** TOOL-60 entscheidet explizit über Review-Kanal, Remote-Backend und die Freigabe von Phase 6. Phasen 5–7 werden nach dem Pilot-Review neu terminiert.")
    o.append("5. **Lesen vor Analysieren.** Die Narrata-Oberflächen (Phase 5) kommen vor IT/OT (Phase 6) — ein importiertes Transkript muss erst nutzbar sein, bevor es klassifiziert wird; das Lesen deckt zudem Contract-Lücken auf, die TOOL-71 sonst zementiert.")
    o.append("6. **Das Kernziel kommt zuerst.** Innerhalb von Phase 5 stehen Suche und Chat/MCP (IOA-1220, IOA-1223) vor Lese-UI und Links: Sie hängen nur an IOA-1218 und machen das Transkript für den KI-Assistenten nutzbar.\n")
    o.append("## Meilensteine\n")
    o.append("| # | Meilenstein | Phase | Zeitraum | Tage |")
    o.append("|---|---|---|---|---|")
    for i, p in enumerate(phases):
        short = p["milestone"].split("—", 1)[1].split(".")[0].strip()
        o.append(f"| M{i} | {short} | {p['title'].split('—')[0].strip()} | {de(p['start'])} – {de(p['end'])} | {p['days']:g} |")
    o.append("")
    o.append("## Reflexionspunkte\n")
    o.append("| Nach | Frage | Ticket, das entscheidet | Was sich ändert |")
    o.append("|---|---|---|---|")
    o.append("| M1 | Braucht das Backend externe Segmentierung? | TOOL-62 | Beantwortet: nein, TOOL-11 und TOOL-33 verworfen; Phase 2 −2 Tage |")
    o.append("| M1 | Liefert Diarisierung stabile Labels? | TOOL-20 | Beantwortet: ja, pyannote hält 4 Labels für 4 Personen über 5 h, 8 % Fehlzuordnung in der Stichprobe; TOOL-68 bleibt bei 1 Tag |")
    o.append("| M1 | Liefert das ASR-Backend die Sprecher-Labels selbst? | TOOL-20 | Beantwortet: nein, separate Diarisierung mit pyannote; Integration als TOOL-76 (1,5 Tage) in Phase 2, M2 verschiebt sich entsprechend |")
    o.append("| M3 | Trägt der Contract den Import ohne Rückfragen? | IOA-1218 gegen TOOL-69 | Contract-Minor-Bump vor Phase 4, nicht danach |")
    o.append("| M4 | Trägt die Kernhypothese (Konfidenz grenzt Review ein)? Aufwand pro Abend alltagstauglich? | TOOL-60 | Go/No-Go Phase 6; Review-Kanal CSV vs. Narrata-UI (→ ggf. neues IOA-Ticket); TOOL-14 |")
    o.append("| Phase 6, Tag 2 | Reicht ein lokales LLM für IT/OT? Bringt der zweite Durchlauf messbar etwas? | TOOL-70 | TOOL-73 bleibt oder entfällt; ggf. Remote-Option |")
    o.append("| M7 | Welche Fragen aus der Zielliste sind jetzt beantwortbar, welche nicht? | Retro, kein Ticket | V0.2-Backlog beider Projekte |\n")
    o.append("## Arbeitsfolge\n")
    o.append("Start/Ende sind in Jira als Start date / Due date gespiegelt.\n")
    for p in phases:
        o.append(f"### {p['title']}\n")
        o.append(f"**{p['milestone']}**\n")
        o.append("| Ticket | Inhalt | Tage | Start | Ende | Hinweis |")
        o.append("|---|---|---|---|---|---|")
        for r in rows:
            if r["phase"] == p["title"]:
                o.append(f"| {r['key']} | {r['title']} | {r['days']:g} | {de(r['start'])} | {de(r['end'])} | {r['note']} |")
        o.append("")
    o.append("## Pflege\n")
    o.append("- `transcript-roadmap.py` ist die Quelle (Reihenfolge, Aufwände, Kapazität, Pausen); diese Datei und die Jira-Daten sind generiert. Ändern → Skript laufen lassen → Jira per `editJiraIssue` (`customfield_10015`, `duedate`) aus der JSON-Ausgabe nachziehen.")
    o.append("- Nach jedem Meilenstein `START`/Aufwände an die Realität anpassen und neu rechnen; nach M4 die Phasen 5–7 bewusst neu terminieren (Pilot-Erkenntnisse).")
    o.append("- Verworfene oder neu geschnittene Tickets im Skript entfernen bzw. ergänzen und den Grund im Jira-Ticket festhalten.")

    here = pathlib.Path(__file__).resolve().parent
    (here / "transcript-roadmap.md").write_text("\n".join(o) + "\n", encoding="utf-8")
    for r in rows:
        print(json.dumps({"key": r["key"], "start": r["start"].isoformat(), "end": r["end"].isoformat()}))


if __name__ == "__main__":
    main()
