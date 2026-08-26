from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from threading import RLock

from .errors import DomainError, require
from .ledger import LedgerService
from .models import (
    Acceptance,
    BudgetDecision,
    ChangeOrder,
    ChangeOrderState,
    EstimateDistribution,
    PricingModel,
    ProjectContract,
    Quote,
    QuoteState,
    canonical_digest,
    require_aware,
)
from .money import Money, checked_add, checked_i64, normalize_currency, require_non_negative, require_positive


class TaskCostEstimator:
    """Deterministic nearest-rank cost percentiles with a separate machine ETA."""

    @staticmethod
    def estimate(*, cost_samples_minor: tuple[int, ...], machine_eta_seconds: int) -> EstimateDistribution:
        require(bool(cost_samples_minor), "ESTIMATE_SAMPLES_REQUIRED", "at least one cost sample is required")
        for value in cost_samples_minor:
            require_non_negative(value, field="cost_sample_minor")
        require_non_negative(machine_eta_seconds, field="machine_eta_seconds")
        ordered = tuple(sorted(cost_samples_minor))
        return EstimateDistribution(
            p50_minor=TaskCostEstimator._nearest_rank(ordered, 50),
            p80_minor=TaskCostEstimator._nearest_rank(ordered, 80),
            p90_minor=TaskCostEstimator._nearest_rank(ordered, 90),
            machine_eta_seconds=machine_eta_seconds,
            sample_count=len(ordered),
        )

    @staticmethod
    def _nearest_rank(ordered: tuple[int, ...], percentile: int) -> int:
        rank = max(1, (percentile * len(ordered) + 99) // 100)
        return ordered[rank - 1]


class QuoteBudgetService:
    """Scope-bound quotes with atomic reserve and hard-cap preflight decisions."""

    _MODEL_STRATEGIES = frozenset({"ECONOMY", "BALANCED", "BEST_QUALITY"})

    def __init__(self, ledger: LedgerService) -> None:
        self._ledger = ledger
        self._lock = RLock()
        self._quotes: dict[str, Quote] = {}
        self._spend_idempotency: dict[tuple[str, str], tuple[str, Quote]] = {}

    def create(
        self,
        *,
        quote_id: str,
        tenant_id: str,
        scope_digest: str,
        money: Money,
        estimate: EstimateDistribution,
        price_book_id: str,
        price_book_version: int,
        price_book_digest: str,
        model_strategy: str,
        human_time_reference_seconds: int,
        confidence_basis_points: int,
        hard_cap_minor: int,
        threshold_percents: tuple[int, ...],
        expires_at: datetime,
    ) -> Quote:
        require(bool(quote_id.strip()), "QUOTE_ID_REQUIRED", "quote_id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require_positive(money.minor, field="quote_minor")
        require_positive(hard_cap_minor, field="hard_cap_minor")
        require(hard_cap_minor >= money.minor, "HARD_CAP_BELOW_QUOTE", "hard cap cannot be below quoted amount")
        require(bool(price_book_id.strip()), "PRICE_BOOK_ID_REQUIRED", "price_book_id is required")
        require_positive(price_book_version, field="price_book_version")
        require(bool(price_book_digest.strip()), "PRICE_BOOK_DIGEST_REQUIRED", "price_book_digest is required")
        require(model_strategy in self._MODEL_STRATEGIES, "INVALID_MODEL_STRATEGY", "model strategy is unsupported")
        require_non_negative(human_time_reference_seconds, field="human_time_reference_seconds")
        require(
            0 <= confidence_basis_points <= 10_000,
            "INVALID_CONFIDENCE_BASIS_POINTS",
            "confidence basis points must be in 0..10000",
        )
        require_non_negative(confidence_basis_points, field="confidence_basis_points")
        for threshold in threshold_percents:
            checked_i64(threshold, field="threshold_percent")
        require(
            tuple(sorted(set(threshold_percents))) == threshold_percents
            and all(0 < threshold <= 100 for threshold in threshold_percents),
            "INVALID_BUDGET_THRESHOLDS",
            "thresholds must be unique, sorted percentages in 1..100",
        )
        normalized_expiry = require_aware(expires_at, field_name="expires_at")
        require(bool(scope_digest.strip()), "SCOPE_DIGEST_REQUIRED", "scope digest is required")
        estimate_snapshot_digest = canonical_digest(
            {
                "p50_minor": estimate.p50_minor,
                "p80_minor": estimate.p80_minor,
                "p90_minor": estimate.p90_minor,
                "machine_eta_seconds": estimate.machine_eta_seconds,
                "sample_count": estimate.sample_count,
            }
        )
        with self._lock:
            require(quote_id not in self._quotes, "QUOTE_EXISTS", "quote id already exists")
            quote = Quote(
                quote_id=quote_id,
                tenant_id=tenant_id,
                scope_digest=scope_digest,
                money=money,
                estimate=estimate,
                estimate_snapshot_digest=estimate_snapshot_digest,
                price_book_id=price_book_id,
                price_book_version=price_book_version,
                price_book_digest=price_book_digest,
                model_strategy=model_strategy,
                human_time_reference_seconds=human_time_reference_seconds,
                confidence_basis_points=confidence_basis_points,
                hard_cap_minor=hard_cap_minor,
                threshold_percents=threshold_percents,
                expires_at=normalized_expiry,
                state=QuoteState.OPEN,
            )
            self._quotes[quote_id] = quote
            return quote

    def accept(
        self,
        *,
        quote_id: str,
        tenant_id: str,
        scope_digest: str,
        accepted_by: str,
        accepted_at: datetime,
    ) -> Quote:
        require(bool(accepted_by.strip()), "ACCEPTED_BY_REQUIRED", "accepted_by is required")
        normalized_at = require_aware(accepted_at, field_name="accepted_at")
        with self._lock:
            quote = self._required(quote_id)
            require(quote.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "quote belongs to another tenant")
            require(quote.scope_digest == scope_digest, "QUOTE_SCOPE_MISMATCH", "accepted scope does not match quote")
            if quote.state is QuoteState.ACCEPTED:
                require(
                    quote.accepted_by == accepted_by, "QUOTE_ALREADY_ACCEPTED", "quote was accepted by another actor"
                )
                return quote
            require(quote.state is QuoteState.OPEN, "QUOTE_NOT_OPEN", "quote is not open")
            require(normalized_at <= quote.expires_at, "QUOTE_EXPIRED", "quote expired before acceptance")
            reserve = self._ledger.reserve(
                tenant_id=tenant_id,
                money=Money(quote.money.currency, quote.hard_cap_minor),
                idempotency_key=f"quote-accept:{quote_id}",
                reference=quote_id,
                occurred_at=normalized_at,
            )
            accepted = replace(
                quote,
                state=QuoteState.ACCEPTED,
                accepted_at=normalized_at,
                accepted_by=accepted_by,
                reserve_transaction_id=reserve.transaction_id,
            )
            self._quotes[quote_id] = accepted
            return accepted

    def expire(self, *, quote_id: str, tenant_id: str, as_of: datetime) -> Quote:
        normalized_at = require_aware(as_of, field_name="as_of")
        with self._lock:
            quote = self._required(quote_id)
            require(quote.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "quote belongs to another tenant")
            if quote.state is QuoteState.OPEN and normalized_at > quote.expires_at:
                quote = replace(quote, state=QuoteState.EXPIRED)
                self._quotes[quote_id] = quote
            return quote

    def preflight_spend(
        self,
        *,
        quote_id: str,
        tenant_id: str,
        next_minor: int,
        approved_thresholds: frozenset[int] = frozenset(),
    ) -> BudgetDecision:
        require_positive(next_minor, field="next_minor")
        for threshold in approved_thresholds:
            checked_i64(threshold, field="approved_threshold")
        with self._lock:
            quote = self._required(quote_id)
            require(quote.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "quote belongs to another tenant")
            require(quote.state is QuoteState.ACCEPTED, "QUOTE_NOT_ACCEPTED", "spend requires an accepted quote")
            projected = checked_add(quote.committed_spend_minor, next_minor, field="projected_spend_minor")
            if projected > quote.hard_cap_minor:
                return BudgetDecision(False, projected, quote.hard_cap_minor, (), "HARD_CAP_EXCEEDED")
            crossed = tuple(
                threshold
                for threshold in quote.threshold_percents
                if quote.committed_spend_minor * 100 < quote.hard_cap_minor * threshold <= projected * 100
            )
            missing = tuple(threshold for threshold in crossed if threshold not in approved_thresholds)
            if missing:
                return BudgetDecision(False, projected, quote.hard_cap_minor, missing, "THRESHOLD_APPROVAL_REQUIRED")
            return BudgetDecision(True, projected, quote.hard_cap_minor, crossed, "ALLOWED")

    def commit_spend(
        self,
        *,
        quote_id: str,
        tenant_id: str,
        amount_minor: int,
        idempotency_key: str,
        approved_thresholds: frozenset[int] = frozenset(),
    ) -> Quote:
        require(bool(idempotency_key.strip()), "IDEMPOTENCY_KEY_REQUIRED", "idempotency key is required")
        fingerprint = canonical_digest(
            {
                "quote_id": quote_id,
                "tenant_id": tenant_id,
                "amount_minor": amount_minor,
                "approved_thresholds": sorted(approved_thresholds),
            }
        )
        with self._lock:
            key = (tenant_id, idempotency_key)
            existing = self._spend_idempotency.get(key)
            if existing is not None:
                require(existing[0] == fingerprint, "IDEMPOTENCY_CONFLICT", "idempotency key has different input")
                return existing[1]
            decision = self.preflight_spend(
                quote_id=quote_id,
                tenant_id=tenant_id,
                next_minor=amount_minor,
                approved_thresholds=approved_thresholds,
            )
            require(decision.allowed, decision.reason, "spend failed the pre-side-effect budget guard")
            quote = self._required(quote_id)
            updated = replace(quote, committed_spend_minor=decision.projected_minor)
            self._quotes[quote_id] = updated
            self._spend_idempotency[key] = (fingerprint, updated)
            return updated

    def get(self, *, quote_id: str, tenant_id: str) -> Quote:
        with self._lock:
            quote = self._required(quote_id)
            require(quote.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "quote belongs to another tenant")
            return quote

    def _required(self, quote_id: str) -> Quote:
        try:
            return self._quotes[quote_id]
        except KeyError as exc:
            raise DomainError("QUOTE_NOT_FOUND", "quote was not found") from exc


class ProjectContractService:
    """Fixed/capped contract state with maker-checker change orders and acceptance."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._contracts: dict[str, ProjectContract] = {}
        self._changes: dict[str, ChangeOrder] = {}
        self._acceptances: dict[str, Acceptance] = {}

    def create(
        self,
        *,
        contract_id: str,
        tenant_id: str,
        model: PricingModel,
        scope_digest: str,
        currency: str,
        fixed_minor: int = 0,
        cap_minor: int = 0,
    ) -> ProjectContract:
        require(bool(contract_id.strip()), "CONTRACT_ID_REQUIRED", "contract_id is required")
        require(bool(tenant_id.strip()), "TENANT_REQUIRED", "tenant_id is required")
        require(bool(scope_digest.strip()), "SCOPE_DIGEST_REQUIRED", "scope_digest is required")
        require_non_negative(fixed_minor, field="fixed_minor")
        require_non_negative(cap_minor, field="cap_minor")
        if model is PricingModel.FIXED:
            require(
                fixed_minor > 0 and cap_minor == 0, "INVALID_FIXED_CONTRACT", "fixed contract requires only fixed_minor"
            )
        else:
            require(
                cap_minor > 0 and fixed_minor == 0, "INVALID_CAPPED_CONTRACT", "capped contract requires only cap_minor"
            )
        with self._lock:
            require(contract_id not in self._contracts, "CONTRACT_EXISTS", "contract id already exists")
            contract = ProjectContract(
                contract_id=contract_id,
                tenant_id=tenant_id,
                model=model,
                scope_digest=scope_digest,
                currency=normalize_currency(currency),
                fixed_minor=fixed_minor,
                cap_minor=cap_minor,
                version=1,
            )
            self._contracts[contract_id] = contract
            return contract

    def propose_change(
        self,
        *,
        change_id: str,
        contract_id: str,
        tenant_id: str,
        proposed_by: str,
        new_scope_digest: str,
        delta_minor: int,
    ) -> ChangeOrder:
        require(bool(change_id.strip()), "CHANGE_ORDER_ID_REQUIRED", "change_id is required")
        require(bool(proposed_by.strip()), "PROPOSED_BY_REQUIRED", "proposed_by is required")
        require(bool(new_scope_digest.strip()), "SCOPE_DIGEST_REQUIRED", "new_scope_digest is required")
        checked_i64(delta_minor, field="delta_minor")
        with self._lock:
            self._required_contract(contract_id, tenant_id)
            require(change_id not in self._changes, "CHANGE_ORDER_EXISTS", "change order already exists")
            change = ChangeOrder(
                change_id=change_id,
                contract_id=contract_id,
                proposed_by=proposed_by,
                new_scope_digest=new_scope_digest,
                delta_minor=delta_minor,
                state=ChangeOrderState.PROPOSED,
            )
            self._changes[change_id] = change
            return change

    def approve_change(self, *, change_id: str, tenant_id: str, approved_by: str) -> ProjectContract:
        require(bool(approved_by.strip()), "APPROVED_BY_REQUIRED", "approved_by is required")
        with self._lock:
            try:
                change = self._changes[change_id]
            except KeyError as exc:
                raise DomainError("CHANGE_ORDER_NOT_FOUND", "change order was not found") from exc
            contract = self._required_contract(change.contract_id, tenant_id)
            require(
                change.state is ChangeOrderState.PROPOSED, "CHANGE_ORDER_NOT_PROPOSED", "change order is not proposed"
            )
            require(change.proposed_by != approved_by, "MAKER_CHECKER_VIOLATION", "proposer cannot approve own change")
            if contract.model is PricingModel.FIXED:
                new_fixed = checked_add(contract.fixed_minor, change.delta_minor, field="changed_fixed_minor")
                require(new_fixed > 0, "INVALID_CHANGED_FIXED_PRICE", "changed fixed price must remain positive")
                updated = replace(
                    contract,
                    scope_digest=change.new_scope_digest,
                    fixed_minor=new_fixed,
                    version=contract.version + 1,
                )
            else:
                new_cap = checked_add(contract.cap_minor, change.delta_minor, field="changed_cap_minor")
                require(new_cap > 0, "INVALID_CHANGED_CAP", "changed cap must remain positive")
                updated = replace(
                    contract,
                    scope_digest=change.new_scope_digest,
                    cap_minor=new_cap,
                    version=contract.version + 1,
                )
            self._contracts[contract.contract_id] = updated
            self._changes[change_id] = replace(change, state=ChangeOrderState.APPROVED, decided_by=approved_by)
            return updated

    def accept_milestone(
        self,
        *,
        acceptance_id: str,
        contract_id: str,
        tenant_id: str,
        milestone: str,
        accepted_by: str,
        accepted_at: datetime,
        scope_digest: str,
    ) -> Acceptance:
        require(bool(acceptance_id.strip()), "ACCEPTANCE_ID_REQUIRED", "acceptance_id is required")
        require(bool(milestone.strip()), "MILESTONE_REQUIRED", "milestone is required")
        require(bool(accepted_by.strip()), "ACCEPTED_BY_REQUIRED", "accepted_by is required")
        normalized_at = require_aware(accepted_at, field_name="accepted_at")
        with self._lock:
            contract = self._required_contract(contract_id, tenant_id)
            require(contract.scope_digest == scope_digest, "ACCEPTANCE_SCOPE_MISMATCH", "acceptance scope is stale")
            require(acceptance_id not in self._acceptances, "ACCEPTANCE_EXISTS", "acceptance id already exists")
            acceptance = Acceptance(
                acceptance_id=acceptance_id,
                contract_id=contract_id,
                milestone=milestone,
                accepted_by=accepted_by,
                accepted_at=normalized_at,
                scope_digest=scope_digest,
            )
            self._acceptances[acceptance_id] = acceptance
            return acceptance

    def billable_minor(self, *, contract_id: str, tenant_id: str, measured_minor: int) -> int:
        require_non_negative(measured_minor, field="measured_minor")
        with self._lock:
            contract = self._required_contract(contract_id, tenant_id)
            return (
                contract.fixed_minor
                if contract.model is PricingModel.FIXED
                else min(measured_minor, contract.cap_minor)
            )

    def _required_contract(self, contract_id: str, tenant_id: str) -> ProjectContract:
        try:
            contract = self._contracts[contract_id]
        except KeyError as exc:
            raise DomainError("CONTRACT_NOT_FOUND", "project contract was not found") from exc
        require(contract.tenant_id == tenant_id, "TENANT_ISOLATION_VIOLATION", "contract belongs to another tenant")
        return contract
