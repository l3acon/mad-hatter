# self-service — Deploy Ansible Automation Portal on OpenShift

Deploys the Red Hat Ansible Automation Platform (AAP) Automation Portal
(RHAAP/Developer Hub) onto an OpenShift cluster using the upstream Helm
chart. Supports both OCI plugin delivery (default, recommended for AAP 2.7+)
and legacy tarball-based plugin registry.

## What the role does

1. **Preflight checks** — validates CLI tools (`helm`, `oc`), cluster login,
   and required variables. In tarball mode, also validates plugin tarball
   presence and plugin/chart version alignment.
2. **OAuth2 application** — creates (or recreates) an OAuth2 app in AAP
   for portal authentication.
3. **AAP token** — generates a personal access token scoped for write.
4. **OpenShift namespace** — creates the target Project (default
   `self-service`).
5. **Secrets** — writes `secrets-rhaap-portal` (AAP host, token, OAuth
   credentials) and `secrets-scm` (optional GitHub/GitLab tokens).
6. **Plugin registry** *(tarball mode only)* — builds an httpd-based image
   from local plugin tarballs, pushes it via an OpenShift BuildConfig, and
   deploys the registry pod + service. Skipped when `ssp_plugin_mode: oci`.
7. **Helm install** — adds the OpenShift Helm repo, installs or upgrades the
   `redhat-rhaap-portal` chart with the bundled `values.yml`, injecting the
   cluster router base domain and SSL flags.
8. **OAuth redirect update** — discovers the RHAAP Route and updates the AAP
   OAuth2 application with the correct redirect URI.

## AAP 2.7+ features

The portal Helm values include configuration for AAP 2.7 features:

- **EE Builder** — a visual wizard for defining Execution Environments (base
  image, collections, Python/system packages, MCP servers). Generates
  `execution-environment.yml` definitions and optional GitHub Actions build
  workflows. Enabled via the `default.ee` menu item in the Helm values.
- **Content catalog** — syncs collections from Private Automation Hub and
  discovers Ansible content in Git orgs/groups. Configured via
  `pahCollections` and `ansibleGitContents` sync providers.
- **OCI plugin delivery** — plugins are pulled as OCI artifacts from
  `registry.redhat.io` instead of from a custom tarball registry. Set
  `ssp_plugin_mode: oci` (the default).

**Note:** The EE Builder produces definition files; actual image builds happen
out-of-band via `ansible-builder` on CI/workstations or GitHub Actions.

## Prerequisites

| Requirement | Notes |
|---|---|
| `oc` CLI | Logged into the target OpenShift cluster (`oc login ...`) |
| `helm` CLI | v3+ — [install guide](https://helm.sh/docs/intro/install/) |
| AAP 2.6+ | Accessible from the control node; admin credentials required. AAP 2.7+ required for EE Builder and content catalog features. |
| Plugin tarballs | **Tarball mode only** — downloaded from the [Red Hat Customer Portal](https://access.redhat.com/downloads/content/480) and placed in `files/plugins/`. Not needed when `ssp_plugin_mode: oci`. |
| Ansible collections | `ansible.platform`, `redhat.openshift`, `kubernetes.core` (see `requirements.yml`) |
| GitHub/GitLab token | **Optional** — required for EE Builder save-to-Git and content discovery |

## Required variables

| Variable | Description |
|---|---|
| `controller_host` | AAP Controller URL, e.g. `https://aap.apps.example.com` |
| `controller_username` | AAP admin username |
| `controller_password` | AAP admin password |

## Optional variables

| Variable | Default | Description |
|---|---|---|
| `openshift_namespace` | `self-service` | OpenShift Project for the portal |
| `helm_chart_version` | `2.2.0` | Helm chart version — in tarball mode must match plugin tarball version |
| `helm_repo_url` | `https://charts.openshift.io` | Helm repo URL |
| `helm_repo_name` | `openshift-helm-charts` | Helm repo name |
| `helm_chart_name` | `redhat-rhaap-portal` | Helm chart name |
| `helm_release_name` | `self-service` | Helm release name |
| `controller_verify_ssl` | `true` | Validate AAP TLS certificates |
| `aap_ssl_verify` | `true` | Passed to the portal's AAP integration config |
| `aap_oauth_client_name` | `Self Service` | OAuth2 application name in AAP |
| `aap_organization` | `Default` | AAP organization |
| `github_token` | *(empty)* | GitHub PAT — required for EE Builder save-to-Git and content discovery |
| `gitlab_token` | *(empty)* | GitLab PAT — required for EE Builder save-to-Git and content discovery |
| `ssp_plugin_mode` | `oci` | Plugin delivery: `oci` (recommended, 2.7+) or `tarball` (legacy) |
| `ssp_ee_builder_enabled` | `true` | Enable EE Builder feature (AAP 2.7+) |
| `ssp_content_catalog_enabled` | `true` | Enable content catalog/collection discovery (AAP 2.7+) |

## Plugin files (tarball mode only)

When running with `ssp_plugin_mode: tarball`, download the portal plugin
bundles from the
[Red Hat Customer Portal](https://access.redhat.com/downloads/content/480)
and place them in `roles/self-service/files/plugins/`. The role expects four
tarballs:

```
files/plugins/
├── ansible-plugin-scaffolder-backend-module-backstage-rhaap-dynamic-<version>.tgz
├── ansible-backstage-plugin-catalog-backend-module-rhaap-dynamic-<version>.tgz
├── ansible-plugin-backstage-self-service-dynamic-<version>.tgz
└── ansible-backstage-plugin-auth-backend-module-rhaap-provider-dynamic-<version>.tgz
```

The `<version>` embedded in the filenames **must** match the `appVersion` of
the Helm chart specified by `helm_chart_version`. The preflight checks enforce
this and will fail with an actionable message if they diverge.

When using `ssp_plugin_mode: oci` (the default), plugin tarballs are not
required — plugins are pulled as OCI artifacts from `registry.redhat.io`.

## Usage

### Minimal command-line run

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword'
```

### With optional SCM tokens and a custom namespace

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  -e github_token=ghp_xxxxxxxxxxxxxxxxxxxx \
  -e openshift_namespace=my-portal
```

### With EE Builder and GitHub integration

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  -e github_token=ghp_xxxxxxxxxxxxxxxxxxxx
```

### Legacy tarball mode (pre-2.7)

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  -e ssp_plugin_mode=tarball \
  -e helm_chart_version=2.1.5
```

### Disable AAP TLS verification (lab/self-signed certs)

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  -e controller_verify_ssl=false \
  -e aap_ssl_verify=false
```

### Run only the preflight checks

```bash
ansible-playbook deploy_ssp.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  --tags preflight
```

## Tags

| Tag | Scope |
|---|---|
| `preflight` | Run only the preflight validation checks |
| `create_oauth` | Create OAuth2 application in AAP |
| `create_token` | Create AAP personal access token |
| `create_namespace` | Create the OpenShift Project |
| `create_secrets` | Create both portal and SCM secrets |
| `build_plugin` | Build the plugin registry image |
| `deploy_plugin` | Deploy the plugin registry pod + service |
| `helm` | Helm repo add + chart install/upgrade |
| `update_oauth` | Patch OAuth2 app with the final Route URL |

## Troubleshooting

### Init container `CrashLoopBackOff` with npm 404

The Helm chart's templates embed the `appVersion` into plugin registry URLs.
If the plugin tarballs are a different version, the init container gets 404s.
The preflight checks now catch this — run `--tags preflight` to verify
alignment, or check:

```bash
helm show chart openshift-helm-charts/redhat-rhaap-portal --version <chart_version>
# compare appVersion against the tarball filenames in files/plugins/
```

### `oc whoami` fails

You are not logged into an OpenShift cluster. Run `oc login` first.

### `helm: command not found`

Install Helm v3+: <https://helm.sh/docs/intro/install/>

## License

MIT-0

## Author

Arsalan Naeem — Red Hat
