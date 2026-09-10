package cache

import (
	"testing"
	"time"

	"io.elmos/inferencegateway/pkg/providers"
)

func TestPromptCacheOperations(t *testing.T) {
	cache := NewPromptCache(5, 500*time.Millisecond)

	req1 := &providers.ChatRequest{
		Model: "gpt-4o",
		Messages: []providers.Message{
			{Role: "system", Content: "You are an expert compiler engineer."},
			{Role: "user", Content: "Explain AST lowerings."},
		},
	}

	resp1 := &providers.ChatResponse{
		ID:    "resp-1",
		Model: "gpt-4o",
		Choices: []providers.ChatChoice{
			{Index: 0, Message: providers.Message{Role: "assistant", Content: "AST lowering converts high-level AST..."}},
		},
		Usage: providers.UsageMetrics{
			PromptTokens:     50,
			CompletionTokens: 20,
			TotalTokens:      70,
		},
	}

	// 1. Initial miss
	if _, hit := cache.Get(req1); hit {
		t.Fatal("expected cache miss initially")
	}

	// 2. Set
	cache.Set(req1, resp1)

	// 3. Hit
	cached, hit := cache.Get(req1)
	if !hit {
		t.Fatal("expected cache hit after Set")
	}
	if cached.Choices[0].Message.Content != resp1.Choices[0].Message.Content {
		t.Errorf("content mismatch")
	}
	if cached.Usage.CachedTokens != 50 {
		t.Errorf("expected 50 cached tokens, got %d", cached.Usage.CachedTokens)
	}

	// 4. Metrics
	metrics := cache.Metrics()
	if metrics.Hits != 1 || metrics.Misses != 1 {
		t.Errorf("unexpected metrics: %+v", metrics)
	}
	if metrics.TotalTokensSaved != 50 {
		t.Errorf("expected 50 saved tokens, got %d", metrics.TotalTokensSaved)
	}

	// 5. Expiration
	time.Sleep(600 * time.Millisecond)
	if _, hit := cache.Get(req1); hit {
		t.Fatal("expected cache miss after TTL expiration")
	}
}

func TestPromptCacheEviction(t *testing.T) {
	cache := NewPromptCache(2, 10*time.Second)

	makeReq := func(content string) *providers.ChatRequest {
		return &providers.ChatRequest{
			Model: "test-model",
			Messages: []providers.Message{
				{Role: "user", Content: content},
			},
		}
	}
	makeResp := func(id string) *providers.ChatResponse {
		return &providers.ChatResponse{
			ID: id,
			Choices: []providers.ChatChoice{
				{Index: 0, Message: providers.Message{Role: "assistant", Content: "response " + id}},
			},
		}
	}

	reqA := makeReq("A")
	reqB := makeReq("B")
	reqC := makeReq("C")

	cache.Set(reqA, makeResp("A"))
	cache.Set(reqB, makeResp("B"))

	// Access A to make B oldest
	cache.Get(reqA)

	// Set C, should evict B
	cache.Set(reqC, makeResp("C"))

	if _, hit := cache.Get(reqB); hit {
		t.Error("expected B to be evicted")
	}
	if _, hit := cache.Get(reqA); !hit {
		t.Error("expected A to remain in cache")
	}
	if _, hit := cache.Get(reqC); !hit {
		t.Error("expected C to be in cache")
	}

	metrics := cache.Metrics()
	if metrics.Evictions != 1 {
		t.Errorf("expected 1 eviction, got %d", metrics.Evictions)
	}
}
