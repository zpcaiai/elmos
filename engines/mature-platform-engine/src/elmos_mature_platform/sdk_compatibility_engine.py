"""SDK Compatibility Engine (Batch 43 - Skill 1439).

Governs multi-language SDK package releases (Python, TypeScript, Java, Go, C#),
assessing backward/forward compatibility against server API releases, detecting broken methods,
and tracking runtime version requirements.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    SdkCompatibilityAssessment,
    SdkCompatibilityLevel,
    SdkLanguage,
    SdkPackageRelease,
)


class SdkCompatibilityEngine:
    """Governance and automated verification of client SDK compatibility across runtime targets."""

    def __init__(self) -> None:
        self._releases: Dict[str, SdkPackageRelease] = {}
        self._assessments: Dict[str, SdkCompatibilityAssessment] = {}

    def register_sdk_release(self, release: SdkPackageRelease) -> str:
        """Register a published or candidate client SDK package release."""
        if not release.version or not release.language:
            raise ValueError("version and language are required")

        if not release.sdk_id:
            release.sdk_id = f"sdk-{release.language.value}-{release.version}"

        if not release.published_at:
            release.published_at = datetime.now(timezone.utc).isoformat()

        self._releases[release.sdk_id] = release
        return release.sdk_id

    def assess_compatibility(
        self,
        sdk_id: str,
        target_server_version: str,
        broken_methods: Optional[List[str]] = None,
        deprecated_methods: Optional[List[str]] = None,
        notes: str = "",
    ) -> SdkCompatibilityAssessment:
        """Assess compatibility between a specific SDK build and target server API version."""
        release = self._releases.get(sdk_id)
        if not release:
            raise ValueError(f"SDK release not found: {sdk_id}")
        if not target_server_version:
            raise ValueError("target_server_version is required")

        brokens = broken_methods or []
        deprecations = deprecated_methods or []

        if len(brokens) > 0:
            level = SdkCompatibilityLevel.INCOMPATIBLE
        elif len(deprecations) > 0:
            level = SdkCompatibilityLevel.COMPATIBLE_WITH_DEPRECATIONS
        else:
            level = SdkCompatibilityLevel.FULLY_COMPATIBLE

        assessment = SdkCompatibilityAssessment(
            assessment_id=f"sdk-ass-{uuid.uuid4().hex[:8]}",
            sdk_id=sdk_id,
            target_server_version=target_server_version,
            level=level,
            broken_methods=brokens,
            deprecated_methods=deprecations,
            notes=notes,
            tested_at=datetime.now(timezone.utc).isoformat(),
        )

        self._assessments[assessment.assessment_id] = assessment

        if level in (
            SdkCompatibilityLevel.FULLY_COMPATIBLE,
            SdkCompatibilityLevel.COMPATIBLE_WITH_DEPRECATIONS,
        ):
            if target_server_version not in release.supported_server_versions:
                release.supported_server_versions.append(target_server_version)

        return assessment

    def get_compatible_sdks(
        self, target_server_version: str, language: Optional[SdkLanguage] = None
    ) -> List[SdkPackageRelease]:
        """Query all SDK releases certified as compatible with the requested server version."""
        results = [
            r for r in self._releases.values()
            if target_server_version in r.supported_server_versions
        ]
        if language:
            results = [r for r in results if r.language == language]
        return results

    def get_sdk_release(self, sdk_id: str) -> Optional[SdkPackageRelease]:
        """Retrieve SDK release details."""
        return self._releases.get(sdk_id)

    def get_sdk_matrix_report(self) -> Dict[str, Any]:
        """Generate platform SDK compatibility matrix metrics."""
        total = len(self._releases)
        by_lang: Dict[str, int] = {}
        for r in self._releases.values():
            l = r.language.value
            by_lang[l] = by_lang.get(l, 0) + 1

        incompat_count = sum(
            1 for a in self._assessments.values() if a.level == SdkCompatibilityLevel.INCOMPATIBLE
        )

        return {
            "total_sdk_releases": total,
            "by_language": by_lang,
            "total_assessments_recorded": len(self._assessments),
            "incompatible_evaluations_count": incompat_count,
        }
