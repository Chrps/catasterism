FROM python:3.12-slim-bookworm

ARG USERNAME=dev

RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
      curl \
      less \
      ripgrep \
      jq \
      build-essential \
      unzip \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash --uid 1000 ${USERNAME} 2>/dev/null \
    || usermod --login ${USERNAME} --home /home/${USERNAME} --move-home "$(id -nu 1000)"

# Node is needed only to run Claude Code. Fetched as a tarball (with arch
# detection) so this works on any Debian/Ubuntu-based image, amd64 or arm64.
ARG NODE_VERSION=22.12.0
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) NODE_ARCH=x64 ;; \
      arm64) NODE_ARCH=arm64 ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
      | tar -xJ -C /usr/local --strip-components=1 --no-same-owner

# Installed globally as root so the unprivileged user can't modify it.
RUN npm install -g @anthropic-ai/claude-code && npm cache clean --force

# Bun: the client toolchain (see PLAN.md 12.5b). Installed to /usr/local/bin as
# root for the same reason as Claude Code. The x64 build needs AVX2; swap to
# bun-linux-x64-baseline if the host CPU predates it.
ARG BUN_VERSION=1.2.21
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) BUN_ARCH=x64 ;; \
      arm64) BUN_ARCH=aarch64 ;; \
      *) echo "unsupported architecture" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/bun.zip \
      "https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}/bun-linux-${BUN_ARCH}.zip"; \
    unzip -q /tmp/bun.zip -d /tmp; \
    install -m 0755 /tmp/bun-linux-${BUN_ARCH}/bun /usr/local/bin/bun; \
    rm -rf /tmp/bun.zip /tmp/bun-linux-${BUN_ARCH}; \
    bun --version

# Config and history live here. A fresh named volume inherits the
# ownership of the image directory it shadows, which is why these are
# created and chowned before the volumes are attached.
RUN mkdir -p /home/${USERNAME}/.claude /commandhistory /workspace \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.claude /commandhistory /workspace

USER ${USERNAME}
WORKDIR /workspace
ENV SHELL=/bin/bash
