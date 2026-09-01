"""Offline diagram/presentation export: determinism, geometry, and boundaries."""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree

from elmos_project_intelligence import cli
from elmos_project_intelligence.diagram_html import ReportSection, render_report
from elmos_project_intelligence.diagram_layout import (
    MERMAID_LABEL_PUNCTUATION,
    DiagramLayoutError,
    layout_diagram,
    sanitize_label,
)
from elmos_project_intelligence.diagram_svg import escape_xml_text, render_svg
from elmos_project_intelligence.domain import _safe_mermaid_label
from elmos_project_intelligence.export_cli import digest_bytes, extract_diagram_spec
from elmos_project_intelligence.pptx_export import (
    BulletSlide,
    DiagramSlide,
    build_pptx,
    slides_from_manifest,
)
from elmos_project_intelligence.runtime import dispatch_skill

from test_runtime import request


def simple_spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "diagram_id": "sha256:" + "0" * 64,
        "type": "flow",
        "project_id": "project-a",
        "revision_id": "abc123",
        "title": "Refund flow",
        "nodes": [
            {"id": "start", "kind": "start", "label": "start"},
            {"id": "check", "kind": "decision", "label": "is refundable"},
            {"id": "pay", "kind": "process", "label": "issue refund"},
            {"id": "loop", "kind": "loop", "label": "retry batch"},
            {"id": "done", "kind": "end", "label": "done"},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "check", "kind": "next"},
            {"id": "e2", "source": "check", "target": "pay", "kind": "yes",
             "label": "yes"},
            {"id": "e3", "source": "pay", "target": "loop", "kind": "next"},
            {"id": "e4", "source": "loop", "target": "done", "kind": "next"},
            # cycle-closing edge: the layering must not inflate on it
            {"id": "e5", "source": "loop", "target": "check", "kind": "retry"},
            {"id": "e6", "source": "loop", "target": "loop", "kind": "self"},
        ],
    }


def wide_cyclic_spec(width: int = 24) -> dict[str, object]:
    nodes: list[dict[str, object]] = [
        {"id": "root", "kind": "start", "label": "ingest gateway"}
    ]
    edges: list[dict[str, object]] = []
    for index in range(width):
        node_id = f"svc{index:02d}"
        nodes.append(
            {"id": node_id, "kind": "service", "label": f"handler module {index:02d}"}
        )
        edges.append(
            {"id": f"in{index}", "source": "root", "target": node_id, "kind": "calls"}
        )
        edges.append(
            {"id": f"out{index}", "source": node_id, "target": "sink", "kind": "writes"}
        )
    nodes.append({"id": "sink", "kind": "database", "label": "audit store"})
    edges.append({"id": "back", "source": "sink", "target": "root", "kind": "retries"})
    return {
        "schema_version": 1,
        "diagram_id": "sha256:" + "1" * 64,
        "type": "component",
        "project_id": "project-a",
        "revision_id": "abc123",
        "nodes": nodes,
        "edges": edges,
    }


#: The corpus the two sanitisers used to be compared on byte-for-byte.  It is
#: kept, and both rules are still run over it -- the assertions changed, the
#: inputs did not.
SANITIZER_CORPUS = [
    'Refund API"]\n  attacker["injected"]',
    "<script>alert(1)</script>",
    "total = item",
    "a -> b",
    "  spaced   out  ",
    "x" * 400,
    "",
    "重构 refund",
    "%%{init: {\"securityLevel\": \"loose\"}}%%",
]


class LabelSanitizerTests(unittest.TestCase):
    """The two sanitisers are deliberately different, and constrained anyway.

    ``sanitize_label`` (SVG/OOXML) and ``domain._safe_mermaid_label`` (Mermaid)
    used to be pinned byte-for-byte to each other.  That single assertion was
    doing two jobs: it pinned each rule, and it caught the two drifting apart.
    Widening the export side for readable control-flow labels makes the
    equality false, but the *intent* -- "these two cannot diverge without a
    test noticing" -- has to survive, so it is now carried by four assertions
    instead of one:

    1. the Mermaid rule is pinned to its own explicit character set;
    2. the export rule is pinned to its own explicit character set;
    3. the export set is a **superset** of the Mermaid set, over a full sweep
       of the Basic Multilingual Plane -- so neither "Mermaid was widened" nor
       "the exporter was narrowed" can pass unnoticed;
    4. neither rule ever keeps a character that is unsafe *after* escaping.

    Divergence is still caught.  What is no longer required is that the two be
    identical, which was never the property anyone wanted -- it was the
    cheapest way to express it when both sets happened to be equal.
    """

    #: Sampled once and reused: every code point of the BMP except the
    #: surrogate range, which cannot appear in a well-formed ``str`` scalar.
    SWEEP = [
        chr(code)
        for code in range(0x10000)
        if not 0xD800 <= code <= 0xDFFF
    ] + ["\U0001F600", "\U0001F4CA", "\U000E0001"]

    def test_the_mermaid_rule_is_pinned_to_its_own_character_set(self) -> None:
        """Mermaid's allowlist is its only defence, so it is pinned exactly.

        Nothing about widening the exporter may widen this.
        """

        kept = {c for c in self.SWEEP if _safe_mermaid_label(c)[0] == c}
        expected = {
            c
            for c in self.SWEEP
            if c.isalnum() or c in MERMAID_LABEL_PUNCTUATION
        }
        # ``" "`` survives as itself but a lone space collapses to "node"; take
        # the character set from the rule, not from the whole-string helper.
        self.assertEqual(kept - {" "}, expected - {" "})
        for forbidden in ("<", ">", "&", '"', "'", "[", "]", "{", "}", "=", "%"):
            with self.subTest(character=forbidden):
                self.assertNotIn(forbidden, kept)

    def test_the_export_rule_is_pinned_to_its_own_character_set(self) -> None:
        kept = {c for c in self.SWEEP if sanitize_label(c)[0] == c}
        expected = {c for c in self.SWEEP if c.isprintable()}
        self.assertEqual(kept - {" "}, expected - {" "})
        for wanted in ("<", ">", "&", '"', "'", "[", "]", "{", "}", "=", "%", "*", "+"):
            with self.subTest(character=wanted):
                self.assertIn(wanted, kept)

    def test_the_export_rule_is_a_superset_of_the_mermaid_rule(self) -> None:
        """The relation the old equality assertion was really protecting.

        If Mermaid is ever widened, or the exporter ever narrowed, this fails.
        """

        mermaid_kept = {c for c in self.SWEEP if _safe_mermaid_label(c)[0] == c}
        export_kept = {c for c in self.SWEEP if sanitize_label(c)[0] == c}
        missing = sorted(mermaid_kept - export_kept)
        self.assertEqual(
            missing,
            [],
            f"the exporter drops {len(missing)} character(s) Mermaid keeps: "
            f"{missing[:10]}",
        )
        self.assertTrue(
            export_kept - mermaid_kept,
            "the two rules are identical again; either the widening was "
            "reverted or Mermaid was widened to match it",
        )

    def test_neither_rule_keeps_a_character_that_escaping_cannot_make_safe(
        self,
    ) -> None:
        """Control, format, surrogate and unassigned code points.

        XML escaping does nothing about a bidirectional override or a
        zero-width space, and a C0 control character is illegal in XML 1.0 text
        even escaped.  Both rules must drop them outright.
        """

        dangerous = [
            "\x00", "\x07", "\x08", "\x0b", "\x0c", "\x1b", "\x7f",  # controls
            "\u202e", "\u202d", "\u200f",  # bidi overrides
            "\u200b", "\u200d", "\ufeff",  # zero width
            "\u00a0", "\u2028", "\u2029",  # non-standard spaces / separators
            "\ufffe",  # noncharacter
        ]
        for character in dangerous:
            with self.subTest(codepoint=hex(ord(character))):
                self.assertNotIn(character, sanitize_label(f"a{character}b")[0])
                self.assertNotIn(character, _safe_mermaid_label(f"a{character}b")[0])

    def test_both_rules_still_bound_and_collapse_the_shared_corpus(self) -> None:
        """The properties the old equality test also happened to cover."""

        for value in SANITIZER_CORPUS:
            with self.subTest(value=value[:24]):
                for rule, text in (
                    ("export", sanitize_label(value)[0]),
                    ("mermaid", _safe_mermaid_label(value)[0]),
                ):
                    self.assertLessEqual(len(text), 160, rule)
                    self.assertNotIn("\n", text, rule)
                    self.assertNotIn("  ", text, rule)
                    self.assertTrue(text, rule)

    def test_mermaid_still_dismantles_the_injection_corpus(self) -> None:
        """Widening the exporter must not have touched the Mermaid path."""

        self.assertEqual(
            _safe_mermaid_label('Refund API"]\n  attacker["injected"]')[0],
            "Refund API attacker injected",
        )
        self.assertEqual(
            _safe_mermaid_label("<script>alert(1)</script>")[0], "script alert(1) script"
        )
        # The same two strings survive the exporter intact, which is the whole
        # point of the widening -- and is only safe because they get escaped.
        self.assertEqual(
            sanitize_label("<script>alert(1)</script>")[0], "<script>alert(1)</script>"
        )

    def test_xml_escaper_neutralises_markup_on_unsanitized_input(self) -> None:
        escaped = escape_xml_text("<a href='x' title=\"y\">&</a>")
        for character in ("<", ">", "'", '"'):
            self.assertNotIn(character, escaped)
        self.assertIn("&lt;", escaped)
        self.assertIn("&amp;", escaped)


class LayoutTests(unittest.TestCase):
    def test_every_shape_stays_inside_the_canvas_on_a_cyclic_spec(self) -> None:
        """Regression: a cycle used to inflate layer numbers.

        The canvas height came from the number of occupied layers while node
        ``y`` came from the raw layer number, so once a cycle opened a gap the
        shapes were placed far below the canvas and rendered nowhere.
        """

        for spec in (simple_spec(), wide_cyclic_spec()):
            with self.subTest(nodes=len(spec["nodes"])):  # type: ignore[arg-type]
                layout = layout_diagram(spec)
                for node in layout.nodes:
                    self.assertGreaterEqual(node.x, 0)
                    self.assertGreaterEqual(node.y, 0)
                    self.assertLessEqual(node.x + node.width, layout.width)
                    self.assertLessEqual(node.y + node.height, layout.height)
                for edge in layout.edges:
                    for point_x, point_y in edge.points + edge.arrow:
                        self.assertGreaterEqual(point_x, 0)
                        self.assertGreaterEqual(point_y, 0)
                        self.assertLessEqual(point_x, layout.width)
                        self.assertLessEqual(point_y, layout.height)

    def test_layer_ranks_are_dense_and_bounded_by_the_node_count(self) -> None:
        layout = layout_diagram(wide_cyclic_spec())
        ranks = sorted({node.layer for node in layout.nodes})
        self.assertEqual(ranks, list(range(len(ranks))))
        self.assertLessEqual(max(ranks), len(layout.nodes))

    def test_dangling_edge_and_empty_node_list_are_rejected(self) -> None:
        spec = simple_spec()
        spec["edges"] = [
            {"id": "x", "source": "start", "target": "missing", "kind": "next"}
        ]
        with self.assertRaises(DiagramLayoutError):
            layout_diagram(spec)
        empty = simple_spec()
        empty["nodes"] = []
        empty["edges"] = []
        with self.assertRaises(DiagramLayoutError):
            layout_diagram(empty)

    def test_layout_is_pure_integer_geometry(self) -> None:
        layout = layout_diagram(simple_spec())
        for node in layout.nodes:
            for value in (node.x, node.y, node.width, node.height):
                self.assertIsInstance(value, int)


#: A label built only from characters the widened export rule newly admits.
#: Before the widening ``sanitize_label`` deleted all of them, so the injection
#: tests below passed without the escaper ever being consulted; they were
#: green for the wrong reason.  Now the payload arrives at the escaper intact
#: and those tests measure the escaper, which is what they always claimed to.
INJECTION_LABEL = '</text></svg><script>alert(1)</script><svg x="&\'y\'"'


class WidenedAllowlistInjectionTests(unittest.TestCase):
    """Negative control for the widening: newly admitted markup must be inert.

    Two things have to hold together, and each is asserted separately, because
    only one of them was true before:

    1. the payload **survives sanitising** -- if it did not, everything below
       would be green because the characters were deleted, which is exactly the
       state this widening left behind;
    2. the payload is **dead in every rendered artefact** -- SVG, HTML report
       and PPTX -- which can now only be the escaper's doing.

    Checked against a build with ``escape_xml_text`` reduced to the identity
    function: every assertion in this class fails.
    """

    def test_the_payload_actually_reaches_the_renderer(self) -> None:
        """Assertion 1.  Without this the rest proves nothing."""

        sanitized, changed = sanitize_label(INJECTION_LABEL)
        self.assertEqual(sanitized, INJECTION_LABEL)
        self.assertFalse(changed)
        for character in ("<", ">", "&", '"', "'", "/"):
            self.assertIn(character, sanitized)

    def _spec_with_payload(self) -> dict[str, object]:
        spec = simple_spec()
        spec["nodes"][0]["label"] = INJECTION_LABEL  # type: ignore[index]
        return spec

    def test_it_is_inert_in_the_svg(self) -> None:
        svg = render_svg(layout_diagram(self._spec_with_payload()))
        self.assertIn("&lt;script&gt;", svg)
        self.assertNotIn("<script", svg)
        self.assertNotIn("</text><", svg)
        self.assertEqual(svg.count("</svg>"), 1)
        self.assertEqual(svg.count("<text"), svg.count("</text>"))

    def test_it_is_inert_in_the_html_report(self) -> None:
        layout = layout_diagram(self._spec_with_payload())
        svg = render_svg(layout)
        html = render_report(
            [
                ReportSection(
                    heading=INJECTION_LABEL,
                    layout=layout,
                    svg=svg,
                    svg_digest=digest_bytes(svg.encode("utf-8")),
                )
            ],
            title=INJECTION_LABEL,
            project_id=INJECTION_LABEL,
            revision_id=INJECTION_LABEL,
        )
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("</svg><svg x=", html)

    def test_it_is_inert_in_the_pptx(self) -> None:
        layout = layout_diagram(self._spec_with_payload())
        payload = build_pptx(
            [DiagramSlide(title=INJECTION_LABEL, layout=layout)],
            title=INJECTION_LABEL,
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml") and not name.endswith(".rels"):
                    continue
                text = archive.read(name).decode("utf-8")
                with self.subTest(part=name):
                    self.assertNotIn("<script", text)
                    self.assertNotIn("<svg", text)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            slide = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn("&lt;script&gt;", slide)

    def test_the_package_still_parses_as_xml_with_the_payload_in_it(self) -> None:
        """The strongest form of "inert": a real parser accepts it and hands
        the text back as text, not as elements."""

        layout = layout_diagram(self._spec_with_payload())
        payload = build_pptx(
            [DiagramSlide(title=INJECTION_LABEL, layout=layout)], title="deck"
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            slide = archive.read("ppt/slides/slide1.xml")
        root = ElementTree.fromstring(slide)
        texts = [
            element.text
            for element in root.iter()
            if element.tag.endswith("}t") and element.text
        ]
        self.assertIn(INJECTION_LABEL, texts)
        self.assertEqual(
            [element for element in root.iter() if element.tag == "script"], []
        )

    def test_the_svg_parses_and_keeps_the_payload_as_text(self) -> None:
        svg = render_svg(layout_diagram(self._spec_with_payload()))
        root = ElementTree.fromstring(svg)
        texts = [
            element.text
            for element in root.iter()
            if element.tag.endswith("}text") and element.text
        ]
        self.assertIn(INJECTION_LABEL, texts)


class SvgTests(unittest.TestCase):
    def test_same_spec_renders_byte_identical_svg_twice(self) -> None:
        spec = wide_cyclic_spec()
        first = render_svg(layout_diagram(spec)).encode("utf-8")
        second = render_svg(layout_diagram(json.loads(json.dumps(spec)))).encode("utf-8")
        self.assertEqual(digest_bytes(first), digest_bytes(second))
        self.assertEqual(first, second)

    def test_injection_in_a_label_cannot_escape_the_svg(self) -> None:
        """Kept as written.  What makes it pass changed: before the export
        allowlist was widened the payload was deleted by ``sanitize_label`` and
        the escaper was never reached, so this was a sanitiser test wearing an
        escaper's name.  It is now genuinely an escaper test.  See
        ``WidenedAllowlistInjectionTests`` for the version that proves it."""

        spec = simple_spec()
        spec["nodes"][0]["label"] = (  # type: ignore[index]
            '</text></svg><script>alert(1)</script><svg x="'
        )
        svg = render_svg(layout_diagram(spec))
        self.assertNotIn("<script", svg)
        self.assertNotIn("</svg><", svg)
        self.assertEqual(svg.count("</svg>"), 1)

    def test_svg_declares_its_natural_pixel_size(self) -> None:
        layout = layout_diagram(wide_cyclic_spec())
        svg = render_svg(layout)
        self.assertIn(f'width="{layout.width}"', svg)
        self.assertIn(f'height="{layout.height}"', svg)
        self.assertIn(f'viewBox="0 0 {layout.width} {layout.height}"', svg)


class ReportTests(unittest.TestCase):
    def _report(self) -> tuple[str, int]:
        layout = layout_diagram(wide_cyclic_spec())
        svg = render_svg(layout)
        html = render_report(
            (
                ReportSection(
                    heading="Wide graph",
                    layout=layout,
                    svg=svg,
                    svg_digest=digest_bytes(svg.encode("utf-8")),
                ),
            ),
            title="Report",
            project_id="project-a",
            revision_id="abc123",
        )
        return html, layout.width

    def test_a_wide_diagram_scrolls_inside_its_own_frame(self) -> None:
        html, width = self._report()
        # The frame scrolls horizontally and the page body is width-bounded, so
        # a diagram wider than the page cannot stretch the document.
        self.assertIn("overflow-x: auto", html)
        self.assertIn("max-width: 1100px", html)
        self.assertGreater(width, 1100)
        self.assertIn(f'width="{width}"', html)
        frame_start = html.index('<div class="frame">')
        svg_start = html.index("<svg", frame_start)
        self.assertLess(frame_start, svg_start)

    def test_report_is_self_contained_and_states_the_evidence_boundary(self) -> None:
        html, _ = self._report()
        self.assertNotIn("<script", html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))
        self.assertIn("NOT_RUN", html)
        self.assertIn("NOT_CERTIFIED", html)

    def test_report_bytes_are_identical_across_runs(self) -> None:
        self.assertEqual(self._report()[0], self._report()[0])


class PptxTests(unittest.TestCase):
    def _deck(self) -> bytes:
        layout = layout_diagram(simple_spec())
        return build_pptx(
            [
                BulletSlide(title="Evidence boundary", bullets=("NOT_CERTIFIED",)),
                DiagramSlide(title="Refund flow", layout=layout),
            ],
            title="Deck",
        )

    def test_same_inputs_produce_byte_identical_packages(self) -> None:
        self.assertEqual(digest_bytes(self._deck()), digest_bytes(self._deck()))

    def test_package_has_the_parts_an_ooxml_reader_requires(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self._deck())) as archive:
            names = set(archive.namelist())
            for required in (
                "[Content_Types].xml",
                "_rels/.rels",
                "ppt/presentation.xml",
                "ppt/_rels/presentation.xml.rels",
                "ppt/slideMasters/slideMaster1.xml",
                "ppt/slideLayouts/slideLayout1.xml",
                "ppt/theme/theme1.xml",
                "ppt/slides/slide1.xml",
                "ppt/slides/_rels/slide1.xml.rels",
                "docProps/core.xml",
                "docProps/app.xml",
            ):
                self.assertIn(required, names)
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def test_the_diagram_is_vector_shapes_and_never_a_raster_image(self) -> None:
        payload = self._deck()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            self.assertFalse([name for name in names if name.startswith("ppt/media/")])
            slide = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        # preset flowchart geometry for nodes, custGeom paths for connectors
        self.assertIn("<a:prstGeom prst=", slide)
        self.assertIn("<a:custGeom>", slide)
        self.assertIn("<a:moveTo>", slide)
        self.assertNotIn("<a:blip", slide)
        # node labels survive as real text runs, not outlines
        self.assertIn("<a:t>issue refund</a:t>", slide)

    def test_every_shape_lands_inside_the_slide(self) -> None:
        payload = build_pptx([DiagramSlide("Wide", layout_diagram(wide_cyclic_spec()))])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            slide = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        offsets = re.findall(r'<a:off x="(-?\d+)" y="(-?\d+)"/>', slide)
        self.assertTrue(offsets)
        for raw_x, raw_y in offsets:
            self.assertGreaterEqual(int(raw_x), 0)
            self.assertGreaterEqual(int(raw_y), 0)
            self.assertLessEqual(int(raw_x), 12192000)
            self.assertLessEqual(int(raw_y), 6858000)

    def test_manifest_slides_convert_and_are_sanitized(self) -> None:
        """Markup now reaches the slide text, and must be dead in the package.

        This test used to assert ``"<b>T</b>" -> "b T b"``: the exporter threw
        the angle brackets away.  After the widening it keeps them, because a
        title like ``count < limit`` is worth more than a stripped one.  The
        safety claim did not disappear, it moved one layer down -- so the
        assertion moved with it, from "the characters are gone" to "the
        characters are in the file and inert".
        """

        slides = slides_from_manifest(
            {"slides": [{"title": "<b>T</b>", "bullets": ["a\nb"]}]}
        )
        self.assertEqual(slides[0].title, "<b>T</b>")
        # Newlines are still collapsed: they are not printable.
        self.assertEqual(slides[0].bullets, ("a b",))

        payload = build_pptx([slides[0]], title="deck")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        self.assertIn("&lt;b&gt;T&lt;/b&gt;", slide_xml)
        self.assertNotIn("<b>", slide_xml)
        self.assertNotIn("</b>", slide_xml)


class ExportBoundaryTests(unittest.TestCase):
    def test_the_presentation_handler_still_reports_no_pptx(self) -> None:
        """The exporter must not widen the contract-pinned handler."""

        result = dispatch_skill("elmos-presentation-generation", request())
        self.assertEqual(
            sorted(result["outputs"]), ["digest", "pptx_generated", "slides"]
        )
        self.assertIs(result["outputs"]["pptx_generated"], False)
        self.assertEqual(result["external_evidence"], "NOT_RUN")

    def test_exporter_accepts_a_dispatch_result_or_a_bare_spec(self) -> None:
        result = dispatch_skill("elmos-diagram-spec-engine", request())
        self.assertEqual(
            extract_diagram_spec(result), result["outputs"]["diagram_spec"]
        )
        bare = simple_spec()
        self.assertEqual(extract_diagram_spec(bare), bare)


class ExportCliTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, value: object) -> Path:
        path = directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    @staticmethod
    def _run(argv: list[str]) -> tuple[int, str]:
        """Run the CLI, capturing the receipt it prints instead of leaking it."""

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = cli.main(argv)
        return code, stream.getvalue()

    def test_cli_writes_svg_report_and_pptx_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            spec_path = self._write(directory, "spec.json", simple_spec())
            manifest = dispatch_skill("elmos-presentation-generation", request())
            manifest_path = self._write(directory, "manifest.json", manifest)

            for command, arguments, name in (
                ("render-svg", [], "diagram.svg"),
                ("report", [], "report.html"),
                (
                    "pptx",
                    ["--manifest", str(manifest_path)],
                    "deck.pptx",
                ),
            ):
                with self.subTest(command=command):
                    first = directory / f"first-{name}"
                    second = directory / f"second-{name}"
                    for output in (first, second):
                        code, receipt = self._run(
                            [
                                command,
                                "--spec",
                                str(spec_path),
                                "--output",
                                str(output),
                                *arguments,
                            ]
                        )
                        self.assertEqual(code, 0)
                        self.assertIn('"raster_used":false', receipt)
                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    self.assertGreater(first.stat().st_size, 0)

    def test_cli_rejects_a_document_without_a_diagram_spec(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            bad = self._write(directory, "bad.json", {"unrelated": True})
            code, _ = self._run(
                [
                    "render-svg",
                    "--spec",
                    str(bad),
                    "--output",
                    str(directory / "out.svg"),
                ]
            )
            self.assertEqual(code, 2)
            self.assertFalse((directory / "out.svg").exists())

    def test_cli_refuses_to_follow_a_symlinked_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            spec_path = self._write(directory, "spec.json", simple_spec())
            target = directory / "target.svg"
            target.write_text("original", encoding="utf-8")
            link = directory / "link.svg"
            link.symlink_to(target)
            code, _ = self._run(
                ["render-svg", "--spec", str(spec_path), "--output", str(link)]
            )
            self.assertEqual(code, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
