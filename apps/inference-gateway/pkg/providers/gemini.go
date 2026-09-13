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

type GeminiAdapter struct {
	config ProviderConfig
	client *http.Client
}

func NewGeminiAdapter(cfg ProviderConfig, client *http.Client) *GeminiAdapter {
	if client == nil {
		client = &http.Client{Timeout: cfg.Timeout}
	}
	if cfg.BaseURL == "" {
		cfg.BaseURL = "https://generativelanguage.googleapis.com/v1beta"
	}
	return &GeminiAdapter{
		config: cfg,
		client: client,
	}
}

func (g *GeminiAdapter) Name() ProviderType {
	return ProviderGemini
}

func (g *GeminiAdapter) HealthCheck(ctx context.Context) error {
	url := fmt.Sprintf("%s/models?key=%s", g.config.BaseURL, g.config.APIKey)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return err
	}
	resp, err := g.client.Do(req)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return ParseHTTPError(resp)
	}
	return nil
}

func (g *GeminiAdapter) convertRequest(req *ChatRequest) map[string]interface{} {
	contents := make([]map[string]interface{}, 0, len(req.Messages))
	var systemInstruction *map[string]interface{}

	for _, msg := range req.Messages {
		if msg.Role == "system" {
			inst := map[string]interface{}{
				"parts": []map[string]interface{}{{"text": msg.Content}},
			}
			systemInstruction = &inst
			continue
		}

		role := "user"
		if msg.Role == "assistant" {
			role = "model"
		}

		contents = append(contents, map[string]interface{}{
			"role": role,
			"parts": []map[string]interface{}{
				{"text": msg.Content},
			},
		})
	}

	generationConfig := map[string]interface{}{}
	if req.Temperature != nil {
		generationConfig["temperature"] = *req.Temperature
	}
	if req.TopP != nil {
		generationConfig["topP"] = *req.TopP
	}
	if req.MaxTokens > 0 {
		generationConfig["maxOutputTokens"] = req.MaxTokens
	}

	payload := map[string]interface{}{
		"contents": contents,
	}
	if systemInstruction != nil {
		payload["systemInstruction"] = *systemInstruction
	}
	if len(generationConfig) > 0 {
		payload["generationConfig"] = generationConfig
	}

	return payload
}

func (g *GeminiAdapter) ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error) {
	start := time.Now()
	cleanModel := strings.TrimPrefix(req.Model, "gemini/")
	url := fmt.Sprintf("%s/models/%s:generateContent?key=%s", g.config.BaseURL, cleanModel, g.config.APIKey)

	payloadMap := g.convertRequest(req)
	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(payloadBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, ParseHTTPError(resp)
	}

	var geminiResp struct {
		Candidates []struct {
			Content struct {
				Parts []struct {
					Text string `json:"text"`
				} `json:"parts"`
				Role string `json:"role"`
			} `json:"content"`
			FinishReason string `json:"finishReason"`
		} `json:"candidates"`
		UsageMetadata struct {
			PromptTokenCount     int `json:"promptTokenCount"`
			CandidatesTokenCount int `json:"candidatesTokenCount"`
			TotalTokenCount      int `json:"totalTokenCount"`
		} `json:"usageMetadata"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&geminiResp); err != nil {
		return nil, fmt.Errorf("failed to decode Gemini response: %w", err)
	}

	var textBuilder strings.Builder
	if len(geminiResp.Candidates) > 0 {
		for _, part := range geminiResp.Candidates[0].Content.Parts {
			textBuilder.WriteString(part.Text)
		}
	}

	return &ChatResponse{
		ID:        fmt.Sprintf("gemini-%d", time.Now().UnixNano()),
		Object:    "chat.completion",
		Created:   time.Now().Unix(),
		Model:     req.Model,
		Provider:  ProviderGemini,
		LatencyMs: time.Since(start).Milliseconds(),
		Choices: []ChatChoice{
			{
				Index: 0,
				Message: Message{
					Role:    "assistant",
					Content: textBuilder.String(),
				},
				FinishReason: "stop",
			},
		},
		Usage: UsageMetrics{
			PromptTokens:     geminiResp.UsageMetadata.PromptTokenCount,
			CompletionTokens: geminiResp.UsageMetadata.CandidatesTokenCount,
			TotalTokens:      geminiResp.UsageMetadata.TotalTokenCount,
		},
	}, nil
}

func (g *GeminiAdapter) ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error {
	cleanModel := strings.TrimPrefix(req.Model, "gemini/")
	url := fmt.Sprintf("%s/models/%s:streamGenerateContent?alt=sse&key=%s", g.config.BaseURL, cleanModel, g.config.APIKey)

	payloadMap := g.convertRequest(req)
	payloadBytes, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(payloadBytes))
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(httpReq)
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
			var chunkResp struct {
				Candidates []struct {
					Content struct {
						Parts []struct {
							Text string `json:"text"`
						} `json:"parts"`
					} `json:"content"`
				} `json:"candidates"`
			}
			if err := json.Unmarshal([]byte(data), &chunkResp); err != nil {
				continue
			}

			if len(chunkResp.Candidates) > 0 {
				for _, part := range chunkResp.Candidates[0].Content.Parts {
					if part.Text != "" {
						chunk := &ChatResponse{
							Object:   "chat.completion.chunk",
							Created:  time.Now().Unix(),
							Model:    req.Model,
							Provider: ProviderGemini,
							Choices: []ChatChoice{
								{
									Index: 0,
									Delta: &Message{
										Role:    "assistant",
										Content: part.Text,
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
		}
	}

	return nil
}

func (g *GeminiAdapter) CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error) {
	start := time.Now()
	cleanModel := strings.TrimPrefix(req.Model, "gemini/")
	if cleanModel == "" {
		cleanModel = "text-embedding-004"
	}
	url := fmt.Sprintf("%s/models/%s:batchEmbedContents?key=%s", g.config.BaseURL, cleanModel, g.config.APIKey)

	requests := make([]map[string]interface{}, len(req.Input))
	for i, text := range req.Input {
		requests[i] = map[string]interface{}{
			"model": fmt.Sprintf("models/%s", cleanModel),
			"content": map[string]interface{}{
				"parts": []map[string]interface{}{{"text": text}},
			},
		}
	}

	payloadBytes, err := json.Marshal(map[string]interface{}{"requests": requests})
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidRequest, err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(payloadBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := g.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrProviderUnavailable, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, ParseHTTPError(resp)
	}

	var batchResp struct {
		Embeddings []struct {
			Values []float64 `json:"values"`
		} `json:"embeddings"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&batchResp); err != nil {
		return nil, fmt.Errorf("failed to decode Gemini embedding: %w", err)
	}

	result := &EmbeddingResponse{
		Object:    "list",
		Model:     req.Model,
		LatencyMs: time.Since(start).Milliseconds(),
		Data:      make([]EmbeddingObject, len(batchResp.Embeddings)),
	}

	for i, emb := range batchResp.Embeddings {
		result.Data[i] = EmbeddingObject{
			Index:     i,
			Embedding: emb.Values,
			Object:    "embedding",
		}
	}

	return result, nil
}
