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

type AnthropicAdapter struct {
	config     ProviderConfig
	client     *http.Client
	apiVersion string
}

func NewAnthropicAdapter(cfg ProviderConfig, client *http.Client) *AnthropicAdapter {
	if client == nil {
		client = &http.Client{Timeout: cfg.Timeout}
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "https://api.anthropic.com/v1"
	}
	return &AnthropicAdapter{
		config:     cfg,
		client:     client,
		apiVersion: "2023-06-01",
	}
}

func (a *AnthropicAdapter) Name() ProviderType {
	return ProviderAnthropic
}

func (a *AnthropicAdapter) HealthCheck(ctx context.Context) error {
	// Anthropic has no /models GET endpoint, verify auth/connectivity via head of base
	req, err := http.NewRequestWithContext(ctx, "GET", a.config.BaseURL+"/messages", nil)
	if err != nil {
		return err
	}
	req.Header.Set("x-api-key", a.config.APIKey)
	req.Header.Set("anthropic-version", a.apiVersion)
	resp, err := a.client.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()
	// Method not allowed (405) means server is healthy and endpoint exists
	if resp.StatusCode == http.StatusMethodNotAllowed || resp.StatusCode == http.StatusOK {
		return nil
	}
	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return ErrProviderAuthFailed
	}
	return nil
}

// Translate standard messages to Anthropic format
func (a *AnthropicAdapter) convertRequest(req *ChatRequest) map[string]interface{} {
	var systemPrompt string
	anthropicMsgs := make([]map[string]interface{}, 0, len(req.Messages))

	for _, msg := range req.Messages {
		if msg.Role == "system" {
			if systemPrompt != "" {
				systemPrompt += "\n\n" + msg.Content
			} else {
				systemPrompt = msg.Content
			}
			continue
		}

		role := msg.Role
		if role != "user" && role != "assistant" {
			role = "user"
		}

		anthropicMsgs = append(anthropicMsgs, map[string]interface{}{
			"role":    role,
			"content": msg.Content,
		})
	}

	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 4096
	}

	payload := map[string]interface{}{
		"model":      req.Model,
		"messages":   anthropicMsgs,
		"max_tokens": maxTokens,
	}

	if systemPrompt != "" {
		payload["system"] = systemPrompt
	}
	if req.Temperature != nil {
		payload["temperature"] = *req.Temperature
	}
	if req.TopP != nil {
		payload["top_p"] = *req.TopP
	}

	// Tool mapping if provided
	if len(req.Tools) > 0 {
		anthropicTools := make([]map[string]interface{}, len(req.Tools))
		for i, t := range req.Tools {
			anthropicTools[i] = map[string]interface{}{
				"name":        t.Function.Name,
				"description": t.Function.Description,
				"input_schema": t.Function.Parameters,
			}
		}
		payload["tools"] = anthropicTools
	}

	return payload
}

func (a *AnthropicAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	start := time.Now()
	payloadMap := a.convertRequest(req)
	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", a.config.BaseURL+"/messages", bytes.NewReader(payloadBytes))
	if err != nil {
		return nil, err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", a.config.APIKey)
	httpReq.Header.Set("anthropic-version", a.apiVersion)
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

	var anthropicResp struct {
		ID      string `json:"id"`
		Type    string `json:"type"`
		Role    string `json:"role"`
		Model   string `json:"model"`
		Content []struct {
			Type  string `json:"type"`
			Text  string `json:"text,omitempty"`
			ID    string `json:"id,omitempty"`
			Name  string `json:"name,omitempty"`
			Input map[string]interface{} `json:"input,omitempty"`
		} `json:"content"`
		StopReason string `json:"stop_reason"`
		Usage      struct {
			InputTokens  int `json:"input_tokens"`
			OutputTokens int `json:"output_tokens"`
		} `json:"usage"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&anthropicResp); err != nil {
		return nil, fmt.Errorf("failed to decode Anthropic response: %w", err)
	}

	var combinedText strings.Builder
	var toolCalls []ToolCall

	for _, item := range anthropicResp.Content {
		if item.Type == "text" {
			combinedText.WriteString(item.Text)
		} else if item.Type == "tool_use" {
			argBytes, _ := json.Marshal(item.Input)
			toolCalls = append(toolCalls, ToolCall{
				ID:   item.ID,
				Type: "function",
				Function: FunctionCall{
					Name:      item.Name,
					Arguments: string(argBytes),
				},
			})
		}
	}

	finishReason := "stop"
	if anthropicResp.StopReason == "tool_use" {
		finishReason = "tool_calls"
	} else if anthropicResp.StopReason == "max_tokens" {
		finishReason = "length"
	}

	res := &ChatResponse{
		ID:        anthropicResp.ID,
		Object:    "chat.completion",
		Created:   time.Now().Unix(),
		Model:     anthropicResp.Model,
		Provider:  ProviderAnthropic,
		LatencyMs: time.Since(start).Milliseconds(),
		Choices: []ChatChoice{
			{
				Index: 0,
				Message: Message{
					Role:      "assistant",
					Content:   combinedText.String(),
					ToolCalls: toolCalls,
				},
				FinishReason: finishReason,
			},
		},
		Usage: UsageMetrics{
			PromptTokens:     anthropicResp.Usage.InputTokens,
			CompletionTokens: anthropicResp.Usage.OutputTokens,
			TotalTokens:      anthropicResp.Usage.InputTokens + anthropicResp.Usage.OutputTokens,
		},
	}

	return res, nil
}

func (a *AnthropicAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	payloadMap := a.convertRequest(req)
	payloadMap["stream"] = true

	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", a.config.BaseURL+"/messages", bytes.NewReader(payloadBytes))
	if err != nil {
		return err
	}

	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	httpReq.Header.Set("x-api-key", a.config.APIKey)
	httpReq.Header.Set("anthropic-version", a.apiVersion)

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
		if strings.HasPrefix(trimmed, "data: ") {
			data := strings.TrimPrefix(trimmed, "data: ")
			var event struct {
				Type  string `json:"type"`
				Delta struct {
					Type string `json:"type"`
					Text string `json:"text"`
				} `json:"delta"`
			}
			if err := json.Unmarshal([]byte(data), &event); err != nil {
				continue
			}

			if event.Type == "content_block_delta" && event.Delta.Text != "" {
				chunk := &ChatResponse{
					Object:   "chat.completion.chunk",
					Created:  time.Now().Unix(),
					Model:    req.Model,
					Provider: ProviderAnthropic,
					Choices: []ChatChoice{
						{
							Index: 0,
							Delta: &Message{
								Role:    "assistant",
								Content: event.Delta.Text,
							},
						},
					},
				}
				if err := handler(chunk); err != nil {
					return err
				}
			}
		}
	}

	return nil
}

func (a *AnthropicAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	return nil, errors.New("anthropic does not provide a native vector embeddings endpoint")
}
