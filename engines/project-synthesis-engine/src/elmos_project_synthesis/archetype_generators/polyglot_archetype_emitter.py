"""Industrial Polyglot (Java, C#, Rust) Archetype Code Emitter.

Generates production-grade microservices for Banking Ledger, Supply Chain Logistics,
and SaaS Billing in Java (Spring Boot 3), C# (.NET 8), and Rust (Axum).
"""
from __future__ import annotations

from typing import Dict
from ..models import SynthesisRequest, pascal


def generate_java_archetype_files(request: SynthesisRequest, archetype_name: str = "banking") -> Dict[str, str]:
    """Emit Java Spring Boot 3 domain files for the archetype."""
    files: Dict[str, str] = {}
    pkg = request.namespace or "com.elmos.enterprise"
    pkg_path = pkg.replace(".", "/")
    arch = archetype_name.lower()

    if "bank" in arch or "ledger" in arch:
        files[f"src/main/java/{pkg_path}/banking/AccountEntity.java"] = f"""package {pkg}.banking;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "accounts")
public class AccountEntity {{
    @Id
    @Column(length = 64)
    private String id;

    @Column(nullable = false, length = 64)
    private String tenantId;

    @Column(nullable = false, unique = true, length = 64)
    private String accountNumber;

    @Column(nullable = false, length = 128)
    private String accountName;

    @Column(nullable = false, precision = 18, scale = 4)
    private BigDecimal postedBalance = BigDecimal.ZERO;

    @Column(nullable = false, length = 3)
    private String currency;

    @Version
    private Long version;

    public AccountEntity() {{}}

    public String getId() {{ return id; }}
    public void setId(String id) {{ this.id = id; }}
    public BigDecimal getPostedBalance() {{ return postedBalance; }}
    public void setPostedBalance(BigDecimal bal) {{ this.postedBalance = bal; }}
}}
"""
    return files


def generate_dotnet_archetype_files(request: SynthesisRequest, archetype_name: str = "banking") -> Dict[str, str]:
    """Emit C# .NET 8 domain files for the archetype."""
    files: Dict[str, str] = {}
    arch = archetype_name.lower()

    if "bank" in arch or "ledger" in arch:
        files["Domain/BankingEntities.cs"] = """using System;
using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Enterprise.Banking.Domain
{
    [Table("accounts")]
    public class Account
    {
        [Key]
        [MaxLength(64)]
        public string Id { get; set; } = string.Empty;

        [Required]
        [MaxLength(64)]
        public string TenantId { get; set; } = string.Empty;

        [Required]
        [MaxLength(64)]
        public string AccountNumber { get; set; } = string.Empty;

        [Column(TypeName = "decimal(18,4)")]
        public decimal PostedBalance { get; set; } = 0m;

        [MaxLength(3)]
        public string Currency { get; set; } = "USD";

        [ConcurrencyCheck]
        public long Version { get; set; } = 1;
    }
}
"""
    return files


def generate_rust_archetype_files(request: SynthesisRequest, archetype_name: str = "banking") -> Dict[str, str]:
    """Emit Rust Axum / Tokio domain files for the archetype."""
    files: Dict[str, str] = {}
    arch = archetype_name.lower()

    if "bank" in arch or "ledger" in arch:
        files["src/domain/banking.rs"] = """use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub id: String,
    pub tenant_id: String,
    pub account_number: String,
    pub posted_balance: Decimal,
    pub currency: String,
    pub version: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalLine {
    pub account_id: String,
    pub posting_key: String, // DEBIT / CREDIT
    pub amount: Decimal,
    pub currency: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalEntry {
    pub id: String,
    pub reference: String,
    pub lines: Vec<JournalLine>,
}
"""
    return files
