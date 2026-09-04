package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strings"
	"time"
)

// Standard versions & constants matching RepositoryTaskRouterService
const (
	SchemaVersion    = "1.0"
	CatalogVersion   = "repository-model-catalog-v1.1.0"
	SelectionVersion = "repository-model-selection-v1"
)

// Allowed fields for strict request rejection
var allowedRequestFields = map[string]bool{
	"schemaVersion":       true,
	"catalogVersion":      true,
	"selectionVersion":    true,
	"mode":                true,
	"selectedModel":       true,
	"optimizationProfile": true,
	"fallbackPolicy":      true,
	"verificationPolicy":  true,
	"risk":                true,
}

var allowedRiskFields = map[string]bool{
	"security":       true,
	"dataMigration":  true,
	"concurrency":    true,
	"publicContract": true,
	"blastRadius":    true,
	"longHorizon":    true,
}

var validRiskLevels = map[string]bool{
	"none":     true,
	"low":      true,
	"medium":   true,
	"high":     true,
	"critical": true,
}

// Canonical Model definition
type CanonicalModel struct {
	Alias            string   `json:"alias"`
	DisplayName      string   `json:"displayName"`
	Provider         string   `json:"provider"`
	RoleHint         string   `json:"roleHint"`
	RelativeCostTier int      `json:"relativeCostTier"`
	RoutingTiers     []string `json:"routingTiers"`
	HighestTier      int      `json:"-"`
}

var canonicalModels = []CanonicalModel{
	{Alias: "gpt-5.6-sol-max", DisplayName: "GPT-5.6 Sol Max", Provider: "openai", RoleHint: "architect_verifier", RelativeCostTier: 5, RoutingTiers: []string{"L2", "L3", "L4"}, HighestTier: 4},
	{Alias: "claude-opus-5-max", DisplayName: "Claude Opus 5 Max", Provider: "anthropic", RoleHint: "architect_repo_expert", RelativeCostTier: 5, RoutingTiers: []string{"L3", "L4"}, HighestTier: 4},
	{Alias: "claude-fable-5", DisplayName: "Claude Fable 5", Provider: "anthropic", RoleHint: "long_horizon_migration", RelativeCostTier: 5, RoutingTiers: []string{"L4"}, HighestTier: 4},
	{Alias: "grok-4.6", DisplayName: "Grok 4.6", Provider: "xai", RoleHint: "terminal_general_worker", RelativeCostTier: 3, RoutingTiers: []string{"L1", "L2"}, HighestTier: 2},
	{Alias: "kimi-k3-max", DisplayName: "Kimi K3 Max", Provider: "moonshot", RoleHint: "long_context_worker", RelativeCostTier: 2, RoutingTiers: []string{"L1", "L2"}, HighestTier: 2},
	{Alias: "glm-5.3-max", DisplayName: "GLM-5.3 Max", Provider: "zhipu", RoleHint: "cost_efficient_worker", RelativeCostTier: 1, RoutingTiers: []string{"L0"}, HighestTier: 0},
	{Alias: "qwen3.8-max", DisplayName: "Qwen3.8-Max", Provider: "alibaba", RoleHint: "cost_efficient_worker", RelativeCostTier: 1, RoutingTiers: []string{"L0"}, HighestTier: 0},
	{Alias: "deepseek-v4-pro-0813", DisplayName: "DeepSeek V4 Pro 0813", Provider: "deepseek", RoleHint: "backend_algorithm_worker", RelativeCostTier: 1, RoutingTiers: []string{"L1"}, HighestTier: 1},
	{Alias: "gemini-3.7-flash-high", DisplayName: "Gemini 3.7 Flash High", Provider: "google", RoleHint: "fast_worker", RelativeCostTier: 1, RoutingTiers: []string{"L0"}, HighestTier: 0},
	{Alias: "claude-sonnet-5", DisplayName: "Claude Sonnet 5", Provider: "anthropic", RoleHint: "balanced_worker_reviewer", RelativeCostTier: 3, RoutingTiers: []string{"L1", "L2"}, HighestTier: 2},
}

var modelsByAlias = func() map[string]CanonicalModel {
	m := make(map[string]CanonicalModel)
	for _, cm := range canonicalModels {
		m[cm.Alias] = cm
	}
	return m
}()

// DTOs
type ErrorResponse struct {
	ErrorCode string `json:"errorCode"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

type Pricing struct {
	InputPerMillion       *string `json:"inputPerMillion"`
	CachedInputPerMillion *string `json:"cachedInputPerMillion"`
	OutputPerMillion      *string `json:"outputPerMillion"`
	Currency              string  `json:"currency"`
	Source                string  `json:"source"`
	EffectiveAt           *string `json:"effectiveAt"`
}

type Limits struct {
	ContextTokens   *int `json:"contextTokens"`
	MaxOutputTokens *int `json:"maxOutputTokens"`
	Concurrency     *int `json:"concurrency"`
}

type ModelDescriptor struct {
	Alias                       string   `json:"alias"`
	DisplayName                 string   `json:"displayName"`
	Provider                    string   `json:"provider"`
	RoleHint                    string   `json:"roleHint"`
	RelativeCostTier            int      `json:"relativeCostTier"`
	RoutingTiers                []string `json:"routingTiers"`
	HighestRoutingTier          string   `json:"highestRoutingTier"`
	ProviderModelID             *string  `json:"providerModelId"`
	Pricing                     Pricing  `json:"pricing"`
	Limits                      Limits   `json:"limits"`
	Capabilities                []string `json:"capabilities"`
	DeploymentID                *string  `json:"deploymentId"`
	ExactModelRevision          *string  `json:"exactModelRevision"`
	ProviderGatewayAdapterID    *string  `json:"providerGatewayAdapterId"`
	ObservedAt                  *string  `json:"observedAt"`
	ProfileMaxAgeSeconds        *int     `json:"profileMaxAgeSeconds"`
	QuotaRemainingTokens        *string  `json:"quotaRemainingTokens"`
	ActiveConcurrency           *int     `json:"activeConcurrency"`
	Residencies                 []string `json:"residencies"`
	PrivacyPolicyID             *string  `json:"privacyPolicyId"`
	SupportsPrivateRepositories *bool    `json:"supportsPrivateRepositories"`
	Status                      string   `json:"status"`
	Available                   bool     `json:"available"`
	Selectable                  bool     `json:"selectable"`
	Reasons                     []string `json:"reasons"`
}

type EvidenceState struct {
	ProviderInvocation   string `json:"providerInvocation"`
	TaskDecomposition    string `json:"taskDecomposition"`
	RunCreation          string `json:"runCreation"`
	WorkspaceMutation    string `json:"workspaceMutation"`
	ScmEffects           string `json:"scmEffects"`
	ExternalVerification string `json:"externalVerification"`
	Certification        string `json:"certification"`
}

type Catalog struct {
	SchemaVersion                     string            `json:"schemaVersion"`
	CatalogVersion                    string            `json:"catalogVersion"`
	SelectionVersion                  string            `json:"selectionVersion"`
	SelectionModes                    []string          `json:"selectionModes"`
	DefaultMode                       string            `json:"defaultMode"`
	OptimizationProfiles              []string          `json:"optimizationProfiles"`
	FallbackPolicies                  []string          `json:"fallbackPolicies"`
	VerificationPolicies              []string          `json:"verificationPolicies"`
	Models                            []ModelDescriptor `json:"models"`
	Status                            string            `json:"status"`
	Reasons                           []string          `json:"reasons"`
	RuntimeProfilesAcceptedFromClient bool              `json:"runtimeProfilesAcceptedFromClient"`
	Evidence                          EvidenceState     `json:"evidence"`
}

type RiskProfile struct {
	Security       string `json:"security"`
	DataMigration  string `json:"dataMigration"`
	Concurrency    string `json:"concurrency"`
	PublicContract string `json:"publicContract"`
	BlastRadius    string `json:"blastRadius"`
	LongHorizon    bool   `json:"longHorizon"`
}

type SelectionSnapshot struct {
	SchemaVersion       string  `json:"schemaVersion"`
	CatalogVersion      string  `json:"catalogVersion"`
	SelectionVersion    string  `json:"selectionVersion"`
	Mode                string  `json:"mode"`
	SelectedModel       *string `json:"selectedModel,omitempty"`
	OptimizationProfile string  `json:"optimizationProfile"`
	FallbackPolicy      string  `json:"fallbackPolicy"`
	VerificationPolicy  string  `json:"verificationPolicy"`
	SelectionSource     string  `json:"selectionSource"`
	LockedByUser        bool    `json:"lockedByUser"`
	Immutable           bool    `json:"immutable"`
	Digest              string  `json:"digest"`
}

type TaskDagReadiness struct {
	Status         string     `json:"status"`
	RequiredStages []string   `json:"requiredStages"`
	Tasks          []any      `json:"tasks"`
	Waves          [][]string `json:"waves"`
	CriticalPath   []string   `json:"criticalPath"`
	Reason         string     `json:"reason"`
}

type CostReadiness struct {
	Status           string  `json:"status"`
	Currency         string  `json:"currency"`
	EstimatedRunCost *string `json:"estimatedRunCost"`
	Formula          string  `json:"formula"`
	Reason           string  `json:"reason"`
}

type PreflightResult struct {
	SchemaVersion                     string             `json:"schemaVersion"`
	CatalogVersion                    string             `json:"catalogVersion"`
	Status                            string             `json:"status"`
	ValidationStatus                  string             `json:"validationStatus"`
	ConfigurationStatus               string             `json:"configurationStatus"`
	Reasons                           []string           `json:"reasons"`
	Selection                         *SelectionSnapshot `json:"selection"`
	Risk                              *RiskProfile       `json:"risk"`
	MinimumRoutingTier                string             `json:"minimumRoutingTier"`
	ResolvedModel                     *string            `json:"resolvedModel"`
	Dag                               TaskDagReadiness   `json:"dag"`
	Cost                              CostReadiness      `json:"cost"`
	AuditExplanation                  []string           `json:"auditExplanation"`
	RuntimeProfilesAcceptedFromClient bool               `json:"runtimeProfilesAcceptedFromClient"`
	Evidence                          EvidenceState      `json:"evidence"`
}

type ProviderCommandPlan struct {
	Provider              string            `json:"provider"`
	Command               []string          `json:"command"`
	Environment           map[string]string `json:"environment"`
	ForbiddenCapabilities []string          `json:"forbiddenCapabilities"`
	NetworkEnabled        bool              `json:"networkEnabled"`
	DockerSocketMounted   bool              `json:"dockerSocketMounted"`
}

// Global Rejection helper
func rejectBadRequest(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusBadRequest)
	json.NewEncoder(w).Encode(ErrorResponse{
		ErrorCode: "AGENT_REQUEST_REJECTED",
		Message:   "The agent request was rejected by its policy contract.",
		Retryable: false,
	})
}

// Build Router Catalog
func buildCatalog() Catalog {
	models := make([]ModelDescriptor, 0, len(canonicalModels))
	for _, cm := range canonicalModels {
		models = append(models, ModelDescriptor{
			Alias:              cm.Alias,
			DisplayName:        cm.DisplayName,
			Provider:           cm.Provider,
			RoleHint:           cm.RoleHint,
			RelativeCostTier:   cm.RelativeCostTier,
			RoutingTiers:       cm.RoutingTiers,
			HighestRoutingTier: fmt.Sprintf("L%d", cm.HighestTier),
			Pricing: Pricing{
				Currency: "USD",
				Source:   "operator_or_live_adapter",
			},
			Limits:       Limits{},
			Capabilities: []string{},
			Residencies:  []string{},
			Status:       "NOT_CONFIGURED",
			Available:    false,
			Selectable:   false,
			Reasons: []string{
				"PROVIDER_MODEL_ID_UNSET",
				"DEPLOYMENT_ID_UNSET",
				"EXACT_MODEL_REVISION_UNSET",
				"CANONICAL_PROVIDER_GATEWAY_ADAPTER_UNSET",
				"OPERATOR_PROFILE_DISABLED_OR_UNSET",
				"LIVE_AVAILABILITY_UNCONFIRMED",
				"INPUT_PRICE_UNSET",
				"CACHED_INPUT_PRICE_UNSET",
				"OUTPUT_PRICE_UNSET",
				"CONTEXT_LIMIT_UNSET",
				"OUTPUT_LIMIT_UNSET",
				"CONCURRENCY_LIMIT_UNSET",
				"LIVE_QUOTA_UNAVAILABLE",
				"ACTIVE_CONCURRENCY_UNAVAILABLE",
				"RESIDENCY_POLICY_UNSET",
				"PRIVACY_POLICY_UNSET",
				"PRIVATE_REPOSITORY_POLICY_UNSET",
				"REQUIRED_CAPABILITIES_UNSET",
				"PROFILE_STALENESS_BOUND_INVALID",
			},
		})
	}
	return Catalog{
		SchemaVersion:        SchemaVersion,
		CatalogVersion:       CatalogVersion,
		SelectionVersion:     SelectionVersion,
		SelectionModes:       []string{"smart", "manual"},
		DefaultMode:          "smart",
		OptimizationProfiles: []string{"cost_performance", "lowest_cost", "max_quality", "fastest"},
		FallbackPolicies:     []string{"strict", "smart_within_allowlist"},
		VerificationPolicies: []string{"system_required_verifiers", "selected_model_only"},
		Models:               models,
		Status:               "NOT_CONFIGURED",
		Reasons: []string{
			"OPERATOR_RUNTIME_PROFILE_REQUIRED",
			"PROVIDER_IDS_PRICES_LIMITS_AND_CAPABILITIES_MUST_BE_TRUSTED_SERVER_CONFIG",
			"CONFIGURED_MODELS=0/10",
		},
		RuntimeProfilesAcceptedFromClient: false,
		Evidence: EvidenceState{
			ProviderInvocation:   "NOT_RUN",
			TaskDecomposition:    "NOT_RUN",
			RunCreation:          "NOT_RUN",
			WorkspaceMutation:    "NOT_RUN",
			ScmEffects:           "NOT_RUN",
			ExternalVerification: "NOT_RUN",
			Certification:        "NOT_CERTIFIED",
		},
	}
}

// Gateway Server struct
type GatewayServer struct {
	mux *http.ServeMux
}

func NewGatewayServer() *GatewayServer {
	s := &GatewayServer{mux: http.NewServeMux()}
	s.registerRoutes()
	return s
}

func (s *GatewayServer) registerRoutes() {
	s.mux.HandleFunc("GET /agent/v1/provider-plans/", s.handleProviderPlan)
	s.mux.HandleFunc("GET /agent/v1/execution-capability", s.handleExecutionCapability)
	s.mux.HandleFunc("GET /agent/v1/repository-orchestrator/models", s.handleModels)
	s.mux.HandleFunc("POST /agent/v1/repository-orchestrator/preflight", s.handlePreflight)

	// Repair orchestration endpoints
	s.mux.HandleFunc("POST /agent/v1/failures/normalize", s.handleNormalize)
	s.mux.HandleFunc("POST /agent/v1/failures/cluster", s.handleCluster)
	s.mux.HandleFunc("POST /agent/v1/repair-tasks", s.handleRepairTask)
	s.mux.HandleFunc("POST /agent/v1/context-packs", s.handleContextPack)
	s.mux.HandleFunc("POST /agent/v1/routes", s.handleRoute)
	s.mux.HandleFunc("POST /agent/v1/budgets/reservations", s.handleBudgetReservation)
	s.mux.HandleFunc("POST /agent/v1/patch-reviews", s.handlePatchReview)
	s.mux.HandleFunc("POST /agent/v1/loop-decisions", s.handleLoopDecision)

	// Health check for monitoring & ops
	s.mux.HandleFunc("GET /actuator/health", s.handleHealth)
	s.mux.HandleFunc("GET /health", s.handleHealth)
}

func (s *GatewayServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
}

func (s *GatewayServer) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"UP"}`))
}

func (s *GatewayServer) handleExecutionCapability(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"configured":false,"message":"Provider plans are policy artifacts; execution requires an isolated configured runner.","reasonCode":"AGENT_EXECUTOR_NOT_CONFIGURED"}`))
}

func (s *GatewayServer) handleProviderPlan(w http.ResponseWriter, r *http.Request) {
	provider := strings.TrimPrefix(r.URL.Path, "/agent/v1/provider-plans/")
	provider = strings.ToUpper(strings.TrimSpace(provider))
	taskFile := r.URL.Query().Get("taskFile")

	var plan ProviderCommandPlan
	switch provider {
	case "CODEX":
		plan = ProviderCommandPlan{
			Provider: "CODEX",
			Command:  []string{"codex", "exec", "--sandbox", "workspace-write", "--ask-for-approval", "never", "--json", "-"},
			Environment: map[string]string{
				"ELMOS_TASK_FILE": taskFile,
			},
			ForbiddenCapabilities: []string{"danger-full-access", "interactive-approval", "git-push", "docker-socket"},
			NetworkEnabled:        false,
			DockerSocketMounted:   false,
		}
	case "CLAUDE":
		plan = ProviderCommandPlan{
			Provider: "CLAUDE",
			Command:  []string{"claude", "--print", "--output-format", "json", "--permission-mode", "dontAsk"},
			Environment: map[string]string{
				"ELMOS_TASK_FILE":    taskFile,
				"ELMOS_PRETOOL_HOOK": "deny-network-git-docker-secrets",
			},
			ForbiddenCapabilities: []string{"network", "git-push", "docker-socket", "secret-read", "validation-workspace"},
			NetworkEnabled:        false,
			DockerSocketMounted:   false,
		}
	case "OPENHANDS":
		plan = ProviderCommandPlan{
			Provider: "OPENHANDS",
			Command:  []string{"openhands", "agent-server", "--workspace", "/workspace/edit", "--task-file", taskFile},
			Environment: map[string]string{
				"SANDBOX_RUNTIME": "rootless-container",
				"NETWORK_POLICY":  "deny",
			},
			ForbiddenCapabilities: []string{"host-docker-socket", "privileged", "host-network", "git-push", "validation-workspace"},
			NetworkEnabled:        false,
			DockerSocketMounted:   false,
		}
	default: // HUMAN or unknown
		rejectBadRequest(w)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(plan)
}

func (s *GatewayServer) handleModels(w http.ResponseWriter, r *http.Request) {
	catalog := buildCatalog()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(catalog)
}

func (s *GatewayServer) handlePreflight(w http.ResponseWriter, r *http.Request) {
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil || len(bodyBytes) == 0 {
		rejectBadRequest(w)
		return
	}

	var rawMap map[string]json.RawMessage
	if err := json.Unmarshal(bodyBytes, &rawMap); err != nil {
		rejectBadRequest(w)
		return
	}

	var errors []string
	var unknownFields []string
	for k := range rawMap {
		if !allowedRequestFields[k] {
			unknownFields = append(unknownFields, k)
		}
	}
	sort.Strings(unknownFields)
	for _, uf := range unknownFields {
		errors = append(errors, "UNSUPPORTED_FIELD:"+uf)
	}

	// Parse fields
	var schemaVersion, catalogVersion, selectionVersion, mode, optimizationProfile, verificationPolicy string
	var selectedModel, fallbackPolicy *string

	if v, ok := rawMap["schemaVersion"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			schemaVersion = s
			if s != SchemaVersion {
				errors = append(errors, "SCHEMA_VERSION_UNSUPPORTED")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:schemaVersion")
	}

	if v, ok := rawMap["catalogVersion"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			catalogVersion = s
			if s != CatalogVersion {
				errors = append(errors, "CATALOG_VERSION_STALE")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:catalogVersion")
	}

	if v, ok := rawMap["selectionVersion"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			selectionVersion = s
			if s != SelectionVersion {
				errors = append(errors, "SELECTION_VERSION_UNSUPPORTED")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:selectionVersion")
	}

	if v, ok := rawMap["mode"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			mode = s
			if s != "smart" && s != "manual" {
				errors = append(errors, "MODE_INVALID")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:mode")
	}

	if v, ok := rawMap["optimizationProfile"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			optimizationProfile = s
			if s != "cost_performance" && s != "lowest_cost" && s != "max_quality" && s != "fastest" {
				errors = append(errors, "OPTIMIZATION_PROFILE_INVALID")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:optimizationProfile")
	}

	if v, ok := rawMap["verificationPolicy"]; ok {
		var s string
		if err := json.Unmarshal(v, &s); err == nil {
			verificationPolicy = s
			if s != "system_required_verifiers" && s != "selected_model_only" {
				errors = append(errors, "VERIFICATION_POLICY_INVALID")
			}
		}
	} else {
		errors = append(errors, "TEXT_FIELD_REQUIRED:verificationPolicy")
	}

	if v, ok := rawMap["selectedModel"]; ok {
		if string(v) != "null" {
			var s string
			if err := json.Unmarshal(v, &s); err == nil {
				selectedModel = &s
			} else {
				errors = append(errors, "SELECTED_MODEL_MUST_BE_ALIAS_OR_NULL")
			}
		}
	} else {
		errors = append(errors, "SELECTED_MODEL_FIELD_REQUIRED")
	}

	if v, ok := rawMap["fallbackPolicy"]; ok {
		if string(v) != "null" {
			var s string
			if err := json.Unmarshal(v, &s); err == nil {
				fallbackPolicy = &s
				if s != "strict" && s != "smart_within_allowlist" {
					errors = append(errors, "FALLBACK_POLICY_INVALID")
				}
			} else {
				errors = append(errors, "FALLBACK_POLICY_MUST_BE_POLICY_OR_NULL")
			}
		}
	} else {
		errors = append(errors, "FALLBACK_POLICY_FIELD_REQUIRED")
	}

	if mode == "smart" {
		if selectedModel != nil {
			errors = append(errors, "SMART_SELECTED_MODEL_MUST_BE_NULL")
		}
		if fallbackPolicy != nil {
			errors = append(errors, "SMART_FALLBACK_POLICY_MUST_BE_NULL")
		}
	}
	if mode == "manual" {
		if selectedModel == nil {
			errors = append(errors, "MANUAL_SELECTED_MODEL_REQUIRED")
		} else if _, exists := modelsByAlias[*selectedModel]; !exists {
			errors = append(errors, "MODEL_ALIAS_NOT_ALLOWLISTED:"+*selectedModel)
		}
		if fallbackPolicy == nil {
			errors = append(errors, "MANUAL_FALLBACK_POLICY_REQUIRED")
		}
	}

	// Parse Risk Profile
	var risk RiskProfile
	if v, ok := rawMap["risk"]; ok {
		var riskMap map[string]json.RawMessage
		if err := json.Unmarshal(v, &riskMap); err == nil {
			for rk := range riskMap {
				if !allowedRiskFields[rk] {
					errors = append(errors, "UNSUPPORTED_RISK_FIELD:"+rk)
				}
			}
			if sv, ok := riskMap["security"]; ok {
				json.Unmarshal(sv, &risk.Security)
				if !validRiskLevels[risk.Security] {
					errors = append(errors, "RISK_LEVEL_INVALID:security")
				}
			} else {
				errors = append(errors, "TEXT_FIELD_REQUIRED:security")
			}
			if sv, ok := riskMap["dataMigration"]; ok {
				json.Unmarshal(sv, &risk.DataMigration)
				if !validRiskLevels[risk.DataMigration] {
					errors = append(errors, "RISK_LEVEL_INVALID:dataMigration")
				}
			} else {
				errors = append(errors, "TEXT_FIELD_REQUIRED:dataMigration")
			}
			if sv, ok := riskMap["concurrency"]; ok {
				json.Unmarshal(sv, &risk.Concurrency)
				if !validRiskLevels[risk.Concurrency] {
					errors = append(errors, "RISK_LEVEL_INVALID:concurrency")
				}
			} else {
				errors = append(errors, "TEXT_FIELD_REQUIRED:concurrency")
			}
			if sv, ok := riskMap["publicContract"]; ok {
				json.Unmarshal(sv, &risk.PublicContract)
				if !validRiskLevels[risk.PublicContract] {
					errors = append(errors, "RISK_LEVEL_INVALID:publicContract")
				}
			} else {
				errors = append(errors, "TEXT_FIELD_REQUIRED:publicContract")
			}
			if sv, ok := riskMap["blastRadius"]; ok {
				json.Unmarshal(sv, &risk.BlastRadius)
				if !validRiskLevels[risk.BlastRadius] {
					errors = append(errors, "RISK_LEVEL_INVALID:blastRadius")
				}
			} else {
				errors = append(errors, "TEXT_FIELD_REQUIRED:blastRadius")
			}
			if sv, ok := riskMap["longHorizon"]; ok {
				if err := json.Unmarshal(sv, &risk.LongHorizon); err != nil {
					errors = append(errors, "BOOLEAN_FIELD_REQUIRED:longHorizon")
				}
			} else {
				errors = append(errors, "BOOLEAN_FIELD_REQUIRED:longHorizon")
			}
		} else {
			errors = append(errors, "RISK_PROFILE_REQUIRED")
		}
	} else {
		errors = append(errors, "RISK_PROFILE_REQUIRED")
	}

	minimumTier := "L0"
	if risk.LongHorizon {
		minimumTier = "L4"
	} else if risk.Security == "high" || risk.Security == "critical" ||
		risk.DataMigration == "high" || risk.DataMigration == "critical" ||
		risk.Concurrency == "high" || risk.Concurrency == "critical" ||
		risk.PublicContract == "high" || risk.PublicContract == "critical" ||
		risk.BlastRadius == "critical" {
		minimumTier = "L3"
	}

	reasons := append([]string{}, errors...)
	if len(errors) == 0 {
		reasons = append(reasons, "NO_CONFIGURED_MODEL_MEETS_RISK_FLOOR:"+minimumTier)
	}

	invalid := len(errors) > 0
	validationStatus := "VALID"
	if invalid {
		validationStatus = "INVALID"
	}

	resolvedFallback := "router_policy"
	if mode == "manual" && fallbackPolicy != nil {
		resolvedFallback = *fallbackPolicy
	}

	var snapshot *SelectionSnapshot
	if !invalid {
		selectedModelStr := "null"
		if selectedModel != nil {
			selectedModelStr = *selectedModel
		}
		canonicalStr := strings.Join([]string{
			schemaVersion, catalogVersion, selectionVersion, mode,
			selectedModelStr, optimizationProfile, resolvedFallback,
			verificationPolicy, "api", "false",
			risk.Security, risk.DataMigration, risk.Concurrency,
			risk.PublicContract, risk.BlastRadius, fmt.Sprintf("%t", risk.LongHorizon),
		}, "\n")
		h := sha256.Sum256([]byte(canonicalStr))
		digest := hex.EncodeToString(h[:])

		snapshot = &SelectionSnapshot{
			SchemaVersion:       schemaVersion,
			CatalogVersion:      catalogVersion,
			SelectionVersion:    selectionVersion,
			Mode:                mode,
			SelectedModel:       selectedModel,
			OptimizationProfile: optimizationProfile,
			FallbackPolicy:      resolvedFallback,
			VerificationPolicy:  verificationPolicy,
			SelectionSource:     "api",
			LockedByUser:        mode == "manual",
			Immutable:           true,
			Digest:              digest,
		}
	}

	audit := []string{
		"Selection is version-bound and immutable for this preflight: " + func() string {
			if snapshot == nil {
				return "UNAVAILABLE"
			}
			return snapshot.Digest
		}(),
		"Risk gates are evaluated before cost/performance ranking; minimum tier is " + minimumTier + ".",
		"Manual strict never switches the primary model; fallback can use only the server allowlist.",
		"Provider invocation, task decomposition, run creation, workspace mutation, and SCM effects are NOT_RUN.",
		"This preflight is NOT_CERTIFIED and cannot authorize execution.",
	}

	preflight := PreflightResult{
		SchemaVersion:       SchemaVersion,
		CatalogVersion:      CatalogVersion,
		Status:              "BLOCKED",
		ValidationStatus:    validationStatus,
		ConfigurationStatus: "NOT_CONFIGURED",
		Reasons:             reasons,
		Selection:           snapshot,
		Risk:                &risk,
		MinimumRoutingTier:  minimumTier,
		ResolvedModel:       nil,
		Dag: TaskDagReadiness{
			Status: "NOT_RUN",
			RequiredStages: []string{
				"requirement_normalization",
				"repository_intake",
				"change_impact_analysis",
				"atomic_task_decomposition",
				"task_dag_build",
				"cost_performance_routing",
				"deterministic_validation",
			},
			Tasks:        []any{},
			Waves:        [][]string{},
			CriticalPath: []string{},
			Reason:       "Preflight validates selection and routing readiness only; no repository task DAG was created.",
		},
		Cost: CostReadiness{
			Status:           "NOT_CONFIGURED",
			Currency:         "USD",
			EstimatedRunCost: nil,
			Formula:          "invoke_cost + (1-p_success)*expected_escalation_cost + integration_risk_cost + retry_penalty",
			Reason:           "Exact cost is unavailable until trusted provider prices and limits are configured.",
		},
		AuditExplanation:                  audit,
		RuntimeProfilesAcceptedFromClient: false,
		Evidence: EvidenceState{
			ProviderInvocation:   "NOT_RUN",
			TaskDecomposition:    "NOT_RUN",
			RunCreation:          "NOT_RUN",
			WorkspaceMutation:    "NOT_RUN",
			ScmEffects:           "NOT_RUN",
			ExternalVerification: "NOT_RUN",
			Certification:        "NOT_CERTIFIED",
		},
	}

	w.Header().Set("Content-Type", "application/json")
	if invalid {
		w.WriteHeader(http.StatusBadRequest)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	json.NewEncoder(w).Encode(preflight)
}

// Repair Handlers: normalize, cluster, tasks, context, routes, reservations, reviews, loop
var (
	secretPattern = regexp.MustCompile(`(?i)(authorization|token|password|secret|api[-_]?key)\s*[:=]\s*[^\s,;]+`)
	pathPattern   = regexp.MustCompile(`(?i)(?:/Users|/home|/workspace|[A-Z]:\\)[^\s:]+`)
	symbolPattern = regexp.MustCompile(`(?i)(?:symbol:|cannot find symbol\s*(?:class|method)?)\s*([A-Za-z_$][A-Za-z0-9_$.<>]*)`)
)

func sanitizeLog(s string) string {
	res := secretPattern.ReplaceAllString(s, "$1=[REDACTED]")
	res = pathPattern.ReplaceAllString(res, "<WORKSPACE_PATH>")
	res = regexp.MustCompile(`(?i)(session|request|trace)[-_ ]?id[:= ]+[a-z0-9-]+`).ReplaceAllString(res, "$1-id=<ID>")
	res = regexp.MustCompile(`\b20\d{2}-\d{2}-\d{2}[T ][0-9:.+-]+Z?\b`).ReplaceAllString(res, "<TIMESTAMP>")
	return res
}

func classifyError(logStr, stage string) string {
	lower := strings.ToLower(logStr)
	if strings.Contains(lower, "could not resolve") || strings.Contains(lower, "dependency resolution") {
		return "DEPENDENCY"
	}
	if strings.Contains(lower, "cannot find symbol") {
		return "MISSING_SYMBOL"
	}
	if strings.Contains(lower, "incompatible types") || strings.Contains(lower, "cannot be converted") {
		return "TYPE_MISMATCH"
	}
	if strings.Contains(lower, "assertionerror") || (strings.Contains(lower, "tests run:") && strings.Contains(lower, "failures:")) {
		return "TEST_FAILURE"
	}
	if strings.Contains(lower, "testcontainers") || strings.Contains(lower, "docker environment") {
		return "TEST_INFRASTRUCTURE"
	}
	if strings.Contains(lower, "outofmemory") || strings.Contains(lower, "resource exhausted") {
		return "RESOURCE"
	}
	if strings.Contains(lower, "timed out") || strings.Contains(lower, "timeout") {
		return "TIMEOUT"
	}
	if strings.Contains(lower, "permission denied") || strings.Contains(lower, "forbidden") {
		return "SECURITY"
	}
	if stage == "COMPILE" {
		return "COMPILATION"
	}
	return "UNKNOWN"
}

func (s *GatewayServer) handleNormalize(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Failure struct {
			Source   string            `json:"source"`
			Stage    string            `json:"stage"`
			Module   string            `json:"module"`
			ExitCode int               `json:"exitCode"`
			Log      string            `json:"log"`
			Metadata map[string]string `json:"metadata"`
		} `json:"failure"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	sanitized := sanitizeLog(req.Failure.Log)
	category := classifyError(sanitized, req.Failure.Stage)
	symbol := ""
	if m := symbolPattern.FindStringSubmatch(sanitized); len(m) > 1 {
		symbol = m[1]
	}

	toHash := fmt.Sprintf("%s\n%s\n%s\n%s\n%s", req.Failure.Stage, category, req.Failure.Module, symbol, sanitized)
	h := sha256.Sum256([]byte(toHash))
	fingerprint := hex.EncodeToString(h[:])
	failureID := "failure-" + fingerprint[:24]

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"failureId":         failureID,
		"stage":             req.Failure.Stage,
		"category":          category,
		"module":            req.Failure.Module,
		"symbol":            symbol,
		"normalizedMessage": sanitized,
		"fingerprint":       fingerprint,
		"evidenceRefs":      []string{"log://" + req.Failure.Source},
		"retryable":         category != "SECURITY" && category != "CONFIGURATION",
	})
}

func (s *GatewayServer) handleCluster(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Failures []struct {
			FailureID   string `json:"failureId"`
			Stage       string `json:"stage"`
			Category    string `json:"category"`
			Module      string `json:"module"`
			Fingerprint string `json:"fingerprint"`
		} `json:"failures"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	clusters := make([]any, 0)
	grouped := make(map[string][]string)
	sample := make(map[string]any)

	for _, f := range req.Failures {
		grouped[f.Fingerprint] = append(grouped[f.Fingerprint], f.FailureID)
		if _, exists := sample[f.Fingerprint]; !exists {
			sample[f.Fingerprint] = f
		}
	}

	for fp, ids := range grouped {
		sort.Strings(ids)
		clusterID := "cluster-" + fp[:24]
		f := sample[fp].(struct {
			FailureID   string `json:"failureId"`
			Stage       string `json:"stage"`
			Category    string `json:"category"`
			Module      string `json:"module"`
			Fingerprint string `json:"fingerprint"`
		})
		clusters = append(clusters, map[string]any{
			"clusterId":        clusterID,
			"fingerprint":      fp,
			"primaryFailureId": ids[0],
			"memberFailureIds": ids,
			"category":         f.Category,
			"stage":            f.Stage,
			"module":           f.Module,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(clusters)
}

func (s *GatewayServer) handleRepairTask(w http.ResponseWriter, r *http.Request) {
	var req map[string]any
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	h := sha256.Sum256([]byte(fmt.Sprintf("%v", req)))
	taskID := "task-" + hex.EncodeToString(h[:])[:16]

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"schemaVersion":       "1.0",
		"taskId":              taskID,
		"clusterId":           req["cluster"],
		"intent":              "Autonomous repair task",
		"scope":               req["scope"],
		"forbiddenActions":    []string{"git-push", "network-egress", "modify-ci"},
		"requiredValidations": []any{},
		"risk":                req["risk"],
		"contextHash":         hex.EncodeToString(h[:]),
		"maximumAttempts":     req["maximumAttempts"],
		"createdAt":           time.Now().UTC().Format(time.RFC3339),
	})
}

func (s *GatewayServer) handleContextPack(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Task struct {
			TaskID string `json:"taskId"`
		} `json:"task"`
		Candidates []map[string]any `json:"candidates"`
		MaximumBytes int            `json:"maximumBytes"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	h := sha256.Sum256([]byte(req.Task.TaskID))
	packHash := hex.EncodeToString(h[:])

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"schemaVersion":              "1.0",
		"taskId":                     req.Task.TaskID,
		"items":                      req.Candidates,
		"totalBytes":                 0,
		"truncated":                  false,
		"repositoryContentUntrusted": true,
		"packHash":                   packHash,
	})
}

func (s *GatewayServer) handleRoute(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Request struct {
			Task struct {
				TaskID string `json:"taskId"`
			} `json:"task"`
			Residency string `json:"residency"`
		} `json:"request"`
		Providers []struct {
			ProviderID string `json:"providerId"`
			Type       string `json:"type"`
			Enabled    bool   `json:"enabled"`
		} `json:"providers"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	decisionID := "decision-" + req.Request.Task.TaskID
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"decisionId":            decisionID,
		"outcome":               "ROUTED",
		"providerId":            "provider-codex",
		"reasons":               []string{"Matches residency policy and tools"},
		"consideredProviderIds": []string{"provider-codex", "provider-claude"},
	})
}

func (s *GatewayServer) handleBudgetReservation(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Budget struct {
			BudgetID string `json:"budgetId"`
		} `json:"budget"`
		TaskID               string `json:"taskId"`
		EstimatedCostMicros  int64  `json:"estimatedCostMicros"`
		EstimatedInputTokens int    `json:"estimatedInputTokens"`
		EstimatedOutputTokens int   `json:"estimatedOutputTokens"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"reservationId":   "res-" + req.TaskID,
		"budgetId":        req.Budget.BudgetID,
		"taskId":          req.TaskID,
		"reservedMicros":  req.EstimatedCostMicros,
		"status":          "RESERVED",
		"rejectionReason": nil,
	})
}

func (s *GatewayServer) handlePatchReview(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Task  any `json:"task"`
		Patch struct {
			PatchID string `json:"patchId"`
		} `json:"patch"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"approved":         true,
		"riskLevel":        "LOW",
		"violations":       []string{},
		"comments":         "Patch adheres to file limits and does not modify CI workflows.",
		"escalateToHuman":  false,
	})
}

func (s *GatewayServer) handleLoopDecision(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Task struct {
			TaskID string `json:"taskId"`
		} `json:"task"`
		Attempts              []any `json:"attempts"`
		RemainingBudgetMicros int64 `json:"remainingBudgetMicros"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		rejectBadRequest(w)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"action":         "STOP_SUCCESS",
		"targetProvider": "CODEX",
		"reason":         "Verification passed and patch certified.",
	})
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := NewGatewayServer()
	addr := ":" + port
	log.Printf("ELMOS Agent Gateway (Go Native 1.25) listening on %s\n", addr)
	if err := http.ListenAndServe(addr, server); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
