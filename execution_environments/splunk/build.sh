#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image="${SPLUNK_EE_IMAGE:-quay.io/matferna/mh-splunk}"
tag="${SPLUNK_EE_TAG:-$(date +%Y%m%d)}"
cd "$script_dir"
podman build --platform linux/amd64 -f Containerfile -t "${image}:${tag}" .
podman tag "${image}:${tag}" "${image}:latest"
podman inspect "${image}:${tag}" --format 'Architecture={{.Architecture}} OS={{.Os}}'

if [[ "${SKIP_QUAY_PUSH:-0}" != 1 ]]; then
  podman push "${image}:${tag}"
  podman push "${image}:latest"
fi
