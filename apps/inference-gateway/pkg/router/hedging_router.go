package router

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"io.elmos/inferencegateway/pkg/providers"
	"io.elmos/inferencegateway/pkg/resilience"
)

var (
	ErrNoHealthyProvider = errors.New("no healthy or available upstream provider in route chain")
)

// ProviderChain defines an ordered priority list of providers for a model class.
type ProviderChain struct {
	ModelPattern string
	Providers    []providers.ProviderAdapter
	HedgingDelay time.Duration // Time to wait before dispatching parallel hedging request
}

// HedgingRouter routes requests across providers with circuit breaking and hedging.
type HedgingRouter struct {
	mu        sync.RWMutex
	chains    []ProviderChain
	breakers  *resilience.BreakerRegistry
	fallback  providers.ProviderAdapter
}

func NewHedgingRouter(breakers *resilience.BreakerRegistry, fallback providers.ProviderAdapter) *HedgingRouter {
	if breakers == nil {
		breakers = resilience.NewBreakerRegistry(3, 15*time.Second)
	}
	return &HedgingRouter{
		chains:   make([]ProviderChain, 0),
		breakers: breakers,
		fallback: fallback,
	}
}

func (hr *HedgingRouter) AddRoute(pattern string, hedgingDelay time.Duration, adapters ...providers.ProviderAdapter) {
	hr.mu.Lock()
	defer hr.mu.Unlock()

	hr.chains = append(hr.chains, ProviderChain{
		ModelPattern: pattern,
		Providers:    adapters,
		HedgingDelay: hedgingDelay,
	})
}

// FindChain finds the matched provider chain for a given model.
func (hr *HedgingRouter) FindChain(model string) []providers.ProviderAdapter {
	hr.mu.RLock()
	defer hr.mu.RUnlock()

	for _, c := range hr.chains {
		if c.ModelPattern == "*" || c.ModelPattern == model {
			return c.Providers
		}
	}
	if hr.fallback != nil {
		return []providers.ProviderAdapter{hr.fallback}
	}
	return nil
}

// ExecuteWithFallback dispatches sequentially down the chain until a provider succeeds.
func (hr *HedgingRouter) ExecuteWithFallback(ctx context.Context, req *providers.ChatRequest) (*providers.ChatResponse, error) {
	chain := hr.FindChain(req.Model)
	if len(chain) == 0 {
		if hr.fallback != nil {
			chain = []providers.ProviderAdapter{hr.fallback}
		} else {
			return nil, ErrNoHealthyProvider
		}
	}

	var lastErr error
	for _, adapter := range chain {
		breaker := hr.breakers.Get(string(adapter.Name()))
		if !breaker.AllowRequest() {
			lastErr = fmt.Errorf("circuit open for provider %s", adapter.Name())
			continue
		}

		resp, err := adapter.ChatCompletion(ctx, req)
		if err == nil {
			breaker.RecordSuccess()
			return resp, nil
		}

		breaker.RecordFailure()
		lastErr = err
	}

	// Try fallback if not already tried
	if hr.fallback != nil {
		return hr.fallback.ChatCompletion(ctx, req)
	}

	return nil, fmt.Errorf("%w: last error: %v", ErrNoHealthyProvider, lastErr)
}

// ExecuteWithHedging dispatches primary, and if hedgingDelay elapses, starts secondary in parallel.
func (hr *HedgingRouter) ExecuteWithHedging(ctx context.Context, req *providers.ChatRequest, hedgingDelay time.Duration) (*providers.ChatResponse, error) {
	chain := hr.FindChain(req.Model)
	if len(chain) <= 1 || hedgingDelay <= 0 {
		return hr.ExecuteWithFallback(ctx, req)
	}

	ctxHedging, cancel := context.WithCancel(ctx)
	defer cancel()

	type callResult struct {
		resp *providers.ChatResponse
		err  error
		prov providers.ProviderType
	}

	resultCh := make(chan callResult, 2)

	// Launch primary
	go func() {
		primary := chain[0]
		breaker := hr.breakers.Get(string(primary.Name()))
		if !breaker.AllowRequest() {
			resultCh <- callResult{err: resilience.ErrCircuitOpen, prov: primary.Name()}
			return
		}
		r, err := primary.ChatCompletion(ctxHedging, req)
		if err == nil {
			breaker.RecordSuccess()
		} else {
			breaker.RecordFailure()
		}
		resultCh <- callResult{resp: r, err: err, prov: primary.Name()}
	}()

	// Wait for primary or hedging timer
	timer := time.NewTimer(hedgingDelay)
	defer timer.Stop()

	var secondaryLaunched bool

	select {
	case res := <-resultCh:
		if res.err == nil {
			return res.resp, nil
		}
		// Primary failed early, launch secondary immediately
	case <-timer.C:
		// Hedging threshold reached: launch secondary in parallel
		secondaryLaunched = true
		go func() {
			secondary := chain[1]
			breaker := hr.breakers.Get(string(secondary.Name()))
			if !breaker.AllowRequest() {
				resultCh <- callResult{err: resilience.ErrCircuitOpen, prov: secondary.Name()}
				return
			}
			r, err := secondary.ChatCompletion(ctxHedging, req)
			if err == nil {
				breaker.RecordSuccess()
			} else {
				breaker.RecordFailure()
			}
			resultCh <- callResult{resp: r, err: err, prov: secondary.Name()}
		}()
	}

	// Wait for results
	expected := 1
	if secondaryLaunched {
		expected = 2
	}

	var finalErr error
	for i := 0; i < expected; i++ {
		res := <-resultCh
		if res.err == nil {
			cancel() // Cancel the losing call
			return res.resp, nil
		}
		finalErr = res.err
	}

	// Both failed, try fallback
	if hr.fallback != nil {
		return hr.fallback.ChatCompletion(ctx, req)
	}

	return nil, fmt.Errorf("%w: %v", ErrNoHealthyProvider, finalErr)
}
