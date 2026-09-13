package test

import (
	"strings"
	"testing"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
)

func TestAMLCTRThresholdExceeded(t *testing.T) {
	monitor := service.NewAMLRegulatoryMonitor()
	now := time.Date(2026, 9, 10, 8, 0, 0, 0, time.UTC)

	// Single customer making cash deposits aggregating to > $10,000 within 24 hours
	events := []service.AMLTransactionEvent{
		{
			TransactionID: "TX-DEP-001",
			AccountID:     "ACC-1001",
			CustomerUBOID: "UBO-CORP-99",
			TxType:        service.TxCashDeposit,
			AmountCents:   600000, // $6,000
			Timestamp:     now,
		},
		{
			TransactionID: "TX-DEP-002",
			AccountID:     "ACC-1001",
			CustomerUBOID: "UBO-CORP-99",
			TxType:        service.TxCashDeposit,
			AmountCents:   500000, // $5,000 -> Total $11,000 in 2 hours
			Timestamp:     now.Add(2 * time.Hour),
		},
	}

	alerts, sar := monitor.EvaluateCustomerActivity("UBO-CORP-99", events, 500000, false)
	if len(alerts) == 0 {
		t.Fatalf("Expected CTR threshold alert for $11,000 cash deposit aggregation")
	}

	var foundCTR bool
	for _, a := range alerts {
		if a.ViolationType == service.ViolationCTRThresholdBreached {
			foundCTR = true
			if a.SeverityScore != 65 {
				t.Errorf("Expected severity score 65, got %d", a.SeverityScore)
			}
			if len(a.TriggeringTxs) != 2 {
				t.Errorf("Expected 2 triggering txs, got %d", len(a.TriggeringTxs))
			}
		}
	}
	if !foundCTR {
		t.Fatalf("ViolationCTRThresholdBreached alert not found")
	}

	// CTR threshold alone does not automatically require SAR filing without suspicious structuring
	if sar != nil {
		t.Errorf("Expected nil SAR for routine CTR disclosure without illicit intent markers")
	}
}

func TestAMLStructuringSmurfingDetection(t *testing.T) {
	monitor := service.NewAMLRegulatoryMonitor()
	now := time.Date(2026, 9, 10, 9, 0, 0, 0, time.UTC)

	// Multiple cash transactions specifically between $9,000 and $9,999 to evade CTR
	events := []service.AMLTransactionEvent{
		{
			TransactionID: "TX-SMURF-1",
			AccountID:     "ACC-2002",
			CustomerUBOID: "UBO-SMURF-42",
			TxType:        service.TxCashDeposit,
			AmountCents:   950000, // $9,500
			Timestamp:     now,
		},
		{
			TransactionID: "TX-SMURF-2",
			AccountID:     "ACC-2002",
			CustomerUBOID: "UBO-SMURF-42",
			TxType:        service.TxCashDeposit,
			AmountCents:   980000, // $9,800
			Timestamp:     now.Add(24 * time.Hour),
		},
	}

	alerts, sar := monitor.EvaluateCustomerActivity("UBO-SMURF-42", events, 100000, false)
	if len(alerts) == 0 {
		t.Fatalf("Expected structuring alerts for smurfing transactions")
	}

	var foundStruct bool
	for _, a := range alerts {
		if a.ViolationType == service.ViolationStructuringEvadingCTR {
			foundStruct = true
			if !a.RequiresSARFiling {
				t.Errorf("Structuring must mandate SAR filing")
			}
			if a.SeverityScore != 90 {
				t.Errorf("Expected severity score 90, got %d", a.SeverityScore)
			}
		}
	}
	if !foundStruct {
		t.Fatalf("ViolationStructuringEvadingCTR alert not found")
	}

	if sar == nil {
		t.Fatalf("Expected generated SAR Dossier for detected structuring behavior")
	}
	if sar.CustomerUBOID != "UBO-SMURF-42" {
		t.Errorf("SAR customer mismatch: got %s", sar.CustomerUBOID)
	}
	if sar.TotalSuspiciousAmountCents != 1930000 { // $19,300.00
		t.Errorf("Expected total suspicious amount 1930000 cents, got %d", sar.TotalSuspiciousAmountCents)
	}
	if sar.EvidentiaryGraphHash == "" {
		t.Errorf("SAR dossier must have non-empty SHA256 cryptographic evidentiary graph hash")
	}
	if !strings.Contains(sar.FinCENNarrative, "FINCEN SUSPICIOUS ACTIVITY REPORT") {
		t.Errorf("FinCEN narrative missing SAR header: %s", sar.FinCENNarrative)
	}
}

func TestAMLRapidPassThroughAccounts(t *testing.T) {
	monitor := service.NewAMLRegulatoryMonitor()
	now := time.Date(2026, 9, 10, 10, 0, 0, 0, time.UTC)

	// Inflow of $50,000 followed by rapid drain of $48,000 (96%) within 30 minutes
	events := []service.AMLTransactionEvent{
		{
			TransactionID: "TX-WIRE-IN",
			AccountID:     "ACC-MULE-01",
			CustomerUBOID: "UBO-MULE-88",
			TxType:        service.TxWireInbound,
			AmountCents:   5000000, // $50,000
			Timestamp:     now,
		},
		{
			TransactionID: "TX-WIRE-OUT-1",
			AccountID:     "ACC-MULE-01",
			CustomerUBOID: "UBO-MULE-88",
			TxType:        service.TxWireOutbound,
			AmountCents:   2800000, // $28,000
			Timestamp:     now.Add(15 * time.Minute),
		},
		{
			TransactionID: "TX-WIRE-OUT-2",
			AccountID:     "ACC-MULE-01",
			CustomerUBOID: "UBO-MULE-88",
			TxType:        service.TxWireOutbound,
			AmountCents:   2000000, // $20,000 -> Total out $48,000 (96%)
			Timestamp:     now.Add(30 * time.Minute),
		},
	}

	alerts, sar := monitor.EvaluateCustomerActivity("UBO-MULE-88", events, 20000, false)
	if len(alerts) == 0 {
		t.Fatalf("Expected rapid pass-through alert")
	}

	var foundPassThrough bool
	for _, a := range alerts {
		if a.ViolationType == service.ViolationRapidPassThrough {
			foundPassThrough = true
			if !a.RequiresSARFiling {
				t.Errorf("Rapid pass-through must mandate SAR filing")
			}
		}
	}
	if !foundPassThrough {
		t.Fatalf("ViolationRapidPassThrough alert not found")
	}

	if sar == nil {
		t.Fatalf("Expected SAR Dossier for pass-through mule account")
	}
	if !strings.Contains(sar.FinCENNarrative, "RAPID_PASS_THROUGH_FLOW") {
		t.Errorf("FinCEN narrative missing pass-through typology: %s", sar.FinCENNarrative)
	}
}

func TestAMLDormantAccountVelocitySpike(t *testing.T) {
	monitor := service.NewAMLRegulatoryMonitor()
	now := time.Date(2026, 9, 10, 14, 0, 0, 0, time.UTC)

	// Historically dormant account suddenly receives $75,000
	events := []service.AMLTransactionEvent{
		{
			TransactionID: "TX-DORMANT-W1",
			AccountID:     "ACC-DORM-77",
			CustomerUBOID: "UBO-DORM-12",
			TxType:        service.TxWireInbound,
			AmountCents:   7500000, // $75,000
			Timestamp:     now,
		},
	}

	alerts, sar := monitor.EvaluateCustomerActivity("UBO-DORM-12", events, 5000, true)
	if len(alerts) == 0 {
		t.Fatalf("Expected dormant account velocity spike alert")
	}

	var foundDormant bool
	for _, a := range alerts {
		if a.ViolationType == service.ViolationDormantAccountSurge {
			foundDormant = true
			if a.SeverityScore != 80 {
				t.Errorf("Expected severity score 80, got %d", a.SeverityScore)
			}
		}
	}
	if !foundDormant {
		t.Fatalf("ViolationDormantAccountSurge alert not found")
	}

	if sar == nil {
		t.Fatalf("Expected SAR dossier for dormant account velocity surge")
	}
}
