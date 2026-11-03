#!/usr/bin/env bash
# Copy a committed GitLab tree to the private GitHub evaluation mirror.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <compliance-source-directory>" >&2
  exit 2
fi
for tool in git gh tar; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done

source_dir=$(cd "$1" && pwd)
source_commit=$(git -C "$source_dir" rev-parse HEAD)
source_tree=$(git -C "$source_dir" rev-parse 'HEAD^{tree}')
repository=l3acon/aap-compliance-pipelines

# Never push the pre-release tree until both checks succeed. Actions must stay
# disabled so the upstream release workflows do not run in this mirror.
if [[ $(gh api "repos/$repository" --jq '.private and .default_branch == "main"') != true ]]; then
  echo "The GitHub evaluation repository must be private and use main." >&2
  exit 1
fi
if [[ $(gh api "repos/$repository/actions/permissions" --jq '.enabled') != false ]]; then
  echo "Disable GitHub Actions on the evaluation repository before syncing." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/compliance-mirror.XXXXXXXX")
trap 'rm -rf "$work_dir"' EXIT
GIT_LFS_SKIP_SMUDGE=1 git clone --quiet --depth 1 --single-branch --branch main \
  "git@github.com:$repository.git" "$work_dir/mirror"
git -C "$work_dir/mirror" rm --quiet -r --ignore-unmatch -- .
git -C "$source_dir" archive "$source_commit" | tar -xf - -C "$work_dir/mirror"
git -C "$work_dir/mirror" add --force --all
mirror_tree=$(git -C "$work_dir/mirror" write-tree)
if [[ "$mirror_tree" != "$source_tree" ]]; then
  echo "The snapshot differs from the source Git tree; nothing was pushed." >&2
  exit 1
fi
if git -C "$work_dir/mirror" diff --cached --quiet; then
  echo "The private mirror already matches source commit $source_commit."
  exit 0
fi
git -C "$work_dir/mirror" commit -m "Sync compliance evaluation snapshot $source_commit"
git -C "$work_dir/mirror" push origin HEAD:main
echo "Updated the private mirror from source commit $source_commit."
