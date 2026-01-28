{{/*
Expand the name of the chart.
*/}}
{{- define "ask-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ask-api.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ask-api.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ask-api.labels" -}}
helm.sh/chart: {{ include "ask-api.chart" . }}
{{ include "ask-api.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ask-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ask-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: ask-api
{{- end }}

{{/*
Service account name
*/}}
{{- define "ask-api.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "ask-api.fullname" . }}-sa
{{- end }}
{{- end }}

{{/*
Secret provider class name
*/}}
{{- define "ask-api.secretProviderClassName" -}}
{{ include "ask-api.fullname" . }}-secrets
{{- end }}

{{/*
Kubernetes secret name (synced from Key Vault)
*/}}
{{- define "ask-api.secretName" -}}
{{ include "ask-api.fullname" . }}-secrets
{{- end }}

{{/*
Full image name (handles both tags and digests)
*/}}
{{- define "ask-api.image" -}}
{{- if hasPrefix "sha256:" .Values.image.tag }}
{{- printf "%s/%s@%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- else }}
{{- printf "%s/%s:%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- end }}
{{- end }}
