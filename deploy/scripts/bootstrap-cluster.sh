#!/usr/bin/env bash
# Prepares a fresh AKS cluster for the API: the namespace and the Application Gateway for Containers (ALB) controller.
# Called by the infra workflow after `terraform apply`. Idempotent. Needs az, kubectl, helm and kubelogin, and cluster access.
#
#   RG=... AKS=... NS=... ALB_CLIENT_ID=... bash deploy/scripts/bootstrap-cluster.sh
set -euo pipefail

: "${RG:?}" "${AKS:?}" "${NS:?}" "${ALB_CLIENT_ID:?}"
ALB_VERSION="${ALB_VERSION:-1.13.0}"   # https://mcr.microsoft.com/v2/application-lb/charts/alb-controller/tags/list

az aks get-credentials -g "$RG" -n "$AKS" --overwrite-existing
command -v kubelogin >/dev/null && kubelogin convert-kubeconfig -l azurecli

# Cluster role assignments can take a few minutes to reach the API server.
for i in $(seq 1 20); do
  kubectl get ns >/dev/null 2>&1 && break
  echo "waiting for cluster access ($i)..."; sleep 15
done

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install alb-controller oci://mcr.microsoft.com/application-lb/charts/alb-controller \
  --namespace azure-alb-system --create-namespace --version "$ALB_VERSION" \
  --set albController.namespace=azure-alb-system \
  --set albController.podIdentity.clientID="$ALB_CLIENT_ID" \
  --wait --timeout 10m

kubectl -n azure-alb-system get pods
