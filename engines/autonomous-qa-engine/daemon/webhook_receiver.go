package daemon

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

// WebhookEvent represents an immutable webhook ingestion record with audit telemetry.
type WebhookEvent struct {
	EventID       string            `json:"event_id"`
	Provider      string            `json:"provider"`
	EventType     string            `json:"event_type"`
	TenantID      string            `json:"tenant_id"`
	ProjectID     string            `json:"project_id"`
	RepositoryID  string            `json:"repository_id"`
	Action        string            `json:"action"`
	Timestamp     int64             `json:"timestamp"`
	DeliveryID    string            `json:"delivery_id"`
	PayloadDigest string            `json:"payload_digest"`
	Metadata      map[string]string `json:"metadata"`
	RetryCount    int               `json:"retry_count"`
	IsProcessed   bool              `json:"is_processed"`
	ErrorLog      []string          `json:"error_log"`
	ProcessingMs  int64             `json:"processing_ms"`
}

func (e *WebhookEvent) Validate() error {
	if e.EventID == "" {
		return errors.New("event_id cannot be empty")
	}
	if e.TenantID == "" {
		return errors.New("tenant_id cannot be empty")
	}
	if e.PayloadDigest == "" {
		return errors.New("payload_digest cannot be empty")
	}
	if e.Timestamp <= 0 {
		return errors.New("invalid timestamp")
	}
	return nil
}

func (e *WebhookEvent) ComputeHash() string {
	h := sha256.New()
	h.Write([]byte(fmt.Sprintf("%s:%s:%s:%d", e.EventID, e.TenantID, e.PayloadDigest, e.Timestamp)))
	return hex.EncodeToString(h.Sum(nil))
}

// TokenBucketLimiter controls tenant-level webhook ingress burst and sustained rates.
type TokenBucketLimiter struct {
	mu         sync.Mutex
	capacity   float64
	tokens     float64
	refillRate float64
	lastRefill time.Time
}

func NewTokenBucketLimiter(capacity, refillRate float64) *TokenBucketLimiter {
	return &TokenBucketLimiter{
		capacity:   capacity,
		tokens:     capacity,
		refillRate: refillRate,
		lastRefill: time.Now(),
	}
}

func (l *TokenBucketLimiter) Allow() bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	now := time.Now()
	duration := now.Sub(l.lastRefill).Seconds()
	l.tokens += duration * l.refillRate
	if l.tokens > l.capacity {
		l.tokens = l.capacity
	}
	l.lastRefill = now
	if l.tokens >= 1.0 {
		l.tokens -= 1.0
		return true
	}
	return false
}

// WebhookIngestionServer routes and authorizes GitHub and GitLab webhook events.
type WebhookIngestionServer struct {
	githubSecret  string
	gitlabToken   string
	limiters      map[string]*TokenBucketLimiter
	limiterMu     sync.RWMutex
	eventBuffer   map[string]time.Time
	bufferMu      sync.RWMutex
	totalReceived atomic.Uint64
	totalVerified atomic.Uint64
	totalRejected atomic.Uint64
}

func NewWebhookIngestionServer(githubSecret, gitlabToken string) *WebhookIngestionServer {
	return &WebhookIngestionServer{
		githubSecret: githubSecret,
		gitlabToken:  gitlabToken,
		limiters:     make(map[string]*TokenBucketLimiter),
		eventBuffer:  make(map[string]time.Time),
	}
}

// VerifyGitHubHMAC validates a GitHub webhook HMAC-SHA256 signature using constant-time comparison.
func VerifyGitHubHMAC(payload []byte, signatureHeader string, secret string) bool {
	if signatureHeader == "" || len(signatureHeader) < 7 || signatureHeader[:7] != "sha256=" {
		return false
	}
	sigBytes, err := hex.DecodeString(signatureHeader[7:])
	if err != nil {
		return false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	expected := mac.Sum(nil)
	return subtle.ConstantTimeCompare(sigBytes, expected) == 1
}

func (s *WebhookIngestionServer) VerifyGitHubSignature(payload []byte, signatureHeader string) bool {
	return VerifyGitHubHMAC(payload, signatureHeader, s.githubSecret)
}

func (s *WebhookIngestionServer) VerifyGitLabToken(tokenHeader string) bool {
	return VerifyGitLabToken(tokenHeader, s.gitlabToken)
}

// VerifyGitLabToken validates a GitLab webhook token using constant-time comparison.
func VerifyGitLabToken(tokenHeader, secretToken string) bool {
	if tokenHeader == "" || secretToken == "" {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(tokenHeader), []byte(secretToken)) == 1
}

func (s *WebhookIngestionServer) IsDuplicate(eventID string, ttl time.Duration) bool {
	s.bufferMu.Lock()
	defer s.bufferMu.Unlock()
	now := time.Now()
	if t, exists := s.eventBuffer[eventID]; exists && now.Sub(t) < ttl {
		return true
	}
	s.eventBuffer[eventID] = now
	// Cleanup expired entries periodically
	if len(s.eventBuffer) > 10000 {
		for k, v := range s.eventBuffer {
			if now.Sub(v) > ttl {
				delete(s.eventBuffer, k)
			}
		}
	}
	return false
}

func (s *WebhookIngestionServer) HandleEvent(ctx context.Context, payload []byte) (*WebhookEvent, error) {
	s.totalReceived.Add(1)
	var event WebhookEvent
	if err := json.Unmarshal(payload, &event); err != nil {
		s.totalRejected.Add(1)
		return nil, fmt.Errorf("failed to unmarshal payload: %w", err)
	}
	if err := event.Validate(); err != nil {
		s.totalRejected.Add(1)
		return nil, fmt.Errorf("invalid event payload: %w", err)
	}
	s.totalVerified.Add(1)
	event.IsProcessed = true
	return &event, nil
}

func (s *WebhookIngestionServer) Metrics() (received, verified, rejected uint64) {
	return s.totalReceived.Load(), s.totalVerified.Load(), s.totalRejected.Load()
}

// HTTPHandler returns an http.Handler that authenticates and dispatches incoming webhook requests.
func (s *WebhookIngestionServer) HTTPHandler(worker func(event *WebhookEvent)) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}
		var payload []byte
		if r.Body != nil {
			defer r.Body.Close()
			buf := make([]byte, 1024*1024)
			n, _ := r.Body.Read(buf)
			payload = buf[:n]
		}
		ghSig := r.Header.Get("X-Hub-Signature-256")
		glToken := r.Header.Get("X-Gitlab-Token")
		verified := false
		if ghSig != "" && s.VerifyGitHubSignature(payload, ghSig) {
			verified = true
		} else if glToken != "" && s.VerifyGitLabToken(glToken) {
			verified = true
		}
		if !verified {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		event, err := s.HandleEvent(r.Context(), payload)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		if worker != nil {
			go worker(event)
		}
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ACCEPTED", "event_id": event.EventID})
	})
}
