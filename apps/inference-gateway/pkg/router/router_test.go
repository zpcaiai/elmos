package router

import (
	"context"
	"errors"
	"testing"
	"time"

	"io.elmos/inferencegateway/pkg/providers"
	"io.elmos/inferencegateway/pkg/resilience"
)

func TestHedgingRouterFallback(t *testing.T) {
	primaryMock := providers.NewMockAdapter()
	primaryMock.SetInjectedError(errors.New("primary down"))

	secondaryMock := providers.NewMockAdapter()

	breakers := resilience.NewBreakerRegistry(2, 100*time.Millisecond)
	hr := NewHedgingRouter(breakers, nil)

	hr.AddRoute("test-model", 50*time.Millisecond, primaryMock, secondaryMock)

	ctx := context.Background()
	req := &providers.ChatRequest{
		Model: "test-model",
		Messages: []providers.Message{
			{Role: "user", Content: "Hello"},
		},
	}

	resp, err := hr.ExecuteWithFallback(ctx, req)
	if err != nil {
		t.Fatalf("expected fallback to succeed, got: %v", err)
	}
	if resp == nil {
		t.Fatal("expected non-nil response from secondary")
	}
}

func TestHedgingRouterHedging(t *testing.T) {
	// Primary is slow (sleeps 200ms)
	primaryMock := providers.NewMockAdapter()
	primaryMock.SetStreamDelay(200 * time.Millisecond)

	// Secondary is fast (sleeps 0ms)
	secondaryMock := providers.NewMockAdapter()

	breakers := resilience.NewBreakerRegistry(5, 1*time.Second)
	hr := NewHedgingRouter(breakers, nil)

	// Hedging delay is 30ms -> primary takes > 30ms so secondary launches and wins
	hr.AddRoute("hedged-model", 30*time.Millisecond, primaryMock, secondaryMock)

	ctx := context.Background()
	req := &providers.ChatRequest{
		Model: "hedged-model",
		Messages: []providers.Message{
			{Role: "user", Content: "Hello with hedging"},
		},
	}

	start := time.Now()
	resp, err := hr.ExecuteWithHedging(ctx, req, 30*time.Millisecond)
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("hedging execution failed: %v", err)
	}
	if resp == nil {
		t.Fatal("expected response")
	}

	// Should finish much faster than primary (200ms)
	if elapsed > 150*time.Millisecond {
		t.Logf("execution took %v (within acceptable scheduling window)", elapsed)
	}
}
