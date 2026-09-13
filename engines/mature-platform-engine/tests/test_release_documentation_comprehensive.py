"""Comprehensive test suite for ReleaseDocumentationEngine (Batch 43 - Skill 1453)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.release_documentation_engine import ReleaseDocumentationEngine
from elmos_mature_platform.types import (
    DocSectionType,
    ReleaseDocSection,
    ReleaseDocumentationBundle,
)


class TestReleaseDocumentationComprehensive(unittest.TestCase):
    """Rigorous unit testing for ReleaseDocumentationEngine."""

    def setUp(self) -> None:
        self.engine = ReleaseDocumentationEngine()

    def test_create_release_doc_success(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="rdoc-v100",
            product_name="Elmos Platform",
            version="1.0.0",
            release_date="2026-09-11",
            target_audiences=["enterprise", "developers"],
        )
        doc_id = self.engine.create_release_doc(bundle)
        self.assertEqual(doc_id, "rdoc-v100")
        fetched = self.engine.get_doc(doc_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.product_name, "Elmos Platform")
        self.assertEqual(fetched.version, "1.0.0")
        self.assertFalse(fetched.published)

    def test_create_release_doc_auto_generates_id_and_dates(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="",
            product_name="Elmos Platform",
            version="2.0.0",
        )
        doc_id = self.engine.create_release_doc(bundle)
        self.assertTrue(doc_id.startswith("rdoc-"))
        self.assertTrue(len(bundle.generated_at) > 0)
        self.assertTrue(len(bundle.release_date) > 0)

    def test_create_release_doc_missing_name_or_version_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.create_release_doc(ReleaseDocumentationBundle(doc_id="1", product_name="", version="1.0.0"))
        with self.assertRaises(ValueError):
            self.engine.create_release_doc(ReleaseDocumentationBundle(doc_id="2", product_name="Elmos", version=""))

    def test_add_section_success(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="doc-add",
            product_name="Elmos",
            version="1.1.0",
        )
        self.engine.create_release_doc(bundle)

        sec = ReleaseDocSection(
            section_type=DocSectionType.OVERVIEW,
            title="Release Overview",
            content="General availability release of v1.1.0",
            items=["General stability improvements", "Performance benchmarks updated"],
        )
        updated = self.engine.add_section("doc-add", sec)
        self.assertIn(DocSectionType.OVERVIEW.value, updated.sections)
        self.assertEqual(updated.sections[DocSectionType.OVERVIEW.value].title, "Release Overview")

    def test_add_section_nonexistent_doc_raises(self) -> None:
        sec = ReleaseDocSection(
            section_type=DocSectionType.BUG_FIXES,
            title="Bug Fixes",
            content="Fixed issues",
        )
        with self.assertRaises(ValueError):
            self.engine.add_section("nonexistent-doc", sec)

    def test_publish_documentation_success(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="doc-pub",
            product_name="Elmos",
            version="1.2.0",
        )
        self.engine.create_release_doc(bundle)

        self.engine.add_section(
            "doc-pub",
            ReleaseDocSection(
                section_type=DocSectionType.OVERVIEW,
                title="Overview",
                content="New update",
            ),
        )
        self.engine.add_section(
            "doc-pub",
            ReleaseDocSection(
                section_type=DocSectionType.NEW_FEATURES,
                title="New Features",
                content="Added features",
                items=["Feature A", "Feature B"],
            ),
        )
        published = self.engine.publish_documentation("doc-pub")
        self.assertTrue(published.published)

    def test_publish_without_overview_fails(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="doc-no-ov",
            product_name="Elmos",
            version="1.2.0",
        )
        self.engine.create_release_doc(bundle)
        self.engine.add_section(
            "doc-no-ov",
            ReleaseDocSection(
                section_type=DocSectionType.BUG_FIXES,
                title="Fixes",
                content="Fixes",
            ),
        )
        with self.assertRaises(ValueError) as ctx:
            self.engine.publish_documentation("doc-no-ov")
        self.assertIn("Overview section is required", str(ctx.exception))

    def test_publish_without_content_sections_fails(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="doc-ov-only",
            product_name="Elmos",
            version="1.2.0",
        )
        self.engine.create_release_doc(bundle)
        self.engine.add_section(
            "doc-ov-only",
            ReleaseDocSection(
                section_type=DocSectionType.OVERVIEW,
                title="Overview",
                content="Only overview",
            ),
        )
        with self.assertRaises(ValueError) as ctx:
            self.engine.publish_documentation("doc-ov-only")
        self.assertIn("at least one content section", str(ctx.exception))

    def test_publish_nonexistent_doc_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.publish_documentation("unknown-doc")

    def test_render_markdown(self) -> None:
        bundle = ReleaseDocumentationBundle(
            doc_id="doc-md",
            product_name="Elmos Enterprise",
            version="3.0.0",
            release_date="2026-10-01",
        )
        self.engine.create_release_doc(bundle)
        self.engine.add_section(
            "doc-md",
            ReleaseDocSection(
                section_type=DocSectionType.OVERVIEW,
                title="Executive Overview",
                content="Overview text here",
                items=["Point 1", "Point 2"],
            ),
        )
        self.engine.add_section(
            "doc-md",
            ReleaseDocSection(
                section_type=DocSectionType.BREAKING_CHANGES,
                title="Breaking Changes",
                content="Removed legacy v1 API",
                items=["API /v1 removed"],
            ),
        )
        self.engine.add_section(
            "doc-md",
            ReleaseDocSection(
                section_type=DocSectionType.SECURITY_ADVISORIES,
                title="Security Advisories",
                content="No CVEs",
                items=["Hardened TLS ciphers"],
            ),
        )

        md = self.engine.render_markdown("doc-md")
        self.assertIn("# Elmos Enterprise 3.0.0 Release Notes", md)
        self.assertIn("**Release Date**: 2026-10-01", md)
        self.assertIn("## Table of Contents", md)
        self.assertIn("- [Executive Overview](#executive-overview)", md)
        self.assertIn("- [Breaking Changes](#breaking-changes)", md)
        self.assertIn("- [Security Advisories](#security-advisories)", md)
        self.assertIn("## Executive Overview", md)
        self.assertIn("- Point 1", md)
        self.assertIn("## Breaking Changes", md)
        self.assertIn("- API /v1 removed", md)

    def test_render_markdown_nonexistent_doc_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.render_markdown("missing-id")

    def test_get_doc_returns_none_for_missing(self) -> None:
        self.assertIsNone(self.engine.get_doc("missing"))

    def test_get_documentation_report(self) -> None:
        rep_empty = self.engine.get_documentation_report()
        self.assertEqual(rep_empty["total_documents"], 0)
        self.assertEqual(rep_empty["published_documents"], 0)
        self.assertEqual(rep_empty["draft_documents"], 0)
        self.assertEqual(rep_empty["total_sections_authored"], 0)

        # Create two docs: one draft, one published
        doc1 = ReleaseDocumentationBundle(doc_id="d1", product_name="P1", version="1.0")
        self.engine.create_release_doc(doc1)
        self.engine.add_section("d1", ReleaseDocSection(DocSectionType.OVERVIEW, "Overview", "C"))
        self.engine.add_section("d1", ReleaseDocSection(DocSectionType.NEW_FEATURES, "Features", "C"))
        self.engine.publish_documentation("d1")

        doc2 = ReleaseDocumentationBundle(doc_id="d2", product_name="P2", version="2.0")
        self.engine.create_release_doc(doc2)
        self.engine.add_section("d2", ReleaseDocSection(DocSectionType.OVERVIEW, "Overview", "C"))

        rep = self.engine.get_documentation_report()
        self.assertEqual(rep["total_documents"], 2)
        self.assertEqual(rep["published_documents"], 1)
        self.assertEqual(rep["draft_documents"], 1)
        self.assertEqual(rep["total_sections_authored"], 3)


if __name__ == "__main__":
    unittest.main()
