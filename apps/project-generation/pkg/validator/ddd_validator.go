package validator

import (
	"bufio"
	"encoding/json"
	"fmt"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Layer represents a DDD architectural layer.
type Layer string

const (
	LayerDomain         Layer = "Domain"
	LayerApplication    Layer = "Application"
	LayerInfrastructure Layer = "Infrastructure"
	LayerInterfaces     Layer = "Interfaces"
	LayerPkg            Layer = "Pkg"
	LayerComposition    Layer = "CompositionRoot"
	LayerUnknown        Layer = "Unknown"
)

// Violation describes a specific DDD architectural rule violation.
type Violation struct {
	File        string `json:"file"`
	Line        int    `json:"line"`
	SourceLayer Layer  `json:"source_layer"`
	TargetLayer Layer  `json:"target_layer"`
	ImportPath  string `json:"import_path"`
	Rule        string `json:"rule"`
	Message     string `json:"message"`
}

// ValidationReport contains the aggregated results of a DDD architecture validation.
type ValidationReport struct {
	Valid        bool        `json:"valid"`
	CheckedFiles int         `json:"checked_files"`
	Violations   []Violation `json:"violations"`
	Summary      string      `json:"summary"`
}

// String returns a human-readable summary of the validation report.
func (r *ValidationReport) String() string {
	var sb strings.Builder
	sb.WriteString("=== DDD Architecture Compliance Report ===\n")
	sb.WriteString(fmt.Sprintf("Checked Files: %d\n", r.CheckedFiles))
	sb.WriteString(fmt.Sprintf("Violations Found: %d\n", len(r.Violations)))
	sb.WriteString(fmt.Sprintf("Status: %s\n", map[bool]string{true: "PASSED (100% Compliant)", false: "FAILED"}[r.Valid]))

	if len(r.Violations) > 0 {
		sb.WriteString("\nViolations List:\n")
		for i, v := range r.Violations {
			sb.WriteString(fmt.Sprintf("  [%d] %s:%d\n", i+1, v.File, v.Line))
			sb.WriteString(fmt.Sprintf("      Rule: %s\n", v.Rule))
			sb.WriteString(fmt.Sprintf("      Violation: Layer '%s' illegally imports Layer '%s' via '%s'\n", v.SourceLayer, v.TargetLayer, v.ImportPath))
			sb.WriteString(fmt.Sprintf("      Detail: %s\n", v.Message))
		}
	}
	return sb.String()
}

// ToJSON converts the validation report into JSON format.
func (r *ValidationReport) ToJSON() (string, error) {
	bytes, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return "", err
	}
	return string(bytes), nil
}

// DDDValidator inspects codebases for architectural layer compliance.
type DDDValidator struct{}

// NewDDDValidator creates a new DDD static validator.
func NewDDDValidator() *DDDValidator {
	return &DDDValidator{}
}

// Validate inspects a project directory for DDD compliance.
func (v *DDDValidator) Validate(projectDir string) (*ValidationReport, error) {
	report := &ValidationReport{
		Valid:      true,
		Violations: make([]Violation, 0),
	}

	err := filepath.WalkDir(projectDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			name := d.Name()
			if name == ".git" || name == "vendor" || name == ".venv" || name == "node_modules" {
				return filepath.SkipDir
			}
			return nil
		}

		ext := filepath.Ext(path)
		switch ext {
		case ".go":
			report.CheckedFiles++
			violations, err := v.validateGoFile(projectDir, path)
			if err != nil {
				return err
			}
			report.Violations = append(report.Violations, violations...)
		case ".py":
			report.CheckedFiles++
			violations, err := v.validatePyFile(projectDir, path)
			if err != nil {
				return err
			}
			report.Violations = append(report.Violations, violations...)
		}

		return nil
	})

	if err != nil {
		return nil, err
	}

	report.Valid = len(report.Violations) == 0
	if report.Valid {
		report.Summary = fmt.Sprintf("All %d files strictly adhere to DDD architecture layer boundaries.", report.CheckedFiles)
	} else {
		report.Summary = fmt.Sprintf("Found %d architectural violations across %d files.", len(report.Violations), report.CheckedFiles)
	}

	return report, nil
}

func (v *DDDValidator) detectGoLayer(relPath string) Layer {
	clean := filepath.ToSlash(relPath)
	if strings.HasPrefix(clean, "cmd/") || clean == "main.go" {
		return LayerComposition
	}
	if strings.Contains(clean, "internal/domain/") {
		return LayerDomain
	}
	if strings.Contains(clean, "internal/application/") {
		return LayerApplication
	}
	if strings.Contains(clean, "internal/infrastructure/") {
		return LayerInfrastructure
	}
	if strings.Contains(clean, "internal/interfaces/") {
		return LayerInterfaces
	}
	if strings.HasPrefix(clean, "pkg/") {
		return LayerPkg
	}
	return LayerUnknown
}

func (v *DDDValidator) detectImportLayer(importPath string) Layer {
	clean := filepath.ToSlash(importPath)
	if strings.Contains(clean, "/internal/domain") || strings.Contains(clean, "app.domain") || strings.Contains(clean, "app/domain") {
		return LayerDomain
	}
	if strings.Contains(clean, "/internal/application") || strings.Contains(clean, "app.application") || strings.Contains(clean, "app/application") {
		return LayerApplication
	}
	if strings.Contains(clean, "/internal/infrastructure") || strings.Contains(clean, "app.infrastructure") || strings.Contains(clean, "app/infrastructure") {
		return LayerInfrastructure
	}
	if strings.Contains(clean, "/internal/interfaces") || strings.Contains(clean, "app.interfaces") || strings.Contains(clean, "app/interfaces") {
		return LayerInterfaces
	}
	if strings.Contains(clean, "/pkg") {
		return LayerPkg
	}
	return LayerUnknown
}

func (v *DDDValidator) validateGoFile(rootDir, filePath string) ([]Violation, error) {
	relPath, err := filepath.Rel(rootDir, filePath)
	if err != nil {
		return nil, err
	}

	sourceLayer := v.detectGoLayer(relPath)
	// Composition root (main.go) is allowed to wire all layers
	if sourceLayer == LayerComposition || sourceLayer == LayerUnknown || sourceLayer == LayerPkg {
		return nil, nil
	}

	fset := token.NewFileSet()
	node, err := parser.ParseFile(fset, filePath, nil, parser.ImportsOnly)
	if err != nil {
		return nil, fmt.Errorf("failed to parse Go file %s: %w", filePath, err)
	}

	var violations []Violation

	for _, imp := range node.Imports {
		importPath := strings.Trim(imp.Path.Value, `"`)
		targetLayer := v.detectImportLayer(importPath)
		if targetLayer == LayerUnknown || targetLayer == LayerPkg {
			continue
		}

		line := fset.Position(imp.Pos()).Line

		// Rule 1: Domain layer must NEVER depend on Application, Infrastructure, or Interfaces
		if sourceLayer == LayerDomain {
			if targetLayer == LayerApplication || targetLayer == LayerInfrastructure || targetLayer == LayerInterfaces {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        line,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 1: Domain layer must not depend on Application, Infrastructure, or Interfaces",
					Message:     fmt.Sprintf("Domain file '%s' violates isolation by importing %s", relPath, importPath),
				})
			}
		}

		// Rule 2: Application layer can ONLY depend on Domain layer, NOT on Infrastructure or Interfaces
		if sourceLayer == LayerApplication {
			if targetLayer == LayerInfrastructure || targetLayer == LayerInterfaces {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        line,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 2: Application layer can only depend on Domain, never on Infrastructure or Interfaces",
					Message:     fmt.Sprintf("Application file '%s' violates layer direction by importing %s", relPath, importPath),
				})
			}
		}

		// Rule 3: Interfaces layer can depend on Application and Domain, but MUST NOT directly depend on Infrastructure
		if sourceLayer == LayerInterfaces {
			if targetLayer == LayerInfrastructure {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        line,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 3: Interfaces must not directly depend on Infrastructure implementations",
					Message:     fmt.Sprintf("Interfaces file '%s' directly couples with Infrastructure %s", relPath, importPath),
				})
			}
		}
	}

	return violations, nil
}

func (v *DDDValidator) detectPyLayer(relPath string) Layer {
	clean := filepath.ToSlash(relPath)
	if clean == "app/main.py" || clean == "main.py" {
		return LayerComposition
	}
	if strings.HasPrefix(clean, "app/domain/") {
		return LayerDomain
	}
	if strings.HasPrefix(clean, "app/application/") {
		return LayerApplication
	}
	if strings.HasPrefix(clean, "app/infrastructure/") {
		return LayerInfrastructure
	}
	if strings.HasPrefix(clean, "app/interfaces/") {
		return LayerInterfaces
	}
	if strings.HasPrefix(clean, "tests/") {
		return LayerComposition // Tests are allowed to assemble components
	}
	return LayerUnknown
}

var (
	pyImportRe        = regexp.MustCompile(`^\s*import\s+([a-zA-Z0-9_\.]+)`)
	pyFromImportRe    = regexp.MustCompile(`^\s*from\s+([a-zA-Z0-9_\.]+)\s+import`)
	pyDynamicImportRe = regexp.MustCompile(`(?:(?:importlib\.)?import_module|__import__)\s*\(\s*(?:name\s*=\s*)?["']([^"']+)["']`)
)

func (v *DDDValidator) validatePyFile(rootDir, filePath string) ([]Violation, error) {
	relPath, err := filepath.Rel(rootDir, filePath)
	if err != nil {
		return nil, err
	}

	sourceLayer := v.detectPyLayer(relPath)
	if sourceLayer == LayerComposition || sourceLayer == LayerUnknown {
		return nil, nil
	}

	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var violations []Violation
	scanner := bufio.NewScanner(file)
	lineNum := 0

	// Exemption: dependencies.py in interfaces is the dependency injection factory
	isDIFactory := strings.Contains(relPath, "dependencies.py")

	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		var importPath string
		isDynamic := false

		if m := pyFromImportRe.FindStringSubmatch(line); len(m) > 1 {
			importPath = m[1]
		} else if m := pyImportRe.FindStringSubmatch(line); len(m) > 1 {
			importPath = m[1]
		} else if m := pyDynamicImportRe.FindStringSubmatch(line); len(m) > 1 {
			importPath = m[1]
			isDynamic = true
		}

		if importPath == "" {
			continue
		}

		targetLayer := v.detectImportLayer(importPath)
		if targetLayer == LayerUnknown {
			continue
		}

		suffix := ""
		if isDynamic {
			suffix = fmt.Sprintf(" (detected dynamic reflection import: '%s')", importPath)
		}

		// Rule 1: Domain layer must NEVER depend on outer layers
		if sourceLayer == LayerDomain {
			if targetLayer == LayerApplication || targetLayer == LayerInfrastructure || targetLayer == LayerInterfaces {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        lineNum,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 1: Domain layer must not depend on Application, Infrastructure, or Interfaces",
					Message:     fmt.Sprintf("Domain file '%s' violates isolation by importing %s%s", relPath, importPath, suffix),
				})
			}
		}

		// Rule 2: Application layer can ONLY depend on Domain
		if sourceLayer == LayerApplication {
			if targetLayer == LayerInfrastructure || targetLayer == LayerInterfaces {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        lineNum,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 2: Application layer can only depend on Domain, never on Infrastructure or Interfaces",
					Message:     fmt.Sprintf("Application file '%s' violates layer direction by importing %s%s", relPath, importPath, suffix),
				})
			}
		}

		// Rule 3: Interfaces layer must not directly depend on Infrastructure (except composition DI factory)
		if sourceLayer == LayerInterfaces && !isDIFactory {
			if targetLayer == LayerInfrastructure {
				violations = append(violations, Violation{
					File:        relPath,
					Line:        lineNum,
					SourceLayer: sourceLayer,
					TargetLayer: targetLayer,
					ImportPath:  importPath,
					Rule:        "Rule 3: Interfaces must not directly depend on Infrastructure implementations",
					Message:     fmt.Sprintf("Interfaces file '%s' directly couples with Infrastructure %s%s", relPath, importPath, suffix),
				})
			}
		}
	}

	return violations, scanner.Err()
}
