package validator_test

import (
	"os"
	"path/filepath"
	"testing"

	"apps/project-generation/pkg/validator"
)

func TestDDDValidator_DetectsViolations_Go(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "ddd-violation-test-go-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Create an illegal domain file that imports infrastructure
	domainDir := filepath.Join(tmpDir, "internal", "domain", "model")
	if err := os.MkdirAll(domainDir, 0755); err != nil {
		t.Fatalf("mkdir failed: %v", err)
	}

	illegalFile := filepath.Join(domainDir, "illegal.go")
	illegalContent := `package model

import (
	"context"
	"sample-module/internal/infrastructure/persistence"
)

type BadEntity struct {
	repo *persistence.Repository
}
`
	if err := os.WriteFile(illegalFile, []byte(illegalContent), 0644); err != nil {
		t.Fatalf("write failed: %v", err)
	}

	v := validator.NewDDDValidator()
	report, err := v.Validate(tmpDir)
	if err != nil {
		t.Fatalf("validate failed: %v", err)
	}

	if report.Valid {
		t.Fatal("expected report to be INVALID due to Rule 1 violation, but got valid")
	}

	if len(report.Violations) == 0 {
		t.Fatal("expected at least 1 violation, got 0")
	}

	foundRule1 := false
	for _, vio := range report.Violations {
		if vio.SourceLayer == validator.LayerDomain && vio.TargetLayer == validator.LayerInfrastructure {
			foundRule1 = true
			break
		}
	}

	if !foundRule1 {
		t.Errorf("expected Rule 1 violation (Domain -> Infrastructure), but got:\n%s", report.String())
	}
}

func TestDDDValidator_DetectsViolations_Python(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "ddd-violation-test-py-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	// Create an illegal domain file that imports application
	domainDir := filepath.Join(tmpDir, "app", "domain", "models")
	if err := os.MkdirAll(domainDir, 0755); err != nil {
		t.Fatalf("mkdir failed: %v", err)
	}

	illegalFile := filepath.Join(domainDir, "illegal.py")
	illegalContent := `from app.application.services.entity_service import EntityService

class BadModel:
    pass
`
	if err := os.WriteFile(illegalFile, []byte(illegalContent), 0644); err != nil {
		t.Fatalf("write failed: %v", err)
	}

	v := validator.NewDDDValidator()
	report, err := v.Validate(tmpDir)
	if err != nil {
		t.Fatalf("validate failed: %v", err)
	}

	if report.Valid {
		t.Fatal("expected report to be INVALID due to Rule 1 violation, but got valid")
	}

	foundRule1 := false
	for _, vio := range report.Violations {
		if vio.SourceLayer == validator.LayerDomain && vio.TargetLayer == validator.LayerApplication {
			foundRule1 = true
			break
		}
	}

	if !foundRule1 {
		t.Errorf("expected Rule 1 violation (Domain -> Application), but got:\n%s", report.String())
	}
}
