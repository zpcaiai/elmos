import uuid
import datetime
from typing import List, Dict, Optional
from elmos_mature_platform.types import (
    KnowledgeArticle,
    KnowledgeVersion,
    KnowledgeSourceType,
    FreshnessStatus
)

class KnowledgeFreshnessVersioningEngine:
    """
    Engine to manage knowledge freshness and versioning.
    """
    def __init__(self):
        self._articles: Dict[str, KnowledgeArticle] = {}
        self._versions: Dict[str, List[KnowledgeVersion]] = {}

    def ingest_article(self, article: KnowledgeArticle) -> str:
        """
        Register a new knowledge article and create version 1.
        """
        if not article.article_id:
            article.article_id = str(uuid.uuid4())
            
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        if not article.created_at:
            article.created_at = now
        if not article.updated_at:
            article.updated_at = now
            
        article.version = 1
        self._articles[article.article_id] = article
        
        version_id = str(uuid.uuid4())
        version = KnowledgeVersion(
            version_id=version_id,
            article_id=article.article_id,
            version_number=1,
            content_hash=article.content_hash,
            created_at=now,
            change_summary="Initial ingestion",
            author="System"
        )
        self._versions[article.article_id] = [version]
        
        return article.article_id

    def update_article(self, article_id: str, new_hash: str, change_summary: str, author: str) -> KnowledgeArticle:
        """
        Bump version, create KnowledgeVersion, update hash and timestamps.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        article = self._articles[article_id]
        if article.superseded_by:
            raise ValueError(f"Cannot update superseded article {article_id}.")
            
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        article.version += 1
        article.content_hash = new_hash
        article.updated_at = now
        
        version_id = str(uuid.uuid4())
        version = KnowledgeVersion(
            version_id=version_id,
            article_id=article.article_id,
            version_number=article.version,
            content_hash=new_hash,
            created_at=now,
            change_summary=change_summary,
            author=author
        )
        self._versions[article.article_id].append(version)
        
        return article

    def check_freshness(self, article_id: str) -> FreshnessStatus:
        """
        Compare expires_at with now, or ttl_seconds from updated_at.
        Returns and updates freshness_status.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        article = self._articles[article_id]
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if article.expires_at:
            try:
                expires = datetime.datetime.fromisoformat(article.expires_at)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                expires = now
                
            if now >= expires:
                article.freshness_status = FreshnessStatus.EXPIRED
                return article.freshness_status

        if article.updated_at:
            try:
                updated = datetime.datetime.fromisoformat(article.updated_at)
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                updated = now
                
            age = (now - updated).total_seconds()
            if age >= article.ttl_seconds:
                article.freshness_status = FreshnessStatus.STALE
                return article.freshness_status
                
        article.freshness_status = FreshnessStatus.CURRENT
        return article.freshness_status

    def refresh_article(self, article_id: str) -> KnowledgeArticle:
        """
        Reset freshness to CURRENT, update timestamps.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        article = self._articles[article_id]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        article.updated_at = now
        article.freshness_status = FreshnessStatus.CURRENT
        
        return article

    def supersede_article(self, old_id: str, new_id: str) -> KnowledgeArticle:
        """
        Mark old as superseded by new.
        """
        if old_id not in self._articles:
            raise ValueError(f"Old article {old_id} not found.")
        if new_id not in self._articles:
            raise ValueError(f"New article {new_id} not found.")
            
        old_article = self._articles[old_id]
        old_article.superseded_by = new_id
        old_article.freshness_status = FreshnessStatus.EXPIRED
        
        return old_article

    def get_version_history(self, article_id: str) -> List[KnowledgeVersion]:
        """
        All versions of article.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        return self._versions.get(article_id, [])

    def get_stale_articles(self, max_age_seconds: int = 0) -> List[KnowledgeArticle]:
        """
        Articles past TTL or expired. If max_age_seconds > 0, also includes articles older than max_age_seconds.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        result = []
        for article in self._articles.values():
            status = self.check_freshness(article.article_id)
            is_old = False
            if max_age_seconds > 0 and article.updated_at:
                try:
                    updated = datetime.datetime.fromisoformat(article.updated_at)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=datetime.timezone.utc)
                    age = (now - updated).total_seconds()
                    if age >= max_age_seconds:
                        is_old = True
                except ValueError:
                    pass
                    
            if status in (FreshnessStatus.STALE, FreshnessStatus.EXPIRED) or is_old:
                result.append(article)
                
        return result

    def get_dependency_graph(self, article_id: str) -> Dict:
        """
        Transitive deps.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        graph = {}
        visited = set()
        
        def build_graph(current_id):
            if current_id in visited:
                return
            visited.add(current_id)
            
            if current_id in self._articles:
                article = self._articles[current_id]
                graph[current_id] = article.dependencies
                for dep in article.dependencies:
                    build_graph(dep)
                    
        build_graph(article_id)
        return graph

    def cascade_staleness(self, article_id: str) -> List[str]:
        """
        When article goes stale, mark dependents stale too.
        Returns list of newly stale article IDs.
        """
        if article_id not in self._articles:
            raise ValueError(f"Article {article_id} not found.")
            
        stale_ids = []
        
        # Build reverse dependency graph
        rev_deps = {}
        for aid, art in self._articles.items():
            for dep in art.dependencies:
                rev_deps.setdefault(dep, []).append(aid)
                
        # BFS to propagate staleness
        queue = [article_id]
        while queue:
            current = queue.pop(0)
            if current in rev_deps:
                for dependent in rev_deps[current]:
                    if dependent in self._articles:
                        dep_art = self._articles[dependent]
                        if dep_art.freshness_status != FreshnessStatus.STALE:
                            dep_art.freshness_status = FreshnessStatus.STALE
                            stale_ids.append(dependent)
                            queue.append(dependent)
                            
        return stale_ids

    def get_freshness_report(self) -> Dict:
        """
        Summary: by status, by source_type, avg age, oldest articles
        """
        report = {
            "by_status": {},
            "by_source_type": {},
            "avg_age_seconds": 0.0,
            "oldest_articles": []
        }
        
        now = datetime.datetime.now(datetime.timezone.utc)
        total_age = 0.0
        count = 0
        
        articles_with_age = []
        
        for article in self._articles.values():
            status = article.freshness_status.value
            report["by_status"][status] = report["by_status"].get(status, 0) + 1
            
            src = article.source_type.value
            report["by_source_type"][src] = report["by_source_type"].get(src, 0) + 1
            
            if article.updated_at:
                try:
                    updated = datetime.datetime.fromisoformat(article.updated_at)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=datetime.timezone.utc)
                    age = (now - updated).total_seconds()
                    total_age += age
                    count += 1
                    articles_with_age.append((age, article.article_id))
                except ValueError:
                    pass
                    
        if count > 0:
            report["avg_age_seconds"] = total_age / count
            
        articles_with_age.sort(reverse=True)
        report["oldest_articles"] = [aid for age, aid in articles_with_age[:5]]
        
        return report

    def search_by_tags(self, tags: List[str]) -> List[KnowledgeArticle]:
        """
        Find articles matching any tag
        """
        search_tags = set(tags)
        result = []
        for article in self._articles.values():
            if search_tags.intersection(article.tags):
                result.append(article)
        return result

    def delete_expired(self, max_age_seconds: int) -> int:
        """
        Remove articles expired beyond threshold, return count
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        to_delete = []
        
        for article_id, article in self._articles.items():
            if article.freshness_status == FreshnessStatus.EXPIRED and article.updated_at:
                try:
                    updated = datetime.datetime.fromisoformat(article.updated_at)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=datetime.timezone.utc)
                    age = (now - updated).total_seconds()
                    if age >= max_age_seconds:
                        to_delete.append(article_id)
                except ValueError:
                    pass
                    
        for article_id in to_delete:
            del self._articles[article_id]
            if article_id in self._versions:
                del self._versions[article_id]
                
        return len(to_delete)
