# shellcheck shell=bash
# EE build helpers: Automation Hub token discovery and container registry logins.
# Source from execution_environments/*/build.sh

# Print the first token= value found under any [galaxy_server.*] section (trimmed).
read_automation_hub_token_from_ansible_cfg() {
  local cfg="${1:-${SYSTEM_ANSIBLE_CFG:-/etc/ansible/ansible.cfg}}"
  if [[ ! -r "$cfg" ]]; then
    return 1
  fi
  awk '
    /^\[galaxy_server\./ { in_server=1; next }
    /^\[/ { in_server=0 }
    in_server && /^token[ \t]*=/ {
      gsub(/^token[ \t]*=[ \t]*/, "")
      gsub(/[ \t]+$/, "")
      if (length($0)) { print; exit 0 }
    }
  ' "$cfg"
}

fill_galaxy_build_tokens_from_system_ansible_cfg() {
  local cfg="${SYSTEM_ANSIBLE_CFG:-/etc/ansible/ansible.cfg}"
  local tok
  if [[ -n "${ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN:-}" && -n "${ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN:-}" ]]; then
    return 0
  fi
  tok="$(read_automation_hub_token_from_ansible_cfg "$cfg")" || return 1
  if [[ -z "${ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN:-}" ]]; then
    export ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN="$tok"
  fi
  if [[ -z "${ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN:-}" ]]; then
    export ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN="$tok"
  fi
  echo "Using Automation Hub token from ${cfg} (set ANSIBLE_GALAXY_SERVER_*_TOKEN to override)."
}

# Log in to registry.redhat.io for base EE pulls if not already authenticated.
# Uses REGISTRY_REDHAT_IO_USER (or REGISTRY_REDHAT_IO_USERNAME) + REGISTRY_REDHAT_IO_PASSWORD when needed.
# See: https://access.redhat.com/terms-based-registry/
ensure_podman_redhat_registry_login() {
  local reg="registry.redhat.io"
  local who
  if who="$(podman login --get-login "$reg" 2>/dev/null)" && [[ -n "$who" ]]; then
    echo "${reg}: already logged in (${who})"
    return 0
  fi
  local user="${REGISTRY_REDHAT_IO_USER:-${REGISTRY_REDHAT_IO_USERNAME:-}}"
  local pass="${REGISTRY_REDHAT_IO_PASSWORD:-}"
  if [[ -z "$user" || -z "$pass" ]]; then
    echo "Not logged in to ${reg}."
    echo "Run: podman login ${reg}"
    echo "Or set REGISTRY_REDHAT_IO_USER and REGISTRY_REDHAT_IO_PASSWORD (password-stdin; use a registry/service account token as the password if applicable)."
    return 1
  fi
  echo "${pass}" | podman login "$reg" -u "$user" --password-stdin
  echo "Logged in to ${reg} as ${user}"
}

# Log in to quay.io for image push/pull if not already authenticated.
# Uses QUAY_IO_USER (or QUAY_IO_USERNAME) + QUAY_IO_PASSWORD when needed.
ensure_podman_quay_io_login() {
  local reg="quay.io"
  local who
  if who="$(podman login --get-login "$reg" 2>/dev/null)" && [[ -n "$who" ]]; then
    echo "${reg}: already logged in (${who})"
    return 0
  fi
  local user="${QUAY_IO_USER:-${QUAY_IO_USERNAME:-}}"
  local pass="${QUAY_IO_PASSWORD:-}"
  if [[ -z "$user" || -z "$pass" ]]; then
    echo "Not logged in to ${reg}."
    echo "Run: podman login ${reg}"
    echo "Or set QUAY_IO_USER and QUAY_IO_PASSWORD (robot account token or CLI password via --password-stdin)."
    return 1
  fi
  echo "${pass}" | podman login "$reg" -u "$user" --password-stdin
  echo "Logged in to ${reg} as ${user}"
}

# Optional: prepend non-empty [defaults] from repo ansible.cfg into EE ansible.cfg.
# $3 = path to original EE ansible.cfg (read-only); output overwrites "${ee_dir}/ansible.cfg".
merge_repo_defaults_into_ee_ansible_cfg() {
  local ee_dir="$1"
  local repo_cfg="$2"
  local orig_ee_cfg="$3"
  if [[ ! -f "$repo_cfg" ]] || [[ ! -f "$orig_ee_cfg" ]]; then
    return 0
  fi
  local block
  block="$(awk '/^\[defaults\]/{p=1;next} /^\[/{if(p)exit} p' "$repo_cfg" || true)"
  if [[ -z "${block//[$'\t\r\n ']}" ]]; then
    return 0
  fi
  {
    printf '%s\n' '# Merged [defaults] from repository ansible.cfg (MERGE_REPO_ANSIBLE_CFG=1)'
    printf '%s\n' '[defaults]'
    printf '%s\n' "$block"
    printf '\n'
    cat "$orig_ee_cfg"
  } > "${ee_dir}/ansible.cfg.tmp.$$"
  mv -f "${ee_dir}/ansible.cfg.tmp.$$" "${ee_dir}/ansible.cfg"
  echo "Merged [defaults] from ${repo_cfg} into ${ee_dir}/ansible.cfg"
}
