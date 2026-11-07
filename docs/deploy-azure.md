# Deploying the backend to Azure (AKS)

Backend only. The frontend is built and hosted separately and calls this API (set `CORS_ORIGINS`).

```
Internet → Application Gateway for Containers (TLS) → AKS: Deployment "strategic-trader" (HPA, 2–10 pods)
                                                       └ pre-upgrade Job: python -m app.dbinit (schema + bundled NIFTY50)
 pods → Azure Database for PostgreSQL Flexible Server   DATABASE_URL     (private access)
 pods → Azure Redis                                     REDIS_URL        (shared rate limits across pods)
 pods ← Key Vault via Secrets Store CSI + workload identity (no stored credentials)
 images: Azure Container Registry     metrics: Managed Prometheus + Managed Grafana (scrapes /metrics)
 CI/CD: GitHub Actions (OIDC) → ACR → helm upgrade --atomic
```

What is in the repo: [Dockerfile.api](../Dockerfile.api) (backend-only image), [deploy/helm/strategic-trader](../deploy/helm/strategic-trader) (chart), [deploy/azure/alb.yaml](../deploy/azure/alb.yaml) (one-time gateway resource), [.github/workflows/backend-aks.yml](../.github/workflows/backend-aks.yml) (pipeline).

Design choices worth knowing:
- Only `/api/*` is routed by the gateway, so `/metrics` is never public. The gateway health check hits `/api/ready` (the API has no `/` route without the frontend).
- Replicas never create tables or seed data. A Helm pre-install/pre-upgrade Job does that once (`SEED_DEFAULT_DATASET=false` on the pods), so scaling out cannot race on an empty database.
- Sign-in is invite-only: the admin gives each person the shared 6-digit code; `ALLOWED_MOBILES` lists who may sign in. Both come from Key Vault.

## 0. Variables (bash)

```bash
export LOC=centralindia RG=rg-strategic-trader
export ACR=<globally-unique-acr-name> AKS=aks-trader KV=<globally-unique-kv-name>
export PG=<globally-unique-pg-name> REDIS=<globally-unique-redis-name>
export NS=trader        # Kubernetes namespace
export REL=strategic-trader   # Helm release name (also the ServiceAccount name)
az login && az account set --subscription <subscription-id>
az provider register -n Microsoft.ContainerService -n Microsoft.Network -n Microsoft.NetworkFunction \
  -n Microsoft.ServiceNetworking -n Microsoft.DBforPostgreSQL -n Microsoft.KeyVault -n Microsoft.Cache
az group create -n $RG -l $LOC
```

## 1. Network

```bash
az network vnet create -g $RG -n vnet-trader --address-prefixes 10.10.0.0/16
az network vnet subnet create -g $RG --vnet-name vnet-trader -n snet-aks   --address-prefixes 10.10.0.0/22
az network vnet subnet create -g $RG --vnet-name vnet-trader -n snet-alb   --address-prefixes 10.10.8.0/24 \
  --delegations Microsoft.ServiceNetworking/trafficControllers        # Application Gateway for Containers
az network vnet subnet create -g $RG --vnet-name vnet-trader -n snet-pg    --address-prefixes 10.10.9.0/24 \
  --delegations Microsoft.DBforPostgreSQL/flexibleServers
az network vnet subnet create -g $RG --vnet-name vnet-trader -n snet-pe    --address-prefixes 10.10.10.0/24
```

## 2. Registry and cluster

```bash
az acr create -g $RG -n $ACR --sku Standard

SUBNET_AKS=$(az network vnet subnet show -g $RG --vnet-name vnet-trader -n snet-aks --query id -o tsv)
az aks create -g $RG -n $AKS -l $LOC --zones 1 2 3 \
  --network-plugin azure --network-plugin-mode overlay --vnet-subnet-id $SUBNET_AKS \
  --node-count 2 --enable-cluster-autoscaler --min-count 2 --max-count 6 --node-vm-size Standard_D2as_v5 \
  --enable-oidc-issuer --enable-workload-identity \
  --enable-aad --enable-azure-rbac \
  --enable-addons azure-keyvault-secrets-provider --enable-secret-rotation \
  --enable-azure-monitor-metrics \
  --attach-acr $ACR
az aks get-credentials -g $RG -n $AKS
kubectl create namespace $NS
```

`--enable-azure-monitor-metrics` turns on Managed Prometheus (the chart's `PodMonitor` is scraped by it). Add Managed Grafana from the portal or `az grafana create`, link it to the Azure Monitor workspace, and import `deploy/grafana/dashboards/backtest-lab.json`.

## 3. PostgreSQL (private access)

```bash
az postgres flexible-server create -g $RG -n $PG -l $LOC --version 16 \
  --tier GeneralPurpose --sku-name Standard_D2ds_v5 --storage-size 64 --zonal-resiliency Enabled \
  --vnet vnet-trader --subnet snet-pg --private-dns-zone $PG.private.postgres.database.azure.com \
  --admin-user trader_admin --admin-password '<strong-password>' --database-name trader --yes
```

`DATABASE_URL=postgresql://trader_admin:<url-encoded-password>@<PG>.postgres.database.azure.com:5432/trader?sslmode=require`
(the app converts the scheme to the psycopg driver). For production use a dedicated least-privilege role instead of the admin user.
Scale the database independently with `az postgres flexible-server update --sku-name ...`.

## 4. Redis (shared rate limits)

The login rate limits must be shared across pods, otherwise each pod counts on its own.

```bash
az redis create -g $RG -n $REDIS -l $LOC --sku Standard --vm-size c1 --minimum-tls-version 1.2
```

Put a private endpoint on it in `snet-pe`. `REDIS_URL=rediss://:<access-key>@<REDIS>.redis.cache.windows.net:6380/0`.
Azure Cache for Redis is being succeeded by **Azure Managed Redis**; if you use that, the TLS port is 10000, so add it to `networkPolicy.egressPorts` and use the Enterprise cluster policy so the plain client works.

## 5. Key Vault, secrets and workload identity

```bash
az keyvault create -g $RG -n $KV -l $LOC --enable-rbac-authorization true
KV_ID=$(az keyvault show -n $KV --query id -o tsv)
az role assignment create --assignee $(az ad signed-in-user show --query id -o tsv) --role "Key Vault Secrets Officer" --scope $KV_ID

python3 -c "import secrets;print(secrets.token_urlsafe(48))"                 # SECRET_KEY
python3 -c "import secrets;print(f'{secrets.randbelow(10**6):06d}')"         # OTP_DEV_CODE (the 6-digit code you give users)

az keyvault secret set --vault-name $KV -n database-url   --value '<DATABASE_URL>'
az keyvault secret set --vault-name $KV -n redis-url      --value '<REDIS_URL>'
az keyvault secret set --vault-name $KV -n secret-key     --value '<generated>'
az keyvault secret set --vault-name $KV -n admin-mobiles  --value '<admin numbers, comma separated>'
az keyvault secret set --vault-name $KV -n otp-dev-code   --value '<6 digits>'
az keyvault secret set --vault-name $KV -n allowed-mobiles --value '<invited numbers, comma separated>'

# Identity the pods use to read the vault
az identity create -g $RG -n id-trader-api
export WI_CLIENT_ID=$(az identity show -g $RG -n id-trader-api --query clientId -o tsv)
az role assignment create --assignee $WI_CLIENT_ID --role "Key Vault Secrets User" --scope $KV_ID
az identity federated-credential create -g $RG --identity-name id-trader-api -n aks-$NS \
  --issuer $(az aks show -g $RG -n $AKS --query oidcIssuerProfile.issuerUrl -o tsv) \
  --subject system:serviceaccount:$NS:$REL --audience api://AzureADTokenExchange
```

The ServiceAccount name equals the Helm release name (`strategic-trader`), which is what the federated credential trusts.

**Inviting someone:** append their number to `allowed-mobiles`, then restart so pods re-read it:
`kubectl -n $NS rollout restart deploy/$REL`. Changing the code is the same (`otp-dev-code`). Environment variables are read at pod start; CSI rotation does not update them.

## 6. Application Gateway for Containers

```bash
az extension add --name alb
AKS_NODE_RG=$(az aks show -g $RG -n $AKS --query nodeResourceGroup -o tsv)
AKS_NODE_RG_ID=$(az group show -n $AKS_NODE_RG --query id -o tsv)
SUBNET_ALB_ID=$(az network vnet subnet show -g $RG --vnet-name vnet-trader -n snet-alb --query id -o tsv)

# Identity for the ALB controller
az identity create -g $RG -n id-alb-controller
ALB_CLIENT_ID=$(az identity show -g $RG -n id-alb-controller --query clientId -o tsv)
az identity federated-credential create -g $RG --identity-name id-alb-controller -n alb-controller \
  --issuer $(az aks show -g $RG -n $AKS --query oidcIssuerProfile.issuerUrl -o tsv) \
  --subject system:serviceaccount:azure-alb-system:alb-controller-sa --audience api://AzureADTokenExchange
az role assignment create --assignee $ALB_CLIENT_ID --role "Reader" --scope $AKS_NODE_RG_ID
az role assignment create --assignee $ALB_CLIENT_ID --role "AppGw for Containers Configuration Manager" --scope $AKS_NODE_RG_ID
az role assignment create --assignee $ALB_CLIENT_ID --role "Network Contributor" --scope $SUBNET_ALB_ID

# Controller (pin the current version listed in the Microsoft docs: "Quickstart: Deploy Application Gateway for Containers ALB Controller")
helm install alb-controller oci://mcr.microsoft.com/application-lb/charts/alb-controller \
  --namespace azure-alb-system --create-namespace --version <ALB_CONTROLLER_VERSION> \
  --set albController.namespace=azure-alb-system --set albController.podIdentity.clientID=$ALB_CLIENT_ID

# The gateway resource (once per cluster)
ALB_SUBNET_ID=$SUBNET_ALB_ID envsubst < deploy/azure/alb.yaml | kubectl apply -f -
kubectl -n alb-infra get applicationloadbalancer alb-trader -o jsonpath='{.status.conditions}'   # wait for Deployment=True
```

**TLS:** import your certificate into Key Vault (`az keyvault certificate import --vault-name $KV -n api-cert -f cert.pfx`, PEM with key also works) and set the repo variable `TLS_CERT_NAME=api-cert`. The chart syncs it to a TLS secret for the HTTPS listener.

**DNS:** after the first deploy, `kubectl -n $NS get gateway $REL -o jsonpath='{.status.addresses[0].value}'` gives the gateway FQDN. Create a CNAME `api.<yourdomain>` pointing to it.

## 7. GitHub Actions (OIDC, no secrets)

```bash
az ad app create --display-name gh-trader-deploy --query appId -o tsv        # -> GH_CLIENT_ID
az ad sp create --id $GH_CLIENT_ID
for SUBJ in "repo:<owner>/<repo>:ref:refs/heads/main" "repo:<owner>/<repo>:environment:production"; do
  az ad app federated-credential create --id $GH_CLIENT_ID --parameters \
    "{\"name\":\"gh-$(echo $SUBJ | tr -c 'a-zA-Z0-9' '-')\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"$SUBJ\",\"audiences\":[\"api://AzureADTokenExchange\"]}"
done
az role assignment create --assignee $GH_CLIENT_ID --role AcrPush --scope $(az acr show -n $ACR --query id -o tsv)
AKS_ID=$(az aks show -g $RG -n $AKS --query id -o tsv)
az role assignment create --assignee $GH_CLIENT_ID --role "Azure Kubernetes Service Cluster User Role" --scope $AKS_ID
az role assignment create --assignee $GH_CLIENT_ID --role "Azure Kubernetes Service RBAC Admin" --scope $AKS_ID/namespaces/$NS
```

In GitHub → Settings → Secrets and variables → Actions → **Variables** (and create an Environment named `production`; add required reviewers there for a manual approval gate):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | `$GH_CLIENT_ID` |
| `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | from `az account show` |
| `ACR_NAME` | `$ACR` |
| `AKS_RESOURCE_GROUP`, `AKS_CLUSTER` | `$RG`, `$AKS` |
| `K8S_NAMESPACE` | `$NS` |
| `KEYVAULT_NAME` | `$KV` |
| `WORKLOAD_IDENTITY_CLIENT_ID` | `$WI_CLIENT_ID` |
| `API_HOSTNAME` | e.g. `api.example.com` |
| `TLS_CERT_NAME` | `api-cert` (empty = HTTP only) |
| `CORS_ORIGINS` | your frontend URL(s), comma separated |

## 8. Deploy and verify

Push to `main`. The pipeline runs ruff and pytest, lints the chart, builds and pushes the image, then runs `helm upgrade --install --atomic`. A failed readiness check rolls the release back automatically.

```bash
kubectl -n $NS get pods,hpa,gateway,httproute
kubectl -n $NS logs job/$REL-db-init          # only while the Job exists; look for "Loaded default dataset NIFTY50"
curl https://api.<yourdomain>/api/ready        # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
curl -i https://api.<yourdomain>/metrics       # must NOT be reachable (404)
```

Manual deploy (same as CI): `helm upgrade --install $REL deploy/helm/strategic-trader -n $NS --atomic --wait --set image.repository=$ACR.azurecr.io/strategic-trader-api --set image.tag=<sha> --set keyVault.name=$KV --set keyVault.tenantId=<tenant> --set keyVault.workloadIdentityClientId=$WI_CLIENT_ID --set gateway.hostname=api.<yourdomain>`.

## Scaling and growth

| Concern | How it scales | Knob |
|---|---|---|
| API traffic | Pods by CPU, nodes by the cluster autoscaler | `autoscaling.*`, `az aks nodepool update --max-count` |
| Heavy backtests | Same pods today. When they dominate, split a `worker` Deployment (own HPA, own node pool) fed by a queue (Service Bus + KEDA) and have the API enqueue and poll | new Deployment in the chart |
| Database | Vertical SKU, storage, read replicas | `az postgres flexible-server update` |
| Login limits and sessions | Redis shared across pods; sessions live in Postgres, so pods stay stateless | Redis SKU |
| Isolation | Dedicated node pools via `nodeSelector`/`tolerations` | values |
| New services | Add Deployments + `HTTPRoute` rules behind the same gateway | chart templates |

Optional hardening once traffic flows: set `networkPolicy.enabled=true` with `albSubnetCidr=10.10.8.0/24`, add a WAF policy to the gateway, and use a least-privilege Postgres role.
