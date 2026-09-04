package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestHealthEndpoint(t *testing.T) {
	gw := NewInferenceGateway(100.0, 50.0, 5, 1*time.Second)
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	rr := httptest.NewRecorder()

	gw.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var resp map[string]any
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp["status"] != "UP" {
		t.Errorf("expected status UP, got %v", resp["status"])
	}
	if resp["circuitBreaker"] != "CLOSED" {
		t.Errorf("expected circuitBreaker CLOSED, got %v", resp["circuitBreaker"])
	}
}

func TestMetricsEndpoint(t *testing.T) {
	gw := NewInferenceGateway(100.0, 50.0, 5, 1*time.Second)
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	rr := httptest.NewRecorder()

	gw.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var resp map[string]any
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if _, ok := resp["totalRequests"]; !ok {
		t.Errorf("expected totalRequests in metrics")
	}
}

func TestChatCompletionsNonStreaming(t *testing.T) {
	gw := NewInferenceGateway(100.0, 50.0, 5, 1*time.Second)

	body := `{"model":"mock-llm","messages":[{"role":"user","content":"hello"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	gw.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", rr.Code, rr.Body.String())
	}

	var resp map[string]any
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to parse json response: %v", err)
	}

	choices, ok := resp["choices"].([]any)
	if !ok || len(choices) == 0 {
		t.Fatalf("expected choices in response")
	}
}

func TestChatCompletionsStreaming(t *testing.T) {
	gw := NewInferenceGateway(100.0, 50.0, 5, 1*time.Second)

	body := `{"model":"mock-llm","stream":true,"messages":[{"role":"user","content":"hello stream"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	gw.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	contentType := rr.Header().Get("Content-Type")
	if !strings.HasPrefix(contentType, "text/event-stream") {
		t.Errorf("expected Content-Type text/event-stream, got %s", contentType)
	}

	bodyStr := rr.Body.String()
	if !strings.Contains(bodyStr, "data: [DONE]") {
		t.Errorf("expected stream to contain data: [DONE]")
	}
	if !strings.Contains(bodyStr, "chat.completion.chunk") {
		t.Errorf("expected stream to contain chat.completion.chunk")
	}
}

func TestEmbeddings(t *testing.T) {
	gw := NewInferenceGateway(100.0, 50.0, 5, 1*time.Second)

	body := `{"model":"text-embedding-3-small","input":"test string"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/embeddings", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	gw.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var resp map[string]any
	if err := json.NewDecoder(rr.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if resp["object"] != "list" {
		t.Errorf("expected object list, got %v", resp["object"])
	}
}

func TestRateLimiter(t *testing.T) {
	// Capacity 1 token, refill 0 tokens/sec
	gw := NewInferenceGateway(1.0, 0.0, 5, 1*time.Second)

	body := `{"model":"mock-llm","messages":[{"role":"user","content":"test"}]}`

	// First request succeeds
	req1 := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", bytes.NewBufferString(body))
	rr1 := httptest.NewRecorder()
	gw.ServeHTTP(rr1, req1)
	if rr1.Code != http.StatusOK {
		t.Fatalf("first request expected 200, got %d", rr1.Code)
	}

	// Second request should be rate limited (429)
	req2 := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", bytes.NewBufferString(body))
	rr2 := httptest.NewRecorder()
	gw.ServeHTTP(rr2, req2)
	if rr2.Code != http.StatusTooManyRequests {
		t.Fatalf("second request expected 429, got %d", rr2.Code)
	}
}

func TestCircuitBreaker(t *testing.T) {
	// Threshold 2 failures, cooldown 50ms
	cb := NewCircuitBreaker(2, 50*time.Millisecond)

	if !cb.AllowRequest() {
		t.Errorf("expected request to be allowed initially")
	}

	cb.RecordFailure()
	if cb.GetState() != "CLOSED" {
		t.Errorf("expected state CLOSED after 1 failure, got %s", cb.GetState())
	}

	cb.RecordFailure() // Hits threshold 2 -> trips to OPEN
	if cb.GetState() != "OPEN" {
		t.Errorf("expected state OPEN after 2 failures, got %s", cb.GetState())
	}

	if cb.AllowRequest() {
		t.Errorf("expected request to be blocked while OPEN")
	}

	// Wait for cooldown
	time.Sleep(60 * time.Millisecond)

	// Half-open check
	if !cb.AllowRequest() {
		t.Errorf("expected request to be allowed after cooldown (HALF_OPEN)")
	}
	if cb.GetState() != "HALF_OPEN" {
		t.Errorf("expected state HALF_OPEN, got %s", cb.GetState())
	}

	// Success restores closed
	cb.RecordSuccess()
	if cb.GetState() != "CLOSED" {
		t.Errorf("expected state CLOSED after success, got %s", cb.GetState())
	}
}
