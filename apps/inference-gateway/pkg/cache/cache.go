package cache

import (
	"container/list"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sync"
	"sync/atomic"
	"time"

	"io.elmos/inferencegateway/pkg/providers"
)

// CacheEntry stores cached response and metadata.
type CacheEntry struct {
	Key          string                  `json:"key"`
	PrefixKey    string                  `json:"prefix_key"`
	Response     *providers.ChatResponse `json:"response"`
	CreatedAt    time.Time               `json:"created_at"`
	ExpiresAt    time.Time               `json:"expires_at"`
	TokensSaved  int                     `json:"tokens_saved"`
	AccessCount  int64                   `json:"access_count"`
}

// CacheMetrics captures operational statistics for monitoring.
type CacheMetrics struct {
	Hits            uint64  `json:"hits"`
	Misses          uint64  `json:"misses"`
	Evictions       uint64  `json:"evictions"`
	ItemsCount      int     `json:"items_count"`
	TotalTokensSaved uint64  `json:"total_tokens_saved"`
	HitRatio        float64 `json:"hit_ratio"`
}

// PromptCache is an LRU-based high-performance multi-tier cache.
type PromptCache struct {
	mu           sync.RWMutex
	capacity     int
	ttl          time.Duration
	items        map[string]*list.Element
	evictList    *list.List
	prefixIndex  map[string]string // Maps prefix hashes to full keys
	hits         uint64
	misses       uint64
	evictions    uint64
	tokensSaved  uint64
}

func NewPromptCache(capacity int, ttl time.Duration) *PromptCache {
	if capacity <= 0 {
		capacity = 1000
	}
	if ttl <= 0 {
		ttl = 1 * time.Hour
	}
	return &PromptCache{
		capacity:    capacity,
		ttl:         ttl,
		items:       make(map[string]*list.Element),
		evictList:   list.New(),
		prefixIndex: make(map[string]string),
	}
}

// ComputeCacheKey generates a Merkle-like SHA256 digest of request attributes.
func ComputeCacheKey(req *providers.ChatRequest) (fullKey string, prefixKey string) {
	h := sha256.New()
	h.Write([]byte(fmt.Sprintf("model:%s|max_tokens:%d|", req.Model, req.MaxTokens)))

	prefixH := sha256.New()
	prefixH.Write([]byte(fmt.Sprintf("model:%s|", req.Model)))

	// Tools hash
	if len(req.Tools) > 0 {
		toolBytes, _ := json.Marshal(req.Tools)
		h.Write([]byte("tools:"))
		h.Write(toolBytes)
	}

	// Messages hash
	for i, m := range req.Messages {
		msgChunk := fmt.Sprintf("|idx:%d|role:%s|content:%s", i, m.Role, m.Content)
		h.Write([]byte(msgChunk))

		// If this is a system message or early conversation prefix, include in prefix hash
		if m.Role == "system" || i < 2 {
			prefixH.Write([]byte(msgChunk))
		}
	}

	fullKey = hex.EncodeToString(h.Sum(nil))
	prefixKey = hex.EncodeToString(prefixH.Sum(nil))
	return fullKey, prefixKey
}

func (c *PromptCache) Get(req *providers.ChatRequest) (*providers.ChatResponse, bool) {
	fullKey, _ := ComputeCacheKey(req)

	c.mu.Lock()
	defer c.mu.Unlock()

	if elem, found := c.items[fullKey]; found {
		entry := elem.Value.(*CacheEntry)
		if time.Now().After(entry.ExpiresAt) {
			// Expired
			c.removeElement(elem)
			atomic.AddUint64(&c.misses, 1)
			return nil, false
		}

		c.evictList.MoveToFront(elem)
		atomic.AddInt64(&entry.AccessCount, 1)
		atomic.AddUint64(&c.hits, 1)
		atomic.AddUint64(&c.tokensSaved, uint64(entry.Response.Usage.PromptTokens))

		// Return a copy with marked cached tokens
		respCopy := *entry.Response
		respCopy.Usage.CachedTokens = respCopy.Usage.PromptTokens
		return &respCopy, true
	}

	atomic.AddUint64(&c.misses, 1)
	return nil, false
}

func (c *PromptCache) Set(req *providers.ChatRequest, resp *providers.ChatResponse) {
	if resp == nil || len(resp.Choices) == 0 {
		return
	}

	fullKey, prefixKey := ComputeCacheKey(req)

	c.mu.Lock()
	defer c.mu.Unlock()

	// Check if already present
	if elem, found := c.items[fullKey]; found {
		c.evictList.MoveToFront(elem)
		entry := elem.Value.(*CacheEntry)
		entry.Response = resp
		entry.ExpiresAt = time.Now().Add(c.ttl)
		return
	}

	// Evict oldest if capacity exceeded
	for c.evictList.Len() >= c.capacity {
		c.evictOldest()
	}

	entry := &CacheEntry{
		Key:         fullKey,
		PrefixKey:   prefixKey,
		Response:    resp,
		CreatedAt:   time.Now(),
		ExpiresAt:   time.Now().Add(c.ttl),
		TokensSaved: resp.Usage.PromptTokens,
		AccessCount: 1,
	}

	elem := c.evictList.PushFront(entry)
	c.items[fullKey] = elem
	c.prefixIndex[prefixKey] = fullKey
}

func (c *PromptCache) evictOldest() {
	elem := c.evictList.Back()
	if elem != nil {
		c.removeElement(elem)
		atomic.AddUint64(&c.evictions, 1)
	}
}

func (c *PromptCache) removeElement(elem *list.Element) {
	c.evictList.Remove(elem)
	entry := elem.Value.(*CacheEntry)
	delete(c.items, entry.Key)
	delete(c.prefixIndex, entry.PrefixKey)
}

func (c *PromptCache) Invalidate(fullKey string) bool {
	c.mu.Lock()
	defer c.mu.Unlock()

	if elem, found := c.items[fullKey]; found {
		c.removeElement(elem)
		return true
	}
	return false
}

func (c *PromptCache) Clear() {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.items = make(map[string]*list.Element)
	c.prefixIndex = make(map[string]string)
	c.evictList.Init()
}

func (c *PromptCache) Metrics() CacheMetrics {
	c.mu.RLock()
	defer c.mu.RUnlock()

	hits := atomic.LoadUint64(&c.hits)
	misses := atomic.LoadUint64(&c.misses)
	total := hits + misses
	ratio := 0.0
	if total > 0 {
		ratio = float64(hits) / float64(total)
	}

	return CacheMetrics{
		Hits:             hits,
		Misses:           misses,
		Evictions:        atomic.LoadUint64(&c.evictions),
		ItemsCount:       len(c.items),
		TotalTokensSaved: atomic.LoadUint64(&c.tokensSaved),
		HitRatio:         ratio,
	}
}
