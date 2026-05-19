# Windows on OpenShift Virtualization (KubeVirt)

This folder supports **DataVolume-based** Windows Server eval installs, **unattend / SetupComplete** golden bootstrap, optional **Cloudbase-Init** (NoCloud), and **Ansible** automation on AAP (see CasC in `roles/openshift_virtualization_aap/`).

## Prerequisites

- `oc` logged into the cluster, `virtctl` installed locally.
- A Windows Server ISO (eval or licensed) on the machine that runs the upload playbook.
- Storage class (e.g. `gp3-csi` on ROSA) — often **WaitForFirstConsumer**: the blank OS PVC may stay **Pending** until a VM references it; that is expected.

## 1. Blank OS disk and ISO upload

| Playbook | Purpose |
|----------|---------|
| `dv_create_blank_os.yml` | Creates a blank **DataVolume** (default 60 Gi). Set **`ocpv_win_os_blank_recreate: true`** to delete the installer VM (optional) and **remove + recreate** the blank OS DV from scratch. |
| `dv_upload_iso.yml` | `virtctl image-upload` of the eval ISO into a **DataVolume** (large transfer; uses async + `--force-bind`). |
| `vm_apply_installer.yml` | Creates the **installer** `VirtualMachine` (UEFI, eval ISO + virtio driver CD + blank disk). |
| `prep_windows_install_media.yml` | Chains blank OS DV, eval ISO upload, optional **autounattend** build+upload, then installer VM. |

Defaults (override with `-e`): `ocpv_win_namespace`, `ocpv_win_storage_class`, `ocpv_win_iso_local_path`, DataVolume names, etc.

### Unattended installer / golden bootstrap (`Autounattend.xml` on a small ISO)

When **`ocpv_win_autounattend_enabled=true`** (and **`export OCPV_WIN_AUTOUNATTEND_ADMIN_PASSWORD=…`** matches the Administrator password you will use for WinRM / AAP surveys on the resulting golden), **`prep_windows_install_media.yml`** also runs **`autounattend_iso_pipeline.yml`**, which:

1. Stages **`Autounattend.xml`**, **`StageGoldenSetupComplete.ps1`**, **`GoldenBootstrap.ps1`**, and **`LoadVirtioDrivers.ps1`** (optional / legacy on-disk helper; WinPE uses **PnpCustomizationWinPE** paths instead).
2. Builds a small ISO with **xorriso** (preferred) or **genisoimage**.
3. Uploads it to DataVolume **`windows-autounattend-iso`** (override with **`-e ocpv_win_autounattend_iso_dv_name=…`**). Before upload, **`autounattend_iso_pipeline.yml`** defaults to **replacing** an existing populated DV: it removes **`windows-server-installer`** (optional) and deletes the **`windows-autounattend-iso`** DataVolume/PVC so **`virtctl image-upload`** is not blocked by *PVC already successfully populated*. Disable with **`-e ocpv_win_autounattend_replace_existing=false`** (then you must delete the DV/PVC yourself before re-upload).

**`vm_apply_installer.yml`** then adds a **fourth SATA CD-ROM** (no boot order) backed by that DataVolume. Windows Setup discovers **`Autounattend.xml`** on that volume. The unattend file:

- In **windowsPE**, **`Microsoft-Windows-PnpCustomizationWinPE`** / **`DriverPaths`** scans **`D:`–`I:`** for both **`amd64/<release>/`** (**`quay.io/kubevirt/virtio-container-disk`** layout, e.g. **`amd64/2k22`**) and **`viostor/.../amd64`** (Fedora **virtio-win.iso** layout). Some builds still show **no fixed disks** until drivers load; the answer ISO therefore ships **`WinPELoadVirtio.cmd`**, which **`Microsoft-Windows-Setup` / `RunSynchronous`** runs **before** **`DiskConfiguration`** to **`pnputil /add-driver …\*.inf /install /subdirs`** (same as a manual fix). Disable with **`-e ocpv_unattend_winpe_load_virtio=false`**. **`DriverPaths` must not** be placed under **`Microsoft-Windows-Setup`** in **windowsPE** (invalid schema). **No PowerShell** runs in WinPE from the answer file. **`DiskConfiguration`** creates **EFI + MSR + sized primary** (**`ocpv_unattend_primary_partition_mb`**, default **55000** MB — must fit the blank disk; a **~55 GB** disk needs a smaller value than **55000**). **`ModifyPartitions`** does **not** assign **`Letter`** on the OS partition in WinPE. **`InstallTo`**: **`DiskID`** / **`PartitionID` 3**. In **specialize**, **`Microsoft-Windows-Deployment` / `RunSynchronous`** runs **`StageGoldenSetupComplete.ps1`** from the answer CD. Override path list with **`ocpv_unattend_virtio_driver_subpaths`** if your virtio CD layout differs.
- Sets **Administrator** password in **UserAccounts** (no AutoLogon). **`GoldenBootstrap.ps1`** applies the same **mini-setup registry mitigations** as the clone unstick script, installs **NetKVM**, downloads **`prepare-win.ps1`** (override **`ocpv_prepare_win_ps1_url`** for forks/branches), and runs it with **`-AllowSystemContext`** so **WinRM** and **sysprep** can run under **SYSTEM** from SetupComplete. Guest logs: **`%TEMP%\ocpv-golden-bootstrap.log`**, **`%SystemRoot%\Setup\Scripts\golden-bootstrap.log`**.

**Lab discipline:** use the **same** Administrator password for **`OCPV_WIN_AUTOUNATTEND_ADMIN_PASSWORD`**, the golden build, **`OCPV_WIN_ADMIN_PASSWORD`** when validating **`controller_validate_windows_workflow.yml`**, and the AAP workflow survey.

**Local validation without uploading:**  
`ansible-playbook playbooks/openshift_virtualization/windows/autounattend_iso_pipeline.yml -e ocpv_win_autounattend_enabled=true -e ocpv_win_autounattend_upload=false -e ocpv_win_autounattend_admin_password='…'`  
prints the temp ISO path; requires **xorriso** or **genisoimage**.

**Validate `Autounattend.xml` before booting Windows:** **`validate_autounattend_local.yml`** renders **`Autounattend.xml.j2`** and runs **`xmllint`** (well‑formed XML only). Example: `ansible-playbook playbooks/openshift_virtualization/windows/validate_autounattend_local.yml -e ocpv_win_autounattend_admin_password='…'` (or export **`OCPV_WIN_AUTOUNATTEND_ADMIN_PASSWORD`**). Add **`-e ocpv_validate_autounattend_copy_to=/path/Autounattend.xml`** to keep a file for **Windows SIM**. For settings that exist on **your** Windows edition / image index, install the [Windows ADK](https://learn.microsoft.com/en-us/windows-hardware/get-started/adk-install), open **Windows System Image Manager**, create a **catalog** from the same **`install.wim`** index you install, import **`Autounattend.xml`**, and resolve red validation markers—this catches unknown components and pass mismatches that **`xmllint`** cannot see.

| Variable | Default / notes |
|----------|-----------------|
| **`ocpv_win_autounattend_enabled`** | **`false`** — set **`true`** for automated path. |
| **`ocpv_unattend_os_disk_id`** | **`0`** — WinPE disk index for the **virtio blank OS** disk; try **`1`** if **`ImageInstall`** or **`DiskConfiguration`** still fails (enumeration order). |
| **`ocpv_unattend_primary_partition_mb`** | **`55000`** — Windows primary partition size in MB (must be **less than** blank PVC capacity minus EFI/MSR). Increase or decrease if **`DiskConfiguration`** fails or you need more free space. |
| **`ocpv_unattend_wim_index`** | **`1`** — index in `install.wim` for your SKU (Core vs Desktop, etc.). |
| **`ocpv_unattend_efi_mb`** / **`ocpv_unattend_msr_mb`** | **`260`** / **`128`** — EFI and MSR sizes in MB. |
| **`ocpv_unattend_virtio_driver_subpaths`** | Optional YAML list of path suffixes (forward slashes) appended to each **`D:`–`I:`** drive for **`DriverPaths`**; defaults cover **KubeVirt virtio container** (`amd64/2k22`, …) and **virtio-win.iso** (`viostor/w11/amd64`, …). |
| **`ocpv_unattend_winpe_load_virtio`** | **`true`** — run **`WinPELoadVirtio.cmd`** from the answer ISO via **`RunSynchronous`** before **`DiskConfiguration`**. |
| **`ocpv_prepare_win_ps1_url`** | Raw GitHub URL to **`prepare-win.ps1`** on your branch/fork. |
| **`ocpv_win_autounattend_upload`** | **`true`** — set **`false`** to only build the ISO locally. |
| **`ocpv_win_autounattend_replace_existing`** | **`true`** — delete existing autounattend DV/PVC (and by default the installer VM) before upload so re-runs succeed. |
| **`ocpv_win_autounattend_delete_installer_vm_when_replace`** | **`true`** — set **`false`** to keep the installer VM (only if the autounattend ISO is not mounted / you handle conflicts). |

## 2. Installer VM and boot order

The template `templates/windows_installer_vm.yaml.j2` attaches:

1. **Windows eval ISO** (SATA CD-ROM, **boot order 1**)
2. **Blank virtio system disk** (boot order 2)
3. **VirtIO guest tools container disk** (SATA CD-ROM, **boot order 99**)
4. **Optional autounattend answer ISO** (SATA CD-ROM, **no boot order**) when **`ocpv_win_autounattend_enabled`** is **true** — DataVolume **`ocpv_win_autounattend_iso_dv_name`** (default **`windows-autounattend-iso`**). Windows Setup discovers **`Autounattend.xml`** on this volume without booting from it ahead of the eval ISO.

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

- **`../vm_create_windows_from_golden.yml`** — By default (**`ocpv_clone_golden_root`**, default **true**), creates a **CDI clone** DataVolume from the golden source, waits until **Succeeded**, then creates the VM with the **clone** as the root disk. Set **`ocpv_clone_golden_root: false`** only to attach the golden DV directly (RWO: one consumer). Optional **`ocpv_win_clone_dv_name`** overrides the clone DV name (`<vm_name>-win-os`, truncated if needed).

  **NoCloud / Cloudbase-Init:** **`ocpv_use_cloudbase_nocloud`** defaults to **`false`**. In that mode the VM has **no** `cloudInitNoCloud` volume; **Administrator on the generalized golden image must already match** **`ocpv_windows_admin_password`** (survey / WinRM). Set **`ocpv_use_cloudbase_nocloud: true`** to attach a NoCloud Secret and render **`windows_golden_nocloud.yaml.j2`** (sentinel + password + clone unstick **`runcmd`**). If **`ocpv_cloudinit_userdata`** is non-empty, a NoCloud volume is attached **regardless** of **`ocpv_use_cloudbase_nocloud`**.

**Disk lifecycle:** each provisioned VM keeps its own clone DataVolume (default naming); deleting the VM does **not** delete the clone DV—remove it with **`oc delete datavolume <name> -n <ns>`** when reclaiming space.

**KubeVirt userdata size:** when NoCloud is used, **`userData`** is stored in Secret **`<vm_name>-nocloud`** (key **`userdata`**) and referenced via **`cloudInitNoCloud.secretRef`**. Inline userData is capped at **2048 bytes**.

**Clone first boot — "The computer restarted unexpectedly":** with **`ocpv_use_cloudbase_nocloud: true`**, the default **`windows_golden_nocloud.yaml.j2`** **`runcmd`** applies the ChildCompletion / Setup mitigations (see [Windows OS Hub](https://woshub.com/windows-install-error-computer-restarted-unexpectedly/)); check **`C:\Windows\Temp\ocpv-unstick-clone-setup.log`**. With NoCloud **off**, rely on a **clean golden** from unattend / **`GoldenBootstrap.ps1`** and matching passwords; if loops persist, fix the golden disk or use **`ocpv_use_cloudbase_nocloud: true`** temporarily.

**Golden image / sysprep:** if the error **persists**, the golden DataVolume may never have reached a clean **generalized / shutdown** state. Re-run sealing or rebuild from **`dv_create_blank_os.yml`** (see **`ocpv_win_os_blank_recreate`**) plus installer media.

If you use fully custom **`ocpv_cloudinit_userdata`** with NoCloud enabled, replicate the ChildCompletion + Setup logic or apply the manual registry steps from the link above.

**RWO golden disk (legacy direct attach):** if **`ocpv_clone_golden_root: false`**, only one virt-launcher can attach the golden PVC. The playbook can fail fast when another VM still references that DV (see **`ocpv_skip_rwo_dv_conflict_check`** for RWX).

- **`../vm_post_install_windows.yml`** — VMI IP, WinRM, optional **sentinel check** (`ocpv_verify_cloudbase_init`, default **false**; set **true** when using Cloudbase + default NoCloud template), Chocolatey bootstrap.
- CasC workflow **OpenShift Virtualization | Provision Windows VM and install package** chains the two job templates. The **create** job template uses the **OpenShift Virtualization EE** (`openshift_virt_aap_ee_name`, Kubernetes API only). The **post-install** job template still uses the **Windows EE** (`openshift_virt_aap_ee_windows_name`, `ansible.windows` + **pywinrm**); that image must pull successfully on the cluster or the second node fails with worker stream / pod errors even when the first node reaches WinRM.

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

## 6. Recapturing the golden root DataVolume (`windows-server-os-work`)

Use this when **every clone** still shows the blue **“installation cannot proceed”** loop after the NoCloud unstick script, or you know the golden disk was **booted again after sysprep**, **sysprep failed**, or never finished **generalize / shutdown**. Cloud-init cannot fix a golden that never reached a clean sealed state.

### Before you start

1. **Free the golden RWO disk** — stop/delete **every** `VirtualMachine` in the namespace that still mounts **`windows-server-os-work`** (and any stuck `virt-launcher` pods). Only **one** consumer can attach it.
2. **Delete test clones** you no longer need (`oc delete vm …`, then `oc delete datavolume <vm>-win-os` if reclaiming space). Keep **`windows-server-eval-iso`** if you still use the installer path.

### Path A — Repair in place (same DV name)

Keep the existing **`windows-server-os-work`** DataVolume; you only refresh its contents from a single maintenance VM.

1. Create **one** `VirtualMachine` whose **root** volume is **`windows-server-os-work`** (same namespace). Example: use **`../vm_create_windows_from_golden.yml`** with **`ocpv_clone_golden_root: false`** and a throwaway **`ocpv_vm_name`** (or apply a minimal VM template by hand). **Do not** run a second VM on that DV.
2. **Start** the VM and open **virt console** / RDP if you have it: `virtctl console <vm> -n <ns>` (Server Core is text-only).
3. Sign in as **Administrator** (password you set during last known-good state, or reset via your org process if unknown).
4. Copy **`scripts/prepare-win.ps1`** into the guest (see script header for `Invoke-WebRequest` example from GitHub `raw`).
5. From **elevated** PowerShell:
   - First run: **`.\prepare-win.ps1 -Force -Verbose`**
   - If this disk was **generalized before** and you are re-sealing, add **`-WinRmForceNewSSLCert`** so HTTPS listener certs are rebuilt.
   - On **Server Core**, **`SysprepOobeMode`** defaults to **Auto** (no **`/oobe`**). Only force **`-SysprepOobeMode Oobe`** on SKUs that support the full OOBE wizard (see section 4 above).
   - To **debug without sysprep**: **`-SkipSysprep`**, then shut down manually when satisfied; remove **`-SkipSysprep`** for the real capture run.
6. Wait until **`sysprep` shuts the VM down** (power off is normal). Watch **`%SystemRoot%\Panther\`** logs if anything loops.
7. **Critical:** do **not** power the maintenance VM on again if you want a clean golden—another boot can dirty setup state. **`oc delete vm <maintenance-vm> -n <ns>`** (the **DataVolume** stays; only the VM object goes).
8. Point AAP workflows at **`ocpv_win_root_dv_name: windows-server-os-work`** (unchanged). Recreate clones with **`ocpv_clone_golden_root: true`** (default).

### Path B — New golden DV name (safer rollback)

1. Run **`prep_windows_install_media.yml`** (or the three DV/installer playbooks) with a **new** OS DV name, e.g. **`-e ocpv_win_os_blank_dv_name=windows-server-os-work-v2`** (and matching installer template vars if you customize names).
2. Install Windows on the installer VM, install VirtIO/NetKVM, then run **`prepare-win.ps1`** as in Path A.
3. After sysprep shutdown, delete the installer VM; keep **`windows-server-os-work-v2`** as the new golden.
4. Update the controller workflow survey / extra vars so **`ocpv_win_root_dv_name`** matches the **new** DV. When confident, delete the old **`windows-server-os-work`** DV to reclaim storage.

### After recapture

- Re-run **`playbooks/openshift_virtualization/aap_rollout_casc.yml`** only if you changed CasC; refresh **`aap_sync_openshift_credential_from_oc.yml`** if `oc` token drifted.
- Launch **OpenShift Virtualization | Provision Windows VM and install package** again (clone path uses the updated golden).

## Related paths

- `../vm_create_windows_from_golden.yml`, `../vm_post_install_windows.yml`
- `../../../roles/openshift_virtualization_aap/` — job templates, workflow, EE image names
- `../../../execution_environments/windows/` — EE image build for `ansible.windows` + WinRM
