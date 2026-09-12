package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"gorm.io/gorm"
)

// JournalEntryGormModel maps to the partitioned ledger_journal_entries table.
type JournalEntryGormModel struct {
	EntryID           string    `gorm:"primaryKey;type:varchar(64)"`
	TenantID          string    `gorm:"index:idx_tenant_entry;type:varchar(64);not null"`
	IdempotencyKey    string    `gorm:"uniqueIndex:idx_tenant_idem,composite:tenant_id;type:varchar(128);not null"`
	ReferenceID       string    `gorm:"index;type:varchar(128);not null"`
	Description       string    `gorm:"type:text"`
	Status            string    `gorm:"type:varchar(32);not null"`
	ValueDate         time.Time `gorm:"not null"`
	PostingDate       time.Time `gorm:"index:idx_posting_date;not null"`
	TotalDebit        int64     `gorm:"type:bigint;not null"`
	TotalCredit       int64     `gorm:"type:bigint;not null"`
	Currency          string    `gorm:"type:varchar(3);not null"`
	IsMultiCurrency   bool      `gorm:"not null;default:false"`
	BaseCurrency      string    `gorm:"type:varchar(3)"`
	MerkleRoot        string    `gorm:"type:varchar(64);not null"`
	PreviousEntryHash string    `gorm:"type:varchar(64);not null"`
	ReversalOfEntryID string    `gorm:"type:varchar(64)"`
	ReversedByEntryID string    `gorm:"type:varchar(64)"`
	CreatedAt         time.Time `gorm:"not null"`
	PostedAt          time.Time

	Lines []JournalLineGormModel `gorm:"foreignKey:EntryID;references:EntryID"`
}

func (JournalEntryGormModel) TableName() string {
	return "ledger_journal_entries"
}

// JournalLineGormModel maps each debit/credit leg in a voucher.
type JournalLineGormModel struct {
	LineID       string  `gorm:"primaryKey;type:varchar(64)"`
	EntryID      string  `gorm:"index;type:varchar(64);not null"`
	AccountID    string  `gorm:"index:idx_acc_lines;type:varchar(64);not null"`
	Direction    string  `gorm:"type:varchar(16);not null"`
	Amount       int64   `gorm:"type:bigint;not null"`
	Currency     string  `gorm:"type:varchar(3);not null"`
	ExchangeRate float64 `gorm:"type:decimal(18,6)"`
	BaseAmount   int64   `gorm:"type:bigint"`
	Description  string  `gorm:"type:varchar(255)"`
	MetadataJSON string  `gorm:"type:text"`
}

func (JournalLineGormModel) TableName() string {
	return "ledger_journal_lines"
}

// GormJournalRepository implements JournalRepository via GORM.
type GormJournalRepository struct {
	db *gorm.DB
}

func NewGormJournalRepository(db *gorm.DB) *GormJournalRepository {
	return &GormJournalRepository{db: db}
}

func (r *GormJournalRepository) SaveEntry(ctx context.Context, entry *model.JournalEntryAggregate) error {
	m := &JournalEntryGormModel{
		EntryID:           entry.EntryID,
		TenantID:          entry.TenantID,
		IdempotencyKey:    entry.IdempotencyKey,
		ReferenceID:       entry.ReferenceID,
		Description:       entry.Description,
		Status:            string(entry.Status),
		ValueDate:         entry.ValueDate,
		PostingDate:       entry.PostingDate,
		TotalDebit:        entry.TotalDebit,
		TotalCredit:       entry.TotalCredit,
		Currency:          entry.Currency,
		IsMultiCurrency:   entry.IsMultiCurrency,
		BaseCurrency:      entry.BaseCurrency,
		MerkleRoot:        entry.MerkleRoot,
		PreviousEntryHash: entry.PreviousEntryHash,
		ReversalOfEntryID: entry.ReversalOfEntryID,
		ReversedByEntryID: entry.ReversedByEntryID,
		CreatedAt:         entry.CreatedAt,
		PostedAt:          entry.PostedAt,
	}

	for _, l := range entry.Lines {
		metaBytes, _ := json.Marshal(l.Metadata)
		m.Lines = append(m.Lines, JournalLineGormModel{
			LineID:       l.LineID,
			EntryID:      entry.EntryID,
			AccountID:    l.AccountID,
			Direction:    string(l.Direction),
			Amount:       l.Amount,
			Currency:     l.Currency,
			ExchangeRate: l.ExchangeRate,
			BaseAmount:   l.BaseAmount,
			Description:  l.Description,
			MetadataJSON: string(metaBytes),
		})
	}

	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(m).Error; err != nil {
			return err
		}
		return nil
	})
}

func (r *GormJournalRepository) FindEntryByID(ctx context.Context, tenantID, entryID string) (*model.JournalEntryAggregate, error) {
	var m JournalEntryGormModel
	err := r.db.WithContext(ctx).
		Preload("Lines").
		Where("tenant_id = ? AND entry_id = ?", tenantID, entryID).
		First(&m).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, repository.ErrEntryNotFound
		}
		return nil, err
	}

	return r.toAggregate(&m), nil
}

func (r *GormJournalRepository) FindLatestEntry(ctx context.Context, tenantID string) (*model.JournalEntryAggregate, error) {
	var m JournalEntryGormModel
	err := r.db.WithContext(ctx).
		Preload("Lines").
		Where("tenant_id = ?", tenantID).
		Order("posting_date DESC, created_at DESC").
		First(&m).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return r.toAggregate(&m), nil
}

func (r *GormJournalRepository) ListEntriesByAccount(
	ctx context.Context,
	tenantID, accountID string,
	from, to time.Time,
	limit, offset int,
) ([]*model.JournalEntryAggregate, error) {
	var entryIDs []string
	err := r.db.WithContext(ctx).
		Table("ledger_journal_lines").
		Select("DISTINCT entry_id").
		Where("account_id = ?", accountID).
		Scan(&entryIDs).Error

	if err != nil || len(entryIDs) == 0 {
		return nil, err
	}

	var models []JournalEntryGormModel
	err = r.db.WithContext(ctx).
		Preload("Lines").
		Where("tenant_id = ? AND entry_id IN ? AND posting_date BETWEEN ? AND ?", tenantID, entryIDs, from, to).
		Order("posting_date DESC").
		Limit(limit).
		Offset(offset).
		Find(&models).Error

	if err != nil {
		return nil, err
	}

	var res []*model.JournalEntryAggregate
	for i := range models {
		res = append(res, r.toAggregate(&models[i]))
	}
	return res, nil
}

func (r *GormJournalRepository) GetEntryHashesForPeriod(
	ctx context.Context,
	tenantID string,
	from, to time.Time,
) ([]string, error) {
	var hashes []string
	err := r.db.WithContext(ctx).
		Table("ledger_journal_entries").
		Select("merkle_root").
		Where("tenant_id = ? AND posting_date BETWEEN ? AND ? AND merkle_root != ''", tenantID, from, to).
		Order("posting_date ASC, created_at ASC").
		Scan(&hashes).Error

	return hashes, err
}

func (r *GormJournalRepository) toAggregate(m *JournalEntryGormModel) *model.JournalEntryAggregate {
	var lines []model.EntryLine
	for _, l := range m.Lines {
		var meta map[string]any
		if l.MetadataJSON != "" {
			_ = json.Unmarshal([]byte(l.MetadataJSON), &meta)
		}
		lines = append(lines, model.EntryLine{
			LineID:       l.LineID,
			AccountID:    l.AccountID,
			Direction:    model.PostingDirection(l.Direction),
			Amount:       l.Amount,
			Currency:     l.Currency,
			ExchangeRate: l.ExchangeRate,
			BaseAmount:   l.BaseAmount,
			Description:  l.Description,
			Metadata:     meta,
		})
	}

	return &model.JournalEntryAggregate{
		EntryID:           m.EntryID,
		TenantID:          m.TenantID,
		IdempotencyKey:    m.IdempotencyKey,
		ReferenceID:       m.ReferenceID,
		Description:       m.Description,
		Status:            model.JournalStatus(m.Status),
		ValueDate:         m.ValueDate,
		PostingDate:       m.PostingDate,
		Lines:             lines,
		TotalDebit:        m.TotalDebit,
		TotalCredit:       m.TotalCredit,
		Currency:          m.Currency,
		IsMultiCurrency:   m.IsMultiCurrency,
		BaseCurrency:      m.BaseCurrency,
		MerkleRoot:        m.MerkleRoot,
		PreviousEntryHash: m.PreviousEntryHash,
		ReversalOfEntryID: m.ReversalOfEntryID,
		ReversedByEntryID: m.ReversedByEntryID,
		CreatedAt:         m.CreatedAt,
		PostedAt:          m.PostedAt,
	}
}
