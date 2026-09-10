"""Enterprise ERP & Payroll HR Corpus.

Provides corporate legal entities, employee structures, progressive income tax calculations,
social security fund deductions, attendance tracking, and payroll batch processing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any


@dataclass
class LegalEntityRecord:
    """Corporate legal entity and jurisdiction."""

    entity_code: str
    entity_name: str
    country_code: str = "CHN"
    tax_registration_no: str = "91110000123456789X"
    currency_code: str = "CNY"


@dataclass
class DepartmentRecord:
    """Enterprise department organizational unit."""

    dept_code: str
    dept_name: str
    entity_code: str
    cost_center: str
    parent_dept_code: str | None = None


@dataclass
class EmployeeRecord:
    """Employee master contract and base compensation profile."""

    employee_id: str
    entity_code: str
    dept_code: str
    full_name: str
    id_number: str
    hire_date: str
    base_salary: float
    performance_target: float = 0.0
    employment_status: str = "ACTIVE"


@dataclass
class TaxBracketRecord:
    """Progressive individual income tax tier bracket."""

    bracket_id: str
    country_code: str
    tier_min: float
    tier_max: float
    tax_rate: float
    quick_deduction: float


@dataclass
class SocialSecurityRateRecord:
    """Statutory social insurance contribution rate."""

    fund_code: str  # PENSION, MEDICAL, UNEMPLOYMENT, HOUSING
    fund_name: str
    city_code: str
    employee_rate: float
    employer_rate: float
    max_base: float
    min_base: float


@dataclass
class MonthlyPayrollRecord:
    """Calculated net salary slip for pay cycle."""

    payroll_id: str
    employee_id: str
    period_month: str  # YYYYMM
    gross_salary: float
    social_security_deduction: float
    housing_fund_deduction: float
    income_tax: float
    net_salary: float
    payout_status: str = "CALCULATED"


@dataclass
class AttendanceRecord:
    """Monthly employee attendance and time tracking."""

    record_id: str
    employee_id: str
    period_month: str
    working_days: float
    leave_days: float = 0.0
    overtime_hours: float = 0.0


@dataclass
class CdcEvent:
    """Change Data Capture (CDC) streaming event."""

    event_id: str
    table_name: str
    operation: str  # INSERT, UPDATE, DELETE
    timestamp_ms: int
    before_state: dict[str, Any] = field(default_factory=dict)
    after_state: dict[str, Any] = field(default_factory=dict)


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
    def parse_statements(cls) -> list[str]:
        """Split corpus into individual executable SQL statements."""
        raw = cls.get_raw_sql()
        stmts: list[str] = []
        cur: list[str] = []
        in_plsql = False

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue

            if any(
                stripped.upper().startswith(kw)
                for kw in ("CREATE OR REPLACE PROCEDURE", "CREATE OR REPLACE TRIGGER", "BEGIN")
            ):
                in_plsql = True

            cur.append(line)

            if in_plsql:
                if stripped == "/":
                    stmts.append("\n".join(cur[:-1]).strip())
                    cur = []
                    in_plsql = False
            else:
                if stripped.endswith(";"):
                    joined = "\n".join(cur).strip()
                    if joined.endswith(";"):
                        joined = joined[:-1].strip()
                    stmts.append(joined)
                    cur = []

        if cur:
            tail = "\n".join(cur).strip()
            if tail:
                stmts.append(tail)

        return [s for s in stmts if s]

    @classmethod
    def get_seed_entities(cls) -> list[LegalEntityRecord]:
        """Generate master legal entities."""
        return [
            LegalEntityRecord(
                "ENT_BJ_01", "Enterprise Tech China Ltd.", "CHN", "91110000123456789X", "CNY"
            ),
            LegalEntityRecord(
                "ENT_HK_01", "Enterprise Global Holdings Ltd.", "HKG", "HK9988776655", "HKD"
            ),
        ]

    @classmethod
    def get_seed_departments(cls) -> list[DepartmentRecord]:
        """Generate organizational business units."""
        return [
            DepartmentRecord("DEPT_ENG", "Software Engineering", "ENT_BJ_01", "CC_ENG_101"),
            DepartmentRecord("DEPT_FIN", "Finance and Treasury", "ENT_BJ_01", "CC_FIN_201"),
            DepartmentRecord("DEPT_HR", "Human Resources", "ENT_BJ_01", "CC_HR_301"),
            DepartmentRecord("DEPT_OPS", "Infrastructure & Operations", "ENT_BJ_01", "CC_OPS_401"),
        ]

    @classmethod
    def get_seed_tax_brackets(cls) -> list[TaxBracketRecord]:
        """Generate standard progressive income tax brackets."""
        return [
            TaxBracketRecord("TAX_T1", "CHN", 0.0, 3000.0, 0.03, 0.0),
            TaxBracketRecord("TAX_T2", "CHN", 3000.0, 12000.0, 0.10, 210.0),
            TaxBracketRecord("TAX_T3", "CHN", 12000.0, 25000.0, 0.20, 1410.0),
            TaxBracketRecord("TAX_T4", "CHN", 25000.0, 35000.0, 0.25, 2660.0),
            TaxBracketRecord("TAX_T5", "CHN", 35000.0, 55000.0, 0.30, 4410.0),
            TaxBracketRecord("TAX_T6", "CHN", 55000.0, 80000.0, 0.35, 7160.0),
            TaxBracketRecord("TAX_T7", "CHN", 80000.0, 9999999.0, 0.45, 15160.0),
        ]

    @classmethod
    def get_seed_employees(cls, count: int = 50) -> list[EmployeeRecord]:
        """Generate deterministic employee payroll records."""
        emps: list[EmployeeRecord] = []
        depts = ["DEPT_ENG", "DEPT_FIN", "DEPT_HR", "DEPT_OPS"]
        for i in range(1, count + 1):
            sal = 12000.0 + (i * 250.0)
            emps.append(
                EmployeeRecord(
                    employee_id=f"EMP_{i:04d}",
                    entity_code="ENT_BJ_01",
                    dept_code=depts[i % len(depts)],
                    full_name=f"Enterprise Staff {i}",
                    id_number=f"ID_EMP_{i:08d}",
                    hire_date="2022-03-01",
                    base_salary=sal,
                    performance_target=sal * 0.2,
                )
            )
        return emps

    @classmethod
    def generate_attendance_workload(
        cls, employees: list[EmployeeRecord], period_month: str = "202603"
    ) -> list[AttendanceRecord]:
        """Generate monthly employee attendance and overtime timesheets."""
        records: list[AttendanceRecord] = []
        for e in employees:
            records.append(
                AttendanceRecord(
                    record_id=f"ATT_{e.employee_id}_{period_month}",
                    employee_id=e.employee_id,
                    period_month=period_month,
                    working_days=21.75,
                    leave_days=1.0 if int(e.employee_id[-4:]) % 5 == 0 else 0.0,
                    overtime_hours=8.0 if int(e.employee_id[-4:]) % 3 == 0 else 0.0,
                )
            )
        return records

    @classmethod
    def calculate_employee_payroll_in_memory(
        cls,
        employee: EmployeeRecord,
        attendance: AttendanceRecord | None,
        period_month: str = "202603",
        standard_deduction: float = 5000.0,
        social_security_rate: float = 0.105,
        housing_fund_rate: float = 0.07,
    ) -> MonthlyPayrollRecord:
        """Calculate complete net salary breakdown under progressive tax laws."""
        gross = Decimal(str(employee.base_salary))

        # Adjust for attendance overtime or unpaid leave
        if attendance and attendance.overtime_hours > 0:
            hourly_rate = gross / Decimal("174.0")
            overtime_pay = hourly_rate * Decimal(str(attendance.overtime_hours)) * Decimal("1.5")
            gross += overtime_pay

        gross_val = float(gross.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

        # Social & Housing deductions
        ss_dec = (gross * Decimal(str(social_security_rate))).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        hf_dec = (gross * Decimal(str(housing_fund_rate))).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        ss_val = float(ss_dec)
        hf_val = float(hf_dec)

        # Taxable income
        std_dec = Decimal(str(standard_deduction))
        taxable_dec = max(Decimal("0.0"), gross - ss_dec - hf_dec - std_dec)
        taxable_val = float(taxable_dec)

        # Progressive tax calculation
        brackets = cls.get_seed_tax_brackets()
        matched_bracket = brackets[0]
        for b in brackets:
            if b.tier_min <= taxable_val <= b.tier_max:
                matched_bracket = b
                break

        tax_rate_dec = Decimal(str(matched_bracket.tax_rate))
        quick_ded_dec = Decimal(str(matched_bracket.quick_deduction))
        tax_dec = max(Decimal("0.0"), (taxable_dec * tax_rate_dec) - quick_ded_dec).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        tax_val = float(tax_dec)

        # Net salary
        net_dec = gross - ss_dec - hf_dec - tax_dec
        net_val = float(net_dec.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

        return MonthlyPayrollRecord(
            payroll_id=f"PAY_{employee.employee_id}_{period_month}",
            employee_id=employee.employee_id,
            period_month=period_month,
            gross_salary=gross_val,
            social_security_deduction=ss_val,
            housing_fund_deduction=hf_val,
            income_tax=tax_val,
            net_salary=net_val,
            payout_status="CALCULATED",
        )

    @classmethod
    def verify_payroll_mass_balance(
        cls, payroll: MonthlyPayrollRecord
    ) -> tuple[bool, float, str]:
        """Verify fundamental conservation: Gross == Net + SS + Housing + Tax."""
        deductions = (
            payroll.net_salary
            + payroll.social_security_deduction
            + payroll.housing_fund_deduction
            + payroll.income_tax
        )
        diff = abs(payroll.gross_salary - deductions)
        is_balanced = diff < 0.01
        msg = (
            f"Gross: {payroll.gross_salary:.4f}, Net+Deductions: {deductions:.4f}, "
            f"Diff: {diff:.4f}"
        )
        return is_balanced, diff, msg

    @classmethod
    def simulate_cdc_stream(
        cls, payrolls: list[MonthlyPayrollRecord]
    ) -> list[CdcEvent]:
        """Generate CDC change event stream for real-time replication verification."""
        events: list[CdcEvent] = []
        base_ts = int(time.time() * 1000)

        for idx, p in enumerate(payrolls):
            events.append(
                CdcEvent(
                    event_id=f"EVT_ERP_{idx + 1:08d}",
                    table_name="erp_monthly_payroll",
                    operation="INSERT",
                    timestamp_ms=base_ts + idx * 5,
                    before_state={},
                    after_state={
                        "payroll_id": p.payroll_id,
                        "employee_id": p.employee_id,
                        "period_month": p.period_month,
                        "gross_salary": p.gross_salary,
                        "net_salary": p.net_salary,
                        "income_tax": p.income_tax,
                        "payout_status": p.payout_status,
                    },
                )
            )
        return events

    @classmethod
    def simulate_concurrent_payroll_stress(
        cls,
        concurrency: int = 16,
        batches_per_worker: int = 50,
    ) -> dict[str, Any]:
        """Simulate high-throughput enterprise payroll calculation run."""
        employees = cls.get_seed_employees(count=100)
        attendance_list = cls.generate_attendance_workload(employees)
        att_map = {a.employee_id: a for a in attendance_list}

        latencies_ms: list[float] = []
        calculated_count = 0
        total_gross = 0.0
        total_net = 0.0
        total_tax = 0.0
        balance_failures = 0

        start_time = time.time()
        for worker_id in range(concurrency):
            for b_idx in range(batches_per_worker):
                t0 = time.time()
                emp_i = (worker_id * 3 + b_idx) % len(employees)
                emp = employees[emp_i]
                att = att_map.get(emp.employee_id)

                pay = cls.calculate_employee_payroll_in_memory(emp, att)
                t1 = time.time()
                latencies_ms.append((t1 - t0) * 1000.0)

                calculated_count += 1
                total_gross += pay.gross_salary
                total_net += pay.net_salary
                total_tax += pay.income_tax

                balanced, _, _ = cls.verify_payroll_mass_balance(pay)
                if not balanced:
                    balance_failures += 1

        total_duration = max(0.001, time.time() - start_time)
        latencies_ms.sort()
        p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
        p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
        p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

        return {
            "total_payrolls_calculated": len(latencies_ms),
            "calculated_count": calculated_count,
            "total_gross_disbursed": total_gross,
            "total_net_disbursed": total_net,
            "total_tax_withheld": total_tax,
            "balance_failures": balance_failures,
            "total_duration_sec": total_duration,
            "throughput_tps": len(latencies_ms) / total_duration,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "p99_latency_ms": p99,
        }
