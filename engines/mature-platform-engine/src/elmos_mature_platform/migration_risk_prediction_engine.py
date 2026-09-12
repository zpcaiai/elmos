from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    MigrationProject,
    MigrationRiskFactor,
    RiskPrediction,
    MigrationRiskLevel,
    MigrationRiskCategory
)

class MigrationRiskPredictionEngine:
    def __init__(self):
        self.projects: Dict[str, MigrationProject] = {}
        self.factors: Dict[str, List[MigrationRiskFactor]] = {}

    def create_project(self, project: MigrationProject) -> str:
        """Create a new migration project."""
        self.projects[project.project_id] = project
        self.factors[project.project_id] = []
        return project.project_id

    def add_risk_factor(self, project_id: str, factor: MigrationRiskFactor) -> None:
        """Add a risk factor to a project and compute its risk score."""
        if project_id not in self.projects:
            raise ValueError(f"Project {project_id} not found")
        factor.risk_score = factor.likelihood * factor.impact
        self.factors[project_id].append(factor)
        self.compute_overall_risk(project_id)

    def get_risk_factors(self, project_id: str) -> List[MigrationRiskFactor]:
        """Get all risk factors for a given project."""
        if project_id not in self.factors:
            raise ValueError(f"Project {project_id} not found")
        return self.factors[project_id]

    def _get_risk_level(self, score: float) -> MigrationRiskLevel:
        if score > 0.8: return MigrationRiskLevel.CRITICAL
        if score > 0.6: return MigrationRiskLevel.HIGH
        if score > 0.4: return MigrationRiskLevel.MEDIUM
        if score > 0.2: return MigrationRiskLevel.LOW
        return MigrationRiskLevel.MINIMAL

    def compute_overall_risk(self, project_id: str) -> MigrationProject:
        """Compute weighted average of risk factors and set overall risk level."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        factors = self.factors.get(project_id, [])
        if not factors:
            project.overall_risk_score = 0.0
            project.overall_risk_level = MigrationRiskLevel.MINIMAL
            return project
            
        avg_score = sum(f.risk_score for f in factors) / len(factors)
        project.overall_risk_score = avg_score
        project.overall_risk_level = self._get_risk_level(avg_score)
        return project

    def predict_outcome(self, project_id: str) -> RiskPrediction:
        """Predict success probability based on factors and project attributes."""
        project = self.compute_overall_risk(project_id)
        factors = self.factors.get(project_id, [])
        
        # Base probability is 1 - overall_risk_score
        prob = 1.0 - project.overall_risk_score
        
        # Adjust based on project complexity and team experience
        # complexity is 0-10, team experience is 0-10
        complexity_penalty = (project.complexity_score / 10.0) * 0.2
        experience_bonus = (project.team_experience_score / 10.0) * 0.2
        prob = prob - complexity_penalty + experience_bonus
        prob = max(0.0, min(1.0, prob))
        
        sorted_factors = sorted(factors, key=lambda f: f.risk_score, reverse=True)
        top_factors = [f.factor_id for f in sorted_factors[:3]]
        mitigations = [f.mitigation for f in sorted_factors[:3] if f.mitigation and not f.mitigated]
        
        return RiskPrediction(
            project_id=project_id,
            predicted_risk_level=project.overall_risk_level,
            confidence=min(1.0, len(factors) * 0.1 + 0.5),
            predicted_success_probability=prob,
            top_risk_factors=top_factors,
            recommended_mitigations=mitigations
        )

    def mitigate_factor(self, project_id: str, factor_id: str, mitigation: str) -> MigrationRiskFactor:
        """Apply mitigation, reducing the factor's risk score by 50%."""
        factors = self.factors.get(project_id, [])
        for f in factors:
            if f.factor_id == factor_id:
                if not f.mitigated:
                    f.mitigation = mitigation
                    f.mitigated = True
                    f.risk_score *= 0.5
                    self.compute_overall_risk(project_id)
                return f
        raise ValueError(f"Factor {factor_id} not found in project {project_id}")

    def record_outcome(self, project_id: str, succeeded: bool, actual_days: int) -> None:
        """Record the actual outcome of the migration project."""
        project = self.projects.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        project.succeeded = succeeded
        project.actual_duration_days = actual_days

    def get_historical_accuracy(self) -> Dict:
        """Compare predicted outcomes against actual recorded outcomes."""
        completed = [p for p in self.projects.values() if p.succeeded is not None]
        if not completed:
            return {"accuracy": 0.0, "total_completed": 0, "correct_predictions": 0}
        
        correct = 0
        for p in completed:
            pred = self.predict_outcome(p.project_id)
            predicted_success = pred.predicted_success_probability >= 0.5
            if predicted_success == p.succeeded:
                correct += 1
                
        return {
            "accuracy": correct / len(completed),
            "total_completed": len(completed),
            "correct_predictions": correct
        }

    def get_similar_projects(self, project_id: str, top_n: int = 5) -> List[MigrationProject]:
        """Find similar projects based on source system, target system, and data size."""
        target_project = self.projects.get(project_id)
        if not target_project:
            raise ValueError(f"Project {project_id} not found")
            
        similar = []
        for p in self.projects.values():
            if p.project_id == project_id:
                continue
            
            score = 0
            if p.source_system == target_project.source_system: score += 3
            if p.target_system == target_project.target_system: score += 3
            
            # size diff penalty
            size_diff = abs(p.data_size_gb - target_project.data_size_gb)
            if size_diff < 100:
                score += 2
            elif size_diff < 500:
                score += 1
                
            if score > 0:
                similar.append((score, p))
                
        similar.sort(key=lambda x: x[0], reverse=True)
        return [p for score, p in similar[:top_n]]

    def get_risk_heatmap(self) -> Dict[str, float]:
        """Generate a heatmap of risk categories across all projects."""
        category_scores: Dict[str, List[float]] = {cat.value: [] for cat in MigrationRiskCategory}
        
        for factors in self.factors.values():
            for f in factors:
                category_scores[f.category.value].append(f.risk_score)
                
        heatmap = {}
        for cat, scores in category_scores.items():
            if scores:
                heatmap[cat] = sum(scores) / len(scores)
            else:
                heatmap[cat] = 0.0
                
        return heatmap

    def get_risk_report(self, project_id: str) -> Dict:
        """Generate a risk summary report for a project."""
        project = self.compute_overall_risk(project_id)
        factors = self.factors.get(project_id, [])
        pred = self.predict_outcome(project_id)
        
        return {
            "project_id": project.project_id,
            "project_name": project.name,
            "overall_risk_level": project.overall_risk_level.value,
            "overall_risk_score": project.overall_risk_score,
            "predicted_success_probability": pred.predicted_success_probability,
            "total_factors": len(factors),
            "top_risk_factors": pred.top_risk_factors,
            "recommended_mitigations": pred.recommended_mitigations,
            "mitigated_factors": len([f for f in factors if f.mitigated])
        }
