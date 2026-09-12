package service

import (
	"context"
	"fmt"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/google/uuid"
)

type FeeType string

const (
	FeeWireDomestic      FeeType = "WIRE_DOMESTIC"
	FeeWireInternational FeeType = "WIRE_INTERNATIONAL"
	FeeOverdraft         FeeType = "OVERDRAFT_PENALTY"
	FeeMonthlyService    FeeType = "MONTHLY_MAINTENANCE"
	FeeAtmOutOfNetwork   FeeType = "ATM_OUT_OF_NETWORK"
)

type CustomerTier string

const (
	TierRetail     CustomerTier = "RETAIL"
	TierPreferred  CustomerTier = "PREFERRED"
	TierPrivate    CustomerTier = "PRIVATE_BANKING"
	TierCommercial CustomerTier = "COMMERCIAL"
)

type FeeScheduleConfig struct {
	FeeIncomeAccountID     string
	DomesticWireFeeCents   int64
	IntlWireFeeCents       int64
	OverdraftFeeCents      int64
	OverdraftBufferCents   int64
	MonthlyServiceFeeCents int64
	MinBalanceWaiverCents  int64
}

type FeeCalculationResult struct {
	FeeType       FeeType
	GrossFeeCents int64
	WaivedCents   int64
	NetFeeCents   int64
	WaiverReason  string
	Currency      string
}

type FeeEngineService struct {
	config     FeeScheduleConfig
	postingEng *PostingEngine
}

func NewFeeEngineService(config FeeScheduleConfig, postingEng *PostingEngine) *FeeEngineService {
	return &FeeEngineService{
		config:     config,
		postingEng: postingEng,
	}
}

// CalculateWireFee evaluates fees and waivers based on transaction magnitude and customer tier.
func (s *FeeEngineService) CalculateWireFee(
	transferAmountCents int64,
	currency string,
	isInternational bool,
	tier CustomerTier,
) FeeCalculationResult {
	var gross int64
	feeType := FeeWireDomestic
	if isInternational {
		gross = s.config.IntlWireFeeCents
		feeType = FeeWireInternational
	} else {
		gross = s.config.DomesticWireFeeCents
	}

	var waived int64
	var reason string

	switch tier {
	case TierPrivate:
		waived = gross
		reason = "Private Banking client full fee waiver"
	case TierPreferred:
		waived = gross / 2
		reason = "Preferred Banking client 50% waiver"
	default:
		waived = 0
		reason = "Standard fee schedule applied"
	}

	return FeeCalculationResult{
		FeeType:       feeType,
		GrossFeeCents: gross,
		WaivedCents:   waived,
		NetFeeCents:   gross - waived,
		WaiverReason:  reason,
		Currency:      currency,
	}
}

// AssessOverdraftFee evaluates whether an overdraft penalty should be assessed.
func (s *FeeEngineService) AssessOverdraftFee(
	endingBalanceCents int64,
	currency string,
	dailyOverdraftCount int,
) FeeCalculationResult {
	// If balance is above negative courtesy buffer, waive fee
	if endingBalanceCents >= -s.config.OverdraftBufferCents {
		return FeeCalculationResult{
			FeeType:       FeeOverdraft,
			GrossFeeCents: s.config.OverdraftFeeCents,
			WaivedCents:   s.config.OverdraftFeeCents,
			NetFeeCents:   0,
			WaiverReason:  "Within courtesy buffer limit",
			Currency:      currency,
		}
	}

	// Maximum 3 overdraft fees per calendar day
	if dailyOverdraftCount >= 3 {
		return FeeCalculationResult{
			FeeType:       FeeOverdraft,
			GrossFeeCents: s.config.OverdraftFeeCents,
			WaivedCents:   s.config.OverdraftFeeCents,
			NetFeeCents:   0,
			WaiverReason:  "Daily overdraft cap reached (max 3 per day)",
			Currency:      currency,
		}
	}

	return FeeCalculationResult{
		FeeType:       FeeOverdraft,
		GrossFeeCents: s.config.OverdraftFeeCents,
		WaivedCents:   0,
		NetFeeCents:   s.config.OverdraftFeeCents,
		WaiverReason:  "Uncovered overdraft event",
		Currency:      currency,
	}
}

// ChargeFee posts the net fee from the customer's account to the bank's fee income account.
func (s *FeeEngineService) ChargeFee(
	ctx context.Context,
	tenantID, customerAccountID string,
	result FeeCalculationResult,
) (*model.JournalEntryAggregate, error) {
	if result.NetFeeCents <= 0 {
		return nil, nil
	}

	req := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: fmt.Sprintf("FEE-%s-%d", customerAccountID, time.Now().UnixNano()),
		Type:           model.TxTypeFeeDeduction,
		ReferenceID:    fmt.Sprintf("REF-FEE-%s", customerAccountID),
		SourceAccount:  customerAccountID,
		TargetAccount:  s.config.FeeIncomeAccountID,
		Amount:         result.NetFeeCents,
		Currency:       result.Currency,
		Description:    fmt.Sprintf("Service fee charge: %s", result.FeeType),
		ValueDate:      time.Now().UTC(),
	}

	return s.postingEng.ProcessTransfer(ctx, req)
}
