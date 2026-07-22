---
name: technology-financial-cost-usage-and-labor-ingestion
description: "导入总账、采购、云、SaaS、数据中心、License、人工和消费数据，并统一期间、币种和成本语义。"
---

# Cost and Usage Ingestion

## Cost Source

GENERAL_LEDGER
ACCOUNTS_PAYABLE
PURCHASE_ORDER
CLOUD_BILLING
SAAS_BILLING
DATA_CENTER
LICENSE
NETWORK
TELECOM
LABOR
CONTRACTOR
DEPRECIATION
AMORTIZATION
SHARED_SERVICE
OTHER

## Cost Record

Source
Document
Period
Posting Date
Cost Center
Account
Vendor
Amount
Currency
Tax
Commitment
Owner
Reference

## Cost状态

ACTUAL
ACCRUAL
COMMITMENT
BUDGET
FORECAST
ADJUSTMENT
CREDIT
UNKNOWN

## Usage

CPU
MEMORY
STORAGE
NETWORK
SEAT
USER
TRANSACTION
REQUEST
TOKEN
BUILD
DEPLOYMENT
SUPPORT_CASE
OTHER

## Labor

优先使用：

Role
Team
Cost Rate
Allocation Percentage
Product
Activity
Period

不默认导入个人薪资。

## Currency

保存：

Original Currency
Reporting Currency
FX Date
FX Source
FX Rate
Conversion Policy

## Period

Fiscal Year
Fiscal Period
Calendar Period
Posting Period
Service Period

## Duplicate

通过：

Source ID
Invoice
Line
Amount
Date
Vendor
Reference

检测重复，不能仅按金额。

## 输出

technology-cost-source.json
technology-cost-records.json
technology-usage-records.json
labor-cost-records.json
currency-conversion.json
cost-ingestion-quality.json

## 验收标准

- Actual与Commitment分开；
- Usage和Cost可关联；
- Currency可重算；
- 财务期间明确；
- Labor数据最小化；
- Credit和Refund正确处理；
- Duplicate可检测。
