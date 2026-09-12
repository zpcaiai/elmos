package persistence

import (
	"context"
	"errors"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// AccountGormModel represents the relational database schema for ledger accounts.
type AccountGormModel struct {
	AccountID      string    `gorm:"primaryKey;type:varchar(64)"`
	TenantID       string    `gorm:"index:idx_tenant_acc;type:varchar(64);not null"`
	AccountNumber  string    `gorm:"uniqueIndex:idx_tenant_acc_num,composite:tenant_id;type:varchar(64);not null"`
	Name           string    `gorm:"type:varchar(255);not null"`
	Type           string    `gorm:"type:varchar(32);not null"`
	Status         string    `gorm:"type:varchar(32);not null"`
	Currency       string    `gorm:"type:varchar(3);not null"`
	PostedBalance  int64     `gorm:"type:bigint;not null;default:0"`
	PendingDebit   int64     `gorm:"type:bigint;not null;default:0"`
	PendingCredit  int64     `gorm:"type:bigint;not null;default:0"`
	HeldAmount     int64     `gorm:"type:bigint;not null;default:0"`
	OverdraftLimit int64     `gorm:"type:bigint;not null;default:0"`
	Version        int64     `gorm:"type:bigint;not null;default:1"`
	MerkleRoot     string    `gorm:"type:varchar(64);not null"`
	CreatedAt      time.Time `gorm:"not null"`
	UpdatedAt      time.Time `gorm:"not null"`
}

func (AccountGormModel) TableName() string {
	return "ledger_accounts"
}

// GormAccountRepository implements AccountRepository using GORM with optimistic and pessimistic locking.
type GormAccountRepository struct {
	db *gorm.DB
}

func NewGormAccountRepository(db *gorm.DB) *GormAccountRepository {
	return &GormAccountRepository{db: db}
}

func (r *GormAccountRepository) toAggregate(m *AccountGormModel) *model.AccountAggregate {
	acc, _ := model.NewAccount(
		m.AccountID,
		m.TenantID,
		m.AccountNumber,
		m.Name,
		model.AccountType(m.Type),
		m.Currency,
		m.OverdraftLimit,
	)
	if acc == nil {
		return nil
	}
	acc.Status = model.AccountStatus(m.Status)
	acc.PostedBalance = m.PostedBalance
	acc.PendingDebit = m.PendingDebit
	acc.PendingCredit = m.PendingCredit
	acc.HeldAmount = m.HeldAmount
	acc.Version = m.Version
	acc.MerkleRoot = m.MerkleRoot
	acc.CreatedAt = m.CreatedAt
	acc.UpdatedAt = m.UpdatedAt
	return acc
}

func (r *GormAccountRepository) toModel(a *model.AccountAggregate) *AccountGormModel {
	snap := a.Snapshot()
	return &AccountGormModel{
		AccountID:      snap.AccountID,
		TenantID:       snap.TenantID,
		AccountNumber:  snap.AccountNumber,
		Name:           snap.Name,
		Type:           string(snap.Type),
		Status:         string(snap.Status),
		Currency:       snap.Currency,
		PostedBalance:  snap.PostedBalance,
		PendingDebit:   snap.PendingDebit,
		PendingCredit:  snap.PendingCredit,
		HeldAmount:     snap.HeldAmount,
		OverdraftLimit: snap.OverdraftLimit,
		Version:        snap.Version,
		MerkleRoot:     snap.MerkleRoot,
		CreatedAt:      a.CreatedAt,
		UpdatedAt:      snap.UpdatedAt,
	}
}

func (r *GormAccountRepository) FindByID(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error) {
	var m AccountGormModel
	err := r.db.WithContext(ctx).
		Where("tenant_id = ? AND account_id = ?", tenantID, accountID).
		First(&m).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, repository.ErrAccountNotFound
		}
		return nil, err
	}
	return r.toAggregate(&m), nil
}

func (r *GormAccountRepository) FindByIDForUpdate(ctx context.Context, tenantID, accountID string) (*model.AccountAggregate, error) {
	var m AccountGormModel
	err := r.db.WithContext(ctx).
		Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("tenant_id = ? AND account_id = ?", tenantID, accountID).
		First(&m).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, repository.ErrAccountNotFound
		}
		return nil, err
	}
	return r.toAggregate(&m), nil
}

func (r *GormAccountRepository) Save(ctx context.Context, account *model.AccountAggregate) error {
	m := r.toModel(account)
	// Optimistic locking update: check version
	result := r.db.WithContext(ctx).
		Model(&AccountGormModel{}).
		Where("tenant_id = ? AND account_id = ? AND version = ?", m.TenantID, m.AccountID, m.Version-1).
		Updates(map[string]any{
			"posted_balance": m.PostedBalance,
			"pending_debit":  m.PendingDebit,
			"pending_credit": m.PendingCredit,
			"held_amount":    m.HeldAmount,
			"status":         m.Status,
			"version":        m.Version,
			"merkle_root":    m.MerkleRoot,
			"updated_at":     m.UpdatedAt,
		})

	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		// Try insert if new record
		if m.Version == 1 {
			return r.db.WithContext(ctx).Create(m).Error
		}
		return model.ErrOptimisticLockFailure
	}
	return nil
}

func (r *GormAccountRepository) ListByTenant(ctx context.Context, tenantID string, limit, offset int) ([]*model.AccountAggregate, error) {
	var models []AccountGormModel
	err := r.db.WithContext(ctx).
		Where("tenant_id = ?", tenantID).
		Order("account_number ASC").
		Limit(limit).
		Offset(offset).
		Find(&models).Error

	if err != nil {
		return nil, err
	}

	var aggregates []*model.AccountAggregate
	for i := range models {
		aggregates = append(aggregates, r.toAggregate(&models[i]))
	}
	return aggregates, nil
}

func (r *GormAccountRepository) GetTrialBalance(ctx context.Context, tenantID string) (map[string]int64, error) {
	type BalResult struct {
		AccountID     string
		PostedBalance int64
	}
	var results []BalResult
	err := r.db.WithContext(ctx).
		Table("ledger_accounts").
		Select("account_id, posted_balance").
		Where("tenant_id = ?", tenantID).
		Scan(&results).Error

	if err != nil {
		return nil, err
	}

	m := make(map[string]int64)
	for _, res := range results {
		m[res.AccountID] = res.PostedBalance
	}
	return m, nil
}
