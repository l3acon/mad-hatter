#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../utils/ee_build_prep.sh"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Use token from /etc/ansible/ansible.cfg when build-arg env vars are not set.
fill_galaxy_build_tokens_from_system_ansible_cfg || true

if [[ -z ${ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN:-} || -z ${ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN:-} ]]; then
  echo "A valid Automation Hub token is required. Either:"
  echo "  export ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN=<token>"
  echo "  export ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN=<token>"
  echo "or place a token under a [galaxy_server.*] section in \${SYSTEM_ANSIBLE_CFG:-/etc/ansible/ansible.cfg}"
  exit 1
fi

# Only require registry.redhat.io when the EE base_image pulls from there.
if grep -qE '^[[:space:]]*name:[[:space:]]*registry\.redhat\.io/' "${SCRIPT_DIR}/execution-environment.yml" 2>/dev/null; then
  ensure_podman_redhat_registry_login
else
  echo "No registry.redhat.io base_image in execution-environment.yml; skipping Red Hat registry login."
fi

if [[ "${SKIP_QUAY_PUSH:-}" == "1" ]]; then
  echo "SKIP_QUAY_PUSH=1: will build and tag locally but skip podman push."
else
  ensure_podman_quay_io_login
fi

# Optional: merge [defaults] from the repository ansible.cfg into this EE's ansible.cfg for the build only.
if [[ "${MERGE_REPO_ANSIBLE_CFG:-}" == 1 ]]; then
  _ee_ans_restore=$(mktemp)
  cp "${SCRIPT_DIR}/ansible.cfg" "${_ee_ans_restore}"
  trap 'mv -f "${_ee_ans_restore}" "${SCRIPT_DIR}/ansible.cfg"' EXIT
  merge_repo_defaults_into_ee_ansible_cfg "${SCRIPT_DIR}" "${REPO_ROOT}/ansible.cfg" "${_ee_ans_restore}"
fi

cd "${SCRIPT_DIR}"

IMAGE=quay.io/matferna/mh-$(basename "${SCRIPT_DIR}")
_tag=$(date +%Y%m%d)
IMAGE_TAG="${IMAGE}:${_tag}"

echo "Begin EE definition creation"
rm -rf ./context/*
ansible-builder create \
    --file execution-environment.yml \
    --context ./context \
    -v 3 | tee ansible-builder.log

# Single-arch image (default amd64). Avoid podman manifest lists with --manifest:
# an empty manifest list breaks `podman run` / pulls with
# "no image found in manifest list for architecture amd64".
for arch in amd64 # arm64: add a second build + manifest workflow if needed
do
    _baseurl=https://mirror.openshift.com/pub/openshift-v4/${arch}/dependencies/rpms/4.18-el9-beta/
    _rpm=$(curl -s "${_baseurl}" | grep openshift-clients-4 | grep href | cut -d\" -f2)

    pushd ./context/ > /dev/null
    echo "Begin podman build ${IMAGE_TAG} for ${arch}"
    podman build --platform linux/"${arch}" \
      --build-arg ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN \
      --build-arg ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN \
      --build-arg OPENSHIFT_CLIENT_RPM="${_baseurl}${_rpm}" \
      -t "${IMAGE_TAG}" . \
      | tee "podman-build-${arch}.log"
    popd > /dev/null
    echo "Finish podman build for ${arch} after ${SECONDS} seconds"
done

podman tag "${IMAGE_TAG}" "${IMAGE}:latest"

echo "Built ${IMAGE_TAG} and tagged ${IMAGE}:latest"
podman inspect "${IMAGE_TAG}" --format 'Architecture={{.Architecture}} OS={{.Os}}'

if [[ "${SKIP_QUAY_PUSH:-}" == "1" ]]; then
  echo "Skipping push (SKIP_QUAY_PUSH=1). Image available locally as ${IMAGE_TAG} and ${IMAGE}:latest"
else
  echo "Pushing ${IMAGE_TAG} and ${IMAGE}:latest"
  podman push "${IMAGE_TAG}"
  podman push "${IMAGE}:latest"
fi
