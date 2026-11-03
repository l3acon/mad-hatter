# Optional reboot for APD cloud patching

The **Patch Cloud Stack in AWS** workflow can optionally reboot registered
RHEL hosts after patching when `needs-restarting -r` reports that it is needed.
The workflow survey variable is `reboot`, with `false` as the default. Set it
to `true` to reboot before the RHEL post-check and compliance report. Windows
hosts are unaffected by this setting.

The RHEL patch template uses a separate AAP project, **APD Cloud Patch
(reboot)**, so other APD demos continue using their existing project. Its
source defaults to `l3acon/product-demos` on the `codex/cloud-patch-reboot`
branch. Configure `apd_patch_reboot_project_scm_url` and
`apd_patch_reboot_project_scm_branch` to use a different source.

After APD cloud setup creates the workflow and its templates, apply or reapply
the extension with:

```bash
set -a; source .env; set +a
ansible-playbook casc-deploy.yml --tags apd_patch_reboot
```

Reapply it after rerunning APD cloud setup: that setup manages the same survey
and RHEL template and may restore their upstream defaults. The extension keeps
the other survey questions and job-template settings intact. Once the change is
merged into the APD source used by the shared project, switch the RHEL template
back to that project and retire the temporary project as appropriate.

The existing workflow routes RHEL patch-job failures to snapshot restore. A
reboot timeout is a patch-job failure, so select `true` only when rebooting and
the workflow's existing restore behavior are appropriate for the target hosts.
