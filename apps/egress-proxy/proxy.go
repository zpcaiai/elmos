package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var (
	hostRegex = regexp.MustCompile(`^(?i)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$`)
	ipRegex   = regexp.MustCompile(`^[0-9.]+$`)
)

type ConnectRequest struct {
	Host string
}

func ReadConnectRequest(r io.Reader) (*ConnectRequest, error) {
	buf := make([]byte, 0, 1024)
	oneByte := make([]byte, 1)

	for {
		n, err := r.Read(oneByte)
		if err != nil {
			if errors.Is(err, io.EOF) {
				return nil, errors.New("incomplete proxy request")
			}
			return nil, err
		}
		if n > 0 {
			buf = append(buf, oneByte[0])
			if len(buf) >= 16*1024 {
				return nil, errors.New("request headers exceed limit")
			}
			if bytes.HasSuffix(buf, []byte("\r\n\r\n")) {
				break
			}
		}
	}

	headerStr := string(buf)
	lines := strings.Split(headerStr, "\r\n")
	if len(lines) == 0 {
		return nil, errors.New("empty request")
	}

	reqParts := strings.Split(lines[0], " ")
	if len(reqParts) != 3 || reqParts[0] != "CONNECT" || !strings.HasPrefix(reqParts[2], "HTTP/1.") {
		return nil, errors.New("only HTTP CONNECT is supported")
	}

	target := reqParts[1]
	sep := strings.LastIndex(target, ":")
	if sep < 1 || target[sep+1:] != "443" {
		return nil, errors.New("only destination port 443 is allowed")
	}

	host := strings.ToLower(target[:sep])
	if ipRegex.MatchString(host) {
		return nil, errors.New("IP literals are not allowed")
	}
	if len(host) < 1 || len(host) > 253 || !hostRegex.MatchString(host) {
		return nil, errors.New("invalid destination host")
	}

	return &ConnectRequest{Host: host}, nil
}

type Config struct {
	Port          int
	MaxBytes      int64
	IdleSeconds   int
	WorkspaceID   string
	AllowedHosts  map[string]bool
	PolicyID      string
	PolicyVersion int
}

func LoadConfigFromEnv() (*Config, error) {
	port, err := intEnv("ELMOS_PROXY_PORT", 8080, 1024, 65535)
	if err != nil {
		return nil, err
	}
	maxMB, err := intEnv("ELMOS_PROXY_MAX_TUNNEL_MB", 1024, 1, 10240)
	if err != nil {
		return nil, err
	}
	idleSec, err := intEnv("ELMOS_PROXY_IDLE_SECONDS", 120, 5, 3600)
	if err != nil {
		return nil, err
	}
	workspace := os.Getenv("ELMOS_WORKSPACE_ID")
	if strings.TrimSpace(workspace) == "" {
		return nil, errors.New("ELMOS_WORKSPACE_ID is required")
	}
	rawHosts := os.Getenv("ELMOS_EGRESS_ALLOWED_HOSTS")
	if strings.TrimSpace(rawHosts) == "" {
		return nil, errors.New("ELMOS_EGRESS_ALLOWED_HOSTS is required")
	}
	allowed := make(map[string]bool)
	for _, h := range strings.Split(rawHosts, ",") {
		trimmed := strings.ToLower(strings.TrimSpace(h))
		if trimmed != "" {
			allowed[trimmed] = true
		}
	}
	policyID := os.Getenv("ELMOS_NETWORK_POLICY_ID")
	if strings.TrimSpace(policyID) == "" {
		return nil, errors.New("ELMOS_NETWORK_POLICY_ID is required")
	}
	policyVersion, err := intEnv("ELMOS_NETWORK_POLICY_VERSION", 1, 1, 1<<30)
	if err != nil {
		return nil, err
	}

	return &Config{
		Port:          port,
		MaxBytes:      int64(maxMB) * 1024 * 1024,
		IdleSeconds:   idleSec,
		WorkspaceID:   workspace,
		AllowedHosts:  allowed,
		PolicyID:      policyID,
		PolicyVersion: policyVersion,
	}, nil
}

func intEnv(name string, fallback, minVal, maxVal int) (int, error) {
	val := os.Getenv(name)
	if strings.TrimSpace(val) == "" {
		return fallback, nil
	}
	parsed, err := strconv.Atoi(val)
	if err != nil || parsed < minVal || parsed > maxVal {
		return 0, fmt.Errorf("%s is outside policy", name)
	}
	return parsed, nil
}

type AuditLog struct {
	WorkspaceID       string   `json:"workspaceId"`
	PolicyID          string   `json:"policyId"`
	PolicyVersion     int      `json:"policyVersion"`
	Host              string   `json:"host"`
	ResolvedAddresses []string `json:"resolvedAddresses"`
	Decision          string   `json:"decision"`
	Reason            string   `json:"reason"`
	BytesSent         int64    `json:"bytesSent"`
	BytesReceived     int64    `json:"bytesReceived"`
}

type ConnectProxy struct {
	config *Config
}

func NewConnectProxy(cfg *Config) *ConnectProxy {
	return &ConnectProxy{config: cfg}
}

func (p *ConnectProxy) Serve(listener net.Listener) error {
	for {
		client, err := listener.Accept()
		if err != nil {
			return err
		}
		go p.Handle(client)
	}
}

func (p *ConnectProxy) Handle(client net.Conn) {
	defer client.Close()

	idleTimeout := time.Duration(p.config.IdleSeconds) * time.Second
	_ = client.SetDeadline(time.Now().Add(idleTimeout))

	host := "unknown"
	result := "DENY"
	reason := "invalid request"
	var resolved []string
	var sent, received atomic.Int64

	defer func() {
		p.audit(host, resolved, result, reason, sent.Load(), received.Load())
	}()

	reader := bufio.NewReader(client)
	req, err := ReadConnectRequest(reader)
	if err != nil {
		reason = err.Error()
		return
	}
	host = req.Host

	// DNS lookup
	ips, err := net.LookupIP(host)
	if err != nil || len(ips) == 0 {
		reason = "DNS resolution failed"
		respond(client, 403, "Forbidden")
		return
	}

	for _, ip := range ips {
		resolved = append(resolved, ip.String())
	}
	sort.Strings(resolved)

	// Check policy
	if !p.isHostAllowed(host) {
		reason = fmt.Sprintf("host %s is not in allowed egress policy", host)
		respond(client, 403, "Forbidden")
		return
	}

	upstreamAddr := net.JoinHostPort(ips[0].String(), "443")
	upstream, err := net.DialTimeout("tcp", upstreamAddr, 10*time.Second)
	if err != nil {
		reason = fmt.Sprintf("upstream connect failed: %v", err)
		respond(client, 502, "Bad Gateway")
		return
	}
	defer upstream.Close()

	_ = upstream.SetDeadline(time.Now().Add(idleTimeout))
	respond(client, 200, "Connection Established")
	result = "ALLOW"
	reason = "matched allowed network policy"

	// Reset read deadlines before tunneling
	_ = client.SetDeadline(time.Time{})
	_ = upstream.SetDeadline(time.Time{})

	var wg sync.WaitGroup
	wg.Add(2)

	// client -> upstream
	go func() {
		defer wg.Done()
		defer upstream.Close()
		copyLimit(client, upstream, &sent, p.config.MaxBytes)
	}()

	// upstream -> client
	go func() {
		defer wg.Done()
		defer client.Close()
		copyLimit(upstream, client, &received, p.config.MaxBytes)
	}()

	wg.Wait()
}

func (p *ConnectProxy) isHostAllowed(host string) bool {
	if p.config.AllowedHosts[host] {
		return true
	}
	// Check wildcard domain e.g. *.maven.org
	for allowed := range p.config.AllowedHosts {
		if strings.HasPrefix(allowed, "*.") {
			suffix := allowed[1:] // .maven.org
			if strings.HasSuffix(host, suffix) {
				return true
			}
		}
	}
	return false
}

func copyLimit(src io.Reader, dst io.Writer, counter *atomic.Int64, limit int64) {
	buf := make([]byte, 32*1024)
	for {
		nr, err := src.Read(buf)
		if nr > 0 {
			total := counter.Add(int64(nr))
			if total > limit {
				return
			}
			_, ew := dst.Write(buf[:nr])
			if ew != nil {
				return
			}
		}
		if err != nil {
			return
		}
	}
}

func respond(conn io.Writer, status int, text string) {
	msg := fmt.Sprintf("HTTP/1.1 %d %s\r\nConnection: keep-alive\r\n\r\n", status, text)
	_, _ = conn.Write([]byte(msg))
}

func (p *ConnectProxy) audit(host string, resolved []string, result, reason string, sent, received int64) {
	log := AuditLog{
		WorkspaceID:       p.config.WorkspaceID,
		PolicyID:          p.config.PolicyID,
		PolicyVersion:     p.config.PolicyVersion,
		Host:              host,
		ResolvedAddresses: resolved,
		Decision:          result,
		Reason:            reason,
		BytesSent:         sent,
		BytesReceived:     received,
	}
	payload, _ := json.Marshal(log)
	fmt.Println(string(payload))
}

func main() {
	cfg, err := LoadConfigFromEnv()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Configuration error: %v\n", err)
		os.Exit(1)
	}

	listener, err := net.Listen("tcp", fmt.Sprintf("0.0.0.0:%d", cfg.Port))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to bind port %d: %v\n", cfg.Port, err)
		os.Exit(1)
	}
	defer listener.Close()

	proxy := NewConnectProxy(cfg)
	if err := proxy.Serve(listener); err != nil {
		fmt.Fprintf(os.Stderr, "Proxy terminated: %v\n", err)
		os.Exit(1)
	}
}
