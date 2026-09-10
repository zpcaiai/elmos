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
	FeeWireDomestic    FeeType = "WIRE_DOMESTIC"
	FeeWireInternational FeeType = "WIRE_INTERNATIONAL"
	FeeOverdraft       FeeType = "OVERDRAFT_PENALTY"
	FeeMonthlyService  FeeType = "MONTHLY_MAINTENANCE"
	FeeAtmOutOfNetwork FeeType = "ATM_OUT_OF_NETWORK"
)

type CustomerTier string

const (
	TierRetail     CustomerTier = "RETAIL"
	TierPreferred  CustomerTier = "PREFERRED"
	TierPrivate    CustomerTier = "PRIVATE_BANKING"
	TierCommercial CustomerTier = "COMMERCIAL"
)

type FeeScheduleConfig struct {
	FeeIncomeAccountID    string
	DomesticWireFeeCents  int64
	IntlWireFeeCents      int64
	OverdraftFeeCents     int64
	OverdraftBufferCents  int64 // Courtesy cushion (e.g. $10.00 negative before fee applies)
	MonthlyServiceFeeCents int64
	MinBalanceWaiverCents int64
}

type FeeCalculationResult struct {
	FeeType       FeeType
	GrossFeeCents int64
	WaivedCents   int64
	NetFeeCents   int64
	WaiverReason  string
	Currency      model.Currency
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
	transferAmount model.Money,
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
		Currency:      transferAmount.Currency(),
	}
}

// AssessOverdraftFee evaluates whether an overdraft penalty should be assessed.
func (s *FeeEngineService) AssessOverdraftFee(
	endingBalance model.Money,
	dailyOverdraftCount int,
) FeeCalculationResult {
	balanceCents := endingBalance.AmountMinor()

	// If balance is above negative courtesy buffer, waive fee
	if balanceCents >= -s.config.OverdraftBufferCents {
		return FeeCalculationResult{
			FeeType:       FeeOverdraft,
			GrossFeeCents: s.config.OverdraftFeeCents,
			WaivedCents:   s.config.OverdraftFeeCents,
			NetFeeCents:   0,
			WaiverReason:  "Within courtesy buffer limit",
			Currency:      endingBalance.Currency(),
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
			Currency:      endingBalance.Currency(),
		}
	}

	return FeeCalculationResult{
		FeeType:       FeeOverdraft,
		GrossFeeCents: s.config.OverdraftFeeCents,
		WaivedCents:   0,
		NetFeeCents:   s.config.OverdraftFeeCents,
		WaiverReason:  "Uncovered overdraft event",
		Currency:      endingBalance.Currency(),
	}
}

// ChargeFee posts the net fee from the customer's account to the bank's fee income account.
func (s *FeeEngineService) ChargeFee(
	ctx context.Context,
	customerAccountID string,
	result FeeCalculationResult,
) (*model.JournalEntry, error) {
	if result.NetFeeCents <= 0 {
		return nil, nil // No net fee to debit
	}

	feeMoney, err := model.NewMoney(result.NetFeeCents, result.Currency)
	if err != nil {
		return nil, err
	}

	journalID := uuid.New().String()
	now := time.Now().UTC()
	desc := fmt.Sprintf("Service fee charge: %s", result.FeeType)

	lines := []model.PostingLine{
		{
			ID:          uuid.New().String(),
			AccountID:   customerAccountID,
			Direction:   model.DirectionDebit,
			Amount:      feeMoney,
			Description: desc,
		},
		{
			ID:          uuid.New().String(),
			AccountID:   s.config.FeeIncomeAccountID,
			Direction:   model.DirectionCredit,
			Amount:      feeMoney,
			Description: desc,
		},
	}

	entry, err := model.NewJournalEntry(
		journalID,
		now,
		now,
		desc,
		"FEE_ASSESSMENT",
		lines,
	)
	if err != nil {
		return nil, err
	}

	return s.postingEng.Post(ctx, entry)
}
