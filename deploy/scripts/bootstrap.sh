#!/usr/bin/env bash
# One-time setup that Terraform needs before it can run, and cannot create for itself:
#   1. a storage account for the Terraform state
#   2. the identity GitHub Actions signs in with (OIDC, no stored secrets) and its permissions
# Run in Azure Cloud Shell (Bash), logged in as someone who can create role assignments (Owner on the subscription).
#
#   export GH_REPO=<owner>/<repo>  SUFFIX=<3-6 lowercase letters/digits>
#   export OTP_CODE=<6 digits> ADMIN_MOBILES=<n1,n2> ALLOWED_MOBILES=<n1,n2,...>   # stored as GitHub secrets
#   gh auth login            # once, or: export GH_TOKEN=<token with repo scope>
#   bash deploy/scripts/bootstrap.sh
#
# With the GitHub CLI signed in and the three values exported, it also sets every GitHub variable and secret and
# creates the "production" environment (you approve each apply and deploy; REQUIRE_APPROVAL=false removes that).
# Without them it prints what to add by hand. Safe to run again.
set -euo pipefail

: "${GH_REPO:?set GH_REPO=<owner>/<repo>}"
: "${SUFFIX:?set SUFFIX=<3-6 lowercase letters/digits, same as the Terraform suffix>}"
LOC="${LOC:-centralindia}"
STATE_RG="${STATE_RG:-rg-tfstate}"
STATE_SA="${STATE_SA:-sttfstate${SUFFIX}}"   # 3-24 lowercase letters/digits, globally unique
STATE_CONTAINER="tfstate"
APP_NAME="${APP_NAME:-gh-strategic-trader-deploy}"

SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
ME_OID="$(az ad signed-in-user show --query id -o tsv)"
echo "Subscription $SUB_ID  tenant $TENANT_ID"

assign() { # principal-object-id principal-type role scope
  if [ -z "$(az role assignment list --assignee "$1" --role "$3" --scope "$4" --query '[0].id' -o tsv 2>/dev/null)" ]; then
    az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" --role "$3" --scope "$4" -o none
    echo "  granted: $3"
  fi
}

echo "== Terraform state storage"
az group create -n "$STATE_RG" -l "$LOC" -o none
az storage account create -g "$STATE_RG" -n "$STATE_SA" -l "$LOC" --sku Standard_ZRS --kind StorageV2 \
  --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false -o none
SA_ID="$(az storage account show -g "$STATE_RG" -n "$STATE_SA" --query id -o tsv)"
assign "$ME_OID" User "Storage Blob Data Contributor" "$SA_ID"
for i in 1 2 3 4 5 6; do   # role assignments take a moment to apply
  az storage container create --account-name "$STATE_SA" -n "$STATE_CONTAINER" --auth-mode login -o none 2>/dev/null && break
  echo "  waiting for the role to apply..."; sleep 20
done

echo "== GitHub OIDC identity"
APP_ID="$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv)"
[ -n "$APP_ID" ] || APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
az ad sp show --id "$APP_ID" >/dev/null 2>&1 || az ad sp create --id "$APP_ID" -o none
SP_OID="$(az ad sp show --id "$APP_ID" --query id -o tsv)"

for subject in "repo:${GH_REPO}:ref:refs/heads/main" "repo:${GH_REPO}:environment:production" "repo:${GH_REPO}:pull_request"; do
  name="gh-$(echo "$subject" | tr -c 'a-zA-Z0-9\n' '-' | cut -c1-60)"
  if [ -z "$(az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$subject'].name" -o tsv)" ]; then
    az ad app federated-credential create --id "$APP_ID" --parameters \
      "{\"name\":\"$name\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"$subject\",\"audiences\":[\"api://AzureADTokenExchange\"]}" -o none
    echo "  trust added: $subject"
  fi
done

# Terraform creates resources and the role assignments between them.
assign "$SP_OID" ServicePrincipal "Contributor" "/subscriptions/$SUB_ID"
assign "$SP_OID" ServicePrincipal "Role Based Access Control Administrator" "/subscriptions/$SUB_ID"
assign "$SP_OID" ServicePrincipal "Storage Blob Data Contributor" "$SA_ID"

cat > backend.hcl <<EOF
resource_group_name  = "$STATE_RG"
storage_account_name = "$STATE_SA"
container_name       = "$STATE_CONTAINER"
key                  = "strategic-trader.tfstate"
use_azuread_auth     = true
EOF

echo "== GitHub configuration"
VARS=(
  "AZURE_CLIENT_ID=$APP_ID"
  "AZURE_TENANT_ID=$TENANT_ID"
  "AZURE_SUBSCRIPTION_ID=$SUB_ID"
  "TFSTATE_RG=$STATE_RG"
  "TFSTATE_STORAGE=$STATE_SA"
  "TF_SUFFIX=$SUFFIX"
  "ADMIN_OBJECT_IDS=[\"$ME_OID\"]"
)
SECRET_NAMES=(OTP_CODE ADMIN_MOBILES ALLOWED_MOBILES)

have_secrets=true
for s in "${SECRET_NAMES[@]}"; do [ -n "${!s:-}" ] || have_secrets=false; done

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1 && [ "$have_secrets" = true ]; then
  for kv in "${VARS[@]}"; do gh variable set "${kv%%=*}" --body "${kv#*=}" --repo "$GH_REPO"; done
  for s in "${SECRET_NAMES[@]}"; do printf '%s' "${!s}" | gh secret set "$s" --repo "$GH_REPO"; done
  echo "  variables and secrets set on $GH_REPO"

  # The "production" environment gates apply and deploy. REQUIRE_APPROVAL=false removes the pause.
  if [ "${REQUIRE_APPROVAL:-true}" = true ]; then
    GH_UID="$(gh api user --jq .id)"
    if printf '{"reviewers":[{"type":"User","id":%s}]}' "$GH_UID" \
         | gh api -X PUT "repos/$GH_REPO/environments/production" --input - >/dev/null 2>&1; then
      echo "  environment 'production' created; you must approve each apply and deploy"
    else
      gh api -X PUT "repos/$GH_REPO/environments/production" >/dev/null
      echo "  environment 'production' created WITHOUT reviewers (private repos need GitHub Pro/Team for required reviewers)"
    fi
  else
    gh api -X PUT "repos/$GH_REPO/environments/production" >/dev/null
    echo "  environment 'production' created with no approval gate: every merge applies automatically"
  fi
  echo
  echo "Done. Next: GitHub > Actions > 'Infrastructure (Terraform)' > Run workflow > apply."
else
  echo "  GitHub CLI not ready, so set these by hand (or re-run after 'gh auth login' with OTP_CODE, ADMIN_MOBILES, ALLOWED_MOBILES exported)."
  cat <<EOF

In GitHub > Settings > Secrets and variables > Actions, add these VARIABLES:

  AZURE_CLIENT_ID        $APP_ID
  AZURE_TENANT_ID        $TENANT_ID
  AZURE_SUBSCRIPTION_ID  $SUB_ID
  TFSTATE_RG             $STATE_RG
  TFSTATE_STORAGE        $STATE_SA
  TF_SUFFIX              $SUFFIX
  ADMIN_OBJECT_IDS       ["$ME_OID"]        (JSON list of people who should get cluster admin; optional)

and these SECRETS:

  OTP_CODE               the 6-digit access code you give to users
  ADMIN_MOBILES          admin mobile numbers, comma separated
  ALLOWED_MOBILES        invited mobile numbers, comma separated

Also create an Environment named "production" (Settings > Environments); add required reviewers for an approval step.
EOF
fi
echo "A backend.hcl for running Terraform by hand was written to $(pwd)/backend.hcl (keep it out of git)."
