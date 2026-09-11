package generator_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"apps/project-generation/pkg/generator"
	"apps/project-generation/pkg/validator"
)

func TestEngine_GenerateGoProject(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "project-gen-go-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	engine := generator.NewEngine("")

	cfg := generator.ProjectConfig{
		Language:    generator.LanguageGo,
		ProjectName: "order-service",
		ModuleName:  "github.com/example/order-service",
		ServiceName: "order-service",
		Port:        "8080",
		GRPCPort:    "9090",
		Database:    "postgres",
		Description: "Order microservice in Go",
		Author:      "Elmos Team",
		OutputDir:   filepath.Join(tmpDir, "order-service"),
	}

	result, err := engine.Generate(cfg)
	if err != nil {
		t.Fatalf("generation failed: %v", err)
	}

	if !result.Success {
		t.Fatalf("expected success, got error: %s", result.Error)
	}

	if len(result.FilesGenerated) == 0 {
		t.Fatal("expected generated files, got 0")
	}

	// Verify main files exist
	expectedFiles := []string{
		"go.mod",
		"Makefile",
		"Dockerfile",
		"README.md",
		filepath.Join("cmd", "server", "main.go"),
		filepath.Join("internal", "domain", "model", "entity.go"),
		filepath.Join("internal", "application", "service", "service.go"),
		filepath.Join("internal", "infrastructure", "persistence", "repository_impl.go"),
		filepath.Join("internal", "interfaces", "http", "handler.go"),
		filepath.Join("internal", "interfaces", "http", "middleware", "telemetry.go"),
		filepath.Join("pkg", "telemetry", "tracer.go"),
		filepath.Join("pkg", "resilience", "circuit_breaker.go"),
		filepath.Join("pkg", "errors", "errors.go"),
	}

	for _, f := range expectedFiles {
		p := filepath.Join(cfg.OutputDir, f)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("expected file missing: %s", p)
		}
	}

	// Verify graceful drain and telemetry in main.go
	mainBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "cmd", "server", "main.go"))
	if err != nil {
		t.Fatalf("failed to read main.go: %v", err)
	}
	mainContent := string(mainBytes)
	if !strings.Contains(mainContent, "30*time.Second") {
		t.Error("expected 30s graceful drain timeout in main.go")
	}
	if !strings.Contains(mainContent, "telemetry.InitTracer") {
		t.Error("expected telemetry.InitTracer in main.go")
	}

	// Verify RFC 7807 Problem Details in pkg/errors/errors.go
	errBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "pkg", "errors", "errors.go"))
	if err != nil {
		t.Fatalf("failed to read errors.go: %v", err)
	}
	if !strings.Contains(string(errBytes), "ProblemDetails") {
		t.Error("expected ProblemDetails struct in errors.go")
	}

	// Verify CircuitBreaker in pkg/resilience/circuit_breaker.go
	cbBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "pkg", "resilience", "circuit_breaker.go"))
	if err != nil {
		t.Fatalf("failed to read circuit_breaker.go: %v", err)
	}
	if !strings.Contains(string(cbBytes), "CircuitBreaker") {
		t.Error("expected CircuitBreaker in circuit_breaker.go")
	}

	// Validate DDD constraints
	v := validator.NewDDDValidator()
	report, err := v.Validate(cfg.OutputDir)
	if err != nil {
		t.Fatalf("validation failed: %v", err)
	}

	if !report.Valid {
		t.Fatalf("DDD validation failed:\n%s", report.String())
	}
}

func TestEngine_FeatureFlagDisabling(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "project-gen-flags-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	engine := generator.NewEngine("")

	cfg := generator.ProjectConfig{
		Language:       generator.LanguageGo,
		ProjectName:    "minimal-service",
		OutputDir:      filepath.Join(tmpDir, "minimal-service"),
		WithTelemetry:  generator.Bool(false),
		WithResilience: generator.Bool(false),
	}

	result, err := engine.Generate(cfg)
	if err != nil {
		t.Fatalf("generation failed: %v", err)
	}
	if !result.Success {
		t.Fatalf("expected success, got: %s", result.Error)
	}

	// Check telemetry and resilience were omitted
	telemetryFile := filepath.Join(cfg.OutputDir, "pkg", "telemetry", "tracer.go")
	if _, err := os.Stat(telemetryFile); !os.IsNotExist(err) {
		t.Errorf("expected telemetry file omitted, but it exists: %s", telemetryFile)
	}

	resilienceFile := filepath.Join(cfg.OutputDir, "pkg", "resilience", "circuit_breaker.go")
	if _, err := os.Stat(resilienceFile); !os.IsNotExist(err) {
		t.Errorf("expected resilience file omitted, but it exists: %s", resilienceFile)
	}
}

func TestEngine_GeneratePythonProject(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "project-gen-py-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	engine := generator.NewEngine("")

	cfg := generator.ProjectConfig{
		Language:    generator.LanguagePython,
		ProjectName: "user-service",
		Port:        "8000",
		Database:    "postgresql",
		Description: "User microservice in FastAPI",
		Author:      "Elmos Team",
		OutputDir:   filepath.Join(tmpDir, "user-service"),
	}

	result, err := engine.Generate(cfg)
	if err != nil {
		t.Fatalf("generation failed: %v", err)
	}

	if !result.Success {
		t.Fatalf("expected success, got error: %s", result.Error)
	}

	expectedFiles := []string{
		"pyproject.toml",
		"Makefile",
		"Dockerfile",
		"README.md",
		filepath.Join("app", "main.py"),
		filepath.Join("app", "domain", "models", "entity.py"),
		filepath.Join("app", "application", "services", "application_service.py"),
		filepath.Join("app", "infrastructure", "repositories", "repository_impl.py"),
		filepath.Join("app", "infrastructure", "telemetry.py"),
		filepath.Join("app", "interfaces", "api", "router.py"),
	}

	for _, f := range expectedFiles {
		p := filepath.Join(cfg.OutputDir, f)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("expected file missing: %s", p)
		}
	}

	// Verify lifespan and RFC 7807 problem details in main.py
	pyMainBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "app", "main.py"))
	if err != nil {
		t.Fatalf("failed to read app/main.py: %v", err)
	}
	pyMainContent := string(pyMainBytes)
	if !strings.Contains(pyMainContent, "lifespan") {
		t.Error("expected lifespan in app/main.py")
	}
	if !strings.Contains(pyMainContent, "await db_manager.ping()") {
		t.Error("expected db_manager.ping() in app/main.py lifespan")
	}
	if !strings.Contains(pyMainContent, "application/problem+json") {
		t.Error("expected application/problem+json in app/main.py")
	}

	// Validate DDD constraints
	v := validator.NewDDDValidator()
	report, err := v.Validate(cfg.OutputDir)
	if err != nil {
		t.Fatalf("validation failed: %v", err)
	}

	if !report.Valid {
		t.Fatalf("DDD validation failed:\n%s", report.String())
	}
}

func TestEngine_GenerateK8sManifests(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "project-gen-k8s-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	engine := generator.NewEngine("")

	cfg := generator.ProjectConfig{
		Language:    generator.LanguageK8s,
		ProjectName: "payment-service",
		Port:        "8080",
		Database:    "postgres",
		Description: "K8s manifests for payment service",
		OutputDir:   filepath.Join(tmpDir, "k8s-manifests"),
	}

	result, err := engine.Generate(cfg)
	if err != nil {
		t.Fatalf("generation failed: %v", err)
	}

	if !result.Success {
		t.Fatalf("expected success, got error: %s", result.Error)
	}

	expectedFiles := []string{
		filepath.Join("base", "deployment.yaml"),
		filepath.Join("base", "service.yaml"),
		filepath.Join("base", "kustomization.yaml"),
		filepath.Join("base", "pdb.yaml"),
		filepath.Join("overlays", "dev", "kustomization.yaml"),
		filepath.Join("overlays", "prod", "kustomization.yaml"),
		filepath.Join("helm", "chart", "Chart.yaml"),
		filepath.Join("helm", "chart", "values.yaml"),
	}

	for _, f := range expectedFiles {
		p := filepath.Join(cfg.OutputDir, f)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("expected file missing: %s", p)
		}
	}

	// Verify PDB content
	pdbBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "base", "pdb.yaml"))
	if err != nil {
		t.Fatalf("failed to read pdb.yaml: %v", err)
	}
	if !strings.Contains(string(pdbBytes), "PodDisruptionBudget") {
		t.Error("expected PodDisruptionBudget in pdb.yaml")
	}

	// Verify startupProbe and topologySpreadConstraints in deployment.yaml
	depBytes, err := os.ReadFile(filepath.Join(cfg.OutputDir, "base", "deployment.yaml"))
	if err != nil {
		t.Fatalf("failed to read deployment.yaml: %v", err)
	}
	depContent := string(depBytes)
	if !strings.Contains(depContent, "startupProbe") {
		t.Error("expected startupProbe in deployment.yaml")
	}
	if !strings.Contains(depContent, "topologySpreadConstraints") {
		t.Error("expected topologySpreadConstraints in deployment.yaml")
	}
}
