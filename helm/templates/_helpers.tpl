{{- define "vow-agent.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: vow-agent
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
{{- end }}

{{- define "vow-agent.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
