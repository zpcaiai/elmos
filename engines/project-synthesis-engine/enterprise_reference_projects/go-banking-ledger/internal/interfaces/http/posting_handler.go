package http

import (
	"net/http"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// PostingHandler handles transaction posting requests and reversals.
type PostingHandler struct {
	engine *service.PostingEngine
}

func NewPostingHandler(engine *service.PostingEngine) *PostingHandler {
	return &PostingHandler{engine: engine}
}

// Transfer initiates an atomic transfer between two ledger accounts.
func (h *PostingHandler) Transfer(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	if tenantID == "" {
		tenantID = "default"
	}

	var req TransferRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	valDate := time.Now().UTC()
	if req.ValueDate != nil {
		valDate = req.ValueDate.UTC()
	}

	postingReq := model.PostingRequest{
		RequestID:      uuid.New().String(),
		TenantID:       tenantID,
		IdempotencyKey: req.IdempotencyKey,
		Type:           model.TxTypeTransfer,
		ReferenceID:    req.ReferenceID,
		SourceAccount:  req.SourceAccount,
		TargetAccount:  req.TargetAccount,
		Amount:         req.Amount,
		Currency:       req.Currency,
		FeeAmount:      req.FeeAmount,
		FeeAccount:     req.FeeAccount,
		Description:    req.Description,
		ValueDate:      valDate,
		Metadata:       req.Metadata,
	}

	entry, err := h.engine.ProcessTransfer(c.Request.Context(), postingReq)
	if err != nil {
		c.JSON(http.StatusUnprocessableEntity, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	c.JSON(http.StatusCreated, ApiResponse{Success: true, Data: entry})
}

// ReverseTransaction creates a counter-entry canceling a posted voucher.
func (h *PostingHandler) ReverseTransaction(c *gin.Context) {
	tenantID := c.GetString("tenant_id")
	entryID := c.Param("entry_id")

	var req ReversalRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	reversal, err := h.engine.ReverseTransaction(c.Request.Context(), tenantID, entryID, req.Reason)
	if err != nil {
		c.JSON(http.StatusUnprocessableEntity, ApiResponse{Success: false, Error: err.Error()})
		return
	}

	c.JSON(http.StatusOK, ApiResponse{Success: true, Data: reversal})
}
