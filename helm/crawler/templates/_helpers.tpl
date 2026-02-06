{{/*
Expand the name of the chart.
*/}}
{{- define "crawler.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "crawler.fullname" -}}
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
{{- define "crawler.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "crawler.labels" -}}
helm.sh/chart: {{ include "crawler.chart" . }}
{{ include "crawler.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "crawler.selectorLabels" -}}
app.kubernetes.io/name: {{ include "crawler.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Master selector labels
*/}}
{{- define "crawler.masterSelectorLabels" -}}
{{ include "crawler.selectorLabels" . }}
app: crawler-master
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "crawler.workerSelectorLabels" -}}
{{ include "crawler.selectorLabels" . }}
app: crawler-worker
{{- end }}

{{/*
Service account name
*/}}
{{- define "crawler.serviceAccountName" -}}
{{- if .Values.serviceAccount.name }}
{{- .Values.serviceAccount.name }}
{{- else }}
{{- include "crawler.fullname" . }}-sa
{{- end }}
{{- end }}

{{/*
Secret provider class name
*/}}
{{- define "crawler.secretProviderClassName" -}}
{{ include "crawler.fullname" . }}-secrets
{{- end }}

{{/*
Kubernetes secret name (synced from Key Vault)
*/}}
{{- define "crawler.secretName" -}}
{{ include "crawler.fullname" . }}-secrets
{{- end }}

{{/*
Full image name (handles both tags and digests)
*/}}
{{- define "crawler.image" -}}
{{- if hasPrefix "sha256:" .Values.image.tag }}
{{- printf "%s/%s@%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- else }}
{{- printf "%s/%s:%s" .Values.global.containerRegistry.server .Values.image.repository .Values.image.tag }}
{{- end }}
{{- end }}

{{/*
Master deployment name
*/}}
{{- define "crawler.masterName" -}}
{{ include "crawler.fullname" . }}-master
{{- end }}

{{/*
Worker deployment name
*/}}
{{- define "crawler.workerName" -}}
{{ include "crawler.fullname" . }}-worker
{{- end }}

{{/*
Master service name
*/}}
{{- define "crawler.masterServiceName" -}}
{{ include "crawler.fullname" . }}-master-service
{{- end }}
