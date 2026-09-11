package generator_test

import (
	"os"
	"path/filepath"
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
	}

	for _, f := range expectedFiles {
		p := filepath.Join(cfg.OutputDir, f)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("expected file missing: %s", p)
		}
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
		filepath.Join("app", "interfaces", "api", "router.py"),
	}

	for _, f := range expectedFiles {
		p := filepath.Join(cfg.OutputDir, f)
		if _, err := os.Stat(p); os.IsNotExist(err) {
			t.Errorf("expected file missing: %s", p)
		}
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
}
