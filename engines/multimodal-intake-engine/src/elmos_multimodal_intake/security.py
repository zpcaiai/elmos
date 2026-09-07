"""Content-first type detection and passive security inspection."""

from __future__ import annotations

import io
import hmac
import stat
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from .canonical import normalize_sha256, sha256_bytes
from .errors import ValidationError
from .models import AssetKind, DetectionResult, InputAsset, ResultStatus, SecurityDecision
from .providers import ProviderResult, ToolCapability


_MALWARE_CLEARANCE_REQUIRED_KINDS = frozenset(
    {
        AssetKind.DOCX,
        AssetKind.PDF,
        AssetKind.IMAGE,
        AssetKind.AUDIO,
        AssetKind.ARCHIVE,
        AssetKind.UNKNOWN,
    }
)


@dataclass(frozen=True, slots=True)
class InspectionPolicy:
    maximum_archive_entries: int = 10_000
    maximum_archive_directory_bytes: int = 64 * 1024 * 1024
    maximum_archive_uncompressed_bytes: int = 512 * 1024 * 1024
    maximum_compression_ratio: float = 200.0
    maximum_nested_archive_depth: int = 0
    maximum_content_probe_bytes: int = 8 * 1024 * 1024


class FileSecurityInspector:
    """Never executes input; parser selection follows observed bytes, not suffixes."""

    REGISTRY_VERSION = "elmos-file-types-1.0.0"

    _EXECUTABLE_MAGICS = (
        b"MZ",
        b"\x7fELF",
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
    )
    _IMAGE_TYPES = {
        "image/png": AssetKind.IMAGE,
        "image/jpeg": AssetKind.IMAGE,
        "image/gif": AssetKind.IMAGE,
        "image/webp": AssetKind.IMAGE,
        "image/tiff": AssetKind.IMAGE,
        "image/bmp": AssetKind.IMAGE,
        "image/heic": AssetKind.IMAGE,
        "image/heif": AssetKind.IMAGE,
        "image/avif": AssetKind.IMAGE,
        "image/svg+xml": AssetKind.IMAGE,
    }
    _AUDIO_TYPES = {
        "audio/wav": AssetKind.AUDIO,
        "audio/mpeg": AssetKind.AUDIO,
        "audio/ogg": AssetKind.AUDIO,
        "audio/flac": AssetKind.AUDIO,
        "audio/mp4": AssetKind.AUDIO,
        "audio/aac": AssetKind.AUDIO,
    }
    _SUFFIX_MEDIA_TYPES = {
        ".pdf": frozenset({"application/pdf"}),
        ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
        ".doc": frozenset({"application/msword"}),
        ".md": frozenset({"text/markdown"}),
        ".mdx": frozenset({"text/markdown"}),
        ".markdown": frozenset({"text/markdown"}),
        ".log": frozenset({"text/plain"}),
        ".txt": frozenset({"text/plain"}),
        ".png": frozenset({"image/png"}),
        ".jpg": frozenset({"image/jpeg"}),
        ".jpeg": frozenset({"image/jpeg"}),
        ".gif": frozenset({"image/gif"}),
        ".webp": frozenset({"image/webp"}),
        ".tif": frozenset({"image/tiff"}),
        ".tiff": frozenset({"image/tiff"}),
        ".bmp": frozenset({"image/bmp"}),
        ".svg": frozenset({"image/svg+xml"}),
        ".heic": frozenset({"image/heic", "image/heif"}),
        ".heif": frozenset({"image/heif", "image/heic"}),
        ".avif": frozenset({"image/avif"}),
        ".wav": frozenset({"audio/wav"}),
        ".mp3": frozenset({"audio/mpeg"}),
        ".ogg": frozenset({"audio/ogg"}),
        ".flac": frozenset({"audio/flac"}),
        ".m4a": frozenset({"audio/mp4"}),
        ".aac": frozenset({"audio/aac"}),
        ".zip": frozenset({"application/zip"}),
        ".gz": frozenset({"application/gzip"}),
        ".tgz": frozenset({"application/gzip"}),
        ".tar": frozenset({"application/x-tar"}),
    }
    _PARSER_CANDIDATES = {
        AssetKind.TEXT: ("text-v1",),
        AssetKind.MARKDOWN: ("markdown-v1",),
        AssetKind.LOG: ("log-v1",),
        AssetKind.DOCX: ("word-ooxml-v2", "legacy-doc-sandbox-v1"),
        AssetKind.PDF: ("pdf-external-v1",),
        AssetKind.IMAGE: ("image-ocr-external-v1",),
        AssetKind.AUDIO: ("audio-asr-external-v1",),
        AssetKind.ARCHIVE: ("secure-archive-stream-v1",),
        AssetKind.UNKNOWN: (),
    }

    def __init__(self, policy: InspectionPolicy | None = None) -> None:
        self.policy = policy or InspectionPolicy()

    def inspect(self, asset: InputAsset, data: bytes) -> DetectionResult:
        findings: list[str] = []
        suffix = PurePosixPath(asset.display_name).suffix.lower()
        declared = asset.declared_media_type.split(";", 1)[0].strip().lower()
        evidence = [
            f"filename_suffix:{suffix or '<none>'}",
            f"declared_media_type:{declared or '<none>'}",
            f"content_bytes:{len(data)}",
            f"probe_limit:{self.policy.maximum_content_probe_bytes}",
        ]
        if any(data.startswith(magic) for magic in self._EXECUTABLE_MAGICS):
            return DetectionResult(
                kind=AssetKind.UNKNOWN,
                media_type="application/x-executable",
                decision=SecurityDecision.QUARANTINE,
                confidence=1.0,
                findings=("EXECUTABLE_CONTENT_BLOCKED",),
                registry_version=self.REGISTRY_VERSION,
                evidence=tuple(evidence + ["magic:executable"]),
                parser_candidates=(),
            )

        kind, media_type, confidence = self._detect(asset.display_name, data, findings, evidence)
        expected_from_suffix = self._SUFFIX_MEDIA_TYPES.get(suffix)
        if expected_from_suffix is not None and media_type not in expected_from_suffix:
            findings.append("FILE_EXTENSION_MISMATCH")
        if self._has_embedded_secondary_magic(data, media_type):
            findings.append("POLYGLOT_SIGNATURES_DETECTED")
        decision = SecurityDecision.ALLOW
        if any(
            finding in findings
            for finding in (
                "DOCX_MACRO_PRESENT",
                "DOCX_EMBEDDED_OBJECT_PRESENT",
                "ARCHIVE_UNSAFE",
                "POLYGLOT_SIGNATURES_DETECTED",
            )
        ):
            decision = SecurityDecision.QUARANTINE
        elif findings or kind in {AssetKind.UNKNOWN, AssetKind.ARCHIVE}:
            decision = SecurityDecision.NEEDS_REVIEW

        if declared not in {"application/octet-stream", "binary/octet-stream", ""}:
            compatible = self._compatible_declared_types(kind, media_type)
            if declared not in compatible:
                findings.append("DECLARED_MEDIA_TYPE_MISMATCH")
                if decision is SecurityDecision.ALLOW:
                    decision = SecurityDecision.NEEDS_REVIEW

        return DetectionResult(
            kind=kind,
            media_type=media_type,
            decision=decision,
            confidence=confidence,
            findings=tuple(sorted(set(findings))),
            registry_version=self.REGISTRY_VERSION,
            evidence=tuple(evidence),
            parser_candidates=self._PARSER_CANDIDATES[kind],
        )

    def _detect(
        self,
        display_name: str,
        data: bytes,
        findings: list[str],
        evidence: list[str],
    ) -> tuple[AssetKind, str, float]:
        suffix = PurePosixPath(display_name).suffix.lower()
        probe = data[: self.policy.maximum_content_probe_bytes]
        if len(data) > len(probe):
            findings.append("CONTENT_PROBE_LIMIT_REACHED")
        if data.startswith(b"%PDF-"):
            evidence.append("magic:pdf")
            if any(marker in probe for marker in (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile")):
                findings.append("PDF_ACTIVE_CONTENT_PRESENT")
            return AssetKind.PDF, "application/pdf", 1.0
        if data.startswith(b"%PDF"):
            evidence.append("magic:truncated-pdf")
            findings.append("TRUNCATED_MAGIC_HEADER")
            return AssetKind.PDF, "application/pdf", 0.45
        if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
            evidence.append("magic:zip")
            return self._inspect_zip(data, findings)
        if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            evidence.append("magic:ole-compound-document")
            findings.append("LEGACY_DOC_REQUIRES_SANDBOX_CONVERSION")
            return AssetKind.DOCX, "application/msword", 0.98
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            evidence.append("magic:png")
            return AssetKind.IMAGE, "image/png", 1.0
        if data.startswith(b"\xff\xd8\xff"):
            evidence.append("magic:jpeg")
            return AssetKind.IMAGE, "image/jpeg", 1.0
        if data.startswith((b"GIF87a", b"GIF89a")):
            evidence.append("magic:gif")
            return AssetKind.IMAGE, "image/gif", 1.0
        if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            evidence.append("magic:webp")
            return AssetKind.IMAGE, "image/webp", 1.0
        if data.startswith((b"II*\x00", b"MM\x00*")):
            evidence.append("magic:tiff")
            return AssetKind.IMAGE, "image/tiff", 1.0
        if data.startswith(b"BM") and len(data) >= 14:
            evidence.append("magic:bmp")
            return AssetKind.IMAGE, "image/bmp", 0.98
        if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE":
            evidence.append("magic:wav")
            return AssetKind.AUDIO, "audio/wav", 1.0
        if data.startswith(b"ID3"):
            evidence.append("magic:mp3-id3")
            return AssetKind.AUDIO, "audio/mpeg", 0.98
        if len(data) > 1 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0:
            evidence.append("magic:aac-adts")
            return AssetKind.AUDIO, "audio/aac", 0.96
        if len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:
            evidence.append("magic:mpeg-audio-frame")
            return AssetKind.AUDIO, "audio/mpeg", 0.9
        if data.startswith(b"OggS"):
            evidence.append("magic:ogg")
            return AssetKind.AUDIO, "audio/ogg", 1.0
        if data.startswith(b"fLaC"):
            evidence.append("magic:flac")
            return AssetKind.AUDIO, "audio/flac", 1.0
        if len(data) >= 12 and data[4:8] == b"ftyp":
            brand = data[8:12]
            evidence.append(f"magic:iso-bmff:{brand.decode('ascii', errors='replace')}")
            if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
                return AssetKind.IMAGE, "image/heic" if brand.startswith(b"hei") else "image/heif", 0.95
            if brand in {b"avif", b"avis"}:
                return AssetKind.IMAGE, "image/avif", 0.98
            if b"vide" in probe:
                findings.append("VIDEO_CONTAINER_NOT_SUPPORTED")
                return AssetKind.UNKNOWN, "video/mp4", 0.85
            if brand in {b"M4A ", b"M4B ", b"M4P "} or b"soun" in probe:
                return AssetKind.AUDIO, "audio/mp4", 0.93
            findings.append("ISO_BASE_MEDIA_CONTAINER_AMBIGUOUS")
            return AssetKind.UNKNOWN, "application/octet-stream", 0.45
        if data.startswith(b"\x1f\x8b"):
            evidence.append("magic:gzip")
            return AssetKind.ARCHIVE, "application/gzip", 1.0
        if len(data) >= 265 and data[257:262] == b"ustar":
            evidence.append("magic:tar")
            return AssetKind.ARCHIVE, "application/x-tar", 1.0

        stripped = probe.lstrip()
        lowered = stripped[:4096].lower()
        if lowered.startswith(b"<svg") or (lowered.startswith(b"<?xml") and b"<svg" in lowered):
            evidence.append("content-probe:svg")
            active_markers = (b"<script", b"javascript:", b"onload=", b"onerror=", b"<foreignobject")
            if any(marker in probe.lower() for marker in active_markers):
                findings.append("SVG_ACTIVE_CONTENT_PRESENT")
            return AssetKind.IMAGE, "image/svg+xml", 0.98

        text_probe = probe if len(data) == len(probe) else probe + data[-65_536:]
        if self._is_text(text_probe):
            evidence.append("content-probe:text")
            if suffix in {".md", ".mdx", ".markdown"}:
                return AssetKind.MARKDOWN, "text/markdown", 0.95
            if suffix in {".log", ".out"}:
                return AssetKind.LOG, "text/plain", 0.9
            return AssetKind.TEXT, "text/plain", 0.85
        findings.append("UNRECOGNIZED_BINARY_CONTENT")
        evidence.append("content-probe:unrecognized-binary")
        return AssetKind.UNKNOWN, "application/octet-stream", 0.25

    def _inspect_zip(
        self,
        data: bytes,
        findings: list[str],
    ) -> tuple[AssetKind, str, float]:
        if not self._zip_directory_preflight(data, findings):
            return AssetKind.ARCHIVE, "application/zip", 0.5
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > self.policy.maximum_archive_entries:
                    findings.append("ARCHIVE_UNSAFE")
                    findings.append("ARCHIVE_ENTRY_LIMIT_EXCEEDED")
                total = 0
                names: set[str] = set()
                canonical_names: dict[str, str] = {}
                for entry in entries:
                    normalized = entry.filename
                    path = PurePosixPath(normalized)
                    total += entry.file_size
                    canonical_name = self._canonical_archive_member_name(normalized)
                    if canonical_name is None:
                        findings.extend(
                            (
                                "ARCHIVE_UNSAFE",
                                "ARCHIVE_PATH_TRAVERSAL",
                                "ARCHIVE_MEMBER_NAME_INVALID",
                            )
                        )
                    else:
                        alias = canonical_name.casefold()
                        prior = canonical_names.get(alias)
                        if prior is not None:
                            findings.extend(
                                (
                                    "ARCHIVE_UNSAFE",
                                    "ARCHIVE_MEMBER_NAME_COLLISION",
                                )
                            )
                        else:
                            canonical_names[alias] = canonical_name
                            names.add(canonical_name)
                    mode = entry.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_LINK_BLOCKED"))
                    if entry.flag_bits & 0x1:
                        findings.append("ARCHIVE_ENCRYPTED_ENTRY")
                    compressed = max(entry.compress_size, 1)
                    if entry.file_size / compressed > self.policy.maximum_compression_ratio:
                        findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_COMPRESSION_RATIO_EXCEEDED"))
                    if self._looks_nested_archive(path.name):
                        findings.append("ARCHIVE_NESTED_CONTENT_NOT_EXPANDED")
                if total > self.policy.maximum_archive_uncompressed_bytes:
                    findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_UNCOMPRESSED_LIMIT_EXCEEDED"))
                is_docx = {"[Content_Types].xml", "word/document.xml"}.issubset(names)
                if is_docx:
                    if "word/vbaProject.bin" in names:
                        findings.append("DOCX_MACRO_PRESENT")
                    if any(name.startswith("word/embeddings/") for name in names):
                        findings.append("DOCX_EMBEDDED_OBJECT_PRESENT")
                    return AssetKind.DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 1.0
                return AssetKind.ARCHIVE, "application/zip", 1.0
        except (zipfile.BadZipFile, OSError, ValueError):
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_DIRECTORY_INVALID"))
            return AssetKind.ARCHIVE, "application/zip", 0.5

    @staticmethod
    def _canonical_archive_member_name(name: str) -> str | None:
        """Return one exact portable member path or reject its aliases.

        ZIP names are attacker-controlled and are interpreted differently by
        case-insensitive and Unicode-normalizing filesystems.  Accept only an
        already-NFKC, POSIX-relative spelling and compare callers through
        ``casefold`` in :meth:`_inspect_zip`.  This makes exact duplicates,
        case aliases, composed/decomposed aliases, full-width separators, and
        file/directory aliases fail before any parser or extraction step.
        """

        if (
            not isinstance(name, str)
            or not name
            or "\\" in name
            or unicodedata.normalize("NFKC", name) != name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
        ):
            return None
        directory = name.endswith("/")
        exact = name[:-1] if directory else name
        if not exact or exact.startswith("/") or "//" in exact:
            return None
        path = PurePosixPath(exact)
        if (
            not path.parts
            or path.as_posix() != exact
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.parts[0].endswith(":")
        ):
            return None
        # A trailing slash is metadata, not a distinct path identity.  This
        # deliberately collides ``name`` and ``name/``.
        return path.as_posix()

    def _zip_directory_preflight(self, data: bytes, findings: list[str]) -> bool:
        """Bound central-directory materialization before zipfile parses attacker metadata."""

        tail = data[-(65_535 + 22) :]
        offset = tail.rfind(b"PK\x05\x06")
        if offset < 0 or offset + 22 > len(tail):
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_DIRECTORY_INVALID"))
            return False
        try:
            (
                _signature,
                disk_number,
                directory_disk,
                entries_on_disk,
                total_entries,
                directory_size,
                directory_offset,
                comment_length,
            ) = struct.unpack_from("<4s4H2LH", tail, offset)
        except struct.error:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_DIRECTORY_INVALID"))
            return False
        absolute_offset = len(data) - len(tail) + offset
        unsafe = False
        if absolute_offset + 22 + comment_length != len(data):
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_TRAILING_DATA"))
            unsafe = True
        if disk_number or directory_disk or entries_on_disk != total_entries:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_MULTI_DISK_UNSUPPORTED"))
            unsafe = True
        if total_entries == 0xFFFF or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_ZIP64_UNSUPPORTED"))
            unsafe = True
        if total_entries > self.policy.maximum_archive_entries:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_ENTRY_LIMIT_EXCEEDED"))
            unsafe = True
        if directory_size > self.policy.maximum_archive_directory_bytes:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_DIRECTORY_LIMIT_EXCEEDED"))
            unsafe = True
        if directory_offset + directory_size > absolute_offset:
            findings.extend(("ARCHIVE_UNSAFE", "ARCHIVE_DIRECTORY_INVALID"))
            unsafe = True
        return not unsafe

    @staticmethod
    def _is_text(data: bytes) -> bool:
        if not data:
            return True
        encodings = ("utf-8-sig", "utf-16") if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig",)
        for encoding in encodings:
            try:
                decoded = data.decode(encoding)
            except UnicodeDecodeError:
                continue
            if "\x00" in decoded:
                return False
            controls = sum(1 for character in decoded if ord(character) < 32 and character not in "\r\n\t")
            return controls <= max(1, len(decoded) // 1000)
        return False

    @staticmethod
    def _looks_nested_archive(name: str) -> bool:
        lowered = name.lower()
        return lowered.endswith((".zip", ".tar", ".tgz", ".tar.gz", ".gz", ".7z", ".rar"))

    @staticmethod
    def _has_embedded_secondary_magic(data: bytes, media_type: str) -> bool:
        if media_type not in {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/tiff",
            "image/bmp",
            "audio/wav",
            "audio/mpeg",
            "audio/aac",
            "audio/ogg",
            "audio/flac",
            "audio/mp4",
        }:
            return False
        signatures = (b"PK\x03\x04", b"%PDF-")
        return any(data.find(signature, 16) >= 16 for signature in signatures)

    @staticmethod
    def _compatible_declared_types(kind: AssetKind, detected: str) -> set[str]:
        compatible = {detected}
        if kind in {AssetKind.TEXT, AssetKind.MARKDOWN, AssetKind.LOG}:
            compatible.update({"text/plain", "text/markdown", "text/x-log"})
        elif kind is AssetKind.DOCX:
            compatible.update(
                {
                    "application/zip",
                    "application/msword",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                }
            )
        elif kind is AssetKind.AUDIO:
            compatible.add("audio/*")
        elif kind is AssetKind.IMAGE:
            compatible.add("image/*")
        elif kind is AssetKind.ARCHIVE:
            compatible.update({"application/zip", "application/gzip", "application/x-gzip", "application/x-tar"})
        return compatible


def apply_malware_scan(
    detection: DetectionResult,
    scan: ProviderResult,
) -> tuple[DetectionResult, str, tuple[str, ...]]:
    """Merge an independently sandboxed scanner result without weakening passive findings."""

    if scan.capability is not ToolCapability.MALWARE_SCAN:
        raise ValueError("malware assessment requires the MALWARE_SCAN capability")
    findings: list[str] = []
    verdict = scan.status.value
    if scan.status is ResultStatus.PASSED:
        raw_verdict = scan.payload.get("verdict")
        if isinstance(raw_verdict, str) and raw_verdict.upper() in {"CLEAN", "SUSPICIOUS", "MALICIOUS"}:
            verdict = raw_verdict.upper()
        else:
            verdict = "INVALID"
            findings.append("MALWARE_SCAN_OUTPUT_INVALID")
        raw_findings = scan.payload.get("findings", [])
        if not isinstance(raw_findings, list):
            verdict = "INVALID"
            findings.append("MALWARE_SCAN_OUTPUT_INVALID")
        else:
            findings.extend(
                item.strip()[:128]
                for item in raw_findings[:256]
                if isinstance(item, str) and item.strip()
            )
    elif scan.error_code:
        findings.append(scan.error_code)

    decision = detection.decision
    if verdict == "MALICIOUS":
        decision = SecurityDecision.QUARANTINE
        findings.append("MALWARE_DETECTED")
    elif verdict != "CLEAN" or findings:
        if decision is SecurityDecision.ALLOW:
            decision = SecurityDecision.NEEDS_REVIEW
    combined = tuple(sorted(set(detection.findings + tuple(findings))))
    assessed = DetectionResult(
        kind=detection.kind,
        media_type=detection.media_type,
        decision=decision,
        confidence=detection.confidence,
        findings=combined,
        registry_version=detection.registry_version,
        evidence=detection.evidence + (f"malware_scan:{verdict}",),
        parser_candidates=detection.parser_candidates,
    )
    return assessed, verdict, tuple(sorted(set(findings)))


def requires_malware_clearance(kind: AssetKind) -> bool:
    """Return whether parsing the detected kind may execute a complex parser/provider."""

    return kind in _MALWARE_CLEARANCE_REQUIRED_KINDS


def validate_malware_clearance(
    detection: DetectionResult,
    scan: ProviderResult,
    verdict: str,
    data: bytes,
) -> tuple[bool, str]:
    """Validate a byte-bound CLEAN receipt before any complex parser is invoked."""

    if not requires_malware_clearance(detection.kind):
        return True, "LOCAL_TEXT_PARSER_EXEMPT"
    if detection.decision is SecurityDecision.QUARANTINE:
        return False, "PASSIVE_OR_SCANNER_QUARANTINE"
    if scan.capability is not ToolCapability.MALWARE_SCAN:
        return False, "MALWARE_SCAN_CAPABILITY_MISMATCH"
    if scan.status is not ResultStatus.PASSED or scan.error_code is not None:
        return False, "MALWARE_SCAN_NOT_PASSED"
    if verdict != "CLEAN":
        return False, "MALWARE_VERDICT_NOT_CLEAN"
    if scan.warnings or detection.decision is not SecurityDecision.ALLOW:
        return False, "MALWARE_OR_PASSIVE_FINDINGS_REQUIRE_REVIEW"

    receipt = scan.receipt
    raw_input_digest = receipt.get("input_sha256")
    raw_executable_digest = receipt.get("executable_sha256")
    raw_policy_digest = receipt.get("policy_sha256")
    raw_auth_tag = receipt.get("provider_auth_tag")
    if (
        not isinstance(raw_input_digest, str)
        or not isinstance(raw_executable_digest, str)
        or not isinstance(raw_policy_digest, str)
        or not isinstance(raw_auth_tag, str)
    ):
        return False, "MALWARE_SCAN_RECEIPT_INVALID"
    try:
        receipt_digest = normalize_sha256(raw_input_digest)
        normalize_sha256(raw_executable_digest)
        normalize_sha256(raw_policy_digest)
        normalize_sha256(raw_auth_tag)
        expected_digest = sha256_bytes(data)
    except (TypeError, ValueError, ValidationError):
        return False, "MALWARE_SCAN_RECEIPT_INVALID"
    required_strings = (
        "schema_version",
        "executable",
        "executable_sha256",
        "policy_sha256",
        "provider_auth_tag",
        "job_id",
        "stage",
        "completed_at",
    )
    if (
        receipt.get("tool") != ToolCapability.MALWARE_SCAN.value
        or receipt.get("executable") != "elmos-malware-scan"
        or not hmac.compare_digest(receipt_digest, expected_digest)
        or receipt.get("input_bytes") != len(data)
        or receipt.get("exit_code") != 0
        or receipt.get("sandboxed") is not True
        or receipt.get("network_allowed") is not False
        or any(not isinstance(receipt.get(key), str) or not receipt.get(key) for key in required_strings)
    ):
        return False, "MALWARE_SCAN_RECEIPT_INVALID"
    return True, "CLEAN_MALWARE_CLEARANCE"
