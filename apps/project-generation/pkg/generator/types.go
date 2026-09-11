package generator

import "time"

// SupportedLanguage defines target language types.
type SupportedLanguage string

const (
	LanguageGo     SupportedLanguage = "go"
	LanguagePython SupportedLanguage = "python"
	LanguageK8s    SupportedLanguage = "k8s"
)

// ProjectConfig contains all parameters for generating a new project.
type ProjectConfig struct {
	Language        SupportedLanguage `json:"language"`
	ProjectName     string            `json:"project_name"`
	ModuleName      string            `json:"module_name"`
	ServiceName     string            `json:"service_name"`
	Port            string            `json:"port"`
	GRPCPort        string            `json:"grpc_port"`
	Database        string            `json:"database"`
	Description     string            `json:"description"`
	Author          string            `json:"author"`
	Version         string            `json:"version"`
	Environment     string            `json:"environment"`
	Namespace       string            `json:"namespace"`
	ImageRepository string            `json:"image_repository"`
	ImageTag        string            `json:"image_tag"`
	Replicas        int               `json:"replicas"`
	OutputDir       string            `json:"output_dir"`
	TemplateDir     string            `json:"template_dir"`
}

// TemplateVars represents data passed to template engines for rendering.
type TemplateVars struct {
	ProjectName     string
	ModuleName      string
	ServiceName     string
	Port            string
	GRPCPort        string
	Database        string
	Description     string
	Author          string
	Version         string
	Environment     string
	Replicas        int
	Namespace       string
	ImageRepository string
	ImageTag        string
}

// ToMap converts TemplateVars to a map for flexible template rendering.
func (v TemplateVars) ToMap() map[string]interface{} {
	return map[string]interface{}{
		"ProjectName":     v.ProjectName,
		"ModuleName":      v.ModuleName,
		"ServiceName":     v.ServiceName,
		"Port":            v.Port,
		"GRPCPort":        v.GRPCPort,
		"Database":        v.Database,
		"Description":     v.Description,
		"Author":          v.Author,
		"Version":         v.Version,
		"Environment":     v.Environment,
		"Replicas":        v.Replicas,
		"Namespace":       v.Namespace,
		"ImageRepository": v.ImageRepository,
		"ImageTag":        v.ImageTag,
	}
}

// K8sSpec defines parameters for dedicated Kubernetes manifests generation.
type K8sSpec struct {
	Name        string `json:"name"`
	Port        int    `json:"port"`
	Replicas    int    `json:"replicas"`
	Image       string `json:"image"`
	Namespace   string `json:"namespace"`
	OutputDir   string `json:"output_dir"`
	TemplateDir string `json:"template_dir"`
}

// Normalize sets sensible defaults for K8sSpec.
func (s *K8sSpec) Normalize() {
	if s.Port <= 0 {
		s.Port = 8080
	}
	if s.Replicas <= 0 {
		s.Replicas = 2
	}
	if s.Image == "" {
		s.Image = s.Name + ":latest"
	}
	if s.Namespace == "" {
		s.Namespace = "default"
	}
}

// GenerationResult encapsulates the outcome of a project generation process.
type GenerationResult struct {
	Success        bool          `json:"success"`
	OutputDir      string        `json:"output_dir"`
	FilesGenerated []string      `json:"files_generated"`
	Duration       time.Duration `json:"duration"`
	Error          string        `json:"error,omitempty"`
}
