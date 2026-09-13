package http

import (
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/repository"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// AccountHandler manages REST endpoints for ledger account entities.
type AccountHandler struct {
	accountRepo repository.AccountRepository
}

func NewAccountHandler(repo repository.AccountRepository) *AccountHandler {
	return &AccountHandler{accountRepo: repo}
}

// CreateAccount provisions a new ledger account.
func (h *AccountHandler) CreateAccount(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	if tenantID == "" {
		tenantID = "default"
	}

	var req CreateAccountRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}
	if err := req.Validate(); err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	accountID := fmtAccountID(req.AccountNumber)
	acc, err := model.NewAccount(
		accountID,
		tenantID,
		req.AccountNumber,
		req.Name,
		req.Type,
		req.Currency,
		req.OverdraftLimit,
	)
	if err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	if err := h.accountRepo.Save(c.Request.Context(), acc); err != nil {
		c.JSON(http.StatusInternalServerError, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	c.JSON(http.StatusCreated, ApiResponse{Success: true, Data: acc.Snapshot()})
}

// GetAccount retrieves account details and real-time balances.
func (h *AccountHandler) GetAccount(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	accountID := c.Param("id")

	acc, err := h.accountRepo.FindByID(c.Request.Context(), tenantID, accountID)
	if err != nil {
		if errors.Is(err, repository.ErrAccountNotFound) {
			c.JSON(http.StatusNotFound, ApiResponse{Success: false, Error: "account not found"})
			return
		}
		c.JSON(http.StatusInternalServerError, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: acc.Snapshot()})
}

// ListAccounts lists all accounts for the current tenant.
func (h *AccountHandler) ListAccounts(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	accs, err := h.accountRepo.ListByTenant(c.Request.Context(), tenantID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	var snapshots []model.AccountSnapshot
	for _, a := range accs {
		snapshots = append(snapshots, a.Snapshot())
	}

	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: snapshots})
}

// PlaceHold places an authorization hold on funds.
func (h *AccountHandler) PlaceHold(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	accountID := c.Param("id")

	var req PlaceHoldRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	acc, err := h.accountRepo.FindByID(c.Request.Context(), tenantID, accountID)
	if err != nil {
		c.JSON(http.StatusNotFound, ApiResponse{Success: false, Error: "account not found"})
		return
	}

	hold, err := acc.PlaceHold(
		req.HoldID,
		req.ReferenceID,
		req.Reason,
		req.Amount,
		req.Currency,
		time.Duration(req.DurationSec)*time.Second,
	)
	if err != nil {
		c.JSON(http.StatusUnprocessableEntity, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	_ = h.accountRepo.Save(c.Request.Context(), acc)
	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: hold})
}

// ReleaseHold releases an existing funds hold.
func (h *AccountHandler) ReleaseHold(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	accountID := c.Param("id")
	holdID := c.Param("hold_id")

	acc, err := h.accountRepo.FindByID(c.Request.Context(), tenantID, accountID)
	if err != nil {
		c.JSON(http.StatusNotFound, ApiResponse{Success: false, Error: "account not found"})
		return
	}

	hold, err := acc.ReleaseHold(holdID)
	if err != nil {
		c.JSON(http.StatusUnprocessableEntity, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	_ = h.accountRepo.Save(c.Request.Context(), acc)
	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: hold})
}

// FreezeAccount suspends debit operations on the account.
func (h *AccountHandler) FreezeAccount(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	accountID := c.Param("id")

	acc, err := h.accountRepo.FindByID(c.Request.Context(), tenantID, accountID)
	if err != nil {
		c.JSON(http.StatusNotFound, ApiResponse{Success: false, Error: "account not found"})
		return
	}

	if err := acc.Freeze("administrative freeze"); err != nil {
		c.JSON(http.StatusUnprocessableEntity, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	_ = h.accountRepo.Save(c.Request.Context(), acc)
	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: acc.Snapshot()})
}

func fmtAccountID(accNum string) string {
	return "acc_" + uuid.New().String()[:8] + "_" + accNum
}
