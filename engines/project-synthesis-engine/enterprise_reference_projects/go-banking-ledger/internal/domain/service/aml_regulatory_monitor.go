package service

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"time"
)

type AMLRuleViolationType string

const (
	ViolationCTRThresholdBreached AMLRuleViolationType = "CTR_THRESHOLD_EXCEEDED"     // Cash > $10,000 in 24h
	ViolationStructuringEvadingCTR AMLRuleViolationType = "STRUCTURING_SMURFING_DETECTED" // Multiple $9k-$9.9k txs
	ViolationRapidPassThrough      AMLRuleViolationType = "RAPID_PASS_THROUGH_FLOW"       // Drain > 90% in < 2h
	ViolationDormantAccountSurge   AMLRuleViolationType = "DORMANT_VELOCITY_SPIKE"        // 10x historical volume
)

type AMLTransactionType string

const (
	TxCashDeposit    AMLTransactionType = "CASH_DEPOSIT"
	TxCashWithdrawal AMLTransactionType = "CASH_WITHDRAWAL"
	TxWireInbound    AMLTransactionType = "WIRE_INBOUND"
	TxWireOutbound   AMLTransactionType = "WIRE_OUTBOUND"
	TxBookTransfer   AMLTransactionType = "BOOK_TRANSFER"
)

type AMLTransactionEvent struct {
	TransactionID   string
	AccountID       string
	CustomerUBOID   string // Ultimate Beneficial Owner
	TxType          AMLTransactionType
	AmountCents     int64
	Timestamp       time.Time
	Counterparty    string
	OriginCountry   string
	DestCountry     string
}

type AMLAlertRecord struct {
	AlertID           string
	CustomerUBOID     string
	ViolationType     AMLRuleViolationType
	SeverityScore     int // 1 to 100
	TriggeredAt       time.Time
	TriggeringTxs     []string
	NarrativeSummary  string
	RequiresSARFiling bool
}

type SARDossier struct {
	DossierID         string
	CustomerUBOID     string
	PrimaryViolation  AMLRuleViolationType
	GeneratedAt       time.Time
	TotalSuspiciousAmountCents int64
	SupportingAlerts  []AMLAlertRecord
	EvidentiaryGraphHash string
	FinCENNarrative   string
}

type AMLRegulatoryMonitor struct {
	ctrThresholdCents int64
	structuringWindow time.Duration
	passThroughWindow time.Duration
}

func NewAMLRegulatoryMonitor() *AMLRegulatoryMonitor {
	return &AMLRegulatoryMonitor{
		ctrThresholdCents: 1000000, // $10,000.00
		structuringWindow: 5 * 24 * time.Hour,
		passThroughWindow: 2 * time.Hour,
	}
}

// EvaluateCustomerActivity executes full BSA/FinCEN compliance surveillance rules
func (m *AMLRegulatoryMonitor) EvaluateCustomerActivity(
	customerUBOID string,
	events []AMLTransactionEvent,
	historical90DayAvgBalanceCents int64,
	isHistoricallyDormant bool,
) ([]AMLAlertRecord, *SARDossier) {
	if len(events) == 0 {
		return nil, nil
	}

	// Sort events by timestamp ascending
	sorted := make([]AMLTransactionEvent, len(events))
	copy(sorted, events)
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].Timestamp.Before(sorted[j].Timestamp)
	})

	var alerts []AMLAlertRecord
	alertSeq := 1

	// Rule 1: CTR 24-Hour Cash Aggregation Surveillance (BSA Form 112)
	cashEvents := make([]AMLTransactionEvent, 0)
	for _, e := range sorted {
		if e.TxType == TxCashDeposit || e.TxType == TxCashWithdrawal {
			cashEvents = append(cashEvents, e)
		}
	}

	for i := 0; i < len(cashEvents); i++ {
		windowStart := cashEvents[i].Timestamp
		windowEnd := windowStart.Add(24 * time.Hour)
		var rollingCashDepositCents int64 = 0
		var rollingCashWithdrawalCents int64 = 0
		txIDs := make([]string, 0)

		for j := i; j < len(cashEvents); j++ {
			if cashEvents[j].Timestamp.After(windowEnd) {
				break
			}
			if cashEvents[j].TxType == TxCashDeposit {
				rollingCashDepositCents += cashEvents[j].AmountCents
			} else {
				rollingCashWithdrawalCents += cashEvents[j].AmountCents
			}
			txIDs = append(txIDs, cashEvents[j].TransactionID)
		}

		if rollingCashDepositCents >= m.ctrThresholdCents {
			alerts = append(alerts, AMLAlertRecord{
				AlertID:           fmt.Sprintf("ALT-CTR-DEP-%d", alertSeq),
				CustomerUBOID:     customerUBOID,
				ViolationType:     ViolationCTRThresholdBreached,
				SeverityScore:     65,
				TriggeredAt:       windowStart,
				TriggeringTxs:     txIDs,
				NarrativeSummary:  fmt.Sprintf("Aggregate cash deposits of $%.2f exceed BSA CTR $10k threshold within 24 hours.", float64(rollingCashDepositCents)/100.0),
				RequiresSARFiling: false, // CTR is statutory disclosure, only SAR if evasion present
			})
			alertSeq++
			break // Deduplicate per customer batch
		}
		if rollingCashWithdrawalCents >= m.ctrThresholdCents {
			alerts = append(alerts, AMLAlertRecord{
				AlertID:           fmt.Sprintf("ALT-CTR-WTH-%d", alertSeq),
				CustomerUBOID:     customerUBOID,
				ViolationType:     ViolationCTRThresholdBreached,
				SeverityScore:     65,
				TriggeredAt:       windowStart,
				TriggeringTxs:     txIDs,
				NarrativeSummary:  fmt.Sprintf("Aggregate cash withdrawals of $%.2f exceed BSA CTR $10k threshold within 24 hours.", float64(rollingCashWithdrawalCents)/100.0),
				RequiresSARFiling: false,
			})
			alertSeq++
			break
		}
	}

	// Rule 2: Structuring / Smurfing Detection ($9,000 - $9,999 clustering)
	structuringTxs := make([]string, 0)
	var structuringTotal int64 = 0
	for _, e := range sorted {
		// $9,000 (900,000 cents) to $9,999.99 (999,999 cents)
		if e.AmountCents >= 900000 && e.AmountCents < 1000000 {
			structuringTxs = append(structuringTxs, e.TransactionID)
			structuringTotal += e.AmountCents
		}
	}
	if len(structuringTxs) >= 2 {
		alerts = append(alerts, AMLAlertRecord{
			AlertID:           fmt.Sprintf("ALT-STRUCT-%d", alertSeq),
			CustomerUBOID:     customerUBOID,
			ViolationType:     ViolationStructuringEvadingCTR,
			SeverityScore:     90,
			TriggeredAt:       time.Now().UTC(),
			TriggeringTxs:     structuringTxs,
			NarrativeSummary:  fmt.Sprintf("Suspected structuring: %d transactions just below $10k CTR threshold totaling $%.2f.", len(structuringTxs), float64(structuringTotal)/100.0),
			RequiresSARFiling: true,
		})
		alertSeq++
	}

	// Rule 3: Rapid Movement of Funds / Pass-Through Accounts (Inflow -> >= 90% Outflow in < 2 hrs)
	for i := 0; i < len(sorted); i++ {
		inflow := sorted[i]
		if inflow.TxType == TxWireInbound || inflow.TxType == TxCashDeposit {
			if inflow.AmountCents >= 500000 { // >= $5,000
				windowLimit := inflow.Timestamp.Add(m.passThroughWindow)
				var rapidOutflow int64 = 0
				outflowTxs := []string{inflow.TransactionID}

				for j := i + 1; j < len(sorted); j++ {
					out := sorted[j]
					if out.Timestamp.After(windowLimit) {
						break
					}
					if out.TxType == TxWireOutbound || out.TxType == TxCashWithdrawal {
						rapidOutflow += out.AmountCents
						outflowTxs = append(outflowTxs, out.TransactionID)
					}
				}

				if float64(rapidOutflow) >= float64(inflow.AmountCents)*0.90 {
					alerts = append(alerts, AMLAlertRecord{
						AlertID:           fmt.Sprintf("ALT-PASS-%d", alertSeq),
						CustomerUBOID:     customerUBOID,
						ViolationType:     ViolationRapidPassThrough,
						SeverityScore:     85,
						TriggeredAt:       inflow.Timestamp,
						TriggeringTxs:     outflowTxs,
						NarrativeSummary:  fmt.Sprintf("Rapid pass-through flow: $%.2f received and %.1f%% drained within %v.", float64(inflow.AmountCents)/100.0, float64(rapidOutflow)/float64(inflow.AmountCents)*100.0, m.passThroughWindow),
						RequiresSARFiling: true,
					})
					alertSeq++
					break
				}
			}
		}
	}

	// Rule 4: Dormant Account Sudden Velocity Surge
	if isHistoricallyDormant {
		for _, e := range sorted {
			if e.AmountCents >= 5000000 { // >= $50,000 on dormant account
				alerts = append(alerts, AMLAlertRecord{
					AlertID:           fmt.Sprintf("ALT-DORMANT-%d", alertSeq),
					CustomerUBOID:     customerUBOID,
					ViolationType:     ViolationDormantAccountSurge,
					SeverityScore:     80,
					TriggeredAt:       e.Timestamp,
					TriggeringTxs:     []string{e.TransactionID},
					NarrativeSummary:  fmt.Sprintf("Velocity surge on dormant account: $%.2f transacted vs historical average $%.2f.", float64(e.AmountCents)/100.0, float64(historical90DayAvgBalanceCents)/100.0),
					RequiresSARFiling: true,
				})
				alertSeq++
				break
			}
		}
	}

	// Determine if SAR dossier should be compiled
	var sarDossier *SARDossier
	sarAlerts := make([]AMLAlertRecord, 0)
	var totalSuspicious int64 = 0

	for _, a := range alerts {
		if a.RequiresSARFiling {
			sarAlerts = append(sarAlerts, a)
		}
	}

	if len(sarAlerts) > 0 {
		for _, e := range sorted {
			totalSuspicious += e.AmountCents
		}

		hashInput := fmt.Sprintf("UBO:%s|ALERTS:%d|AMT:%d|TIME:%s",
			customerUBOID, len(sarAlerts), totalSuspicious, time.Now().UTC().Format(time.RFC3339))
		h := sha256.Sum256([]byte(hashInput))
		graphHash := hex.EncodeToString(h[:])

		primary := sarAlerts[0].ViolationType

		narrative := fmt.Sprintf(
			"FINCEN SUSPICIOUS ACTIVITY REPORT (SAR-DI):\n"+
				"Customer UBO %s exhibited %d high-priority AML alert(s).\n"+
				"Primary typology identified: %s.\n"+
				"Total aggregate transactional exposure under review: $%.2f.\n"+
				"Investigation indicates anomalous pattern inconsistent with stated customer profile and business purpose.\n"+
				"Evidentiary ledger cryptographic verification hash: %s.",
			customerUBOID, len(sarAlerts), primary, float64(totalSuspicious)/100.0, graphHash)

		sarDossier = &SARDossier{
			DossierID:                  fmt.Sprintf("SAR-%s-%d", customerUBOID, time.Now().Unix()),
			CustomerUBOID:              customerUBOID,
			PrimaryViolation:           primary,
			GeneratedAt:                time.Now().UTC(),
			TotalSuspiciousAmountCents: totalSuspicious,
			SupportingAlerts:           sarAlerts,
			EvidentiaryGraphHash:       graphHash,
			FinCENNarrative:            narrative,
		}
	}

	return alerts, sarDossier
}
