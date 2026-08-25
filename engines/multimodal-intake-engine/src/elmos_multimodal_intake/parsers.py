"""Deterministic parsers producing ContentBlock plus immutable SourceAnchor IR."""

from __future__ import annotations

import io
import base64
import binascii
import json
import re
import stat
import zipfile
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree

from .canonical import canonical_digest, normalize_text, sha256_bytes
from .errors import ValidationError
from .models import (
    AssetKind,
    ContentBlock,
    ContentBlockKind,
    DetectionResult,
    InputAsset,
    ParseReport,
    ResultStatus,
    SecurityDecision,
    SourceAnchor,
)
from .providers import ExternalToolProvider, ProviderResult, ToolCapability


_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_WORD_REL_NAMESPACE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class ParserRegistry:
    _MAX_BLOCKS = 10_000
    _MAX_TEXT_BYTES = 4 * 1024 * 1024
    _MAX_TEXT_LINES = 100_000
    _MAX_PROVIDER_ITEMS = 10_000

    def __init__(self, providers: ExternalToolProvider | None = None, *, text_chunk_lines: int = 200) -> None:
        self.providers = providers or ExternalToolProvider()
        self.text_chunk_lines = text_chunk_lines

    def parse(
        self,
        asset: InputAsset,
        data: bytes,
        detection: DetectionResult,
        options: Mapping[str, Any] | None = None,
        *,
        job_id: str | None = None,
        stage: str | None = None,
        provider_result: ProviderResult | None = None,
    ) -> ParseReport:
        if detection.decision is SecurityDecision.QUARANTINE:
            return ParseReport(
                parser="security-gate",
                status=ResultStatus.BLOCKED,
                blocks=(),
                warnings=detection.findings,
                error_code="ASSET_QUARANTINED",
            )
        if detection.kind in {AssetKind.TEXT, AssetKind.MARKDOWN, AssetKind.LOG}:
            report = self._parse_text(asset, data, detection.kind)
            return self._bounded_report(report)
        if detection.kind is AssetKind.DOCX:
            revision_mode = (options or {}).get("revision_mode", "final")
            if not isinstance(revision_mode, str):
                raise ValidationError("DOCX_REVISION_MODE_INVALID")
            report = self._parse_word(
                asset,
                data,
                revision_mode,
                job_id,
                stage,
                provider_result,
            )
            return self._bounded_report(report)
        if detection.kind is AssetKind.PDF:
            report = self._parse_pdf(
                asset,
                data,
                detection.media_type,
                job_id,
                stage,
                provider_result,
            )
            return self._bounded_report(report)
        if detection.kind is AssetKind.IMAGE:
            report = self._parse_image(
                asset,
                data,
                detection.media_type,
                job_id,
                stage,
                provider_result,
            )
            return self._bounded_report(report)
        if detection.kind is AssetKind.AUDIO:
            report = self._parse_audio(
                asset,
                data,
                detection.media_type,
                job_id,
                stage,
                provider_result,
            )
            return self._bounded_report(report)
        return ParseReport(
            parser="unsupported",
            status=ResultStatus.NOT_RUN,
            blocks=(),
            warnings=("NO_SAFE_PARSER_FOR_DETECTED_TYPE",),
            error_code="PARSER_NOT_AVAILABLE",
        )

    def _parse_text(self, asset: InputAsset, data: bytes, kind: AssetKind) -> ParseReport:
        decoded = self._decode_text(data)
        if decoded is None:
            return ParseReport(
                parser="text-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=(),
                warnings=("TEXT_ENCODING_UNSUPPORTED",),
                error_code="TEXT_DECODING_FAILED",
            )
        text = normalize_text(decoded)
        if (
            len(text.encode("utf-8")) > self._MAX_TEXT_BYTES
            or text.count("\n") + 1 > self._MAX_TEXT_LINES
        ):
            return self._budget_blocked("text-v1", "TEXT_PARSE_BUDGET_EXCEEDED")
        if kind is AssetKind.MARKDOWN and sum(
            1
            for line in text.splitlines()
            if line.lstrip().startswith("\x60\x60\x60") or re.match(r"^#{1,6}\s+", line)
        ) > self._MAX_BLOCKS:
            return self._budget_blocked("markdown-v1", "MARKDOWN_BLOCK_LIMIT_EXCEEDED")
        if kind is AssetKind.MARKDOWN:
            blocks = self._markdown_blocks(asset, text)
            parser = "markdown-v1"
        else:
            block_kind = ContentBlockKind.LOG if kind is AssetKind.LOG else ContentBlockKind.TEXT
            blocks = self._line_blocks(asset, text, block_kind)
            parser = "log-v1" if kind is AssetKind.LOG else "text-v1"
        return ParseReport(parser=parser, status=ResultStatus.PASSED, blocks=tuple(blocks))

    def _parse_word(
        self,
        asset: InputAsset,
        data: bytes,
        revision_mode: str,
        job_id: str | None,
        stage: str | None,
        provider_result: ProviderResult | None,
    ) -> ParseReport:
        normalized_mode = revision_mode.strip().lower().replace("-", "_")
        aliases = {
            "all_revisions": "all",
            "deleted_history": "deleted",
            "original_version": "original",
        }
        normalized_mode = aliases.get(normalized_mode, normalized_mode)
        if normalized_mode not in {"final", "all", "original", "deleted"}:
            raise ValidationError("DOCX_REVISION_MODE_INVALID")
        if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return self._parse_legacy_doc(
                asset,
                data,
                normalized_mode,
                job_id,
                stage,
                provider_result,
            )
        return self._parse_docx(asset, data, normalized_mode)

    def _parse_legacy_doc(
        self,
        asset: InputAsset,
        data: bytes,
        revision_mode: str,
        job_id: str | None,
        stage: str | None,
        provider_result: ProviderResult | None,
    ) -> ParseReport:
        provider = self._provider_or_run(
            ToolCapability.WORD_DOC_CONVERT,
            provider_result,
            data,
            "application/msword",
            job_id=job_id,
            stage=f"{stage or 'direct'}:word-convert",
        )
        if provider.status is not ResultStatus.PASSED:
            return self._provider_not_run("legacy-doc-sandbox-v1", provider)
        encoded = provider.payload.get("docx_base64")
        if not isinstance(encoded, str):
            return ParseReport(
                parser="legacy-doc-sandbox-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=(),
                warnings=("LEGACY_DOC_CONVERTER_OUTPUT_INVALID",),
                error_code="LEGACY_DOC_CONVERTER_OUTPUT_INVALID",
                provider_receipt=provider.receipt,
            )
        try:
            converted = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            converted = b""
        if not converted.startswith((b"PK\x03\x04", b"PK\x05\x06")) or len(converted) > 64 * 1024 * 1024:
            return ParseReport(
                parser="legacy-doc-sandbox-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=(),
                warnings=("LEGACY_DOC_CONVERTER_OUTPUT_INVALID",),
                error_code="LEGACY_DOC_CONVERTER_OUTPUT_INVALID",
                provider_receipt=provider.receipt,
            )
        parsed = self._parse_docx(asset, converted, revision_mode)
        return ParseReport(
            parser="legacy-doc-sandbox-v1",
            status=parsed.status,
            blocks=parsed.blocks,
            warnings=tuple(sorted(set(parsed.warnings + ("LEGACY_DOC_CONVERTED_IN_SANDBOX",)))),
            error_code=parsed.error_code,
            provider_receipt=provider.receipt,
            metadata={
                **dict(parsed.metadata),
                "derived_docx_sha256": sha256_bytes(converted),
                "original_media_type": "application/msword",
                "conversion_network_allowed": False,
            },
        )

    def _parse_docx(self, asset: InputAsset, data: bytes, revision_mode: str) -> ParseReport:
        maximum_entries = 4096
        maximum_uncompressed = 128 * 1024 * 1024
        maximum_xml_bytes = 32 * 1024 * 1024
        maximum_xml_nodes = 200_000
        maximum_xml_depth = 128
        maximum_xml_text_bytes = 16 * 1024 * 1024
        parts: dict[str, bytes] = {}
        media: list[dict[str, Any]] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                if len(entries) > maximum_entries:
                    return self._unsafe_docx("DOCX_ENTRY_LIMIT_EXCEEDED")
                total = 0
                for entry in entries:
                    path = PurePosixPath(entry.filename.replace("\\", "/"))
                    if (
                        not path.parts
                        or entry.filename.startswith("/")
                        or any(part in {"", ".", ".."} for part in path.parts)
                        or path.parts[0].endswith(":")
                    ):
                        return self._unsafe_docx("DOCX_PATH_TRAVERSAL")
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        return self._unsafe_docx("DOCX_LINK_ENTRY")
                    if entry.flag_bits & 0x1:
                        return self._unsafe_docx("DOCX_ENCRYPTED_ENTRY")
                    total += entry.file_size
                    if total > maximum_uncompressed:
                        return self._unsafe_docx("DOCX_UNCOMPRESSED_LIMIT_EXCEEDED")
                    if entry.file_size / max(entry.compress_size, 1) > 200:
                        return self._unsafe_docx("DOCX_COMPRESSION_RATIO_EXCEEDED")
                if "word/document.xml" not in names:
                    return self._unsafe_docx("DOCX_DOCUMENT_XML_MISSING")
                if "word/vbaProject.bin" in names:
                    return self._unsafe_docx("DOCX_MACRO_PRESENT")
                if any(name.startswith("word/embeddings/") for name in names):
                    return self._unsafe_docx("DOCX_EMBEDDED_OBJECT_PRESENT")
                wanted = {
                    "word/document.xml",
                    "word/comments.xml",
                    "word/footnotes.xml",
                    "word/endnotes.xml",
                    "word/_rels/document.xml.rels",
                }
                cumulative_xml_bytes = 0
                for name in sorted(wanted & names):
                    info = archive.getinfo(name)
                    cumulative_xml_bytes += info.file_size
                    if info.file_size > maximum_xml_bytes or cumulative_xml_bytes > maximum_xml_bytes:
                        return self._unsafe_docx("DOCX_XML_PART_LIMIT_EXCEEDED")
                    value = archive.read(name)
                    if self._xml_has_forbidden_declaration(value):
                        return self._unsafe_docx("DOCX_XML_DTD_BLOCKED")
                    parts[name] = value
                media_names = sorted(
                    item for item in names if item.startswith("word/media/") and not item.endswith("/")
                )
                if len(media_names) > 1024:
                    return self._unsafe_docx("DOCX_MEDIA_ENTRY_LIMIT_EXCEEDED")
                for name in media_names:
                    info = archive.getinfo(name)
                    record: dict[str, Any] = {
                        "name": name,
                        "byte_size": info.file_size,
                        "compressed_size": info.compress_size,
                    }
                    if info.file_size <= maximum_xml_bytes:
                        record["sha256"] = sha256_bytes(archive.read(name))
                    else:
                        record["sha256"] = None
                        record["digest_state"] = "NOT_COMPUTED_SIZE_LIMIT"
                    media.append(record)
        except (zipfile.BadZipFile, KeyError, OSError, RuntimeError, ValueError):
            return self._unsafe_docx("DOCX_CONTAINER_INVALID")

        roots: dict[str, ElementTree.Element] = {}
        try:
            total_nodes = 0
            total_text_bytes = 0
            for name, part_bytes in parts.items():
                nodes, text_bytes = self._xml_budget(
                    part_bytes,
                    maximum_nodes=maximum_xml_nodes - total_nodes,
                    maximum_depth=maximum_xml_depth,
                    maximum_text_bytes=maximum_xml_text_bytes - total_text_bytes,
                )
                total_nodes += nodes
                total_text_bytes += text_bytes
                roots[name] = ElementTree.fromstring(part_bytes)
        except ValidationError as error:
            return self._unsafe_docx(error.code)
        except ElementTree.ParseError:
            return self._unsafe_docx("DOCX_XML_INVALID")
        root = roots["word/document.xml"]
        body = root.find(f".//{_WORD_NAMESPACE}body")
        if body is None:
            return self._unsafe_docx("DOCX_BODY_MISSING")

        relationships = self._word_relationships(roots.get("word/_rels/document.xml.rels"))
        comments = self._word_notes(roots.get("word/comments.xml"), f"{_WORD_NAMESPACE}comment")
        footnotes = self._word_notes(roots.get("word/footnotes.xml"), f"{_WORD_NAMESPACE}footnote")
        endnotes = self._word_notes(roots.get("word/endnotes.xml"), f"{_WORD_NAMESPACE}endnote")
        revisions = self._word_revisions(root)
        blocks: list[ContentBlock] = []
        paragraph_index = 0
        table_index = 0

        for child in body:
            if child.tag == f"{_WORD_NAMESPACE}p":
                paragraph_text = self._word_text_for_mode(child, revision_mode)
                style_node = child.find(f"./{_WORD_NAMESPACE}pPr/{_WORD_NAMESPACE}pStyle")
                style = style_node.get(f"{_WORD_NAMESPACE}val", "") if style_node is not None else ""
                numbering = self._word_numbering(child)
                bookmarks = sorted(
                    {
                        node.get(f"{_WORD_NAMESPACE}name", "")
                        for node in child.iter(f"{_WORD_NAMESPACE}bookmarkStart")
                        if node.get(f"{_WORD_NAMESPACE}name")
                    }
                )
                hyperlinks = self._word_hyperlinks(child, relationships, revision_mode)
                comment_ids = self._word_reference_ids(
                    child,
                    ("commentRangeStart", "commentReference"),
                )
                footnote_ids = self._word_reference_ids(child, ("footnoteReference",))
                endnote_ids = self._word_reference_ids(child, ("endnoteReference",))
                payload: dict[str, Any] = {
                    "revision_mode": revision_mode,
                    "bookmarks": bookmarks,
                    "hyperlinks": hyperlinks,
                    "comment_ids": comment_ids,
                    "footnote_ids": footnote_ids,
                    "endnote_ids": endnote_ids,
                }
                if style:
                    payload["style"] = style
                if numbering:
                    payload["numbering"] = numbering
                if paragraph_text or bookmarks or hyperlinks:
                    if len(blocks) >= self._MAX_BLOCKS:
                        return self._unsafe_docx("DOCX_BLOCK_LIMIT_EXCEEDED")
                    block_kind = ContentBlockKind.HEADING if style.lower().startswith("heading") else ContentBlockKind.TEXT
                    blocks.append(
                        self._block(
                            asset,
                            len(blocks),
                            block_kind,
                            paragraph_text,
                            payload,
                            locator_type="DOCX_PARAGRAPH",
                            paragraph_index=paragraph_index,
                        )
                    )
                paragraph_index += 1
            elif child.tag == f"{_WORD_NAMESPACE}tbl":
                if len(blocks) >= self._MAX_BLOCKS:
                    return self._unsafe_docx("DOCX_BLOCK_LIMIT_EXCEEDED")
                rows: list[list[str]] = []
                for row in child.findall(f"./{_WORD_NAMESPACE}tr"):
                    rows.append(
                        [
                            self._word_text_for_mode(cell, revision_mode)
                            for cell in row.findall(f"./{_WORD_NAMESPACE}tc")
                        ]
                    )
                blocks.append(
                    self._block(
                        asset,
                        len(blocks),
                        ContentBlockKind.TABLE,
                        "\n".join("\t".join(row) for row in rows),
                        {"rows": rows, "table_index": table_index, "revision_mode": revision_mode},
                        locator_type="DOCX_TABLE",
                        paragraph_index=paragraph_index,
                        symbol=f"table:{table_index}",
                    )
                )
                table_index += 1
                paragraph_index += 1

        for revision in revisions:
            if len(blocks) >= self._MAX_BLOCKS:
                return self._unsafe_docx("DOCX_BLOCK_LIMIT_EXCEEDED")
            blocks.append(
                self._block(
                    asset,
                    len(blocks),
                    ContentBlockKind.REVIEW_NOTE,
                    revision["text"],
                    {"review_type": "REVISION", **revision},
                    locator_type="DOCX_REVISION",
                    symbol=f"revision:{revision['id']}",
                )
            )
        for review_type, values in (("COMMENT", comments), ("FOOTNOTE", footnotes), ("ENDNOTE", endnotes)):
            for review_note in values:
                if len(blocks) >= self._MAX_BLOCKS:
                    return self._unsafe_docx("DOCX_BLOCK_LIMIT_EXCEEDED")
                blocks.append(
                    self._block(
                        asset,
                        len(blocks),
                        ContentBlockKind.REVIEW_NOTE,
                        review_note["text"],
                        {"review_type": review_type, **review_note},
                        locator_type=f"DOCX_{review_type}",
                        symbol=f"{review_type.lower()}:{review_note['id']}",
                    )
                )
        for image_index, item in enumerate(media):
            if len(blocks) >= self._MAX_BLOCKS:
                return self._unsafe_docx("DOCX_BLOCK_LIMIT_EXCEEDED")
            blocks.append(
                self._block(
                    asset,
                    len(blocks),
                    ContentBlockKind.IMAGE,
                    None,
                    {"embedded_media": item, "image_index": image_index},
                    locator_type="DOCX_MEDIA",
                    symbol=item["name"],
                )
            )

        warnings: tuple[str, ...] = ()
        status = ResultStatus.PASSED
        if not blocks:
            status = ResultStatus.NEEDS_REVIEW
            warnings = ("DOCX_HAS_NO_EXTRACTABLE_CONTENT",)
        return ParseReport(
            parser="word-ooxml-v2",
            status=status,
            blocks=tuple(blocks),
            warnings=warnings,
            metadata={
                "parsed_document": {
                    "revision_mode": revision_mode,
                    "paragraph_count": paragraph_index,
                    "table_count": table_index,
                    "embedded_media_count": len(media),
                    "revision_count": len(revisions),
                    "comment_count": len(comments),
                    "footnote_count": len(footnotes),
                    "endnote_count": len(endnotes),
                    "external_links_fetched": False,
                },
                "revisions": revisions,
                "comments": comments,
                "footnotes": footnotes,
                "endnotes": endnotes,
                "relationships": list(relationships.values()),
                "embedded_media": media,
            },
        )

    def _parse_pdf(
        self,
        asset: InputAsset,
        data: bytes,
        media_type: str,
        job_id: str | None,
        stage: str | None,
        provider_result: ProviderResult | None,
    ) -> ParseReport:
        provider = self._provider_or_run(
            ToolCapability.PDF_TEXT,
            provider_result,
            data,
            media_type,
            job_id=job_id,
            stage=f"{stage or 'direct'}:pdf-text",
        )
        if provider.status is not ResultStatus.PASSED:
            return self._provider_not_run("pdf-external-v1", provider)
        pages = provider.payload.get("pages")
        page_values: list[tuple[int, str]] = []
        if isinstance(pages, list):
            if len(pages) > self._MAX_PROVIDER_ITEMS:
                return self._budget_blocked(
                    "pdf-external-v1",
                    "PDF_PAGE_LIMIT_EXCEEDED",
                    provider.receipt,
                )
            for index, page in enumerate(pages, start=1):
                if isinstance(page, dict):
                    number = page.get("page_number", index)
                    text = page.get("text", "")
                else:
                    number, text = index, page
                if isinstance(number, int) and number >= 1 and isinstance(text, str):
                    page_values.append((number, normalize_text(text)))
        else:
            text = provider.payload.get("text")
            if isinstance(text, str):
                page_values = [(index, normalize_text(value)) for index, value in enumerate(text.split("\f"), start=1)]
        blocks = tuple(
            self._block(
                asset,
                ordinal,
                ContentBlockKind.PAGE,
                text,
                {"page_number": page_number},
                locator_type="PDF_PAGE",
                page_number=page_number,
                confidence=1.0,
            )
            for ordinal, (page_number, text) in enumerate(page_values)
            if text
        )
        if not blocks:
            return ParseReport(
                parser="pdf-external-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=(),
                warnings=("PDF_PROVIDER_RETURNED_NO_TEXT",),
                error_code="PDF_TEXT_EMPTY",
                provider_receipt=provider.receipt,
            )
        return ParseReport(
            parser="pdf-external-v1",
            status=ResultStatus.PASSED,
            blocks=blocks,
            provider_receipt=provider.receipt,
        )

    def _parse_image(
        self,
        asset: InputAsset,
        data: bytes,
        media_type: str,
        job_id: str | None,
        stage: str | None,
        provider_result: ProviderResult | None,
    ) -> ParseReport:
        image_block = self._block(
            asset,
            0,
            ContentBlockKind.IMAGE,
            None,
            {"media_type": media_type, "byte_size": len(data)},
            locator_type="WHOLE_ASSET",
        )
        provider = self._provider_or_run(
            ToolCapability.OCR,
            provider_result,
            data,
            media_type,
            job_id=job_id,
            stage=f"{stage or 'direct'}:ocr",
        )
        if provider.status is not ResultStatus.PASSED:
            report = self._provider_not_run("image-ocr-external-v1", provider, blocks=(image_block,))
            return ParseReport(
                parser=report.parser,
                status=ResultStatus.NEEDS_REVIEW,
                blocks=report.blocks,
                warnings=report.warnings,
                error_code=report.error_code,
                provider_receipt=report.provider_receipt,
            )
        blocks: list[ContentBlock] = [image_block]
        regions = provider.payload.get("regions")
        spatial = False
        if isinstance(regions, list):
            if len(regions) > self._MAX_PROVIDER_ITEMS:
                return self._budget_blocked(
                    "image-ocr-external-v1",
                    "OCR_REGION_LIMIT_EXCEEDED",
                    provider.receipt,
                )
            for region in regions:
                if not isinstance(region, dict) or not isinstance(region.get("text"), str):
                    continue
                bbox = self._bbox(region.get("bbox"))
                spatial = spatial or bbox is not None
                blocks.append(
                    self._block(
                        asset,
                        len(blocks),
                        ContentBlockKind.TEXT,
                        normalize_text(region["text"]),
                        {"provider": "OCR"},
                        locator_type="IMAGE_REGION" if bbox else "WHOLE_ASSET",
                        bbox=bbox,
                        confidence=self._confidence(region.get("confidence")),
                    )
                )
        elif isinstance(provider.payload.get("text"), str) and provider.payload["text"].strip():
            blocks.append(
                self._block(
                    asset,
                    1,
                    ContentBlockKind.TEXT,
                    normalize_text(provider.payload["text"]),
                    {"provider": "OCR"},
                    locator_type="WHOLE_ASSET",
                )
            )
        if len(blocks) == 1:
            return ParseReport(
                parser="image-ocr-external-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=tuple(blocks),
                warnings=("OCR_PROVIDER_RETURNED_NO_TEXT",),
                error_code="OCR_TEXT_EMPTY",
                provider_receipt=provider.receipt,
            )
        warnings = () if spatial else ("OCR_SPATIAL_ANCHORS_UNAVAILABLE",)
        return ParseReport(
            parser="image-ocr-external-v1",
            status=ResultStatus.PASSED if spatial else ResultStatus.PARTIAL,
            blocks=tuple(blocks),
            warnings=warnings,
            provider_receipt=provider.receipt,
        )

    def _parse_audio(
        self,
        asset: InputAsset,
        data: bytes,
        media_type: str,
        job_id: str | None,
        stage: str | None,
        provider_result: ProviderResult | None,
    ) -> ParseReport:
        metadata = self._block(
            asset,
            0,
            ContentBlockKind.AUDIO_SEGMENT,
            None,
            {"media_type": media_type, "byte_size": len(data), "transcript_status": "NOT_RUN"},
            locator_type="WHOLE_ASSET",
        )
        provider = self._provider_or_run(
            ToolCapability.ASR,
            provider_result,
            data,
            media_type,
            job_id=job_id,
            stage=f"{stage or 'direct'}:asr",
        )
        if provider.status is not ResultStatus.PASSED:
            return self._provider_not_run("audio-asr-external-v1", provider, blocks=(metadata,))
        blocks: list[ContentBlock] = []
        segments = provider.payload.get("segments")
        timed = False
        if isinstance(segments, list):
            if len(segments) > self._MAX_PROVIDER_ITEMS:
                return self._budget_blocked(
                    "audio-asr-external-v1",
                    "ASR_SEGMENT_LIMIT_EXCEEDED",
                    provider.receipt,
                )
            for segment in segments:
                if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                    continue
                start = self._milliseconds(segment.get("start_ms"))
                end = self._milliseconds(segment.get("end_ms"))
                if start is None:
                    start = self._seconds_to_milliseconds(segment.get("start"))
                if end is None:
                    end = self._seconds_to_milliseconds(segment.get("end"))
                if start is not None and end is not None and end >= start:
                    timed = True
                else:
                    start = end = None
                blocks.append(
                    self._block(
                        asset,
                        len(blocks),
                        ContentBlockKind.AUDIO_SEGMENT,
                        normalize_text(segment["text"]),
                        {"speaker": segment.get("speaker")},
                        locator_type="AUDIO_TIME_RANGE" if start is not None else "WHOLE_ASSET",
                        time_start_ms=start,
                        time_end_ms=end,
                        confidence=self._confidence(segment.get("confidence")),
                    )
                )
        elif isinstance(provider.payload.get("text"), str) and provider.payload["text"].strip():
            blocks.append(
                self._block(
                    asset,
                    0,
                    ContentBlockKind.AUDIO_SEGMENT,
                    normalize_text(provider.payload["text"]),
                    {},
                    locator_type="WHOLE_ASSET",
                )
            )
        if not blocks:
            return ParseReport(
                parser="audio-asr-external-v1",
                status=ResultStatus.NEEDS_REVIEW,
                blocks=(metadata,),
                warnings=("ASR_PROVIDER_RETURNED_NO_TRANSCRIPT",),
                error_code="ASR_TRANSCRIPT_EMPTY",
                provider_receipt=provider.receipt,
            )
        return ParseReport(
            parser="audio-asr-external-v1",
            status=ResultStatus.PASSED if timed else ResultStatus.PARTIAL,
            blocks=tuple(blocks),
            warnings=() if timed else ("ASR_TIMESTAMPS_UNAVAILABLE",),
            provider_receipt=provider.receipt,
        )

    def _provider_or_run(
        self,
        capability: ToolCapability,
        provider_result: ProviderResult | None,
        data: bytes,
        media_type: str,
        *,
        job_id: str | None,
        stage: str,
    ) -> ProviderResult:
        """Consume a workflow-fenced result or invoke the direct local provider.

        Durable workflows inject an already persisted result so this parser can
        never repeat a paid/external effect after a process crash.  Standalone
        parser use retains the bounded provider adapter path.
        """

        if provider_result is not None:
            if provider_result.capability is not capability:
                raise ValidationError("PROVIDER_RESULT_CAPABILITY_MISMATCH")
            return provider_result
        return self.providers.run(
            capability,
            data,
            media_type,
            job_id=job_id,
            stage=stage,
        )

    def _line_blocks(
        self,
        asset: InputAsset,
        text: str,
        kind: ContentBlockKind,
    ) -> list[ContentBlock]:
        lines = text.split("\n")
        if text == "":
            return [self._block(asset, 0, kind, "", {}, locator_type="WHOLE_ASSET")]
        blocks: list[ContentBlock] = []
        for start_index in range(0, len(lines), self.text_chunk_lines):
            selected = lines[start_index : start_index + self.text_chunk_lines]
            blocks.append(
                self._block(
                    asset,
                    len(blocks),
                    kind,
                    "\n".join(selected),
                    {},
                    locator_type="LINE_RANGE",
                    line_start=start_index + 1,
                    line_end=start_index + len(selected),
                )
            )
        return blocks

    def _markdown_blocks(self, asset: InputAsset, text: str) -> list[ContentBlock]:
        lines = text.split("\n")
        blocks: list[ContentBlock] = []
        pending: list[str] = []
        pending_start = 1
        code_lines: list[str] = []
        code_start = 1
        code_language = ""
        in_code = False

        def append(kind: ContentBlockKind, value: str, start: int, end: int, payload: dict[str, Any]) -> None:
            blocks.append(
                self._block(
                    asset,
                    len(blocks),
                    kind,
                    value,
                    payload,
                    locator_type="LINE_RANGE",
                    line_start=start,
                    line_end=end,
                )
            )

        def flush_pending(end: int) -> None:
            nonlocal pending
            if pending:
                append(ContentBlockKind.TEXT, "\n".join(pending), pending_start, end, {})
                pending = []

        for line_number, line in enumerate(lines, start=1):
            if in_code:
                if line.lstrip().startswith("```"):
                    append(
                        ContentBlockKind.CODE,
                        "\n".join(code_lines),
                        code_start,
                        line_number,
                        {"language": code_language},
                    )
                    code_lines = []
                    in_code = False
                else:
                    code_lines.append(line)
                continue
            if line.lstrip().startswith("```"):
                flush_pending(line_number - 1)
                in_code = True
                code_start = line_number
                code_language = line.strip()[3:].strip()
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                flush_pending(line_number - 1)
                append(
                    ContentBlockKind.HEADING,
                    heading.group(2),
                    line_number,
                    line_number,
                    {"level": len(heading.group(1))},
                )
                continue
            if not pending:
                pending_start = line_number
            pending.append(line)
        flush_pending(len(lines))
        if in_code:
            append(
                ContentBlockKind.CODE,
                "\n".join(code_lines),
                code_start,
                len(lines),
                {"language": code_language, "unterminated": True},
            )
        return blocks or [self._block(asset, 0, ContentBlockKind.TEXT, "", {}, locator_type="WHOLE_ASSET")]

    @staticmethod
    def _decode_text(data: bytes) -> str | None:
        encodings = ("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig",)
        for encoding in encodings:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                pass
        return None

    @staticmethod
    def _word_relationships(root: ElementTree.Element | None) -> dict[str, dict[str, Any]]:
        relationships: dict[str, dict[str, Any]] = {}
        if root is None:
            return relationships
        for node in root.iter(f"{_PACKAGE_REL_NAMESPACE}Relationship"):
            relationship_id = node.get("Id")
            target = node.get("Target")
            if not relationship_id or not target or len(target) > 4096:
                continue
            target_mode = node.get("TargetMode", "Internal")
            relationships[relationship_id] = {
                "id": relationship_id,
                "type": node.get("Type", ""),
                "target": target,
                "target_mode": target_mode,
                "external": target_mode.lower() == "external",
                "fetched": False,
            }
        return relationships

    @classmethod
    def _word_notes(
        cls,
        root: ElementTree.Element | None,
        tag: str,
    ) -> list[dict[str, Any]]:
        notes: list[dict[str, Any]] = []
        if root is None:
            return notes
        for node in root.iter(tag):
            identifier = node.get(f"{_WORD_NAMESPACE}id")
            if identifier is None or identifier.startswith("-"):
                continue
            notes.append(
                {
                    "id": identifier,
                    "author": node.get(f"{_WORD_NAMESPACE}author"),
                    "date": node.get(f"{_WORD_NAMESPACE}date"),
                    "text": cls._word_text_for_mode(node, "all"),
                }
            )
        return notes

    @classmethod
    def _word_revisions(cls, root: ElementTree.Element) -> list[dict[str, Any]]:
        revisions: list[dict[str, Any]] = []
        for revision_type, tag in (("INSERTION", "ins"), ("DELETION", "del")):
            for index, node in enumerate(root.iter(f"{_WORD_NAMESPACE}{tag}")):
                identifier = node.get(f"{_WORD_NAMESPACE}id", f"{tag}-{index}")
                revisions.append(
                    {
                        "id": identifier,
                        "type": revision_type,
                        "author": node.get(f"{_WORD_NAMESPACE}author"),
                        "date": node.get(f"{_WORD_NAMESPACE}date"),
                        "text": cls._word_text_for_mode(node, "all"),
                        "included_in_final": revision_type == "INSERTION",
                    }
                )
        return revisions

    @classmethod
    def _word_text_for_mode(cls, element: ElementTree.Element, revision_mode: str) -> str:
        values: list[str] = []

        def visit(node: ElementTree.Element, *, in_deletion: bool = False) -> None:
            if node.tag == f"{_WORD_NAMESPACE}ins" and revision_mode in {"original", "deleted"}:
                return
            if node.tag == f"{_WORD_NAMESPACE}del":
                if revision_mode == "final":
                    return
                in_deletion = True
            if node.tag in {f"{_WORD_NAMESPACE}t", f"{_WORD_NAMESPACE}delText"}:
                if revision_mode != "deleted" or in_deletion:
                    values.append(node.text or "")
                return
            if node.tag == f"{_WORD_NAMESPACE}tab" and revision_mode != "deleted":
                values.append("\t")
            elif node.tag in {f"{_WORD_NAMESPACE}br", f"{_WORD_NAMESPACE}cr"} and revision_mode != "deleted":
                values.append("\n")
            for child in node:
                visit(child, in_deletion=in_deletion)

        visit(element)
        return normalize_text("".join(values)).strip()

    @staticmethod
    def _word_numbering(paragraph: ElementTree.Element) -> dict[str, str]:
        properties = paragraph.find(f"./{_WORD_NAMESPACE}pPr/{_WORD_NAMESPACE}numPr")
        if properties is None:
            return {}
        level = properties.find(f"./{_WORD_NAMESPACE}ilvl")
        number = properties.find(f"./{_WORD_NAMESPACE}numId")
        result: dict[str, str] = {}
        if level is not None and level.get(f"{_WORD_NAMESPACE}val") is not None:
            result["level"] = str(level.get(f"{_WORD_NAMESPACE}val"))
        if number is not None and number.get(f"{_WORD_NAMESPACE}val") is not None:
            result["numbering_id"] = str(number.get(f"{_WORD_NAMESPACE}val"))
        return result

    @classmethod
    def _word_hyperlinks(
        cls,
        paragraph: ElementTree.Element,
        relationships: Mapping[str, Mapping[str, Any]],
        revision_mode: str,
    ) -> list[dict[str, Any]]:
        hyperlinks: list[dict[str, Any]] = []
        for node in paragraph.iter(f"{_WORD_NAMESPACE}hyperlink"):
            relationship_id = node.get(f"{_WORD_REL_NAMESPACE}id")
            relationship = relationships.get(relationship_id or "", {})
            hyperlinks.append(
                {
                    "relationship_id": relationship_id,
                    "anchor": node.get(f"{_WORD_NAMESPACE}anchor"),
                    "text": cls._word_text_for_mode(node, revision_mode),
                    "target": relationship.get("target"),
                    "external": bool(relationship.get("external", False)),
                    "fetched": False,
                }
            )
        return hyperlinks

    @staticmethod
    def _word_reference_ids(
        paragraph: ElementTree.Element,
        local_names: tuple[str, ...],
    ) -> list[str]:
        identifiers: set[str] = set()
        for local_name in local_names:
            for node in paragraph.iter(f"{_WORD_NAMESPACE}{local_name}"):
                identifier = node.get(f"{_WORD_NAMESPACE}id")
                if identifier is not None:
                    identifiers.add(identifier)
        return sorted(identifiers)

    @staticmethod
    def _xml_has_forbidden_declaration(value: bytes) -> bool:
        upper = value.upper()
        tokens = (b"<!DOCTYPE", b"<!ENTITY")
        encodings = ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")
        return any(token in upper for token in tokens) or any(
            token.decode("ascii").encode(encoding).upper() in upper
            for token in tokens
            for encoding in encodings
        )

    @staticmethod
    def _xml_budget(
        value: bytes,
        *,
        maximum_nodes: int,
        maximum_depth: int,
        maximum_text_bytes: int,
    ) -> tuple[int, int]:
        if maximum_nodes < 1 or maximum_text_bytes < 0:
            raise ValidationError("DOCX_XML_NODE_LIMIT_EXCEEDED")
        nodes = 0
        depth = 0
        text_bytes = 0
        for event, element in ElementTree.iterparse(io.BytesIO(value), events=("start", "end")):
            if event == "start":
                nodes += 1
                depth += 1
                if nodes > maximum_nodes:
                    raise ValidationError("DOCX_XML_NODE_LIMIT_EXCEEDED")
                if depth > maximum_depth:
                    raise ValidationError("DOCX_XML_DEPTH_LIMIT_EXCEEDED")
                continue
            text_bytes += len((element.text or "").encode("utf-8"))
            text_bytes += len((element.tail or "").encode("utf-8"))
            if text_bytes > maximum_text_bytes:
                raise ValidationError("DOCX_XML_TEXT_LIMIT_EXCEEDED")
            depth -= 1
        if depth != 0:
            raise ValidationError("DOCX_XML_INVALID")
        return nodes, text_bytes

    def _bounded_report(self, report: ParseReport) -> ParseReport:
        if len(report.blocks) > self._MAX_BLOCKS:
            return self._budget_blocked(report.parser, "PARSER_BLOCK_LIMIT_EXCEEDED", report.provider_receipt)
        text_bytes = 0
        anchor_count = 0
        try:
            for block in report.blocks:
                text_bytes += len((block.text or "").encode("utf-8"))
                anchor_count += len(block.anchors)
                text_bytes += len(
                    json.dumps(
                        dict(block.payload),
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                if text_bytes > self._MAX_TEXT_BYTES or anchor_count > self._MAX_BLOCKS * 2:
                    return self._budget_blocked(
                        report.parser,
                        "PARSER_OUTPUT_LIMIT_EXCEEDED",
                        report.provider_receipt,
                    )
            metadata_bytes = len(
                json.dumps(
                    {
                        "metadata": dict(report.metadata),
                        "provider_receipt": dict(report.provider_receipt),
                        "warnings": list(report.warnings),
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        except (TypeError, ValueError, OverflowError, RecursionError):
            return self._budget_blocked(
                report.parser,
                "PARSER_OUTPUT_NOT_CANONICAL",
                report.provider_receipt,
            )
        if metadata_bytes > 1024 * 1024:
            return self._budget_blocked(
                report.parser,
                "PARSER_METADATA_LIMIT_EXCEEDED",
                report.provider_receipt,
            )
        return report

    @staticmethod
    def _budget_blocked(
        parser: str,
        code: str,
        provider_receipt: Mapping[str, Any] | None = None,
    ) -> ParseReport:
        return ParseReport(
            parser=parser,
            status=ResultStatus.BLOCKED,
            blocks=(),
            warnings=(code,),
            error_code=code,
            provider_receipt=provider_receipt or {},
            metadata={"budget_enforced": True},
        )

    @staticmethod
    def _unsafe_docx(code: str) -> ParseReport:
        return ParseReport(
            parser="docx-stdlib-v1",
            status=ResultStatus.BLOCKED,
            blocks=(),
            warnings=(code,),
            error_code=code,
        )

    @staticmethod
    def _provider_not_run(
        parser: str,
        provider: ProviderResult,
        *,
        blocks: tuple[ContentBlock, ...] = (),
    ) -> ParseReport:
        status = ResultStatus.NOT_RUN if provider.status is ResultStatus.NOT_RUN else ResultStatus.NEEDS_REVIEW
        return ParseReport(
            parser=parser,
            status=status,
            blocks=blocks,
            warnings=tuple(provider.warnings) + ((provider.error_code,) if provider.error_code else ()),
            error_code=provider.error_code,
            provider_receipt=provider.receipt,
        )

    @staticmethod
    def _bbox(value: Any) -> tuple[float, float, float, float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            result = tuple(float(item) for item in value)
        except (TypeError, ValueError):
            return None
        if any(item < 0 for item in result):
            return None
        return result  # type: ignore[return-value]

    @staticmethod
    def _confidence(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            candidate = float(value)
            if 0 <= candidate <= 1:
                return candidate
        return None

    @staticmethod
    def _milliseconds(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        if isinstance(value, float) and value >= 0:
            return round(value)
        return None

    @staticmethod
    def _seconds_to_milliseconds(value: Any) -> int | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return round(float(value) * 1000)
        return None

    @staticmethod
    def _block(
        asset: InputAsset,
        ordinal: int,
        kind: ContentBlockKind,
        text: str | None,
        payload: dict[str, Any],
        *,
        locator_type: str,
        page_number: int | None = None,
        paragraph_index: int | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        time_start_ms: int | None = None,
        time_end_ms: int | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        symbol: str | None = None,
        confidence: float | None = None,
    ) -> ContentBlock:
        if asset.sha256 is None:
            raise ValidationError("SOURCE_ASSET_DIGEST_REQUIRED")
        source_digest = asset.sha256
        identity = {
            "asset_id": asset.asset_id,
            "source_sha256": source_digest,
            "ordinal": ordinal,
            "kind": kind.value,
            "text_sha256": sha256_bytes(text.encode("utf-8")) if text is not None else None,
            "locator": {
                "type": locator_type,
                "page": page_number,
                "paragraph": paragraph_index,
                "line_start": line_start,
                "line_end": line_end,
                "time_start_ms": time_start_ms,
                "time_end_ms": time_end_ms,
                "bbox": bbox,
                "symbol": symbol,
            },
        }
        block_id = f"block-{canonical_digest(identity)[:32]}"
        anchor_id = f"anchor-{canonical_digest([block_id, identity['locator']])[:32]}"
        anchor = SourceAnchor(
            anchor_id=anchor_id,
            asset_id=asset.asset_id,
            source_sha256=source_digest,
            locator_type=locator_type,
            page_number=page_number,
            paragraph_index=paragraph_index,
            line_start=line_start,
            line_end=line_end,
            time_start_ms=time_start_ms,
            time_end_ms=time_end_ms,
            bbox=bbox,
            symbol=symbol,
            excerpt_sha256=sha256_bytes(text.encode("utf-8")) if text is not None else None,
        )
        return ContentBlock(
            block_id=block_id,
            asset_id=asset.asset_id,
            kind=kind,
            ordinal=ordinal,
            text=text,
            payload=payload,
            anchors=(anchor,),
            confidence=confidence,
        )
