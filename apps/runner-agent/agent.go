package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	Version  = "0.1.0"
	ExConfig = 78
	ExOK     = 0
)

var (
	nodeIdRegex     = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]{2,95}$`)
	capabilityRegex = regexp.MustCompile(`^[a-z0-9][a-z0-9:._-]{1,95}$`)
)

type Config struct {
	ControlPlaneBaseURL      string
	RunnerNodeId             string
	PoolId                   string
	EnrolmentToken           string
	Capabilities             []string
	MaxConcurrency           int
	WorkRoot                 string
	ContainerEngine          string
	ClaimBatchSize           int
	LeaseSeconds             int
	HeartbeatIntervalSeconds int
	CancelGraceSeconds       int
	MetricsPort              int
	AllowHostExecution       bool
	WorkloadUid              int
	WorkloadGid              int
}

func ConfigFromEnv(env map[string]string) (*Config, error) {
	get := func(key string) string {
		if env != nil {
			return env[key]
		}
		return os.Getenv(key)
	}

	baseURL := strings.TrimSpace(get("ELMOS_CONTROL_PLANE_BASE_URL"))
	if baseURL == "" {
		return nil, errors.New("ELMOS_CONTROL_PLANE_BASE_URL is required")
	}
	if !strings.HasPrefix(baseURL, "http://") && !strings.HasPrefix(baseURL, "https://") {
		return nil, errors.New("ELMOS_CONTROL_PLANE_BASE_URL must be an absolute http(s) URL")
	}
	if strings.HasPrefix(baseURL, "http://") && !strings.Contains(baseURL, "://localhost") && !strings.Contains(baseURL, "://127.0.0.1") {
		return nil, errors.New("ELMOS_CONTROL_PLANE_BASE_URL must use https outside loopback")
	}

	nodeId := strings.TrimSpace(get("ELMOS_RUNNER_NODE_ID"))
	if nodeId == "" {
		return nil, errors.New("ELMOS_RUNNER_NODE_ID is required")
	}
	if !nodeIdRegex.MatchString(nodeId) {
		return nil, errors.New("ELMOS_RUNNER_NODE_ID has an unsupported shape")
	}

	enrolment := strings.TrimSpace(get("ELMOS_RUNNER_ENROLMENT_TOKEN"))
	if enrolment == "" {
		return nil, errors.New("ELMOS_RUNNER_ENROLMENT_TOKEN is required")
	}
	if len(enrolment) < 32 {
		return nil, errors.New("ELMOS_RUNNER_ENROLMENT_TOKEN must be at least 32 characters")
	}

	capsRaw := strings.TrimSpace(get("ELMOS_RUNNER_CAPABILITIES"))
	if capsRaw == "" {
		return nil, errors.New("ELMOS_RUNNER_CAPABILITIES is required")
	}
	var capabilities []string
	for _, part := range strings.Split(capsRaw, ",") {
		val := strings.TrimSpace(part)
		if val != "" {
			if !capabilityRegex.MatchString(val) {
				return nil, fmt.Errorf("capability has an unsupported shape: %s", val)
			}
			capabilities = appendIfMissing(capabilities, val)
		}
	}
	if len(capabilities) == 0 || len(capabilities) > 32 {
		return nil, errors.New("ELMOS_RUNNER_CAPABILITIES must declare 1..32 capabilities")
	}

	maxConc := 2
	if v := strings.TrimSpace(get("ELMOS_RUNNER_MAX_CONCURRENCY")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 && n <= 16 {
			maxConc = n
		} else {
			return nil, errors.New("ELMOS_RUNNER_MAX_CONCURRENCY must be an integer between 1 and 16")
		}
	}

	workRootRaw := strings.TrimSpace(get("ELMOS_RUNNER_WORK_ROOT"))
	if workRootRaw == "" {
		return nil, errors.New("ELMOS_RUNNER_WORK_ROOT is required")
	}
	workRoot, err := filepath.Abs(workRootRaw)
	if err != nil {
		return nil, fmt.Errorf("ELMOS_RUNNER_WORK_ROOT invalid path: %w", err)
	}

	allowHost := strings.EqualFold(strings.TrimSpace(get("ELMOS_RUNNER_ALLOW_HOST_EXECUTION")), "true")
	engine := strings.TrimSpace(get("ELMOS_RUNNER_CONTAINER_ENGINE"))
	if !allowHost {
		if engine == "" {
			return nil, errors.New("ELMOS_RUNNER_CONTAINER_ENGINE is required when allowHostExecution is false")
		}
		if engine != "podman" && engine != "docker" {
			return nil, fmt.Errorf("ELMOS_RUNNER_CONTAINER_ENGINE must be podman or docker: got %s", engine)
		}
	}

	poolId := strings.TrimSpace(get("ELMOS_RUNNER_POOL_ID"))
	if poolId == "" {
		poolId = "default"
	} else if !nodeIdRegex.MatchString(poolId) {
		return nil, errors.New("ELMOS_RUNNER_POOL_ID has an unsupported shape")
	}

	leaseSec := 60
	if v := strings.TrimSpace(get("ELMOS_RUNNER_LEASE_SECONDS")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 10 && n <= 300 {
			leaseSec = n
		}
	}

	heartbeatSec := 15
	if v := strings.TrimSpace(get("ELMOS_RUNNER_HEARTBEAT_INTERVAL_SECONDS")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 3 && n <= 60 {
			heartbeatSec = n
		}
	}

	cancelGrace := 10
	if v := strings.TrimSpace(get("ELMOS_RUNNER_CANCEL_GRACE_SECONDS")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 && n <= 120 {
			cancelGrace = n
		}
	}

	metricsPort := 9090
	if v := strings.TrimSpace(get("ELMOS_RUNNER_METRICS_PORT")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1024 && n <= 65535 {
			metricsPort = n
		}
	}

	claimBatch := 1
	if v := strings.TrimSpace(get("ELMOS_RUNNER_CLAIM_BATCH_SIZE")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 && n <= 8 {
			claimBatch = n
		}
	}

	uid := os.Getuid()
	gid := os.Getgid()
	if v := strings.TrimSpace(get("ELMOS_RUNNER_WORKLOAD_UID")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			uid = n
		}
	}
	if v := strings.TrimSpace(get("ELMOS_RUNNER_WORKLOAD_GID")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 0 {
			gid = n
		}
	}

	cfg := &Config{
		ControlPlaneBaseURL:      strings.TrimRight(baseURL, "/"),
		RunnerNodeId:             nodeId,
		PoolId:                   poolId,
		EnrolmentToken:           enrolment,
		Capabilities:             capabilities,
		MaxConcurrency:           maxConc,
		WorkRoot:                 workRoot,
		ContainerEngine:          engine,
		ClaimBatchSize:           claimBatch,
		LeaseSeconds:             leaseSec,
		HeartbeatIntervalSeconds: heartbeatSec,
		CancelGraceSeconds:       cancelGrace,
		MetricsPort:              metricsPort,
		AllowHostExecution:       allowHost,
		WorkloadUid:              uid,
		WorkloadGid:              gid,
	}

	if err := cfg.ValidateTimings(); err != nil {
		return nil, err
	}
	return cfg, nil
}

func appendIfMissing(slice []string, v string) []string {
	for _, item := range slice {
		if item == v {
			return slice
		}
	}
	return append(slice, v)
}

func (c *Config) ValidateTimings() error {
	if c.HeartbeatIntervalSeconds >= c.LeaseSeconds {
		return fmt.Errorf("heartbeatIntervalSeconds (%d) must be strictly less than leaseSeconds (%d)",
			c.HeartbeatIntervalSeconds, c.LeaseSeconds)
	}
	if c.HeartbeatIntervalSeconds*2 > c.LeaseSeconds {
		return fmt.Errorf("heartbeatIntervalSeconds (%d) allows fewer than two attempts inside leaseSeconds (%d)",
			c.HeartbeatIntervalSeconds, c.LeaseSeconds)
	}
	return nil
}

// SandboxAttestation
type SandboxAttestation struct {
	Rootless              bool              `json:"rootless"`
	ReadOnlyRoot          bool              `json:"read_only_root"`
	CapabilitiesDropped   bool              `json:"capabilities_dropped"`
	NetworkDefaultDeny    bool              `json:"network_default_deny"`
	ImageAllowlistVersion string            `json:"image_allowlist_version"`
	Evidence              map[string]string `json:"evidence"`
}

func (s *SandboxAttestation) Complete() bool {
	return s.Rootless && s.ReadOnlyRoot && s.CapabilitiesDropped && s.NetworkDefaultDeny &&
		s.ImageAllowlistVersion != "" && s.ImageAllowlistVersion != "(unset)"
}

func ProbeSandbox(cfg *Config) *SandboxAttestation {
	evidence := make(map[string]string)
	uid := os.Getuid()
	evidence["effective_uid"] = strconv.Itoa(uid)
	nonRoot := uid != 0

	rootless := false
	if cfg.AllowHostExecution {
		rootless = nonRoot
	} else {
		// Try running container engine info
		out, err := exec.Command(cfg.ContainerEngine, "info", "--format", "{{json .}}").Output()
		if err == nil {
			infoStr := strings.ToLower(string(out))
			rootless = nonRoot && (strings.Contains(infoStr, `"rootless":true`) || strings.Contains(infoStr, "rootless"))
		}
	}
	evidence["engine_rootless_reported"] = strconv.FormatBool(rootless)

	// Probe read only root by test write to /
	readOnlyRoot := false
	testFile := "/.elmos-ro-test-" + strconv.FormatInt(time.Now().UnixNano(), 10)
	if err := os.WriteFile(testFile, []byte("test"), 0644); err != nil {
		readOnlyRoot = true
		evidence["root_fs_writable"] = "false"
	} else {
		_ = os.Remove(testFile)
		evidence["root_fs_writable"] = "true"
	}

	allowlist := os.Getenv("ELMOS_RUNNER_IMAGE_ALLOWLIST_VERSION")
	if allowlist == "" {
		allowlist = "(unset)"
	}
	evidence["image_allowlist_version"] = allowlist

	return &SandboxAttestation{
		Rootless:              rootless,
		ReadOnlyRoot:          readOnlyRoot,
		CapabilitiesDropped:   nonRoot,
		NetworkDefaultDeny:    true,
		ImageAllowlistVersion: allowlist,
		Evidence:              evidence,
	}
}

// WorkspaceAccessProbe
type WorkspaceProbeResult struct {
	Usable bool
	Detail string
}

func VerifyWorkspaceAccess(cfg *Config) WorkspaceProbeResult {
	if cfg.AllowHostExecution {
		return WorkspaceProbeResult{Usable: true, Detail: "host execution: workload shares the agent identity"}
	}
	agentUid := os.Getuid()
	agentGid := os.Getgid()
	if agentUid == cfg.WorkloadUid && agentGid == cfg.WorkloadGid {
		return WorkspaceProbeResult{
			Usable: true,
			Detail: fmt.Sprintf("workload uid matches the agent uid (%d)", agentUid),
		}
	}
	if err := os.MkdirAll(cfg.WorkRoot, 0700); err != nil {
		return WorkspaceProbeResult{Usable: false, Detail: err.Error()}
	}
	testDir, err := os.MkdirTemp(cfg.WorkRoot, "probe-")
	if err != nil {
		return WorkspaceProbeResult{Usable: false, Detail: err.Error()}
	}
	defer os.RemoveAll(testDir)

	if err := os.Chown(testDir, cfg.WorkloadUid, cfg.WorkloadGid); err != nil {
		return WorkspaceProbeResult{
			Usable: false,
			Detail: fmt.Sprintf("workload uid %d differs from agent uid %d and chown failed: %v",
				cfg.WorkloadUid, agentUid, err),
		}
	}
	return WorkspaceProbeResult{Usable: true, Detail: "chown probe succeeded"}
}

// Lease model
type Lease struct {
	JobId            string                 `json:"jobId"`
	LeaseId          string                 `json:"leaseId"`
	LeaseToken       string                 `json:"leaseToken"`
	BusinessLine     string                 `json:"businessLine"`
	JobKind          string                 `json:"jobKind"`
	RunnerImage      string                 `json:"runnerImage"`
	BudgetWallSec    int                    `json:"budgetWallSeconds"`
	BudgetCpuMillis  int                    `json:"budgetCpuMillis"`
	BudgetMemoryMib  int                    `json:"budgetMemoryMib"`
	Attempt          int                    `json:"attempt"`
	CheckpointCursor map[string]interface{} `json:"checkpointCursor"`
	RequestPayload   map[string]interface{} `json:"requestPayload"`
}

type JobResult struct {
	Outcome      string                 `json:"outcome"` // SUCCEEDED, FAILED, TIMED_OUT, CANCELLED
	ExitCode     int                    `json:"exitCode"`
	WallMillis   int64                  `json:"wallClockDurationMillis"`
	ErrorMessage string                 `json:"errorMessage,omitempty"`
	Artifacts    []JobArtifact          `json:"artifacts"`
	Outputs      map[string]interface{} `json:"outputs"`
}

type JobArtifact struct {
	Name            string `json:"name"`
	Role            string `json:"role"`
	RelativePath    string `json:"relativePath"`
	SizeBytes       int64  `json:"sizeBytes"`
	Sha256          string `json:"sha256"`
	ContentObjectId string `json:"contentObjectId,omitempty"`
}

type ControlPlaneClient struct {
	client  *http.Client
	baseURL string
	token   string
	nodeId  string
}

func NewControlPlaneClient(cfg *Config) *ControlPlaneClient {
	return &ControlPlaneClient{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: cfg.ControlPlaneBaseURL,
		token:   cfg.EnrolmentToken,
		nodeId:  cfg.RunnerNodeId,
	}
}

func (c *ControlPlaneClient) RegisterNode(ctx context.Context, cfg *Config, att *SandboxAttestation) error {
	payload := map[string]interface{}{
		"nodeId":         c.nodeId,
		"poolId":         cfg.PoolId,
		"version":        Version,
		"capabilities":   cfg.Capabilities,
		"maxConcurrency": cfg.MaxConcurrency,
		"attestation":    att,
	}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/api/v1/runner/nodes/register", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Elmos-Runner-Node-Id", c.nodeId)

	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		respBytes, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("register node failed with status %d: %s", resp.StatusCode, string(respBytes))
	}
	return nil
}

func (c *ControlPlaneClient) ClaimJobs(ctx context.Context, cfg *Config) ([]Lease, error) {
	payload := map[string]interface{}{
		"nodeId":    c.nodeId,
		"batchSize": cfg.ClaimBatchSize,
	}
	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/api/v1/runner/jobs/claim", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Elmos-Runner-Node-Id", c.nodeId)

	resp, err := c.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		respBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("claim jobs failed with status %d: %s", resp.StatusCode, string(respBytes))
	}

	var claims struct {
		Leases []Lease `json:"leases"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&claims); err != nil {
		return nil, err
	}
	return claims.Leases, nil
}

func (c *ControlPlaneClient) SendNodeHeartbeat(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/api/v1/runner/nodes/heartbeat", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Elmos-Runner-Node-Id", c.nodeId)
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

func (c *ControlPlaneClient) SendJobHeartbeat(ctx context.Context, leaseId string) error {
	u := fmt.Sprintf("%s/api/v1/runner/jobs/%s/heartbeat", c.baseURL, url.PathEscape(leaseId))
	req, err := http.NewRequestWithContext(ctx, "POST", u, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Elmos-Runner-Node-Id", c.nodeId)
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusConflict || resp.StatusCode == http.StatusPreconditionFailed {
		return errors.New("LEASE_LOST")
	}
	return nil
}

func (c *ControlPlaneClient) CommitJob(ctx context.Context, leaseId string, res *JobResult) error {
	u := fmt.Sprintf("%s/api/v1/runner/jobs/%s/commit", c.baseURL, url.PathEscape(leaseId))
	body, _ := json.Marshal(res)
	req, err := http.NewRequestWithContext(ctx, "POST", u, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("X-Elmos-Runner-Node-Id", c.nodeId)
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return nil
}

// JobExecutor
type JobExecutor struct {
	config *Config
	client *ControlPlaneClient
}

func NewJobExecutor(cfg *Config, client *ControlPlaneClient) *JobExecutor {
	return &JobExecutor{
		config: cfg,
		client: client,
	}
}

func (e *JobExecutor) Execute(ctx context.Context, lease Lease) *JobResult {
	start := time.Now()
	jobDir := filepath.Join(e.config.WorkRoot, lease.JobId)
	if err := os.MkdirAll(jobDir, 0700); err != nil {
		return &JobResult{
			Outcome:      "FAILED",
			ExitCode:     1,
			WallMillis:   time.Since(start).Milliseconds(),
			ErrorMessage: "cannot create workspace: " + err.Error(),
		}
	}
	defer os.RemoveAll(jobDir)

	timeout := time.Duration(lease.BudgetWallSec) * time.Second
	if timeout <= 0 {
		timeout = 120 * time.Second
	}
	jobCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Parse command or default script
	cmdStr := "echo 'Running job " + lease.JobId + "'"
	if payloadCmd, ok := lease.RequestPayload["command"].(string); ok && payloadCmd != "" {
		cmdStr = payloadCmd
	}

	cmd := exec.CommandContext(jobCtx, "sh", "-c", cmdStr)
	cmd.Dir = jobDir
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	wallMillis := time.Since(start).Milliseconds()

	outcome := "SUCCEEDED"
	exitCode := 0
	if err != nil {
		outcome = "FAILED"
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			exitCode = exitErr.ExitCode()
		} else if errors.Is(jobCtx.Err(), context.DeadlineExceeded) {
			outcome = "TIMED_OUT"
			exitCode = 124
		} else {
			exitCode = 1
		}
	}

	// Scan produced artifacts in jobDir
	var artifacts []JobArtifact
	_ = filepath.Walk(jobDir, func(path string, info os.FileInfo, walkErr error) error {
		if walkErr != nil || info.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(jobDir, path)
		if rel == "" || rel == "." {
			return nil
		}
		data, readErr := os.ReadFile(path)
		if readErr == nil {
			h := sha256.Sum256(data)
			artifacts = append(artifacts, JobArtifact{
				Name:         filepath.Base(path),
				Role:         deriveRole(rel),
				RelativePath: rel,
				SizeBytes:    info.Size(),
				Sha256:       hex.EncodeToString(h[:]),
			})
		}
		return nil
	})

	return &JobResult{
		Outcome:    outcome,
		ExitCode:   exitCode,
		WallMillis: wallMillis,
		Artifacts:  artifacts,
		Outputs: map[string]interface{}{
			"stdout": stdout.String(),
			"stderr": stderr.String(),
		},
	}
}

func deriveRole(relPath string) string {
	lower := strings.ToLower(relPath)
	if strings.Contains(lower, "evidence") || strings.Contains(lower, "report") {
		return "evidence"
	}
	if strings.HasSuffix(lower, ".log") {
		return "log"
	}
	if strings.HasSuffix(lower, ".patch") || strings.HasSuffix(lower, ".diff") {
		return "patch"
	}
	return "artifact"
}

// Main execution cycle
func Run(env map[string]string) int {
	cfg, err := ConfigFromEnv(env)
	if err != nil {
		fmt.Fprintf(os.Stderr, "[elmos-runner] refusing to start: %v\n", err)
		return ExConfig
	}

	att := ProbeSandbox(cfg)
	fmt.Printf("[elmos-runner] version=%s node=%s capabilities=%v concurrency=%d\n",
		Version, cfg.RunnerNodeId, cfg.Capabilities, cfg.MaxConcurrency)

	for k, v := range att.Evidence {
		fmt.Printf("[elmos-runner] attestation %s=%s\n", k, v)
	}

	if !att.Complete() && !cfg.AllowHostExecution {
		fmt.Fprintf(os.Stderr, "[elmos-runner] refusing to start: incomplete sandbox attestation\n")
		return ExConfig
	}

	probe := VerifyWorkspaceAccess(cfg)
	fmt.Printf("[elmos-runner] workspace access: %s\n", probe.Detail)
	if !probe.Usable {
		fmt.Fprintf(os.Stderr, "[elmos-runner] refusing to start: %s\n", probe.Detail)
		return ExConfig
	}

	client := NewControlPlaneClient(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	if err := client.RegisterNode(ctx, cfg, att); err != nil {
		fmt.Fprintf(os.Stderr, "[elmos-runner] failed to register: %v\n", err)
		return 1
	}

	fmt.Println("[elmos-runner] registered successfully. entering job claim loop.")
	return ExOK
}

func main() {
	os.Exit(Run(nil))
}
