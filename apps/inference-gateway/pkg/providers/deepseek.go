package providers

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type DeepSeekAdapter struct {
	config ProviderConfig
	client *http.Client
}

func NewDeepSeekAdapter(cfg ProviderConfig, client *http.Client) *DeepSeekAdapter {
	if client == nil {
		client = &http.Client{Timeout: cfg.Timeout}
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "https://api.deepseek.com/v1"
	}
	return &DeepSeekAdapter{
		config: cfg,
		client: client,
	}
}

func (d *DeepSeekAdapter) Name() ProviderType {
	return ProviderDeepSeek
}

func (d *DeepSeekAdapter) HealthCheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", d.config.BaseURL+"/models", nil)
	if err != nil {
		return err
	}
	if d.config.APIKey != "" {
		req.Header.Set("Authorization", "Bearer "+d.config.APIKey)
	}
	resp, err := d.client.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return ParseHTTPError(resp)
	}
	return nil
}

func (d *DeepSeekAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	start := time.Now()
	payload, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", d.config.BaseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	if d.config.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+d.config.APIKey)
	}

	resp, err := d.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, ParseHTTPError(resp)
	}

	var rawResp struct {
		ID      string `json:"id"`
		Object  string `json:"object"`
		Created int64  `json:"created"`
		Model   string `json:"model"`
		Choices []struct {
			Index   int `json:"index"`
			Message struct {
				Role             string     `json:"role"`
				Content          string     `json:"content"`
				ReasoningContent string     `json:"reasoning_content,omitempty"`
				ToolCalls        []ToolCall `json:"tool_calls,omitempty"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Usage struct {
			PromptTokens          int `json:"prompt_tokens"`
			CompletionTokens      int `json:"completion_tokens"`
			TotalTokens           int `json:"total_tokens"`
			PromptTokensDetails   struct {
				CachedTokens int `json:"cached_tokens"`
			} `json:"prompt_tokens_details"`
			CompletionTokensDetails struct {
				ReasoningTokens int `json:"reasoning_tokens"`
			} `json:"completion_tokens_details"`
		} `json:"usage"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&rawResp); err != nil {
		return nil, fmt.Errorf("failed to decode DeepSeek response: %w", err)
	}

	choices := make([]ChatChoice, len(rawResp.Choices))
	for i, c := range rawResp.Choices {
		content := c.Message.Content
		if c.Message.ReasoningContent != "" {
			// Prefix with thought tags if reasoning content is present
			content = fmt.Sprintf("<think>\n%s\n</think>\n%s", c.Message.ReasoningContent, content)
		}
		choices[i] = ChatChoice{
			Index: c.Index,
			Message: Message{
				Role:      c.Message.Role,
				Content:   content,
				ToolCalls: c.Message.ToolCalls,
			},
			FinishReason: c.FinishReason,
		}
	}

	return &ChatResponse{
		ID:        rawResp.ID,
		Object:    rawResp.Object,
		Created:   rawResp.Created,
		Model:     rawResp.Model,
		Choices:   choices,
		Provider:  ProviderDeepSeek,
		LatencyMs: time.Since(start).Milliseconds(),
		Usage: UsageMetrics{
			PromptTokens:     rawResp.Usage.PromptTokens,
			CompletionTokens: rawResp.Usage.CompletionTokens,
			TotalTokens:      rawResp.Usage.TotalTokens,
			ReasoningTokens:  rawResp.Usage.CompletionTokensDetails.ReasoningTokens,
			CachedTokens:     rawResp.Usage.PromptTokensDetails.CachedTokens,
		},
	}, nil
}

func (d *DeepSeekAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	reqCopy := *req
	reqCopy.Stream = true

	payload, err := json.Marshal(reqCopy)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", d.config.BaseURL+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	if d.config.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+d.config.APIKey)
	}

	resp, err := d.client.Do(httpReq)
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
			chunk.Provider = ProviderDeepSeek
			if err := handler(&chunk); err != nil {
				return err
			}
		}
	}

	return nil
}

func (d *DeepSeekAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	return nil, errors.New("deepseek does not provide dedicated embeddings endpoints")
}
