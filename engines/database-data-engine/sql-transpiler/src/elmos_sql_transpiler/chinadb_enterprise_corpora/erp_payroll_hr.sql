-- ============================================================================
-- Enterprise ERP & Payroll HR Progressive Tax Calculation Workload
-- Source Dialects: Oracle PL/SQL & SQL Server T-SQL
-- ============================================================================

-- Table: Departments
CREATE TABLE erp_departments (
    dept_id VARCHAR2(16) NOT NULL,
    dept_name VARCHAR2(64) NOT NULL,
    cost_center VARCHAR2(32) NOT NULL,
    manager_id VARCHAR2(32),
    budget_annual NUMBER(18, 4) NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_erp_dept PRIMARY KEY (dept_id)
);

-- Table: Employees
CREATE TABLE erp_employees (
    emp_id VARCHAR2(32) NOT NULL,
    dept_id VARCHAR2(16) NOT NULL,
    full_name VARCHAR2(64) NOT NULL,
    id_card VARCHAR2(18) NOT NULL,
    base_salary NUMBER(14, 4) NOT NULL,
    performance_ratio NUMBER(4, 2) DEFAULT 1.00 NOT NULL,
    social_base NUMBER(14, 4) NOT NULL,
    hire_date DATE NOT NULL,
    status VARCHAR2(16) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_erp_emp PRIMARY KEY (emp_id),
    CONSTRAINT fk_erp_emp_dept FOREIGN KEY (dept_id) REFERENCES erp_departments (dept_id),
    CONSTRAINT chk_erp_emp_status CHECK (status IN ('ACTIVE', 'PROBATION', 'RESIGNED', 'LEAVE'))
);

-- Table: Progressive Individual Income Tax Brackets
CREATE TABLE erp_tax_brackets (
    bracket_id NUMBER(2, 0) NOT NULL,
    min_income NUMBER(14, 4) NOT NULL,
    max_income NUMBER(14, 4) NOT NULL,
    tax_rate NUMBER(4, 2) NOT NULL,
    quick_deduction NUMBER(14, 4) NOT NULL,
    CONSTRAINT pk_erp_tax PRIMARY KEY (bracket_id)
);

-- Table: Monthly Payroll Ledger
CREATE TABLE erp_payroll_runs (
    payroll_id VARCHAR2(64) NOT NULL,
    emp_id VARCHAR2(32) NOT NULL,
    pay_period VARCHAR2(7) NOT NULL, -- e.g. '2026-06'
    gross_salary NUMBER(14, 4) NOT NULL,
    social_pension_ee NUMBER(12, 4) NOT NULL, -- 8% Employee
    social_medical_ee NUMBER(12, 4) NOT NULL, -- 2% Employee
    social_unemp_ee NUMBER(12, 4) NOT NULL,   -- 0.5% Employee
    housing_fund_ee NUMBER(12, 4) NOT NULL,   -- 12% Employee
    taxable_income NUMBER(14, 4) NOT NULL,
    income_tax NUMBER(12, 4) NOT NULL,
    net_payout NUMBER(14, 4) NOT NULL,
    processed_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_erp_payroll PRIMARY KEY (payroll_id),
    CONSTRAINT fk_erp_pay_emp FOREIGN KEY (emp_id) REFERENCES erp_employees (emp_id),
    CONSTRAINT uk_erp_pay_period UNIQUE (emp_id, pay_period)
);

-- View: Department Monthly Payroll Expense
CREATE OR REPLACE VIEW v_erp_dept_payroll AS
SELECT 
    d.dept_id,
    d.dept_name,
    p.pay_period,
    COUNT(p.emp_id) AS employee_count,
    SUM(p.gross_salary) AS total_gross_salary,
    SUM(p.income_tax) AS total_income_tax_withheld,
    SUM(p.net_payout) AS total_net_disbursement
FROM erp_payroll_runs p
JOIN erp_employees e ON p.emp_id = e.emp_id
JOIN erp_departments d ON e.dept_id = d.dept_id
GROUP BY d.dept_id, d.dept_name, p.pay_period;

-- Procedure: Calculate Monthly Payroll Batch with Progressive Tax Brackets
CREATE OR REPLACE PROCEDURE sp_erp_calculate_payroll (
    p_pay_period IN VARCHAR2,
    p_standard_deduction IN NUMBER,
    p_processed_count OUT NUMBER,
    p_total_disbursement OUT NUMBER
)
IS
    CURSOR cur_employees IS
        SELECT emp_id, base_salary, performance_ratio, social_base
        FROM erp_employees
        WHERE status = 'ACTIVE';

    v_emp_id VARCHAR2(32);
    v_base NUMBER(14, 4);
    v_perf NUMBER(4, 2);
    v_social NUMBER(14, 4);
    
    v_gross NUMBER(14, 4);
    v_pension NUMBER(12, 4);
    v_medical NUMBER(12, 4);
    v_unemp NUMBER(12, 4);
    v_housing NUMBER(12, 4);
    v_total_deduct NUMBER(14, 4);
    v_taxable NUMBER(14, 4);
    v_tax NUMBER(12, 4);
    v_net NUMBER(14, 4);
    v_pay_id VARCHAR2(64);
BEGIN
    p_processed_count := 0;
    p_total_disbursement := 0;

    OPEN cur_employees;
    LOOP
        FETCH cur_employees INTO v_emp_id, v_base, v_perf, v_social;
        EXIT WHEN cur_employees%NOTFOUND;

        -- 1. Calculate gross salary
        v_gross := ROUND(v_base * v_perf, 4);

        -- 2. Calculate statutory social benefits deductions
        v_pension := ROUND(v_social * 0.08, 4);
        v_medical := ROUND(v_social * 0.02, 4);
        v_unemp := ROUND(v_social * 0.005, 4);
        v_housing := ROUND(v_social * 0.12, 4);
        v_total_deduct := v_pension + v_medical + v_unemp + v_housing;

        -- 3. Calculate taxable income
        v_taxable := v_gross - v_total_deduct - p_standard_deduction;
        IF v_taxable < 0 THEN
            v_taxable := 0;
        END IF;

        -- 4. Calculate progressive tax
        IF v_taxable <= 3000 THEN
            v_tax := ROUND(v_taxable * 0.03, 4);
        ELSIF v_taxable <= 12000 THEN
            v_tax := ROUND(v_taxable * 0.10 - 210, 4);
        ELSIF v_taxable <= 25000 THEN
            v_tax := ROUND(v_taxable * 0.20 - 1410, 4);
        ELSIF v_taxable <= 35000 THEN
            v_tax := ROUND(v_taxable * 0.25 - 2660, 4);
        ELSIF v_taxable <= 55000 THEN
            v_tax := ROUND(v_taxable * 0.30 - 4410, 4);
        ELSIF v_taxable <= 80000 THEN
            v_tax := ROUND(v_taxable * 0.35 - 7160, 4);
        ELSE
            v_tax := ROUND(v_taxable * 0.45 - 15160, 4);
        END IF;

        IF v_tax < 0 THEN
            v_tax := 0;
        END IF;

        -- 5. Calculate net payout
        v_net := v_gross - v_total_deduct - v_tax;

        v_pay_id := 'PAY_' || p_pay_period || '_' || v_emp_id;

        -- Insert or replace into payroll run ledger
        INSERT INTO erp_payroll_runs (
            payroll_id, emp_id, pay_period, gross_salary, social_pension_ee,
            social_medical_ee, social_unemp_ee, housing_fund_ee, taxable_income,
            income_tax, net_payout
        ) VALUES (
            v_pay_id, v_emp_id, p_pay_period, v_gross, v_pension,
            v_medical, v_unemp, v_housing, v_taxable,
            v_tax, v_net
        );

        p_processed_count := p_processed_count + 1;
        p_total_disbursement := p_total_disbursement + v_net;
    END LOOP;
    CLOSE cur_employees;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF cur_employees%ISOPEN THEN
            CLOSE cur_employees;
        END IF;
        ROLLBACK;
        RAISE;
END sp_erp_calculate_payroll;
/
