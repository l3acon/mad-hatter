#!/usr/bin/env bash
# Build private Portal plugin images from a committed compliance source tree.
# Images are built locally; push them only to a registry you have made private.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <compliance-source-directory> <private-image-repository>" >&2
  exit 2
fi

source_dir=$(cd "$1" && pwd)
image_repo=${2%/}
commit=$(git -C "$source_dir" rev-parse HEAD)
short_commit=${commit:0:7}
work_dir=$(mktemp -d "${TMPDIR:-/tmp}/compliance-build.XXXXXXXX")
trap 'rm -rf "$work_dir"' EXIT

for tool in git node corepack podman python3 tar; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done
node_major=$(node -p 'Number(process.versions.node.split(".")[0])')
if [[ "$node_major" != 20 && "$node_major" != 22 ]]; then
  echo 'Use Node.js 20 or 22 to build the compliance plugins.' >&2
  exit 1
fi

echo "Building compliance source commit $commit in an isolated directory"
git -C "$source_dir" archive HEAD | tar -xf - -C "$work_dir"
cd "$work_dir/backstage-app"
export HUSKY=0 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
corepack yarn install --immutable
corepack yarn tsc -b plugins/compliance-common plugins/compliance-backend
corepack yarn workspace @aap-compliance/plugin-compliance-backend export-dynamic
corepack yarn workspace @aap-compliance/plugin-compliance export-dynamic

python3 - <<'PY'
from pathlib import Path
import shutil
p = Path('plugins/compliance-backend')
typescript = {f.stem for f in (p / 'src/database/migrations').glob('*.ts')}
javascript = {f.stem for f in (p / 'migrations').glob('*.js')}
if not typescript or typescript != javascript:
    raise SystemExit(f'Migration parity failed: missing={sorted(typescript-javascript)}, extra={sorted(javascript-typescript)}')
for dest in (p / 'dist-dynamic/migrations', p / 'dist-dynamic/dist/database/migrations'):
    dest.mkdir(parents=True, exist_ok=True)
    for migration in (p / 'migrations').glob('*.js'):
        shutil.copy2(migration, dest / migration.name)
print(f'Included {len(javascript)} compiled database migrations')
PY

cli="$work_dir/backstage-app/node_modules/.bin/rhdh-cli"
(cd plugins/compliance && "$cli" plugin package --tag "$image_repo:frontend-$short_commit")
(cd plugins/compliance-backend && "$cli" plugin package --tag "$image_repo:backend-$short_commit")
ee_context="$work_dir/ee-context"
mkdir -p "$ee_context/collection"
cp -R "$work_dir/profiles/rhel9-stig/ansible_collections/security/compliance_rhel9_stig/." "$ee_context/collection/"
cat > "$ee_context/Containerfile" <<'EOF'
FROM ghcr.io/cross-logic/compliance-stig-rhel9@sha256:e9604a97a5aab03560625383b42d4f58dff7d0cf610922f017f3e8c551014a73
USER 0
RUN rm -rf /usr/share/ansible/collections/ansible_collections/security/compliance_rhel9_stig
COPY collection/ /usr/share/ansible/collections/ansible_collections/security/compliance_rhel9_stig/
USER 1000
EOF
podman build --platform linux/amd64 --tag "$image_repo:ee-$short_commit" \
  -f "$ee_context/Containerfile" "$ee_context"
printf '\nBuilt locally from %s. Push only to your private registry:\n' "$commit"
printf '  %s:frontend-%s\n  %s:backend-%s\n  %s:ee-%s\n' "$image_repo" "$short_commit" "$image_repo" "$short_commit" "$image_repo" "$short_commit"
printf 'Portal plugin references:\n  oci://%s:frontend-%s!aap-compliance-plugin-compliance\n' "$image_repo" "$short_commit"
printf '  oci://%s:backend-%s!aap-compliance-plugin-compliance-backend\n' "$image_repo" "$short_commit"
