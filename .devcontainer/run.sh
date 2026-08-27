#!/usr/bin/env bash
# Build + enter the sandbox with plain Docker (no devcontainer CLI needed).
#   ./.devcontainer/run.sh           -> interactive shell
#   ./.devcontainer/run.sh claude    -> straight into claude, auto mode
#
# Auto mode is safe here precisely because the container is the boundary: only
# this repo is mounted, the user is unprivileged, and there is no sudo.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="catasterism-sandbox"

docker build -t "$IMAGE" "$REPO/.devcontainer"

docker volume create catasterism-claude-config >/dev/null
docker volume create catasterism-bash-history >/dev/null

# `claude` alone starts in auto permission mode; anything else runs verbatim.
if [ "${1:-}" = "claude" ]; then
  shift
  set -- claude --permission-mode auto "$@"
fi

exec docker run --rm -it \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  -v "$REPO:/workspace" \
  -v catasterism-claude-config:/home/dev/.claude \
  -v catasterism-bash-history:/commandhistory \
  -e HISTFILE=/commandhistory/.bash_history \
  -w /workspace \
  "$IMAGE" "${@:-bash}"
