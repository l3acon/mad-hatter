# Execution Environments

This directory contains Execution Environment (EE) definitions for
`ansible-builder`. Each subdirectory (`aro/`, `rosa/`, `windows/`) has its
own `execution-environment.yml`, `requirements.yml`, and `build.sh`.

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

## CI/CD

A unified GitHub Actions workflow (`.github/workflows/ee-build.yml`) builds
and pushes all EEs in this directory.

### Triggers

| Trigger | Behavior |
|---|---|
| **Manual dispatch** | Pick a single EE (`aro`, `rosa`, `windows`) or `all` from the Actions UI. |
| **Push to `main`** | Auto-detects which `execution_environments/` subdirectories changed and builds only those. Changes to `utils/` rebuild all EEs. |
| **Pull request** | Builds changed EEs without pushing (`SKIP_QUAY_PUSH=1`), validating the definition compiles. |

### Required repository secrets

Configure these under **Settings > Secrets and variables > Actions**:

| Secret | Purpose |
|---|---|
| `QUAY_IO_USERNAME` | quay.io robot or account with push access to `quay.io/matferna/mh-*` |
| `QUAY_IO_PASSWORD` | quay.io robot token or CLI password |
| `AUTOMATION_HUB_TOKEN` | Offline token for certified + validated Automation Hub Galaxy pulls |
| `REGISTRY_REDHAT_IO_USERNAME` | Red Hat registry service-account (needed for aro/rosa base images) |
| `REGISTRY_REDHAT_IO_PASSWORD` | Red Hat registry token |

### How it works

The workflow has two jobs:

1. **detect** -- determines which EE(s) to build. For dispatch events it
   reads the user's choice; for push/PR events it runs `git diff` to find
   changed subdirectories under `execution_environments/`.
2. **build** -- runs as a matrix over the detected EEs. Each matrix entry
   `cd`s into the EE's directory and runs its `build.sh`, which handles
   `ansible-builder create`, `podman build`, tagging, and pushing.

On pull requests the `SKIP_QUAY_PUSH` environment variable is set to `1`,
so the build scripts skip the quay.io login and push steps, letting the
build validate the definition without requiring registry credentials.

### Local-only builds

The same `SKIP_QUAY_PUSH` flag works locally:

```bash
SKIP_QUAY_PUSH=1 ./build.sh
```

## Automation Portal EE Builder

The AAP 2.7 Automation Portal includes a visual **EE Builder** wizard that
generates `execution-environment.yml` definitions from a 4-step UI (base
image, collections, Python/system deps, build steps). This is an EE
*definition authoring tool*, not an image builder -- the actual container
build relies on external CI/CD.

### How the Portal flow works

1. A user opens the Portal and navigates to **Self-Service > Execution
   Environments**.
2. The EE Builder wizard produces an `execution-environment.yml`,
   `ansible.cfg`, and a `.github/workflows/ee-build.yml` CI workflow
   (generated by `ansible-creator` via the `ansible-devtools-server`
   sidecar).
3. The Portal's scaffolder can **publish** the files to a new GitHub
   repository or as a pull request to an existing repo.
4. If the user opted to build, the scaffolder dispatches
   `github:actions:dispatch` against the `ee-build.yml` workflow in the
   target repo.

### Relationship to this repository

The Portal scaffolder creates **standalone** EE repos -- it does not write
into this directory. This project's own EEs (aro, rosa, windows) are
maintained here and built by the unified `.github/workflows/ee-build.yml`
workflow described above.

Both paths use the same underlying toolchain (`ansible-builder` +
`podman`/`buildah`) and the same secret/token model for Galaxy and registry
authentication.

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
