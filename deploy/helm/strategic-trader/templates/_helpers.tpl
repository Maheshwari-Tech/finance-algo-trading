{{- define "st.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "st.serviceAccountName" -}}
{{- default (include "st.fullname" .) .Values.serviceAccount.name -}}
{{- end -}}

{{- define "st.secretName" -}}
{{- printf "%s-secrets" (include "st.fullname" .) -}}
{{- end -}}

{{- define "st.tlsSecretName" -}}
{{- default (printf "%s-tls" (include "st.fullname" .)) .Values.gateway.tls.secretName -}}
{{- end -}}

{{- define "st.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "st.labels" -}}
{{ include "st.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "st.image" -}}
{{- required "image.repository is required" .Values.image.repository -}}:{{- required "image.tag is required" .Values.image.tag -}}
{{- end -}}

{{/* Settings shared by the API Deployment and the db-init Job. */}}
{{- define "st.env" -}}
- {name: APP_ENV, value: {{ .Values.app.env | quote }}}
- {name: AUTH_MODE, value: {{ .Values.app.authMode | quote }}}
- {name: DEFAULT_COUNTRY_CODE, value: {{ .Values.app.defaultCountryCode | quote }}}
- {name: CORS_ORIGINS, value: {{ .Values.app.corsOrigins | quote }}}
- {name: LOG_LEVEL, value: {{ .Values.app.logLevel | quote }}}
- {name: LOG_JSON, value: "true"}
- {name: SEED_DEFAULT_DATASET, value: {{ .Values.app.seedDefaultDataset | quote }}}
{{- end -}}

{{/* Pod settings shared by the API Deployment and the db-init Job. */}}
{{- define "st.podCommon" -}}
serviceAccountName: {{ include "st.serviceAccountName" . }}
automountServiceAccountToken: false
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile: {type: RuntimeDefault}
{{- with .Values.nodeSelector }}
nodeSelector: {{ toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations: {{ toYaml . | nindent 2 }}
{{- end }}
volumes:
  - name: secrets-store
    csi:
      driver: secrets-store.csi.k8s.io
      readOnly: true
      volumeAttributes:
        secretProviderClass: {{ include "st.fullname" . }}
  - name: tmp
    emptyDir: {}
{{- end -}}

{{- define "st.containerCommon" -}}
image: {{ include "st.image" . }}
imagePullPolicy: {{ .Values.image.pullPolicy }}
env:
{{ include "st.env" . }}
envFrom:
  - secretRef: {name: {{ include "st.secretName" . }}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities: {drop: [ALL]}
volumeMounts:
  # Mounting the CSI volume is what makes the driver create the Kubernetes Secret used by envFrom.
  - {name: secrets-store, mountPath: /mnt/secrets-store, readOnly: true}
  - {name: tmp, mountPath: /tmp}
{{- end -}}
