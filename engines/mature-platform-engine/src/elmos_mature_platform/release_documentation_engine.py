"""Release Documentation Engine (Batch 43 - Skill 1453).

Generates and publishes enterprise product release documentation, release notes,
breaking change summaries, migration guides, and security advisories.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    DocSectionType,
    ReleaseDocSection,
    ReleaseDocumentationBundle,
)


class ReleaseDocumentationEngine:
    """Automated authoring, validation, and publishing engine for product release notes."""

    def __init__(self) -> None:
        self._docs: Dict[str, ReleaseDocumentationBundle] = {}

    def create_release_doc(self, bundle: ReleaseDocumentationBundle) -> str:
        """Create a new release documentation bundle."""
        if not bundle.product_name or not bundle.version:
            raise ValueError("product_name and version are required")

        if not bundle.doc_id:
            bundle.doc_id = f"rdoc-{uuid.uuid4().hex[:8]}"

        if not bundle.generated_at:
            bundle.generated_at = datetime.now(timezone.utc).isoformat()

        if not bundle.release_date:
            bundle.release_date = bundle.generated_at[:10]

        self._docs[bundle.doc_id] = bundle
        return bundle.doc_id

    def add_section(
        self, doc_id: str, section: ReleaseDocSection
    ) -> ReleaseDocumentationBundle:
        """Add or update a documentation section (breaking changes, features, etc.)."""
        bundle = self._docs.get(doc_id)
        if not bundle:
            raise ValueError(f"Release documentation not found: {doc_id}")

        bundle.sections[section.section_type.value] = section
        return bundle

    def publish_documentation(self, doc_id: str) -> ReleaseDocumentationBundle:
        """Validate required sections and publish release documentation."""
        bundle = self._docs.get(doc_id)
        if not bundle:
            raise ValueError(f"Release documentation not found: {doc_id}")

        sec_keys = set(bundle.sections.keys())
        if DocSectionType.OVERVIEW.value not in sec_keys:
            raise ValueError("Overview section is required before publication")

        has_features = DocSectionType.NEW_FEATURES.value in sec_keys
        has_fixes = DocSectionType.BUG_FIXES.value in sec_keys
        has_breaking = DocSectionType.BREAKING_CHANGES.value in sec_keys

        if not (has_features or has_fixes or has_breaking):
            raise ValueError("Release notes must contain at least one content section (features, fixes, or breaking changes)")

        bundle.published = True
        return bundle

    def render_markdown(self, doc_id: str) -> str:
        """Render complete structured GitHub Flavored Markdown release notes."""
        bundle = self._docs.get(doc_id)
        if not bundle:
            raise ValueError(f"Release documentation not found: {doc_id}")

        md_lines = [
            f"# {bundle.product_name} {bundle.version} Release Notes",
            f"**Release Date**: {bundle.release_date}  ",
            f"**Status**: {'Published' if bundle.published else 'Draft'}",
            "",
            "## Table of Contents",
        ]

        order = [
            DocSectionType.OVERVIEW,
            DocSectionType.BREAKING_CHANGES,
            DocSectionType.NEW_FEATURES,
            DocSectionType.BUG_FIXES,
            DocSectionType.MIGRATION_GUIDE,
            DocSectionType.SECURITY_ADVISORIES,
            DocSectionType.KNOWN_ISSUES,
        ]

        for st in order:
            if st.value in bundle.sections:
                sec = bundle.sections[st.value]
                anchor = sec.title.lower().replace(" ", "-")
                md_lines.append(f"- [{sec.title}](#{anchor})")

        md_lines.append("")

        for st in order:
            if st.value in bundle.sections:
                sec = bundle.sections[st.value]
                md_lines.append(f"## {sec.title}")
                if sec.content:
                    md_lines.append(sec.content)
                    md_lines.append("")
                for item in sec.items:
                    md_lines.append(f"- {item}")
                md_lines.append("")

        return "\n".join(md_lines)

    def get_doc(self, doc_id: str) -> Optional[ReleaseDocumentationBundle]:
        """Retrieve release documentation bundle."""
        return self._docs.get(doc_id)

    def get_documentation_report(self) -> Dict[str, Any]:
        """Generate platform release documentation metrics."""
        total = len(self._docs)
        published = sum(1 for d in self._docs.values() if d.published)
        total_sections = sum(len(d.sections) for d in self._docs.values())

        return {
            "total_documents": total,
            "published_documents": published,
            "draft_documents": total - published,
            "total_sections_authored": total_sections,
        }
