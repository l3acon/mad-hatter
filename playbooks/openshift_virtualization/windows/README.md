# Windows on OpenShift Virtualization (KubeVirt)

This folder supports **DataVolume-based** Windows Server eval installs, **Cloudbase-Init** sealing, and **Ansible** automation on AAP (see CasC in `roles/openshift_virtualization_aap/`).

## Prerequisites

- `oc` logged into the cluster, `virtctl` installed locally.
- A Windows Server ISO (eval or licensed) on the machine that runs the upload playbook.
- Storage class (e.g. `gp3-csi` on ROSA) — often **WaitForFirstConsumer**: the blank OS PVC may stay **Pending** until a VM references it; that is expected.

## 1. Blank OS disk and ISO upload

| Playbook | Purpose |
|----------|---------|
| `dv_create_blank_os.yml` | Creates a blank **DataVolume** (default 60 Gi) for the Windows system disk. |
| `dv_upload_iso.yml` | `virtctl image-upload` of the eval ISO into a **DataVolume** (large transfer; uses async + `--force-bind`). |
| `vm_apply_installer.yml` | Creates the **installer** `VirtualMachine` (UEFI, eval ISO + virtio driver CD + blank disk). |
| `prep_windows_install_media.yml` | Chains the three playbooks above. |

Defaults (override with `-e`): `ocpv_win_namespace`, `ocpv_win_storage_class`, `ocpv_win_iso_local_path`, DataVolume names, etc.

## 2. Installer VM and boot order

The template `templates/windows_installer_vm.yaml.j2` attaches:

1. **Windows eval ISO** (SATA CD-ROM, **boot order 1**)
2. **Blank virtio system disk** (boot order 2)
3. **VirtIO guest tools container disk** (SATA CD-ROM, **boot order 99**)

If the **virtio driver CD** is tried before the ISO, firmware may not boot setup. **Always keep the eval ISO lowest boot order** and the virtio CD **last**.

## 3. VirtIO drivers (manual on Server Core)

Windows does not ship VirtIO block or network drivers. From the **virtio** CD attached to the installer VM you must install drivers by hand (no full GUI on Server Core).

### Storage: see the **install / system disk** (virtio block)

During setup (or afterward in Core), Windows may not see the virtio **system disk** until the **VirtIO SCSI / block (viostor)** driver is loaded from the virtio CD (**Load driver** in setup, or `pnputil` against the `viostor` / `vioscsi` INF tree on the CD). Without this, the installer target disk can stay invisible or unusable.

### Network

After install, the guest may have **no working network** until **NetKVM** (VirtIO Ethernet) is installed from the same CD (Device Manager is not available on Core — use `Get-PnpDevice`, **`pnputil /add-driver ...\NetKVM\...\*.inf /subdirs /install`**, then `Restart-NetAdapter`). See **`scripts/prepare-win.ps1`** header comments for download examples.

## 4. `prepare-win.ps1` — WinRM, firewall, Cloudbase-Init, sysprep

Primary script: **`scripts/prepare-win.ps1`**. The legacy filename **`scripts/Prepare-CloudbaseInitForKubeVirt.ps1`** is a thin wrapper that forwards to it (same parameters as before).

Run from an **elevated** PowerShell. Typical flow:

1. **Ansible `ConfigureRemotingForAnsible.ps1`** — Downloaded from the [Ansible documentation examples](https://raw.githubusercontent.com/ansible/ansible-documentation/refs/heads/devel/examples/scripts/ConfigureRemotingForAnsible.ps1) unless you pass **`-ConfigureRemotingScriptPath`**. Enables PowerShell remoting / WinRM, **`LocalAccountTokenFilterPolicy`**, HTTP and HTTPS listeners, and the firewall rules that script adds. **`-WinRmSkipNetworkProfileCheck`** defaults to **true** so a **Public** NIC profile (common on lab VMs) does not block setup.
2. **Disable Windows Firewall** for **Domain / Private / Public** profiles (`Set-NetFirewallProfile`, with **`netsh advfirewall set allprofiles state off`** fallback) so **host** firewall does not block AAP execution environments from reaching **5985/5986** (cluster **NetworkPolicy** may still restrict traffic).
3. **Cloudbase-Init** — MSI from GitHub, patches **`cloudbase-init.conf`** only (see below), then **`sysprep.exe /generalize [/oobe] /shutdown`** with Cloudbase’s **`Unattend.xml`**. On **Windows Server Core**, **`/oobe` is omitted by default** so setup does not try to launch the OOBE wizard (see below).

**`cloudbase-init-unattend.conf` is left stock.** Rewriting it (or half-replacing multi-line `metadata_services`) can break the sysprep specialize path and cause **reboot / recovery loops**.

Optional switches: **`-SkipWinRmConfiguration`**, **`-SkipFirewallDisable`** (not recommended for AAP), **`-AnsibleConfigureRemotingUri`**, **`-WinRmCertValidityDays`**, **`-WinRmForceNewSSLCert`**, **`-WinRmGlobalHttpFirewallAccess`**, **`-WinRmEnableCredSSP`**, plus **`-SkipSysprep`**, **`-SysprepOobeMode`**, **`-CloudbaseVersion`**, **`-MsiDownloadUri`**, **`-Force`**.

### Sysprep / reboot loop after running the script

Likely causes we have seen:

1. **Corrupt `cloudbase-init.conf`** — Cloudbase ships **`metadata_services=` as a multi-line comma list**. Replacing only the **first** line leaves invalid continuation lines; the parser misbehaves and Windows can enter **specialize / OOBE recovery loops**.
2. **Editing `cloudbase-init-unattend.conf` unnecessarily** — the unattend phase expects Cloudbase’s default layout; keep it unless you know exactly what to change.

The script now **removes the entire `metadata_services` block** (multi-line aware), inserts **one** clean line, sets **`config_drive_cdrom`** / **`config_drive_raw_hhd`**, writes **UTF-8 without BOM**, and **stops** the `cloudbase-init` service before sysprep.

**Recovery:** restore from `cloudbase-init.conf.bak.<timestamp>` next to the file, then reinstall Cloudbase or rerun a fixed script.

### `setuperr.log`: `[msoobe.exe] Failed to create the wizard … hr=0x80040154`

**`0x80040154`** is **`REGDB_E_CLASSNOTREG`** (a COM class is not registered). **`msoobe.exe`** is the **OOBE** (out-of-box experience) shell. On **Windows Server Core**, the full OOBE wizard stack is not present, so **`sysprep … /oobe`** can fail in **`UnattendGC\setuperr.log`** with this pattern even though other steps look fine.

**What to do:** on **Windows Server Core** the script omits **`/oobe`** automatically. You can force the same behavior on any SKU with **`-SysprepOobeMode NoOobe`**. Microsoft documents that after **`/generalize /shutdown`**, the next boot still runs the **specialize** configuration pass, which is what Cloudbase’s **`Unattend.xml`** relies on. If you truly need interactive OOBE, install **Server with Desktop Experience** (or a client SKU) instead of Core.

The drive letter in paths (for example **`F:\Windows\Panther\…`**) is whatever volume Windows assigned during setup or recovery; the same log files live under **`%SystemRoot%\Panther\`** on the system volume.

### Sysprep shows only “USAGE: sysprep.exe …”

That almost always means **sysprep did not receive a valid command line**. The usual cause is **`/unattend:` pointing under `C:\Program Files\...`** when the launcher splits arguments at spaces (e.g. `Start-Process -ArgumentList` with a broken argv). The script invokes sysprep with **`&` (call operator)** so the unattend path stays a **single** argument. Re-download the script if yours still uses `Start-Process` for sysprep.

### Invocation pitfalls

| Issue | What to do |
|-------|------------|
| `Invoke-WebRequest` + second command on one line | Separate with **newline** or **`;`**. Otherwise extra tokens bind to `Invoke-WebRequest` and fail. |
| `Invoke-WebRequest` “positional parameter” | Use **named** parameters: `-Uri ... -OutFile ...`. |
| `-Confirm:$false` with **`powershell.exe -File` from cmd.exe** | `Confirm` can bind as the **string** `false` → error. Prefer **running from PowerShell**: `.\prepare-win.ps1 -Confirm:$false -Verbose`, or **`powershell.exe -Command "& { .\prepare-win.ps1 -Confirm:$false -Verbose }"`**, or use **`-Force`** when using `-File` from cmd after updating the script. |

## 5. Day-2 VMs and AAP

After you have a **golden root DataVolume** name in the same namespace:

- **`../vm_create_windows_from_golden.yml`** — By default (**`ocpv_clone_golden_root`**, default **true**), creates a **CDI clone** DataVolume from the golden source (`spec.source.pvc` → existing golden DV/PVC), waits until the clone is **Succeeded**, then creates the VM with the **clone** as the root disk so the golden RWO volume is never attached to more than one launcher. Set **`ocpv_clone_golden_root: false`** only to attach the golden DV directly (legacy; subject to RWO exclusivity). Optional **`ocpv_win_clone_dv_name`** overrides the default clone DV name (`<vm_name>-win-os`, truncated if the VM name is very long). When **`ocpv_cloudinit_userdata`** is not set, the playbook renders **`windows/windows_golden_nocloud.yaml.j2`**: a **sentinel file** under `C:\Windows\Temp\.ocpv-cloudbase-init-sentinel` and an **Administrator** **`users`** entry (plaintext **`passwd`**, per [cloudbase-init cloud-config](https://cloudbase-init.readthedocs.io/en/latest/userdata.html)) so the guest password matches **`ocpv_windows_admin_password`** from the workflow survey before WinRM connects.

**Disk lifecycle:** each provisioned VM keeps its own clone DataVolume (default naming); deleting the VM does **not** delete the clone DV—remove it with **`oc delete datavolume <name> -n <ns>`** when reclaiming space.

**Clone first boot — "The computer restarted unexpectedly" / "Windows installation cannot proceed":** after a **block-level clone** of a generalized disk, Windows sometimes leaves **`SystemSetupInProgress`** or **`OOBEInProgress`** set so mini-setup shows that blue recovery screen. The default **`windows_golden_nocloud.yaml.j2`** ships a one-time **`runcmd`** script (disable with **`ocpv_cloudinit_clear_clone_setup_state: false`**) that clears those registry values, sets **`ImageState`** to **`IMAGE_STATE_COMPLETE`**, and reboots once when stuck. If you use fully custom **`ocpv_cloudinit_userdata`**, replicate that logic or apply the manual registry fix from Microsoft’s guidance for stuck OOBE/mini-setup.

**RWO golden disk (legacy direct attach):** if **`ocpv_clone_golden_root: false`**, the usual golden root PVC is **ReadWriteOnce**—only one virt-launcher can attach it. The playbook can fail fast when another VM still references that DV (see **`ocpv_skip_rwo_dv_conflict_check`** for RWX).

- **`../vm_post_install_windows.yml`** — VMI IP, WinRM, optional **sentinel check** (`ocpv_verify_cloudbase_init`, default true), Chocolatey bootstrap.
- CasC workflow **OpenShift Virtualization | Provision Windows VM and install package** chains the two job templates. The **create** job template uses the **OpenShift Virtualization EE** (`openshift_virt_aap_ee_name`, Kubernetes API only). The **post-install** job template still uses the **Windows EE** (`openshift_virt_aap_ee_windows_name`, `ansible.windows` + **pywinrm**); that image must pull successfully on the cluster or the second node fails with worker stream / pod errors even when the first node and cloudbase-init are fine.

### KubeVirt inventory with WinRM defaults (CasC)

CasC adds a second dynamic inventory **`OpenShift Virtualization | KubeVirt VMs (WinRM)`** (see `roles/openshift_virtualization_aap/defaults/main.yml`: `openshift_virt_aap_kubevirt_winrm_inventory_*`). It uses the same **`openshift_virtualization`** sync and namespaces as the primary KubeVirt inventory, and sets **inventory-level** variables so synced hosts default to **`ansible_connection: winrm`**, **`ansible_winrm_scheme: http`**, **`ansible_winrm_transport: ntlm`**, **`ansible_winrm_server_cert_validation: ignore`**, **`ansible_port: 5985`**. Re-run **`playbooks/openshift_virtualization/aap_rollout_casc.yml`** after pulling these changes, then **sync** both inventory sources in the controller UI (or wait for `update_on_launch`).

### Troubleshoot WinRM from AAP

Job template **OpenShift Virtualization | Troubleshoot Windows WinRM connectivity** runs **`vm_troubleshoot_windows_winrm.yml`**: **`wait_for`** to the VMI IP on **5985** from the execution environment (same network path as **pywinrm**), lists **NetworkPolicies** in the VM namespace and **`aap`**, then an **HTTP POST to `/wsman`** (no **`ansible.windows`** required on the EE). Launch with **Limit** = the KubeVirt inventory host (usually **`<namespace>-<vmname>`**), extra vars **namespace / VM name**, and **prompt for your WinRM Machine credential** when **`ask_credential_on_launch`** is enabled.

### Optional NetworkPolicy (OCP egress)

If namespaces use **default-deny** egress, automation pods may need an explicit allow rule to reach VM overlay IPs on **5985/5986**. See **`manifests/example-networkpolicy-aap-egress-winrm.yaml`** (edit namespaces and tighten **`podSelector`**); apply with **`oc apply`**. This is cluster-specific—use only when policy analysis shows blocked egress.

### WinRM: Ansible remoting script (also inside `prepare-win.ps1`)

**`prepare-win.ps1`** downloads and runs **`ConfigureRemotingForAnsible.ps1`** before disabling the firewall and installing Cloudbase-Init, so a golden image is ready for **HTTP 5985** / **HTTPS 5986** and the usual Ansible variables. For air-gapped builds, copy the script from [ansible-documentation](https://raw.githubusercontent.com/ansible/ansible-documentation/refs/heads/devel/examples/scripts/ConfigureRemotingForAnsible.ps1) and pass **`-ConfigureRemotingScriptPath`**.

That upstream script is intended for lab/eval (self-signed certs). Production should use CA-signed certificates and stricter auth. See [Managing Windows with WinRM](https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html#winrm-setup).

After **sysprep / generalize**, clones may need **`-WinRmForceNewSSLCert`** if you re-run the Ansible script and HTTPS fails because the listener certificate no longer matches the new machine identity.

#### Ansible variables (`ansible.builtin.winrm`)

Use the [winrm connection plugin](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/winrm_connection.html) (short name **`winrm`**). Credentials usually come from **`ansible_user`** / **`ansible_password`** (or a Machine credential in AAP); the plugin also honors **`ansible_winrm_user`** / **`ansible_winrm_password`**.

| Variable | Role |
|----------|------|
| **`ansible_connection`** | Must be **`winrm`** for this plugin (alternative: **`psrp`** with `ansible_psrp_*`; see the same [WinRM guide](https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html)). |
| **`ansible_host`** | Reachable address of the guest (KubeVirt inventory sets this from the VMI). |
| **`ansible_port`** or **`ansible_winrm_port`** | **`5985`** for HTTP, **`5986`** for HTTPS (plugin default is **5986** if scheme implies TLS—set explicitly when using HTTP). |
| **`ansible_winrm_scheme`** | **`http`** or **`https`** (must match the listener you target). |
| **`ansible_winrm_transport`** | Auth wrapper: **`ntlm`** for local or domain accounts without Kerberos setup; **`basic`** only with TLS or when you accept the risk; **`kerberos`** in AD (see [Kerberos](https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html#kerberos-and-negotiate)); **`credssp`** only if you need delegation (see [CredSSP](https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html#credssp)). |
| **`ansible_winrm_server_cert_validation`** | Use **`ignore`** when the guest uses the script’s **self-signed** HTTPS certificate (or set **`ansible_winrm_ca_trust_path`** to a PEM chain you trust). |
| **`ansible_winrm_connection_timeout`** | Optional; raises WS-Man / HTTP read timeouts for slow networks (see plugin docs). |
| **`ansible_winrm_message_encryption`** | Optional **`always`** for stricter message-level encryption over HTTP when using **`psrp`** / **`winrm`** (see [encryption](https://docs.ansible.com/ansible/latest/os_guide/windows_winrm.html#winrm-encryption)). |

**Two common profiles after `ConfigureRemotingForAnsible.ps1`:**

1. **HTTP 5985 + NTLM** (matches **`vm_post_install_windows.yml`** defaults): NTLM encrypts the payload over HTTP, which Ansible documents as acceptable for this transport. Set **`ansible_connection: winrm`**, **`ansible_port: 5985`**, **`ansible_winrm_scheme: http`**, **`ansible_winrm_transport: ntlm`**, **`ansible_winrm_server_cert_validation: ignore`** (ignored for HTTP; harmless).

2. **HTTPS 5986 + NTLM** (aligns with the script’s TLS listener): **`ansible_port: 5986`**, **`ansible_winrm_scheme: https`**, **`ansible_winrm_transport: ntlm`**, **`ansible_winrm_server_cert_validation: ignore`** until you replace the cert with one your controllers trust.

Pick **one** listener (5985 or 5986) consistently in **`wait_for`**, inventory host vars, and firewall/network policy.

## Related paths

- `../vm_create_windows_from_golden.yml`, `../vm_post_install_windows.yml`
- `../../../roles/openshift_virtualization_aap/` — job templates, workflow, EE image names
- `../../../execution_environments/windows/` — EE image build for `ansible.windows` + WinRM
