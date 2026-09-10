package service

import (
	"context"
	"fmt"
	"math"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
)

// DayCountConvention specifies how days between dates and year length are calculated.
type DayCountConvention string

const (
	DayCountActualActual DayCountConvention = "ACTUAL_ACTUAL"
	DayCountActual360    DayCountConvention = "ACTUAL_360"
	DayCountActual365    DayCountConvention = "ACTUAL_365"
	DayCount30360US      DayCountConvention = "30_360_US"
	DayCount30360Europe  DayCountConvention = "30_360_EUROPEAN"
)

// CompoundingFrequency defines how often accrued interest is compounded.
type CompoundingFrequency string

const (
	CompoundingDaily     CompoundingFrequency = "DAILY"
	CompoundingMonthly   CompoundingFrequency = "MONTHLY"
	CompoundingQuarterly CompoundingFrequency = "QUARTERLY"
	CompoundingAnnual    CompoundingFrequency = "ANNUAL"
	CompoundingSimple    CompoundingFrequency = "SIMPLE" // No compounding
)

// InterestTier represents a balance tranche with its corresponding interest rate.
type InterestTier struct {
	MinBalanceCents int64   // Lower threshold in cents (inclusive)
	MaxBalanceCents int64   // Upper threshold in cents (0 = unlimited)
	AnnualRatePct   float64 // E.g., 4.25 for 4.25%
}

// InterestProductConfig contains product-level interest parameters.
type InterestProductConfig struct {
	ProductID            string
	DayCount             DayCountConvention
	Frequency            CompoundingFrequency
	Tiers                []InterestTier
	OverdraftRatePct     float64
	InterestExpenseAcct  string // General Ledger Account for Interest Expense
	InterestPayableAcct  string // General Ledger Account for Accrued Payable
}

// AccrualResult holds calculated interest for an accrual cycle.
type AccrualResult struct {
	AccountID            string
	Currency             model.Currency
	OpeningBalanceCents  int64
	AccruedInterestCents int64
	PeriodStartDate      time.Time
	PeriodEndDate        time.Time
	DayFraction          float64
	IsOverdraftCharge    bool
}

// DayCountCalculator implements standard financial day-count arithmetic.
type DayCountCalculator struct{}

func NewDayCountCalculator() *DayCountCalculator {
	return &DayCountCalculator{}
}

// YearFraction calculates the fraction of a year between start and end under the given convention.
func (c *DayCountCalculator) YearFraction(start, end time.Time, convention DayCountConvention) float64 {
	if end.Before(start) {
		return 0.0
	}

	switch convention {
	case DayCountActual360:
		days := end.Sub(start).Hours() / 24.0
		return days / 360.0

	case DayCountActual365:
		days := end.Sub(start).Hours() / 24.0
		return days / 365.0

	case DayCount30360US:
		d1 := start.Day()
		d2 := end.Day()
		m1 := int(start.Month())
		m2 := int(end.Month())
		y1 := start.Year()
		y2 := end.Year()

		if d1 == 31 {
			d1 = 30
		}
		if d2 == 31 && d1 >= 30 {
			d2 = 30
		}

		days := float64((y2-y1)*360 + (m2-m1)*30 + (d2-d1))
		return days / 360.0

	case DayCount30360Europe:
		d1 := start.Day()
		d2 := end.Day()
		m1 := int(start.Month())
		m2 := int(end.Month())
		y1 := start.Year()
		y2 := end.Year()

		if d1 == 31 {
			d1 = 30
		}
		if d2 == 31 {
			d2 = 30
		}

		days := float64((y2-y1)*360 + (m2-m1)*30 + (d2-d1))
		return days / 360.0

	case DayCountActualActual:
		fallthrough
	default:
		// Actual/Actual ISDA formula
		days := end.Sub(start).Hours() / 24.0
		daysInYear := 365.0
		if c.isLeapYear(start.Year()) || c.isLeapYear(end.Year()) {
			daysInYear = 366.0
		}
		return days / daysInYear
	}
}

func (c *DayCountCalculator) isLeapYear(year int) bool {
	return year%4 == 0 && (year%100 != 0 || year%400 == 0)
}

// InterestAccrualService handles interest calculations and journal postings.
type InterestAccrualService struct {
	accountRepo repository.AccountRepository
	journalRepo repository.JournalEntryRepository
	postingEng  *PostingEngine
	calculator  *DayCountCalculator
}

func NewInterestAccrualService(
	accountRepo repository.AccountRepository,
	journalRepo repository.JournalEntryRepository,
	postingEng *PostingEngine,
) *InterestAccrualService {
	return &InterestAccrualService{
		accountRepo: accountRepo,
		journalRepo: journalRepo,
		postingEng:  postingEng,
		calculator:  NewDayCountCalculator(),
	}
}

// CalculateAccrual computes accrued interest for a given period without persisting entries.
func (s *InterestAccrualService) CalculateAccrual(
	account *model.Account,
	config *InterestProductConfig,
	start, end time.Time,
) (*AccrualResult, error) {
	if account == nil || config == nil {
		return nil, fmt.Errorf("account and config cannot be nil")
	}

	dayFraction := s.calculator.YearFraction(start, end, config.DayCount)
	balanceCents := account.AvailableBalance.AmountMinor()

	// 1. Negative Balance -> Overdraft interest charge
	if balanceCents < 0 {
		absBal := float64(-balanceCents)
		rate := config.OverdraftRatePct / 100.0
		interest := absBal * rate * dayFraction
		interestCents := int64(math.Round(interest))

		return &AccrualResult{
			AccountID:            account.ID,
			Currency:             account.Currency,
			OpeningBalanceCents:  balanceCents,
			AccruedInterestCents: interestCents,
			PeriodStartDate:      start,
			PeriodEndDate:        end,
			DayFraction:          dayFraction,
			IsOverdraftCharge:    true,
		}, nil
	}

	// 2. Positive Balance -> Tiered deposit interest calculation
	var totalInterest float64 = 0.0
	remainingBalance := balanceCents

	for _, tier := range config.Tiers {
		if remainingBalance <= 0 {
			break
		}

		var trancheCents int64
		if tier.MaxBalanceCents > 0 {
			tierCapacity := tier.MaxBalanceCents - tier.MinBalanceCents
			if tierCapacity <= 0 {
				continue
			}
			if remainingBalance > tierCapacity {
				trancheCents = tierCapacity
			} else {
				trancheCents = remainingBalance
			}
		} else {
			// Unlimited top tier
			trancheCents = remainingBalance
		}

		tierRate := tier.AnnualRatePct / 100.0
		tierInterest := float64(trancheCents) * tierRate * dayFraction
		totalInterest += tierInterest
		remainingBalance -= trancheCents
	}

	accruedCents := int64(math.Round(totalInterest))

	return &AccrualResult{
		AccountID:            account.ID,
		Currency:             account.Currency,
		OpeningBalanceCents:  balanceCents,
		AccruedInterestCents: accruedCents,
		PeriodStartDate:      start,
		PeriodEndDate:        end,
		DayFraction:          dayFraction,
		IsOverdraftCharge:    false,
	}, nil
}

// CapitalizeInterest posts accrued interest into the customer's balance via double-entry journal.
func (s *InterestAccrualService) CapitalizeInterest(
	ctx context.Context,
	result *AccrualResult,
	config *InterestProductConfig,
) (*model.JournalEntry, error) {
	if result.AccruedInterestCents <= 0 {
		return nil, nil // No interest to post
	}

	interestMoney, err := model.NewMoney(result.AccruedInterestCents, result.Currency)
	if err != nil {
		return nil, fmt.Errorf("invalid interest money amount: %w", err)
	}

	journalID := uuid.New().String()
	now := time.Now().UTC()

	var debitAcct, creditAcct string
	var desc string

	if result.IsOverdraftCharge {
		// Overdraft: Debit Customer Deposit (deduct funds), Credit Bank Fee/Interest Income
		debitAcct = result.AccountID
		creditAcct = config.InterestExpenseAcct
		desc = fmt.Sprintf("Overdraft interest charge for period %s to %s",
			result.PeriodStartDate.Format("2006-01-02"), result.PeriodEndDate.Format("2006-01-02"))
	} else {
		// Deposit Interest: Debit Bank Interest Expense, Credit Customer Deposit (add funds)
		debitAcct = config.InterestExpenseAcct
		creditAcct = result.AccountID
		desc = fmt.Sprintf("Interest capitalization for period %s to %s",
			result.PeriodStartDate.Format("2006-01-02"), result.PeriodEndDate.Format("2006-01-02"))
	}

	lines := []model.PostingLine{
		{
			ID:          uuid.New().String(),
			AccountID:   debitAcct,
			Direction:   model.DirectionDebit,
			Amount:      interestMoney,
			Description: desc,
		},
		{
			ID:          uuid.New().String(),
			AccountID:   creditAcct,
			Direction:   model.DirectionCredit,
			Amount:      interestMoney,
			Description: desc,
		},
	}

	entry, err := model.NewJournalEntry(
		journalID,
		result.PeriodEndDate,
		now,
		desc,
		"INTEREST_CAPITALIZATION",
		lines,
	)
	if err != nil {
		return nil, fmt.Errorf("failed to build interest journal entry: %w", err)
	}

	postedEntry, err := s.postingEng.Post(ctx, entry)
	if err != nil {
		return nil, fmt.Errorf("failed to post interest capitalization: %w", err)
	}

	return postedEntry, nil
}
