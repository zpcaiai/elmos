package providers

import (
	"context"
	"net/http"
)

type LiteLLMAdapter struct {
	openAIAdapter *OpenAIAdapter
}

func NewLiteLLMAdapter(cfg ProviderConfig, client *http.Client) *LiteLLMAdapter {
	if cfg.BaseURL == "" {
		cfg.BaseURL = "http://localhost:4000/v1"
	}
	return &LiteLLMAdapter{
		openAIAdapter: NewOpenAIAdapter(cfg, client),
	}
}

func (l *LiteLLMAdapter) Name() ProviderType {
	return ProviderLiteLLM
}

func (l *LiteLLMAdapter) HealthCheck(ctx context.Context) error {
	return l.openAIAdapter.HealthCheck(ctx)
}

func (l *LiteLLMAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	resp, err := l.openAIAdapter.ChatCompletion(ctx, req)
	if err != nil {
		return nil, err
	}
	resp.Provider = ProviderLiteLLM
	return resp, nil
}

func (l *LiteLLMAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	return l.openAIAdapter.ChatCompletionStream(ctx, req, func(chunk *ChatResponse) error {
		chunk.Provider = ProviderLiteLLM
		return handler(chunk)
	})
}

func (l *LiteLLMAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	return l.openAIAdapter.CreateEmbeddings(ctx, req)
}
