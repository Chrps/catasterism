#!/usr/bin/env bash
# Build + enter the sandbox with plain Docker (no devcontainer CLI needed).
#   ./.devcontainer/run.sh           -> interactive shell
#   ./.devcontainer/run.sh claude   -> straight into claude
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="star-sandbox"

docker build -t "$IMAGE" "$REPO/.devcontainer"

docker volume create star-claude-config >/dev/null
docker volume create star-bash-history >/dev/null

exec docker run --rm -it \
  --security-opt=no-new-privileges \
  --cap-drop=ALL \
  -v "$REPO:/workspace" \
  -v star-claude-config:/home/dev/.claude \
  -v star-bash-history:/commandhistory \
  -e HISTFILE=/commandhistory/.bash_history \
  -w /workspace \
  "$IMAGE" "${@:-bash}"
