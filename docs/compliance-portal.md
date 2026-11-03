# Compliance dashboard evaluation

This deployment adds the pre-release compliance frontend and backend to the
Ansible Automation Portal. The compliance source and plugin images must remain
private. The Portal uses its own PostgreSQL database and connects to AAP.

## Private source

The AAP project uses `https://github.com/l3acon/aap-compliance-pipelines.git`
and the `GITHUB_PAT` environment variable as its source-control credential.
The initial private GitHub repository is a snapshot of GitLab commit
`dbfbeaf487f4a0ff815365d8e1c4b698d6be6766`: its Git tree matches that commit,
but it does not contain the GitLab history. GitHub Actions are disabled on the
evaluation repository. Update the private mirror as the upstream project
changes; do not make it public. With GitHub CLI and SSH access to the private
repository, sync a committed source revision with:

```bash
scripts/sync-compliance-mirror.sh /path/to/aap-compliance-pipelines
```

The script verifies that the destination is private, GitHub Actions are
disabled, and the snapshot matches the source tree before pushing. It copies
only the committed tree, not uncommitted changes or GitLab history. Build the
images from the same source commit to keep the plugins, execution environment,
and AAP project aligned.

## Build plugins

Use Node.js 20 or 22, Corepack, Yarn, Podman, Git, and Python 3. The build
script archives the committed source into a temporary directory, builds both
plugins, checks migration parity, and creates local OCI images for both
plugins and the RHEL 9 execution environment:

```bash
scripts/build-compliance-plugins.sh /path/to/aap-compliance-pipelines quay.io/matferna/mh-compliance-private
```

Push the printed tags only after verifying that the registry repository is
private. The script prints the OCI references to use for the Portal values.
The cluster must be able to pull the images using the supplied registry auth
file; a Podman `auth.json` containing the private registry login works. The
execution environment's public base image is pinned by digest; update that
digest deliberately when refreshing the base.

## Deploy the Portal

Log `oc` into the intended cluster, and provide a protected Ansible variables
file containing the Portal values. For example, substitute current image tags
and AAP credentials in a file readable only by your user:

```yaml
controller_host: https://AAP-GATEWAY
controller_username: admin
controller_password: YOUR_PASSWORD
controller_verify_ssl: true
aap_ssl_verify: true
ssp_compliance_enabled: true
ssp_compliance_frontend_image: 'oci://quay.io/matferna/mh-compliance-private:frontend-COMMIT!aap-compliance-plugin-compliance'
ssp_compliance_backend_image: 'oci://quay.io/matferna/mh-compliance-private:backend-COMMIT!aap-compliance-plugin-compliance-backend'
ssp_plugin_registry_auth_file: /path/to/containers/auth.json
```

Run `ansible-playbook portal-deploy.yml -e @/path/to/protected-vars.yml`.
The role preserves the existing Portal plugin list and merges private registry
authentication with the cluster's Red Hat registry credentials. Use the
cluster's trusted certificates where available.
On a rerun, it preserves the existing OAuth redirect and reuses the client
secret when the Portal secret matches the AAP application. If that secret is
lost, the application must be recreated because AAP does not reveal it again.

Portal chart 2.2's RHAAP login provider does not send a PKCE challenge. AAP
2.7 enables PKCE for new OAuth applications by default, so the role disables
it **for this Portal OAuth application only** by default. Set
`ssp_oauth_require_pkce: true` when using a Portal provider that supports it.

## Configure AAP

Set `CONTROLLER_HOST`, `CONTROLLER_USERNAME`, `CONTROLLER_PASSWORD`, and
`GITHUB_PAT`, `COMPLIANCE_REGISTRY_USERNAME`, and
`COMPLIANCE_REGISTRY_PASSWORD` for the intended AAP instance, then run:

Check `CONTROLLER_HOST` before running: a local `.env` may still point to a
different cluster than the one currently selected by `oc`.

```bash
ansible-playbook compliance-casc.yml
```

For a lab with untrusted Gateway certificates, add
`-e compliance_validate_certs=false`. The playbook creates an AAP source
credential, private project, RHEL 9 STIG execution environment, and assessment
and remediation job templates. Set `compliance_ee_image` to the tag printed
by the build script. Its defaults use the APD inventory and machine
credential. The assessment's `target_hosts` defaults to `aws-rhel9`; override
`compliance_target_hosts` if your RHEL 9 inventory host has a different name.
The remediation template also uses that value as its default job limit because
its imported playbook targets all hosts. Portal-initiated remediation can
override the limit with the selected hosts.

The assessment can temporarily install OpenSCAP and copy a SCAP datastream to
the target. Remediation changes the target and should be launched only after
reviewing findings. The compliance plugin can fall back to its configured AAP
service token when a user's AAP token is unavailable, so review the plugin's
authorization behavior and the service account's privileges before wider use.

After signing in to the Portal, register a compliance profile in **Compliance
→ Settings**. For the tested profile, use name `DISA STIG RHEL 9`, slug
`rhel9-stig`, standard `DISA STIG` (`DISA_STIG`), version `V2R8`, and platform `RHEL 9`.
Set the platform guards to OS family `RedHat` and OS version `9`. Map the scan
template to `compliance-run-oscap`, the remediation template to
`compliance-remediate`, and the execution environment to
`Compliance | RHEL 9 STIG`. Use the profile to run an assessment and review
results. With the shared APD inventory,
use `aws-rhel9:localhost` as the scan limit: the second play runs on localhost.
The current plugin checks platform compatibility against the entire inventory,
so it may warn about RHEL 10 even when the limit excludes that host.

The current evaluation build was observed sending a scan request without the
user's AAP token; the backend then used the Portal service token. In this
revision the frontend API factory constructs `ComplianceBackendClient` without
an AAP auth API. Treat this as an evaluation limitation until the project wires
the user token and verifies per-user authorization.

The configured fine-grained GitHub token can read the private evaluation
repository, but GitHub rejects it for the Red Hat organization's public
Portal template catalog because its lifetime exceeds that organization's
366-day policy. Correct the token policy or use suitable separate Portal
catalog credentials if the stock templates are needed.

The evaluation scan also exposed a results-view pagination defect: the UI
fetches 100 findings per page but uses page-local totals whenever there are
500 or fewer findings. For the test scan, the API reported 169 passes and 263
failures, while the results page displayed 100 rules and a 30.1% rate. Do not
use the results-page score for decisions until the project corrects this.
