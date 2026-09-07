{{- define "elmos-autonomy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end }}
{{- define "elmos-autonomy.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "elmos-autonomy.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}
{{- define "elmos-autonomy.labels" -}}
app.kubernetes.io/name: {{ include "elmos-autonomy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
