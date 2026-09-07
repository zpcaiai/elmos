package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

func TestConfigFailsClosed(t *testing.T) {
	// Missing base url
	_, err := ConfigFromEnv(map[string]string{})
	if err == nil || !strings.Contains(err.Error(), "ELMOS_CONTROL_PLANE_BASE_URL") {
		t.Fatalf("expected missing base url error, got %v", err)
	}

	// Non-https outside loopback
	_, err = ConfigFromEnv(map[string]string{
		"ELMOS_CONTROL_PLANE_BASE_URL": "http://api.production.internal",
	})
	if err == nil || !strings.Contains(err.Error(), "must use https") {
		t.Fatalf("expected non-https failure, got %v", err)
	}

	// Invalid node id
	_, err = ConfigFromEnv(map[string]string{
		"ELMOS_CONTROL_PLANE_BASE_URL": "http://localhost:8080",
		"ELMOS_RUNNER_NODE_ID":         "INVALID_UPPERCASE",
	})
	if err == nil || !strings.Contains(err.Error(), "ELMOS_RUNNER_NODE_ID") {
		t.Fatalf("expected node id error, got %v", err)
	}

	// Enrolment token too short
	_, err = ConfigFromEnv(map[string]string{
		"ELMOS_CONTROL_PLANE_BASE_URL": "http://localhost:8080",
		"ELMOS_RUNNER_NODE_ID":         "runner-node-01",
		"ELMOS_RUNNER_ENROLMENT_TOKEN": "short-secret",
	})
	if err == nil || !strings.Contains(err.Error(), "at least 32 characters") {
		t.Fatalf("expected token length error, got %v", err)
	}

	// Valid config with host execution
	tmpDir := t.TempDir()
	validEnv := map[string]string{
		"ELMOS_CONTROL_PLANE_BASE_URL":     "http://localhost:8080",
		"ELMOS_RUNNER_NODE_ID":             "runner-node-01",
		"ELMOS_RUNNER_ENROLMENT_TOKEN":     "0123456789abcdef0123456789abcdef",
		"ELMOS_RUNNER_CAPABILITIES":         "java:21,rust:1.80,go:1.25",
		"ELMOS_RUNNER_WORK_ROOT":            tmpDir,
		"ELMOS_RUNNER_ALLOW_HOST_EXECUTION": "true",
	}
	cfg, err := ConfigFromEnv(validEnv)
	if err != nil {
		t.Fatalf("expected valid config, got %v", err)
	}
	if cfg.MaxConcurrency != 2 {
		t.Errorf("expected default max concurrency 2, got %d", cfg.MaxConcurrency)
	}
	if len(cfg.Capabilities) != 3 {
		t.Errorf("expected 3 capabilities, got %d", len(cfg.Capabilities))
	}
}

func TestSandboxAndWorkspaceProbes(t *testing.T) {
	tmpDir := t.TempDir()
	cfg := &Config{
		RunnerNodeId:       "node-01",
		WorkRoot:           tmpDir,
		AllowHostExecution: true,
		WorkloadUid:        os.Getuid(),
		WorkloadGid:        os.Getgid(),
	}

	att := ProbeSandbox(cfg)
	if att == nil {
		t.Fatal("expected non-nil attestation")
	}

	probe := VerifyWorkspaceAccess(cfg)
	if !probe.Usable {
		t.Fatalf("expected usable workspace probe, got: %s", probe.Detail)
	}
}

func TestControlPlaneClientMock(t *testing.T) {
	var registered, heartbeatSent, jobClaimed, jobCommitted bool

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := r.Header.Get("Authorization")
		if !strings.HasPrefix(token, "Bearer 0123456789abcdef0123456789abcdef") {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}

		switch r.URL.Path {
		case "/api/v1/runner/nodes/register":
			registered = true
			w.WriteHeader(http.StatusOK)
		case "/api/v1/runner/nodes/heartbeat":
			heartbeatSent = true
			w.WriteHeader(http.StatusOK)
		case "/api/v1/runner/jobs/claim":
			jobClaimed = true
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]interface{}{
				"leases": []Lease{
					{
						JobId:         "job-101",
						LeaseId:       "lease-101",
						BusinessLine:  "modernization",
						JobKind:       "spring-check",
						BudgetWallSec: 10,
						RequestPayload: map[string]interface{}{
							"command": "echo 'Hello Native Runner' > output.log",
						},
					},
				},
			})
		case "/api/v1/runner/jobs/lease-101/commit":
			jobCommitted = true
			w.WriteHeader(http.StatusOK)
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer server.Close()

	tmpDir := t.TempDir()
	cfg := &Config{
		ControlPlaneBaseURL: server.URL,
		RunnerNodeId:        "node-01",
		EnrolmentToken:      "0123456789abcdef0123456789abcdef",
		WorkRoot:            tmpDir,
		ClaimBatchSize:      1,
		AllowHostExecution:  true,
	}

	client := NewControlPlaneClient(cfg)
	ctx := context.Background()

	// Register
	att := ProbeSandbox(cfg)
	if err := client.RegisterNode(ctx, cfg, att); err != nil {
		t.Fatalf("register failed: %v", err)
	}
	if !registered {
		t.Error("expected registered to be true")
	}

	// Node Heartbeat
	if err := client.SendNodeHeartbeat(ctx); err != nil {
		t.Fatalf("heartbeat failed: %v", err)
	}
	if !heartbeatSent {
		t.Error("expected heartbeatSent to be true")
	}

	// Claim
	leases, err := client.ClaimJobs(ctx, cfg)
	if err != nil {
		t.Fatalf("claim failed: %v", err)
	}
	if !jobClaimed || len(leases) != 1 {
		t.Fatalf("expected 1 claimed lease, got %d", len(leases))
	}

	// Execute Job
	executor := NewJobExecutor(cfg, client)
	res := executor.Execute(ctx, leases[0])
	if res.Outcome != "SUCCEEDED" {
		t.Fatalf("expected SUCCEEDED, got %s: %s", res.Outcome, res.ErrorMessage)
	}
	if len(res.Artifacts) != 1 {
		t.Fatalf("expected 1 artifact, got %d", len(res.Artifacts))
	}
	if res.Artifacts[0].Role != "log" {
		t.Errorf("expected role 'log', got %s", res.Artifacts[0].Role)
	}

	// Commit
	if err := client.CommitJob(ctx, leases[0].LeaseId, res); err != nil {
		t.Fatalf("commit failed: %v", err)
	}
	if !jobCommitted {
		t.Error("expected jobCommitted to be true")
	}
}

func TestArtifactRoleDerivation(t *testing.T) {
	tests := []struct {
		path string
		role string
	}{
		{"reports/evidence.json", "evidence"},
		{"build.log", "log"},
		{"changes.patch", "patch"},
		{"main.jar", "artifact"},
	}
	for _, tc := range tests {
		got := deriveRole(tc.path)
		if got != tc.role {
			t.Errorf("path %s: expected role %s, got %s", tc.path, tc.role, got)
		}
	}
}
