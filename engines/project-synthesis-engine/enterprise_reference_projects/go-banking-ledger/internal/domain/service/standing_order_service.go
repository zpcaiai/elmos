package service

import (
	"context"
	"fmt"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/google/uuid"
)

type ScheduleFrequency string

const (
	FreqDaily     ScheduleFrequency = "DAILY"
	FreqWeekly    ScheduleFrequency = "WEEKLY"
	FreqBiWeekly  ScheduleFrequency = "BI_WEEKLY"
	FreqMonthly   ScheduleFrequency = "MONTHLY"
	FreqQuarterly ScheduleFrequency = "QUARTERLY"
	FreqAnnual    ScheduleFrequency = "ANNUAL"
)

type BusinessDayConvention string

const (
	ConvFollowing         BusinessDayConvention = "FOLLOWING"          // Move to next business day
	ConvPreceding         BusinessDayConvention = "PRECEDING"          // Move to previous business day
	ConvModifiedFollowing BusinessDayConvention = "MODIFIED_FOLLOWING" // Next business day unless in next month
)

type StandingOrderStatus string

const (
	StandingOrderActive    StandingOrderStatus = "ACTIVE"
	StandingOrderPaused    StandingOrderStatus = "PAUSED"
	StandingOrderCompleted StandingOrderStatus = "COMPLETED"
	StandingOrderCancelled StandingOrderStatus = "CANCELLED"
)

// StandingOrder defines an automated recurring payment mandate.
type StandingOrder struct {
	ID                    string
	DebtorAccountID       string
	CreditorAccountID     string
	Amount                model.Money
	Frequency             ScheduleFrequency
	BusinessDayConv       BusinessDayConvention
	StartDate             time.Time
	EndDate               *time.Time
	NextExecutionDate     time.Time
	LastExecutionDate     *time.Time
	Status                StandingOrderStatus
	Description           string
	ConsecutiveFailures   int
	MaxRetryLimit         int
	TotalExecutedCount    int
}

type StandingOrderService struct {
	accountRepo repository.AccountRepository
	postingEng  *PostingEngine
	orders      map[string]*StandingOrder
}

func NewStandingOrderService(
	accountRepo repository.AccountRepository,
	postingEng *PostingEngine,
) *StandingOrderService {
	return &StandingOrderService{
		accountRepo: accountRepo,
		postingEng:  postingEng,
		orders:      make(map[string]*StandingOrder),
	}
}

func (s *StandingOrderService) CreateStandingOrder(
	debtorID, creditorID string,
	amount model.Money,
	frequency ScheduleFrequency,
	convention BusinessDayConvention,
	startDate time.Time,
	endDate *time.Time,
	description string,
) (*StandingOrder, error) {
	if debtorID == creditorID {
		return nil, fmt.Errorf("debtor and creditor accounts must differ")
	}
	if amount.AmountMinor() <= 0 {
		return nil, fmt.Errorf("standing order amount must be positive")
	}

	orderID := uuid.New().String()
	nextDate := s.adjustBusinessDay(startDate, convention)

	order := &StandingOrder{
		ID:                  orderID,
		DebtorAccountID:     debtorID,
		CreditorAccountID:   creditorID,
		Amount:              amount,
		Frequency:           frequency,
		BusinessDayConv:     convention,
		StartDate:           startDate,
		EndDate:             endDate,
		NextExecutionDate:   nextDate,
		Status:              StandingOrderActive,
		Description:         description,
		ConsecutiveFailures: 0,
		MaxRetryLimit:       3,
		TotalExecutedCount:  0,
	}

	s.orders[orderID] = order
	return order, nil
}

// ExecuteDueOrders sweeps all orders whose NextExecutionDate <= asOfDate and executes them.
func (s *StandingOrderService) ExecuteDueOrders(ctx context.Context, asOfDate time.Time) ([]*model.JournalEntry, []error) {
	var executedEntries []*model.JournalEntry
	var executionErrors []error

	for _, order := range s.orders {
		if order.Status != StandingOrderActive {
			continue
		}
		if !order.NextExecutionDate.After(asOfDate) {
			entry, err := s.executeSingleOrder(ctx, order)
			if err != nil {
				order.ConsecutiveFailures++
				if order.ConsecutiveFailures >= order.MaxRetryLimit {
					order.Status = StandingOrderPaused
				}
				executionErrors = append(executionErrors, fmt.Errorf("order %s failed: %w", order.ID, err))
			} else {
				order.ConsecutiveFailures = 0
				order.TotalExecutedCount++
				now := asOfDate
				order.LastExecutionDate = &now
				order.NextExecutionDate = s.calculateNextDate(order.NextExecutionDate, order.Frequency, order.BusinessDayConv)

				if order.EndDate != nil && order.NextExecutionDate.After(*order.EndDate) {
					order.Status = StandingOrderCompleted
				}
				executedEntries = append(executedEntries, entry)
			}
		}
	}

	return executedEntries, executionErrors
}

func (s *StandingOrderService) executeSingleOrder(ctx context.Context, order *StandingOrder) (*model.JournalEntry, error) {
	journalID := uuid.New().String()
	now := time.Now().UTC()

	lines := []model.PostingLine{
		{
			ID:          uuid.New().String(),
			AccountID:   order.DebtorAccountID,
			Direction:   model.DirectionDebit,
			Amount:      order.Amount,
			Description: fmt.Sprintf("Standing order: %s", order.Description),
		},
		{
			ID:          uuid.New().String(),
			AccountID:   order.CreditorAccountID,
			Direction:   model.DirectionCredit,
			Amount:      order.Amount,
			Description: fmt.Sprintf("Standing order credit: %s", order.Description),
		},
	}

	entry, err := model.NewJournalEntry(
		journalID,
		order.NextExecutionDate,
		now,
		fmt.Sprintf("Standing order execution: %s", order.Description),
		"STANDING_ORDER",
		lines,
	)
	if err != nil {
		return nil, err
	}

	return s.postingEng.Post(ctx, entry)
}

func (s *StandingOrderService) calculateNextDate(current time.Time, freq ScheduleFrequency, conv BusinessDayConvention) time.Time {
	var next time.Time
	switch freq {
	case FreqDaily:
		next = current.AddDate(0, 0, 1)
	case FreqWeekly:
		next = current.AddDate(0, 0, 7)
	case FreqBiWeekly:
		next = current.AddDate(0, 0, 14)
	case FreqMonthly:
		next = current.AddDate(0, 1, 0)
	case FreqQuarterly:
		next = current.AddDate(0, 3, 0)
	case FreqAnnual:
		next = current.AddDate(1, 0, 0)
	default:
		next = current.AddDate(0, 1, 0)
	}

	return s.adjustBusinessDay(next, conv)
}

func (s *StandingOrderService) adjustBusinessDay(t time.Time, conv BusinessDayConvention) time.Time {
	weekday := t.Weekday()

	switch conv {
	case ConvFollowing:
		if weekday == time.Saturday {
			return t.AddDate(0, 0, 2)
		} else if weekday == time.Sunday {
			return t.AddDate(0, 0, 1)
		}
		return t

	case ConvPreceding:
		if weekday == time.Saturday {
			return t.AddDate(0, 0, -1)
		} else if weekday == time.Sunday {
			return t.AddDate(0, 0, -2)
		}
		return t

	case ConvModifiedFollowing:
		originalMonth := t.Month()
		adjusted := t
		if weekday == time.Saturday {
			adjusted = t.AddDate(0, 0, 2)
		} else if weekday == time.Sunday {
			adjusted = t.AddDate(0, 0, 1)
		}
		// If following pushed us into next month, switch to preceding
		if adjusted.Month() != originalMonth {
			if weekday == time.Saturday {
				return t.AddDate(0, 0, -1)
			} else if weekday == time.Sunday {
				return t.AddDate(0, 0, -2)
			}
		}
		return adjusted

	default:
		return t
	}
}
