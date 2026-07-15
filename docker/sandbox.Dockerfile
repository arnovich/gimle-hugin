# The Hugin bash-sandbox image: thick and boring on purpose.
#
# A thin image is a false economy — every binary the agent reaches for and does
# not find is a wasted turn (a failed command, a re-plan). So this ships the
# tools an agent actually uses, and nothing about Hugin itself: NO Hugin source,
# NO credentials, NO secrets. The sandbox is dumb; the stack, interactions, and
# artifacts stay host-side. Its only writable locations at runtime are the
# bind-mounted /workspace and a small tmpfs /tmp (the rootfs is mounted
# read-only by DockerSandbox).
#
# Build (from repo root):
#   docker build -f docker/sandbox.Dockerfile -t gimle/hugin-sandbox:latest .
#
# In production this should be pinned by digest, scanned (Trivy/Grype), signed
# (cosign), and verified on pull — the tag here is for local iteration.

# Pin the base by digest in production; the tag is the human-readable anchor.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Boring, widely-used tooling: a POSIX userland, git, search/JSON, an HTTP
# client, and the three runtimes agents most often shell out to (python, uv,
# node). Kept to one layer; caches removed so the image stays lean-ish.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        coreutils \
        curl \
        findutils \
        git \
        jq \
        less \
        nodejs \
        npm \
        python3 \
        python3-venv \
        ripgrep \
        tini; \
    rm -rf /var/lib/apt/lists/*

# uv (fast Python package manager) into a system path on PATH for every user.
RUN set -eux; \
    curl -LsSf https://astral.sh/uv/install.sh \
      | env UV_INSTALL_DIR=/usr/local/bin sh; \
    uv --version

# The workspace is a bind mount at runtime; declare it so tools relying on the
# directory existing behave even if run before the mount is populated.
RUN mkdir -p /workspace
WORKDIR /workspace

# DockerSandbox runs the container as the host user (a non-root uid) with an
# idle PID and execs each command; keep a default that is harmless if run bare.
CMD ["sleep", "infinity"]
