#!/bin/bash
# Validate Ansible collections inside an EE image (podman).
set -euo pipefail

IMAGE="${1:-quay.io/matferna/mh-rosa:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EE_DIR="${2:-${SCRIPT_DIR}/../rosa}"

echo "==> Image: ${IMAGE}"
echo "==> ansible-playbook --version"
podman run --pull=missing --rm "${IMAGE}" ansible-playbook --version

echo "==> ansible-galaxy collection list"
list_out=$(podman run --pull=missing --rm "${IMAGE}" ansible-galaxy collection list)
printf '%s\n' "${list_out}"

req="${EE_DIR}/requirements.yml"
if [[ ! -f "$req" ]]; then
  echo "No requirements at ${req}; skipping name checks." >&2
  exit 0
fi

echo "==> Verify collections declared in ${req}"
mapfile -t NAMES < <(grep -E '^\s+- name:\s*' "$req" | sed 's/^[[:space:]]*- name:[[:space:]]*//' | tr -d '"' | tr -d "'")
for c in "${NAMES[@]}"; do
  [[ -z "$c" ]] && continue
  if printf '%s\n' "${list_out}" | awk '{print $1}' | grep -qx "${c}"; then
    echo "  OK  ${c}"
  else
    echo "  MISSING: ${c}" >&2
    exit 1
  fi
done

echo "==> oc client"
podman run --pull=missing --rm "${IMAGE}" oc version --client 2>&1 | head -3

echo "All checks passed."
