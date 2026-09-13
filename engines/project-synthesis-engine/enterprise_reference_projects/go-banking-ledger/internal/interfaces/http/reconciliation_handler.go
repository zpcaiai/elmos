package http

import (
	"net/http"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/gin-gonic/gin"
)

// ReconciliationHandler handles trial balance generation and audit integrity checks.
type ReconciliationHandler struct {
	reconciliationSvc *service.ReconciliationService
}

func NewReconciliationHandler(svc *service.ReconciliationService) *ReconciliationHandler {
	return &ReconciliationHandler{reconciliationSvc: svc}
}

// GetTrialBalance computes the trial balance sheet as of current time.
func (h *ReconciliationHandler) GetTrialBalance(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	if tenantID == "" {
		tenantID = "default"
	}

	report, err := h.reconciliationSvc.GenerateTrialBalance(c.Request.Context(), tenantID, time.Now().UTC())
	if err != nil {
		c.JSON(http.StatusInternalServerError, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	status := http.StatusOK
	if !report.IsBalanced {
		status = http.StatusConflict // Trial balance imbalance indicates ledger inconsistency
	}

	c.JSON(status, ApiResponse{Success: true, Data: report})
}

// VerifyAuditChain validates the Merkle tree hash chain for a specific date range.
func (h *ReconciliationHandler) VerifyAuditChain(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	if tenantID == "" {
		tenantID = "default"
	}

	fromStr := c.DefaultQuery("from", time.Now().UTC().AddDate(0, 0, -30).Format(time.RFC3339))
	toStr := c.DefaultQuery("to", time.Now().UTC().Format(time.RFC3339))

	from, err := time.Parse(time.RFC3339, fromStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: "invalid from time format (RFC3339 required)"})
		return
	}
	to, err := time.Parse(time.RFC3339, toStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: "invalid to time format (RFC3339 required)"})
		return
	}

	report, err := h.reconciliationSvc.VerifyAuditIntegrity(c.Request.Context(), tenantID, from, to)
	if err != nil {
		c.JSON(http.StatusInternalServerError, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: report})
}
