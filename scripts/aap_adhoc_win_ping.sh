#!/usr/bin/env bash
# Launch AAP ad-hoc win_ping against a KubeVirt Windows host (reads .env from repo root).
#
# Prerequisite: the inventory host must use ansible_connection=winrm (and related vars).
# AAP blocks those keys in ad-hoc extra_vars; merge them on the host (API PATCH) or in group_vars.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
[[ -f "${ROOT}/.env" ]] && set -a && source "${ROOT}/.env" && set +a

: "${CONTROLLER_HOST:?Set CONTROLLER_HOST in .env}"
: "${CONTROLLER_USERNAME:?Set CONTROLLER_USERNAME in .env}"
: "${CONTROLLER_PASSWORD:?Set CONTROLLER_PASSWORD in .env}"
: "${AAP_WINRM_CREDENTIAL_ID:?Set AAP_WINRM_CREDENTIAL_ID in .env (Machine credential id)}"
: "${AAP_KUBEVIRT_INVENTORY_ID:?Set AAP_KUBEVIRT_INVENTORY_ID in .env}"
: "${AAP_DEFAULT_EE_ID:?Set AAP_DEFAULT_EE_ID in .env (ee-supported-rhel9)}"
: "${AAP_WIN_HOST_LIMIT:?Set AAP_WIN_HOST_LIMIT (inventory hostname e.g. namespace-vmname)}"

BASE="${CONTROLLER_HOST%/}/api/v2"
AUTH=(-sS -u "${CONTROLLER_USERNAME}:${CONTROLLER_PASSWORD}" -k)

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
# AAP forbids WinRM-related keys in ad hoc extra_vars; set ansible_connection on the inventory host instead.
jq -n \
  --argjson inv "$AAP_KUBEVIRT_INVENTORY_ID" \
  --argjson cred "$AAP_WINRM_CREDENTIAL_ID" \
  --argjson ee "$AAP_DEFAULT_EE_ID" \
  --arg lim "$AAP_WIN_HOST_LIMIT" \
  '{
    inventory: $inv,
    credential: $cred,
    execution_environment: $ee,
    module_name: "win_ping",
    module_args: "",
    limit: $lim,
    job_type: "run",
    forks: 1,
    verbosity: 1
  }' >"$TMP"

RESP="$(/usr/bin/curl "${AUTH[@]}" -X POST "${BASE}/ad_hoc_commands/" -H 'Content-Type: application/json' --data-binary @"$TMP")"
JOB_ID="$(echo "$RESP" | jq -r .id)"
if [[ -z "$JOB_ID" || "$JOB_ID" == "null" ]]; then
  echo "$RESP" | jq .
  exit 1
fi
echo "Launched ad hoc job id=${JOB_ID}"

for _ in $(seq 1 60); do
  ST="$(/usr/bin/curl "${AUTH[@]}" "${BASE}/ad_hoc_commands/${JOB_ID}/" | jq -r .status)"
  echo "status: $ST"
  case "$ST" in successful | failed | error | canceled) break ;; esac
  sleep 5
done

/usr/bin/curl "${AUTH[@]}" "${BASE}/ad_hoc_commands/${JOB_ID}/stdout/?format=txt_download" | tail -40
