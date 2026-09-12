import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from elmos_mature_platform.types import (
    RouteCertificationStatus,
    MigrationRouteCell,
    RouteBreadthMatrixReport
)

class RouteBreadthCertificationEngine:
    """Engine for tracking, certifying, and reporting multi-language migration route breadth across the platform."""

    def __init__(self):
        self._routes: Dict[str, MigrationRouteCell] = {}  # route_id -> MigrationRouteCell
        self._route_lookup: Dict[str, str] = {}  # key -> route_id

    def _route_key(self, source_lang: str, target_lang: str, source_fw: str = "", target_fw: str = "") -> str:
        return f"{source_lang.lower()}::{source_fw.lower()}->{target_lang.lower()}::{target_fw.lower()}"

    def register_route(self, cell: MigrationRouteCell) -> str:
        """Register a migration route cell in the breadth catalog."""
        if cell.route_id in self._routes:
            raise ValueError(f"Route {cell.route_id} already registered")
        
        key = self._route_key(cell.source_language, cell.target_language, cell.source_framework, cell.target_framework)
        if key in self._route_lookup:
            raise ValueError(f"Route {key} already exists with ID {self._route_lookup[key]}")

        self._routes[cell.route_id] = cell
        self._route_lookup[key] = cell.route_id
        return cell.route_id

    def get_route(self, route_id: str) -> Optional[MigrationRouteCell]:
        """Retrieve a route cell by ID."""
        return self._routes.get(route_id)

    def find_route_by_pair(
        self,
        source_lang: str,
        target_lang: str,
        source_fw: str = "",
        target_fw: str = ""
    ) -> Optional[MigrationRouteCell]:
        """Find a route by its source and target coordinates."""
        key = self._route_key(source_lang, target_lang, source_fw, target_fw)
        route_id = self._route_lookup.get(key)
        return self._routes.get(route_id) if route_id else None

    def list_routes(
        self,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        status: Optional[RouteCertificationStatus] = None
    ) -> List[MigrationRouteCell]:
        """List registered routes matching optional filter criteria."""
        routes = list(self._routes.values())
        if source_language:
            routes = [r for r in routes if r.source_language.lower() == source_language.lower()]
        if target_language:
            routes = [r for r in routes if r.target_language.lower() == target_language.lower()]
        if status:
            routes = [r for r in routes if r.status == status]
        return routes

    def update_route_metrics(
        self,
        route_id: str,
        test_coverage_pct: float,
        syntax_fidelity_score: float,
        semantic_equivalence_score: float,
        limitations: Optional[List[str]] = None
    ) -> MigrationRouteCell:
        """Update test coverage and fidelity scores for a route cell."""
        route = self.get_route(route_id)
        if not route:
            raise ValueError(f"Route {route_id} not found")
        route.test_coverage_pct = test_coverage_pct
        route.syntax_fidelity_score = syntax_fidelity_score
        route.semantic_equivalence_score = semantic_equivalence_score
        if limitations is not None:
            route.known_limitations = limitations
        return route

    def evaluate_certification(
        self,
        route_id: str,
        certifier: str = "platform-gate",
        min_coverage: float = 85.0,
        min_syntax: float = 90.0,
        min_semantic: float = 90.0
    ) -> MigrationRouteCell:
        """Evaluate qualification criteria and certify or provisionalize a route."""
        route = self.get_route(route_id)
        if not route:
            raise ValueError(f"Route {route_id} not found")

        cov_ok = route.test_coverage_pct >= min_coverage
        syn_ok = route.syntax_fidelity_score >= min_syntax
        sem_ok = route.semantic_equivalence_score >= min_semantic

        now_str = datetime.now(timezone.utc).isoformat()
        route.certifier = certifier

        if cov_ok and syn_ok and sem_ok:
            route.status = RouteCertificationStatus.CERTIFIED
            route.certified_at = now_str
        elif (route.test_coverage_pct >= min_coverage * 0.8 and 
              route.syntax_fidelity_score >= min_syntax * 0.8):
            route.status = RouteCertificationStatus.PROVISIONAL
            route.certified_at = now_str
        else:
            route.status = RouteCertificationStatus.CANDIDATE

        return route

    def deprecate_route(self, route_id: str, reason: str = "") -> MigrationRouteCell:
        """Deprecate a migration route."""
        route = self.get_route(route_id)
        if not route:
            raise ValueError(f"Route {route_id} not found")
        route.status = RouteCertificationStatus.DEPRECATED
        if reason:
            route.known_limitations.append(f"DEPRECATED: {reason}")
        return route

    def generate_matrix_report(self) -> RouteBreadthMatrixReport:
        """Generate comprehensive matrix report on route breadth and certification status."""
        total = len(self._routes)
        certified = sum(1 for r in self._routes.values() if r.status == RouteCertificationStatus.CERTIFIED)
        candidate = sum(1 for r in self._routes.values() if r.status == RouteCertificationStatus.CANDIDATE)
        provisional = sum(1 for r in self._routes.values() if r.status == RouteCertificationStatus.PROVISIONAL)

        language_pairs = set()
        for r in self._routes.values():
            language_pairs.add(f"{r.source_language}->{r.target_language}")

        coverage_breadth = (certified / total * 100.0) if total > 0 else 0.0

        return RouteBreadthMatrixReport(
            report_id=str(uuid.uuid4()),
            total_routes=total,
            certified_routes_count=certified,
            candidate_routes_count=candidate,
            provisional_routes_count=provisional,
            coverage_breadth_pct=round(coverage_breadth, 2),
            language_pairs_supported=sorted(list(language_pairs)),
            generated_at=datetime.now(timezone.utc).isoformat()
        )

    def find_migration_path(self, source_lang: str, target_lang: str) -> List[MigrationRouteCell]:
        """Find direct or single-hop certified/provisional migration routes connecting source to target language."""
        source_lower = source_lang.lower()
        target_lower = target_lang.lower()

        # 1. Direct route
        direct = [
            r for r in self._routes.values()
            if r.source_language.lower() == source_lower 
            and r.target_language.lower() == target_lower
            and r.status in {RouteCertificationStatus.CERTIFIED, RouteCertificationStatus.PROVISIONAL}
        ]
        if direct:
            return [direct[0]]

        # 2. Multi-hop (1 intermediate hop)
        intermediates = [
            r for r in self._routes.values()
            if r.source_language.lower() == source_lower
            and r.status in {RouteCertificationStatus.CERTIFIED, RouteCertificationStatus.PROVISIONAL}
        ]
        for step1 in intermediates:
            intermediate_lang = step1.target_language.lower()
            step2 = [
                r for r in self._routes.values()
                if r.source_language.lower() == intermediate_lang
                and r.target_language.lower() == target_lower
                and r.status in {RouteCertificationStatus.CERTIFIED, RouteCertificationStatus.PROVISIONAL}
            ]
            if step2:
                return [step1, step2[0]]

        return []
