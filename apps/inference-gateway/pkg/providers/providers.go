package providers

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Standard Provider Error Types
var (
	ErrProviderRateLimit   = errors.New("upstream provider rate limit exceeded")
	ErrProviderAuthFailed  = errors.New("upstream provider authentication failed")
	ErrProviderUnavailable = errors.New("upstream provider temporarily unavailable")
	ErrModelNotFound       = errors.New("requested model not found on upstream provider")
	ErrInvalidRequest      = errors.New("invalid request payload or schema")
	ErrContextExceeded     = errors.New("context length exceeded model limit")
)

// ProviderType represents supported LLM backends.
type ProviderType string

const (
	ProviderOpenAI    ProviderType = "openai"
	ProviderAnthropic ProviderType = "anthropic"
	ProviderGemini    ProviderType = "gemini"
	ProviderDeepSeek  ProviderType = "deepseek"
	ProviderLiteLLM   ProviderType = "litellm"
	ProviderMock      ProviderType = "mock"
)

// Message represents a standardized chat message across providers.
type Message struct {
	Role       string     `json:"role"`
	Content    string     `json:"content"`
	Name       string     `json:"name,omitempty"`
	ToolCalls  []ToolCall `json:"tool_calls,omitempty"`
	ToolCallID string     `json:"tool_call_id,omitempty"`
}

// ToolCall represents a standardized tool or function invocation.
type ToolCall struct {
	ID       string       `json:"id"`
	Type     string       `json:"type"`
	Function FunctionCall `json:"function"`
}

// FunctionCall contains the function name and JSON arguments.
type FunctionCall struct {
	Name      string `json:"name"`
	Arguments string `json:"arguments"`
}

// ToolDefinition represents a tool schema exposed to the model.
type ToolDefinition struct {
	Type     string             `json:"type"`
	Function FunctionDefinition `json:"function"`
}

// FunctionDefinition defines the signature and JSON schema parameters.
type FunctionDefinition struct {
	Name        string                 `json:"name"`
	Description string                 `json:"description,omitempty"`
	Parameters  map[string]interface{} `json:"parameters"`
	Strict      bool                   `json:"strict,omitempty"`
}

// ChatRequest represents a normalized chat completion request.
type ChatRequest struct {
	Model          string           `json:"model"`
	Messages       []Message        `json:"messages"`
	Temperature    *float64         `json:"temperature,omitempty"`
	TopP           *float64         `json:"top_p,omitempty"`
	MaxTokens      int              `json:"max_tokens,omitempty"`
	Stream         bool             `json:"stream,omitempty"`
	Tools          []ToolDefinition `json:"tools,omitempty"`
	ToolChoice     interface{}      `json:"tool_choice,omitempty"`
	ResponseFormat interface{}      `json:"response_format,omitempty"`
	Stop           []string         `json:"stop,omitempty"`
	TenantID       string           `json:"tenant_id,omitempty"`
	TraceID        string           `json:"trace_id,omitempty"`
	Timeout        time.Duration    `json:"-"`
}

// UsageMetrics captures token accounting for billing and telemetry.
type UsageMetrics struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
	ReasoningTokens  int `json:"reasoning_tokens,omitempty"`
	CachedTokens     int `json:"cached_tokens,omitempty"`
}

// ChatChoice represents an individual choice in a completion response.
type ChatChoice struct {
	Index        int      `json:"index"`
	Message      Message  `json:"message"`
	FinishReason string   `json:"finish_reason"`
	Delta        *Message `json:"delta,omitempty"`
}

// ChatResponse represents a normalized chat completion response.
type ChatResponse struct {
	ID        string       `json:"id"`
	Object    string       `json:"object"`
	Created   int64        `json:"created"`
	Model     string       `json:"model"`
	Choices   []ChatChoice `json:"choices"`
	Usage     UsageMetrics `json:"usage"`
	Provider  ProviderType `json:"provider"`
	LatencyMs int64        `json:"latency_ms"`
}

// StreamChunkHandler defines callback for streaming tokens/deltas.
type StreamChunkHandler func(chunk *ChatResponse) error

// EmbeddingRequest represents an embedding generation request.
type EmbeddingRequest struct {
	Model    string   `json:"model"`
	Input    []string `json:"input"`
	TenantID string   `json:"tenant_id,omitempty"`
}

// EmbeddingObject holds an individual vector embedding.
type EmbeddingObject struct {
	Index     int       `json:"index"`
	Embedding []float64 `json:"embedding"`
	Object    string    `json:"object"`
}

// EmbeddingResponse represents an embedding response.
type EmbeddingResponse struct {
	Object    string            `json:"object"`
	Data      []EmbeddingObject `json:"data"`
	Model     string            `json:"model"`
	Usage     UsageMetrics      `json:"usage"`
	LatencyMs int64             `json:"latency_ms"`
}

// ProviderAdapter defines the unified interface that all LLM backends must implement.
type ProviderAdapter interface {
	Name() ProviderType
	ChatCompletion(ctx context.Context, req *ChatRequest) (*ChatResponse, error)
	ChatCompletionStream(ctx context.Context, req *ChatRequest, handler StreamChunkHandler) error
	CreateEmbeddings(ctx context.Context, req *EmbeddingRequest) (*EmbeddingResponse, error)
	HealthCheck(ctx context.Context) error
}

// ProviderConfig holds authentication, endpoint, and SLA configurations.
type ProviderConfig struct {
	Type            ProviderType  `json:"type"`
	BaseURL         string        `json:"base_url"`
	APIKey          string        `json:"api_key"`
	Organization    string        `json:"organization,omitempty"`
	Project         string        `json:"project,omitempty"`
	MaxRetries      int           `json:"max_retries"`
	Timeout         time.Duration `json:"timeout"`
	RateLimitRPM    int           `json:"rate_limit_rpm"`
	RateLimitTPM    int           `json:"rate_limit_tpm"`
	SupportedModels []string      `json:"supported_models"`
}

// ParseHTTPError standardizes upstream HTTP status code inspection.
func ParseHTTPError(resp *http.Response) error {
	body, _ := io.ReadAll(resp.Body)
	defer resp.Body.Close()

	var errPayload struct {
		Error struct {
			Message string `json:"message"`
			Type    string `json:"type"`
			Code    string `json:"code"`
		} `json:"error"`
	}

	_ = json.Unmarshal(body, &errPayload)
	msg := errPayload.Error.Message
	if msg == "" {
		msg = string(body)
	}

	switch resp.StatusCode {
	case http.StatusUnauthorized, http.StatusForbidden:
		return fmt.Errorf("%w: %s (status %d)", ErrProviderAuthFailed, msg, resp.StatusCode)
	case http.StatusTooManyRequests:
		return fmt.Errorf("%w: %s (status %d)", ErrProviderRateLimit, msg, resp.StatusCode)
	case http.StatusNotFound:
		return fmt.Errorf("%w: %s (status %d)", ErrModelNotFound, msg, resp.StatusCode)
	case http.StatusBadRequest:
		return fmt.Errorf("%w: %s (status %d)", ErrInvalidRequest, msg, resp.StatusCode)
	case http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return fmt.Errorf("%w: %s (status %d)", ErrProviderUnavailable, msg, resp.StatusCode)
	default:
		return fmt.Errorf("upstream provider error (status %d): %s", resp.StatusCode, msg)
	}
}
