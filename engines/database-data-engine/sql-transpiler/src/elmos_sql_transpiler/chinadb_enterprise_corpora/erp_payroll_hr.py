"""Enterprise ERP & Payroll HR Corpus.

Provides employee structures, salary compensation tables, progressive income tax calculations,
and payroll batch processing procedures for cross-engine database verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DepartmentRecord:
    """Enterprise department unit."""

    dept_id: str
    dept_name: str
    cost_center: str
    budget_annual: float = 5000000.0


@dataclass
class EmployeeRecord:
    """Employee compensation profile."""

    emp_id: str
    dept_id: str
    full_name: str
    id_card: str
    base_salary: float
    performance_ratio: float = 1.0
    social_base: float = 10000.0
    hire_date: str = "2024-01-15"


class ErpPayrollCorpus:
    """Industrial ERP & Payroll HR Workload Suite."""

    domain_name = "Enterprise ERP & Payroll HR"
    primary_source_dialect = "oracle"

    @classmethod
    def get_raw_sql_path(cls) -> Path:
        """Return path to raw SQL corpus file."""
        return Path(__file__).with_name("erp_payroll_hr.sql")

    @classmethod
    def get_raw_sql(cls) -> str:
        """Load full raw SQL corpus text."""
        return cls.get_raw_sql_path().read_text(encoding="utf-8")

    @classmethod
    def get_seed_departments(cls) -> list[DepartmentRecord]:
        """Generate deterministic departments."""
        return [
            DepartmentRecord("D_ENG", "Engineering & R&D", "CC_ENG_101"),
            DepartmentRecord("D_FIN", "Finance & Accounting", "CC_FIN_201"),
            DepartmentRecord("D_HR", "Human Resources", "CC_HR_301"),
            DepartmentRecord("D_OPS", "Global Operations", "CC_OPS_401"),
        ]

    @classmethod
    def get_seed_employees(cls, count: int = 50) -> list[EmployeeRecord]:
        """Generate employee records with diverse salary tiers."""
        employees: list[EmployeeRecord] = []
        depts = ["D_ENG", "D_FIN", "D_HR", "D_OPS"]
        for i in range(1, count + 1):
            emp_id = f"EMP_{i:06d}"
            dept = depts[i % len(depts)]
            base = 8000.0 + (i * 750.0)
            perf = 1.0 + ((i % 5) * 0.05)
            employees.append(
                EmployeeRecord(
                    emp_id=emp_id,
                    dept_id=dept,
                    full_name=f"Staff Member {i:03d}",
                    id_card=f"11010119900101{i:04d}",
                    base_salary=base,
                    performance_ratio=perf,
                    social_base=min(base, 35000.0),
                )
            )
        return employees
