package generator

import (
	"bytes"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"text/template"
	"time"
)

// Engine manages project generation from DDD templates.
type Engine struct {
	baseTemplateDir string
}

// NewEngine creates a new generator engine instance.
func NewEngine(baseTemplateDir ...string) *Engine {
	dir := ""
	if len(baseTemplateDir) > 0 {
		dir = baseTemplateDir[0]
	}
	return &Engine{
		baseTemplateDir: dir,
	}
}

// FindTemplateDir locates the template directory by subfolder name.
func (e *Engine) FindTemplateDir(subDir, customDir string) (string, error) {
	if customDir != "" {
		target := filepath.Join(customDir, subDir)
		if fi, err := os.Stat(target); err == nil && fi.IsDir() {
			return target, nil
		}
		if fi, err := os.Stat(customDir); err == nil && fi.IsDir() {
			return customDir, nil
		}
	}

	if e.baseTemplateDir != "" {
		target := filepath.Join(e.baseTemplateDir, subDir)
		if fi, err := os.Stat(target); err == nil && fi.IsDir() {
			return target, nil
		}
	}

	candidateBases := []string{
		"templates",
		"../templates",
		"../../templates",
		"apps/project-generation/templates",
		"../apps/project-generation/templates",
	}

	for _, base := range candidateBases {
		target := filepath.Join(base, subDir)
		if fi, err := os.Stat(target); err == nil && fi.IsDir() {
			return target, nil
		}
	}

	return "", fmt.Errorf("template directory '%s' not found", subDir)
}

// ResolveTemplateDir locates the template directory across common search paths.
func (e *Engine) ResolveTemplateDir(lang SupportedLanguage, customDir string) (string, error) {
	var subDir string
	switch lang {
	case LanguageGo:
		subDir = "microservice-go-ddd"
	case LanguagePython:
		subDir = "microservice-python-ddd"
	case LanguageK8s:
		subDir = "k8s-manifests"
	default:
		return "", fmt.Errorf("unsupported language: %s", lang)
	}

	return e.FindTemplateDir(subDir, customDir)
}

// Generate creates a new project directory and renders all files from the template.
func (e *Engine) Generate(cfg ProjectConfig) (*GenerationResult, error) {
	startTime := time.Now()

	if cfg.ProjectName == "" {
		cfg.ProjectName = "my-service"
	}
	if cfg.ModuleName == "" {
		cfg.ModuleName = cfg.ProjectName
	}
	if cfg.ServiceName == "" {
		cfg.ServiceName = cfg.ProjectName
	}
	if cfg.Port == "" {
		cfg.Port = "8080"
	}
	if cfg.GRPCPort == "" {
		cfg.GRPCPort = "9090"
	}
	if cfg.Database == "" {
		cfg.Database = "postgres"
	}
	if cfg.Description == "" {
		cfg.Description = fmt.Sprintf("%s microservice with DDD architecture", cfg.ProjectName)
	}
	if cfg.Author == "" {
		cfg.Author = "Elmos Platform Team"
	}
	if cfg.Version == "" {
		cfg.Version = "0.1.0"
	}
	if cfg.Environment == "" {
		cfg.Environment = "development"
	}
	if cfg.Namespace == "" {
		cfg.Namespace = "default"
	}
	if cfg.ImageRepository == "" {
		cfg.ImageRepository = cfg.ProjectName
	}
	if cfg.ImageTag == "" {
		cfg.ImageTag = "latest"
	}
	if cfg.Replicas <= 0 {
		cfg.Replicas = 2
	}
	if cfg.OutputDir == "" {
		cfg.OutputDir = filepath.Join(".", cfg.ProjectName)
	}

	tmplDir, err := e.ResolveTemplateDir(cfg.Language, cfg.TemplateDir)
	if err != nil {
		return nil, err
	}

	withTelemetry := true
	if cfg.WithTelemetry != nil {
		withTelemetry = *cfg.WithTelemetry
	}
	withResilience := true
	if cfg.WithResilience != nil {
		withResilience = *cfg.WithResilience
	}

	vars := TemplateVars{
		ProjectName:     cfg.ProjectName,
		ModuleName:      cfg.ModuleName,
		ServiceName:     cfg.ServiceName,
		Port:            cfg.Port,
		GRPCPort:        cfg.GRPCPort,
		Database:        cfg.Database,
		Description:     cfg.Description,
		Author:          cfg.Author,
		Version:         cfg.Version,
		Environment:     cfg.Environment,
		Replicas:        cfg.Replicas,
		Namespace:       cfg.Namespace,
		ImageRepository: cfg.ImageRepository,
		ImageTag:        cfg.ImageTag,
		WithTelemetry:   withTelemetry,
		WithResilience:  withResilience,
	}

	var generatedFiles []string

	// Walk the template directory
	err = filepath.WalkDir(tmplDir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}

		// Calculate relative path inside template directory
		relPath, err := filepath.Rel(tmplDir, path)
		if err != nil {
			return err
		}

		if relPath == "." {
			return nil
		}

		// Skip optional feature files if disabled
		cleanRel := filepath.ToSlash(relPath)
		if !withTelemetry && strings.Contains(cleanRel, "telemetry") {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if !withResilience && (strings.Contains(cleanRel, "resilience") || strings.Contains(cleanRel, "circuit_breaker")) {
			if d.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}

		// Target output path
		outRelPath := relPath
		isTemplate := strings.HasSuffix(relPath, ".tmpl")
		if isTemplate {
			outRelPath = strings.TrimSuffix(relPath, ".tmpl")
		}

		targetPath := filepath.Join(cfg.OutputDir, outRelPath)

		if d.IsDir() {
			return os.MkdirAll(targetPath, 0755)
		}

		// Ensure parent directory exists
		if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
			return fmt.Errorf("failed to create directory %s: %w", filepath.Dir(targetPath), err)
		}

		// Render or copy file
		if isTemplate {
			if err := renderTemplateFile(path, targetPath, vars); err != nil {
				return fmt.Errorf("error rendering template %s: %w", path, err)
			}
		} else {
			if err := copyFile(path, targetPath); err != nil {
				return fmt.Errorf("error copying file %s: %w", path, err)
			}
		}

		generatedFiles = append(generatedFiles, targetPath)
		return nil
	})

	if err != nil {
		return &GenerationResult{
			Success:        false,
			OutputDir:      cfg.OutputDir,
			FilesGenerated: generatedFiles,
			Duration:       time.Since(startTime),
			Error:          err.Error(),
		}, err
	}

	return &GenerationResult{
		Success:        true,
		OutputDir:      cfg.OutputDir,
		FilesGenerated: generatedFiles,
		Duration:       time.Since(startTime),
	}, nil
}

func renderTemplateFile(srcPath, dstPath string, vars TemplateVars) error {
	content, err := os.ReadFile(srcPath)
	if err != nil {
		return err
	}

	tmplFuncs := template.FuncMap{
		"lower": strings.ToLower,
		"upper": strings.ToUpper,
		"title": strings.Title,
		"snake": func(s string) string {
			return strings.ToLower(strings.ReplaceAll(s, "-", "_"))
		},
		"kebab": func(s string) string {
			return strings.ToLower(strings.ReplaceAll(s, "_", "-"))
		},
		"default": func(defVal, val any) any {
			if val == nil || val == "" {
				return defVal
			}
			return val
		},
		"quote": func(val any) string {
			return fmt.Sprintf("%q", fmt.Sprintf("%v", val))
		},
		"replace": func(old, new, src string) string {
			return strings.ReplaceAll(src, old, new)
		},
		"trunc": func(length int, s string) string {
			if len(s) <= length {
				return s
			}
			return s[:length]
		},
		"trimSuffix": func(suffix, s string) string {
			return strings.TrimSuffix(s, suffix)
		},
		"indent": func(spaces int, s string) string {
			pad := strings.Repeat(" ", spaces)
			lines := strings.Split(s, "\n")
			for i, line := range lines {
				if line != "" {
					lines[i] = pad + line
				}
			}
			return strings.Join(lines, "\n")
		},
		"nindent": func(spaces int, s string) string {
			return "\n" + strings.Repeat(" ", spaces) + s
		},
	}

	tmpl, err := template.New(filepath.Base(srcPath)).
		Option("missingkey=zero").
		Funcs(tmplFuncs).
		Parse(string(content))
	if err != nil {
		return fmt.Errorf("parse error: %w", err)
	}

	var buf bytes.Buffer
	dataMap := vars.ToMap()
	if err := tmpl.Execute(&buf, dataMap); err != nil {
		return fmt.Errorf("execute error: %w", err)
	}

	return os.WriteFile(dstPath, buf.Bytes(), 0644)
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}

// RenderStringPlaceholders replaces simple string placeholders like {{.Name}}.
func renderStringPlaceholders(s string, data map[string]interface{}) string {
	res := s
	for k, v := range data {
		res = strings.ReplaceAll(res, fmt.Sprintf("{{.%s}}", k), fmt.Sprintf("%v", v))
	}
	return res
}

// RenderTemplateContent renders arbitrary template string content using map data.
func renderTemplateContent(tmplContent string, data map[string]interface{}) (string, error) {
	tmpl, err := template.New("tmpl").Option("missingkey=zero").Parse(tmplContent)
	if err != nil {
		return "", err
	}
	var buf bytes.Buffer
	if err := tmpl.Execute(&buf, data); err != nil {
		return "", err
	}
	return buf.String(), nil
}
