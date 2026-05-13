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

After install, the guest may have **no working network** until **NetKVM** (VirtIO Ethernet) is installed from the same CD (Device Manager is not available on Core — use `Get-PnpDevice`, **`pnputil /add-driver ...\NetKVM\...\*.inf /subdirs /install`**, then `Restart-NetAdapter`). See comments in `scripts/Prepare-CloudbaseInitForKubeVirt.ps1` for download examples.

## 4. Cloudbase-Init and sysprep

Script: **`scripts/Prepare-CloudbaseInitForKubeVirt.ps1`**

- Downloads Cloudbase-Init MSI from GitHub, installs silently, patches **`cloudbase-init.conf`** and **`cloudbase-init-unattend.conf`** for KubeVirt-style **NoCloud** metadata, then runs **`sysprep.exe /generalize /oobe /shutdown`** with Cloudbase’s **`Unattend.xml`**.
- Run from an **elevated** PowerShell.

### Sysprep shows only “USAGE: sysprep.exe …”

That almost always means **sysprep did not receive a valid command line**. The usual cause is **`/unattend:` pointing under `C:\Program Files\...`** when the launcher splits arguments at spaces (e.g. `Start-Process -ArgumentList` with a broken argv). The script invokes sysprep with **`&` (call operator)** so the unattend path stays a **single** argument. Re-download the script if yours still uses `Start-Process` for sysprep.

### Invocation pitfalls

| Issue | What to do |
|-------|------------|
| `Invoke-WebRequest` + second command on one line | Separate with **newline** or **`;`**. Otherwise extra tokens bind to `Invoke-WebRequest` and fail. |
| `Invoke-WebRequest` “positional parameter” | Use **named** parameters: `-Uri ... -OutFile ...`. |
| `-Confirm:$false` with **`powershell.exe -File` from cmd.exe** | `Confirm` can bind as the **string** `false` → error. Prefer **running from PowerShell**: `.\Prepare-CloudbaseInitForKubeVirt.ps1 -Confirm:$false -Verbose`, or **`powershell.exe -Command "& { .\Prepare-...ps1 -Confirm:$false -Verbose }"`**, or use **`-Force`** on the script (see script help) when using `-File` from cmd after updating the script. |

## 5. Day-2 VMs and AAP

After you have a **golden root DataVolume** name in the same namespace:

- **`../vm_create_windows_from_golden.yml`** — VM from that DV + `cloudInitNoCloud`.
- **`../vm_post_install_windows.yml`** — VMI IP, WinRM, Chocolatey bootstrap.
- CasC workflow **OpenShift Virtualization — Provision Windows VM and install package** uses the **Windows execution environment** (`execution_environments/windows/`).

## Related paths

- `../vm_create_windows_from_golden.yml`, `../vm_post_install_windows.yml`
- `../../../roles/openshift_virtualization_aap/` — job templates, workflow, EE image names
- `../../../execution_environments/windows/` — EE image build for `ansible.windows` + WinRM
