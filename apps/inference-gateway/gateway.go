package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

// Circuit Breaker State
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

// Circuit Breaker implementation
type CircuitBreaker struct {
	mu           sync.Mutex
	state        CircuitState
	failures     int
	threshold    int
	cooldown     time.Duration
	lastStateChange time.Time
}

func NewCircuitBreaker(threshold int, cooldown time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		state:           StateClosed,
		threshold:       threshold,
		cooldown:        cooldown,
		lastStateChange: time.Now(),
	}
}

func (cb *CircuitBreaker) AllowRequest() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	now := time.Now()
	if cb.state == StateOpen {
		if now.Sub(cb.lastStateChange) >= cb.cooldown {
			cb.state = StateHalfOpen
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

	if cb.state == StateHalfOpen || cb.failures > 0 {
		cb.state = StateClosed
		cb.failures = 0
		cb.lastStateChange = time.Now()
	}
}

func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	cb.failures++
	if cb.failures >= cb.threshold {
		cb.state = StateOpen
		cb.lastStateChange = time.Now()
	}
}

func (cb *CircuitBreaker) GetState() string {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.state.String()
}

// Token Bucket Rate Limiter
type RateLimiter struct {
	mu         sync.Mutex
	capacity   float64
	tokens     float64
	refillRate float64 // tokens per second
	lastRefill time.Time
}

func NewRateLimiter(capacity float64, refillRate float64) *RateLimiter {
	return &RateLimiter{
		capacity:   capacity,
		tokens:     capacity,
		refillRate: refillRate,
		lastRefill: time.Now(),
	}
}

func (rl *RateLimiter) Allow() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(rl.lastRefill).Seconds()
	rl.tokens = min(rl.capacity, rl.tokens+elapsed*rl.refillRate)
	rl.lastRefill = now

	if rl.tokens >= 1.0 {
		rl.tokens -= 1.0
		return true
	}
	return false
}

// Inference Gateway Metrics
type Metrics struct {
	TotalRequests    atomic.Uint64
	SuccessRequests  atomic.Uint64
	RejectedRequests atomic.Uint64
	TotalTokens      atomic.Uint64
}

// Inference Gateway Server
type InferenceGateway struct {
	mux            *http.ServeMux
	limiter        *RateLimiter
	circuitBreaker *CircuitBreaker
	metrics        Metrics
}

func NewInferenceGateway(rateLimitCapacity, refillRate float64, cbThreshold int, cbCooldown time.Duration) *InferenceGateway {
	gw := &InferenceGateway{
		mux:            http.NewServeMux(),
		limiter:        NewRateLimiter(rateLimitCapacity, refillRate),
		circuitBreaker: NewCircuitBreaker(cbThreshold, cbCooldown),
	}
	gw.registerRoutes()
	return gw
}

func (gw *InferenceGateway) registerRoutes() {
	gw.mux.HandleFunc("POST /v1/chat/completions", gw.handleChatCompletions)
	gw.mux.HandleFunc("POST /v1/embeddings", gw.handleEmbeddings)
	gw.mux.HandleFunc("GET /health", gw.handleHealth)
	gw.mux.HandleFunc("GET /metrics", gw.handleMetrics)
}

func (gw *InferenceGateway) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	gw.mux.ServeHTTP(w, r)
}

func (gw *InferenceGateway) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"status":         "UP",
		"circuitBreaker": gw.circuitBreaker.GetState(),
		"service":        "elmos-inference-gateway",
	})
}

func (gw *InferenceGateway) handleMetrics(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"totalRequests":    gw.metrics.TotalRequests.Load(),
		"successRequests":  gw.metrics.SuccessRequests.Load(),
		"rejectedRequests": gw.metrics.RejectedRequests.Load(),
		"totalTokens":      gw.metrics.TotalTokens.Load(),
		"circuitBreaker":   gw.circuitBreaker.GetState(),
	})
}

func (gw *InferenceGateway) handleChatCompletions(w http.ResponseWriter, r *http.Request) {
	gw.metrics.TotalRequests.Add(1)

	// 1. Rate Limiting Check
	if !gw.limiter.Allow() {
		gw.metrics.RejectedRequests.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		json.NewEncoder(w).Encode(map[string]any{
			"error": map[string]string{
				"message": "Rate limit exceeded. Please throttle your requests.",
				"type":    "rate_limit_error",
			},
		})
		return
	}

	// 2. Circuit Breaker Check
	if !gw.circuitBreaker.AllowRequest() {
		gw.metrics.RejectedRequests.Add(1)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]any{
			"error": map[string]string{
				"message": "Circuit breaker open: upstream provider temporarily unavailable.",
				"type":    "circuit_breaker_error",
			},
		})
		return
	}

	// 3. Parse Request
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil || len(bodyBytes) == 0 {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	var req struct {
		Model    string `json:"model"`
		Stream   bool   `json:"stream"`
		Messages []struct {
			Role    string `json:"role"`
			Content string `json:"content"`
		} `json:"messages"`
	}
	if err := json.Unmarshal(bodyBytes, &req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	// Simulate/Handle streaming SSE vs non-streaming
	if req.Stream {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "Streaming unsupported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")

		chunks := []string{"Hello", " from", " ELMOS", " Native", " Inference", " Gateway!"}
		for i, chunk := range chunks {
			chunkData := map[string]any{
				"id":      fmt.Sprintf("chatcmpl-%d", time.Now().UnixNano()),
				"object":  "chat.completion.chunk",
				"created": time.Now().Unix(),
				"model":   req.Model,
				"choices": []map[string]any{
					{
						"index": 0,
						"delta": map[string]string{"content": chunk},
						"finish_reason": func() any {
							if i == len(chunks)-1 {
								return "stop"
							}
							return nil
						}(),
					},
				},
			}
			payload, _ := json.Marshal(chunkData)
			fmt.Fprintf(w, "data: %s\n\n", payload)
			flusher.Flush()
		}
		fmt.Fprintf(w, "data: [DONE]\n\n")
		flusher.Flush()

		gw.metrics.SuccessRequests.Add(1)
		gw.metrics.TotalTokens.Add(uint64(len(chunks)))
		gw.circuitBreaker.RecordSuccess()
		return
	}

	// Non-streaming JSON response
	resp := map[string]any{
		"id":      fmt.Sprintf("chatcmpl-%d", time.Now().UnixNano()),
		"object":  "chat.completion",
		"created": time.Now().Unix(),
		"model":   req.Model,
		"choices": []map[string]any{
			{
				"index": 0,
				"message": map[string]string{
					"role":    "assistant",
					"content": "ELMOS Native Inference Proxy received your request.",
				},
				"finish_reason": "stop",
			},
		},
		"usage": map[string]int{
			"prompt_tokens":     10,
			"completion_tokens": 12,
			"total_tokens":      22,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)

	gw.metrics.SuccessRequests.Add(1)
	gw.metrics.TotalTokens.Add(22)
	gw.circuitBreaker.RecordSuccess()
}

func (gw *InferenceGateway) handleEmbeddings(w http.ResponseWriter, r *http.Request) {
	gw.metrics.TotalRequests.Add(1)

	var req struct {
		Model string `json:"model"`
		Input any    `json:"input"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	resp := map[string]any{
		"object": "list",
		"data": []map[string]any{
			{
				"object":    "embedding",
				"index":     0,
				"embedding": []float32{0.0123, -0.0456, 0.0789, 0.0321},
			},
		},
		"model": req.Model,
		"usage": map[string]int{
			"prompt_tokens": 8,
			"total_tokens":  8,
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)

	gw.metrics.SuccessRequests.Add(1)
	gw.metrics.TotalTokens.Add(8)
	gw.circuitBreaker.RecordSuccess()
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8090"
	}

	gw := NewInferenceGateway(100.0, 50.0, 5, 10*time.Second)
	addr := ":" + port
	log.Printf("ELMOS Inference Gateway (Go Native 1.25) listening on %s\n", addr)
	if err := http.ListenAndServe(addr, gw); err != nil {
		log.Fatalf("Gateway server failed: %v", err)
	}
}
