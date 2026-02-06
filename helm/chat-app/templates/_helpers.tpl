{{/*
Expand the name of the chart.
*/}}
{{- define "chat-app.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "chat-app.fullname" -}}
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
{{- define "chat-app.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "chat-app.labels" -}}
helm.sh/chart: {{ include "chat-app.chart" . }}
{{ include "chat-app.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "chat-app.selectorLabels" -}}
app.kubernetes.io/name: {{ include "chat-app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: chat-app
{{- end }}

{{/*
Full image name (handles both tags and digests)
*/}}
{{- define "chat-app.image" -}}
{{- if hasPrefix "sha256:" .Values.image.tag }}
{{- printf "%s/%s@%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- else }}
{{- printf "%s/%s:%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- end }}
{{- end }}
