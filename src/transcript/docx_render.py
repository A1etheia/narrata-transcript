"""The session's transcript as a Word document, rendered from the JSON export (TOOL-52).

The paragraphs come from `transcript.rendering`, the reading core shared with
TXT, so both show the same text, speakers and markers. The document adds a head
with the session key, ordinal, date and short pipeline metadata from the export.

The package is a minimal WordprocessingML file written with `zipfile`: content
types, relationships, `word/document.xml`, `word/styles.xml` and fixed core
properties. Every zip entry carries the same fixed time and the entries come in a
fixed order, so the same export and rule give the same bytes. Core properties
name no person, machine, path or time.

Speakers sit in the paragraph style `Speaker`; a label (not assigned, or
assigned without a name) gets the character style `SpeakerLabel` on top, so a
name and a label are told apart. Marker labels sit in runs of their own with
the character style `Marker`, never hidden. Text is escaped for XML; characters
XML 1.0 forbids are dropped, since a Word file cannot hold them.

The document holds transcript words and names; `write_docx` stores it as
`output/<s>/transcript.docx` and nothing here logs.
"""

import io
import re
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from xml.sax.saxutils import escape

from transcript.config import TimestampRule
from transcript.jsonfile import write_bytes_atomic
from transcript.rendering import Paragraph, Segment, SegmentKind, layout
from transcript.session import SessionKey, SessionPaths

# Characters outside XML 1.0's `Char` production
_NOT_XML = re.compile(r"[^\t\n\r\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")
# zipfile's earliest date; any fixed value keeps the bytes stable
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

_CONTENT_TYPES = (
    _HEAD
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/docProps/core.xml" '
    'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    "</Types>"
)

_PACKAGE_RELS = (
    _HEAD + f'<Relationships xmlns="{_PKG_REL}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
    'package/2006/relationships/metadata/core-properties" '
    'Target="docProps/core.xml"/>'
    "</Relationships>"
)

_DOCUMENT_RELS = (
    _HEAD + f'<Relationships xmlns="{_PKG_REL}">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

_CORE = (
    _HEAD + "<cp:coreProperties "
    'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
    'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
    "<dc:title>Transkript</dc:title>"
    "<dc:creator>narrata-transcript</dc:creator>"
    "<dc:language>de-DE</dc:language>"
    "</cp:coreProperties>"
)


def _paragraph_style(style_id: str, props: str, run_props: str) -> str:
    return (
        f'<w:style w:type="paragraph" w:styleId="{style_id}">'
        f'<w:name w:val="{style_id}"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        f"<w:pPr>{props}</w:pPr><w:rPr>{run_props}</w:rPr></w:style>"
    )


def _character_style(style_id: str, run_props: str) -> str:
    return (
        f'<w:style w:type="character" w:styleId="{style_id}">'
        f'<w:name w:val="{style_id}"/><w:rPr>{run_props}</w:rPr></w:style>'
    )


_STYLES = (
    _HEAD + f'<w:styles xmlns:w="{_W}">'
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" '
    'w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/>'
    '<w:lang w:val="de-DE"/></w:rPr></w:rPrDefault>'
    '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" '
    'w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/><w:qFormat/></w:style>'
    + _paragraph_style("Title", "", '<w:b/><w:sz w:val="40"/><w:szCs w:val="40"/>')
    + _paragraph_style(
        "Subtitle",
        '<w:spacing w:after="240"/>',
        '<w:color w:val="404040"/><w:sz w:val="26"/><w:szCs w:val="26"/>',
    )
    + _paragraph_style(
        "Meta",
        '<w:spacing w:after="0"/>',
        '<w:color w:val="666666"/><w:sz w:val="18"/><w:szCs w:val="18"/>',
    )
    + _paragraph_style(
        "Speaker", '<w:keepNext/><w:spacing w:before="240" w:after="60"/>', "<w:b/>"
    )
    + _character_style("SpeakerLabel", '<w:i/><w:color w:val="555555"/>')
    + _character_style(
        "Marker", '<w:i/><w:color w:val="8B0000"/><w:highlight w:val="lightGray"/>'
    )
    + _character_style("Time", '<w:color w:val="808080"/>')
    + "</w:styles>"
)

# A4, margins of 2.5 cm
_SECTION = (
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1417" w:right="1417" w:bottom="1134" w:left="1417" '
    'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
)

# The character style of each kind of segment; text and names stay plain
_RUN_STYLES: dict[SegmentKind, str | None] = {
    "time": "Time",
    "name": None,
    "label": "SpeakerLabel",
    "text": None,
    "marker": "Marker",
}


def render_docx(
    key: SessionKey,
    document: Mapping[str, Any],
    found: Sequence[Paragraph],
    rule: TimestampRule,
) -> bytes:
    """The head and paragraphs of a valid export as DOCX bytes."""
    body = _head(key, document)
    for block in layout(found, rule):
        body.append(_paragraph("Speaker", block.head))
        body.extend(_paragraph(None, row) for row in block.rows)
    xml = (
        _HEAD
        + f'<w:document xmlns:w="{_W}" xmlns:r="{_REL}"><w:body>'
        + "".join(body)
        + _SECTION
        + "</w:body></w:document>"
    )
    return _package(
        (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _PACKAGE_RELS),
            ("docProps/core.xml", _CORE),
            ("word/_rels/document.xml.rels", _DOCUMENT_RELS),
            ("word/styles.xml", _STYLES),
            ("word/document.xml", xml),
        )
    )


def write_docx(paths: SessionPaths, data: bytes) -> None:
    """Replace the session's DOCX transcript."""
    write_bytes_atomic(paths.transcript_document, data)


def _head(key: SessionKey, document: Mapping[str, Any]) -> list[str]:
    session = document["session"]
    pipeline = document["pipeline"]
    played = session["session_date"]
    subtitle = f"Sitzung {session['ordinal']}"
    if played is not None:
        subtitle += f" · {date.fromisoformat(played):%d.%m.%Y}"
    snapshot = pipeline["knowledge_snapshot_id"]
    narrata = f"Gruppe {session['group']}, Spielsitzung {session['play_session_id']}"
    meta = (
        f"Backend: {pipeline['backend']} / {pipeline['model']}",
        f"Wissens-Snapshot: {'keiner' if snapshot is None else snapshot}",
        f"Contract: {document['contract_version']}",
        f"Narrata: {narrata}",
    )
    return [
        _paragraph("Title", (Segment(f"Transkript {key}", "text"),)),
        _paragraph("Subtitle", (Segment(subtitle, "text"),)),
        *(_paragraph("Meta", (Segment(line, "text"),)) for line in meta),
    ]


def _paragraph(style: str | None, segments: Sequence[Segment]) -> str:
    """The segments as styled runs, a plain space run between two, as in TXT."""
    props = "" if style is None else f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
    runs = []
    for segment in segments:
        if runs:
            runs.append(_run(" ", None))
        runs.append(_run(segment.text, _RUN_STYLES[segment.kind]))
    return f"<w:p>{props}{''.join(runs)}</w:p>"


def _run(text: str, style: str | None) -> str:
    props = "" if style is None else f'<w:rPr><w:rStyle w:val="{style}"/></w:rPr>'
    safe = escape(_NOT_XML.sub("", text))
    return f'<w:r>{props}<w:t xml:space="preserve">{safe}</w:t></w:r>'


def _package(parts: Sequence[tuple[str, str]]) -> bytes:
    """The parts zipped in order, each with the same fixed time and mode."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return buffer.getvalue()
