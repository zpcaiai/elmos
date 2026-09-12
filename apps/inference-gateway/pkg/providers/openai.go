package providers

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// OpenAIAdapter implements ProviderAdapter for OpenAI compatible APIs.
type OpenAIAdapter struct {
	config ProviderConfig
	client *http.Client
}

func NewOpenAIAdapter(cfg ProviderConfig, client *http.Client) *OpenAIAdapter {
	if client == nil {
		client = &http.Client{Timeout: cfg.Timeout}
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "https://api.openai.com/v1"
	}
	return &OpenAIAdapter{
		config: cfg,
		client: client,
	}
}

func (a *OpenAIAdapter) Name() ProviderType {
	return ProviderOpenAI
}

func (a *OpenAIAdapter) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", a.config.BaseURL+"/models", nil)
	if err != nil {
		return err
	}
	if a.config.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+a.config.APIKey)
	}
	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return ParseHTTPError(resp)
	}
	return nil
}

func (a *OpenAIAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	start := time.Now()
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", a.config.BaseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if a.config.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+a.config.APIKey)
	}
	if a.config.Organization != "" {
		httpReq.Header.Set("OpenAI-Organization", a.config.Organization)
	}
	if a.config.Project != "" {
		httpReq.Header.Set("OpenAI-Project", a.config.Project)
	}
	if req.TraceID != "" {
		httpReq.Header.Set("X-Request-ID", req.TraceID)
	}

	resp, err := a.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, ParseHTTPError(resp)
	}

	var chatResp ChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return nil, fmt.Errorf("failed to decode OpenAI chat response: %w", err)
	}

	chatResp.Provider = ProviderOpenAI
	chatResp.LatencyMs = time.Since(start).Milliseconds()
	return &chatResp, nil
}

func (a *OpenAIAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	reqCopy := *req
	reqCopy.Stream = true

	payload, err := json.Marshal(reqCopy)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", a.config.BaseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	if a.config.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+a.config.APIKey)
	}
	if a.config.Organization != "" {
		httpReq.Header.Set("OpenAI-Organization", a.config.Organization)
	}
	if req.TraceID != "" {
		httpReq.Header.Set("X-Request-ID", req.TraceID)
	}

	resp, err := a.client.Do(httpReq)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return ParseHTTPError(resp)
	}

	reader := bufio.NewReader(resp.Body)
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		line, err := reader.ReadString('\n')
		if err != nil {
			break
		}

		trimmed := strings.TrimSpace(line)
		if trimmed == "" || strings.HasPrefix(trimmed, ":") {
			continue
		}

		if strings.HasPrefix(trimmed, "data: ") {
			data := strings.TrimPrefix(trimmed, "data: ")
			if data == "[DONE]" {
				break
			}

			var chunk ChatResponse
			if err := json.Unmarshal([]byte(data), &chunk); err != nil {
				continue
			}
			chunk.Provider = ProviderOpenAI
			if err := handler(&chunk); err != nil {
				return err
			}
		}
	}

	return nil
}

func (a *OpenAIAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	start := time.Now()
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", a.config.BaseURL+"/embeddings", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if a.config.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+a.config.APIKey)
	}

	resp, err := a.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, ParseHTTPError(resp)
	}

	var embResp EmbeddingResponse
	if err := json.NewDecoder(resp.Body).Decode(&embResp); err != nil {
		return nil, fmt.Errorf("failed to decode OpenAI embedding response: %w", err)
	}

	embResp.LatencyMs = time.Since(start).Milliseconds()
	return &embResp, nil
}
