"""ChinaDB Enterprise Corpora Package.

Contains 5 production industry domains with enterprise SQL schemas,
complex PL/SQL & T-SQL stored procedures, triggers, and verification suites:
1. Core Banking & Double-Entry Settlement
2. Insurance & Actuarial Claims
3. Telecom Billing & Real-Time Rating
4. Supply Chain Logistics & Warehouse FIFO
5. Enterprise ERP & Progressive Payroll HR
"""

from __future__ import annotations

from elmos_sql_transpiler.chinadb_enterprise_corpora.banking_settlement import (
    BankingSettlementCorpus,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.erp_payroll_hr import (
    ErpPayrollCorpus,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.insurance_claims import (
    InsuranceClaimsCorpus,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.supply_chain_logistics import (
    SupplyChainLogisticsCorpus,
)
from elmos_sql_transpiler.chinadb_enterprise_corpora.telecom_rating import (
    TelecomRatingCorpus,
)


class EnterpriseCorpusBase:
    """Base definition for enterprise corpora."""

    domain_name: str
    primary_source_dialect: str


_CORPORA: list[type[EnterpriseCorpusBase]] = [
    BankingSettlementCorpus,  # type: ignore[list-item]
    InsuranceClaimsCorpus,  # type: ignore[list-item]
    TelecomRatingCorpus,  # type: ignore[list-item]
    SupplyChainLogisticsCorpus,  # type: ignore[list-item]
    ErpPayrollCorpus,  # type: ignore[list-item]
]


def get_all_enterprise_corpora() -> list[type[EnterpriseCorpusBase]]:
    """Return all 5 enterprise industry workload corpora."""
    return list(_CORPORA)


def get_corpus_by_domain(domain: str) -> type[EnterpriseCorpusBase] | None:
    """Retrieve corpus class by domain name keyword."""
    d_lower = domain.lower()
    for c in _CORPORA:
        name = getattr(c, "domain_name", "")
        if d_lower in name.lower():
            return c
    return None


__all__ = [
    "BankingSettlementCorpus",
    "ErpPayrollCorpus",
    "InsuranceClaimsCorpus",
    "SupplyChainLogisticsCorpus",
    "TelecomRatingCorpus",
    "get_all_enterprise_corpora",
    "get_corpus_by_domain",
]
