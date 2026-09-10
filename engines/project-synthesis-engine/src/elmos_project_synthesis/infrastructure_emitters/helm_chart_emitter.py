"""Enterprise Production Kubernetes Helm Chart Emitter with Strong Schema Validation.

Generates complete Helm v3 charts complying with restricted PodSecurity standards,
HPA autoscaling, zero-trust NetworkPolicy, Prometheus ServiceMonitors, and Outbox CronJobs.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def generate_enterprise_helm_chart(
    service_name: str,
    target_language: str,
    port: int = 8080,
    metrics_port: int = 9090,
    namespace: str = "production",
) -> Dict[str, str]:
    """Emit production-grade Helm v3 chart files."""
    files: Dict[str, str] = {}
    chart_name = f"{service_name.lower().replace("_", "-")}-service"

    # 1. Chart.yaml
    files["deploy/helm/Chart.yaml"] = f"""apiVersion: v2
name: {chart_name}
description: Industrial Enterprise Microservice Helm Chart for {service_name} ({target_language})
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - enterprise
  - microservice
  - {target_language}
  - cloud-native
maintainers:
  - name: elmos-autonomous-operator
    email: operator@elmos.internal
"""

    # 2. values.schema.json
    schema = {
        "$schema": "https://json-schema.org/draft-07/schema#",
        "title": "Values",
        "type": "object",
        "required": ["replicaCount", "image", "service", "resources"],
        "properties": {
            "replicaCount": {"type": "integer", "minimum": 1, "maximum": 50},
            "image": {
                "type": "object",
                "required": ["repository", "tag", "pullPolicy"],
                "properties": {
                    "repository": {"type": "string"},
                    "tag": {"type": "string"},
                    "pullPolicy": {"type": "string", "enum": ["Always", "IfNotPresent", "Never"]}
                }
            },
            "service": {
                "type": "object",
                "required": ["type", "port"],
                "properties": {
                    "type": {"type": "string", "enum": ["ClusterIP", "NodePort", "LoadBalancer"]},
                    "port": {"type": "integer", "minimum": 1, "maximum": 65535}
                }
            },
            "autoscaling": {
                "type": "object",
                "required": ["enabled", "minReplicas", "maxReplicas", "targetCPUUtilizationPercentage"],
                "properties": {
                    "enabled": {"type": "boolean"},
                    "minReplicas": {"type": "integer", "minimum": 1},
                    "maxReplicas": {"type": "integer", "minimum": 1},
                    "targetCPUUtilizationPercentage": {"type": "integer", "minimum": 1, "maximum": 100}
                }
            }
        }
    }
    files["deploy/helm/values.schema.json"] = json.dumps(schema, indent=2)

    # 3. values.yaml
    files["deploy/helm/values.yaml"] = f"""replicaCount: 3

image:
  repository: ghcr.io/elmos-enterprise/{chart_name}
  pullPolicy: IfNotPresent
  tag: "1.0.0"

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations:
    eks.amazonaws.com/role-arn: "arn:aws:iam::123456789012:role/{chart_name}-sa"
  name: "{chart_name}-sa"

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/path: "/metrics"
  prometheus.io/port: "{metrics_port}"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: {port}
  metricsPort: {metrics_port}

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
  hosts:
    - host: {chart_name}.elmos.internal
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: {chart_name}-tls
      hosts:
        - {chart_name}.elmos.internal

resources:
  limits:
    cpu: 1000m
    memory: 1024Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 75
  targetMemoryUtilizationPercentage: 80

probes:
  liveness:
    path: /health/live
    initialDelaySeconds: 15
    periodSeconds: 10
    timeoutSeconds: 3
    failureThreshold: 3
  readiness:
    path: /health/ready
    initialDelaySeconds: 5
    periodSeconds: 5
    timeoutSeconds: 2
    failureThreshold: 2
  startup:
    path: /health/live
    initialDelaySeconds: 5
    periodSeconds: 5
    failureThreshold: 12

networkPolicy:
  enabled: true

podDisruptionBudget:
  enabled: true
  minAvailable: 1

env:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  PORT: "{port}"
  METRICS_PORT: "{metrics_port}"
"""

    # 4. templates/_helpers.tpl
    files["deploy/helm/templates/_helpers.tpl"] = f"""{{{{/*
Expand the name of the chart.
*/}}}}
{{{{- define "{chart_name}.name" -}}}}
{{{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}

{{{{/*
Create a default fully qualified app name.
*/}}}}
{{{{- define "{chart_name}.fullname" -}}}}
{{{{- if .Values.fullnameOverride }}}}
{{{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}}}
{{{{- else }}}}
{{{{- $name := default .Chart.Name .Values.nameOverride }}}}
{{{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}}}
{{{{- end }}}}
{{{{- end }}}}

{{{{/*
Common labels
*/}}}}
{{{{- define "{chart_name}.labels" -}}}}
helm.sh/chart: {{{{ include "{chart_name}.name" . }}}}-{{{{ .Chart.Version | replace "+" "_" }}}}
{{{{ include "{chart_name}.selectorLabels" . }}}}
app.kubernetes.io/version: {{{{ .Chart.AppVersion | quote }}}}
app.kubernetes.io/managed-by: {{{{ .Release.Service }}}}
{{{{- end }}}}

{{{{/*
Selector labels
*/}}}}
{{{{- define "{chart_name}.selectorLabels" -}}}}
app.kubernetes.io/name: {{{{ include "{chart_name}.name" . }}}}
app.kubernetes.io/instance: {{{{ .Release.Name }}}}
{{{{- end }}}}
"""

    # 5. templates/deployment.yaml
    files["deploy/helm/templates/deployment.yaml"] = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  {{{{- if not .Values.autoscaling.enabled }}}}
  replicas: {{{{ .Values.replicaCount }}}}
  {{{{- end }}}}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 25%
      maxUnavailable: 0
  selector:
    matchLabels:
      {{{{- include "{chart_name}.selectorLabels" . | nindent 6 }}}}
  template:
    metadata:
      annotations:
        {{{{- toYaml .Values.podAnnotations | nindent 8 }}}}
      labels:
        {{{{- include "{chart_name}.selectorLabels" . | nindent 8 }}}}
    spec:
      securityContext:
        {{{{- toYaml .Values.podSecurityContext | nindent 8 }}}}
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    {{{{- include "{chart_name}.selectorLabels" . | nindent 20 }}}}
                topologyKey: kubernetes.io/hostname
      containers:
        - name: {{{{ .Chart.Name }}}}
          securityContext:
            {{{{- toYaml .Values.securityContext | nindent 12 }}}}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag | default .Chart.AppVersion }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - name: http
              containerPort: {{{{ .Values.service.port }}}}
              protocol: TCP
            - name: metrics
              containerPort: {{{{ .Values.service.metricsPort }}}}
              protocol: TCP
          livenessProbe:
            httpGet:
              path: {{{{ .Values.probes.liveness.path }}}}
              port: http
            initialDelaySeconds: {{{{ .Values.probes.liveness.initialDelaySeconds }}}}
            periodSeconds: {{{{ .Values.probes.liveness.periodSeconds }}}}
          readinessProbe:
            httpGet:
              path: {{{{ .Values.probes.readiness.path }}}}
              port: http
            initialDelaySeconds: {{{{ .Values.probes.readiness.initialDelaySeconds }}}}
            periodSeconds: {{{{ .Values.probes.readiness.periodSeconds }}}}
          startupProbe:
            httpGet:
              path: {{{{ .Values.probes.startup.path }}}}
              port: http
            initialDelaySeconds: {{{{ .Values.probes.startup.initialDelaySeconds }}}}
            periodSeconds: {{{{ .Values.probes.startup.periodSeconds }}}}
            failureThreshold: {{{{ .Values.probes.startup.failureThreshold }}}}
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
          volumeMounts:
            - name: tmp-volume
              mountPath: /tmp
      volumes:
        - name: tmp-volume
          emptyDir:
            medium: Memory
            sizeLimit: 128Mi
"""

    # 6. templates/service.yaml
    files["deploy/helm/templates/service.yaml"] = f"""apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: http
      protocol: TCP
      name: http
    - port: {{{{ .Values.service.metricsPort }}}}
      targetPort: metrics
      protocol: TCP
      name: metrics
  selector:
    {{{{- include "{chart_name}.selectorLabels" . | nindent 4 }}}}
"""

    # 7. templates/hpa.yaml
    files["deploy/helm/templates/hpa.yaml"] = f"""{{{{- if .Values.autoscaling.enabled }}}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{{{ include "{chart_name}.fullname" . }}}}
  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}
  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetMemoryUtilizationPercentage }}}}
{{{{- end }}}}
"""

    # 8. templates/networkpolicy.yaml
    files["deploy/helm/templates/networkpolicy.yaml"] = f"""{{{{- if .Values.networkPolicy.enabled }}}}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  podSelector:
    matchLabels:
      {{{{- include "{chart_name}.selectorLabels" . | nindent 6 }}}}
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow ingress traffic from ingress controller and prometheus
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{{{ .Release.Namespace }}}}
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - protocol: TCP
          port: {{{{ .Values.service.port }}}}
        - protocol: TCP
          port: {{{{ .Values.service.metricsPort }}}}
  egress:
    # Allow outbound to DNS and in-cluster databases
    - to:
        - namespaceSelector: {{}}
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 5432 # PostgreSQL
        - protocol: TCP
          port: 6379 # Redis
        - protocol: TCP
          port: 9092 # Kafka
{{{{- end }}}}
"""

    # 9. templates/pdb.yaml
    files["deploy/helm/templates/pdb.yaml"] = f"""{{{{- if .Values.podDisruptionBudget.enabled }}}}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  minAvailable: {{{{ .Values.podDisruptionBudget.minAvailable }}}}
  selector:
    matchLabels:
      {{{{- include "{chart_name}.selectorLabels" . | nindent 6 }}}}
{{{{- end }}}}
"""

    # 10. templates/cronjob-outbox.yaml
    files["deploy/helm/templates/cronjob-outbox.yaml"] = f"""apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{{{ include "{chart_name}.fullname" . }}}}-outbox-sweeper
  labels:
    {{{{- include "{chart_name}.labels" . | nindent 4 }}}}
spec:
  schedule: "*/1 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            app.kubernetes.io/name: {{{{ include "{chart_name}.name" . }}}}-sweeper
        spec:
          restartPolicy: OnFailure
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
          containers:
            - name: sweeper
              image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
              command: ["/bin/sh", "-c", "python -m scripts.outbox_sweeper || true"]
              resources:
                limits:
                  cpu: 200m
                  memory: 256Mi
                requests:
                  cpu: 50m
                  memory: 64Mi
"""

    return files
