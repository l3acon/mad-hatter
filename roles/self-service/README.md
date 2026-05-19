# self-service — Deploy AAP Self-Service Automation Portal on OpenShift

Deploys the Red Hat Ansible Automation Platform (AAP) Self-Service Automation
Portal (RHAAP/Developer Hub) onto an OpenShift cluster using the upstream Helm
chart and a local plugin registry.

## What the role does

1. **Preflight checks** — validates CLI tools (`helm`, `oc`), cluster login,
   required variables, plugin tarball presence, and plugin/chart version
   alignment.
2. **OAuth2 application** — creates (or recreates) an OAuth2 app in AAP
   Controller for RHAAP authentication.
3. **AAP token** — generates a personal access token scoped for write.
4. **OpenShift namespace** — creates the target Project (default
   `self-service`).
5. **Secrets** — writes `secrets-rhaap-portal` (AAP host, token, OAuth
   credentials) and `secrets-scm` (optional GitHub/GitLab tokens).
6. **Plugin registry** — builds an httpd-based image from the local plugin
   tarballs, pushes it via an OpenShift BuildConfig, and deploys the registry
   pod + service.
7. **Helm install** — adds the OpenShift Helm repo, installs or upgrades the
   `redhat-rhaap-portal` chart with the bundled `values.yml`, injecting the
   cluster router base domain and SSL flags.
8. **OAuth redirect update** — discovers the RHAAP Route and updates the AAP
   OAuth2 application with the correct redirect URI.

## Prerequisites

| Requirement | Notes |
|---|---|
| `oc` CLI | Logged into the target OpenShift cluster (`oc login ...`) |
| `helm` CLI | v3+ — [install guide](https://helm.sh/docs/intro/install/) |
| AAP Controller | Accessible from the control node; admin credentials required |
| Plugin tarballs | Downloaded from the [Red Hat Customer Portal](https://access.redhat.com/downloads/content/480) and placed in `files/plugins/` |
| Ansible collections | `ansible.platform`, `redhat.openshift`, `kubernetes.core` (see `requirements.yml`) |

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
| `helm_chart_version` | `2.1.5` | Helm chart version — must match plugin tarball version (preflight enforces this) |
| `helm_repo_url` | `https://charts.openshift.io` | Helm repo URL |
| `helm_repo_name` | `openshift-helm-charts` | Helm repo name |
| `helm_chart_name` | `redhat-rhaap-portal` | Helm chart name |
| `helm_release_name` | `self-service` | Helm release name |
| `controller_verify_ssl` | `true` | Validate AAP TLS certificates |
| `aap_ssl_verify` | `true` | Passed to the portal's AAP integration config |
| `aap_oauth_client_name` | `Self Service` | OAuth2 application name in AAP |
| `aap_organization` | `Default` | AAP organization |
| `github_token` | *(empty)* | GitHub PAT for catalog integrations |
| `gitlab_token` | *(empty)* | GitLab PAT for catalog integrations |

## Plugin files

Download the self-service portal plugin bundles from the
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
