package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/model"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/domain/service"
	ledgerHttp "github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/interfaces/http"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/messaging"
	"github.com/elmos/enterprise_reference_projects/go-banking-ledger/internal/infrastructure/persistence"
)

func main() {
	log.Println("Starting Core Banking Ledger Microservice...")

	// 1. Initialize Currency Registry
	currencyReg := model.NewCurrencyRegistry()

	// 2. Initialize Repositories (In-memory for standalone / GORM in cluster mode)
	accountRepo := persistence.NewInMemoryAccountRepository()
	journalRepo := persistence.NewInMemoryJournalRepository()
	idempotencyRepo := persistence.NewInMemoryIdempotencyRepository()
	lockManager := persistence.NewInMemoryLockManager()

	// 3. Initialize Domain Services
	postingEngine := service.NewPostingEngine(
		accountRepo,
		journalRepo,
		idempotencyRepo,
		lockManager,
		currencyReg,
	)
	reconciliationSvc := service.NewReconciliationService(accountRepo, journalRepo)

	// 4. Initialize Messaging Infrastructure
	eventBus := messaging.NewInMemoryEventBus()
	outboxSweeper := messaging.NewOutboxSweeper(eventBus)

	// Periodic Outbox Sweeper in background
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				_, _ = outboxSweeper.Sweep(ctx)
			}
		}
	}()

	// 5. Setup HTTP Handlers and Router
	accountHandler := ledgerHttp.NewAccountHandler(accountRepo)
	postingHandler := ledgerHttp.NewPostingHandler(postingEngine)
	reconciliationHandler := ledgerHttp.NewReconciliationHandler(reconciliationSvc)

	router := ledgerHttp.SetupRouter(accountHandler, postingHandler, reconciliationHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := &http.Server{
		Addr:         ":" + port,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		log.Printf("Ledger HTTP server listening on port %s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server failed to listen: %v", err)
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down Ledger Server gracefully...")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Ledger Server exited cleanly.")
}
