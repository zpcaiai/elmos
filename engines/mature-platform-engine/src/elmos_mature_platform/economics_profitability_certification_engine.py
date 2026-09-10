from typing import List, Dict, Optional
from elmos_mature_platform.types import RevenueRecord, EconCertification, EconCertLevel, ProfitabilityMetric
from datetime import datetime

class EconomicsProfitabilityCertificationEngine:
    def __init__(self):
        self._records: Dict[str, List[RevenueRecord]] = {}
        self._certifications: Dict[str, EconCertification] = {}

    def add_revenue_record(self, record: RevenueRecord) -> None:
        """Add a revenue record and compute gross profit."""
        record.gross_profit = record.revenue - record.cogs
        if record.product_id not in self._records:
            self._records[record.product_id] = []
        self._records[record.product_id].append(record)

    def get_records(self, product_id: str) -> List[RevenueRecord]:
        """Get records for a product."""
        return self._records.get(product_id, [])

    def compute_gross_margin(self, product_id: str) -> float:
        """Compute average gross margin across periods."""
        records = self.get_records(product_id)
        if not records:
            return 0.0
        margins = []
        for r in records:
            if r.revenue > 0:
                margins.append((r.gross_profit / r.revenue) * 100)
            else:
                margins.append(0.0)
        return sum(margins) / len(margins) if margins else 0.0

    def compute_ltv_cac_ratio(self, product_id: str) -> float:
        """Compute average LTV/CAC ratio."""
        records = self.get_records(product_id)
        if not records:
            return 0.0
        ratios = []
        for r in records:
            if r.cac > 0:
                ratios.append(r.ltv / r.cac)
            else:
                ratios.append(0.0)
        return sum(ratios) / len(ratios) if ratios else 0.0

    def compute_churn_rate(self, product_id: str) -> float:
        """Compute average churn rate."""
        records = self.get_records(product_id)
        if not records:
            return 0.0
        rates = []
        for r in records:
            if r.customers > 0:
                rates.append(r.churn_count / r.customers)
            else:
                rates.append(0.0)
        return sum(rates) / len(rates) if rates else 0.0

    def compute_unit_economics(self, product_id: str) -> Dict:
        """Compute per-customer unit economics."""
        records = self.get_records(product_id)
        if not records:
            return {"revenue_per_customer": 0.0, "cogs_per_customer": 0.0, "margin_per_customer": 0.0, "positive": False}
        
        total_revenue = sum(r.revenue for r in records)
        total_cogs = sum(r.cogs for r in records)
        total_customers = sum(r.customers for r in records)
        
        if total_customers == 0:
            return {"revenue_per_customer": 0.0, "cogs_per_customer": 0.0, "margin_per_customer": 0.0, "positive": False}
            
        rev_per = total_revenue / total_customers
        cogs_per = total_cogs / total_customers
        margin_per = rev_per - cogs_per
        
        return {
            "revenue_per_customer": rev_per,
            "cogs_per_customer": cogs_per,
            "margin_per_customer": margin_per,
            "positive": margin_per > 0
        }

    def certify_economics(self, product_id: str) -> EconCertification:
        """Evaluate and certify economics."""
        gross_margin = self.compute_gross_margin(product_id)
        ltv_cac = self.compute_ltv_cac_ratio(product_id)
        unit_econ = self.compute_unit_economics(product_id)
        
        if ltv_cac > 3.0:
            level = EconCertLevel.HIGHLY_PROFITABLE
        elif ltv_cac > 2.0:
            level = EconCertLevel.PROFITABLE
        elif ltv_cac > 1.0:
            level = EconCertLevel.VIABLE
        elif ltv_cac > 0.5:
            level = EconCertLevel.MARGINAL
        else:
            level = EconCertLevel.NOT_VIABLE
            
        certified = gross_margin > 0 and ltv_cac > 1.0
        
        cert = EconCertification(
            cert_id=f"cert_{product_id}",
            product_id=product_id,
            level=level,
            gross_margin_pct=gross_margin,
            ltv_cac_ratio=ltv_cac,
            unit_economics_positive=unit_econ["positive"],
            burn_rate_monthly=0.0,
            months_to_profitability=0,
            certified=certified,
            certified_at=datetime.now().isoformat() if certified else "",
            notes="Certified successfully" if certified else "Certification failed"
        )
        self._certifications[product_id] = cert
        return cert

    def get_certification(self, product_id: str) -> Optional[EconCertification]:
        """Get latest cert."""
        return self._certifications.get(product_id)

    def project_profitability(self, product_id: str, months: int) -> Dict:
        """Project future revenue/costs."""
        records = self.get_records(product_id)
        if not records or months <= 0:
            return {"projected_revenue": 0.0, "projected_cogs": 0.0, "projected_profit": 0.0}
            
        avg_revenue = sum(r.revenue for r in records) / len(records)
        avg_cogs = sum(r.cogs for r in records) / len(records)
        
        proj_rev = avg_revenue * months
        proj_cogs = avg_cogs * months
        proj_profit = proj_rev - proj_cogs
        
        return {
            "projected_revenue": proj_rev,
            "projected_cogs": proj_cogs,
            "projected_profit": proj_profit
        }

    def compare_products(self, product_ids: List[str]) -> Dict:
        """Compare economics across products."""
        comparison = {}
        for pid in product_ids:
            comparison[pid] = {
                "gross_margin": self.compute_gross_margin(pid),
                "ltv_cac_ratio": self.compute_ltv_cac_ratio(pid),
                "unit_economics": self.compute_unit_economics(pid),
                "churn_rate": self.compute_churn_rate(pid)
            }
        return comparison

    def get_economics_report(self) -> Dict:
        """Summary: all products, margins, LTV/CAC."""
        report = {
            "total_products": len(self._records),
            "products": {}
        }
        for pid in self._records:
            cert = self.get_certification(pid)
            report["products"][pid] = {
                "gross_margin": self.compute_gross_margin(pid),
                "ltv_cac_ratio": self.compute_ltv_cac_ratio(pid),
                "certification": cert
            }
        return report
