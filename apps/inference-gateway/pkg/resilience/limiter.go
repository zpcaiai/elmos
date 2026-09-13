package resilience

import (
	"errors"
	"math"
	"math/rand"
	"sync"
	"time"
)

var ErrRateLimitExceeded = errors.New("rate limit exceeded (RPM or TPM capacity exhausted)")

// TokenBucketLimiter implements a dual RPM/TPM token bucket rate limiter.
type TokenBucketLimiter struct {
	mu           sync.Mutex
	rateRPM      float64       // Tokens added per second for RPM
	burstRPM     float64       // Max bucket size for RPM
	tokensRPM    float64       // Current RPM tokens
	rateTPM      float64       // Tokens added per second for TPM
	burstTPM     float64       // Max bucket size for TPM
	tokensTPM    float64       // Current TPM tokens
	lastRefill   time.Time
}

func NewTokenBucketLimiter(rpm, tpm int) *TokenBucketLimiter {
	if rpm <= 0 {
		rpm = 600
	}
	if tpm <= 0 {
		tpm = 100000
	}

	rRPM := float64(rpm) / 60.0
	rTPM := float64(tpm) / 60.0

	return &TokenBucketLimiter{
		rateRPM:    rRPM,
		burstRPM:   float64(rpm),
		tokensRPM:  float64(rpm),
		rateTPM:    rTPM,
		burstTPM:   float64(tpm),
		tokensTPM:  float64(tpm),
		lastRefill: time.Now(),
	}
}

func (tb *TokenBucketLimiter) refill(now time.Time) {
	elapsed := now.Sub(tb.lastRefill).Seconds()
	if elapsed <= 0 {
		return
	}
	tb.lastRefill = now

	tb.tokensRPM = math.Min(tb.burstRPM, tb.tokensRPM+(elapsed*tb.rateRPM))
	tb.tokensTPM = math.Min(tb.burstTPM, tb.tokensTPM+(elapsed*tb.rateTPM))
}

// Allow checks whether 1 request and estimatedTokens can be accepted.
func (tb *TokenBucketLimiter) Allow(estimatedTokens int) bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	now := time.Now()
	tb.refill(now)

	reqTokens := float64(estimatedTokens)
	if reqTokens <= 0 {
		reqTokens = 100
	}

	if tb.tokensRPM >= 1.0 && tb.tokensTPM >= reqTokens {
		tb.tokensRPM -= 1.0
		tb.tokensTPM -= reqTokens
		return true
	}

	return false
}

// ComputeJitteredBackoff calculates backoff duration with full jitter.
func ComputeJitteredBackoff(attempt int, base time.Duration, max time.Duration) time.Duration {
	if attempt < 0 {
		attempt = 0
	}
	mult := math.Pow(2, float64(attempt))
	temp := float64(base) * mult
	if temp > float64(max) {
		temp = float64(max)
	}

	// Full jitter: random duration between 0 and temp
	r := rand.Float64()
	return time.Duration(r * temp)
}

// TenantRateLimiter manages isolated rate limiters across tenants and models.
type TenantRateLimiter struct {
	mu       sync.RWMutex
	limiters map[string]*TokenBucketLimiter
	defRPM   int
	defTPM   int
}

func NewTenantRateLimiter(defaultRPM, defaultTPM int) *TenantRateLimiter {
	return &TenantRateLimiter{
		limiters: make(map[string]*TokenBucketLimiter),
		defRPM:   defaultRPM,
		defTPM:   defaultTPM,
	}
}

func (trl *TenantRateLimiter) getOrCreate(tenantID, model string) *TokenBucketLimiter {
	key := tenantID + ":" + model
	trl.mu.RLock()
	lim, exists := trl.limiters[key]
	trl.mu.RUnlock()

	if exists {
		return lim
	}

	trl.mu.Lock()
	defer trl.mu.Unlock()

	if lim, exists := trl.limiters[key]; exists {
		return lim
	}

	newLim := NewTokenBucketLimiter(trl.defRPM, trl.defTPM)
	trl.limiters[key] = newLim
	return newLim
}

func (trl *TenantRateLimiter) Allow(tenantID, model string, estimatedTokens int) bool {
	limiter := trl.getOrCreate(tenantID, model)
	return limiter.Allow(estimatedTokens)
}
