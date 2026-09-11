package generator

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// K8sGenerator handles Kubernetes manifest and Helm chart generation.
type K8sGenerator struct {
	engine *Engine
}

// NewK8sGenerator creates a new K8sGenerator.
func NewK8sGenerator(engine ...*Engine) *K8sGenerator {
	if len(engine) > 0 && engine[0] != nil {
		return &K8sGenerator{engine: engine[0]}
	}
	return &K8sGenerator{engine: NewEngine()}
}

// GenerateK8s renders Kubernetes base manifests, overlays, and Helm chart.
func (g *K8sGenerator) GenerateK8s(spec *K8sSpec) error {
	if spec == nil {
		return fmt.Errorf("k8s spec cannot be nil")
	}
	spec.Normalize()

	if spec.Name == "" {
		return fmt.Errorf("k8s resource name is required")
	}
	if spec.OutputDir == "" {
		return fmt.Errorf("output directory is required")
	}

	data := map[string]interface{}{
		"Name":      spec.Name,
		"Port":      spec.Port,
		"Replicas":  spec.Replicas,
		"Image":     spec.Image,
		"Namespace": spec.Namespace,
	}

	templateDir, err := g.engine.FindTemplateDir("k8s-manifests", spec.TemplateDir)
	if err == nil {
		// Use template files
		return filepath.Walk(templateDir, func(path string, info fs.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if info.IsDir() {
				return nil
			}

			relPath, err := filepath.Rel(templateDir, path)
			if err != nil {
				return err
			}

			targetRelPath := strings.TrimSuffix(relPath, ".tmpl")
			targetRelPath = renderStringPlaceholders(targetRelPath, data)
			targetFullPath := filepath.Join(spec.OutputDir, targetRelPath)

			if err := os.MkdirAll(filepath.Dir(targetFullPath), 0755); err != nil {
				return fmt.Errorf("failed to create directory for %s: %w", targetFullPath, err)
			}

			contentBytes, err := os.ReadFile(path)
			if err != nil {
				return fmt.Errorf("failed to read template file %s: %w", path, err)
			}

			rendered, err := renderTemplateContent(string(contentBytes), data)
			if err != nil {
				return fmt.Errorf("failed to render template %s: %w", relPath, err)
			}

			return os.WriteFile(targetFullPath, []byte(rendered), 0644)
		})
	}

	// Direct fallback if template directory not located
	return g.generateFallbackManifests(spec, data)
}

func (g *K8sGenerator) generateFallbackManifests(spec *K8sSpec, data map[string]interface{}) error {
	files := map[string]string{
		"base/deployment.yaml": fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: %s
  labels:
    app.kubernetes.io/name: %s
spec:
  replicas: %d
  selector:
    matchLabels:
      app.kubernetes.io/name: %s
  template:
    metadata:
      labels:
        app.kubernetes.io/name: %s
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: %s
      containers:
        - name: %s
          image: %s
          ports:
            - containerPort: %d
              name: http
          startupProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 10
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 2
`, spec.Name, spec.Name, spec.Replicas, spec.Name, spec.Name, spec.Name, spec.Name, spec.Image, spec.Port),

		"base/pdb.yaml": fmt.Sprintf(`apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: %s-pdb
  labels:
    app.kubernetes.io/name: %s
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: %s
`, spec.Name, spec.Name, spec.Name),

		"base/service.yaml": fmt.Sprintf(`apiVersion: v1
kind: Service
metadata:
  name: %s
  labels:
    app.kubernetes.io/name: %s
spec:
  type: ClusterIP
  ports:
    - port: %d
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app.kubernetes.io/name: %s
`, spec.Name, spec.Name, spec.Port, spec.Name),

		"base/configmap.yaml": fmt.Sprintf(`apiVersion: v1
kind: ConfigMap
metadata:
  name: %s-config
data:
  PORT: "%d"
  ENVIRONMENT: "production"
`, spec.Name, spec.Port),

		"base/kustomization.yaml": `apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
  - pdb.yaml
`,

		"overlays/dev/kustomization.yaml": fmt.Sprintf(`apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: dev
resources:
  - ../../base
namePrefix: dev-
patches:
  - target:
      kind: Deployment
      name: %s
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 1
`, spec.Name),

		"overlays/prod/deployment-patch.yaml": fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: %s
spec:
  replicas: %d
`, spec.Name, spec.Replicas),

		"overlays/prod/kustomization.yaml": `apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: prod
resources:
  - ../../base
namePrefix: prod-
patches:
  - path: deployment-patch.yaml
`,

		"helm/Chart.yaml": fmt.Sprintf(`apiVersion: v2
name: %s
description: Helm chart for %s
type: application
version: 0.1.0
appVersion: "1.0.0"
`, spec.Name, spec.Name),

		"helm/values.yaml": fmt.Sprintf(`replicaCount: %d
image:
  repository: "%s"
  pullPolicy: IfNotPresent
  tag: "latest"
service:
  type: ClusterIP
  port: %d
`, spec.Replicas, spec.Image, spec.Port),

		"helm/templates/deployment.yaml": fmt.Sprintf(`apiVersion: apps/v1
kind: Deployment
metadata:
  name: "{{ .Release.Name }}-%s"
  labels:
    app.kubernetes.io/name: "%s"
spec:
  replicas: %d
  selector:
    matchLabels:
      app.kubernetes.io/name: "%s"
  template:
    metadata:
      labels:
        app.kubernetes.io/name: "%s"
    spec:
      containers:
        - name: "%s"
          image: "%s"
          ports:
            - containerPort: %d
              name: http
`, spec.Name, spec.Name, spec.Replicas, spec.Name, spec.Name, spec.Name, spec.Image, spec.Port),

		"helm/templates/service.yaml": fmt.Sprintf(`apiVersion: v1
kind: Service
metadata:
  name: "{{ .Release.Name }}-%s"
  labels:
    app.kubernetes.io/name: "%s"
spec:
  type: ClusterIP
  ports:
    - port: %d
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app.kubernetes.io/name: "%s"
`, spec.Name, spec.Name, spec.Port, spec.Name),
	}

	for relPath, content := range files {
		targetFullPath := filepath.Join(spec.OutputDir, relPath)
		if err := os.MkdirAll(filepath.Dir(targetFullPath), 0755); err != nil {
			return err
		}
		if err := os.WriteFile(targetFullPath, []byte(content), 0644); err != nil {
			return err
		}
	}

	return nil
}
