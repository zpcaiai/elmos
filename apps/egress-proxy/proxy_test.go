package main

import (
	"strings"
	"testing"
)

func TestAcceptsOnlyExactDnsConnectTo443(t *testing.T) {
	// 1. Valid request
	valid := "CONNECT repo.maven.apache.org:443 HTTP/1.1\r\nHost: repo.maven.apache.org\r\n\r\n"
	req, err := ReadConnectRequest(strings.NewReader(valid))
	if err != nil {
		t.Fatalf("expected valid request to succeed, got error: %v", err)
	}
	if req.Host != "repo.maven.apache.org" {
		t.Fatalf("expected host repo.maven.apache.org, got %s", req.Host)
	}

	// 2. Reject GET
	getReq := "GET https://example.com/ HTTP/1.1\r\n\r\n"
	_, err = ReadConnectRequest(strings.NewReader(getReq))
	if err == nil || !strings.Contains(err.Error(), "only HTTP CONNECT is supported") {
		t.Fatalf("expected GET to be rejected, got: %v", err)
	}

	// 3. Reject IP literal
	ipReq := "CONNECT 169.254.169.254:443 HTTP/1.1\r\n\r\n"
	_, err = ReadConnectRequest(strings.NewReader(ipReq))
	if err == nil || !strings.Contains(err.Error(), "IP literals are not allowed") {
		t.Fatalf("expected IP literal to be rejected, got: %v", err)
	}

	// 4. Reject port 80
	port80 := "CONNECT example.com:80 HTTP/1.1\r\n\r\n"
	_, err = ReadConnectRequest(strings.NewReader(port80))
	if err == nil || !strings.Contains(err.Error(), "only destination port 443 is allowed") {
		t.Fatalf("expected port 80 to be rejected, got: %v", err)
	}

	// 5. Oversize headers (>16KB)
	hugeHeader := "CONNECT example.com:443 HTTP/1.1\r\nX-Spam: " + strings.Repeat("A", 17*1024) + "\r\n\r\n"
	_, err = ReadConnectRequest(strings.NewReader(hugeHeader))
	if err == nil || !strings.Contains(err.Error(), "request headers exceed limit") {
		t.Fatalf("expected huge header to exceed limit, got: %v", err)
	}
}

func TestHostAllowlist(t *testing.T) {
	cfg := &Config{
		AllowedHosts: map[string]bool{
			"repo.maven.apache.org": true,
			"*.github.com":          true,
		},
	}
	proxy := NewConnectProxy(cfg)

	if !proxy.isHostAllowed("repo.maven.apache.org") {
		t.Errorf("expected repo.maven.apache.org to be allowed")
	}
	if !proxy.isHostAllowed("api.github.com") {
		t.Errorf("expected api.github.com to be allowed")
	}
	if proxy.isHostAllowed("evil.com") {
		t.Errorf("expected evil.com to be denied")
	}
}
