{{- define "proof-harness.name" -}}
proof-harness
{{- end -}}
{{- define "proof-harness.fullname" -}}
{{ .Release.Name }}-proof-harness
{{- end -}}
{{- define "proof-harness.serviceAccountName" -}}
{{- if .Values.serviceAccount.name -}}
{{ .Values.serviceAccount.name }}
{{- else -}}
{{ include "proof-harness.fullname" . }}
{{- end -}}
{{- end -}}
{{- define "proof-harness.selectorLabels" -}}
app.kubernetes.io/name: {{ include "proof-harness.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "proof-harness.labels" -}}
{{ include "proof-harness.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}
