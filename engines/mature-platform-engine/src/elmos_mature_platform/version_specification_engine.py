"""Version Specification Engine (Batch 43 - Skill 1436).

Implements strict Semantic Versioning 2.0.0 parsing, range satisfaction matching (caret, tilde, wildcards),
breaking change classification, and dependency version constraint resolution.
"""

from typing import Any, Dict, List, Optional
import re

from .types import (
    SemanticVersion,
    VersionChangeType,
)


class VersionSpecificationEngine:
    """Semantic version parser, comparator, and constraint satisfaction engine."""

    SEMVER_PATTERN = re.compile(
        r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
        r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
        r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
        r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
    )

    def parse_version(self, version_str: str) -> SemanticVersion:
        """Parse a SemVer string into a typed SemanticVersion object."""
        v = version_str.strip().lstrip("v")
        match = self.SEMVER_PATTERN.match(v)
        if not match:
            raise ValueError(f"Invalid semantic version string: '{version_str}'")

        gd = match.groupdict()
        return SemanticVersion(
            major=int(gd["major"]),
            minor=int(gd["minor"]),
            patch=int(gd["patch"]),
            prerelease=gd["prerelease"] or "",
            build_metadata=gd["buildmetadata"] or "",
        )

    def compare_versions(self, v1_str: str, v2_str: str) -> int:
        """Compare two SemVer strings. Returns -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
        v1 = self.parse_version(v1_str)
        v2 = self.parse_version(v2_str)

        if (v1.major, v1.minor, v1.patch) != (v2.major, v2.minor, v2.patch):
            if (v1.major, v1.minor, v1.patch) < (v2.major, v2.minor, v2.patch):
                return -1
            return 1

        # Prerelease precedence: normal version has higher precedence than prerelease
        if not v1.prerelease and v2.prerelease:
            return 1
        if v1.prerelease and not v2.prerelease:
            return -1
        if v1.prerelease and v2.prerelease:
            if v1.prerelease < v2.prerelease:
                return -1
            if v1.prerelease > v2.prerelease:
                return 1

        return 0

    def classify_change(self, old_ver_str: str, new_ver_str: str) -> VersionChangeType:
        """Determine SemVer delta classification between two versions."""
        old_v = self.parse_version(old_ver_str)
        new_v = self.parse_version(new_ver_str)

        if new_v.major != old_v.major:
            return VersionChangeType.MAJOR
        if new_v.minor != old_v.minor:
            return VersionChangeType.MINOR
        if new_v.patch != old_v.patch:
            return VersionChangeType.PATCH
        if new_v.prerelease != old_v.prerelease:
            return VersionChangeType.PRERELEASE
        return VersionChangeType.NO_CHANGE

    def matches_range(self, version_str: str, range_expr: str) -> bool:
        """Check if a version satisfies a range expression (^, ~, *, >=, <=)."""
        v = self.parse_version(version_str)
        expr = range_expr.strip()

        if expr in ("*", "x", "X", ""):
            return True

        if expr.startswith("^"):
            base = self.parse_version(expr[1:])
            if base.major > 0:
                return v.major == base.major and self.compare_versions(version_str, str(base)) >= 0
            if base.minor > 0:
                return (
                    v.major == 0
                    and v.minor == base.minor
                    and self.compare_versions(version_str, str(base)) >= 0
                )
            return (
                v.major == 0
                and v.minor == 0
                and v.patch == base.patch
            )

        if expr.startswith("~"):
            base = self.parse_version(expr[1:])
            return (
                v.major == base.major
                and v.minor == base.minor
                and self.compare_versions(version_str, str(base)) >= 0
            )

        if expr.endswith(".*"):
            prefix = expr[:-2]
            parts = prefix.split(".")
            if len(parts) == 1:
                return v.major == int(parts[0])
            if len(parts) == 2:
                return v.major == int(parts[0]) and v.minor == int(parts[1])

        # Exact match
        return self.compare_versions(version_str, expr) == 0

    def get_highest_compatible(
        self, available_versions: List[str], range_expr: str
    ) -> Optional[str]:
        """Find the highest SemVer among available candidates that satisfies the constraint range."""
        valid_candidates = []
        for cand in available_versions:
            try:
                if self.matches_range(cand, range_expr):
                    valid_candidates.append(cand)
            except ValueError:
                continue

        if not valid_candidates:
            return None

        # Sort candidates using compare_versions
        from functools import cmp_to_key
        valid_candidates.sort(key=cmp_to_key(self.compare_versions), reverse=True)
        return valid_candidates[0]

    def get_version_report(self, versions: List[str]) -> Dict[str, Any]:
        """Generate breakdown metrics of parsed version candidates."""
        majors: Dict[int, int] = {}
        prerelease_count = 0

        for v_str in versions:
            try:
                parsed = self.parse_version(v_str)
                majors[parsed.major] = majors.get(parsed.major, 0) + 1
                if parsed.prerelease:
                    prerelease_count += 1
            except ValueError:
                continue

        return {
            "total_versions_analyzed": len(versions),
            "breakdown_by_major": majors,
            "prereleases_count": prerelease_count,
        }
