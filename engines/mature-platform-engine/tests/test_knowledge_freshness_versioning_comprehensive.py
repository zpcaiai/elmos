import unittest
import datetime
import time
from elmos_mature_platform.types import (
    KnowledgeArticle,
    KnowledgeSourceType,
    FreshnessStatus
)
from elmos_mature_platform.knowledge_freshness_versioning_engine import KnowledgeFreshnessVersioningEngine

class TestKnowledgeFreshnessVersioningEngine(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeFreshnessVersioningEngine()

    def test_ingest_article_creates_id(self):
        article = KnowledgeArticle(
            article_id="",
            title="Test",
            source_type=KnowledgeSourceType.DOCUMENTATION
        )
        aid = self.engine.ingest_article(article)
        self.assertTrue(bool(aid))
        self.assertEqual(article.version, 1)

    def test_ingest_article_versions(self):
        article = KnowledgeArticle(
            article_id="art1",
            title="Test",
            source_type=KnowledgeSourceType.DOCUMENTATION,
            content_hash="hash1"
        )
        self.engine.ingest_article(article)
        versions = self.engine.get_version_history("art1")
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0].content_hash, "hash1")

    def test_update_article(self):
        article = KnowledgeArticle(
            article_id="art1",
            title="Test",
            source_type=KnowledgeSourceType.DOCUMENTATION,
            content_hash="hash1"
        )
        self.engine.ingest_article(article)
        self.engine.update_article("art1", "hash2", "Updated", "Author")
        
        versions = self.engine.get_version_history("art1")
        self.assertEqual(len(versions), 2)
        self.assertEqual(article.version, 2)
        self.assertEqual(article.content_hash, "hash2")

    def test_update_missing_article(self):
        with self.assertRaises(ValueError):
            self.engine.update_article("missing", "hash", "msg", "auth")

    def test_update_superseded_article(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        self.engine.supersede_article("a1", "a2")
        with self.assertRaises(ValueError):
            self.engine.update_article("a1", "hash", "msg", "auth")

    def test_check_freshness_current(self):
        a = KnowledgeArticle(article_id="a", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=86400)
        self.engine.ingest_article(a)
        status = self.engine.check_freshness("a")
        self.assertEqual(status, FreshnessStatus.CURRENT)

    def test_check_freshness_expired(self):
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
        a = KnowledgeArticle(article_id="a", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, expires_at=past)
        self.engine.ingest_article(a)
        status = self.engine.check_freshness("a")
        self.assertEqual(status, FreshnessStatus.EXPIRED)
        self.assertEqual(a.freshness_status, FreshnessStatus.EXPIRED)

    def test_check_freshness_stale_by_ttl(self):
        a = KnowledgeArticle(article_id="a", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=0)
        self.engine.ingest_article(a)
        time.sleep(0.01)
        status = self.engine.check_freshness("a")
        self.assertEqual(status, FreshnessStatus.STALE)

    def test_check_freshness_missing(self):
        with self.assertRaises(ValueError):
            self.engine.check_freshness("missing")

    def test_refresh_article(self):
        a = KnowledgeArticle(article_id="a", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=0)
        self.engine.ingest_article(a)
        self.engine.check_freshness("a")
        self.assertEqual(a.freshness_status, FreshnessStatus.STALE)
        
        self.engine.refresh_article("a")
        self.assertEqual(a.freshness_status, FreshnessStatus.CURRENT)

    def test_refresh_missing(self):
        with self.assertRaises(ValueError):
            self.engine.refresh_article("missing")

    def test_supersede_article(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        
        self.engine.supersede_article("a1", "a2")
        self.assertEqual(a1.superseded_by, "a2")
        self.assertEqual(a1.freshness_status, FreshnessStatus.EXPIRED)

    def test_supersede_missing_old(self):
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a2)
        with self.assertRaises(ValueError):
            self.engine.supersede_article("missing", "a2")

    def test_supersede_missing_new(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        with self.assertRaises(ValueError):
            self.engine.supersede_article("a1", "missing")

    def test_get_version_history_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_version_history("missing")

    def test_get_stale_articles(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=0)
        self.engine.ingest_article(a1)
        time.sleep(0.01)
        stale = self.engine.get_stale_articles()
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].article_id, "a1")

    def test_get_stale_articles_max_age(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        stale = self.engine.get_stale_articles(max_age_seconds=-1)
        
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
        a1.updated_at = past
        stale = self.engine.get_stale_articles(max_age_seconds=5)
        self.assertEqual(len(stale), 1)

    def test_dependency_graph(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, dependencies=["a2"])
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION, dependencies=["a3"])
        a3 = KnowledgeArticle(article_id="a3", title="3", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        self.engine.ingest_article(a3)
        
        graph = self.engine.get_dependency_graph("a1")
        self.assertIn("a1", graph)
        self.assertIn("a2", graph)
        self.assertIn("a3", graph)

    def test_dependency_graph_missing(self):
        with self.assertRaises(ValueError):
            self.engine.get_dependency_graph("missing")

    def test_cascade_staleness(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, dependencies=["a2"])
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        
        stale_ids = self.engine.cascade_staleness("a2")
        self.assertIn("a1", stale_ids)
        self.assertEqual(a1.freshness_status, FreshnessStatus.STALE)

    def test_cascade_staleness_missing(self):
        with self.assertRaises(ValueError):
            self.engine.cascade_staleness("missing")

    def test_get_freshness_report(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        report = self.engine.get_freshness_report()
        self.assertIn("by_status", report)
        self.assertEqual(report["by_status"][FreshnessStatus.CURRENT.value], 1)
        self.assertEqual(report["by_source_type"][KnowledgeSourceType.DOCUMENTATION.value], 1)
        self.assertGreaterEqual(report["avg_age_seconds"], 0.0)

    def test_search_by_tags(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, tags=["tag1", "tag2"])
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION, tags=["tag2", "tag3"])
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        
        res = self.engine.search_by_tags(["tag1"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].article_id, "a1")
        
        res2 = self.engine.search_by_tags(["tag2"])
        self.assertEqual(len(res2), 2)

    def test_delete_expired(self):
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, expires_at=past, updated_at=past)
        self.engine.ingest_article(a1)
        self.engine.check_freshness("a1")
        
        count = self.engine.delete_expired(5)
        self.assertEqual(count, 1)
        self.assertNotIn("a1", self.engine._articles)
        self.assertNotIn("a1", self.engine._versions)

    def test_delete_expired_not_old_enough(self):
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, expires_at=now, updated_at=now)
        self.engine.ingest_article(a1)
        self.engine.check_freshness("a1")
        
        count = self.engine.delete_expired(10)
        self.assertEqual(count, 0)

    def test_delete_expired_not_expired(self):
        past = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, updated_at=past)
        self.engine.ingest_article(a1)
        
        count = self.engine.delete_expired(5)
        self.assertEqual(count, 0)

    def test_check_freshness_malformed_expires_at(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, expires_at="invalid")
        self.engine.ingest_article(a1)
        status = self.engine.check_freshness("a1")
        self.assertEqual(status, FreshnessStatus.EXPIRED)

    def test_check_freshness_malformed_updated_at(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=0)
        self.engine.ingest_article(a1)
        a1.updated_at = "invalid"
        status = self.engine.check_freshness("a1")
        self.assertEqual(status, FreshnessStatus.STALE)

    def test_get_stale_articles_malformed_updated_at(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, ttl_seconds=86400)
        self.engine.ingest_article(a1)
        a1.updated_at = "invalid"
        stale = self.engine.get_stale_articles(max_age_seconds=10)
        self.assertEqual(len(stale), 0)

    def test_get_freshness_report_malformed_updated_at(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION)
        self.engine.ingest_article(a1)
        a1.updated_at = "invalid"
        report = self.engine.get_freshness_report()
        self.assertEqual(report["avg_age_seconds"], 0.0)

    def test_delete_expired_malformed_updated_at(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, expires_at="invalid", updated_at="invalid")
        self.engine.ingest_article(a1)
        self.engine.check_freshness("a1")
        count = self.engine.delete_expired(max_age_seconds=0)
        self.assertEqual(count, 0)

    def test_dependency_graph_cycle(self):
        a1 = KnowledgeArticle(article_id="a1", title="1", source_type=KnowledgeSourceType.DOCUMENTATION, dependencies=["a2"])
        a2 = KnowledgeArticle(article_id="a2", title="2", source_type=KnowledgeSourceType.DOCUMENTATION, dependencies=["a1"])
        self.engine.ingest_article(a1)
        self.engine.ingest_article(a2)
        graph = self.engine.get_dependency_graph("a1")
        self.assertIn("a1", graph)
        self.assertIn("a2", graph)

if __name__ == '__main__':
    unittest.main()
