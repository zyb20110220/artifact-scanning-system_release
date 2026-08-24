{{- define "hello-world.fullname" -}}
{{- printf "%s" .Release.Name -}}
{{- end -}}

{{- define "hello-world.labels" -}}
app.kubernetes.io/name: hello-world
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
