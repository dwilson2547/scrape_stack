{{- define "scrape-stack.namespace" -}}
{{- .Values.namespace.name | default .Release.Namespace -}}
{{- end -}}

{{- define "scrape-stack.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: scrape-stack
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "scrape-stack.fqdn" -}}
{{- if .prefix -}}
{{- printf "%s.%s" .prefix .domain -}}
{{- else -}}
{{- .domain -}}
{{- end -}}
{{- end -}}
