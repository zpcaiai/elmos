package main

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// Provider identifies an upstream LLM service provider.
type Provider string

const (
	ProviderOpenAI    Provider = "openai"
	ProviderAnthropic Provider = "anthropic"
	ProviderGemini    Provider = "gemini"
	ProviderDeepSeek  Provider = "deepseek"
	ProviderLiteLLM   Provider = "litellm"
	ProviderRehearsal Provider = "rehearsal"
)

// UpstreamConfig holds configuration for upstream providers.
type UpstreamConfig struct {
	BaseURL string
	APIKey  string
	Timeout time.Duration
}

// UpstreamRouter manages routing requests to appropriate LLM backends.
type UpstreamRouter struct {
	mu        sync.RWMutex
	providers map[Provider]UpstreamConfig
	client    *http.Client
}

func NewUpstreamRouter() *UpstreamRouter {
	router := &UpstreamRouter{
		providers: make(map[Provider]UpstreamConfig),
		client: &http.Client{
			Timeout: 60 * time.Second,
		},
	}

	// Initialize configs from environment variables if present
	router.providers[ProviderOpenAI] = UpstreamConfig{
		BaseURL: getEnv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
		APIKey:  os.Getenv("OPENAI_API_KEY"),
		Timeout: 60 * time.Second,
	}
	router.providers[ProviderDeepSeek] = UpstreamConfig{
		BaseURL: getEnv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
		APIKey:  os.Getenv("DEEPSEEK_API_KEY"),
		Timeout: 60 * time.Second,
	}
	router.providers[ProviderGemini] = UpstreamConfig{
		BaseURL: getEnv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
		APIKey:  os.Getenv("GEMINI_API_KEY"),
		Timeout: 60 * time.Second,
	}
	router.providers[ProviderAnthropic] = UpstreamConfig{
		BaseURL: getEnv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
		APIKey:  os.Getenv("ANTHROPIC_API_KEY"),
		Timeout: 60 * time.Second,
	}
	router.providers[ProviderLiteLLM] = UpstreamConfig{
		BaseURL: getEnv("LITELLM_BASE_URL", "http://localhost:4000/v1"),
		APIKey:  os.Getenv("LITELLM_API_KEY"),
		Timeout: 60 * time.Second,
	}

	return router
}

func getEnv(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}

// ResolveProvider determines which provider should handle the model.
func (r *UpstreamRouter) ResolveProvider(model string, authHeader string) (Provider, UpstreamConfig) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	modelLower := strings.ToLower(model)

	if strings.HasPrefix(modelLower, "rehearsal") || strings.HasPrefix(modelLower, "mock") {
		return ProviderRehearsal, UpstreamConfig{}
	}

	// OpenAI routing
	if strings.HasPrefix(modelLower, "openai/") || strings.HasPrefix(modelLower, "gpt-") || strings.HasPrefix(modelLower, "o1") || strings.HasPrefix(modelLower, "o3") || strings.HasPrefix(modelLower, "text-embedding") {
		cfg := r.providers[ProviderOpenAI]
		if authHeader != "" && cfg.APIKey == "" {
			cfg.APIKey = extractBearer(authHeader)
		}
		return ProviderOpenAI, cfg
	}

	// Anthropic routing
	if strings.HasPrefix(modelLower, "anthropic/") || strings.HasPrefix(modelLower, "claude") {
		cfg := r.providers[ProviderAnthropic]
		if authHeader != "" && cfg.APIKey == "" {
			cfg.APIKey = extractBearer(authHeader)
		}
		return ProviderAnthropic, cfg
	}

	// Gemini routing
	if strings.HasPrefix(modelLower, "gemini") || strings.HasPrefix(modelLower, "google/") {
		cfg := r.providers[ProviderGemini]
		if authHeader != "" && cfg.APIKey == "" {
			cfg.APIKey = extractBearer(authHeader)
		}
		return ProviderGemini, cfg
	}

	// DeepSeek routing
	if strings.HasPrefix(modelLower, "deepseek") {
		cfg := r.providers[ProviderDeepSeek]
		if authHeader != "" && cfg.APIKey == "" {
			cfg.APIKey = extractBearer(authHeader)
		}
		return ProviderDeepSeek, cfg
	}

	// LiteLLM routing
	if strings.HasPrefix(modelLower, "litellm/") {
		cfg := r.providers[ProviderLiteLLM]
		return ProviderLiteLLM, cfg
	}

	return ProviderRehearsal, UpstreamConfig{}
}

func extractBearer(header string) string {
	parts := strings.SplitN(header, " ", 2)
	if len(parts) == 2 && strings.EqualFold(parts[0], "Bearer") {
		return parts[1]
	}
	return header
}

// ForwardChatRequest forwards a chat completion request to the resolved upstream provider.
func (r *UpstreamRouter) ForwardChatRequest(ctx context.Context, provider Provider, cfg UpstreamConfig, body []byte, stream bool) (*http.Response, error) {
	if provider == ProviderRehearsal || cfg.APIKey == "" {
		return nil, fmt.Errorf("no live upstream configured or rehearsal mode")
	}

	targetURL := strings.TrimRight(cfg.BaseURL, "/") + "/chat/completions"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, targetURL, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+cfg.APIKey)
	if stream {
		req.Header.Set("Accept", "text/event-stream")
	}

	return r.client.Do(req)
}
