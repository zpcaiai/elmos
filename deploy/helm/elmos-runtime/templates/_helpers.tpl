{{- define "elmos-runtime.name" -}}
{{- /* Reserve ten characters for the longest rendered component suffix. */ -}}
{{- default (printf "%s-%s" .Release.Name .Chart.Name) .Values.fullnameOverride | trunc 53 | trimSuffix "-" -}}
{{- end -}}

{{- define "elmos-runtime.labels" -}}
app.kubernetes.io/name: {{ include "elmos-runtime.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "elmos-runtime.selectorLabels" -}}
app.kubernetes.io/name: {{ include "elmos-runtime.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "elmos-runtime.validate" -}}
{{- if .Values.validation.enforceProductionValues -}}
  {{- $zeroUuid := "00000000-0000-0000-0000-000000000000" -}}
  {{- if regexMatch "@sha256:0{64}$" .Values.images.controlPlane }}{{ fail "production control-plane image digest is still the zero placeholder" }}{{ end -}}
  {{- if regexMatch "@sha256:0{64}$" .Values.images.worker }}{{ fail "production worker image digest is still the zero placeholder" }}{{ end -}}
  {{- if eq .Values.images.controlPlane .Values.images.worker }}{{ fail "control-plane and worker must use separately reviewed images" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.database.existingSecret) (hasPrefix "replace-" .Values.database.existingSecret) }}{{ fail "database.existingSecret must identify an environment-owned secret" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.credentials.existingSecret) (hasPrefix "replace-" .Values.credentials.existingSecret) }}{{ fail "credentials.existingSecret must identify an environment-owned secret" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.migration.serviceAccountName) (hasPrefix "replace-" .Values.migration.serviceAccountName) }}{{ fail "migration.serviceAccountName must identify an environment-owned least-privileged account" }}{{ end -}}
  {{- if not .Values.serviceMeshHttp }}{{ fail "this chart's internal HTTP endpoints require an approved service mesh" }}{{ end -}}
  {{- if or (eq .Values.credentials.workloadTokenKey .Values.credentials.topupTokenKey) (eq .Values.credentials.workloadTokenKey .Values.credentials.gateTokenKey) (eq .Values.credentials.workloadTokenKey .Values.credentials.outboxTokenKey) (eq .Values.credentials.topupTokenKey .Values.credentials.gateTokenKey) (eq .Values.credentials.topupTokenKey .Values.credentials.outboxTokenKey) (eq .Values.credentials.gateTokenKey .Values.credentials.outboxTokenKey) }}{{ fail "workload, top-up, gate, and outbox credentials must use distinct Secret keys" }}{{ end -}}
  {{- $schedulerDb := .Values.database.keys.scheduler -}}
  {{- $billingDb := .Values.database.keys.billing -}}
  {{- $projectorDb := .Values.database.keys.projector -}}
  {{- $migrationDb := .Values.database.keys.migration -}}
  {{- if or (eq $schedulerDb.username $billingDb.username) (eq $schedulerDb.username $projectorDb.username) (eq $schedulerDb.username $migrationDb.username) (eq $billingDb.username $projectorDb.username) (eq $billingDb.username $migrationDb.username) (eq $projectorDb.username $migrationDb.username) }}{{ fail "scheduler, billing, projector, and migration must use distinct database username keys" }}{{ end -}}
  {{- if or (eq $schedulerDb.password $billingDb.password) (eq $schedulerDb.password $projectorDb.password) (eq $schedulerDb.password $migrationDb.password) (eq $billingDb.password $projectorDb.password) (eq $billingDb.password $migrationDb.password) (eq $projectorDb.password $migrationDb.password) }}{{ fail "scheduler, billing, projector, and migration must use distinct database password keys" }}{{ end -}}
  {{- if not .Values.networkPolicy.enabled }}{{ fail "networkPolicy.enabled must remain true for production" }}{{ end -}}
  {{- if empty .Values.networkPolicy.databaseCidrs }}{{ fail "production databaseCidrs must be exact and non-empty" }}{{ end -}}
  {{- if empty .Values.networkPolicy.ingressNamespaceSelector.matchLabels }}{{ fail "production ingress namespace selector must be exact and non-empty" }}{{ end -}}
  {{- if empty .Values.networkPolicy.ingressPodSelector.matchLabels }}{{ fail "production ingress pod selector must be exact and non-empty" }}{{ end -}}
  {{- if lt (int .Values.components.scheduler.replicas) 2 }}{{ fail "production scheduler requires at least two replicas" }}{{ end -}}
  {{- if lt (int .Values.components.billing.replicas) 2 }}{{ fail "production billing requires at least two replicas" }}{{ end -}}
  {{- if lt (int .Values.worker.replicas) 2 }}{{ fail "production worker recovery requires at least two replicas" }}{{ end -}}
  {{- if not .Values.pdb.enabled }}{{ fail "production PodDisruptionBudgets must remain enabled" }}{{ end -}}
  {{- range $component := list "scheduler" "billing" "projector" "worker" -}}
    {{- $hpa := index $.Values.autoscaling $component -}}
    {{- if and $hpa.enabled (gt (int $hpa.minReplicas) (int $hpa.maxReplicas)) }}{{ fail (printf "%s autoscaling minReplicas exceeds maxReplicas" $component) }}{{ end -}}
    {{- if and $hpa.enabled (lt (int $hpa.minReplicas) 2) }}{{ fail (printf "production %s autoscaling requires at least two replicas" $component) }}{{ end -}}
    {{- $fixedReplicas := int $.Values.worker.replicas -}}
    {{- if ne $component "worker" }}{{ $fixedReplicas = int (index $.Values.components $component).replicas }}{{ end -}}
    {{- $minimum := ternary (int $hpa.minReplicas) $fixedReplicas $hpa.enabled -}}
    {{- if ge (int (index $.Values.pdb.minAvailable $component)) $minimum }}{{ fail (printf "%s PDB minAvailable must be lower than its minimum replica count" $component) }}{{ end -}}
  {{- end -}}
  {{- if not .Values.topologySpread.enabled }}{{ fail "production topology spread must remain enabled" }}{{ end -}}
  {{- if gt (int .Values.topologySpread.maxSkew) 1 }}{{ fail "production topology spread maxSkew must be one" }}{{ end -}}
  {{- if eq .Values.worker.identityNamespace $zeroUuid }}{{ fail "worker.identityNamespace must be deployment-specific" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.worker.region) (hasPrefix "REPLACE" .Values.worker.zone) }}{{ fail "worker region and zone must be exact" }}{{ end -}}
  {{- if lt (int .Values.worker.maxRetained) (int .Values.worker.maxConcurrent) }}{{ fail "worker.maxRetained cannot be lower than maxConcurrent" }}{{ end -}}
  {{- if empty .Values.worker.routes }}{{ fail "production worker route catalog cannot be empty" }}{{ end -}}
  {{- if not .Values.worker.persistence.enabled }}{{ fail "production worker inbox persistence must remain enabled" }}{{ end -}}
  {{- if empty .Values.worker.persistence.storageClass }}{{ fail "production worker persistence requires an exact storageClass" }}{{ end -}}
  {{- $routeTuples := dict -}}
  {{- range .Values.worker.routes -}}
    {{- $tuple := printf "%s:%s" .jobType .workType -}}
    {{- if hasKey $routeTuples $tuple }}{{ fail (printf "duplicate worker route tuple: %s" $tuple) }}{{ end -}}
    {{- $_ := set $routeTuples $tuple true -}}
    {{- if and (hasPrefix "http://" .endpoint) (not (regexMatch "^http://[^/]+\\.svc(\\.cluster\\.local)?(:[0-9]+)?/" .endpoint)) }}{{ fail (printf "plaintext worker route must be a service-mesh .svc endpoint: %s" $tuple) }}{{ end -}}
    {{- if and (hasPrefix "http://" .reconciliationEndpoint) (not (regexMatch "^http://[^/]+\\.svc(\\.cluster\\.local)?(:[0-9]+)?/" .reconciliationEndpoint)) }}{{ fail (printf "plaintext reconciliation route must be a service-mesh .svc endpoint: %s" $tuple) }}{{ end -}}
  {{- end -}}
  {{- if not .Values.provider.enabled }}{{ fail "production runtime requires the real provider adapter boundary" }}{{ end -}}
  {{- if empty .Values.provider.profiles }}{{ fail "provider.enabled requires exact provider/model profiles" }}{{ end -}}
  {{- if empty .Values.networkPolicy.providerCidrs }}{{ fail "provider.enabled requires exact providerCidrs" }}{{ end -}}
  {{- if empty .Values.networkPolicy.objectStorageCidrs }}{{ fail "provider.enabled requires exact objectStorageCidrs" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.provider.credentialSecret) (hasPrefix "replace-" .Values.provider.credentialSecret) }}{{ fail "provider credentialSecret must be environment-owned" }}{{ end -}}
  {{- if or (hasPrefix "REPLACE" .Values.provider.objectStorage.backendId) (hasPrefix "REPLACE" .Values.provider.objectStorage.region) }}{{ fail "provider object storage backend and region must be exact" }}{{ end -}}
  {{- if and (eq .Values.provider.objectStorage.serverSideEncryption "SSE_KMS") (or (empty .Values.provider.objectStorage.cmkReference) (hasPrefix "REPLACE" .Values.provider.objectStorage.cmkReference)) }}{{ fail "SSE_KMS requires an exact environment-owned CMK reference" }}{{ end -}}
  {{- if contains ".invalid" .Values.provider.objectStorage.endpoint }}{{ fail "provider object storage endpoint cannot use the reserved invalid domain" }}{{ end -}}
  {{- $providerTuples := dict -}}
  {{- $providerCredentialKeys := dict -}}
  {{- range .Values.provider.profiles -}}
    {{- $tuple := printf "%s:%s" .provider .model -}}
    {{- if hasKey $providerTuples $tuple }}{{ fail (printf "duplicate provider/model tuple: %s" $tuple) }}{{ end -}}
    {{- $_ := set $providerTuples $tuple true -}}
    {{- if hasKey $providerCredentialKeys .credentialKey }}{{ fail (printf "provider credential key is reused: %s" .credentialKey) }}{{ end -}}
    {{- $_ := set $providerCredentialKeys .credentialKey true -}}
    {{- if contains ".invalid" .endpoint }}{{ fail (printf "provider endpoint cannot use the reserved invalid domain: %s" $tuple) }}{{ end -}}
    {{- if gt (int .maxResponseBytes) (int $.Values.provider.objectStorage.maxObjectBytes) }}{{ fail (printf "provider response limit exceeds object-storage limit: %s" $tuple) }}{{ end -}}
  {{- end -}}
  {{- if or (hasKey $providerCredentialKeys .Values.provider.objectStorage.accessKeyKey) (hasKey $providerCredentialKeys .Values.provider.objectStorage.secretKeyKey) }}{{ fail "provider API credentials and object-storage credentials must use distinct keys" }}{{ end -}}
  {{- if eq .Values.provider.objectStorage.accessKeyKey .Values.provider.objectStorage.secretKeyKey }}{{ fail "object-storage access and secret keys must be distinct" }}{{ end -}}
  {{- if not .Values.outbox.enabled }}{{ fail "production runtime requires transactional outbox delivery" }}{{ end -}}
  {{- if empty .Values.networkPolicy.outboxCidrs }}{{ fail "outbox.enabled requires exact outboxCidrs" }}{{ end -}}
  {{- if contains ".invalid" .Values.outbox.endpoint }}{{ fail "outbox endpoint cannot use the reserved invalid domain" }}{{ end -}}
  {{- if and (not (empty .Values.worker.routes)) (empty .Values.networkPolicy.workerEngineCidrs) }}{{ fail "worker routes require exact workerEngineCidrs" }}{{ end -}}
  {{- if not .Values.monitoring.enabled }}{{ fail "production runtime requires Prometheus monitoring" }}{{ end -}}
  {{- if empty .Values.monitoring.namespaceSelector.matchLabels }}{{ fail "production monitoring namespace selector must be exact and non-empty" }}{{ end -}}
  {{- if empty .Values.monitoring.podSelector.matchLabels }}{{ fail "production monitoring pod selector must be exact and non-empty" }}{{ end -}}
  {{- if and .Values.gate.enabled (has $zeroUuid (list .Values.gate.fixture.tenant_id .Values.gate.fixture.account_id .Values.gate.fixture.wallet_id .Values.gate.fixture.project_id .Values.gate.fixture.job_id .Values.gate.fixture.stage_id .Values.gate.fixture.work_item_id .Values.gate.fixture.attempt_id .Values.gate.fixture.provider_pricing_version_id .Values.gate.fixture.commercial_pricing_version_id)) }}{{ fail "gate fixture must bind approved non-placeholder identities" }}{{ end -}}
{{- end -}}
{{- end -}}

{{- include "elmos-runtime.validate" . -}}
