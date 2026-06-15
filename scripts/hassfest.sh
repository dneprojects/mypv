#!/usr/bin/env bash
# Run Home Assistant's hassfest against this integration.
#
# hassfest ships with the Home Assistant core source tree, not on PyPI. This
# repository is developed nested inside the core checkout, so we locate the
# core root one level up. When the core checkout is not present (e.g. a
# standalone clone) the check is skipped instead of failing the commit.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
core_root="$(cd "${repo_root}/.." && pwd)"

if [ ! -d "${core_root}/script/hassfest" ]; then
  echo "hassfest: Home Assistant core checkout not found at ${core_root}; skipping." >&2
  exit 0
fi

integration_path="${repo_root#"${core_root}"/}/custom_components/mypv"
cd "${core_root}"
exec python -m script.hassfest \
  --integration-path "${integration_path}" \
  --action validate
