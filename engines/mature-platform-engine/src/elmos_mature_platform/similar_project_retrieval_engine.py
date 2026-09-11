import math
import uuid
from typing import Optional, List, Dict, Any, Set
from elmos_mature_platform.types import (
    ProjectFingerprint,
    SimilarityMatchResult,
    TargetStackRecommendation
)

class SimilarProjectRetrievalEngine:
    """Engine for project fingerprinting, similarity search, effort estimation, and target stack recommendation."""

    def __init__(self):
        self._projects: Dict[str, ProjectFingerprint] = {}  # project_id -> ProjectFingerprint
        self._recommendations: Dict[str, TargetStackRecommendation] = {}  # source_framework.lower() -> TargetStackRecommendation
        self._historical_durations: Dict[str, float] = {}  # project_id -> duration_days
        self._project_recipes: Dict[str, List[str]] = {}  # project_id -> list of recipes used

        # Seed standard recommendations
        self._seed_default_recommendations()

    def _seed_default_recommendations(self):
        defaults = [
            ("struts1", "spring-boot-3", 0.95, "Modern Spring Boot with REST controllers and Spring Security replaces Struts1 Action/ActionForm lifecycle.", ["quarkus", "micronaut"]),
            ("struts2", "spring-boot-3", 0.92, "Spring Boot replaces Struts2 interceptor stack with modern filter chains and controllers.", ["quarkus", "aspnetcore"]),
            ("spring-boot-2", "spring-boot-3", 0.98, "Direct major upgrade with Jakarta EE 10 namespace migration and Spring 6 baseline.", ["quarkus"]),
            ("dotnet-framework", "dotnet-8", 0.96, "Direct modern .NET migration with cross-platform C# runtime and Kestrel web host.", ["dotnet-9"]),
            ("django-3", "django-5", 0.94, "Modern async-ready Django upgrade with updated ORM and security defaults.", ["fastapi"]),
            ("flask", "fastapi", 0.90, "Type-annotated ASGI async migration using Pydantic and OpenAPI native specs.", ["django-5", "litestar"]),
            ("angularjs", "react-19", 0.88, "Modern component architecture replacing legacy AngularJS 1.x two-way dirty-checking.", ["vue-3", "angular-18"]),
            ("vue-2", "vue-3", 0.97, "Composition API and Pinia state migration with modern Vite build chain.", ["react-19"]),
        ]
        for src, tgt, conf, rat, alts in defaults:
            self.register_recommendation(src, tgt, conf, rat, alts)

    def register_recommendation(self, source_framework: str, recommended_target: str, confidence: float, rationale: str, alternatives: List[str]) -> str:
        rec_id = str(uuid.uuid4())
        rec = TargetStackRecommendation(
            recommendation_id=rec_id,
            source_framework=source_framework,
            recommended_target_framework=recommended_target,
            confidence_score=confidence,
            rationale=rationale,
            alternatives=alternatives
        )
        self._recommendations[source_framework.lower()] = rec
        return rec_id

    def index_project(
        self,
        fingerprint: ProjectFingerprint,
        duration_days: float = 30.0,
        recipes: Optional[List[str]] = None
    ) -> str:
        """Index a project fingerprint with associated historical duration and applied recipes."""
        if fingerprint.project_id in self._projects:
            raise ValueError(f"Project {fingerprint.project_id} already indexed")
        self._projects[fingerprint.project_id] = fingerprint
        self._historical_durations[fingerprint.project_id] = duration_days
        self._project_recipes[fingerprint.project_id] = recipes or []
        return fingerprint.project_id

    def get_project(self, project_id: str) -> Optional[ProjectFingerprint]:
        """Retrieve indexed project fingerprint."""
        return self._projects.get(project_id)

    def list_projects(self) -> List[ProjectFingerprint]:
        """List all indexed project fingerprints."""
        return list(self._projects.values())

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    def calculate_similarity(self, query: ProjectFingerprint, candidate: ProjectFingerprint) -> float:
        """Calculate composite similarity score between query and candidate projects (0.0 - 1.0)."""
        score = 0.0
        weights = {"exact_match": 0.35, "tags": 0.25, "size": 0.20, "vector": 0.20}

        # 1. Exact language & framework match
        exact_points = 0.0
        if query.source_language.lower() == candidate.source_language.lower():
            exact_points += 0.4
        if query.source_framework.lower() == candidate.source_framework.lower():
            exact_points += 0.4
        if query.architectural_pattern.lower() == candidate.architectural_pattern.lower():
            exact_points += 0.2
        score += weights["exact_match"] * exact_points

        # 2. Tag Jaccard similarity
        tag_sim = self._jaccard_similarity(
            set(t.lower() for t in query.tags),
            set(t.lower() for t in candidate.tags)
        )
        score += weights["tags"] * tag_sim

        # 3. LOC & Module size similarity
        loc_ratio = 0.0
        if query.loc_count > 0 and candidate.loc_count > 0:
            min_loc = min(query.loc_count, candidate.loc_count)
            max_loc = max(query.loc_count, candidate.loc_count)
            loc_ratio = min_loc / max_loc
        score += weights["size"] * loc_ratio

        # 4. Feature vector cosine similarity
        if query.feature_vector and candidate.feature_vector:
            vec_sim = max(0.0, self._cosine_similarity(query.feature_vector, candidate.feature_vector))
            score += weights["vector"] * vec_sim
        else:
            # Reallocate weight to exact match if no feature vector
            score += weights["vector"] * exact_points

        return min(1.0, max(0.0, score))

    def find_similar_projects(
        self,
        query: ProjectFingerprint,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[SimilarityMatchResult]:
        """Find the top-K most similar projects to a given query fingerprint."""
        results = []
        for pid, candidate in self._projects.items():
            if pid == query.project_id:
                continue
            sim = self.calculate_similarity(query, candidate)
            if sim >= min_score:
                shared_tags = list(set(query.tags).intersection(set(candidate.tags)))
                recipes = self._project_recipes.get(pid, [])
                duration = self._historical_durations.get(pid, 30.0)
                results.append(SimilarityMatchResult(
                    matched_project_id=pid,
                    similarity_score=round(sim, 4),
                    shared_tags=shared_tags,
                    recommended_recipes=recipes,
                    estimated_duration_days=duration
                ))

        results.sort(key=lambda r: r.similarity_score, reverse=True)
        return results[:top_k]

    def recommend_target_stack(self, source_framework: str) -> TargetStackRecommendation:
        """Recommend target stack for a given source framework."""
        key = source_framework.lower().strip()
        if key in self._recommendations:
            return self._recommendations[key]
        
        # Fallback default
        return TargetStackRecommendation(
            recommendation_id=str(uuid.uuid4()),
            source_framework=source_framework,
            recommended_target_framework="cloud-native-modern-stack",
            confidence_score=0.5,
            rationale=f"Standard modernization path for {source_framework}",
            alternatives=["containerized-runtime", "microservice-architecture"]
        )

    def estimate_migration_effort(self, query: ProjectFingerprint) -> Dict[str, Any]:
        """Estimate migration effort in duration and complexity based on similar historical projects."""
        similar = self.find_similar_projects(query, top_k=3, min_score=0.3)
        
        if not similar:
            # Baseline estimation from LOC
            loc = query.loc_count or 10000
            estimated_days = max(10.0, loc / 2000.0)
            confidence = 0.5
            recipes = []
        else:
            # Weighted average duration based on similarity
            total_weight = sum(s.similarity_score for s in similar)
            weighted_duration = sum(s.similarity_score * s.estimated_duration_days for s in similar)
            estimated_days = weighted_duration / total_weight if total_weight > 0 else 30.0
            confidence = min(0.95, similar[0].similarity_score)
            recipes = []
            for s in similar:
                for r in s.recommended_recipes:
                    if r not in recipes:
                        recipes.append(r)

        rec = self.recommend_target_stack(query.source_framework)

        return {
            "query_project_id": query.project_id,
            "estimated_duration_days": round(estimated_days, 1),
            "confidence_score": round(confidence, 2),
            "similar_projects_found": len(similar),
            "top_match_id": similar[0].matched_project_id if similar else None,
            "recommended_target_stack": rec.recommended_target_framework,
            "recommended_recipes": recipes
        }
