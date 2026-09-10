package resilience

import (
	"testing"
	"time"
)

func TestTokenBucketLimiter(t *testing.T) {
	// 60 RPM = 1 request per second capacity
	limiter := NewTokenBucketLimiter(60, 1000)

	// Consume initial tokens
	count := 0
	for i := 0; i < 70; i++ {
		if limiter.Allow(10) {
			count++
		}
	}

	// Should allow burst limit (60)
	if count != 60 {
		t.Errorf("expected 60 allowed requests during burst, got %d", count)
	}

	// Immediately subsequent request should be denied
	if limiter.Allow(10) {
		t.Error("expected request to be denied after exhausting burst")
	}

	// Wait 1.1 seconds for refill
	time.Sleep(1100 * time.Millisecond)
	if !limiter.Allow(10) {
		t.Error("expected request to be allowed after token refill")
	}
}

func TestCircuitBreakerStateTransitions(t *testing.T) {
	cb := NewCircuitBreaker("test-cb", 2, 200*time.Millisecond)

	if cb.State() != StateClosed {
		t.Errorf("initial state should be CLOSED, got %s", cb.State())
	}

	// Record 1 failure
	cb.RecordFailure()
	if cb.State() != StateClosed {
		t.Errorf("state after 1 failure should be CLOSED, got %s", cb.State())
	}

	// Record 2nd failure -> OPEN
	cb.RecordFailure()
	if cb.State() != StateOpen {
		t.Errorf("state after 2 failures should be OPEN, got %s", cb.State())
	}
	if cb.AllowRequest() {
		t.Error("requests should be blocked when OPEN")
	}

	// Wait cooldown -> HALF_OPEN
	time.Sleep(250 * time.Millisecond)
	if !cb.AllowRequest() {
		t.Error("request should be allowed after cooldown (HALF_OPEN trial)")
	}
	if cb.State() != StateHalfOpen {
		t.Errorf("state should now be HALF_OPEN, got %s", cb.State())
	}

	// 2 successes -> CLOSED
	cb.RecordSuccess()
	cb.RecordSuccess()
	if cb.State() != StateClosed {
		t.Errorf("state after consecutive successes should be CLOSED, got %s", cb.State())
	}
}

func TestJitteredBackoff(t *testing.T) {
	base := 50 * time.Millisecond
	max := 500 * time.Millisecond

	for attempt := 0; attempt < 5; attempt++ {
		d := ComputeJitteredBackoff(attempt, base, max)
		if d < 0 || d > max {
			t.Errorf("backoff duration out of range [0, %v]: %v", max, d)
		}
	}
}
