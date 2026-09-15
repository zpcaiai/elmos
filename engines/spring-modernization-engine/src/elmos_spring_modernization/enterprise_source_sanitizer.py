from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class SanitizationEntry:
    placeholder: str
    original_value: str
    category: str
    file_path: str
    occurrence_count: int = 1


@dataclass
class SanitizationManifest:
    project_id: str
    total_sanitized_items: int
    entries: Dict[str, SanitizationEntry] = field(default_factory=dict)
    sanitized_files: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        data = {
            "project_id": self.project_id,
            "total_sanitized_items": self.total_sanitized_items,
            "sanitized_files": self.sanitized_files,
            "entries": {k: asdict(v) for k, v in self.entries.items()},
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> SanitizationManifest:
        data = json.loads(json_str)
        entries = {}
        for k, v in data.get("entries", {}).items():
            entries[k] = SanitizationEntry(**v)
        return cls(
            project_id=data.get("project_id", "unknown"),
            total_sanitized_items=data.get("total_sanitized_items", 0),
            entries=entries,
            sanitized_files=data.get("sanitized_files", []),
        )


class EnterpriseSourceSanitizer:
    """
    Scans and masks sensitive credentials, tokens, passwords, private keys,
    and internal IPs from source code before transmission across air-gapped
    or external analysis environments, with bit-exact reversibility.
    """

    # Categorized patterns: (category, regex_pattern, group_index_to_mask)
    PATTERNS: List[Tuple[str, re.Pattern, int]] = [
        # Private keys (PEM)
        (
            "PRIVATE_KEY",
            re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
            0,
        ),
        # Database passwords in properties / yaml: password: secret123
        (
            "DB_PASSWORD",
            re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{6,})['\"]?"),
            2,
        ),
        # API Keys, secrets, tokens
        (
            "API_SECRET",
            re.compile(r"(?i)(api[_-]?key|secret(?:[_-]?key)?|client[_-]?secret|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.+=/]{8,})['\"]?"),
            2,
        ),
        # JDBC connection strings with user:password@host
        (
            "JDBC_CREDENTIALS",
            re.compile(r"jdbc:[a-z]+://([^:/@\s]+):([^@\s/]+)@"),
            2,
        ),
        # Internal private RFC1918 IPv4 addresses
        (
            "INTERNAL_IP",
            re.compile(r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"),
            1,
        ),
    ]

    @classmethod
    def sanitize_content(
        cls,
        content: str,
        file_path: str,
        manifest: SanitizationManifest,
    ) -> str:
        result = content

        for category, pattern, group_idx in cls.PATTERNS:
            for match in pattern.finditer(result):
                raw_secret = match.group(group_idx)
                if not raw_secret or raw_secret.startswith("__ELMOS_SAN_"):
                    continue

                # Generate a deterministic placeholder based on secret hash
                secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()[:12]
                placeholder = f"__ELMOS_SAN_{category}_{secret_hash}__"

                if placeholder not in manifest.entries:
                    manifest.entries[placeholder] = SanitizationEntry(
                        placeholder=placeholder,
                        original_value=raw_secret,
                        category=category,
                        file_path=file_path,
                        occurrence_count=1,
                    )
                    manifest.total_sanitized_items += 1
                else:
                    manifest.entries[placeholder].occurrence_count += 1

                # Replace the exact secret substring
                result = result.replace(raw_secret, placeholder)

        if result != content and file_path not in manifest.sanitized_files:
            manifest.sanitized_files.append(file_path)

        return result

    @classmethod
    def desanitize_content(cls, sanitized_content: str, manifest: SanitizationManifest) -> str:
        result = sanitized_content
        for placeholder, entry in manifest.entries.items():
            if placeholder in result:
                result = result.replace(placeholder, entry.original_value)
        return result

    @classmethod
    def sanitize_directory(
        cls,
        dir_path: Path,
        project_id: str = "spring-enterprise",
        extensions: Optional[Set[str]] = None,
    ) -> SanitizationManifest:
        if extensions is None:
            extensions = {".java", ".xml", ".properties", ".yml", ".yaml", ".json", ".sql", ".sh", ".gradle"}

        manifest = SanitizationManifest(project_id=project_id, total_sanitized_items=0)

        for file in dir_path.rglob("*"):
            if file.is_file() and file.suffix.lower() in extensions:
                try:
                    rel_path = str(file.relative_to(dir_path))
                    original_text = file.read_text(encoding="utf-8")
                    sanitized_text = cls.sanitize_content(original_text, rel_path, manifest)
                    if sanitized_text != original_text:
                        file.write_text(sanitized_text, encoding="utf-8")
                except Exception:
                    # Skip binary or non-utf8 files
                    continue

        return manifest

    @classmethod
    def desanitize_directory(cls, dir_path: Path, manifest: SanitizationManifest) -> int:
        restored_files_count = 0
        for rel_file in manifest.sanitized_files:
            target_file = dir_path / rel_file
            if target_file.is_file():
                try:
                    content = target_file.read_text(encoding="utf-8")
                    restored = cls.desanitize_content(content, manifest)
                    if restored != content:
                        target_file.write_text(restored, encoding="utf-8")
                        restored_files_count += 1
                except Exception:
                    continue
        return restored_files_count
