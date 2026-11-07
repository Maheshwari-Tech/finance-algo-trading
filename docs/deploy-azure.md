# Deploying the backend to Azure (AKS), automated

Backend only. The frontend is hosted separately and calls this API (set `CORS_ORIGINS`).
Everything in Azure is created from code: **Terraform** builds the infrastructure, **Helm** deploys the API, **GitHub Actions** runs both.

```
Internet → Application Gateway for Containers → AKS: Deployment "strategic-trader" (HPA, 2–10 pods)
                                                  └ pre-upgrade Job: python -m app.dbinit (tables + bundled NIFTY50)
 pods → PostgreSQL Flexible Server (private)      DATABASE_URL
 pods → Azure Cache for Redis (private endpoint)  REDIS_URL, shared rate limits
 pods ← Key Vault via Secrets Store CSI + workload identity (no stored credentials)
 images: Azure Container Registry     metrics: Managed Prometheus (optional Managed Grafana)
```

## What is where

| Path | Purpose |
|---|---|
| [deploy/terraform/](../deploy/terraform) | All Azure resources: network, ACR, AKS, PostgreSQL, Redis, Key Vault + secrets, identities and roles, Application Gateway for Containers, Prometheus |
| [deploy/scripts/bootstrap.sh](../deploy/scripts/bootstrap.sh) | **One-time**: Terraform state storage and the GitHub sign-in identity (Terraform cannot create these for itself) |
| [deploy/scripts/bootstrap-cluster.sh](../deploy/scripts/bootstrap-cluster.sh) | Namespace and ALB controller on a fresh cluster (run by the pipeline) |
| [deploy/helm/strategic-trader/](../deploy/helm/strategic-trader) | The API: Deployment, Service, autoscaler, DB-init job, Gateway route, secrets wiring |
| [Dockerfile.api](../Dockerfile.api) | Backend-only image |
| [.github/workflows/infra.yml](../.github/workflows/infra.yml) | Plans on pull requests; applies on `main` after approval |
| [.github/workflows/backend-aks.yml](../.github/workflows/backend-aks.yml) | Tests, builds the image, deploys with `helm --atomic`, smoke-tests |

The application pipeline reads every Azure name from Terraform's outputs, so nothing is copied between systems by hand.

## What you do (once)

### 1. Remove the resources created by hand earlier
They would collide with Terraform's names (the registry name is global).
```bash
az group delete -n rg-strategic-trader --yes --no-wait
az group delete -n DefaultResourceGroup-centralindia --yes --no-wait   # only if nothing else of yours uses it
```
Wait until `az group exists -n rg-strategic-trader` prints `false`.

### 2. Push this repo to GitHub
The workflows only run from GitHub.

### 3. One command in Azure Cloud Shell (Bash): Azure and GitHub setup
```bash
git clone https://github.com/<owner>/<repo> && cd <repo>
export GH_REPO=<owner>/<repo> SUFFIX=mt7k                 # SUFFIX: 3-6 lowercase letters/digits, makes global names unique
export OTP_CODE=<6 digits> ADMIN_MOBILES=<n1,n2> ALLOWED_MOBILES=<n1,n2,n3>
gh auth login                                              # once; or: export GH_TOKEN=<token with repo scope>
bash deploy/scripts/bootstrap.sh
```
This creates the Terraform state storage and the GitHub sign-in identity in Azure (OIDC, no stored passwords), **and sets every GitHub variable and secret and creates the `production` environment for you**, so there is nothing to type into GitHub by hand.

- The `production` environment pauses for your approval before applying infrastructure or deploying. Run with `REQUIRE_APPROVAL=false` to remove that pause (every merge then applies automatically). Required reviewers on private repositories need a GitHub Pro/Team plan; otherwise the script creates the environment without reviewers and tells you.
- Run it as someone who can assign roles (Owner on the subscription) and create app registrations. It is safe to run again.
- If the GitHub CLI is not signed in or the three values are not exported, the script prints the variables and secrets to add by hand instead (**Settings → Secrets and variables → Actions**, plus an Environment named `production`).

### 4. Create the infrastructure
GitHub → Actions → **Infrastructure (Terraform)** → Run workflow → `apply`. Approve when asked. It takes about 25–40 minutes (PostgreSQL with a standby and Redis are the slow parts). It then installs the ALB controller and creates the namespace.

### 5. Deploy the API
Push to `main`, or Actions → **Backend to AKS** → Run workflow. The pipeline runs tests, builds and pushes the image, runs the DB-init job (tables + NIFTY50), rolls out the pods and checks `/api/ready`. The job log ends with the API address; the same value is `terraform output api_fqdn`.

```bash
curl http://<api_fqdn>/api/ready      # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
```

After this, every push to `main` redeploys automatically, and every change under `deploy/terraform/` is planned on a pull request and applied on `main`.

## Before real users sign in: HTTPS
Until you add a certificate the API answers over plain HTTP, so the access code and tokens are not encrypted in transit. Do this first:
1. Get a certificate for your API name (for example `api.example.com`) and import it into Key Vault (PEM or PFX including the private key):
   `az keyvault certificate import --vault-name <kv> -n api-cert -f cert.pfx`
   (the vault name is `terraform output key_vault_name`; you need the *Key Vault Certificates Officer* role for this).
2. Add GitHub variables `TLS_CERT_NAME=api-cert` and `API_HOSTNAME=api.example.com`, and create a DNS CNAME `api.example.com` → the `api_fqdn` value.
3. Re-run **Backend to AKS**. The chart then serves HTTPS and the smoke test switches to `https://`.

## Everyday operations
| Task | How |
|---|---|
| Invite someone / change the access code | Edit the GitHub secret (`ALLOWED_MOBILES` / `OTP_CODE`), run **Infrastructure (Terraform)**. It updates Key Vault and restarts the pods. |
| Deploy a new version | Merge to `main`. A failed readiness check rolls back automatically. |
| Scale | API pods scale by CPU (`autoscaling.*` in the chart). Nodes scale 2–6 (`aks_min_nodes`/`aks_max_nodes`). Database size: `pg_sku_name`. All are code changes plus a pull request. |
| Turn on dashboards | Set `enable_grafana = true`, apply, then import `deploy/grafana/dashboards/backtest-lab.json` choosing the Azure Managed Prometheus data source. |
| Run Terraform by hand | In Cloud Shell: `cd deploy/terraform && terraform init -backend-config=../../backend.hcl && terraform plan` (set `TF_VAR_*` first, see `terraform.tfvars.example`; `bootstrap.sh` wrote `backend.hcl` where you ran it). |
| Tear it all down | Run **Infrastructure (Terraform)** with `destroy` (state storage from step 3 stays; delete `rg-tfstate` yourself). |

## Scaling and growth

| Concern | How it scales | Knob |
|---|---|---|
| API traffic | Pods by CPU, then nodes by the cluster autoscaler | chart `autoscaling.*`, Terraform `aks_max_nodes` |
| Heavy backtests | Same pods today. When they dominate, split a `worker` Deployment (own HPA, own node pool) fed by a queue and have the API enqueue and poll | new Deployment in the chart, extra node pool in `aks.tf` |
| Database | Vertical SKU, storage, read replicas | `pg_sku_name`, `pg_storage_mb` |
| Login limits and sessions | Redis shared across pods; sessions live in Postgres, so pods stay stateless | `redis_sku_name`, `redis_capacity` |
| New services | Add a Deployment and an `HTTPRoute` rule behind the same gateway | chart templates |

## Notes
- Terraform state holds the generated database password and keys. It sits in a private storage account without shared-key access; keep access to it restricted.
- Do not change these resources in the portal; the next apply reverts the change. Change the code instead.
- Costs come mainly from AKS nodes, PostgreSQL (zone-redundant by default), Redis, Application Gateway for Containers and Prometheus. For a cheaper non-production setup set `pg_high_availability = false` and a smaller `pg_sku_name`.
- Optional hardening once traffic flows: `networkPolicy.enabled=true` with `albSubnetCidr=10.10.8.0/24`, a WAF policy on the gateway, a least-privilege Postgres role, and Key Vault network restrictions.
- The ALB controller version is `ALB_CONTROLLER_VERSION` (repo variable, default `1.13.0`).
