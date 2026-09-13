from typing import List, Dict, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    ExpertDomain, ExpertValidationOutcome as ValidationOutcome, ExpertValidator, ExpertReview
)

class IndependentExpertValidationEngine:
    """
    Engine for managing independent expert validation workflows.
    """
    
    def __init__(self):
        self._validators: Dict[str, ExpertValidator] = {}
        self._reviews: Dict[str, ExpertReview] = {}

    def register_validator(self, validator: ExpertValidator) -> str:
        """Register a new expert validator."""
        self._validators[validator.validator_id] = validator
        return validator.validator_id

    def check_conflict_of_interest(self, validator_id: str, subject_org: str) -> bool:
        """Check if a validator has a conflict of interest with the subject organization."""
        if validator_id not in self._validators:
            raise ValueError(f"Validator {validator_id} not found.")
        validator = self._validators[validator_id]
        if validator.organization == subject_org:
            return True
        if subject_org in validator.conflicts_of_interest:
            return True
        return False

    def assign_review(self, review: ExpertReview) -> str:
        """Assign a review to a validator."""
        if review.validator_id not in self._validators:
            raise ValueError(f"Validator {review.validator_id} not found.")
        validator = self._validators[review.validator_id]
        if not validator.active:
            raise ValueError(f"Validator {validator.validator_id} is not active.")
        
        self._reviews[review.review_id] = review
        return review.review_id

    def submit_review(self, review_id: str, outcome: ValidationOutcome, findings: List[str], score: float, hours: float) -> ExpertReview:
        """Submit a completed review."""
        if review_id not in self._reviews:
            raise ValueError(f"Review {review_id} not found.")
        review = self._reviews[review_id]
        
        if review.outcome != ValidationOutcome.DEFERRED:
            raise ValueError(f"Review {review_id} has already been submitted.")
            
        if not (0.0 <= score <= 10.0):
            raise ValueError("Score must be between 0.0 and 10.0.")

        review.outcome = outcome
        review.findings = findings
        review.score = score
        review.review_hours = hours
        review.submitted_at = datetime.utcnow().isoformat()
        
        # Update validator stats
        validator = self._validators[review.validator_id]
        validator.total_reviews += 1
        
        total_hours = (validator.avg_review_hours * (validator.total_reviews - 1)) + hours
        validator.avg_review_hours = total_hours / validator.total_reviews
        
        # Calculate approval rate based on completed reviews
        completed_reviews = [r for r in self._reviews.values() if r.validator_id == validator.validator_id and r.outcome != ValidationOutcome.DEFERRED]
        approved_count = sum(1 for r in completed_reviews if r.outcome in [ValidationOutcome.APPROVED, ValidationOutcome.CONDITIONALLY_APPROVED])
        if completed_reviews:
            validator.approval_rate = approved_count / len(completed_reviews)
            
        return review

    def get_consensus(self, subject_id: str) -> Dict:
        """Get the consensus of reviews for a subject."""
        subject_reviews = [r for r in self._reviews.values() if r.subject_id == subject_id and r.outcome != ValidationOutcome.DEFERRED]
        
        if len(subject_reviews) < 2:
            return {
                "consensus_reached": False,
                "reason": "Requires at least 2 submitted reviews.",
                "review_count": len(subject_reviews)
            }
            
        outcomes = [r.outcome for r in subject_reviews]
        from collections import Counter
        outcome_counts = Counter(outcomes)
        majority_outcome = outcome_counts.most_common(1)[0][0]
        
        avg_score = sum(r.score for r in subject_reviews) / len(subject_reviews)
        all_findings = []
        for r in subject_reviews:
            all_findings.extend(r.findings)
            
        return {
            "consensus_reached": True,
            "majority_outcome": majority_outcome,
            "average_score": avg_score,
            "total_findings": len(all_findings),
            "all_findings": all_findings,
            "review_count": len(subject_reviews)
        }

    def get_available_validators(self, domain: ExpertDomain, exclude_orgs: List[str] = None) -> List[ExpertValidator]:
        """Get available validators for a given domain, excluding conflicts."""
        exclude_orgs = exclude_orgs or []
        available = []
        for validator in self._validators.values():
            if validator.domain == domain and validator.active:
                conflict = False
                for org in exclude_orgs:
                    if self.check_conflict_of_interest(validator.validator_id, org):
                        conflict = True
                        break
                if not conflict:
                    available.append(validator)
        return available

    def get_validator_stats(self, validator_id: str) -> Dict:
        """Get statistics for a specific validator."""
        if validator_id not in self._validators:
            raise ValueError(f"Validator {validator_id} not found.")
        validator = self._validators[validator_id]
        
        return {
            "total_reviews": validator.total_reviews,
            "approval_rate": validator.approval_rate,
            "avg_review_hours": validator.avg_review_hours,
        }

    def get_pending_reviews(self) -> List[ExpertReview]:
        """Get all unsubmitted reviews."""
        return [r for r in self._reviews.values() if r.outcome == ValidationOutcome.DEFERRED]

    def get_subject_status(self, subject_id: str) -> Dict:
        """Get the status of all reviews for a subject."""
        subject_reviews = [r for r in self._reviews.values() if r.subject_id == subject_id]
        consensus = self.get_consensus(subject_id)
        
        return {
            "subject_id": subject_id,
            "total_reviews": len(subject_reviews),
            "pending_reviews": len([r for r in subject_reviews if r.outcome == ValidationOutcome.DEFERRED]),
            "consensus": consensus,
            "reviews": subject_reviews
        }

    def get_validation_report(self) -> Dict:
        """Generate a report of all validations."""
        by_domain = {}
        by_outcome = {}
        total_score = 0.0
        completed_reviews = [r for r in self._reviews.values() if r.outcome != ValidationOutcome.DEFERRED]
        
        for r in completed_reviews:
            by_domain[r.domain] = by_domain.get(r.domain, 0) + 1
            by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
            total_score += r.score
            
        return {
            "total_reviews": len(self._reviews),
            "completed_reviews": len(completed_reviews),
            "by_domain": by_domain.copy(), # copying enum keys? by_domain uses enum string
            "by_outcome": by_outcome,
            "average_score": total_score / len(completed_reviews) if completed_reviews else 0.0
        }

    def require_independent_validation(self, subject_id: str, min_reviewers: int, domain: ExpertDomain) -> Dict:
        """Check if a subject has met the independent validation requirements."""
        subject_reviews = [r for r in self._reviews.values() if r.subject_id == subject_id and r.domain == domain]
        independent_completed = [r for r in subject_reviews if r.independent and r.outcome != ValidationOutcome.DEFERRED]
        
        met_requirement = len(independent_completed) >= min_reviewers
        
        return {
            "requirement_met": met_requirement,
            "independent_reviews_count": len(independent_completed),
            "required_reviews": min_reviewers,
            "domain": domain
        }
