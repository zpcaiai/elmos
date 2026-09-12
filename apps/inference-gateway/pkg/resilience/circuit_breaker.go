package resilience

import (
	"errors"
	"sync"
	"time"
)

var ErrCircuitOpen = errors.New("circuit breaker is OPEN: downstream service unavailable")

type CircuitState int

const (
	StateClosed CircuitState = iota
	StateOpen
	StateHalfOpen
)

func (s CircuitState) String() string {
	switch s {
	case StateClosed:
		return "CLOSED"
	case StateOpen:
		return "OPEN"
	case StateHalfOpen:
		return "HALF_OPEN"
	default:
		return "UNKNOWN"
	}
}

// CircuitBreaker manages fault tolerance and failover transitions.
type CircuitBreaker struct {
	mu              sync.Mutex
	name            string
	state           CircuitState
	failures        int
	successes       int
	failureThreshold int
	successThreshold int
	cooldown        time.Duration
	lastStateChange time.Time
}

func NewCircuitBreaker(name string, failureThreshold int, cooldown time.Duration) *CircuitBreaker {
	if failureThreshold <= 0 {
		failureThreshold = 5
	}
	if cooldown <= 0 {
		cooldown = 10 * time.Second
	}
	return &CircuitBreaker{
		name:             name,
		state:            StateClosed,
		failureThreshold: failureThreshold,
		successThreshold: 2, // 2 consecutive successes in HALF_OPEN to close
		cooldown:         cooldown,
		lastStateChange:  time.Now(),
	}
}

func (cb *CircuitBreaker) AllowRequest() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	now := time.Now()
	if cb.state == StateOpen {
		if now.Sub(cb.lastStateChange) >= cb.cooldown {
			cb.state = StateHalfOpen
			cb.successes = 0
			cb.lastStateChange = now
			return true
		}
		return false
	}
	return true
}

func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if cb.state == StateHalfOpen {
		cb.successes++
		if cb.successes >= cb.successThreshold {
			cb.state = StateClosed
			cb.failures = 0
			cb.successes = 0
			cb.lastStateChange = time.Now()
		}
	} else if cb.state == StateClosed && cb.failures > 0 {
		cb.failures = 0
	}
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures++
	if cb.state == StateHalfOpen || cb.failures >= cb.failureThreshold {
		cb.state = StateOpen
		cb.lastStateChange = time.Now()
	}
}

func (cb *CircuitBreaker) State() CircuitState {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state
}

func (cb *CircuitBreaker) Status() map[string]interface{} {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	return map[string]interface{}{
		"name":             cb.name,
		"state":            cb.state.String(),
		"consecutive_fails": cb.failures,
		"cooldown_seconds": cb.cooldown.Seconds(),
		"last_change":      cb.lastStateChange.Format(time.RFC3339),
	}
}

// Registry manages circuit breakers per provider/service.
type BreakerRegistry struct {
	mu       sync.RWMutex
	breakers map[string]*CircuitBreaker
	thresh   int
	cooldown time.Duration
}

func NewBreakerRegistry(thresh int, cooldown time.Duration) *BreakerRegistry {
	return &BreakerRegistry{
		breakers: make(map[string]*CircuitBreaker),
		thresh:   thresh,
		cooldown: cooldown,
	}
}

func (br *BreakerRegistry) Get(name string) *CircuitBreaker {
	br.mu.RLock()
	b, exists := br.breakers[name]
	br.mu.RUnlock()

	if exists {
		return b
	}

	br.mu.Lock()
	defer br.mu.Unlock()

	if b, exists := br.breakers[name]; exists {
		return b
	}

	nb := NewCircuitBreaker(name, br.thresh, br.cooldown)
	br.breakers[name] = nb
	return nb
}

func (br *BreakerRegistry) Snapshot() map[string]interface{} {
	br.mu.RLock()
	defer br.mu.RUnlock()

	res := make(map[string]interface{})
	for k, b := range br.breakers {
		res[k] = b.Status()
	}
	return res
}
