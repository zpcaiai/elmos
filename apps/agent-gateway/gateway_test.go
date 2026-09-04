package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func validSmartRequestJSON() string {
	return `{
  "schemaVersion": "1.0",
  "catalogVersion": "repository-model-catalog-v1.1.0",
  "selectionVersion": "repository-model-selection-v1",
  "mode": "smart",
  "selectedModel": null,
  "optimizationProfile": "cost_performance",
  "fallbackPolicy": null,
  "verificationPolicy": "system_required_verifiers",
  "risk": {
    "security": "low",
    "dataMigration": "low",
    "concurrency": "low",
    "publicContract": "low",
    "blastRadius": "low",
    "longHorizon": false
  }
}`
}

func TestCatalogReturnsExactlyTenServerOwnedUnavailableModels(t *testing.T) {
	server := NewGatewayServer()
	req := httptest.NewRequest("GET", "/agent/v1/repository-orchestrator/models", nil)
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", w.Code)
	}

	var catalog Catalog
	if err := json.Unmarshal(w.Body.Bytes(), &catalog); err != nil {
		t.Fatalf("failed to unmarshal catalog: %v", err)
	}

	if catalog.DefaultMode != "smart" {
		t.Errorf("expected defaultMode 'smart', got %s", catalog.DefaultMode)
	}
	if catalog.Status != "NOT_CONFIGURED" {
		t.Errorf("expected status 'NOT_CONFIGURED', got %s", catalog.Status)
	}
	if len(catalog.Models) != 10 {
		t.Fatalf("expected 10 models, got %d", len(catalog.Models))
	}
	if catalog.Models[0].Alias != "gpt-5.6-sol-max" {
		t.Errorf("expected model[0] gpt-5.6-sol-max, got %s", catalog.Models[0].Alias)
	}
	if catalog.Models[9].Alias != "claude-sonnet-5" {
		t.Errorf("expected model[9] claude-sonnet-5, got %s", catalog.Models[9].Alias)
	}
	if catalog.Models[0].Available {
		t.Errorf("expected model[0] available to be false")
	}
	if catalog.Models[0].Selectable {
		t.Errorf("expected model[0] selectable to be false")
	}
	if catalog.RuntimeProfilesAcceptedFromClient {
		t.Errorf("expected runtimeProfilesAcceptedFromClient to be false")
	}
	if catalog.Evidence.ProviderInvocation != "NOT_RUN" {
		t.Errorf("expected providerInvocation NOT_RUN, got %s", catalog.Evidence.ProviderInvocation)
	}
	if catalog.Evidence.Certification != "NOT_CERTIFIED" {
		t.Errorf("expected certification NOT_CERTIFIED, got %s", catalog.Evidence.Certification)
	}
}

func TestValidSmartPreflightIsSideEffectFreeAndBlocked(t *testing.T) {
	server := NewGatewayServer()
	req := httptest.NewRequest("POST", "/agent/v1/repository-orchestrator/preflight", strings.NewReader(validSmartRequestJSON()))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var res PreflightResult
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("failed to unmarshal preflight response: %v", err)
	}

	if res.Status != "BLOCKED" {
		t.Errorf("expected status BLOCKED, got %s", res.Status)
	}
	if res.ValidationStatus != "VALID" {
		t.Errorf("expected validationStatus VALID, got %s", res.ValidationStatus)
	}
	if res.ConfigurationStatus != "NOT_CONFIGURED" {
		t.Errorf("expected configurationStatus NOT_CONFIGURED, got %s", res.ConfigurationStatus)
	}
	if res.Selection == nil {
		t.Fatalf("expected selection snapshot to be non-nil")
	}
	if res.Selection.Mode != "smart" {
		t.Errorf("expected selection mode smart, got %s", res.Selection.Mode)
	}
	if res.Selection.SelectedModel != nil {
		t.Errorf("expected selection selectedModel to be nil, got %v", res.Selection.SelectedModel)
	}
	if res.Selection.SelectionSource != "api" {
		t.Errorf("expected selection selectionSource api, got %s", res.Selection.SelectionSource)
	}
	if res.Selection.LockedByUser {
		t.Errorf("expected selection lockedByUser to be false")
	}
	if res.Selection.FallbackPolicy != "router_policy" {
		t.Errorf("expected selection fallbackPolicy router_policy, got %s", res.Selection.FallbackPolicy)
	}
	if !res.Selection.Immutable {
		t.Errorf("expected selection immutable to be true")
	}
	if res.Dag.Status != "NOT_RUN" {
		t.Errorf("expected dag.status NOT_RUN, got %s", res.Dag.Status)
	}
	if res.Cost.Status != "NOT_CONFIGURED" {
		t.Errorf("expected cost.status NOT_CONFIGURED, got %s", res.Cost.Status)
	}
	if res.Evidence.RunCreation != "NOT_RUN" {
		t.Errorf("expected runCreation NOT_RUN, got %s", res.Evidence.RunCreation)
	}
	if res.Evidence.WorkspaceMutation != "NOT_RUN" {
		t.Errorf("expected workspaceMutation NOT_RUN, got %s", res.Evidence.WorkspaceMutation)
	}
	if res.Evidence.ScmEffects != "NOT_RUN" {
		t.Errorf("expected scmEffects NOT_RUN, got %s", res.Evidence.ScmEffects)
	}
}

func TestClientRuntimeProfilesAndUnknownModelsAreRejected(t *testing.T) {
	server := NewGatewayServer()

	// Injected fields
	injected := strings.Replace(
		validSmartRequestJSON(),
		`"risk": {`,
		`"runtimeProfiles": {}, "selectionSource": "ui", "lockedByUser": true, "resolvedModel": "gpt-5.6-sol-max", "risk": {`,
		1,
	)

	req1 := httptest.NewRequest("POST", "/agent/v1/repository-orchestrator/preflight", strings.NewReader(injected))
	req1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	server.ServeHTTP(w1, req1)

	if w1.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400 for injected request, got %d: %s", w1.Code, w1.Body.String())
	}

	var res1 PreflightResult
	if err := json.Unmarshal(w1.Body.Bytes(), &res1); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	if res1.Status != "BLOCKED" || res1.ValidationStatus != "INVALID" {
		t.Errorf("expected BLOCKED/INVALID, got %s/%s", res1.Status, res1.ValidationStatus)
	}
	if len(res1.Reasons) != 4 {
		t.Errorf("expected 4 rejection reasons, got %d (%v)", len(res1.Reasons), res1.Reasons)
	}

	// Unknown model
	unknownModelReq := strings.Replace(
		strings.Replace(validSmartRequestJSON(), `"mode": "smart"`, `"mode": "manual"`, 1),
		`"selectedModel": null`,
		`"selectedModel": "unknown-model", "fallbackPolicy": "strict"`,
		1,
	)
	req2 := httptest.NewRequest("POST", "/agent/v1/repository-orchestrator/preflight", strings.NewReader(unknownModelReq))
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	server.ServeHTTP(w2, req2)

	if w2.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400 for unknown model, got %d", w2.Code)
	}
	var res2 PreflightResult
	if err := json.Unmarshal(w2.Body.Bytes(), &res2); err != nil {
		t.Fatalf("failed to unmarshal: %v", err)
	}
	foundUnknown := false
	for _, r := range res2.Reasons {
		if r == "MODEL_ALIAS_NOT_ALLOWLISTED:unknown-model" {
			foundUnknown = true
			break
		}
	}
	if !foundUnknown {
		t.Errorf("expected MODEL_ALIAS_NOT_ALLOWLISTED:unknown-model in reasons, got %v", res2.Reasons)
	}
}

func TestProviderPlansRemainPolicyOnlyAndFailClosed(t *testing.T) {
	server := NewGatewayServer()

	// CODEX
	reqCodex := httptest.NewRequest("GET", "/agent/v1/provider-plans/CODEX?taskFile=/tasks/repair.json", nil)
	wCodex := httptest.NewRecorder()
	server.ServeHTTP(wCodex, reqCodex)
	if wCodex.Code != http.StatusOK {
		t.Fatalf("expected 200 for CODEX, got %d", wCodex.Code)
	}
	var planCodex ProviderCommandPlan
	if err := json.Unmarshal(wCodex.Body.Bytes(), &planCodex); err != nil {
		t.Fatalf("failed to unmarshal plan: %v", err)
	}
	if planCodex.NetworkEnabled || planCodex.DockerSocketMounted {
		t.Errorf("expected networkEnabled & dockerSocketMounted false")
	}

	// HUMAN escalation -> 400 Bad Request
	reqHuman := httptest.NewRequest("GET", "/agent/v1/provider-plans/HUMAN?taskFile=/tasks/repair.json", nil)
	wHuman := httptest.NewRecorder()
	server.ServeHTTP(wHuman, reqHuman)
	if wHuman.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for HUMAN, got %d", wHuman.Code)
	}
	var errResp ErrorResponse
	if err := json.Unmarshal(wHuman.Body.Bytes(), &errResp); err != nil {
		t.Fatalf("failed to unmarshal error: %v", err)
	}
	if errResp.ErrorCode != "AGENT_REQUEST_REJECTED" {
		t.Errorf("expected AGENT_REQUEST_REJECTED, got %s", errResp.ErrorCode)
	}

	// Execution Capability
	reqExec := httptest.NewRequest("GET", "/agent/v1/execution-capability", nil)
	wExec := httptest.NewRecorder()
	server.ServeHTTP(wExec, reqExec)
	if wExec.Code != http.StatusOK {
		t.Fatalf("expected 200 for execution capability, got %d", wExec.Code)
	}
	var execCap map[string]any
	if err := json.Unmarshal(wExec.Body.Bytes(), &execCap); err != nil {
		t.Fatalf("failed to unmarshal exec cap: %v", err)
	}
	if execCap["configured"] != false {
		t.Errorf("expected configured: false, got %v", execCap["configured"])
	}
	if execCap["reasonCode"] != "AGENT_EXECUTOR_NOT_CONFIGURED" {
		t.Errorf("expected AGENT_EXECUTOR_NOT_CONFIGURED, got %v", execCap["reasonCode"])
	}
}

func TestHealthCheck(t *testing.T) {
	server := NewGatewayServer()
	req := httptest.NewRequest("GET", "/actuator/health", nil)
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200 for health, got %d", w.Code)
	}
	if !strings.Contains(w.Body.String(), `"status":"UP"`) {
		t.Errorf("expected status UP, got %s", w.Body.String())
	}
}

func TestNormalizeEndpoint(t *testing.T) {
	server := NewGatewayServer()
	payload := `{
		"failure": {
			"source": "ci-build-1",
			"stage": "COMPILE",
			"module": "core-engine",
			"exitCode": 1,
			"log": "ERROR: cannot find symbol class OrderService in /Users/dev/project/Order.java password=secret123",
			"metadata": {}
		}
	}`
	req := httptest.NewRequest("POST", "/agent/v1/failures/normalize", bytes.NewBufferString(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	server.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", w.Code, w.Body.String())
	}
	var res map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("unmarshal error: %v", err)
	}
	if res["category"] != "MISSING_SYMBOL" {
		t.Errorf("expected MISSING_SYMBOL, got %v", res["category"])
	}
	if res["symbol"] != "OrderService" {
		t.Errorf("expected OrderService, got %v", res["symbol"])
	}
	msg := res["normalizedMessage"].(string)
	if strings.Contains(msg, "secret123") {
		t.Errorf("expected password to be redacted, got: %s", msg)
	}
	if strings.Contains(msg, "/Users/dev") {
		t.Errorf("expected path to be sanitized, got: %s", msg)
	}
}
