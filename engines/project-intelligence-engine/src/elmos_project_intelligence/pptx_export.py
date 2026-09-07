"""Deterministic PPTX writer for Project Intelligence exports.

The engine has no third-party dependencies, so this writes the OOXML package
itself with ``zipfile``.  Two properties matter and are both enforced here:

* **Vector, not raster.**  The diagram is emitted as native DrawingML shapes --
  preset flowchart geometries for nodes and ``custGeom`` paths for edges --
  taken from the same :mod:`diagram_layout` geometry the SVG uses.  Nothing is
  rasterised, so the picture stays sharp at any zoom and the text stays real
  text.
* **Deterministic bytes.**  Every zip entry uses a fixed timestamp and fixed
  external attributes, entries are written in a fixed order, and no clock,
  locale, or random identifier reaches the XML.  Two runs on the same inputs
  produce byte-identical files.

This module is *not* reachable from skill dispatch.  ``generate_presentation``
stays a manifest-only handler whose ``pptx_generated`` output is pinned False
by the qualification contract; producing a file is an explicit offline export
performed by the CLI after dispatch has returned.
"""

from __future__ import annotations

from dataclasses import dataclass
import zipfile
from typing import Any, Iterable, Mapping, Sequence

from .diagram_layout import DiagramLayout, LaidOutNode, sanitize_label
from .diagram_svg import escape_xml_text


EMU_PER_INCH = 914400
EMU_PER_PIXEL = 9525  # 96 dpi
EMU_PER_POINT = 12700
#: Smallest run size OOXML allows, in hundredths of a point.
MIN_FONT_HUNDREDTHS = 100
SLIDE_WIDTH = 12192000
SLIDE_HEIGHT = 6858000
CONTENT_LEFT = 457200
CONTENT_TOP = 1143000
CONTENT_WIDTH = SLIDE_WIDTH - CONTENT_LEFT * 2
CONTENT_HEIGHT = SLIDE_HEIGHT - CONTENT_TOP - 457200

#: Fixed zip timestamp.  1980-01-01 is the earliest value the zip format can
#: represent, which keeps the archive reproducible without a clock.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

_PRESET_BY_KIND = {
    "start": "flowChartTerminator",
    "end": "flowChartTerminator",
    "decision": "flowChartDecision",
    "loop": "flowChartPredefinedProcess",
    "merge": "flowChartConnector",
}
_FILL_BY_KIND = {
    "start": "E3F0E4",
    "end": "E3F0E4",
    "decision": "FDF3D8",
    "loop": "E9E6F6",
    "merge": "E3F0E4",
}
_DEFAULT_PRESET = "roundRect"
_DEFAULT_FILL = "EEF2F8"
_LINE_COLOR = "33455C"
_TEXT_COLOR = "1D2733"

_NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
_XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


class PptxExportError(ValueError):
    """The presentation cannot be built."""


@dataclass(frozen=True)
class BulletSlide:
    title: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class DiagramSlide:
    title: str
    layout: DiagramLayout


def _empty_tree() -> str:
    return (
        "<p:spTree>"
        '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
        '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    )


def _text_body(
    text_runs: Sequence[tuple[str, int, bool]],
    *,
    anchor: str = "t",
    align: str = "l",
    bullet: bool = False,
) -> str:
    paragraphs = []
    for content, size, bold in text_runs:
        marker = "" if bullet else "<a:buNone/>"
        paragraphs.append(
            f'<a:p><a:pPr algn="{align}">{marker}</a:pPr>'
            f'<a:r><a:rPr lang="en-US" sz="{size}" b="{1 if bold else 0}" dirty="0">'
            f'<a:solidFill><a:srgbClr val="{_TEXT_COLOR}"/></a:solidFill>'
            f"</a:rPr><a:t>{escape_xml_text(content)}</a:t></a:r></a:p>"
        )
    if not paragraphs:
        paragraphs.append("<a:p><a:endParaRPr lang=\"en-US\"/></a:p>")
    return (
        f'<p:txBody><a:bodyPr wrap="square" anchor="{anchor}"><a:normAutofit/></a:bodyPr>'
        f"<a:lstStyle/>{''.join(paragraphs)}</p:txBody>"
    )


def _textbox(
    shape_id: int,
    name: str,
    box: tuple[int, int, int, int],
    text_runs: Sequence[tuple[str, int, bool]],
    *,
    anchor: str = "t",
    align: str = "l",
    bullet: bool = False,
) -> str:
    x, y, cx, cy = box
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape_xml_text(name)}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
        + _text_body(text_runs, anchor=anchor, align=align, bullet=bullet)
        + "</p:sp>"
    )


def _node_shape(
    shape_id: int,
    node: LaidOutNode,
    *,
    origin_x: int,
    origin_y: int,
    scale: int,
    font_size: int,
) -> str:
    preset = _PRESET_BY_KIND.get(node.kind, _DEFAULT_PRESET)
    fill = _FILL_BY_KIND.get(node.kind, _DEFAULT_FILL)
    x = origin_x + node.x * scale
    y = origin_y + node.y * scale
    cx = max(node.width * scale, 1)
    cy = max(node.height * scale, 1)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" '
        f'name="{escape_xml_text(node.element_id)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
        f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="{preset}"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
        f'<a:ln w="19050"><a:solidFill><a:srgbClr val="{_LINE_COLOR}"/></a:solidFill></a:ln>'
        "</p:spPr>"
        + _text_body(
            [(node.label, font_size, False)], anchor="ctr", align="ctr"
        )
        + "</p:sp>"
    )


def _paths(
    polylines: Iterable[Sequence[tuple[int, int]]],
    *,
    width: int,
    height: int,
    scale: int,
    close: bool,
) -> str:
    fragments = []
    for polyline in polylines:
        if len(polyline) < 2:
            continue
        first_x, first_y = polyline[0]
        steps = [f'<a:moveTo><a:pt x="{first_x * scale}" y="{first_y * scale}"/></a:moveTo>']
        for point_x, point_y in polyline[1:]:
            steps.append(
                f'<a:lnTo><a:pt x="{point_x * scale}" y="{point_y * scale}"/></a:lnTo>'
            )
        if close:
            steps.append("<a:close/>")
        fill_mode = "norm" if close else "none"
        fragments.append(
            f'<a:path w="{width}" h="{height}" fill="{fill_mode}" stroke="1">'
            + "".join(steps)
            + "</a:path>"
        )
    return "".join(fragments)


def _geometry_shape(
    shape_id: int,
    name: str,
    polylines: Sequence[Sequence[tuple[int, int]]],
    *,
    origin_x: int,
    origin_y: int,
    frame_width: int,
    frame_height: int,
    scale: int,
    filled: bool,
) -> str:
    """One custGeom shape holding many subpaths.

    Every edge shape uses the whole diagram frame as its bounding box.  That
    removes the degenerate zero-width/zero-height box a straight vertical or
    horizontal connector would otherwise produce, which some renderers reject.
    """

    body = _paths(
        polylines,
        width=frame_width,
        height=frame_height,
        scale=scale,
        close=filled,
    )
    if not body:
        return ""
    if filled:
        style = (
            f'<a:solidFill><a:srgbClr val="{_LINE_COLOR}"/></a:solidFill>'
            "<a:ln><a:noFill/></a:ln>"
        )
    else:
        style = (
            "<a:noFill/>"
            f'<a:ln w="19050" cap="flat"><a:solidFill>'
            f'<a:srgbClr val="{_LINE_COLOR}"/></a:solidFill></a:ln>'
        )
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape_xml_text(name)}"/>'
        "<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
        f'<p:spPr><a:xfrm><a:off x="{origin_x}" y="{origin_y}"/>'
        f'<a:ext cx="{frame_width}" cy="{frame_height}"/></a:xfrm>'
        "<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>"
        f'<a:rect l="0" t="0" r="{frame_width}" b="{frame_height}"/>'
        f"<a:pathLst>{body}</a:pathLst></a:custGeom>"
        f"{style}</p:spPr>"
        "<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody>"
        "</p:sp>"
    )


def _diagram_slide_xml(slide: DiagramSlide) -> str:
    layout = slide.layout
    scale = min(
        CONTENT_WIDTH // max(layout.width, 1),
        CONTENT_HEIGHT // max(layout.height, 1),
        EMU_PER_PIXEL,
    )
    if scale < 1:
        raise PptxExportError("diagram is too large to place on a slide")
    frame_width = layout.width * scale
    frame_height = layout.height * scale
    origin_x = CONTENT_LEFT + (CONTENT_WIDTH - frame_width) // 2
    origin_y = CONTENT_TOP + (CONTENT_HEIGHT - frame_height) // 2
    # Font size tracks the diagram scale exactly.  A minimum readable floor was
    # tried and rejected: on a wide graph the floored text no longer fits its
    # shape and LibreOffice's autofit drops the run entirely, so a legibility
    # tweak silently deleted every node label.  MIN_FONT_HUNDREDTHS is the
    # OOXML minimum, not a design choice.
    font_size = max(MIN_FONT_HUNDREDTHS, min(2400, 13 * scale * 100 // EMU_PER_POINT))
    edge_font_size = max(
        MIN_FONT_HUNDREDTHS, min(2400, 11 * scale * 100 // EMU_PER_POINT)
    )

    shapes = [
        _textbox(
            2,
            "title",
            (CONTENT_LEFT, 365760, CONTENT_WIDTH, 640080),
            [(slide.title, 2400, True)],
        )
    ]
    shapes.append(
        _geometry_shape(
            3,
            "diagram-edges",
            [edge.points for edge in layout.edges],
            origin_x=origin_x,
            origin_y=origin_y,
            frame_width=frame_width,
            frame_height=frame_height,
            scale=scale,
            filled=False,
        )
    )
    shapes.append(
        _geometry_shape(
            4,
            "diagram-arrows",
            [edge.arrow for edge in layout.edges],
            origin_x=origin_x,
            origin_y=origin_y,
            frame_width=frame_width,
            frame_height=frame_height,
            scale=scale,
            filled=True,
        )
    )
    next_id = 5
    for node in layout.nodes:
        shapes.append(
            _node_shape(
                next_id,
                node,
                origin_x=origin_x,
                origin_y=origin_y,
                scale=scale,
                font_size=font_size,
            )
        )
        next_id += 1
    for edge in layout.edges:
        if not edge.label or edge.label_anchor is None:
            continue
        anchor_x, anchor_y = edge.label_anchor
        shapes.append(
            _textbox(
                next_id,
                f"{edge.element_id}-label",
                (
                    origin_x + anchor_x * scale,
                    origin_y + anchor_y * scale - 10 * scale,
                    max(len(edge.label) * 8 * scale, 1),
                    max(18 * scale, 1),
                ),
                [(edge.label, edge_font_size, False)],
                anchor="ctr",
            )
        )
        next_id += 1
    return _slide_document("".join(shape for shape in shapes if shape))


def _bullet_slide_xml(slide: BulletSlide) -> str:
    shapes = [
        _textbox(
            2,
            "title",
            (CONTENT_LEFT, 365760, CONTENT_WIDTH, 640080),
            [(slide.title, 2800, True)],
        ),
        _textbox(
            3,
            "body",
            (CONTENT_LEFT, CONTENT_TOP, CONTENT_WIDTH, CONTENT_HEIGHT),
            [(bullet, 1800, False) for bullet in slide.bullets],
            bullet=True,
        ),
    ]
    return _slide_document("".join(shapes))


def _slide_document(shapes_xml: str) -> str:
    return (
        _XML_HEADER
        + f"<p:sld {_NS}><p:cSld>"
        + _empty_tree()
        + shapes_xml
        + "</p:spTree></p:cSld>"
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'
    )


def _theme_xml() -> str:
    colors = (
        ("dk1", "sysClr", 'lastClr="000000" val="windowText"'),
        ("lt1", "sysClr", 'lastClr="FFFFFF" val="window"'),
        ("dk2", "srgbClr", 'val="44546A"'),
        ("lt2", "srgbClr", 'val="E7E6E6"'),
        ("accent1", "srgbClr", 'val="4472C4"'),
        ("accent2", "srgbClr", 'val="ED7D31"'),
        ("accent3", "srgbClr", 'val="A5A5A5"'),
        ("accent4", "srgbClr", 'val="FFC000"'),
        ("accent5", "srgbClr", 'val="5B9BD5"'),
        ("accent6", "srgbClr", 'val="70AD47"'),
        ("hlink", "srgbClr", 'val="0563C1"'),
        ("folHlink", "srgbClr", 'val="954F72"'),
    )
    scheme = "".join(
        f"<a:{name}><a:{tag} {attrs}/></a:{name}>" for name, tag, attrs in colors
    )
    fonts = (
        "<a:fontScheme name=\"Office\">"
        '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/>'
        '<a:cs typeface=""/></a:majorFont>'
        '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/>'
        '<a:cs typeface=""/></a:minorFont></a:fontScheme>'
    )
    solid = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    line = (
        '<a:ln w="6350" cap="flat" cmpd="sng" algn="ctr">'
        + solid
        + '<a:prstDash val="solid"/></a:ln>'
    )
    formats = (
        '<a:fmtScheme name="Office">'
        f"<a:fillStyleLst>{solid}{solid}{solid}</a:fillStyleLst>"
        f"<a:lnStyleLst>{line}{line}{line}</a:lnStyleLst>"
        "<a:effectStyleLst>"
        "<a:effectStyle><a:effectLst/></a:effectStyle>"
        "<a:effectStyle><a:effectLst/></a:effectStyle>"
        "<a:effectStyle><a:effectLst/></a:effectStyle>"
        "</a:effectStyleLst>"
        f"<a:bgFillStyleLst>{solid}{solid}{solid}</a:bgFillStyleLst>"
        "</a:fmtScheme>"
    )
    return (
        _XML_HEADER
        + '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'name="Elmos Project Intelligence"><a:themeElements>'
        f'<a:clrScheme name="Office">{scheme}</a:clrScheme>{fonts}{formats}'
        "</a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>"
    )


def _package_parts(
    slides_xml: Sequence[str], *, title: str
) -> list[tuple[str, str]]:
    relationships = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    slide_ids = "".join(
        f'<p:sldId id="{256 + index}" r:id="rId{index + 2}"/>'
        for index in range(len(slides_xml))
    )
    presentation = (
        _XML_HEADER
        + f'<p:presentation {_NS} saveSubsetFonts="1">'
        '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
        f"<p:sldIdLst>{slide_ids}</p:sldIdLst>"
        f'<p:sldSz cx="{SLIDE_WIDTH}" cy="{SLIDE_HEIGHT}"/>'
        '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    )
    presentation_rels = [
        f'<Relationship Id="rId1" Type="{relationships}/slideMaster" '
        'Target="slideMasters/slideMaster1.xml"/>'
    ]
    for index in range(len(slides_xml)):
        presentation_rels.append(
            f'<Relationship Id="rId{index + 2}" Type="{relationships}/slide" '
            f'Target="slides/slide{index + 1}.xml"/>'
        )
    presentation_rels.append(
        f'<Relationship Id="rId{len(slides_xml) + 2}" Type="{relationships}/theme" '
        'Target="theme/theme1.xml"/>'
    )

    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
    ]
    for index in range(len(slides_xml)):
        content_types.append(
            f'<Override PartName="/ppt/slides/slide{index + 1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    content_types.append(
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    )
    content_types.append(
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    )
    content_types.append("</Types>")

    root_rels = (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{relationships}/officeDocument" Target="ppt/presentation.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        f'<Relationship Id="rId3" Type="{relationships}/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    master = (
        _XML_HEADER
        + f"<p:sldMaster {_NS}><p:cSld>"
        + _empty_tree()
        + "</p:spTree></p:cSld>"
        '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
        'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" '
        'accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
        '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
        "</p:sldMaster>"
    )
    master_rels = (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{relationships}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        f'<Relationship Id="rId2" Type="{relationships}/theme" Target="../theme/theme1.xml"/>'
        "</Relationships>"
    )
    slide_layout = (
        _XML_HEADER
        + f'<p:sldLayout {_NS} type="blank" preserve="1"><p:cSld name="Blank">'
        + _empty_tree()
        + "</p:spTree></p:cSld>"
        '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'
    )
    slide_layout_rels = (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{relationships}/slideMaster" Target="../slideMasters/slideMaster1.xml"/>'
        "</Relationships>"
    )
    slide_rels = (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="{relationships}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        "</Relationships>"
    )
    core = (
        _XML_HEADER
        + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape_xml_text(title)}</dc:title>"
        "<dc:creator>elmos-project-intelligence-engine</dc:creator>"
        "<cp:lastModifiedBy>elmos-project-intelligence-engine</cp:lastModifiedBy>"
        '<dcterms:created xsi:type="dcterms:W3CDTF">1980-01-01T00:00:00Z</dcterms:created>'
        '<dcterms:modified xsi:type="dcterms:W3CDTF">1980-01-01T00:00:00Z</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        _XML_HEADER
        + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>elmos-project-intelligence-engine</Application>"
        f"<Slides>{len(slides_xml)}</Slides>"
        "<ScaleCrop>false</ScaleCrop><LinksUpToDate>false</LinksUpToDate>"
        "<SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged>"
        "</Properties>"
    )

    parts: list[tuple[str, str]] = [
        ("[Content_Types].xml", _XML_HEADER + "".join(content_types[1:])),
        ("_rels/.rels", root_rels),
        ("docProps/app.xml", app),
        ("docProps/core.xml", core),
        ("ppt/presentation.xml", presentation),
        (
            "ppt/_rels/presentation.xml.rels",
            _XML_HEADER
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(presentation_rels)
            + "</Relationships>",
        ),
        ("ppt/slideMasters/slideMaster1.xml", master),
        ("ppt/slideMasters/_rels/slideMaster1.xml.rels", master_rels),
        ("ppt/slideLayouts/slideLayout1.xml", slide_layout),
        ("ppt/slideLayouts/_rels/slideLayout1.xml.rels", slide_layout_rels),
        ("ppt/theme/theme1.xml", _theme_xml()),
    ]
    for index, slide_xml in enumerate(slides_xml):
        parts.append((f"ppt/slides/slide{index + 1}.xml", slide_xml))
        parts.append((f"ppt/slides/_rels/slide{index + 1}.xml.rels", slide_rels))
    return parts


def build_pptx(
    slides: Sequence[BulletSlide | DiagramSlide], *, title: str = "Project Intelligence"
) -> bytes:
    """Return a deterministic PPTX package for the given slides."""

    if not slides:
        raise PptxExportError("a presentation needs at least one slide")
    slides_xml = [
        _diagram_slide_xml(slide)
        if isinstance(slide, DiagramSlide)
        else _bullet_slide_xml(slide)
        for slide in slides
    ]
    safe_title, _ = sanitize_label(title)
    parts = _package_parts(slides_xml, title=safe_title)

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 0
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def slides_from_manifest(manifest: Mapping[str, Any]) -> list[BulletSlide]:
    """Convert a ``generate_presentation`` manifest into bullet slides."""

    raw_slides = manifest.get("slides")
    if not isinstance(raw_slides, Sequence) or isinstance(raw_slides, (str, bytes)):
        raise PptxExportError("presentation manifest needs a slides array")
    slides: list[BulletSlide] = []
    for entry in raw_slides:
        if not isinstance(entry, Mapping):
            raise PptxExportError("presentation manifest slides must be objects")
        title, _ = sanitize_label(entry.get("title", "Slide"))
        raw_bullets = entry.get("bullets", [])
        if not isinstance(raw_bullets, Sequence) or isinstance(
            raw_bullets, (str, bytes)
        ):
            raise PptxExportError("presentation manifest bullets must be an array")
        bullets = tuple(sanitize_label(item)[0] for item in raw_bullets)
        slides.append(BulletSlide(title=title, bullets=bullets))
    return slides
