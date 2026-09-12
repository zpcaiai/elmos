package providers

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

type MockAdapter struct {
	injectedError error
	streamDelay   time.Duration
}

func NewMockAdapter() *MockAdapter {
	return &MockAdapter{}
}

func (m *MockAdapter) SetInjectedError(err error) {
	m.injectedError = err
}

func (m *MockAdapter) SetStreamDelay(d time.Duration) {
	m.streamDelay = d
}

func (m *MockAdapter) Name() ProviderType {
	return ProviderMock
}

func (m *MockAdapter) HealthCheck(ctx context.Context) error {
	return m.injectedError
}

func (m *MockAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	if m.injectedError != nil {
		return nil, m.injectedError
	}

	prompt := ""
	for _, msg := range req.Messages {
		prompt += msg.Content + "\n"
	}

	hash := sha256.Sum256([]byte(prompt))
	hashStr := hex.EncodeToString(hash[:8])

	reply := fmt.Sprintf("[MOCK RESPONSE: model=%s, digest=%s] Successfully processed %d messages.", req.Model, hashStr, len(req.Messages))

	promptTokens := len(prompt) / 4
	if promptTokens < 1 {
		promptTokens = 10
	}
	completionTokens := len(reply) / 4
	if completionTokens < 1 {
		completionTokens = 15
	}

	return &ChatResponse{
		ID:        fmt.Sprintf("mock-%s", hashStr),
		Object:    "chat.completion",
		Created:   time.Now().Unix(),
		Model:     req.Model,
		Provider:  ProviderMock,
		LatencyMs: 5,
		Choices: []ChatChoice{
			{
				Index: 0,
				Message: Message{
					Role:    "assistant",
					Content: reply,
				},
				FinishReason: "stop",
			},
		},
		Usage: UsageMetrics{
			PromptTokens:     promptTokens,
			CompletionTokens: completionTokens,
			TotalTokens:      promptTokens + completionTokens,
		},
	}, nil
}

func (m *MockAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	if m.injectedError != nil {
		return m.injectedError
	}

	fullText := fmt.Sprintf("[MOCK STREAM: model=%s] Output token stream simulation.", req.Model)
	words := strings.Split(fullText, " ")

	for idx, word := range words {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if m.streamDelay > 0 {
			time.Sleep(m.streamDelay)
		}

		suffix := " "
		if idx == len(words)-1 {
			suffix = ""
		}

		chunk := &ChatResponse{
			Object:   "chat.completion.chunk",
			Created:  time.Now().Unix(),
			Model:    req.Model,
			Provider: ProviderMock,
			Choices: []ChatChoice{
				{
					Index: 0,
					Delta: &Message{
						Role:    "assistant",
						Content: word + suffix,
					},
				},
			},
		}
		if err := handler(chunk); err != nil {
			return err
		}
	}

	return nil
}

func (m *MockAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	if m.injectedError != nil {
		return nil, m.injectedError
	}

	data := make([]EmbeddingObject, len(req.Input))
	for i, text := range req.Input {
		// Generate deterministic 8-dimensional mock embedding
		h := sha256.Sum256([]byte(text))
		emb := make([]float64, 8)
		for j := 0; j < 8; j++ {
			emb[j] = float64(h[j]) / 255.0
		}
		data[i] = EmbeddingObject{
			Index:     i,
			Embedding: emb,
			Object:    "embedding",
		}
	}

	return &EmbeddingResponse{
		Object:    "list",
		Model:     req.Model,
		Data:      data,
		LatencyMs: 2,
		Usage: UsageMetrics{
			PromptTokens: len(req.Input) * 5,
			TotalTokens:  len(req.Input) * 5,
		},
	}, nil
}
