# Running the sandbox backends for real (locally)

The sandbox test suites parametrize over all three backends (`local` / `docker`
/ `ssh`), but `docker` and `ssh` are `slow`-marked and **skip unless their
runtime is present** — so a plain `uv run pytest` only truly exercises `local`.
To run the real boundaries (containment, lifecycle, the ssh sentinel path), bring
up their runtimes first. All you need is a working local docker.

## docker backend

The docker/contract/e2e tests use `python:3.12-slim`. Pull it once:

```bash
docker pull python:3.12-slim
```

With a reachable daemon + that image present, the `slow` docker tests run:

```bash
uv run pytest tests/test_sandbox_docker.py -m slow
```

## ssh backend — a throwaway sshd container

`ssh-test.Dockerfile` is a **test-only** sshd box (python3 + bash + coreutils —
the ssh backend's documented remote baseline) that authorizes a throwaway key
handed in at runtime. It is NOT hardened; never use it for anything but tests.

```bash
# 1. build the image
docker build -f docker/ssh-test.Dockerfile -t hugin-ssh-test .

# 2. a throwaway keypair
ssh-keygen -t ed25519 -f /tmp/hugin_ssh_key -N '' -q

# 3. run it, mapping sshd to localhost:2222 with your public key authorized
docker run -d --name hugin-ssh-test -p 2222:22 \
  -e AUTHORIZED_KEY="$(cat /tmp/hugin_ssh_key.pub)" hugin-ssh-test

# 4. point the suite at it (the `port` spec field targets 2222)
export HUGIN_SSH_TEST_HOST=agent@127.0.0.1
export HUGIN_SSH_TEST_PORT=2222
export HUGIN_SSH_TEST_KEY=/tmp/hugin_ssh_key

# 5. the ssh real-host tests + the cross-backend contract/e2e now run for real
uv run pytest tests/test_sandbox_ssh.py -m slow
uv run pytest tests/test_sandbox_contract.py tests/test_bash_e2e_backends.py

# cleanup
docker rm -f hugin-ssh-test
```

## everything at once

With `python:3.12-slim` pulled, the sshd container up, and the three
`HUGIN_SSH_TEST_*` vars exported, a full `uv run pytest` exercises all three
backends end to end (locally this is ~1012 passed vs ~976 with only `local`).

> Wiring this into CI needs a runner with docker (the current self-hosted runner
> has none). See `tasks/open/031-bash-sandbox-e2e-test-harness.md`.
