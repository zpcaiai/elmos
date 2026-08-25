from __future__ import annotations

import base64
import hashlib
import io
import json
import sqlite3
import struct
import tempfile
import threading
import unittest
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

from elmos_multimodal_intake import TenantContext, ToolCapability, UploadPolicy, create_runtime
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json
from elmos_multimodal_intake.errors import AuthorizationError, ConflictError, IntegrityError, ValidationError
from elmos_multimodal_intake.models import (
    AssetStatus,
    ContentBlock,
    ContentBlockKind,
    JobStatus,
    ParseReport,
    ResultStatus,
    SessionStatus,
    SourceAnchor,
    UploadStatus,
)
from elmos_multimodal_intake.providers import CommandReceipt


ORCHESTRATOR = "elmos-multimodal-input-orchestrator"
UPLOAD = "elmos-secure-resumable-upload"
DETECT = "elmos-file-type-detection-and-validation"
MALWARE = "elmos-malware-quarantine-and-sandbox"
PDF = "elmos-pdf-layout-table-parser"
IMAGE = "elmos-image-ocr-and-preprocessing"
AUDIO = "elmos-audio-asr-and-diarization"
VISUAL = "elmos-visual-ui-understanding"
DIAGRAM = "elmos-diagram-and-architecture-understanding"
WORD = "elmos-word-document-parser"
TEXT = "elmos-markdown-text-log-parser"
DURABLE = "elmos-durable-processing-and-recovery"


def provisioned(path: str) -> dict[str, str]:
    return {"path": path, "sha256": "a" * 64}


class RecordingSandbox:
    def __init__(self, stdout: bytes | dict[str, bytes]) -> None:
        self.stdout = stdout
        self.calls: list[dict[str, object]] = []

    def execute(self, **request: object) -> CommandReceipt:
        self.calls.append(dict(request))
        stdout = self.stdout[str(request["tool"])] if isinstance(self.stdout, dict) else self.stdout
        return CommandReceipt(
            tool=str(request["tool"]),
            executable_sha256="a" * 64,
            exit_code=0,
            stdout=stdout,
            duration_ms=7,
            sandboxed=True,
            network_allowed=False,
        )


class AmbiguousSandbox:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute(self, **request: object) -> CommandReceipt:
        self.calls.append(dict(request))
        raise RuntimeError("sandbox completion is unknown")


class BoolLikeSandbox:
    def execute(self, **request: object) -> CommandReceipt:
        return CommandReceipt(
            tool=str(request["tool"]),
            executable_sha256="a" * 64,
            exit_code=0,
            stdout=json.dumps({"verdict": "CLEAN", "findings": []}).encode(),
            duration_ms=1,
            sandboxed=1,  # type: ignore[arg-type]
            network_allowed=0,  # type: ignore[arg-type]
        )


class CoreIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.runtime = create_runtime(
            root / "intake.sqlite3",
            root / "cas",
            upload_policy=UploadPolicy(default_part_size=4, maximum_part_size=64),
        )
        self.context = TenantContext("tenant-a", "project-a", "owner@example.test")
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-project"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "session-1", "trace_id": "trace-1"},
        )
        self.session_id = created["session_id"]

    def tearDown(self) -> None:
        self.runtime.close()
        self.temporary.cleanup()

    def _upload(self, name: str, media_type: str, data: bytes, key: str) -> dict[str, object]:
        digest = hashlib.sha256(data).hexdigest()
        started = self.runtime.handle(
            UPLOAD,
            self.context,
            {
                "operation": "start",
                "session_id": self.session_id,
                "display_name": name,
                "declared_media_type": media_type,
                "expected_size": len(data),
                "expected_sha256": digest,
                "part_size": 4,
                "idempotency_key": f"{key}-start",
            },
        )
        upload_id = str(started["upload_session_id"])
        for part_number, offset in enumerate(range(0, len(data), 4)):
            part = data[offset : offset + 4]
            self.runtime.handle(
                UPLOAD,
                self.context,
                {
                    "operation": "upload_part",
                    "upload_session_id": upload_id,
                    "part_number": part_number,
                    "byte_offset": offset,
                    "data_base64": base64.b64encode(part).decode("ascii"),
                    "sha256": hashlib.sha256(part).hexdigest(),
                    "idempotency_key": f"{key}-part-{part_number}",
                },
            )
        committed = self.runtime.handle(
            UPLOAD,
            self.context,
            {
                "operation": "commit",
                "upload_session_id": upload_id,
                "idempotency_key": f"{key}-commit",
            },
        )
        return {**started, **committed, "upload_session_id": upload_id}

    def _reset_with_clean_malware_scanner(self, name: str) -> RecordingSandbox:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox(
            json.dumps({"verdict": "CLEAN", "findings": []}).encode()
        )
        self.runtime = create_runtime(
            root / f"{name}.sqlite3",
            root / f"{name}-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned(
                    "/private/host-only/scanners/elmos-malware-scan"
                )
            },
            upload_policy=UploadPolicy(default_part_size=4, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": f"{name}-bootstrap"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": f"{name}-session"},
        )
        self.session_id = str(created["session_id"])
        return executor

    def test_start_part_commit_are_idempotent_and_tenant_scoped(self) -> None:
        data = b"hello multimodal"
        digest = hashlib.sha256(data).hexdigest()
        request = {
            "operation": "start",
            "session_id": self.session_id,
            "display_name": "notes/readme.txt",
            "declared_media_type": "text/plain",
            "expected_size": len(data),
            "expected_sha256": digest,
            "part_size": 64,
            "idempotency_key": "idem-start",
        }
        first = self.runtime.handle(UPLOAD, self.context, request)
        second = self.runtime.handle(UPLOAD, self.context, request)
        self.assertEqual(first["upload_session_id"], second["upload_session_id"])
        part = {
            "operation": "upload_part",
            "upload_session_id": first["upload_session_id"],
            "part_number": 0,
            "byte_offset": 0,
            "data_base64": base64.b64encode(data).decode("ascii"),
            "sha256": digest,
            "idempotency_key": "idem-part",
        }
        accepted = self.runtime.handle(UPLOAD, self.context, part)
        replayed_part = self.runtime.handle(UPLOAD, self.context, part)
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertEqual(replayed_part, accepted)
        commit = {
            "operation": "commit",
            "upload_session_id": first["upload_session_id"],
            "idempotency_key": "idem-commit",
        }
        completed = self.runtime.handle(UPLOAD, self.context, commit)
        replayed = self.runtime.handle(UPLOAD, self.context, commit)
        self.assertEqual(completed["asset_id"], replayed["asset_id"])
        outsider = TenantContext("tenant-b", "project-a", "owner@example.test")
        with self.assertRaises(AuthorizationError):
            self.runtime.handle(UPLOAD, outsider, {"operation": "status", "upload_session_id": first["upload_session_id"]})

    def test_part_and_final_digest_mismatches_fail_closed(self) -> None:
        data = b"abcd"
        started = self.runtime.handle(
            UPLOAD,
            self.context,
            {
                "operation": "start",
                "session_id": self.session_id,
                "display_name": "bad.txt",
                "declared_media_type": "text/plain",
                "expected_size": 4,
                "expected_sha256": "0" * 64,
                "part_size": 4,
                "idempotency_key": "bad-start",
            },
        )
        upload_id = started["upload_session_id"]
        with self.assertRaises(IntegrityError):
            self.runtime.handle(
                UPLOAD,
                self.context,
                {
                    "operation": "upload_part",
                    "upload_session_id": upload_id,
                    "part_number": 0,
                    "byte_offset": 0,
                    "data": data,
                    "sha256": "f" * 64,
                    "idempotency_key": "bad-part-rejected",
                },
            )
        self.runtime.handle(
            UPLOAD,
            self.context,
            {
                "operation": "upload_part",
                "upload_session_id": upload_id,
                "part_number": 0,
                "byte_offset": 0,
                "data": data,
                "sha256": hashlib.sha256(data).hexdigest(),
                "idempotency_key": "bad-part-valid",
            },
        )
        with self.assertRaises(IntegrityError):
            self.runtime.handle(
                UPLOAD,
                self.context,
                {"operation": "commit", "upload_session_id": upload_id, "idempotency_key": "bad-commit"},
            )
        status = self.runtime.handle(UPLOAD, self.context, {"operation": "status", "upload_session_id": upload_id})
        self.assertEqual(status["upload"]["status"], UploadStatus.QUARANTINED.value)

    def test_text_workflow_persists_content_and_replays_terminal_job(self) -> None:
        uploaded = self._upload("requirements.md", "text/markdown", b"# Goal\n\nShip it.\n", "text")
        request = {
            "operation": "process_session",
            "session_id": self.session_id,
            "idempotency_key": "workflow-1",
        }
        first = self.runtime.handle(ORCHESTRATOR, self.context, request)
        second = self.runtime.handle(ORCHESTRATOR, self.context, request)
        self.assertEqual(first["job"]["job_id"], second["job"]["job_id"])
        self.assertEqual(first["session"]["status"], SessionStatus.NEEDS_REVIEW.value)
        report = first["reports"][uploaded["asset_id"]]
        self.assertEqual(report["status"], "NEEDS_REVIEW")
        self.assertEqual(report["metadata"]["malware_scan"]["status"], "NOT_RUN")
        self.assertTrue(report["blocks"][0]["anchors"])
        final_asset = next(
            item for item in first["assets"] if item["asset_id"] == uploaded["asset_id"]
        )
        source = self.runtime.store._connection.execute(
            """SELECT s.*,h.direction,h.version AS head_version
                 FROM human_review_source_snapshots s
                 JOIN human_review_target_heads h
                   ON h.tenant_id=s.tenant_id AND h.project_id=s.project_id
                  AND h.base_snapshot_id=s.snapshot_id
                WHERE s.tenant_id=? AND s.project_id=? AND s.asset_id=?
                  AND s.asset_version=? AND s.target_kind='TEXT'
                  AND s.target_json=? LIMIT 1""",
            (
                self.context.tenant_id,
                self.context.project_id,
                uploaded["asset_id"],
                final_asset["version"],
                canonical_json(
                    {
                        "path": (
                            f"content_blocks/{report['blocks'][0]['block_id']}/text"
                        )
                    }
                ),
            ),
        ).fetchone()
        self.assertIsNotNone(source)
        self.assertEqual(json.loads(source["original_value_json"]), report["blocks"][0]["text"])
        self.assertEqual(source["producer_actor_id"], "workload:multimodal-parser")
        self.assertEqual(source["direction"], "SNAPSHOT")
        self.assertEqual(source["head_version"], 1)

    def test_parser_review_source_compiler_covers_real_block_anchor_shapes(self) -> None:
        asset_id = "asset-parser-review-source"
        source_sha = "a" * 64

        def anchor(anchor_id: str, locator_type: str, **values: object) -> SourceAnchor:
            return SourceAnchor(
                anchor_id=anchor_id,
                asset_id=asset_id,
                source_sha256=source_sha,
                locator_type=locator_type,
                **values,
            )

        blocks = (
            ContentBlock(
                block_id="block-text",
                asset_id=asset_id,
                kind=ContentBlockKind.TEXT,
                ordinal=0,
                text="plain text",
                anchors=(anchor("anchor-text", "TEXT_LINE", line_start=1, line_end=1),),
            ),
            ContentBlock(
                block_id="block-pdf-page",
                asset_id=asset_id,
                kind=ContentBlockKind.PAGE,
                ordinal=1,
                text="pdf page",
                payload={"page_number": 2},
                anchors=(anchor("anchor-pdf", "PDF_PAGE", page_number=2),),
            ),
            ContentBlock(
                block_id="block-ocr-region",
                asset_id=asset_id,
                kind=ContentBlockKind.TEXT,
                ordinal=2,
                text="ocr text",
                payload={"provider": "OCR"},
                anchors=(
                    anchor(
                        "anchor-ocr",
                        "IMAGE_REGION",
                        bbox=(1.0, 2.0, 30.0, 10.0),
                    ),
                ),
                confidence=0.9,
            ),
            ContentBlock(
                block_id="block-asr-segment",
                asset_id=asset_id,
                kind=ContentBlockKind.AUDIO_SEGMENT,
                ordinal=3,
                text="spoken text",
                payload={"speaker": "speaker-a"},
                anchors=(
                    anchor(
                        "anchor-asr",
                        "AUDIO_TIME_RANGE",
                        time_start_ms=100,
                        time_end_ms=900,
                    ),
                ),
                confidence=0.8,
            ),
            ContentBlock(
                block_id="block-table",
                asset_id=asset_id,
                kind=ContentBlockKind.TABLE,
                ordinal=4,
                text="A\tB",
                payload={"rows": [["A", "B"]], "table_index": 0},
                anchors=(anchor("anchor-table", "DOCX_TABLE", paragraph_index=0),),
            ),
        )
        candidates = self.runtime.store._human_review_parser_source_candidates(
            ParseReport(parser="parser-source-contract-test", status=ResultStatus.PASSED, blocks=blocks),
            asset_id=asset_id,
            asset_version=7,
            report_digest="b" * 64,
        )
        keyed = {
            (candidate["target_kind"], json.dumps(candidate["target"], sort_keys=True)):
            candidate
            for candidate in candidates
        }
        self.assertIn(("TEXT", json.dumps({"path": "content_blocks/block-text/text"}, sort_keys=True)), keyed)
        self.assertIn(("TEXT", json.dumps({"path": "content_blocks/block-pdf-page/text"}, sort_keys=True)), keyed)
        self.assertIn(("BBOX", json.dumps({"page": 1, "x": 1.0, "y": 2.0, "width": 30.0, "height": 10.0}, sort_keys=True)), keyed)
        self.assertIn(("TIME_RANGE", json.dumps({"start_ms": 100, "end_ms": 900}, sort_keys=True)), keyed)
        self.assertIn(("SPEAKER", json.dumps({"segment_id": "block-asr-segment"}, sort_keys=True)), keyed)
        self.assertIn(("TABLE", json.dumps({"table_id": "block-table", "row": 0, "column": 1}, sort_keys=True)), keyed)
        table_candidate = keyed[
            (
                "TABLE",
                json.dumps(
                    {"table_id": "block-table", "row": 0, "column": 1},
                    sort_keys=True,
                ),
            )
        ]
        self.assertEqual(table_candidate["provenance"]["source_kind"], "CONTENT_BLOCK")
        self.assertEqual(table_candidate["provenance"]["source_id"], "block-table")
        self.assertFalse({"REQUIREMENT", "CONFLICT"} & {item["target_kind"] for item in candidates})

    def test_partial_success_keeps_safe_text_and_quarantines_executable(self) -> None:
        safe = self._upload("safe.txt", "text/plain", b"safe requirements", "safe")
        unsafe = self._upload("pretend.txt", "text/plain", b"MZ" + b"\x00" * 10, "unsafe")
        result = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "process_session", "session_id": self.session_id, "idempotency_key": "workflow-partial"},
        )
        statuses = {asset["asset_id"]: asset["status"] for asset in result["assets"]}
        self.assertEqual(statuses[safe["asset_id"]], AssetStatus.NEEDS_REVIEW.value)
        self.assertEqual(statuses[unsafe["asset_id"]], AssetStatus.QUARANTINED.value)
        self.assertEqual(result["session"]["status"], SessionStatus.NEEDS_REVIEW.value)

    def test_docx_stdlib_parser_emits_paragraph_anchor(self) -> None:
        document = b"""<?xml version='1.0' encoding='UTF-8'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
          <w:body><w:p><w:pPr><w:pStyle w:val='Heading1'/></w:pPr><w:r><w:t>Scope</w:t></w:r></w:p></w:body>
        </w:document>"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", document)
        uploaded = self._upload(
            "scope.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
            "docx",
        )
        parsed = self.runtime.handle(
            WORD,
            self.context,
            {"operation": "process_asset", "asset_id": uploaded["asset_id"], "idempotency_key": "docx-parse"},
        )
        self.assertEqual(parsed["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(parsed["report"]["metadata"]["malware_scan"]["status"], "NOT_RUN")
        self.assertEqual(parsed["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")
        self.assertEqual(parsed["report"]["blocks"], [])

    def test_detection_records_registry_evidence_and_blocks_polyglot(self) -> None:
        data = b"\x89PNG\r\n\x1a\n" + b"x" * 32 + b"PK\x03\x04"
        uploaded = self._upload("pretend.pdf", "application/pdf", data, "polyglot")
        detected = self.runtime.handle(
            DETECT,
            self.context,
            {"operation": "inspect", "asset_id": uploaded["asset_id"]},
        )["detection"]
        self.assertEqual(detected["kind"], "IMAGE")
        self.assertEqual(detected["registry_version"], "elmos-file-types-1.0.0")
        self.assertIn("magic:png", detected["evidence"])
        self.assertIn("FILE_EXTENSION_MISMATCH", detected["findings"])
        self.assertIn("POLYGLOT_SIGNATURES_DETECTED", detected["findings"])
        self.assertEqual(detected["decision"], "QUARANTINE")

    def test_zip_directory_entry_limit_is_checked_before_archive_materialization(self) -> None:
        oversized_directory = struct.pack(
            "<4s4H2LH",
            b"PK\x05\x06",
            0,
            0,
            10_001,
            10_001,
            0,
            0,
            0,
        )
        uploaded = self._upload("many.zip", "application/zip", oversized_directory, "zip-entry-limit")
        detected = self.runtime.handle(
            DETECT,
            self.context,
            {"operation": "inspect", "asset_id": uploaded["asset_id"]},
        )["detection"]
        self.assertEqual(detected["decision"], "QUARANTINE")
        self.assertIn("ARCHIVE_ENTRY_LIMIT_EXCEEDED", detected["findings"])

    def test_word_revisions_comments_and_modes_are_preserved(self) -> None:
        scanner = self._reset_with_clean_malware_scanner("word-revisions")
        document = b"""<?xml version='1.0' encoding='UTF-8'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
          <w:body><w:p><w:r><w:t>Base</w:t></w:r>
          <w:ins w:id='1' w:author='A'><w:r><w:t> Added</w:t></w:r></w:ins>
          <w:del w:id='2' w:author='B'><w:r><w:delText> Removed</w:delText></w:r></w:del>
          </w:p></w:body>
        </w:document>"""
        comments = b"""<w:comments xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
        <w:comment w:id='7' w:author='Reviewer'><w:p><w:r><w:t>Check this</w:t></w:r></w:p></w:comment>
        </w:comments>"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", document)
            archive.writestr("word/comments.xml", comments)
        uploaded = self._upload(
            "review.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
            "docx-revisions",
        )
        final = self.runtime.handle(
            WORD,
            self.context,
            {
                "operation": "process_asset",
                "asset_id": uploaded["asset_id"],
                "revision_mode": "final",
                "idempotency_key": "word-revision-final",
            },
        )["report"]
        original = self.runtime.handle(
            WORD,
            self.context,
            {
                "operation": "process_asset",
                "asset_id": uploaded["asset_id"],
                "revision_mode": "original",
                "idempotency_key": "word-revision-original",
            },
        )["report"]
        self.assertEqual(final["blocks"][0]["text"], "Base Added")
        self.assertEqual(original["blocks"][0]["text"], "Base Removed")
        self.assertEqual(final["metadata"]["parsed_document"]["revision_count"], 2)
        self.assertEqual(final["metadata"]["parsed_document"]["comment_count"], 1)
        self.assertTrue(any(block["payload"].get("review_type") == "COMMENT" for block in final["blocks"]))
        self.assertEqual(
            [call["tool"] for call in scanner.calls],
            [ToolCapability.MALWARE_SCAN.value, ToolCapability.MALWARE_SCAN.value],
        )

    def test_legacy_doc_requires_allowlisted_sandbox_converter(self) -> None:
        uploaded = self._upload(
            "legacy.doc",
            "application/msword",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16,
            "legacy-doc",
        )
        parsed = self.runtime.handle(
            WORD,
            self.context,
            {
                "operation": "process_asset",
                "asset_id": uploaded["asset_id"],
                "revision_mode": "all",
                "idempotency_key": "legacy-word-parse",
            },
        )
        self.assertEqual(parsed["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(parsed["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")

    def test_malware_scan_proof_is_honest_when_scanner_is_unconfigured(self) -> None:
        uploaded = self._upload("safe.txt", "text/plain", b"safe", "scan-not-run")
        result = self.runtime.handle(
            MALWARE,
            self.context,
            {"operation": "inspect", "asset_id": uploaded["asset_id"], "idempotency_key": "malware-inspect"},
        )
        self.assertEqual(result["scan_proof"]["status"], "NOT_RUN")
        self.assertEqual(result["scan_proof"]["verdict"], "NOT_RUN")
        self.assertEqual(result["detection"]["decision"], "NEEDS_REVIEW")

    def test_bool_like_sandbox_receipt_cannot_grant_malware_clearance(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        self.runtime = create_runtime(
            root / "bool-like-scan.sqlite3",
            root / "bool-like-scan-cas",
            sandbox_executor=BoolLikeSandbox(),
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan")
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-bool-like-scan"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "bool-like-scan-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload(
            "bool-like.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 8,
            "bool-like-scan",
        )

        result = self.runtime.handle(
            MALWARE,
            self.context,
            {
                "operation": "inspect",
                "asset_id": image["asset_id"],
                "idempotency_key": "bool-like-malware-inspect",
            },
        )

        self.assertEqual(result["scan_proof"]["status"], "FAILED")
        self.assertEqual(result["scan_proof"]["error_code"], "SANDBOX_RECEIPT_INVALID")
        self.assertIs(result["scan_proof"]["clearance_granted"], False)
        self.assertEqual(result["scan_proof"]["clearance_reason"], "MALWARE_SCAN_NOT_PASSED")
        self.assertEqual(result["detection"]["decision"], "NEEDS_REVIEW")

    def test_workflow_reaches_ready_only_with_clean_sandbox_scan(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox(json.dumps({"verdict": "CLEAN", "findings": []}).encode())
        self.runtime = create_runtime(
            root / "clean-scan.sqlite3",
            root / "clean-scan-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan")
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-clean-scan"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "clean-scan-session"},
        )
        self.session_id = created["session_id"]
        uploaded = self._upload("clean.md", "text/markdown", b"# Clean\n", "clean-scan")
        result = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {
                "operation": "process_session",
                "session_id": self.session_id,
                "idempotency_key": "clean-scan-process",
            },
        )
        self.assertEqual(result["session"]["status"], SessionStatus.READY.value)
        self.assertEqual(result["reports"][uploaded["asset_id"]]["status"], "PASSED")
        self.assertEqual(executor.calls[0]["tool"], ToolCapability.MALWARE_SCAN.value)
        scan_receipt = result["reports"][uploaded["asset_id"]]["metadata"]["malware_scan"]["receipt"]
        self.assertEqual(scan_receipt["executable"], "elmos-malware-scan")
        self.assertNotIn("/opt/elmos/bin", json.dumps(result, sort_keys=True))

    def test_durable_scan_precheckpoint_crashes_reconcile_without_rerun(self) -> None:
        class InjectedProcessCrash(BaseException):
            pass

        root = Path(self.temporary.name)
        for fault in ("provider-in-flight", "before-checkpoint"):
            with self.subTest(fault=fault):
                self.runtime.close()
                executor = RecordingSandbox(
                    json.dumps({"verdict": "CLEAN", "findings": []}).encode()
                )
                self.runtime = create_runtime(
                    root / f"scan-{fault}.sqlite3",
                    root / f"scan-{fault}-cas",
                    sandbox_executor=executor,
                    provisioned_tools={
                        ToolCapability.MALWARE_SCAN: provisioned(
                            "/private/host-only/scanners/elmos-malware-scan"
                        )
                    },
                    upload_policy=UploadPolicy(
                        default_part_size=64,
                        maximum_part_size=64,
                    ),
                )
                self.runtime.handle(
                    ORCHESTRATOR,
                    self.context,
                    {
                        "operation": "bootstrap_project",
                        "idempotency_key": f"bootstrap-scan-{fault}",
                    },
                )
                created = self.runtime.handle(
                    ORCHESTRATOR,
                    self.context,
                    {
                        "operation": "create_session",
                        "idempotency_key": f"session-scan-{fault}",
                    },
                )
                self.session_id = created["session_id"]
                uploaded = self._upload(
                    f"{fault}.md",
                    "text/markdown",
                    f"# {fault}\n".encode(),
                    f"scan-{fault}",
                )
                recovery_context = TenantContext(
                    self.context.tenant_id,
                    self.context.project_id,
                    f"recovery-{fault}@example.test",
                )
                self.runtime.store.grant_permissions(
                    self.context,
                    recovery_context.actor_id,
                    [self.runtime.store.READ, self.runtime.store.WRITE],
                )

                provider_invocations = 0
                original_run = self.runtime.providers.run
                original_save = self.runtime.store.save_job_effect_receipt

                def crash_at_provider_boundary(*args: object, **kwargs: object):
                    nonlocal provider_invocations
                    provider_invocations += 1
                    if fault == "provider-in-flight":
                        raise InjectedProcessCrash("provider response is unknown")
                    return original_run(*args, **kwargs)

                def crash_before_checkpoint(*args: object, **kwargs: object):
                    if fault == "before-checkpoint":
                        raise InjectedProcessCrash("validated response not checkpointed")
                    return original_save(*args, **kwargs)

                with (
                    patch.object(
                        self.runtime.providers,
                        "run",
                        crash_at_provider_boundary,
                    ),
                    patch.object(
                        self.runtime.store,
                        "save_job_effect_receipt",
                        crash_before_checkpoint,
                    ),
                ):
                    with self.assertRaises(InjectedProcessCrash):
                        self.runtime.workflow.process_session(
                            self.context,
                            session_id=self.session_id,
                            idempotency_key=f"process-scan-{fault}",
                        )
                    job_row = self.runtime.store._connection.execute(
                        "SELECT job_id,stage FROM processing_jobs WHERE session_id=?",
                        (self.session_id,),
                    ).fetchone()
                    self.assertEqual(
                        job_row["stage"],
                        f"external-effect:{uploaded['asset_id']}:malware-scan",
                    )
                    inner = self.runtime.store._connection.execute(
                        """
                        SELECT status,dispatch_started_at,response_json,response_digest
                          FROM skill_execution_receipts WHERE skill=?
                        """,
                        (self.runtime.workflow.MALWARE_EFFECT_SKILL,),
                    ).fetchone()
                    self.assertEqual(inner["status"], "IN_PROGRESS")
                    self.assertIsNotNone(inner["dispatch_started_at"])
                    self.assertIsNone(inner["response_json"])
                    self.assertIsNone(inner["response_digest"])
                    effect_key = self.runtime.store.job_effect_stage_key(
                        job_row["job_id"],
                        str(job_row["stage"]),
                    )
                    checkpoint_count = self.runtime.store._connection.execute(
                        """
                        SELECT count(*) FROM processing_checkpoints
                         WHERE job_id=? AND stage_key=?
                        """,
                        (job_row["job_id"], effect_key),
                    ).fetchone()[0]
                    self.assertEqual(checkpoint_count, 0)
                    self.runtime.store._connection.execute(
                        "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
                        ("2000-01-01T00:00:00+00:00", job_row["job_id"]),
                    )
                    resumed = self.runtime.workflow.resume_job(
                        recovery_context,
                        job_row["job_id"],
                    )
                self.assertEqual(resumed.job.status, JobStatus.BLOCKED)
                self.assertEqual(
                    resumed.job.failure_code,
                    "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
                )
                self.assertEqual(provider_invocations, 1)
                self.assertEqual(
                    len(executor.calls),
                    0 if fault == "provider-in-flight" else 1,
                )

    def test_workflow_replays_durable_scan_after_crash_without_rescanning(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox(json.dumps({"verdict": "CLEAN", "findings": []}).encode())
        self.runtime = create_runtime(
            root / "scan-crash.sqlite3",
            root / "scan-crash-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned(
                    "/private/host-only/scanners/elmos-malware-scan"
                )
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-scan-crash"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "scan-crash-session"},
        )
        self.session_id = created["session_id"]
        recovery_context = TenantContext(
            self.context.tenant_id,
            self.context.project_id,
            "recovery-writer@example.test",
        )
        self.runtime.store.grant_permissions(
            self.context,
            recovery_context.actor_id,
            [self.runtime.store.READ, self.runtime.store.WRITE],
        )
        uploaded = self._upload("crash.md", "text/markdown", b"# Durable scanner\n", "scan-crash")

        class InjectedProcessCrash(BaseException):
            pass

        original_complete = self.runtime.store.complete_skill_execution
        injected = {"raised": False}

        def crash_before_inner_completion(*args: object, **kwargs: object):
            if (
                kwargs.get("skill") == self.runtime.workflow.MALWARE_EFFECT_SKILL
                and not injected["raised"]
            ):
                injected["raised"] = True
                raise InjectedProcessCrash("fault after job checkpoint commit")
            return original_complete(*args, **kwargs)

        with patch.object(
            self.runtime.store,
            "complete_skill_execution",
            crash_before_inner_completion,
        ):
            with self.assertRaises(InjectedProcessCrash):
                self.runtime.workflow.process_session(
                    self.context,
                    session_id=self.session_id,
                    idempotency_key="scan-crash-process",
                )

        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value],
        )
        job_row = self.runtime.store._connection.execute(
            "SELECT job_id,stage FROM processing_jobs WHERE session_id=?",
            (self.session_id,),
        ).fetchone()
        self.assertEqual(
            job_row["stage"],
            f"external-effect:{uploaded['asset_id']}:malware-scan",
        )
        effect_row = self.runtime.store._connection.execute(
            """
            SELECT status,response_json,response_digest,dispatch_started_at
              FROM skill_execution_receipts
             WHERE skill=?
            """,
            (self.runtime.workflow.MALWARE_EFFECT_SKILL,),
        ).fetchone()
        self.assertEqual(effect_row["status"], "IN_PROGRESS")
        self.assertIsNone(effect_row["response_json"])
        self.assertIsNone(effect_row["response_digest"])
        self.assertIsNotNone(effect_row["dispatch_started_at"])
        checkpoint_row = self.runtime.store._connection.execute(
            """
            SELECT payload_json FROM processing_checkpoints
             WHERE job_id=? AND stage_key=?
            """,
            (
                job_row["job_id"],
                self.runtime.store.job_effect_stage_key(
                    job_row["job_id"],
                    f"external-effect:{uploaded['asset_id']}:malware-scan",
                ),
            ),
        ).fetchone()
        self.assertNotIn("/private/host-only", checkpoint_row["payload_json"])
        checkpoint_receipt = json.loads(checkpoint_row["payload_json"])
        with self.assertRaisesRegex(IntegrityError, "MALWARE_SCAN_EFFECT_RECEIPT_CORRUPT"):
            self.runtime.workflow._malware_result_from_effect_receipt(
                200,
                checkpoint_receipt,
                request_digest=checkpoint_receipt["request_digest"],
                policy_digest="b" * 64,
            )
        self.assertEqual(len(executor.calls), 1)

        self.runtime.store._connection.execute(
            "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", job_row["job_id"]),
        )
        resumed = self.runtime.workflow.resume_job(recovery_context, job_row["job_id"])
        self.assertEqual(resumed.session.status, SessionStatus.READY)
        self.assertEqual(resumed.reports[str(uploaded["asset_id"])].status, ResultStatus.PASSED)
        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value],
        )

    def test_workflow_replays_durable_parser_effect_after_crash_without_rebilling(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox(
            {
                ToolCapability.MALWARE_SCAN.value: json.dumps(
                    {"verdict": "CLEAN", "findings": []}
                ).encode(),
                ToolCapability.OCR.value: json.dumps(
                    {
                        "regions": [
                            {
                                "text": "durable OCR",
                                "bbox": [0.1, 0.1, 0.8, 0.2],
                                "confidence": 0.99,
                            }
                        ]
                    }
                ).encode(),
            }
        )
        self.runtime = create_runtime(
            root / "parser-crash.sqlite3",
            root / "parser-crash-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned(
                    "/private/host-only/scanners/elmos-malware-scan"
                ),
                ToolCapability.OCR: provisioned(
                    "/opt/elmos/bin/tesseract"
                ),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-parser-crash"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "parser-crash-session"},
        )
        self.session_id = created["session_id"]
        uploaded = self._upload(
            "durable.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 16,
            "parser-crash",
        )
        recovery_context = TenantContext(
            self.context.tenant_id,
            self.context.project_id,
            "parser-recovery@example.test",
        )
        self.runtime.store.grant_permissions(
            self.context,
            recovery_context.actor_id,
            [self.runtime.store.READ, self.runtime.store.WRITE],
        )

        class InjectedProcessCrash(BaseException):
            pass

        original_complete = self.runtime.store.complete_skill_execution
        injected = {"raised": False}

        def crash_after_parser_checkpoint(*args: object, **kwargs: object):
            if (
                kwargs.get("skill") == self.runtime.workflow.PARSER_EFFECT_SKILL
                and not injected["raised"]
            ):
                injected["raised"] = True
                raise InjectedProcessCrash("parser result checkpointed before inner receipt")
            return original_complete(*args, **kwargs)

        with patch.object(
            self.runtime.store,
            "complete_skill_execution",
            crash_after_parser_checkpoint,
        ):
            with self.assertRaises(InjectedProcessCrash):
                self.runtime.workflow.process_session(
                    self.context,
                    session_id=self.session_id,
                    idempotency_key="parser-crash-process",
                )

        job_row = self.runtime.store._connection.execute(
            "SELECT job_id,stage FROM processing_jobs WHERE session_id=?",
            (self.session_id,),
        ).fetchone()
        self.assertEqual(
            job_row["stage"],
            f"external-effect:{uploaded['asset_id']}:ocr",
        )
        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value, ToolCapability.OCR.value],
        )
        self.runtime.store._connection.execute(
            "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", job_row["job_id"]),
        )
        resumed = self.runtime.workflow.resume_job(recovery_context, job_row["job_id"])
        self.assertEqual(resumed.session.status, SessionStatus.READY)
        self.assertEqual(
            resumed.reports[str(uploaded["asset_id"])].status,
            ResultStatus.PASSED,
        )
        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value, ToolCapability.OCR.value],
        )

    def test_running_provider_effect_finishes_receipt_then_honors_cancellation(self) -> None:
        class BlockingSandbox(RecordingSandbox):
            def __init__(self) -> None:
                super().__init__(b"")
                self.ocr_started = threading.Event()
                self.release_ocr = threading.Event()

            def execute(self, **request: object) -> CommandReceipt:
                self.calls.append(dict(request))
                tool = str(request["tool"])
                if tool == ToolCapability.OCR.value:
                    self.ocr_started.set()
                    if not self.release_ocr.wait(timeout=10):
                        raise RuntimeError("test did not release OCR provider")
                    stdout = json.dumps(
                        {
                            "regions": [
                                {
                                    "text": "cancelled after exact receipt",
                                    "bbox": [0.1, 0.1, 0.8, 0.2],
                                    "confidence": 0.99,
                                }
                            ]
                        }
                    ).encode()
                else:
                    stdout = json.dumps({"verdict": "CLEAN", "findings": []}).encode()
                return CommandReceipt(
                    tool=tool,
                    executable_sha256="a" * 64,
                    exit_code=0,
                    stdout=stdout,
                    duration_ms=7,
                    sandboxed=True,
                    network_allowed=False,
                )

        root = Path(self.temporary.name)
        self.runtime.close()
        executor = BlockingSandbox()
        self.runtime = create_runtime(
            root / "cancel-effect.sqlite3",
            root / "cancel-effect-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned(
                    "/private/host-only/scanners/elmos-malware-scan"
                ),
                ToolCapability.OCR: provisioned(
                    "/opt/elmos/bin/tesseract"
                ),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-cancel-effect"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "cancel-effect-session"},
        )
        self.session_id = created["session_id"]
        self._upload(
            "cancel-one.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"1" * 16,
            "cancel-one",
        )
        self._upload(
            "cancel-two.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"2" * 16,
            "cancel-two",
        )
        outcome: list[object] = []

        def process() -> None:
            try:
                outcome.append(
                    self.runtime.workflow.process_session(
                        self.context,
                        session_id=self.session_id,
                        idempotency_key="cancel-effect-process",
                    )
                )
            except BaseException as error:  # pragma: no cover - asserted below
                outcome.append(error)

        worker = threading.Thread(target=process, daemon=True)
        worker.start()
        self.assertTrue(executor.ocr_started.wait(timeout=10))
        job = self.runtime.store._connection.execute(
            "SELECT job_id FROM processing_jobs WHERE session_id=?",
            (self.session_id,),
        ).fetchone()
        requested = self.runtime.workflow.cancel_job(self.context, job["job_id"])
        self.assertEqual(requested.job.status, JobStatus.RUNNING)
        self.assertTrue(
            self.runtime.store.job_cancellation_requested(self.context, job["job_id"])
        )
        executor.release_ocr.set()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertFalse(isinstance(outcome[0], BaseException), repr(outcome[0]))
        result = outcome[0]
        self.assertEqual(result.job.status, JobStatus.CANCELLED)  # type: ignore[union-attr]
        self.assertEqual(result.session.status, SessionStatus.CANCELLED)  # type: ignore[union-attr]
        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value, ToolCapability.OCR.value],
        )
        receipt = self.runtime.store._connection.execute(
            "SELECT status,response_json FROM skill_execution_receipts WHERE skill=?",
            (self.runtime.workflow.PARSER_EFFECT_SKILL,),
        ).fetchone()
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertIsNotNone(receipt["response_json"])

    def test_terminal_job_wins_before_cancel_without_rewriting_session(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="terminal-before-cancel-job",
            request_digest=hashlib.sha256(b"terminal-before-cancel").hexdigest(),
        )
        owner = "terminal-before-cancel-owner"
        self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token=owner,
        )
        terminal, session = self.runtime.store.finalize_job_and_session(
            self.context,
            job.job_id,
            session_status=SessionStatus.READY,
            status=JobStatus.COMPLETED,
            stage="completed",
            result_status=ResultStatus.PASSED,
            lease_owner=owner,
        )
        self.assertEqual(terminal.status, JobStatus.COMPLETED)
        self.assertEqual(session.status, SessionStatus.READY)

        cancelled = self.runtime.workflow.cancel_job(
            self.context,
            job.job_id,
            reason="OPERATOR_REQUEST",
        )
        self.assertEqual(cancelled.job.status, JobStatus.COMPLETED)
        self.assertEqual(cancelled.session.status, SessionStatus.READY)
        self.assertFalse(cancelled.job.cancel_requested)
        self.assertIsNone(cancelled.job.cancel_requested_by)
        self.assertIsNone(cancelled.job.cancel_requested_at)
        self.assertIsNone(cancelled.job.cancel_reason)

    def test_cancel_and_terminalization_share_one_authoritative_writer_fence(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="cancel-terminal-race-job",
            request_digest=hashlib.sha256(b"cancel-terminal-race").hexdigest(),
        )
        owner = "cancel-terminal-race-owner"
        running = self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token=owner,
        )
        self.runtime.store.update_session_status(
            self.context,
            running.session_id,
            SessionStatus.PROCESSING,
        )
        barrier = threading.Barrier(2)
        outcomes: list[object] = []

        def terminalize() -> None:
            try:
                barrier.wait(timeout=10)
                outcomes.append(
                    self.runtime.store.finalize_job_and_session(
                        self.context,
                        job.job_id,
                        session_status=SessionStatus.READY,
                        status=JobStatus.COMPLETED,
                        stage="completed",
                        result_status=ResultStatus.PASSED,
                        lease_owner=owner,
                    )
                )
            except BaseException as error:  # pragma: no cover - asserted below
                outcomes.append(error)

        def cancel() -> None:
            try:
                barrier.wait(timeout=10)
                outcomes.append(
                    self.runtime.workflow.cancel_job(
                        self.context,
                        job.job_id,
                        reason="CONCURRENT_OPERATOR_REQUEST",
                    )
                )
            except BaseException as error:  # pragma: no cover - asserted below
                outcomes.append(error)

        workers = [
            threading.Thread(target=terminalize, daemon=True),
            threading.Thread(target=cancel, daemon=True),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes), 2)
        self.assertFalse(
            any(isinstance(outcome, BaseException) for outcome in outcomes),
            repr(outcomes),
        )

        final_job = self.runtime.store.get_job(self.context, job.job_id)
        final_session = self.runtime.store.get_session(self.context, self.session_id)
        pair = (final_job.status, final_session.status, final_job.cancel_requested)
        self.assertIn(
            pair,
            {
                (JobStatus.COMPLETED, SessionStatus.READY, False),
                (JobStatus.CANCELLED, SessionStatus.CANCELLED, True),
            },
        )
        if final_job.cancel_requested:
            self.assertEqual(final_job.cancel_requested_by, self.context.actor_id)
            self.assertIsNotNone(final_job.cancel_requested_at)
            self.assertEqual(final_job.cancel_reason, "CONCURRENT_OPERATOR_REQUEST")

    def test_cancel_reclaims_legacy_dispatch_crash_as_safe_internal_retry(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="cancel-dispatch-crash-job",
            request_digest=hashlib.sha256(b"cancel-dispatch-crash-job").hexdigest(),
        )
        request = {
            "operation": "cancel_job",
            "job_id": job.job_id,
            "reason": "CRASH_RECOVERY_REQUEST",
            "idempotency_key": "cancel-dispatch-crash-request",
        }
        receipt_skill = self.runtime._receipt_skill(ORCHESTRATOR, "cancel_job")
        request_digest = canonical_digest(
            {
                "schema_version": "1.0.0",
                "tenant_id": self.context.tenant_id,
                "project_id": self.context.project_id,
                "actor_id": self.context.actor_id,
                "skill": ORCHESTRATOR,
                "operation": "cancel_job",
                "payload": self.runtime._receipt_payload_identity(request),
            }
        )
        state, replay = self.runtime.store.claim_skill_execution(
            self.context,
            skill=receipt_skill,
            idempotency_key=request["idempotency_key"],
            request_digest=request_digest,
            owner_token="legacy-cancel-dispatch-owner",
            lease_seconds=300,
        )
        self.assertEqual((state, replay), ("CLAIMED", None))
        self.runtime.store.mark_skill_execution_dispatched(
            self.context,
            skill=receipt_skill,
            idempotency_key=request["idempotency_key"],
            request_digest=request_digest,
            owner_token="legacy-cancel-dispatch-owner",
        )

        recovered = self.runtime.handle(ORCHESTRATOR, self.context, request)
        self.assertEqual(recovered["job"]["status"], JobStatus.CANCELLED.value)
        self.assertEqual(recovered["session"]["status"], SessionStatus.CANCELLED.value)
        self.assertEqual(
            self.runtime.handle(ORCHESTRATOR, self.context, request),
            recovered,
        )
        receipt = self.runtime.store._connection.execute(
            """
            SELECT status,dispatch_started_at,response_json
              FROM skill_execution_receipts
             WHERE tenant_id=? AND project_id=? AND actor_id=?
               AND skill=? AND idempotency_key=?
            """,
            (
                self.context.tenant_id,
                self.context.project_id,
                self.context.actor_id,
                receipt_skill,
                request["idempotency_key"],
            ),
        ).fetchone()
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertIsNone(receipt["dispatch_started_at"])
        self.assertIsNotNone(receipt["response_json"])

    def test_cancel_metadata_is_actor_bound_audited_and_cannot_be_reset(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="cancel-audit-job",
            request_digest=hashlib.sha256(b"cancel-audit-job").hexdigest(),
        )
        outcome = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {
                "operation": "cancel_job",
                "job_id": job.job_id,
                "reason": "USER_ABORTED_UPLOAD",
                "idempotency_key": "cancel-audit-request",
            },
        )
        self.assertEqual(outcome["job"]["status"], JobStatus.CANCELLED.value)
        persisted = self.runtime.store.get_job(self.context, job.job_id)
        self.assertTrue(persisted.cancel_requested)
        self.assertEqual(persisted.cancel_requested_by, self.context.actor_id)
        self.assertIsNotNone(persisted.cancel_requested_at)
        self.assertEqual(persisted.cancel_reason, "USER_ABORTED_UPLOAD")
        event = self.runtime.store._connection.execute(
            """
            SELECT payload_json FROM outbox_events
             WHERE tenant_id=? AND project_id=? AND aggregate_id=?
               AND event_type='processing.job.cancellation_requested'
            """,
            (self.context.tenant_id, self.context.project_id, job.job_id),
        ).fetchone()
        self.assertIsNotNone(event)
        payload = json.loads(event["payload_json"])
        self.assertEqual(payload["actor_id"], self.context.actor_id)
        self.assertEqual(payload["reason"], "USER_ABORTED_UPLOAD")
        with self.assertRaises(sqlite3.IntegrityError):
            self.runtime.store._connection.execute(
                """
                UPDATE processing_jobs
                   SET cancel_requested=0,cancel_requested_by=NULL,
                       cancel_requested_at=NULL,cancel_reason=NULL
                 WHERE job_id=?
                """,
                (job.job_id,),
            )

    def test_v23_cancellation_schema_rejects_same_name_noop_trigger_tamper(self) -> None:
        database = Path(self.temporary.name) / "intake.sqlite3"
        cas = Path(self.temporary.name) / "cas"
        self.runtime.close()
        connection = sqlite3.connect(database)
        try:
            connection.execute("DROP TRIGGER processing_jobs_cancellation_metadata_guard")
            connection.execute(
                """
                CREATE TRIGGER processing_jobs_cancellation_metadata_guard
                BEFORE UPDATE OF cancel_requested ON processing_jobs
                FOR EACH ROW BEGIN SELECT 1; END
                """
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(
            IntegrityError,
            "PROCESSING_JOB_CANCELLATION_SCHEMA_INVALID",
        ):
            create_runtime(database, cas)

    def test_v23_cancellation_migration_is_exactly_mirrored(self) -> None:
        engine_root = Path(__file__).resolve().parents[1]
        outer = engine_root / "migrations/023_processing_job_cancellation.sql"
        packaged = (
            engine_root
            / "src/elmos_multimodal_intake/migrations/023_processing_job_cancellation.sql"
        )
        self.assertEqual(outer.read_bytes(), packaged.read_bytes())
        sql = outer.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN cancel_requested_by TEXT", sql)
        self.assertIn("ADD COLUMN cancel_requested_at TEXT", sql)
        self.assertIn("ADD COLUMN cancel_reason TEXT", sql)
        self.assertIn("processing_jobs_cancellation_metadata_guard", sql)
        self.assertIn("OLD.cancel_requested = 1", sql)
        self.assertIn("PRAGMA user_version = 23", sql)

    def test_external_parsers_are_honest_when_sandbox_is_not_configured(self) -> None:
        pdf = self._upload("scan.pdf", "application/pdf", b"%PDF-1.4\n%%EOF\n", "pdf")
        image = self._upload("screen.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 8, "image")
        audio = self._upload("note.wav", "audio/wav", b"RIFF\x00\x00\x00\x00WAVE", "audio")
        pdf_result = self.runtime.handle(
            PDF,
            self.context,
            {"operation": "process_asset", "asset_id": pdf["asset_id"], "idempotency_key": "pdf-parse"},
        )
        image_result = self.runtime.handle(
            IMAGE,
            self.context,
            {"operation": "process_asset", "asset_id": image["asset_id"], "idempotency_key": "image-parse"},
        )
        audio_result = self.runtime.handle(
            AUDIO,
            self.context,
            {"operation": "process_asset", "asset_id": audio["asset_id"], "idempotency_key": "audio-parse"},
        )
        self.assertEqual(pdf_result["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(image_result["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(audio_result["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(pdf_result["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")
        self.assertEqual(image_result["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")
        self.assertEqual(audio_result["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")

    def test_invalid_scanner_json_cannot_clear_or_invoke_complex_parser(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox(
            {
                ToolCapability.MALWARE_SCAN.value: (
                    b'{"verdict":"MALICIOUS","verdict":"CLEAN","findings":[]}'
                ),
                ToolCapability.OCR.value: json.dumps(
                    {"regions": [{"text": "must not execute", "bbox": [0, 0, 1, 1]}]}
                ).encode(),
            }
        )
        self.runtime = create_runtime(
            root / "invalid-scan.sqlite3",
            root / "invalid-scan-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan"),
                ToolCapability.OCR: provisioned("/opt/elmos/bin/tesseract"),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-invalid-scan"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "invalid-scan-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload(
            "blocked.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 8,
            "invalid-scan",
        )
        result = self.runtime.handle(
            IMAGE,
            self.context,
            {
                "operation": "process_asset",
                "asset_id": image["asset_id"],
                "idempotency_key": "invalid-scan-process",
            },
        )
        self.assertEqual(result["report"]["status"], "NEEDS_REVIEW")
        self.assertEqual(result["report"]["error_code"], "MALWARE_CLEARANCE_REQUIRED")
        self.assertEqual(result["report"]["metadata"]["malware_scan"]["status"], "FAILED")
        self.assertEqual(
            [call["tool"] for call in executor.calls],
            [ToolCapability.MALWARE_SCAN.value],
        )

    def test_fixed_tool_arguments_and_receipt_back_real_ocr(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox({
            ToolCapability.MALWARE_SCAN.value: json.dumps({"verdict": "CLEAN", "findings": []}).encode(),
            ToolCapability.OCR.value: json.dumps(
                {"regions": [{"text": "Login", "bbox": [1, 2, 30, 10], "confidence": 0.9}]}
            ).encode(),
        })
        self.runtime = create_runtime(
            root / "configured.sqlite3",
            root / "configured-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan"),
                ToolCapability.OCR: provisioned("/opt/elmos/bin/tesseract"),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-configured"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "configured-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload("ui.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 8, "real-ocr")
        parsed = self.runtime.handle(
            IMAGE,
            self.context,
            {"operation": "process_asset", "asset_id": image["asset_id"], "idempotency_key": "real-ocr-parse"},
        )
        self.assertEqual(parsed["report"]["status"], "PASSED")
        ocr_call = next(call for call in executor.calls if call["tool"] == ToolCapability.OCR.value)
        self.assertEqual(ocr_call["argv"], ("stdin", "stdout", "--psm", "6"))
        self.assertEqual(parsed["report"]["blocks"][1]["text"], "Login")
        receipt = parsed["report"]["provider_receipt"]
        self.assertEqual(receipt["input_sha256"], image["asset"]["sha256"])
        self.assertEqual(receipt["input_bytes"], image["asset"]["byte_size"])
        self.assertEqual(receipt["media_type"], "image/png")
        self.assertEqual(receipt["argv"], ["stdin", "stdout", "--psm", "6"])
        self.assertEqual(len(receipt["policy_sha256"]), 64)
        self.assertEqual(receipt["job_id"], "direct")
        self.assertEqual(receipt["stage"], "direct-process_asset-parse:ocr")
        self.assertEqual(receipt["executable"], "tesseract")
        self.assertNotIn("/opt/elmos/bin", json.dumps(parsed, sort_keys=True))

    def test_visual_provider_output_is_schema_validated_and_source_anchored(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox({
            ToolCapability.MALWARE_SCAN.value: json.dumps({"verdict": "CLEAN", "findings": []}).encode(),
            ToolCapability.VISUAL_UI.value: json.dumps(
                {
                    "target_platform": "web",
                    "elements": [
                        {
                            "id": "button-1",
                            "type": "BUTTON",
                            "label": "Continue",
                            "parent_id": None,
                            "bbox": [10, 20, 100, 40],
                            "basis": "OBSERVED",
                            "confidence": 0.97,
                        }
                    ],
                    "assumptions": [],
                }
            ).encode(),
        })
        self.runtime = create_runtime(
            root / "visual.sqlite3",
            root / "visual-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan"),
                ToolCapability.VISUAL_UI: provisioned("/opt/elmos/bin/elmos-ui-vision"),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-visual"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "visual-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload("ui.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 8, "visual")
        result = self.runtime.handle(
            VISUAL,
            self.context,
            {"operation": "understand", "asset_id": image["asset_id"], "idempotency_key": "visual-understand"},
        )["provider_result"]
        self.assertEqual(result["status"], "PASSED")
        element = result["payload"]["elements"][0]
        self.assertEqual(element["source_anchor"]["asset_id"], image["asset_id"])
        self.assertEqual(result["payload"]["visual_regression"], "NOT_RUN")

    def test_generation_digest_report_replay_and_asset_version_are_bound(self) -> None:
        uploaded = self._upload("generation.md", "text/markdown", b"# Generation\n", "generation")
        asset_id = str(uploaded["asset_id"])
        generation = hashlib.sha256(asset_id.encode("utf-8")).hexdigest()
        request = {
            "operation": "process_session",
            "session_id": self.session_id,
            "idempotency_key": "generation-process",
            "expected_asset_generation_digest": generation,
        }
        first = self.runtime.handle(ORCHESTRATOR, self.context, request)
        replayed = self.runtime.handle(ORCHESTRATOR, self.context, request)
        self.assertEqual(first, replayed)
        resumed = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {
                "operation": "resume_job",
                "job_id": first["job_id"],
                "idempotency_key": "generation-resume",
            },
        )
        self.assertEqual(
            resumed["reports"][asset_id]["metadata"],
            first["reports"][asset_id]["metadata"],
        )
        self.assertEqual(
            resumed["reports"][asset_id]["provider_receipt"],
            first["reports"][asset_id]["provider_receipt"],
        )
        final_asset = next(item for item in first["assets"] if item["asset_id"] == asset_id)
        stored_versions = {
            row["asset_version"]
            for row in self.runtime.store._connection.execute(
                "SELECT asset_version FROM content_blocks WHERE asset_id=?",
                (asset_id,),
            ).fetchall()
        }
        self.assertEqual(stored_versions, {final_asset["version"]})
        report_row = self.runtime.store._connection.execute(
            "SELECT report_json,report_sha256 FROM asset_parse_reports WHERE asset_id=?",
            (asset_id,),
        ).fetchone()
        self.assertEqual(
            hashlib.sha256(report_row["report_json"].encode("utf-8")).hexdigest(),
            report_row["report_sha256"],
        )
        self.runtime.store._connection.execute(
            "UPDATE content_blocks SET text_content=? WHERE asset_id=?",
            ("tampered-content", asset_id),
        )
        with self.assertRaises(IntegrityError):
            self.runtime.store.load_asset_report(
                self.context,
                self.runtime.store.get_asset(self.context, asset_id),
            )
        mismatch = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {
                **request,
                "idempotency_key": "generation-mismatch",
                "expected_asset_generation_digest": "0" * 64,
            },
        )
        self.assertEqual(mismatch["state"], "BLOCKED")
        self.assertEqual(mismatch["code"], "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED")
        self.assertFalse(mismatch["retryable"])

    def test_job_claim_lease_blocks_concurrent_owner_and_allows_expired_takeover(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="lease-job",
            request_digest="b" * 64,
            max_attempts=3,
        )
        claimed = self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token="worker-owner-one",
            lease_seconds=300,
        )
        self.assertEqual(claimed.attempt, 1)
        with self.assertRaises(ConflictError):
            self.runtime.store.claim_job(
                self.context,
                job.job_id,
                owner_token="worker-owner-two",
                lease_seconds=300,
            )
        self.runtime.store._connection.execute(
            "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", job.job_id),
        )
        taken_over = self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token="worker-owner-two",
            lease_seconds=300,
        )
        self.assertEqual(taken_over.attempt, 2)
        with self.assertRaises(ConflictError):
            self.runtime.store.update_job(
                self.context,
                job.job_id,
                status=JobStatus.COMPLETED,
                stage="completed",
                result_status=ResultStatus.PASSED,
                lease_owner="worker-owner-one",
            )
        completed = self.runtime.store.update_job(
            self.context,
            job.job_id,
            status=JobStatus.COMPLETED,
            stage="completed",
            result_status=ResultStatus.PASSED,
            lease_owner="worker-owner-two",
        )
        self.assertEqual(completed.status, JobStatus.COMPLETED)

    def test_expired_external_effect_stage_requires_reconciliation_instead_of_takeover(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="external-stage-job",
            request_digest="c" * 64,
            max_attempts=3,
        )
        self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token="external-stage-owner-one",
            stage="external-effect:asset-example:ocr",
            lease_seconds=300,
        )
        self.runtime.store._connection.execute(
            "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", job.job_id),
        )
        blocked = self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token="external-stage-owner-two",
            lease_seconds=300,
        )
        self.assertEqual(blocked.status, JobStatus.BLOCKED)
        self.assertEqual(blocked.failure_code, "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED")

    def test_job_effect_receipt_is_lease_fenced_cross_actor_and_immutable(self) -> None:
        job = self.runtime.store.create_job(
            self.context,
            self.session_id,
            idempotency_key="effect-receipt-job",
            request_digest="d" * 64,
            max_attempts=3,
        )
        first_owner = "effect-receipt-owner-one"
        self.runtime.store.claim_job(
            self.context,
            job.job_id,
            owner_token=first_owner,
            stage="external-effect:asset-example:malware-scan",
            lease_seconds=300,
        )
        stage_key = self.runtime.store.job_effect_stage_key(
            job.job_id,
            "external-effect:asset-example:malware-scan",
        )
        receipt = {
            "schema_version": "effect-test-v1",
            "request_digest": "a" * 64,
        }
        with self.assertRaises(ConflictError):
            self.runtime.store.save_job_effect_receipt(
                self.context,
                job.job_id,
                stage_key,
                receipt,
                lease_owner="wrong-effect-owner",
            )
        digest = self.runtime.store.save_job_effect_receipt(
            self.context,
            job.job_id,
            stage_key,
            receipt,
            lease_owner=first_owner,
        )
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            self.runtime.store.load_job_effect_receipt(
                self.context,
                job.job_id,
                stage_key,
                lease_owner=first_owner,
            ),
            receipt,
        )

        self.runtime.store._connection.execute(
            "UPDATE processing_jobs SET lease_expires_at=? WHERE job_id=?",
            ("2000-01-01T00:00:00+00:00", job.job_id),
        )
        recovery = TenantContext(
            self.context.tenant_id,
            self.context.project_id,
            "effect-recovery@example.test",
        )
        self.runtime.store.grant_permissions(
            self.context,
            recovery.actor_id,
            [self.runtime.store.READ, self.runtime.store.WRITE],
        )
        second_owner = "effect-receipt-owner-two"
        self.runtime.store.claim_job(
            recovery,
            job.job_id,
            owner_token=second_owner,
            stage="external-effect:asset-example:malware-scan",
            lease_seconds=300,
        )
        self.assertEqual(
            self.runtime.store.load_job_effect_receipt(
                recovery,
                job.job_id,
                stage_key,
                lease_owner=second_owner,
            ),
            receipt,
        )
        with self.assertRaisesRegex(
            ConflictError,
            "JOB_EFFECT_RECEIPT_IMMUTABILITY_CONFLICT",
        ):
            self.runtime.store.save_job_effect_receipt(
                recovery,
                job.job_id,
                stage_key,
                {**receipt, "request_digest": "b" * 64},
                lease_owner=second_owner,
            )

    def test_execution_receipt_response_is_canonical_digest_bound(self) -> None:
        request_digest = hashlib.sha256(b"receipt-response-binding").hexdigest()
        response = {"ok": True, "nested": {"count": 1}}
        claimed, replay = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.response-binding",
            idempotency_key="receipt-response-binding",
            request_digest=request_digest,
            owner_token="receipt-response-owner",
        )
        self.assertEqual((claimed, replay), ("CLAIMED", None))
        self.runtime.store.complete_skill_execution(
            self.context,
            skill="core.test.response-binding",
            idempotency_key="receipt-response-binding",
            request_digest=request_digest,
            owner_token="receipt-response-owner",
            http_status=200,
            response=response,
        )
        row = self.runtime.store._connection.execute(
            """
            SELECT response_json,response_digest FROM skill_execution_receipts
             WHERE skill=? AND idempotency_key=?
            """,
            ("core.test.response-binding", "receipt-response-binding"),
        ).fetchone()
        encoded = canonical_json(response)
        self.assertEqual(row["response_json"], encoded)
        self.assertEqual(
            row["response_digest"],
            hashlib.sha256(encoded.encode()).hexdigest(),
        )
        self.assertEqual(
            self.runtime.store.skill_execution_receipt(
                self.context,
                skill="core.test.response-binding",
                idempotency_key="receipt-response-binding",
                request_digest=request_digest,
            ),
            (200, response),
        )

        self.runtime.store._connection.execute(
            """
            UPDATE skill_execution_receipts SET response_json=?
             WHERE skill=? AND idempotency_key=?
            """,
            (
                canonical_json({"ok": False, "nested": {"count": 1}}),
                "core.test.response-binding",
                "receipt-response-binding",
            ),
        )
        with self.assertRaisesRegex(
            IntegrityError,
            "SKILL_EXECUTION_RECEIPT_CORRUPT",
        ):
            self.runtime.store.skill_execution_receipt(
                self.context,
                skill="core.test.response-binding",
                idempotency_key="receipt-response-binding",
                request_digest=request_digest,
            )

        self.runtime.store._connection.execute(
            """
            UPDATE skill_execution_receipts
               SET response_json=?,response_digest=NULL
             WHERE skill=? AND idempotency_key=?
            """,
            (
                encoded,
                "core.test.response-binding",
                "receipt-response-binding",
            ),
        )
        with self.assertRaisesRegex(
            ConflictError,
            "SKILL_EXECUTION_OUTCOME_RECONCILIATION_REQUIRED",
        ):
            self.runtime.store.skill_execution_receipt(
                self.context,
                skill="core.test.response-binding",
                idempotency_key="receipt-response-binding",
                request_digest=request_digest,
            )

    def test_v12_response_digest_migration_is_exactly_mirrored(self) -> None:
        engine_root = Path(__file__).resolve().parents[1]
        outer = engine_root / "migrations/012_skill_execution_response_digest.sql"
        packaged = (
            engine_root
            / "src/elmos_multimodal_intake/migrations/012_skill_execution_response_digest.sql"
        )
        self.assertEqual(outer.read_bytes(), packaged.read_bytes())
        sql = outer.read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN response_digest TEXT", sql)
        self.assertIn("response_digest IS NULL", sql)
        self.assertIn("PRAGMA user_version = 12", sql)
        self.assertNotIn("UPDATE skill_execution_receipts\n   SET response_digest", sql)

    def test_execution_receipt_claim_has_owner_fencing_and_exact_replay(self) -> None:
        digest = hashlib.sha256(b"receipt-request").hexdigest()
        claimed, replay = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-one",
            lease_seconds=300,
        )
        self.assertEqual((claimed, replay), ("CLAIMED", None))
        renewed_until = self.runtime.store.renew_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-one",
            lease_seconds=300,
        )
        self.assertIn("+00:00", renewed_until)
        with self.assertRaises(ConflictError):
            self.runtime.store.renew_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=digest,
                owner_token="receipt-owner-two",
            )
        with self.assertRaises(ConflictError):
            self.runtime.store.renew_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=hashlib.sha256(b"renew-drift").hexdigest(),
                owner_token="receipt-owner-one",
            )
        busy, _ = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-two",
            lease_seconds=300,
        )
        self.assertEqual(busy, "IN_PROGRESS")
        with self.assertRaises(ConflictError):
            self.runtime.store.claim_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=hashlib.sha256(b"drifted-request").hexdigest(),
                owner_token="receipt-owner-two",
                lease_seconds=300,
            )
        self.runtime.store._connection.execute(
            """
            UPDATE skill_execution_receipts SET lease_expires_at=?
             WHERE skill=? AND idempotency_key=?
            """,
            ("2000-01-01T00:00:00+00:00", "core.test.operation", "receipt-claim"),
        )
        with self.assertRaises(ConflictError):
            self.runtime.store.renew_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=digest,
                owner_token="receipt-owner-one",
            )
        with self.assertRaises(ConflictError):
            self.runtime.store.complete_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=digest,
                owner_token="receipt-owner-one",
                http_status=200,
                response={"stale": True},
            )
        takeover, _ = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-two",
            lease_seconds=300,
        )
        self.assertEqual(takeover, "CLAIMED")
        with self.assertRaises(ConflictError):
            self.runtime.store.complete_skill_execution(
                self.context,
                skill="core.test.operation",
                idempotency_key="receipt-claim",
                request_digest=digest,
                owner_token="receipt-owner-one",
                http_status=200,
                response={"ok": True},
            )
        self.runtime.store.complete_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-two",
            http_status=200,
            response={"ok": True},
        )
        state, persisted = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.operation",
            idempotency_key="receipt-claim",
            request_digest=digest,
            owner_token="receipt-owner-three",
        )
        self.assertEqual(state, "REPLAY")
        self.assertEqual(persisted, (200, {"ok": True}))

    def test_dispatched_execution_receipt_never_allows_expiry_takeover(self) -> None:
        digest = hashlib.sha256(b"dispatched-receipt-request").hexdigest()
        claimed, replay = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.dispatched-operation",
            idempotency_key="dispatched-receipt-claim",
            request_digest=digest,
            owner_token="dispatched-owner-one",
            lease_seconds=300,
        )
        self.assertEqual((claimed, replay), ("CLAIMED", None))
        started_at = self.runtime.store.mark_skill_execution_dispatched(
            self.context,
            skill="core.test.dispatched-operation",
            idempotency_key="dispatched-receipt-claim",
            request_digest=digest,
            owner_token="dispatched-owner-one",
        )
        self.assertIn("+00:00", started_at)
        self.runtime.store._connection.execute(
            """
            UPDATE skill_execution_receipts SET lease_expires_at=?
             WHERE skill=? AND idempotency_key=?
            """,
            (
                "2000-01-01T00:00:00+00:00",
                "core.test.dispatched-operation",
                "dispatched-receipt-claim",
            ),
        )

        takeover, takeover_receipt = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.dispatched-operation",
            idempotency_key="dispatched-receipt-claim",
            request_digest=digest,
            owner_token="dispatched-owner-two",
            lease_seconds=300,
        )
        self.assertEqual((takeover, takeover_receipt), ("RECONCILIATION_REQUIRED", None))
        with self.assertRaisesRegex(ConflictError, "SKILL_EXECUTION_ALREADY_DISPATCHED"):
            self.runtime.store.release_skill_execution(
                self.context,
                skill="core.test.dispatched-operation",
                idempotency_key="dispatched-receipt-claim",
                request_digest=digest,
                owner_token="dispatched-owner-one",
            )

        # No claimant can take over, so the exact original owner can safely
        # publish a late result even after its advisory lease timestamp.
        completed = self.runtime.store.complete_skill_execution(
            self.context,
            skill="core.test.dispatched-operation",
            idempotency_key="dispatched-receipt-claim",
            request_digest=digest,
            owner_token="dispatched-owner-one",
            http_status=200,
            response={"ok": True},
        )
        self.assertEqual(completed, (200, {"ok": True}))
        state, persisted = self.runtime.store.claim_skill_execution(
            self.context,
            skill="core.test.dispatched-operation",
            idempotency_key="dispatched-receipt-claim",
            request_digest=digest,
            owner_token="dispatched-owner-three",
        )
        self.assertEqual(state, "REPLAY")
        self.assertEqual(persisted, (200, {"ok": True}))

    def test_runtime_dispatch_crash_is_reconciliation_only_and_never_reinvoked(self) -> None:
        class InjectedProcessCrash(BaseException):
            pass

        calls = 0
        original = self.runtime._handlers[MALWARE]

        def crash_after_dispatch(
            _context: TenantContext,
            _payload: Mapping[str, Any],
        ) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            row = self.runtime.store._connection.execute(
                """
                SELECT status,dispatch_started_at FROM skill_execution_receipts
                 WHERE skill=? AND idempotency_key=?
                """,
                (
                    self.runtime._receipt_skill(MALWARE, "inspect"),
                    "runtime-dispatch-crash",
                ),
            ).fetchone()
            self.assertEqual(row["status"], "IN_PROGRESS")
            self.assertIsNotNone(row["dispatch_started_at"])
            raise InjectedProcessCrash("fault after durable dispatch marker")

        self.runtime._handlers[MALWARE] = crash_after_dispatch
        request = {
            "operation": "inspect",
            "idempotency_key": "runtime-dispatch-crash",
            "trace_id": "trace-runtime-dispatch-crash",
        }
        try:
            with self.assertRaises(InjectedProcessCrash):
                self.runtime.handle(MALWARE, self.context, request)
            self.runtime.store._connection.execute(
                """
                UPDATE skill_execution_receipts SET lease_expires_at=?
                 WHERE skill=? AND idempotency_key=?
                """,
                (
                    "2000-01-01T00:00:00+00:00",
                    self.runtime._receipt_skill(MALWARE, "inspect"),
                    "runtime-dispatch-crash",
                ),
            )

            def forbidden_repeat(
                _context: TenantContext,
                _payload: Mapping[str, Any],
            ) -> dict[str, Any]:
                nonlocal calls
                calls += 1
                return {"repeated": True}

            self.runtime._handlers[MALWARE] = forbidden_repeat
            blocked = self.runtime.handle(MALWARE, self.context, request)
        finally:
            self.runtime._handlers[MALWARE] = original

        self.assertEqual(calls, 1)
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertEqual(blocked["code"], "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED")
        self.assertIs(blocked["retryable"], False)
        self.assertIs(blocked["outputs"]["automatic_retry_allowed"], False)
        self.assertEqual(blocked["trace_id"], request["trace_id"])

    def test_utf16_docx_dtd_is_blocked_before_element_materialization(self) -> None:
        scanner = self._reset_with_clean_malware_scanner("utf16-dtd")
        document = (
            "<?xml version='1.0' encoding='UTF-16'?>"
            "<!DOCTYPE w:document [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            "<w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>"
        ).encode("utf-16")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", document)
        uploaded = self._upload(
            "utf16-dtd.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            buffer.getvalue(),
            "utf16-dtd",
        )
        parsed = self.runtime.handle(
            WORD,
            self.context,
            {
                "operation": "process_asset",
                "asset_id": uploaded["asset_id"],
                "idempotency_key": "utf16-dtd-parse",
            },
        )
        self.assertEqual(parsed["report"]["status"], "BLOCKED")
        self.assertEqual(parsed["report"]["error_code"], "DOCX_XML_DTD_BLOCKED")
        self.assertEqual(
            [call["tool"] for call in scanner.calls],
            [ToolCapability.MALWARE_SCAN.value],
        )

    def test_upload_type_limit_and_provider_digest_configuration_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            self.runtime.handle(
                UPLOAD,
                self.context,
                {
                    "operation": "start",
                    "session_id": self.session_id,
                    "display_name": "oversized.txt",
                    "declared_media_type": "text/plain",
                    "expected_size": 4 * 1024 * 1024 + 1,
                    "expected_sha256": "0" * 64,
                    "idempotency_key": "oversized-text-start",
                },
            )
        with self.assertRaises(ValueError):
            create_runtime(
                Path(self.temporary.name) / "invalid-tool.sqlite3",
                Path(self.temporary.name) / "invalid-tool-cas",
                sandbox_executor=RecordingSandbox(b"{}"),
                provisioned_tools={ToolCapability.OCR: "/opt/elmos/bin/tesseract"},
            )

    def test_durable_transition_and_outbox_are_persisted_and_replayed(self) -> None:
        transition = {
            "operation": "transition",
            "task_id": "task-durable",
            "current_state": "PENDING",
            "target_state": "RUNNING",
            "payload": {"action": "start"},
            "idempotency_key": "durable-start",
        }
        first = self.runtime.handle(DURABLE, self.context, transition)
        replayed = self.runtime.handle(DURABLE, self.context, transition)
        self.assertEqual(first, replayed)
        self.assertNotIn("effects_to_skip", first["outputs"]["event"])
        self.assertNotIn("effects_to_reconcile", first["outputs"]["event"])
        state = self.runtime.handle(
            DURABLE,
            self.context,
            {"operation": "get_task_state", "task_id": "task-durable"},
        )
        self.assertEqual(state["outputs"]["task"]["state"], "RUNNING")
        outbox = self.runtime.handle(
            DURABLE,
            self.context,
            {
                "operation": "list_outbox",
                "aggregate_type": "durable_task",
                "aggregate_id": "task-durable",
            },
        )
        self.assertEqual(len(outbox["outputs"]["events"]), 1)

    def test_core_outbox_digest_and_exact_idempotency_binding(self) -> None:
        payload = {"state": "READY", "sequence": 1}
        with self.runtime.store.transaction() as connection:
            event_id = self.runtime.store._event(
                connection,
                self.context,
                "test_aggregate",
                "aggregate-one",
                "test.aggregate.changed",
                "core-outbox-exact-key",
                payload,
            )
            replayed_event_id = self.runtime.store._event(
                connection,
                self.context,
                "test_aggregate",
                "aggregate-one",
                "test.aggregate.changed",
                "core-outbox-exact-key",
                payload,
            )
            self.assertEqual(replayed_event_id, event_id)
            drifted_requests = (
                ("other_aggregate", "aggregate-one", "test.aggregate.changed", payload),
                ("test_aggregate", "aggregate-two", "test.aggregate.changed", payload),
                ("test_aggregate", "aggregate-one", "test.aggregate.other", payload),
                ("test_aggregate", "aggregate-one", "test.aggregate.changed", {"state": "DRIFTED"}),
            )
            for aggregate_type, aggregate_id, event_type, drifted_payload in drifted_requests:
                with self.subTest(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    payload=drifted_payload,
                ):
                    with self.assertRaisesRegex(ConflictError, "OUTBOX_EVENT_IDEMPOTENCY_CONFLICT"):
                        self.runtime.store._event(
                            connection,
                            self.context,
                            aggregate_type,
                            aggregate_id,
                            event_type,
                            "core-outbox-exact-key",
                            drifted_payload,
                        )
        events = self.runtime.store.outbox_events(
            self.context,
            aggregate_type="test_aggregate",
            aggregate_id="aggregate-one",
        )
        event = next(item for item in events if item["event_id"] == event_id)
        expected_digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        self.assertEqual(event["payload"], payload)
        self.assertEqual(event["payload_digest"], expected_digest)
        transport_receipt = {
            "schema_version": "core-outbox-transport-receipt-v1",
            "event_id": event_id,
            "payload_digest": event["payload_digest"],
            "transport": "test-transport",
            "delivery_id": "delivery-core-outbox-one",
            "status": "DELIVERED",
            "delivered_at": event["occurred_at"],
            "response_digest": "f" * 64,
        }
        with self.assertRaisesRegex(AuthorizationError, "OUTBOX_PUBLISHER_AUTHORITY_REQUIRED"):
            self.runtime.store.mark_outbox_published(
                self.context,
                event_id,
                publisher_capability=object(),
                transport_receipt=transport_receipt,
            )
        published = self.runtime.acknowledge_core_outbox_delivery(
            self.context,
            event_id=event_id,
            transport_receipt=transport_receipt,
        )
        self.assertEqual(published["event_id"], event_id)
        self.assertIsNotNone(published["published_at"])
        self.assertRegex(published["transport_receipt_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            self.runtime.acknowledge_core_outbox_delivery(
                self.context,
                event_id=event_id,
                transport_receipt=transport_receipt,
            ),
            published,
        )

    def test_core_outbox_payload_tamper_fails_list_and_publish(self) -> None:
        with self.runtime.store.transaction() as connection:
            event_id = self.runtime.store._event(
                connection,
                self.context,
                "test_aggregate",
                "aggregate-tamper",
                "test.aggregate.changed",
                "core-outbox-tamper-key",
                {"state": "ORIGINAL"},
            )
        self.runtime.store._connection.execute(
            "UPDATE outbox_events SET payload_json=? WHERE event_id=?",
            (canonical_json({"state": "TAMPERED"}), event_id),
        )
        binding = self.runtime.store._connection.execute(
            "SELECT payload_digest,occurred_at FROM outbox_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        with self.assertRaisesRegex(IntegrityError, "OUTBOX_EVENT_CORRUPT"):
            self.runtime.store.outbox_events(
                self.context,
                aggregate_type="test_aggregate",
                aggregate_id="aggregate-tamper",
            )
        with self.assertRaisesRegex(IntegrityError, "OUTBOX_EVENT_CORRUPT"):
            self.runtime.acknowledge_core_outbox_delivery(
                self.context,
                event_id=event_id,
                transport_receipt={
                    "schema_version": "core-outbox-transport-receipt-v1",
                    "event_id": event_id,
                    "payload_digest": binding["payload_digest"],
                    "transport": "test-transport",
                    "delivery_id": "delivery-core-outbox-tamper",
                    "status": "DELIVERED",
                    "delivered_at": binding["occurred_at"],
                    "response_digest": "e" * 64,
                },
            )

    def test_durable_progress_join_rejects_core_outbox_type_tamper(self) -> None:
        self.runtime.handle(
            DURABLE,
            self.context,
            {
                "operation": "transition",
                "task_id": "task-outbox-binding",
                "current_state": "PENDING",
                "target_state": "RUNNING",
                "payload": {"action": "start"},
                "idempotency_key": "durable-outbox-binding",
            },
        )
        row = self.runtime.store._connection.execute(
            "SELECT outbox_event_id FROM durable_transitions WHERE task_id=?",
            ("task-outbox-binding",),
        ).fetchone()
        self.runtime.store._connection.execute(
            "UPDATE outbox_events SET aggregate_type=? WHERE event_id=?",
            ("other_type", row["outbox_event_id"]),
        )
        with self.assertRaisesRegex(IntegrityError, "OUTBOX_EVENT_BINDING_MISMATCH"):
            self.runtime.store.durable_task_state(self.context, "task-outbox-binding")

    def test_durable_public_boundary_rejects_effect_receipts_and_publish_ack(self) -> None:
        with self.assertRaisesRegex(AuthorizationError, "DURABLE_EFFECT_RECEIPTS_REQUIRE_RECONCILER"):
            self.runtime.handle(
                DURABLE,
                self.context,
                {
                    "operation": "transition",
                    "task_id": "task-untrusted-effect",
                    "current_state": "PENDING",
                    "target_state": "RUNNING",
                    "payload": {},
                    "attempted_effect_receipts": ["client-claimed-effect"],
                    "recorded_effect_receipts": [],
                    "idempotency_key": "durable-untrusted-effect",
                },
            )
        with self.assertRaisesRegex(AuthorizationError, "OUTBOX_PUBLISHER_AUTHORITY_REQUIRED"):
            self.runtime.handle(
                DURABLE,
                self.context,
                {
                    "operation": "mark_outbox_published",
                    "event_id": "client-claimed-event",
                    "idempotency_key": "durable-untrusted-publish",
                },
            )

    def test_external_effect_failure_is_completed_as_reconciliation_block_and_replayed(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = RecordingSandbox({
            ToolCapability.MALWARE_SCAN.value: json.dumps({"verdict": "CLEAN", "findings": []}).encode(),
            ToolCapability.OCR.value: json.dumps(
                {"regions": [{"text": "Charged OCR", "bbox": [1, 2, 30, 10], "confidence": 0.9}]}
            ).encode(),
        })
        self.runtime = create_runtime(
            root / "external-effect.sqlite3",
            root / "external-effect-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan"),
                ToolCapability.OCR: provisioned("/opt/elmos/bin/tesseract"),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-external-effect"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "external-effect-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload(
            "charged.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 8,
            "external-effect",
        )
        original = self.runtime._handlers[IMAGE]

        def fail_after_provider(context: TenantContext, payload: dict[str, object]) -> dict[str, object]:
            original(context, payload)
            raise RuntimeError("private failure must not escape or be retried")

        self.runtime._handlers[IMAGE] = fail_after_provider
        request = {
            "operation": "process_asset",
            "asset_id": image["asset_id"],
            "idempotency_key": "external-effect-process",
        }
        first = self.runtime.handle(IMAGE, self.context, request)
        call_count = len(executor.calls)
        replayed = self.runtime.handle(IMAGE, self.context, request)
        self.assertEqual(first, replayed)
        self.assertEqual(first["state"], "BLOCKED")
        self.assertEqual(first["code"], "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED")
        self.assertFalse(first["retryable"])
        self.assertEqual(len(executor.calls), call_count)

        self.runtime.store.grant_permissions(self.context, "reader@example.test", [self.runtime.store.READ])
        reader = TenantContext(self.context.tenant_id, self.context.project_id, "reader@example.test")
        with self.assertRaises(AuthorizationError):
            self.runtime.handle(
                IMAGE,
                reader,
                {
                    "operation": "process_asset",
                    "asset_id": image["asset_id"],
                    "idempotency_key": "external-effect-reader-denied",
                },
            )
        self.assertEqual(len(executor.calls), call_count)

    def test_receiptless_provider_failure_terminalizes_job_for_reconciliation(self) -> None:
        root = Path(self.temporary.name)
        self.runtime.close()
        executor = AmbiguousSandbox()
        self.runtime = create_runtime(
            root / "ambiguous-effect.sqlite3",
            root / "ambiguous-effect-cas",
            sandbox_executor=executor,
            provisioned_tools={
                ToolCapability.MALWARE_SCAN: provisioned("/opt/elmos/bin/elmos-malware-scan"),
                ToolCapability.OCR: provisioned("/opt/elmos/bin/tesseract"),
            },
            upload_policy=UploadPolicy(default_part_size=64, maximum_part_size=64),
        )
        self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "bootstrap_project", "idempotency_key": "bootstrap-ambiguous-effect"},
        )
        created = self.runtime.handle(
            ORCHESTRATOR,
            self.context,
            {"operation": "create_session", "idempotency_key": "ambiguous-effect-session"},
        )
        self.session_id = created["session_id"]
        image = self._upload(
            "unknown-completion.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 8,
            "ambiguous-effect",
        )
        request = {
            "operation": "process_session",
            "session_id": self.session_id,
            "idempotency_key": "ambiguous-effect-process",
            "expected_asset_generation_digest": hashlib.sha256(
                str(image["asset_id"]).encode("utf-8")
            ).hexdigest(),
        }
        first = self.runtime.handle(ORCHESTRATOR, self.context, request)
        call_count = len(executor.calls)
        replayed = self.runtime.handle(ORCHESTRATOR, self.context, request)
        self.assertEqual(first, replayed)
        self.assertEqual(first["job"]["status"], JobStatus.BLOCKED.value)
        self.assertEqual(first["job"]["result_status"], ResultStatus.BLOCKED.value)
        self.assertEqual(
            first["job"]["failure_code"],
            "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
        )
        self.assertEqual(first["assets"][0]["status"], AssetStatus.NEEDS_REVIEW.value)
        self.assertEqual(
            first["reports"][str(image["asset_id"])]["error_code"],
            "EXTERNAL_EFFECT_RECONCILIATION_REQUIRED",
        )
        self.assertEqual(len(executor.calls), call_count)


if __name__ == "__main__":
    unittest.main()
