package http

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

// SetupRouter configures Gin engine with middleware and ledger route groups.
func SetupRouter(
	accHandler *AccountHandler,
	postHandler *PostingHandler,
	recHandler *ReconciliationHandler,
) *gin.Engine {
	r := gin.New()

	// Middlewares
	r.Use(gin.Recovery())
	r.Use(requestTracingMiddleware())
	r.Use(tenantContextMiddleware())

	// Health probes
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "UP", "timestamp": time.Now().UTC()})
	})
	r.GET("/readyz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "READY"})
	})

	apiV1 := r.Group("/api/v1")
	{
		// Accounts
		accounts := apiV1.Group("/accounts")
		{
			accounts.POST("", accHandler.CreateAccount)
			accounts.GET("", accHandler.ListAccounts)
			accounts.GET("/:id", accHandler.GetAccount)
			accounts.POST("/:id/holds", accHandler.PlaceHold)
			accounts.DELETE("/:id/holds/:hold_id", accHandler.ReleaseHold)
			accounts.POST("/:id/freeze", accHandler.FreezeAccount)
		}

		// Transactions / Postings
		postings := apiV1.Group("/postings")
		{
			postings.POST("/transfer", postHandler.Transfer)
			postings.POST("/reversal/:entry_id", postHandler.ReverseTransaction)
		}

		// Reconciliation & Audits
		reconciliation := apiV1.Group("/reconciliation")
		{
			reconciliation.GET("/trial-balance", recHandler.GetTrialBalance)
			reconciliation.GET("/audit-chain", recHandler.VerifyAuditChain)
		}
	}

	return r
}

func requestTracingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		traceID := c.GetHeader("X-Trace-ID")
		if traceID == "" {
			traceID = uuid.New().String()
		}
		c.Set("trace_id", traceID)
		c.Header("X-Trace-ID", traceID)
		c.Next()
	}
}

func tenantContextMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		tenantID := c.GetHeader("X-Tenant-ID")
		if tenantID == "" {
			tenantID = "tenant-prod-01"
		}
		c.Set("tenant_id", tenantID)
		c.Next()
	}
}
