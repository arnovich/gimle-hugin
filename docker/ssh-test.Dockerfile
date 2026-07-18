# A disposable sshd box for exercising the ssh sandbox backend in CI (and
# locally). It is NOT a hardened image and must never be used for anything but
# tests: it authorizes a throwaway key handed in at runtime and runs sshd in the
# foreground. It carries exactly the remote baseline the ssh backend assumes —
# bash + coreutils (timeout/base64/find) + python3 — so the containment gate
# (`python3 -c 'os.system("id")'`) and the env-scrubbed wrapper run for real.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openssh-server bash coreutils findutils \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd \
    && useradd -m -s /bin/bash agent \
    && printf 'PasswordAuthentication no\nPermitRootLogin no\n' \
        >> /etc/ssh/sshd_config

COPY docker/ssh-test-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
