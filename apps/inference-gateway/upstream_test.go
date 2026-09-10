package main

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestResolveProvider(t *testing.T) {
	router := NewUpstreamRouter()

	tests := []struct {
		model    string
		auth     string
		expected Provider
	}{
		{"openai/gpt-4o", "Bearer test-key", ProviderOpenAI},
		{"anthropic/claude-3-5-sonnet", "Bearer test-key", ProviderAnthropic},
		{"claude-3-opus", "Bearer test-key", ProviderAnthropic},
		{"gemini-2.5-pro", "Bearer test-key", ProviderGemini},
		{"google/gemini-flash", "Bearer test-key", ProviderGemini},
		{"deepseek-chat", "Bearer test-key", ProviderDeepSeek},
		{"litellm/local-model", "", ProviderLiteLLM},
		{"unknown-model-no-key", "", ProviderRehearsal},
	}

	for _, tc := range tests {
		p, _ := router.ResolveProvider(tc.model, tc.auth)
		if p != tc.expected {
			t.Errorf("model %q: expected provider %v, got %v", tc.model, tc.expected, p)
		}
	}
}

func TestForwardChatRequestToMockUpstream(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer test-secret" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"choices":[{"message":{"content":"response from mock upstream"}}]}`))
	}))
	defer server.Close()

	router := NewUpstreamRouter()
	cfg := UpstreamConfig{
		BaseURL: server.URL,
		APIKey:  "test-secret",
		Timeout: 5 * time.Second,
	}

	resp, err := router.ForwardChatRequest(context.Background(), ProviderOpenAI, cfg, []byte(`{"model":"gpt-4"}`), false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected status 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if len(body) == 0 {
		t.Fatalf("expected non-empty body")
	}
}
