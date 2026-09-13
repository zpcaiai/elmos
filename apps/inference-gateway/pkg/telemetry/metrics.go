package telemetry

import (
	"fmt"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

// MetricsCollector tracks metrics for Prometheus exposition.
type MetricsCollector struct {
	mu             sync.RWMutex
	requestCounts  map[string]uint64
	tokenCounts    map[string]uint64
	durationSums   map[string]float64
	durationCounts map[string]uint64
	activeRequests int64
}

var DefaultMetrics = NewMetricsCollector()

func NewMetricsCollector() *MetricsCollector {
	return &MetricsCollector{
		requestCounts:  make(map[string]uint64),
		tokenCounts:    make(map[string]uint64),
		durationSums:   make(map[string]float64),
		durationCounts: make(map[string]uint64),
	}
}

func (m *MetricsCollector) RecordRequest(provider, model string, statusCode int, duration time.Duration, promptTokens, completionTokens int) {
	status := fmt.Sprintf("%d", statusCode)
	reqKey := fmt.Sprintf(`provider="%s",model="%s",status="%s"`, provider, model, status)
	durKey := fmt.Sprintf(`provider="%s",model="%s"`, provider, model)
	promptKey := fmt.Sprintf(`provider="%s",model="%s",type="prompt"`, provider, model)
	compKey := fmt.Sprintf(`provider="%s",model="%s",type="completion"`, provider, model)

	m.mu.Lock()
	defer m.mu.Unlock()

	m.requestCounts[reqKey]++
	m.durationSums[durKey] += duration.Seconds()
	m.durationCounts[durKey]++

	if promptTokens > 0 {
		m.tokenCounts[promptKey] += uint64(promptTokens)
	}
	if completionTokens > 0 {
		m.tokenCounts[compKey] += uint64(completionTokens)
	}
}

func (m *MetricsCollector) IncActive() {
	atomic.AddInt64(&m.activeRequests, 1)
}

func (m *MetricsCollector) DecActive() {
	atomic.AddInt64(&m.activeRequests, -1)
}

// ServeHTTP renders the metrics in standard Prometheus text exposition format.
func (m *MetricsCollector) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	w.Header().Set("Content-Type", "text/plain; version=0.0.4")

	fmt.Fprintf(w, "# HELP llm_gateway_active_requests Number of currently active in-flight requests\n")
	fmt.Fprintf(w, "# TYPE llm_gateway_active_requests gauge\n")
	fmt.Fprintf(w, "llm_gateway_active_requests %d\n\n", atomic.LoadInt64(&m.activeRequests))

	fmt.Fprintf(w, "# HELP llm_gateway_requests_total Total number of completed LLM requests\n")
	fmt.Fprintf(w, "# TYPE llm_gateway_requests_total counter\n")
	for k, v := range m.requestCounts {
		fmt.Fprintf(w, "llm_gateway_requests_total{%s} %d\n", k, v)
	}
	fmt.Fprintln(w)

	fmt.Fprintf(w, "# HELP llm_gateway_tokens_total Total tokens processed across requests\n")
	fmt.Fprintf(w, "# TYPE llm_gateway_tokens_total counter\n")
	for k, v := range m.tokenCounts {
		fmt.Fprintf(w, "llm_gateway_tokens_total{%s} %d\n", k, v)
	}
	fmt.Fprintln(w)

	fmt.Fprintf(w, "# HELP llm_gateway_request_duration_seconds_sum Total latency in seconds\n")
	fmt.Fprintf(w, "# TYPE llm_gateway_request_duration_seconds_sum counter\n")
	for k, v := range m.durationSums {
		fmt.Fprintf(w, "llm_gateway_request_duration_seconds_sum{%s} %.4f\n", k, v)
		fmt.Fprintf(w, "llm_gateway_request_duration_seconds_count{%s} %d\n", k, m.durationCounts[k])
	}
}
