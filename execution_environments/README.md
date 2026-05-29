# Execution Environments

This directory contains Execution Environment (EE) definitions for
`ansible-builder`. Each subdirectory (`aro/`, `rosa/`) has its own
`execution-environment.yml`, `requirements.yml`, and `build.sh`.

## Building

Each EE has a `build.sh` script. Shared prep logic lives in
`utils/ee_build_prep.sh` (sourced automatically).

```bash
cd execution_environments/rosa   # or aro
./build.sh
```

### Registry authentication

The build scripts handle three registries. For each, you can either
`podman login` beforehand or export environment variables.

**registry.redhat.io** (base images):

If `podman login --get-login registry.redhat.io` does not already return a
user, the script runs non-interactive login using `REGISTRY_REDHAT_IO_USER`
(or `REGISTRY_REDHAT_IO_USERNAME`) and `REGISTRY_REDHAT_IO_PASSWORD` via
`--password-stdin`. Use your Red Hat registry or service-account credentials
from the [container registry](https://access.redhat.com/terms-based-registry/)
flow, or run `podman login registry.redhat.io` once on the host before
building.

**quay.io** (push target):

Same pattern. Images are tagged `quay.io/matferna/mh-*`. If
`podman login --get-login quay.io` is empty, set `QUAY_IO_USER` (or
`QUAY_IO_USERNAME`) and `QUAY_IO_PASSWORD`, or run `podman login quay.io`
first.

**Automation Hub** (collection downloads):

Credentials are passed as `podman` build args for `ansible-builder`. If
`ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN` and
`ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN` are **not** set, the script reads
the first `token` under a `[galaxy_server.*]` section from
`/etc/ansible/ansible.cfg` (override with `SYSTEM_ANSIBLE_CFG`).

### Full example

```bash
cd execution_environments/rosa
export REGISTRY_REDHAT_IO_USER='your-registry-username'
export REGISTRY_REDHAT_IO_PASSWORD='your-registry-token'
export QUAY_IO_USER='your-quay-username'
export QUAY_IO_PASSWORD='your-quay-token-or-password'
./build.sh
```

Optional: `MERGE_REPO_ANSIBLE_CFG=1` prepends the repository root
`[defaults]` block into the EE `ansible.cfg` for that build only (restored
after the script exits).

```bash
MERGE_REPO_ANSIBLE_CFG=1 SYSTEM_ANSIBLE_CFG=/etc/ansible/ansible.cfg ./build.sh
```

## Validating a built image

```bash
execution_environments/utils/validate_ee_collections.sh quay.io/matferna/mh-rosa:latest /path/to/ee-dir
```

The second argument defaults to `../rosa` relative to the script. This runs
`podman run` + `ansible-galaxy collection list` and checks that every
collection in the EE's `requirements.yml` is present.

## Troubleshooting

**"no image found in manifest list for architecture amd64"** when running
`podman run` or `ansible-navigator`: the registry tag was probably an empty
manifest list (older `build.sh` used `podman manifest create` incorrectly).
Rebuild with the current `build.sh` (single-arch `-t` + `podman push`) or
run a locally tagged image:

```bash
podman images
podman run --rm <image_id> ansible-playbook --version
```
