package providers

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestMockAdapterExecution(t *testing.T) {
	mock := NewMockAdapter()
	req := &ChatRequest{
		Model: "mock-general-v1",
		Messages: []Message{
			{Role: "user", Content: "Hello world testing mock execution"},
		},
		MaxTokens: 50,
	}

	ctx := context.Background()
	resp, err := mock.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp == nil {
		t.Fatal("expected non-nil response")
	}
	if len(resp.Choices) == 0 {
		t.Fatal("expected at least 1 choice")
	}
	if resp.Usage.TotalTokens <= 0 {
		t.Errorf("expected positive total tokens, got %d", resp.Usage.TotalTokens)
	}

	// Test streaming
	var streamedWords int
	err = mock.ChatCompletionStream(ctx, req, func(chunk *ChatResponse) error {
		if len(chunk.Choices) > 0 && chunk.Choices[0].Delta != nil {
			streamedWords++
		}
		return nil
	})
	if err != nil {
		t.Fatalf("streaming error: %v", err)
	}
	if streamedWords == 0 {
		t.Errorf("expected streamed chunks, got %d", streamedWords)
	}

	// Test embeddings
	embReq := &EmbeddingRequest{
		Model: "mock-emb-v1",
		Input: []string{"test text 1", "test text 2"},
	}
	embResp, err := mock.CreateEmbeddings(ctx, embReq)
	if err != nil {
		t.Fatalf("embeddings error: %v", err)
	}
	if len(embResp.Data) != 2 {
		t.Errorf("expected 2 embeddings, got %d", len(embResp.Data))
	}
	if len(embResp.Data[0].Embedding) != 8 {
		t.Errorf("expected 8 dimensions, got %d", len(embResp.Data[0].Embedding))
	}
}

func TestOpenAIAdapterMockServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/chat/completions" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{
				"id": "chatcmpl-test",
				"object": "chat.completion",
				"created": 1700000000,
				"model": "gpt-4o",
				"choices": [{
					"index": 0,
					"message": {"role": "assistant", "content": "mock openai response"},
					"finish_reason": "stop"
				}],
				"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
			}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()

	cfg := ProviderConfig{
		Type:    ProviderOpenAI,
		BaseURL: server.URL,
		APIKey:  "sk-test-key",
		Timeout: 5 * time.Second,
	}
	adapter := NewOpenAIAdapter(cfg, server.Client())

	ctx := context.Background()
	req := &ChatRequest{
		Model: "gpt-4o",
		Messages: []Message{
			{Role: "user", Content: "Hello OpenAI"},
		},
	}
	resp, err := adapter.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Choices[0].Message.Content != "mock openai response" {
		t.Errorf("unexpected content: %s", resp.Choices[0].Message.Content)
	}
	if resp.Usage.TotalTokens != 15 {
		t.Errorf("expected 15 total tokens, got %d", resp.Usage.TotalTokens)
	}
}

func TestAnthropicAdapterMockServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/messages" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{
				"id": "msg_test",
				"type": "message",
				"role": "assistant",
				"model": "claude-3-5-sonnet",
				"content": [{"type": "text", "text": "mock anthropic response"}],
				"stop_reason": "end_turn",
				"usage": {"input_tokens": 12, "output_tokens": 8}
			}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()

	cfg := ProviderConfig{
		Type:    ProviderAnthropic,
		BaseURL: server.URL,
		APIKey:  "test-anthropic-key",
		Timeout: 5 * time.Second,
	}
	adapter := NewAnthropicAdapter(cfg, server.Client())

	ctx := context.Background()
	req := &ChatRequest{
		Model: "claude-3-5-sonnet",
		Messages: []Message{
			{Role: "user", Content: "Hello Claude"},
		},
	}
	resp, err := adapter.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Choices[0].Message.Content != "mock anthropic response" {
		t.Errorf("unexpected content: %s", resp.Choices[0].Message.Content)
	}
	if resp.Usage.PromptTokens != 12 || resp.Usage.CompletionTokens != 8 {
		t.Errorf("unexpected tokens: %+v", resp.Usage)
	}
}

func TestGeminiAdapterMockServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{
				"candidates": [{
					"content": {
						"parts": [{"text": "mock gemini response"}],
						"role": "model"
					},
					"finishReason": "STOP"
				}],
				"usageMetadata": {
					"promptTokenCount": 20,
					"candidatesTokenCount": 10,
					"totalTokenCount": 30
				}
			}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()

	cfg := ProviderConfig{
		Type:    ProviderGemini,
		BaseURL: server.URL,
		APIKey:  "test-gemini-key",
		Timeout: 5 * time.Second,
	}
	adapter := NewGeminiAdapter(cfg, server.Client())

	ctx := context.Background()
	req := &ChatRequest{
		Model: "gemini-1.5-pro",
		Messages: []Message{
			{Role: "user", Content: "Hello Gemini"},
		},
	}
	resp, err := adapter.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Choices[0].Message.Content != "mock gemini response" {
		t.Errorf("unexpected content: %s", resp.Choices[0].Message.Content)
	}
	if resp.Usage.TotalTokens != 30 {
		t.Errorf("unexpected tokens: %+v", resp.Usage)
	}
}

func TestDeepSeekAdapterMockServer(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/chat/completions" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`{
				"id": "deepseek-test",
				"object": "chat.completion",
				"created": 1700000000,
				"model": "deepseek-reasoner",
				"choices": [{
					"index": 0,
					"message": {
						"role": "assistant",
						"content": "final answer",
						"reasoning_content": "step by step deduction"
					},
					"finish_reason": "stop"
				}],
				"usage": {
					"prompt_tokens": 15,
					"completion_tokens": 25,
					"total_tokens": 40,
					"completion_tokens_details": {"reasoning_tokens": 20}
				}
			}`))
			return
		}
		http.NotFound(w, r)
	}))
	defer server.Close()

	cfg := ProviderConfig{
		Type:    ProviderDeepSeek,
		BaseURL: server.URL,
		APIKey:  "test-deepseek-key",
		Timeout: 5 * time.Second,
	}
	adapter := NewDeepSeekAdapter(cfg, server.Client())

	ctx := context.Background()
	req := &ChatRequest{
		Model: "deepseek-reasoner",
		Messages: []Message{
			{Role: "user", Content: "Solve this math problem"},
		},
	}
	resp, err := adapter.ChatCompletion(ctx, req)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if resp.Usage.ReasoningTokens != 20 {
		t.Errorf("expected 20 reasoning tokens, got %d", resp.Usage.ReasoningTokens)
	}
	if len(resp.Choices) == 0 || resp.Choices[0].Message.Content == "" {
		t.Fatal("expected non-empty message content")
	}
}
