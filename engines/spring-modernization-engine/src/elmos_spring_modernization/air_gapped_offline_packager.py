from __future__ import annotations

import hashlib
import json
import os
import tarfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class AirGappedPackageManifest:
    package_id: str
    created_at_utc: str
    total_files: int
    package_sha256: str
    file_checksums: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> AirGappedPackageManifest:
        return cls(**json.loads(json_str))


@dataclass
class PackageVerificationResult:
    is_valid: bool
    package_id: str
    total_files_verified: int
    corrupted_files: List[str] = field(default_factory=list)
    missing_files: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


class AirGappedOfflinePackager:
    """
    Constructs and verifies tamper-evident, offline air-gapped modernization
    packages containing sanitized source, OpenRewrite recipes, build recipes,
    and cryptographic SHA-256 verification manifests.
    """

    MANIFEST_FILE_NAME = "elmos_airgap_manifest.json"

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @classmethod
    def create_package(
        cls,
        source_dir: Path,
        output_archive_path: Path,
        package_id: str = "spring-modernization-airgap",
    ) -> Path:
        output_archive_path.parent.mkdir(parents=True, exist_ok=True)

        file_checksums: Dict[str, str] = {}
        files_to_pack: List[Path] = []

        for p in source_dir.rglob("*"):
            if p.is_file() and p.name != cls.MANIFEST_FILE_NAME:
                rel_path = str(p.relative_to(source_dir))
                file_checksums[rel_path] = cls.calculate_sha256(p)
                files_to_pack.append(p)

        manifest = AirGappedPackageManifest(
            package_id=package_id,
            created_at_utc="2026-09-15T12:00:00Z",
            total_files=len(files_to_pack),
            package_sha256="",
            file_checksums=file_checksums,
        )

        manifest_temp = source_dir / cls.MANIFEST_FILE_NAME
        manifest_temp.write_text(manifest.to_json(), encoding="utf-8")

        # Create tar.gz archive
        with tarfile.open(output_archive_path, "w:gz") as tar:
            for f in files_to_pack:
                tar.add(f, arcname=str(f.relative_to(source_dir)))
            tar.add(manifest_temp, arcname=cls.MANIFEST_FILE_NAME)

        # Cleanup temporary manifest in source_dir
        if manifest_temp.exists():
            manifest_temp.unlink()

        # Update package SHA-256
        archive_sha = cls.calculate_sha256(output_archive_path)
        manifest.package_sha256 = archive_sha

        return output_archive_path

    @classmethod
    def verify_package(
        cls,
        archive_path: Path,
        extract_to_dir: Optional[Path] = None,
    ) -> PackageVerificationResult:
        if not archive_path.is_file():
            return PackageVerificationResult(
                is_valid=False,
                package_id="unknown",
                total_files_verified=0,
                error_message=f"Archive does not exist: {archive_path}",
            )

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                manifest_member = None
                for member in tar.getmembers():
                    if member.name == cls.MANIFEST_FILE_NAME:
                        manifest_member = member
                        break

                if not manifest_member:
                    return PackageVerificationResult(
                        is_valid=False,
                        package_id="unknown",
                        total_files_verified=0,
                        error_message="Missing elmos_airgap_manifest.json inside package",
                    )

                f = tar.extractfile(manifest_member)
                if not f:
                    return PackageVerificationResult(
                        is_valid=False,
                        package_id="unknown",
                        total_files_verified=0,
                        error_message="Could not extract manifest file",
                    )

                manifest_text = f.read().decode("utf-8")
                manifest = AirGappedPackageManifest.from_json(manifest_text)

                corrupted: List[str] = []
                missing: List[str] = []
                verified_count = 0

                member_names = {m.name for m in tar.getmembers() if m.isfile()}

                for rel_path, expected_hash in manifest.file_checksums.items():
                    if rel_path not in member_names:
                        missing.append(rel_path)
                        continue

                    file_obj = tar.extractfile(rel_path)
                    if not file_obj:
                        missing.append(rel_path)
                        continue

                    sha = hashlib.sha256(file_obj.read()).hexdigest()
                    if sha != expected_hash:
                        corrupted.append(rel_path)
                    else:
                        verified_count += 1

                if extract_to_dir:
                    extract_to_dir.mkdir(parents=True, exist_ok=True)
                    tar.extractall(extract_to_dir)

                is_valid = len(corrupted) == 0 and len(missing) == 0
                return PackageVerificationResult(
                    is_valid=is_valid,
                    package_id=manifest.package_id,
                    total_files_verified=verified_count,
                    corrupted_files=corrupted,
                    missing_files=missing,
                )

        except Exception as e:
            return PackageVerificationResult(
                is_valid=False,
                package_id="unknown",
                total_files_verified=0,
                error_message=f"Archive corrupted or unreadable: {str(e)}",
            )
