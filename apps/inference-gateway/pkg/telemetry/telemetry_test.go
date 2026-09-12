package telemetry

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestMetricsCollector(t *testing.T) {
	collector := NewMetricsCollector()

	collector.IncActive()
	collector.RecordRequest("openai", "gpt-4o", http.StatusOK, 250*time.Millisecond, 100, 50)
	collector.RecordRequest("anthropic", "claude-3-5", http.StatusOK, 180*time.Millisecond, 80, 40)
	collector.RecordRequest("openai", "gpt-4o", http.StatusTooManyRequests, 10*time.Millisecond, 0, 0)
	collector.DecActive()

	req := httptest.NewRequest("GET", "/metrics", nil)
	rec := httptest.NewRecorder()
	collector.ServeHTTP(rec, req)

	body := rec.Body.String()

	if !strings.Contains(body, "llm_gateway_active_requests 0") {
		t.Errorf("expected active requests 0, got: %s", body)
	}
	if !strings.Contains(body, `llm_gateway_requests_total{provider="openai",model="gpt-4o",status="200"} 1`) {
		t.Errorf("expected openai 200 metric, got: %s", body)
	}
	if !strings.Contains(body, `llm_gateway_tokens_total{provider="openai",model="gpt-4o",type="prompt"} 100`) {
		t.Errorf("expected prompt tokens 100, got: %s", body)
	}
}
